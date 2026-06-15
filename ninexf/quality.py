"""Structured quality-review output for the anti-complacency loop passes."""

from __future__ import annotations

from dataclasses import dataclass, field

QUALITY_DIMENSIONS = (
    "prompt_alignment",
    "correctness",
    "responsiveness",
    "ux",
    "polish",
)


@dataclass
class QualityReview:
    status: str = ""
    scores: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    next_focus: str = ""
    parsed: bool = False

    @property
    def total_score(self) -> int:
        return sum(self.scores.get(name, 0) for name in QUALITY_DIMENSIONS)

    @property
    def ready(self) -> bool:
        return self.status == "READY"


def parse_quality_review(raw: str) -> QualityReview:
    review = QualityReview()
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        upper = key.upper()
        if upper == "STATUS":
            candidate = value.upper()
            if candidate in {"READY", "NEEDS_MORE_WORK"}:
                review.status = candidate
                review.parsed = True
        elif upper.startswith("SCORE "):
            dimension = key[6:].strip().lower().replace(" ", "_")
            if dimension not in QUALITY_DIMENSIONS:
                continue
            try:
                score = int(value.split()[0])
            except (TypeError, ValueError, IndexError):
                continue
            review.scores[dimension] = max(0, min(5, score))
            review.parsed = True
        elif upper == "ISSUE":
            if value:
                review.issues.append(value)
                review.parsed = True
        elif upper == "NEXT_FOCUS":
            review.next_focus = value
            review.parsed = True
    return review


def review_summary(review: QualityReview) -> str:
    if not review.parsed:
        return "quality review unavailable"
    status = review.status or "UNPARSED"
    score = f"score {review.total_score}/{len(QUALITY_DIMENSIONS) * 5}"
    if review.issues:
        return f"{status.lower()} ({score}): {review.issues[0]}"
    if review.next_focus:
        return f"{status.lower()} ({score}): next focus {review.next_focus}"
    return f"{status.lower()} ({score})"
