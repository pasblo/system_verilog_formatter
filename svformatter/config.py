from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict


DEFAULT_HDL_EXTENSIONS = ("sv", "svh", "v")
DEFAULT_EXCLUDE_FOLDERS = (".git", "__pycache__", "build", "dist", "obj_dir")
DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = ()
DEFAULT_TAB_SIZE = 4
DEFAULT_EXPAND_TABS = False
DEFAULT_TRIM_TRAILING_WHITESPACE = True
DEFAULT_FINAL_NEWLINE = True
DEFAULT_MAX_CONSECUTIVE_BLANK_LINES = 0
DEFAULT_LINE_ENDING = "preserve"

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KV_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\s*(=|:)\s*(?P<value>.*)$")


@dataclass(frozen=True)
class ConfData:
    path: Path
    sections: Dict[str, Dict[str, str]]

    def section(self, name: str) -> Dict[str, str]:
        return self.sections.get(name.lower(), {})

    def get(self, key: str, *section_order: str, default: str | None = None) -> str | None:
        normalized_key = _normalize_key(key)
        if section_order:
            candidate_sections = [section.lower() for section in section_order]
        else:
            candidate_sections = ["paths", "formatter", "checks", "settings", "default"]

        for section in candidate_sections:
            section_map = self.sections.get(section)
            if section_map and normalized_key in section_map:
                return section_map[normalized_key]
        return default


@dataclass(frozen=True)
class RuntimeConfig:
    tool_dir: Path
    scripts_dir: Path
    project_root: Path
    conf: ConfData
    target_dir: Path
    hdl_extensions: tuple[str, ...]
    exclude_folders: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    tab_size: int
    expand_tabs: bool
    trim_trailing_whitespace: bool
    final_newline: bool
    max_consecutive_blank_lines: int
    line_ending: str


def resolve_runtime_config(tool_dir: Path, conf_name: str | None = None) -> RuntimeConfig:
    tool_dir = tool_dir.resolve()
    scripts_dir = tool_dir.parent
    project_root = scripts_dir.parent

    conf_path = resolve_conf_path(scripts_dir, conf_name)
    conf = parse_conf_file(conf_path)

    target_dir = _resolve_path(conf.get("TARGET_DIR", "paths"), scripts_dir, project_root / "rtl")
    hdl_extensions = _parse_extensions(conf.get("HDL_EXTENSIONS", "formatter"))
    exclude_folders = _parse_csv(conf.get("EXCLUDE_FOLDERS", "formatter"), DEFAULT_EXCLUDE_FOLDERS)
    exclude_globs = _parse_csv(conf.get("EXCLUDE_GLOBS", "formatter"), DEFAULT_EXCLUDE_GLOBS)
    tab_size = _parse_int(conf.get("TAB_SIZE", "formatter"), DEFAULT_TAB_SIZE, minimum=1)
    expand_tabs = _parse_bool(conf.get("EXPAND_TABS", "formatter"), DEFAULT_EXPAND_TABS)
    trim_trailing_whitespace = _parse_bool(
        conf.get("TRIM_TRAILING_WHITESPACE", "formatter"),
        DEFAULT_TRIM_TRAILING_WHITESPACE,
    )
    final_newline = _parse_bool(conf.get("FINAL_NEWLINE", "formatter"), DEFAULT_FINAL_NEWLINE)
    max_blank_lines = _parse_int(
        conf.get("MAX_CONSECUTIVE_BLANK_LINES", "formatter"),
        DEFAULT_MAX_CONSECUTIVE_BLANK_LINES,
        minimum=0,
    )
    line_ending = _parse_choice(
        conf.get("LINE_ENDING", "formatter"),
        DEFAULT_LINE_ENDING,
        choices={"preserve", "lf", "crlf"},
    )

    return RuntimeConfig(
        tool_dir=tool_dir,
        scripts_dir=scripts_dir,
        project_root=project_root,
        conf=conf,
        target_dir=target_dir,
        hdl_extensions=tuple(hdl_extensions),
        exclude_folders=tuple(exclude_folders),
        exclude_globs=tuple(exclude_globs),
        tab_size=tab_size,
        expand_tabs=expand_tabs,
        trim_trailing_whitespace=trim_trailing_whitespace,
        final_newline=final_newline,
        max_consecutive_blank_lines=max_blank_lines,
        line_ending=line_ending,
    )


