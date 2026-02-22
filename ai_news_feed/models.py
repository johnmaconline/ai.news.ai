from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    id: str
    title: str
    url: str
    summary: str
    source_name: str
    source_type: str
    domain: str
    published_at: datetime | None
    priority: float = 1.0
    tags: set[str] = field(default_factory=set)
    section_hint: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    assigned_section: str | None = None
    section_score: float = 0.0
    summary_text: str = ""
    why_it_matters: str = ""

    def canonical_text(self) -> str:
        return f"{self.title}\n{self.summary}".strip()


@dataclass
class DailyFeed:
    date: str
    generated_at: str
    title: str
    sections: dict[str, list[Article]]
    intro: str
    lead_story_id: str | None = None

