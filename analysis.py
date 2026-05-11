from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SummaryRequest:
    text: str
    language: str
    provider: str
    density: int


@dataclass(frozen=True)
class SummaryResult:
    items: list[str]
    provider: str


class SummaryProvider(Protocol):
    code: str
    label: str

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        ...
