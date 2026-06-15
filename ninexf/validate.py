"""Shallow validation: does the code parse, does the entry point run, do the tests pass.

Per the PRD this is intentionally not semantic. Runs happen in a subprocess
with a stripped environment and a timeout. On macOS, when allow_network is
false, the run is wrapped in sandbox-exec with a deny-network profile
(best-effort: falls back to an unwrapped run if sandbox-exec is unavailable).
"""

from __future__ import annotations

import py_compile
import re
import subprocess
import sys
import ast
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

DENY_NETWORK_PROFILE = '(version 1)(allow default)(deny network*)'


@dataclass
class ValidationResult:
    passed: bool
    detail: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tests_ran: int = 0
    tests_failed: list[str] = field(default_factory=list)
    failure_kind: str = ""
    error_excerpt: str = ""
    error_signature: str = ""


def run_sandboxed(
    project_dir: Path,
    cmd: list[str],
    timeout: float,
    allow_network: bool,
) -> tuple[int, str]:
    """Run a command in the project dir with a stripped env, timeout, and
    (on macOS, best-effort) no network. Returns (returncode, combined output).
    Used by both validation and agent-created tool runs. -1 means timeout."""
    if not allow_network and sys.platform == "darwin":
        sandboxed = ["sandbox-exec", "-p", DENY_NETWORK_PROFILE, *cmd]
        probe = subprocess.run(
            ["sandbox-exec", "-p", DENY_NETWORK_PROFILE, "true"],
            capture_output=True, cwd=project_dir,
        )
        if probe.returncode == 0:
            cmd = sandboxed
    env = {"PATH": "/usr/bin:/bin", "HOME": str(project_dir)}
    try:
        result = subprocess.run(
            cmd, cwd=project_dir, env=env,
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        pieces = []
        for part in (getattr(e, "stdout", None), getattr(e, "stderr", None),
                     getattr(e, "output", None)):
            if not part:
                continue
            if isinstance(part, bytes):
                pieces.append(part.decode(errors="replace"))
            else:
                pieces.append(str(part))
        excerpt = "\n".join(pieces).strip()
        return -1, (f"timed out after {timeout}s"
                    + (f"\nPartial output:\n{excerpt[-3000:]}" if excerpt else ""))
    output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    return result.returncode, output


def _compile_check(paths: list[Path]) -> list[str]:
    errors = []
    for p in paths:
        if p.suffix != ".py":
            continue
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{p.name}: {e.msg.strip().splitlines()[-1] if e.msg else 'syntax error'}")
        except Exception as e:  # unreadable file etc.
            errors.append(f"{p.name}: {e}")
    return errors


def _entry_point(project_dir: Path) -> Path | None:
    for candidate in ("src/main.py", "src/app.py", "src/cli.py"):
        p = project_dir / candidate
        if p.exists():
            return p
    return None


def _tail(text: str, n: int = 8) -> str:
    return " | ".join(text.strip().splitlines()[-n:])


def _failure_excerpt(text: str, max_chars: int = 4000) -> str:
    """Keep the actionable part of unittest/subprocess output."""
    stripped = text.strip()
    if not stripped:
        return ""
    blocks = re.findall(
        r"=+\n(?:ERROR|FAIL): .*?(?=\n=+\n|\n-+\nRan \d+ tests?|\Z)",
        stripped,
        flags=re.S,
    )
    footer = ""
    m = re.search(r"-+\nRan \d+ tests?.*?(?:FAILED .*|OK)\s*$", stripped, flags=re.S)
    if m:
        footer = m.group(0)
    if blocks:
        excerpt = "\n\n".join(blocks[:2] + ([footer] if footer else []))
        return excerpt[-max_chars:]
    return stripped[-max_chars:]


def _signature(text: str) -> str:
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "_", str(text))
    s = re.sub(r"/\S+", "_", s)
    s = re.sub(r"\d+", "_", s)
    return s.strip().lower()[:300]


