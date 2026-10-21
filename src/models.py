"""Data models for question lists."""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class Question:
    id: Optional[int]
    title: str
    url: str
    difficulty: str
    acceptance: Optional[float] = None
    frequency: Optional[float] = None
    topics: List[str] = field(default_factory=list)
    source_window: str = "unknown"
    source_repo: str = "snehasishroy"
    confidence: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyQuestionSet:
    company: str
    windows: Dict[str, List[Question]]
    fetched_at: str
    source_repo: str
    attribution: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "fetched_at": self.fetched_at,
            "source_repo": self.source_repo,
            "attribution": self.attribution,
            "notes": self.notes,
            "windows": {
                k: [q.to_dict() for q in v] for k, v in self.windows.items()
            },
            "summary": {window: len(qs) for window, qs in self.windows.items()},
        }

    def top_questions(
        self, window: str = "last_30_days", n: int = 20, by: str = "frequency"
    ) -> List[Question]:
        qs = self.windows.get(window, [])
        if by == "frequency":
            return sorted(qs, key=lambda q: q.frequency or 0, reverse=True)[:n]
        return qs[:n]