"""Best-of-N candidate sampling + critic verdict parsing (v0.3).

Best-of-N: run the executor N times at different temperatures, write+validate
each candidate in turn (restoring the working tree between them — possible
because every iteration starts HEAD-clean), and keep the best by score tuple.
The validator is the judge; losers survive only as log entries.

On a local 7B each executor call is 30–90s, so this defaults to fix-mode only
(`best_of_mode: "fix"`), where a retry is most likely to pay off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# temperatures cycled across candidates so they actually differ
CANDIDATE_TEMPERATURES = (0.4, 0.7, 0.9)

VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(?P<verdict>ACCEPT|REVISE)\s*$",
                        re.IGNORECASE | re.MULTILINE)
ISSUE_RE = re.compile(r"^\s*ISSUE:\s*(?P<issue>[^\n]+)$", re.MULTILINE)


@dataclass
class CandidateResult:
    index: int
    temperature: float
    summary: str
    passed: bool
    acceptance_passed: bool | None
    tests_ran: int
    errors_n: int
    files_n: int

    def score(self) -> tuple:
        """Higher is better: validation first, then acceptance progress, then
        test coverage; fewer errors and smaller change break ties."""
        return (
            self.passed,
            1 if self.acceptance_passed else 0,
            self.tests_ran,
            -self.errors_n,
            -self.files_n,
        )

    def as_log(self) -> dict:
        return {
            "index": self.index,
            "temperature": self.temperature,
            "summary": self.summary,
            "passed": self.passed,
            "acceptance_passed": self.acceptance_passed,
            "tests_ran": self.tests_ran,
            "errors_n": self.errors_n,
            "files_n": self.files_n,
        }


def pick_winner(candidates: list[CandidateResult]) -> int:
    """Index of the best candidate (first wins ties — lowest temperature)."""
    return max(candidates, key=lambda c: (c.score(), -c.index)).index


def best_of_n_active(best_of_n: int, best_of_mode: str, mode: str) -> int:
    """How many candidates to sample this iteration (1 = feature off)."""
    if best_of_n <= 1 or best_of_mode == "off":
        return 1
    if best_of_mode == "always":
        return best_of_n
    return best_of_n if mode == "fix" else 1  # default: fix mode only


def parse_critic_output(text: str) -> tuple[str, list[str]]:
    """Returns (verdict, issues). Unparseable verdict -> "unparsed" (treated
    as ACCEPT by the loop, but logged distinctly)."""
    m = VERDICT_RE.search(text)
    if not m:
        return "unparsed", []
    verdict = m.group("verdict").upper()
    issues = [i.group("issue").strip() for i in ISSUE_RE.finditer(text)][:3]
    return verdict, issues