def _slow_test_errors(project_dir: Path, threshold: float = 0.5) -> list[str]:
    """Static guard for obvious self-defeating tests."""
    errors = []
    for p in sorted((project_dir / "tests").glob("test_*.py")):
        try:
            source = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                    owner = getattr(node.func.value, "id", "")
                    full = f"{owner}.{name}" if owner else name
                elif isinstance(node.func, ast.Name):
                    full = node.func.id
                else:
                    full = ""
                if full in {"time.sleep", "sleep"}:
                    rel = p.relative_to(project_dir)
                    rendered = ast.get_source_segment(source, node) or f"{full}(...)"
                    errors.append(
                        f"slow_test: {rel} calls {rendered}; tests must not sleep"
                    )
                    continue
                if full in {"time.time", "time.monotonic", "time.perf_counter"}:
                    rel = p.relative_to(project_dir)
                    rendered = ast.get_source_segment(source, node) or f"{full}()"
                    errors.append(
                        f"slow_test: {rel} calls {rendered}; inject a clock or use "
                        "fixed timestamps in tests"
                    )
                    continue
                if isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "assertGreater", "assertGreaterEqual", "assertTrue"
                }:
                    text = ast.get_source_segment(source, node) or ""
                    if any(term in text for term in ("elapsed", "time.time", "seconds")):
                        rel = p.relative_to(project_dir)
                        errors.append(
                            f"slow_test: {rel} asserts wall-clock timing; "
                            "tests must be fast and deterministic"
                        )
    return errors


def _entry_static_errors(project_dir: Path, script: Path) -> list[str]:
    """Fail obvious slow or non-terminating demos before subprocess timeout."""
    try:
        source = script.read_text()
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    rel = script.relative_to(project_dir)
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                owner = getattr(node.func.value, "id", "")
                full = f"{owner}.{node.func.attr}" if owner else node.func.attr
            elif isinstance(node.func, ast.Name):
                full = node.func.id
            else:
                full = ""
            if full in {"time.sleep", "sleep"}:
                rendered = ast.get_source_segment(source, node) or f"{full}(...)"
                errors.append(
                    f"slow_entry: {rel} calls {rendered}; entry points must "
                    "demonstrate quickly without sleeping"
                )
        elif isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                errors.append(
                    f"slow_entry: {rel} contains while True; entry points must terminate"
                )
    return errors