def resolve_conf_path(scripts_dir: Path, conf_name: str | None) -> Path:
    if conf_name:
        conf_path = Path(conf_name)
        if not conf_path.is_absolute():
            conf_path = scripts_dir / conf_path
        conf_path = conf_path.resolve()
        if not conf_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {conf_path}")
        return conf_path

    default_conf = (scripts_dir / "svf.conf").resolve()
    if default_conf.exists():
        return default_conf

    conf_files = sorted(path.resolve() for path in scripts_dir.glob("*.conf"))
    if len(conf_files) == 1:
        return conf_files[0]

    if not conf_files:
        raise FileNotFoundError(
            f"No .conf file found in scripts directory: {scripts_dir}\n"
            "Expected scripts/svf.conf or pass one explicitly with --conf <name.conf>."
        )

    joined = ", ".join(path.name for path in conf_files)
    raise FileNotFoundError(
        f"Multiple .conf files found in {scripts_dir}: {joined}\n"
        "Create scripts/svf.conf or pass one explicitly with --conf <name.conf>."
    )


def parse_conf_file(conf_path: Path) -> ConfData:
    sections: Dict[str, Dict[str, str]] = {"default": {}}
    current_section = "default"

    with conf_path.open("r", encoding="utf-8") as conf_file:
        for raw_line in conf_file:
            stripped = raw_line.strip().lstrip("\ufeff")
            if not stripped or stripped.startswith("#") or stripped.startswith(";") or stripped.startswith("//"):
                continue

            section_match = _SECTION_RE.match(stripped)
            if section_match:
                current_section = section_match.group("name").strip().lower()
                sections.setdefault(current_section, {})
                continue

            kv_match = _KV_RE.match(stripped)
            if not kv_match:
                continue

            key = _normalize_key(kv_match.group("key"))
            value = _strip_inline_comment(kv_match.group("value").strip())
            sections[current_section][key] = value

    return ConfData(path=conf_path, sections=sections)


def _resolve_path(raw_value: str | None, base_dir: Path, default_path: Path) -> Path:
    if raw_value is None:
        return default_path.resolve()

    parsed = Path(raw_value)
    if not parsed.is_absolute():
        parsed = base_dir / parsed
    return parsed.resolve()


def _parse_extensions(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return list(DEFAULT_HDL_EXTENSIONS)
    extensions = [part.strip().lstrip(".").lower() for part in raw_value.split(",") if part.strip()]
    return extensions or list(DEFAULT_HDL_EXTENSIONS)


def _parse_csv(raw_value: str | None, default_values: tuple[str, ...]) -> list[str]:
    if raw_value is None:
        return list(default_values)
    values = [part.strip() for part in raw_value.split(",") if part.strip()]
    return values or list(default_values)


def _parse_bool(raw_value: str | None, default_value: bool) -> bool:
    if raw_value is None:
        return default_value
    normalized = raw_value.strip().lower()
    if normalized in {"1", "yes", "true", "on"}:
        return True
    if normalized in {"0", "no", "false", "off"}:
        return False
    return default_value


def _parse_int(raw_value: str | None, default_value: int, minimum: int | None = None) -> int:
    if raw_value is None:
        return default_value
    try:
        parsed = int(raw_value, 0)
    except ValueError:
        return default_value
    if minimum is not None and parsed < minimum:
        return default_value
    return parsed


def _parse_choice(raw_value: str | None, default_value: str, choices: set[str]) -> str:
    if raw_value is None:
        return default_value
    normalized = raw_value.strip().lower()
    if normalized in choices:
        return normalized
    return default_value


def _normalize_key(key: str) -> str:
    return key.strip().replace("-", "_").replace(".", "_").upper()


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    i = 0
    kept = []
    while i < len(value):
        char = value[i]

        if char == "'" and not in_double:
            in_single = not in_single
            kept.append(char)
            i += 1
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            kept.append(char)
            i += 1
            continue

        if not in_single and not in_double and value.startswith("//", i):
            break
        if not in_single and not in_double and char == "#":
            break

        kept.append(char)
        i += 1

    return "".join(kept).strip()
