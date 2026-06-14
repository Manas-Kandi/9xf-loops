"""Task list and acceptance criteria: TASKS.md + ACCEPTANCE.md.

Both files are harness-managed (the agent reads them in its prompts but cannot
write them — root-level files are outside the sandbox's writable dirs). They
are committed, so task-state changes are part of the research artifact.

TASKS.md format (line-oriented so a 7B model reads it fluently):

    [ ] T1: todo
    [~] T2: in progress
    [x] T3: done
    [!] T4: deferred (failed too many times)

ACCEPTANCE.md format:

    C1: one observable, checkable statement

Unparseable lines are kept verbatim (never destroyed) and reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TASKS_FILENAME = "TASKS.md"
ACCEPTANCE_FILENAME = "ACCEPTANCE.md"

TASKS_HEADER = "# 9xf tasks — managed by the harness, do not edit"
ACCEPTANCE_HEADER = "# Acceptance criteria — managed by the harness"

TASK_LINE_RE = re.compile(r"^\[(?P<status>.)\]\s*T(?P<num>\d+):\s*(?P<text>.+?)\s*$")
CRITERION_LINE_RE = re.compile(r"^C(?P<num>\d+):\s*(?P<text>.+?)\s*$")

# Decompose-output parsing: tolerate "- TASK:", "1. TASK:", "TASK 3:", etc.
DECOMPOSE_TASK_RE = re.compile(r"^[\s\-*]*(?:\d+[.)]\s*)?TASK(?:\s*\d*)?:\s*(?P<text>.+?)\s*$")
DECOMPOSE_CRITERION_RE = re.compile(
    r"^[\s\-*]*(?:\d+[.)]\s*)?CRITERION(?:\s*\d*)?:\s*(?P<text>.+?)\s*$"
)

STATUS_TODO = " "
STATUS_IN_PROGRESS = "~"
STATUS_DONE = "x"
STATUS_DEFERRED = "!"

BAD_DECOMPOSITION_PATTERNS = (
    "venv",
    "virtual environment",
    "activate",
    ".gitignore",
    "pip install",
    "npm install",
    "package install",
    "install dependencies",
    "flake8",
    "pytest",
)

BAD_CRITERION_PATTERNS = (
    "created and empty",
    "exists and is empty",
    "file is empty",
)

FRONTEND_SCAFFOLD_PATTERNS = (
    "basic html structure",
    "basic structure",
    "basic styling",
    "empty container",
    "placeholder",
    "container div",
    "div for charts",
    "div for graphs",
    "charts and graphs div",
    "charts-and-graphs",
)

ROOT_WRITE_PATTERNS = (
    "root",
    "project root",
    "repo root",
)

ALLOWED_GENERATED_DIRS = {"src", "tests", "tools"}
COMMON_NONWRITABLE_DIRS = {
    "app", "apps", "assets", "css", "dist", "docs", "js", "lib", "public",
    "scripts", "static", "styles",
}
ROOT_FILE_RE = re.compile(
    r"(?<![\w/.-])[\w.-]+\.(?:html|css|js|mjs|ts|tsx|jsx|py)(?![\w/.-])",
    re.IGNORECASE,
)


@dataclass
class Task:
    num: int
    text: str
    status: str = STATUS_TODO  # " " | "~" | "x" | "!"

    @property
    def open(self) -> bool:
        return self.status in (STATUS_TODO, STATUS_IN_PROGRESS)


@dataclass
class TaskList:
    tasks: list[Task] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)  # kept verbatim, reported

    def get(self, num: int) -> Task | None:
        for t in self.tasks:
            if t.num == num:
                return t
        return None

    def open_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.open]

    def eligible_task(self) -> Task | None:
        """The next task the planner may execute.

        TASKS.md is ordered work. Allowing arbitrary open tasks lets small
        models jump ahead to tests or polish before the core API exists, which
        was a major Run4 failure mode.
        """
        return next((t for t in sorted(self.tasks, key=lambda t: t.num) if t.open), None)

    def all_resolved(self) -> bool:
        return bool(self.tasks) and not self.open_tasks()

    def counts(self) -> tuple[int, int]:
        """(done, total) — deferred tasks count as resolved but not done."""
        done = sum(1 for t in self.tasks if t.status == STATUS_DONE)
        return done, len(self.tasks)

    def next_num(self) -> int:
        return max((t.num for t in self.tasks), default=0) + 1


def tasks_path(project_dir: Path) -> Path:
    return project_dir / TASKS_FILENAME


def acceptance_path(project_dir: Path) -> Path:
    return project_dir / ACCEPTANCE_FILENAME


def load_tasks(project_dir: Path) -> TaskList:
    path = tasks_path(project_dir)
    tl = TaskList()
    if not path.exists():
        return tl
    for line in path.read_text().splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = TASK_LINE_RE.match(line)
        if m:
            tl.tasks.append(Task(
                num=int(m.group("num")),
                text=m.group("text"),
                status=m.group("status"),
            ))
        else:
            tl.unparsed.append(line)
    return tl


def save_tasks(project_dir: Path, tl: TaskList) -> None:
    lines = [TASKS_HEADER]
    for t in sorted(tl.tasks, key=lambda t: t.num):
        lines.append(f"[{t.status}] T{t.num}: {t.text}")
    lines += tl.unparsed  # never destroy lines we couldn't parse
    tasks_path(project_dir).write_text("\n".join(lines) + "\n")


def load_criteria(project_dir: Path) -> list[tuple[int, str]]:
    path = acceptance_path(project_dir)
    if not path.exists():
        return []
    criteria = []
    for line in path.read_text().splitlines():
        m = CRITERION_LINE_RE.match(line.rstrip())
        if m:
            criteria.append((int(m.group("num")), m.group("text")))
    return criteria


def save_criteria(project_dir: Path, criteria: list[str]) -> None:
    lines = [ACCEPTANCE_HEADER]
    lines += [f"C{i}: {text}" for i, text in enumerate(criteria, start=1)]
    acceptance_path(project_dir).write_text("\n".join(lines) + "\n")


def parse_decomposition(text: str) -> tuple[list[str], list[str]]:
    """Extract TASK:/CRITERION: lines from a decompose-mode model reply."""
    tasks, criteria = [], []
    for line in text.splitlines():
        m = DECOMPOSE_TASK_RE.match(line)
        if m:
            tasks.append(m.group("text"))
            continue
        m = DECOMPOSE_CRITERION_RE.match(line)
        if m:
            criteria.append(m.group("text"))
    return tasks, criteria


def _path_token(token: str) -> str:
    return token.strip(".,;:()[]{}\"'")


def _looks_like_path(token: str) -> bool:
    """Separate real paths from English alternatives like pie/donut or bar/point."""
    if "/" not in token:
        return False
    if token.startswith(("/", "./", "../", "~/")):
        return True
    parts = [p for p in token.split("/") if p]
    if not parts:
        return False
    first = parts[0]
    if first in ALLOWED_GENERATED_DIRS or first in COMMON_NONWRITABLE_DIRS:
        return True
    # dashboard.js, index.html, test_main.py, etc. are much more likely paths
    # than prose choices such as pie/donut, bar/point, or HTML/CSS.
    return any("." in part for part in parts)


def _mentions_forbidden_path(text: str) -> bool:
    """True when a generated task points at an obvious non-writable file/path."""
    lowered = text.lower()
    if any(p in lowered for p in ROOT_WRITE_PATTERNS):
        return True
    if ROOT_FILE_RE.search(text):
        return True
    paths = re.findall(r"`([^`]+)`|(?:^|\s)([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)", text)
    for quoted, bare in paths:
        candidate = (quoted or bare).strip()
        if not candidate or "/" not in candidate:
            continue
        tokens = [candidate] if bare else candidate.split()
        path_tokens = [
            _path_token(token)
            for token in tokens
            if _looks_like_path(_path_token(token))
        ]
        for token in path_tokens:
            first = token.split("/", 1)[0]
            if first not in ALLOWED_GENERATED_DIRS:
                return True
    return False


def _is_frontend_goal(goal: str) -> bool:
    lowered = goal.lower()
    return any(term in lowered for term in (
        "html", "css", "web page", "webpage", "website", "frontend",
        "front-end", "ui", "dashboard",
    ))


def _is_dashboard_goal(goal: str) -> bool:
    lowered = goal.lower()
    return any(term in lowered for term in (
        "dashboard", "metric", "metrics", "kpi", "analytics", "chart",
        "charts", "graph", "graphs", "data",
    ))


def _frontend_quality_rejections(
    goal: str,
    tasks: list[str],
    criteria: list[str],
) -> list[str]:
    if not _is_dashboard_goal(goal):
        return []
    blob = " ".join(tasks + criteria).lower()
    criteria_blob = " ".join(criteria).lower()
    rejections: list[str] = []

    has_metric_requirement = (
        re.search(r"\b(metric|metrics|kpi|stat|stats|card|cards)\b", criteria_blob)
        and re.search(r"\b(value|values|number|numeric|data|percent|percentage|currency|sample)\b", criteria_blob)
    )
    has_chart_requirement = (
        re.search(r"\b(chart|charts|graph|graphs|bar|line|sparkline|svg|table)\b", criteria_blob)
        and re.search(r"\b(visible|data|point|points|mark|marks|bar|bars|line|rows|not empty|non-empty)\b", criteria_blob)
    )
    has_style_requirement = (
        re.search(r"\b(css|stylesheet|style|layout|responsive|polished|clean visual|visual)\b", criteria_blob)
        and "basic styling" not in criteria_blob
    )
    if not (has_metric_requirement and has_chart_requirement and has_style_requirement):
        missing = []
        if not has_metric_requirement:
            missing.append("metric/data-value criterion")
        if not has_chart_requirement:
            missing.append("visible chart/graph criterion")
        if not has_style_requirement:
            missing.append("non-basic styling/layout criterion")
        rejections.append(
            "FRONTEND: decomposition lacks " + ", ".join(missing)
        )

    if "empty" in blob and re.search(r"\b(chart|graph|metric|kpi)\b", blob):
        rejections.append("FRONTEND: decomposition allows empty visual placeholders")
    return rejections


def sanitize_decomposition(
    goal: str,
    tasks: list[str],
    criteria: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Drop generated work items that violate harness constraints.

    The goal is allowed to explicitly request unusual setup. Otherwise,
    decomposition must stay inside the write sandbox and stdlib test harness.
    Returns (tasks, criteria, rejection reasons).
    """
    goal_l = goal.lower()
    frontend_goal = _is_frontend_goal(goal)
    rejections: list[str] = []
    rejected_scaffold = False

    def keep(kind: str, text: str) -> bool:
        nonlocal rejected_scaffold
        lowered = text.lower()
        hits = [p for p in BAD_DECOMPOSITION_PATTERNS
                if p in lowered and p not in goal_l]
        if kind == "CRITERION":
            hits.extend(p for p in BAD_CRITERION_PATTERNS
                        if p in lowered and p not in goal_l)
        if frontend_goal:
            frontend_hits = [p for p in FRONTEND_SCAFFOLD_PATTERNS
                             if p in lowered and p not in goal_l]
            if frontend_hits:
                rejected_scaffold = True
            hits.extend(frontend_hits)
        if hits or (_mentions_forbidden_path(text) and "root" not in goal_l):
            reason = ", ".join(hits) if hits else "non-writable/root path"
            rejections.append(f"{kind}: {text} ({reason})")
            return False
        return True

    clean_tasks = [t for t in tasks if keep("TASK", t)]
    clean_criteria = [c for c in criteria if keep("CRITERION", c)]
    quality_rejections = _frontend_quality_rejections(goal, clean_tasks, clean_criteria)
    if quality_rejections:
        rejections.extend(quality_rejections)
    hard_quality_failure = (
        rejected_scaffold
        or any("empty visual placeholders" in r for r in quality_rejections)
    )
    if hard_quality_failure:
        return [], [], rejections
    return clean_tasks, clean_criteria, rejections


