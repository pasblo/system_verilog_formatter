from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FormatResult:
    path: Path
    changed: bool
    applied_rules: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    column: int
    rule: str
    severity: str
    message: str
    detail: str | None = None
