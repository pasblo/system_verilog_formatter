from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from svformatter.config import RuntimeConfig
from svformatter.models import FormatResult


FormatRule = Callable[[str, RuntimeConfig], tuple[str, bool]]


def format_file(path: Path, runtime: RuntimeConfig, dry_run: bool = False) -> FormatResult:
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return FormatResult(path=path, changed=False, error=f"Could not decode as UTF-8: {exc}")
    except OSError as exc:
        return FormatResult(path=path, changed=False, error=str(exc))

    formatted, applied_rules = format_text(original, runtime)
    changed = formatted != original

    if changed and not dry_run:
        try:
            path.write_text(formatted, encoding="utf-8", newline="")
        except OSError as exc:
            return FormatResult(path=path, changed=False, applied_rules=tuple(applied_rules), error=str(exc))

    return FormatResult(path=path, changed=changed, applied_rules=tuple(applied_rules))


def format_text(source: str, runtime: RuntimeConfig) -> tuple[str, list[str]]:
    target_eol = _select_line_ending(source, runtime.line_ending)
    text = _normalize_to_lf(source)

    applied_rules: list[str] = []
    for rule_name, rule in FORMAT_RULES:
        text, changed = rule(text, runtime)
        if changed:
            applied_rules.append(rule_name)

    if target_eol != "\n":
        text = text.replace("\n", target_eol)

    return text, applied_rules


def register_format_rule(name: str, rule: FormatRule) -> None:
    FORMAT_RULES.append((name, rule))


def trim_trailing_whitespace(text: str, runtime: RuntimeConfig) -> tuple[str, bool]:
    if not runtime.trim_trailing_whitespace:
        return text, False

    lines = text.split("\n")
    stripped = [line.rstrip(" \t") for line in lines]
    formatted = "\n".join(stripped)
    return formatted, formatted != text


def expand_tabs(text: str, runtime: RuntimeConfig) -> tuple[str, bool]:
    if not runtime.expand_tabs:
        return text, False

    formatted = text.expandtabs(runtime.tab_size)
    return formatted, formatted != text


def enforce_final_newline(text: str, runtime: RuntimeConfig) -> tuple[str, bool]:
    if not runtime.final_newline or not text:
        return text, False

    formatted = text.rstrip("\n") + "\n"
    return formatted, formatted != text


def limit_blank_lines(text: str, runtime: RuntimeConfig) -> tuple[str, bool]:
    limit = runtime.max_consecutive_blank_lines
    if limit <= 0:
        return text, False

    output: list[str] = []
    blank_count = 0
    for line in text.split("\n"):
        if line == "":
            blank_count += 1
            if blank_count <= limit:
                output.append(line)
            continue

        blank_count = 0
        output.append(line)

    formatted = "\n".join(output)
    return formatted, formatted != text


def _normalize_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _select_line_ending(source: str, configured: str) -> str:
    if configured == "lf":
        return "\n"
    if configured == "crlf":
        return "\r\n"
    if "\r\n" in source:
        return "\r\n"
    return "\n"


FORMAT_RULES: list[tuple[str, FormatRule]] = [
    ("trim_trailing_whitespace", trim_trailing_whitespace),
    ("expand_tabs", expand_tabs),
    ("limit_blank_lines", limit_blank_lines),
    ("final_newline", enforce_final_newline),
]
