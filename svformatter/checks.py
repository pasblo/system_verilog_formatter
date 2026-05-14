from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .config import RuntimeConfig
from .models import Finding


DesignCheck = Callable[[Path, str, RuntimeConfig], list[Finding]]


def run_checks(paths: Iterable[Path], runtime: RuntimeConfig) -> list[Finding]:
    findings: list[Finding] = []

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    column=1,
                    rule="SVF000",
                    severity="error",
                    message="Could not decode file as UTF-8.",
                    detail=str(exc),
                )
            )
            continue
        except OSError as exc:
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    column=1,
                    rule="SVF000",
                    severity="error",
                    message="Could not read file.",
                    detail=str(exc),
                )
            )
            continue

        for check in DESIGN_CHECKS:
            findings.extend(check(path, text, runtime))

    return sorted(findings, key=lambda item: (str(item.path).lower(), item.line, item.column, item.rule))


def register_design_check(check: DesignCheck) -> None:
    DESIGN_CHECKS.append(check)


DESIGN_CHECKS: list[DesignCheck] = []