def mark_status(project_dir: Path, num: int, status: str) -> None:
    tl = load_tasks(project_dir)
    task = tl.get(num)
    if task is None:
        return
    task.status = status
    save_tasks(project_dir, tl)


def append_tasks(project_dir: Path, texts: list[str]) -> list[int]:
    """Add new tasks (e.g. corrective tasks from a verify-done FAIL)."""
    tl = load_tasks(project_dir)
    nums = []
    for text in texts:
        num = tl.next_num()
        tl.tasks.append(Task(num=num, text=text))
        nums.append(num)
    save_tasks(project_dir, tl)
    return nums


def tasks_for_prompt(project_dir: Path, control_mode: str = "strict") -> str:
    """The task-list section shown to the planner."""
    tl = load_tasks(project_dir)
    if not tl.tasks:
        return ""
    if control_mode in {"hybrid", "freeform"}:
        lines = [
            "Task roadmap:",
            "  Treat this as guidance. In hybrid mode, choose the smallest coherent slice",
            "  that makes real progress; it may span adjacent open tasks when one file set",
            "  naturally needs to be built together.",
        ]
        for t in sorted(tl.tasks, key=lambda t: t.num):
            label = {STATUS_TODO: "open", STATUS_IN_PROGRESS: "in progress",
                     STATUS_DONE: "DONE", STATUS_DEFERRED: "deferred"}.get(t.status, "open")
            suffix = " (avoid unless unblocking final verification)" if t.status == STATUS_DEFERRED else ""
            lines.append(f"  T{t.num} ({label}{suffix}): {t.text}")
        return "\n".join(lines)
    eligible = tl.eligible_task()
    lines = ["Eligible next task:"]
    if eligible:
        status = "in progress" if eligible.status == STATUS_IN_PROGRESS else "open"
        lines.append(f"  T{eligible.num} ({status}): {eligible.text}")
    else:
        lines.append("  (none)")
    queued_lines = []
    deferred_lines = []
    for t in sorted(tl.tasks, key=lambda t: t.num):
        label = {STATUS_TODO: "open", STATUS_IN_PROGRESS: "in progress",
                 STATUS_DONE: "DONE", STATUS_DEFERRED: "deferred"}.get(t.status, "open")
        line = f"  T{t.num} ({label}): {t.text}"
        if t.status == STATUS_DEFERRED:
            deferred_lines.append(f"  T{t.num} (deferred, not eligible): {t.text}")
        elif eligible and t.num == eligible.num:
            continue
        elif t.open:
            queued_lines.append(f"  T{t.num} (queued, not eligible yet): {t.text}")
        else:
            queued_lines.append(line)
    if queued_lines:
        lines.append("Queued/resolved tasks:")
        lines.extend(queued_lines)
    if deferred_lines:
        lines.append("Deferred tasks (not eligible unless verify-done creates a new corrective task):")
        lines.extend(deferred_lines)
    return "\n".join(lines)