class _HTMLProbe(HTMLParser):
    """Small stdlib-only HTML probe for local static UI checks."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.text_parts: list[str] = []
        self.style_text: list[str] = []
        self._skip_text = 0
        self._in_style = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        lowered = tag.lower()
        self.tags.append((lowered, attrs_dict))
        if lowered == "script":
            self._skip_text += 1
        elif lowered == "style":
            self._in_style += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "script" and self._skip_text:
            self._skip_text -= 1
        elif lowered == "style" and self._in_style:
            self._in_style -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.style_text.append(data)
        elif not self._skip_text and data.strip():
            self.text_parts.append(data.strip())


_DASHBOARD_TERMS = (
    "dashboard", "metric", "metrics", "kpi", "analytics", "chart", "charts",
    "graph", "graphs", "data", "revenue", "traffic", "conversion",
)


def _inside_project(project_dir: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(project_dir.resolve())
        return True
    except ValueError:
        return False


def _display_rel(project_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_dir.resolve()))
    except ValueError:
        return str(path)


def _frontend_html_files(project_dir: Path, written_files: list[Path]) -> list[Path]:
    frontend_written = [
        p for p in written_files
        if p.suffix.lower() in {".html", ".htm", ".css", ".js", ".mjs"}
        and _inside_project(project_dir, p)
    ]
    if not frontend_written:
        return []
    html_files = {
        p for p in written_files
        if p.suffix.lower() in {".html", ".htm"} and _inside_project(project_dir, p)
    }
    for root in (project_dir / "src", project_dir):
        if root.exists():
            for p in root.rglob("*.html"):
                if ".git" not in p.parts and _inside_project(project_dir, p):
                    html_files.add(p)
    return sorted(html_files)


def _resolve_local_asset(project_dir: Path, html_file: Path, href: str) -> tuple[Path | None, str | None]:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        return None, "external URL"
    if not parsed.path:
        return None, "empty path"
    if parsed.path.startswith("/"):
        candidate = project_dir / parsed.path.lstrip("/")
    else:
        candidate = html_file.parent / parsed.path
    candidate = candidate.resolve()
    if not _inside_project(project_dir, candidate):
        return candidate, "outside project"
    return candidate, None


def _add_phase_issue(
    errors: list[str],
    warnings: list[str],
    phase: str,
    message: str,
    *,
    final_only: bool = False,
) -> None:
    if final_only and phase == "build":
        warnings.append("product_warning: " + message)
    else:
        errors.append(message)


def _has_dashboard_intent(html_file: Path, source: str, visible_text: str) -> bool:
    haystack = f"{html_file.name} {source} {visible_text}".lower()
    return any(term in haystack for term in _DASHBOARD_TERMS)


def _numeric_value_count(text: str) -> int:
    return len(re.findall(r"(?<![\w.])[$]?\d[\d,]*(?:\.\d+)?[kKmMbB]?%?(?![\w.])", text))


def _has_visible_chart(probe: _HTMLProbe, source: str) -> bool:
    tags = [tag for tag, _ in probe.tags]
    if "table" in tags:
        cells = sum(1 for tag in tags if tag in {"td", "th"})
        rows = tags.count("tr")
        if cells >= 4 or rows >= 3:
            return True
    if "svg" in tags:
        marks = sum(1 for tag in tags if tag in {
            "rect", "path", "circle", "line", "polyline", "polygon", "text"
        })
        if marks >= 3:
            return True
    if any(tag in {"meter", "progress"} for tag in tags):
        return True
    visual_classes = 0
    for tag, attrs in probe.tags:
        if tag not in {"div", "span", "li"}:
            continue
        label = f"{attrs.get('class', '')} {attrs.get('id', '')}".lower()
        style = attrs.get("style", "").lower()
        if any(term in label for term in ("bar", "spark", "chart", "graph")) and (
            re.search(r"(width|height)\s*:\s*\d", style)
            or re.search(r"aria-valuenow\s*=", source, re.I)
        ):
            visual_classes += 1
    return visual_classes >= 3


def _svg_number(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", value)
    return float(m.group(1)) if m else None


def _svg_geometry_errors(probe: _HTMLProbe, rel: str) -> list[str]:
    errors: list[str] = []
    for tag, attrs in probe.tags:
        if tag == "svg":
            viewbox = attrs.get("viewbox") or attrs.get("viewBox")
            if viewbox:
                nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", viewbox)]
                if len(nums) == 4 and (nums[2] <= 0 or nums[3] <= 0):
                    errors.append(
                        f"frontend_static: {rel}: svg viewBox has non-positive size {viewbox!r}"
                    )
        if tag == "rect":
            width = _svg_number(attrs.get("width"))
            height = _svg_number(attrs.get("height"))
            if width is not None and width <= 0:
                errors.append(
                    f"frontend_static: {rel}: svg rect has non-positive width {attrs.get('width')!r}"
                )
            if height is not None and height < 0:
                errors.append(
                    f"frontend_static: {rel}: svg rect has negative height {attrs.get('height')!r}; "
                    "use a positive height and adjust y for negative values"
                )
    return errors


def _load_script_sources(project_dir: Path, assets: list[Path]) -> list[str]:
    sources: list[str] = []
    for asset in assets:
        if asset.suffix.lower() not in {".js", ".mjs"}:
            continue
        try:
            sources.append(asset.read_text())
        except (OSError, UnicodeDecodeError):
            continue
    return sources


def _load_text_sources(assets: list[Path], suffixes: set[str]) -> list[str]:
    sources: list[str] = []
    for asset in assets:
        if asset.suffix.lower() not in suffixes:
            continue
        try:
            sources.append(asset.read_text())
        except (OSError, UnicodeDecodeError):
            continue
    return sources


def _js_defines_chart(js_sources: list[str]) -> bool:
    for source in js_sources:
        if re.search(r"\bclass\s+Chart\b", source):
            return True
        if re.search(r"\bfunction\s+Chart\b", source):
            return True
        if re.search(r"\b(?:const|let|var)\s+Chart\s*=", source):
            return True
        if re.search(r"(?:window|globalThis|self|this)\.Chart\s*=", source):
            return True
        if re.search(r"\bChart\s*=", source):
            return True
    return False


def _js_uses_chart(js_sources: list[str]) -> bool:
    return any(re.search(r"\bnew\s+Chart\s*\(", source) for source in js_sources)


def _js_draws_canvas(js_sources: list[str]) -> bool:
    drawing_terms = (
        "lineTo(", "stroke(", "fillRect(", "arc(", "beginPath(", "moveTo(",
        "bezierCurveTo(", "quadraticCurveTo(", "strokeText(", "fillText(",
    )
    for source in js_sources:
        if "getContext(" not in source:
            continue
        if any(term in source for term in drawing_terms):
            return True
    return False


def _canvas_runtime_issue(js_sources: list[str]) -> str:
    if _js_uses_chart(js_sources) and not _js_defines_chart(js_sources):
        return ("script code instantiates Chart(...) but no local chart library "
                "or Chart implementation is loaded")
    return ""


def _has_canvas_chart_signal(probe: _HTMLProbe, js_sources: list[str]) -> bool:
    tags = [tag for tag, _ in probe.tags]
    if "canvas" not in tags:
        return False
    if _js_draws_canvas(js_sources):
        return True
    if _js_uses_chart(js_sources) and _js_defines_chart(js_sources):
        return True
    return False


def _dashboard_quality_warnings(probe: _HTMLProbe, css_sources: list[str]) -> list[str]:
    warnings: list[str] = []
    css_blob = "\n".join(css_sources).lower()
    if not css_blob:
        return warnings
    responsive_cues = (
        "@media", "minmax(", "clamp(", "flex-wrap", "grid-template-columns",
        "repeat(", "max-width", "min-width",
    )
    if not any(cue in css_blob for cue in responsive_cues):
        warnings.append(
            "product_warning: frontend_static: dashboard-like CSS lacks clear responsive layout cues "
            "(e.g. media queries, minmax, grid columns, or flex-wrap)"
        )
    styling_hits = sum(
        1 for cue in ("background", "border-radius", "box-shadow", "padding", "gap", "font-size")
        if cue in css_blob
    )
    if styling_hits < 4:
        warnings.append(
            "product_warning: frontend_static: dashboard-like CSS appears visually sparse; "
            "add stronger spacing, hierarchy, and surface styling"
        )
    if "100vh" in css_blob or "height: 100vh" in css_blob:
        warnings.append(
            "product_warning: frontend_static: dashboard-like CSS relies on 100vh/full-height layout; "
            "this is often brittle on small or mobile viewports"
        )
    metric_blocks = sum(
        1 for tag, attrs in probe.tags
        if tag in {"div", "section", "article", "li"}
        and any(term in f"{attrs.get('class', '')} {attrs.get('id', '')}".lower()
                for term in ("metric", "kpi", "card", "stat"))
    )
    if metric_blocks < 3:
        warnings.append(
            "product_warning: frontend_static: dashboard-like HTML has fewer than three obvious metric/card blocks"
        )
    return warnings


def _frontend_static_errors(
    project_dir: Path,
    written_files: list[Path],
    phase: str,
) -> tuple[list[str], list[str], bool]:
    """Catch broken local HTML/CSS wiring and empty dashboard-shaped output.

    This is intentionally a shallow guard. It does not grade design taste, but
    it prevents the Run6 failure mode where an unstyled page with an empty
    chart placeholder passes because Python validation had nothing to execute.
    """
    errors: list[str] = []
    warnings: list[str] = []
    html_files = _frontend_html_files(project_dir, written_files)
    if not html_files:
        return errors, warnings, False
    written_css = [
        p for p in written_files
        if p.suffix.lower() == ".css" and _inside_project(project_dir, p)
    ]

    for html_file in html_files:
        rel = _display_rel(project_dir, html_file)
        try:
            source = html_file.read_text()
        except (OSError, UnicodeDecodeError) as e:
            errors.append(f"frontend_static: {rel}: cannot read HTML: {e}")
            continue
        probe = _HTMLProbe()
        try:
            probe.feed(source)
        except Exception as e:
            errors.append(f"frontend_static: {rel}: cannot parse HTML: {e}")
            continue
        errors.extend(_svg_geometry_errors(probe, rel))

        stylesheet_links = []
        stylesheet_assets: list[Path] = []
        valid_stylesheets = 0
        for tag, attrs in probe.tags:
            if tag != "link":
                continue
            rel_attr = attrs.get("rel", "").lower()
            href = attrs.get("href", "").strip()
            if "stylesheet" not in rel_attr:
                continue
            stylesheet_links.append(href)
            asset, problem = _resolve_local_asset(project_dir, html_file, href)
            if problem:
                errors.append(
                    f"frontend_static: {rel}: stylesheet link {href!r} uses {problem}; "
                    "use a local CSS file under src/"
                )
                continue
            if asset is None or not asset.exists():
                target = _display_rel(project_dir, asset) if asset and _inside_project(project_dir, asset) else href
                _add_phase_issue(
                    errors,
                    warnings,
                    phase,
                    f"frontend_static: {rel}: stylesheet link {href!r} does not resolve "
                    f"to an existing file ({target})",
                    final_only=not written_css,
                )
                continue
            valid_stylesheets += 1
            stylesheet_assets.append(asset)

        script_srcs = []
        script_assets: list[Path] = []
        for tag, attrs in probe.tags:
            if tag != "script":
                continue
            src = attrs.get("src", "").strip()
            if not src:
                continue
            script_srcs.append(src)
            asset, problem = _resolve_local_asset(project_dir, html_file, src)
            if problem:
                errors.append(
                    f"frontend_static: {rel}: script src {src!r} uses {problem}; "
                    "use a local JS file under src/"
                )
                continue
            if asset is None or not asset.exists():
                target = _display_rel(project_dir, asset) if asset and _inside_project(project_dir, asset) else src
                _add_phase_issue(
                    errors,
                    warnings,
                    phase,
                    f"frontend_static: {rel}: script src {src!r} does not resolve "
                    f"to an existing file ({target})",
                    final_only=True,
                )
                continue
            script_assets.append(asset)

        js_sources = _load_script_sources(project_dir, script_assets)
        css_sources = _load_text_sources(stylesheet_assets, {".css"})
        runtime_issue = _canvas_runtime_issue(js_sources)
        if runtime_issue and (
            any(tag == "canvas" for tag, _ in probe.tags)
            or any(term in source.lower() for term in ("chart", "charts", "graph", "graphs"))
        ):
            _add_phase_issue(
                errors,
                warnings,
                phase,
                f"frontend_static: {rel}: {runtime_issue}",
                final_only=False,
            )

        visible_text = " ".join(probe.text_parts)
        dashboard_like = _has_dashboard_intent(html_file, source, visible_text)
        has_inline_style = bool("".join(probe.style_text).strip())
        if dashboard_like and not valid_stylesheets and not has_inline_style:
            if stylesheet_links:
                _add_phase_issue(
                    errors,
                    warnings,
                    phase,
                    f"frontend_static: {rel}: dashboard-like HTML has no valid stylesheet loaded",
                    final_only=not written_css,
                )
            else:
                _add_phase_issue(
                    errors,
                    warnings,
                    phase,
                    f"frontend_static: {rel}: dashboard-like HTML needs local CSS or a "
                    "non-empty <style> block; avoid browser-default rendering",
                    final_only=not written_css,
                )

        empty_visual = re.search(
            r"<(?P<tag>div|section|article)\b[^>]*(?:class|id)=['\"][^'\"]*"
            r"(?:chart|graph|metric|kpi)[^'\"]*['\"][^>]*>\s*</(?P=tag)>",
            source,
            flags=re.I | re.S,
        )
        if dashboard_like and empty_visual:
            errors.append(
                f"frontend_static: {rel}: dashboard/chart/metric containers must "
                "contain visible content, not empty placeholders"
            )

        if dashboard_like:
            warnings.extend(_dashboard_quality_warnings(probe, css_sources))
            if len(re.findall(r"<svg\b", source, flags=re.I)) > 1:
                warnings.append(
                    f"product_warning: frontend_static: {rel}: multiple nested SVG regions detected; "
                    "confirm chart markup is intentional and not duplicating the root svg container"
                )
            numbers = _numeric_value_count(visible_text)
            if numbers < 3:
                _add_phase_issue(
                    errors,
                    warnings,
                    phase,
                    f"frontend_static: {rel}: dashboard-like HTML exposes only "
                    f"{numbers} numeric value(s); include real metric values/data points",
                    final_only=True,
                )
            chart_terms = any(term in source.lower() for term in ("chart", "charts", "graph", "graphs"))
            has_visible_chart = _has_visible_chart(probe, source) or _has_canvas_chart_signal(probe, js_sources)
            if chart_terms and not has_visible_chart:
                _add_phase_issue(
                    errors,
                    warnings,
                    phase,
                    f"frontend_static: {rel}: chart/graph language is present but "
                    "no visible chart marks, table data, bars, meter, or progress elements were found",
                    final_only=True,
                )

    return errors, warnings, True


def _import_check(project_dir: Path, written: list[Path], timeout: float, allow_network: bool) -> list[str]:
    """Execute each written src module in the sandbox (runpy, not __main__).
    Catches what compile-check can't: missing imports, module-level NameErrors,
    broken cross-module imports. Without this, a project with no entry point
    gets zero execution feedback and the loop builds on broken foundations."""
    errors = []
    for p in written:
        if p.suffix != ".py":
            continue
        rel = p.relative_to(project_dir)
        if rel.parts[0] != "src":
            continue
        code = (
            "import sys, runpy; sys.path.insert(0, 'src'); "
            f"runpy.run_path({str(rel)!r})"
        )
        rc, out = run_sandboxed(project_dir, [sys.executable, "-c", code], timeout, allow_network)
        if rc != 0:
            errors.append(f"{rel}: import/exec failed: {_failure_excerpt(out, 1500)}")
    return errors


def _run_entry(project_dir: Path, script: Path, timeout: float, allow_network: bool) -> list[str]:
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, str(script.relative_to(project_dir))],
        timeout, allow_network,
    )
    if rc != 0:
        return [f"{script.name}: exit {rc}: {_failure_excerpt(out, 1500)}"]
    return []


def _run_tests(project_dir: Path, timeout: float, allow_network: bool) -> tuple[int, list[str]]:
    """Run unittest discovery over tests/. Returns (tests_ran, failures)."""
    if not list((project_dir / "tests").glob("test_*.py")):
        return 0, []
    # unittest discovery needs the start dir to be importable
    init_py = project_dir / "tests" / "__init__.py"
    if not init_py.exists():
        init_py.touch()
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        timeout, allow_network,
    )
    m = re.search(r"Ran (\d+) tests?", out)
    ran = int(m.group(1)) if m else 0
    if rc != 0:
        return ran, [f"tests: exit {rc}: {_failure_excerpt(out)}"]
    return ran, []


def run_acceptance(project_dir: Path, timeout: float, allow_network: bool) -> tuple[bool | None, int]:
    """Run the held-out acceptance suite (acceptance/test_*.py), if present.
    Returns (passed, tests_ran); passed=None when there is no suite. Kept
    separate from validate() — acceptance failing mid-build is expected; it
    gates verify_done, not commits."""
    if not list((project_dir / "acceptance").glob("test_*.py")):
        return None, 0
    init_py = project_dir / "acceptance" / "__init__.py"
    if not init_py.exists():
        init_py.touch()
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, "-m", "unittest", "discover", "-s", "acceptance", "-t", "."],
        timeout, allow_network,
    )
    m = re.search(r"Ran (\d+) tests?", out)
    ran = int(m.group(1)) if m else 0
    return rc == 0, ran


def validate(
    project_dir: Path,
    written_files: list[Path],
    timeout: float,
    allow_network: bool,
    run_tests: bool = True,
    phase: str = "final",
) -> ValidationResult:
    errors = _compile_check(written_files)
    warnings: list[str] = []
    detail_parts = ["compile-check"]
    tests_ran, tests_failed = 0, []
    if not errors:
        errors = _import_check(project_dir, written_files, timeout, allow_network)
        if any(p.suffix == ".py" and p.relative_to(project_dir).parts[0] == "src"
               for p in written_files):
            detail_parts.append("import-check")
    if not errors:
        frontend_errors, frontend_warnings, frontend_checked = _frontend_static_errors(
            project_dir, written_files, phase
        )
        if frontend_checked:
            detail_parts.append("frontend-static")
        errors.extend(frontend_errors)
        warnings.extend(frontend_warnings)
    if not errors:
        entry = _entry_point(project_dir)
        if entry is not None:
            errors = _entry_static_errors(project_dir, entry)
            if not errors:
                errors = _run_entry(project_dir, entry, timeout, allow_network)
            detail_parts.append(f"ran {entry.relative_to(project_dir)}")
        if run_tests:
            slow_errors = _slow_test_errors(project_dir)
            if slow_errors:
                errors.extend(slow_errors)
            else:
                tests_ran, tests_failed = _run_tests(project_dir, timeout, allow_network)
                if tests_ran or tests_failed:
                    detail_parts.append(f"{tests_ran} tests")
                errors.extend(tests_failed)
    first_error = errors[0] if errors else ""
    failure_kind = ""
    if errors:
        if "timed out after" in first_error:
            failure_kind = "timeout"
        elif first_error.startswith("slow_entry:"):
            failure_kind = "slow_entry"
        elif first_error.startswith("slow_test:"):
            failure_kind = "slow_test"
        elif first_error.startswith("frontend_static:"):
            failure_kind = "frontend_static"
        elif first_error.startswith("tests:"):
            failure_kind = "tests"
        elif "import/exec failed" in first_error:
            failure_kind = "import"
        elif "exit " in first_error:
            failure_kind = "entry"
        else:
            failure_kind = "compile"
    return ValidationResult(
        passed=not errors,
        detail=" + ".join(detail_parts)
        + (f" ({len(warnings)} product warning(s))" if warnings else ""),
        errors=errors,
        warnings=warnings,
        tests_ran=tests_ran,
        tests_failed=tests_failed,
        failure_kind=failure_kind,
        error_excerpt=_failure_excerpt(first_error),
        error_signature=_signature(first_error),
    )
