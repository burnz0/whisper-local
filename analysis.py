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


@dataclass(frozen=True)
class ExtractionRequest:
    text: str
    language: str
    provider: str


@dataclass(frozen=True)
class ExtractionResult:
    action_items: list[str]
    entities: list[str]
    provider: str


class SummaryProvider(Protocol):
    code: str
    label: str

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        ...


class ExtractionProvider(Protocol):
    code: str
    label: str

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        ...