def criteria_for_prompt(project_dir: Path) -> str:
    criteria = load_criteria(project_dir)
    return "\n".join(f"  C{n}: {text}" for n, text in criteria)


def parse_task_ref(subtask: str, tl: TaskList) -> int:
    """Pull a leading 'TASK Tn:' reference out of a planner reply.
    Returns the task number only when it is the current eligible task;
    otherwise 0."""
    m = re.match(r"\s*TASK\s+T?(\d+)\s*:?", subtask, re.IGNORECASE)
    if not m:
        return 0
    num = int(m.group(1))
    eligible = tl.eligible_task()
    return num if eligible and eligible.num == num else 0


def parse_task_refs(subtask: str, tl: TaskList, control_mode: str = "strict") -> list[int]:
    """Task refs this plan is allowed to target.

    Strict mode preserves the old single eligible-task gate. Hybrid mode lets
    the planner name multiple open tasks, including compact ranges like T1-T3.
    """
    if control_mode == "strict":
        num = parse_task_ref(subtask, tl)
        return [num] if num else []
    if control_mode == "freeform" or not tl.tasks:
        return []
    nums: list[int] = []
    for start, end in re.findall(r"\bT?(\d+)\s*[-–]\s*T?(\d+)\b", subtask, re.I):
        lo, hi = sorted((int(start), int(end)))
        nums.extend(range(lo, hi + 1))
    for explicit, shorthand in re.findall(r"\bTASK\s+T?(\d+)\b|\bT(\d+)\b", subtask, re.I):
        value = explicit or shorthand
        if value:
            nums.append(int(value))
    out: list[int] = []
    for num in nums:
        task = tl.get(num)
        if task and task.open and num not in out:
            out.append(num)
    if not out:
        eligible = tl.eligible_task()
        if eligible:
            out.append(eligible.num)
    return out


