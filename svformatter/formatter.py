from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re

from .config import RuntimeConfig
from .models import FormatResult


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


@dataclass(frozen=True)
class DeclarationLine:
    indent: str
    declaration_type: str
    name: str
    terminator: str
    comment: str | None


_DECLARATION_RE = re.compile(
    r"^(?P<type>.+?)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_$]*(?:\s*\[[^\]]+\])*)"
    r"\s*(?P<terminator>[,;]?)$"
)

_DECLARATION_PREFIXES = {
    "input",
    "output",
    "inout",
    "ref",
    "wire",
    "uwire",
    "tri",
    "wand",
    "wor",
    "reg",
    "logic",
    "bit",
    "byte",
    "shortint",
    "int",
    "longint",
    "integer",
    "time",
    "real",
    "realtime",
    "shortreal",
    "parameter",
    "assign",
}

_NON_DECLARATION_PREFIXES = {
    "always",
    "always_comb",
    "always_ff",
    "always_latch",
    "begin",
    "case",
    "casex",
    "casez",
    "class",
    "covergroup",
    "else",
    "end",
    "endcase",
    "endclass",
    "endfunction",
    "endmodule",
    "endpackage",
    "endtask",
    "for",
    "forever",
    "fork",
    "function",
    "generate",
    "if",
    "import",
    "initial",
    "localparam",
    "module",
    "package",
    "return",
    "task",
    "typedef",
    "while",
}

_UNSUPPORTED_DECLARATION_CHARS = set("=(){}")


def align_declaration_groups(text: str, runtime: RuntimeConfig) -> tuple[str, bool]:
    lines = text.split("\n")
    output: list[str] = []
    group: list[DeclarationLine] = []

    def flush_group() -> None:
        if group:
            output.extend(_align_declaration_group(group, runtime.tab_size))
        group.clear()

    for line in lines:
        declaration = _parse_declaration_line(line)
        if declaration is None:
            flush_group()
            output.append(line)
            continue

        if group and group[-1].indent != declaration.indent:
            flush_group()
        group.append(declaration)

    flush_group()

    formatted = "\n".join(output)
    return formatted, formatted != text


def _parse_declaration_line(line: str) -> DeclarationLine | None:
    indent_match = re.match(r"^(?P<indent>[ \t]*)", line)
    indent = indent_match.group("indent") if indent_match else ""
    content = line[len(indent) :]

    code, comment = _split_line_comment(content)
    code = code.rstrip(" \t")
    if not code.strip():
        return None

    stripped_code = code.strip()
    if any(char in stripped_code for char in _UNSUPPORTED_DECLARATION_CHARS):
        return None

    declaration_match = _DECLARATION_RE.match(stripped_code)
    if not declaration_match:
        return None

    declaration_type = declaration_match.group("type").rstrip(" \t")
    name = re.sub(r"\s+", "", declaration_match.group("name"))
    terminator = declaration_match.group("terminator")
    first_type_token = declaration_type.split(None, 1)[0].lower()

    if first_type_token in _NON_DECLARATION_PREFIXES:
        return None
    if terminator == "" and comment is None and first_type_token not in _DECLARATION_PREFIXES:
        return None
    if "," in declaration_type or ";" in declaration_type:
        return None

    return DeclarationLine(
        indent=indent,
        declaration_type=declaration_type,
        name=name,
        terminator=terminator,
        comment=comment,
    )


def _align_declaration_group(group: list[DeclarationLine], tab_size: int) -> list[str]:
    type_width = max(len(line.declaration_type) for line in group)
    name_column = _next_aligned_column(type_width, tab_size)

    declaration_widths = [
        name_column + len(line.name) + len(line.terminator)
        for line in group
    ]
    comment_column = _next_aligned_column(max(declaration_widths), tab_size)

    aligned: list[str] = []
    for line, declaration_width in zip(group, declaration_widths):
        type_padding = " " * (name_column - len(line.declaration_type))
        declaration = f"{line.declaration_type}{type_padding}{line.name}{line.terminator}"

        if line.comment is not None:
            comment_padding = " " * (comment_column - declaration_width)
            declaration = f"{declaration}{comment_padding}{line.comment}"

        aligned.append(f"{line.indent}{declaration}")

    return aligned


def _next_tab_stop(column: int, tab_size: int) -> int:
    tab = max(tab_size, 1)
    return ((column + tab - 1) // tab) * tab


def _next_aligned_column(width: int, tab_size: int) -> int:
    tab = max(tab_size, 1)
    column = _next_tab_stop(width + 1, tab)
    if column - width < 2:
        column += tab
    return column


def _split_line_comment(content: str) -> tuple[str, str | None]:
    in_double_quote = False
    i = 0

    while i < len(content):
        char = content[i]

        if char == '"':
            escaped = i > 0 and content[i - 1] == "\\"
            if not escaped:
                in_double_quote = not in_double_quote
            i += 1
            continue

        if not in_double_quote and content.startswith("//", i):
            return content[:i], content[i:].rstrip(" \t")

        i += 1

    return content, None


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
    ("align_declaration_groups", align_declaration_groups),
    ("trim_trailing_whitespace", trim_trailing_whitespace),
    ("expand_tabs", expand_tabs),
    ("limit_blank_lines", limit_blank_lines),
    ("final_newline", enforce_final_newline),
]