def parse_task_ref_num(subtask: str) -> int:
    """Return the mentioned task number even if unknown/deferred."""
    m = re.match(r"\s*TASK\s+T?(\d+)\s*:?", subtask, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def strip_task_ref(subtask: str) -> str:
    """Remove the 'TASK Tn:' prefix so the executor sees a clean instruction."""
    return re.sub(r"^\s*TASK\s+T?\d+\s*:?\s*", "", subtask, flags=re.IGNORECASE).strip() or subtask


def infer_task_ids_for_files(tl: TaskList, written_rel: list[str]) -> list[int]:
    """Open tasks whose text names one of the files just written."""
    if not written_rel:
        return []
    candidates: list[int] = []
    names = {rel.lower() for rel in written_rel}
    for task in sorted(tl.tasks, key=lambda t: t.num):
        if not task.open:
            continue
        text = task.text.lower()
        if any(name and name in text for name in names):
            candidates.append(task.num)
    return candidates


def task_has_file_evidence(task: Task | None, written_rel: list[str], subtask: str = "") -> bool:
    """True when this successful attempt wrote a file named by the task/slice.

    The model's task-check verdict is still useful, but it should not be the
    only signal. A repair can make validation green by rewriting an unrelated
    file; that must not close a task that named a concrete target file.
    """
    if task is None or not written_rel:
        return False
    haystack = f"{task.text}\n{subtask}".lower()
    mentioned = set()
    for match in re.findall(r"\b(?:src|tests|tools)/[A-Za-z0-9_./-]+", haystack):
        mentioned.add(match.rstrip(".,:;)]}'\"`"))
    if not mentioned:
        return True
    return any(rel.lower() in mentioned for rel in written_rel if rel)


VERDICT_PASS_RE = re.compile(r"^[\s\-*]*PASS:?\s*C?(?P<num>\d+)", re.IGNORECASE)
VERDICT_FAIL_RE = re.compile(
    r"^[\s\-*]*FAIL:?\s*C?(?P<num>\d+)\s*(?:[—\-:]\s*(?P<reason>.+))?", re.IGNORECASE
)


def parse_verify_output(text: str) -> tuple[set[int], dict[int, str]]:
    """Parse PASS: Cn / FAIL: Cn — reason lines from a verify-done reply.
    Returns (passed_nums, {failed_num: reason})."""
    passed: set[int] = set()
    failed: dict[int, str] = {}
    for line in text.splitlines():
        m = VERDICT_FAIL_RE.match(line)
        if m:
            failed[int(m.group("num"))] = (m.group("reason") or "").strip()
            continue
        m = VERDICT_PASS_RE.match(line)
        if m:
            passed.add(int(m.group("num")))
    return passed, failed
