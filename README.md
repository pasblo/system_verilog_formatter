# system_verilog_formatter

Project-agnostic SystemVerilog formatter and design-rule checker.

This repository is intended to be used as a git submodule under a host project, for example `scripts/system_verilog_formatter`. The host project keeps its configuration one folder above the submodule in `scripts/svf.conf`, so the submodule can be updated without overwriting project-specific settings.

The tool currently provides the project structure, recursive file discovery, configuration handling, conservative generic formatting, design-check extension points, and a final execution report. The specific SystemVerilog style and design-decision rules can be added incrementally in the formatter and checker registries described below.

## Host Project Layout

Expected structure in the host project:

```text
<project-root>/
|-- rtl/
|   `-- ... SystemVerilog sources ...
`-- scripts/
    |-- svf.conf
    `-- system_verilog_formatter/   # this submodule
```

By default, paths in `svf.conf` are resolved relative to the host `scripts/` directory.

## Install As Submodule

```bash
git submodule add https://github.com/pasblo/system_verilog_formatter scripts/system_verilog_formatter
git submodule update --init --recursive
```

Create the host config file:

```bash
cp scripts/system_verilog_formatter/svf.conf.example scripts/svf.conf
```

## Run

From the host project root:

```bash
python scripts/system_verilog_formatter/svf.py
```

Or run it as a Python module from the host project root:

```bash
python -m scripts.system_verilog_formatter.svf
```

Python module names use dots, so `python -m scripts/system_verilog_formatter/svf` is not valid.

Useful options:

| Option | Meaning |
|---|---|
| `--conf <path>` | Use an explicit config file. Relative paths are resolved from the host `scripts/` directory. |
| `--dry-run` | Report files that would be changed without writing them. |
| `--check-only` | Run design checks without formatting files. |
| `--format-only` | Format files without running design checks. |
| `--list-files` | Print discovered source files and exit. |

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Completed without errors. |
| `1` | Configuration, read/write, or design-check error. |
| `2` | `--dry-run` found files that would be reformatted. |

## Config Lookup

The config behavior mirrors the pattern used by `auto_verilator`:

1. If `--conf` is passed, that file is used.
2. Else `scripts/svf.conf` is used when present.
3. Else if exactly one `*.conf` exists in `scripts/`, that file is used.
4. Else execution fails and asks for explicit `--conf`.

## `svf.conf` Details

Example:

```ini
[paths]
TARGET_DIR = ../rtl

[formatter]
HDL_EXTENSIONS = sv,svh,v
EXCLUDE_FOLDERS = .git,__pycache__,build,dist,obj_dir
EXCLUDE_GLOBS =
TAB_SIZE = 4
EXPAND_TABS = false
TRIM_TRAILING_WHITESPACE = true
FINAL_NEWLINE = true
MAX_CONSECUTIVE_BLANK_LINES = 0
LINE_ENDING = preserve

[checks]
```

Key reference:

| Section | Key | Meaning |
|---|---|---|
| `[paths]` | `TARGET_DIR` | Folder scanned recursively for SystemVerilog files. |
| `[formatter]` | `HDL_EXTENSIONS` | Comma-separated extensions to include, without dots. |
| `[formatter]` | `EXCLUDE_FOLDERS` | Comma-separated folder names skipped during recursive discovery. |
| `[formatter]` | `EXCLUDE_GLOBS` | Comma-separated file patterns matched against file names or paths relative to `TARGET_DIR`. |
| `[formatter]` | `TAB_SIZE` | Number of spaces used when `EXPAND_TABS = true`, and available to future alignment rules. |
| `[formatter]` | `EXPAND_TABS` | Convert tab characters to spaces using `TAB_SIZE`. |
| `[formatter]` | `TRIM_TRAILING_WHITESPACE` | Remove spaces and tabs at line ends. |
| `[formatter]` | `FINAL_NEWLINE` | Ensure non-empty files end with one newline. |
| `[formatter]` | `MAX_CONSECUTIVE_BLANK_LINES` | Limit repeated blank lines. `0` disables this rule. |
| `[formatter]` | `LINE_ENDING` | `preserve`, `lf`, or `crlf`. |

The initial formatting rules are intentionally conservative. More specific rules, such as signal declaration alignment and spacing around procedural blocks, should be added as dedicated formatter rules.

## Report Format

Every normal run ends with a summary like:

```text
SystemVerilog Formatter Report
================================
Config       : scripts/svf.conf
Target       : rtl
Files scanned: 12

Formatting
----------
Mode         : write
Changed      : 3
Unchanged    : 9
Failed       : 0

Design Checks
-------------
No findings.
```

Design-rule findings are grouped by file and include line, column, severity, rule ID, message, and optional detail.

## Add A Formatting Rule

Formatter rules live in `svformatter/formatter.py`.

A rule is a function with this shape:

```python
def my_rule(text: str, runtime: RuntimeConfig) -> tuple[str, bool]:
    formatted = text
    # transform formatted here
    return formatted, formatted != text
```

Register it in `FORMAT_RULES` in the order it should run:

```python
FORMAT_RULES: list[tuple[str, FormatRule]] = [
    ("trim_trailing_whitespace", trim_trailing_whitespace),
    ("my_rule", my_rule),
    ("final_newline", enforce_final_newline),
]
```

Guidelines for future SystemVerilog formatting rules:

1. Keep each rule focused on one behavior, such as declaration alignment, conditional spacing, or named generate blocks.
2. Prefer parsing line groups or structured tokens over broad regex replacements when the rule depends on syntax context.
3. Use `runtime.tab_size` for every alignment calculation so formatting follows `svf.conf`.
4. Return the original text unchanged when the rule cannot confidently identify the construct.
5. Add config keys in `RuntimeConfig` only when the behavior should be user-tunable.

For declaration alignment, a good first implementation shape is:

1. Detect contiguous declaration groups.
2. Parse each declaration into type/range/name/comment fields.
3. Compute the maximum type/range width and name width in the group.
4. Rebuild the group with padding rounded to `TAB_SIZE`.
5. Leave lines with unsupported syntax unchanged until the parser is expanded.

## Add A Design Check

Design checks live in `svformatter/checks.py`.

A check is a function with this shape:

```python
from pathlib import Path

from svformatter.config import RuntimeConfig
from svformatter.models import Finding


def check_named_generate_blocks(path: Path, text: str, runtime: RuntimeConfig) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "generate" in line:
            findings.append(
                Finding(
                    path=path,
                    line=line_number,
                    column=line.find("generate") + 1,
                    rule="SVF101",
                    severity="warning",
                    message="Generate block naming rule is not implemented yet.",
                    detail="Replace this example with the real project rule.",
                )
            )
    return findings
```

Register it by adding it to `DESIGN_CHECKS`:

```python
DESIGN_CHECKS: list[DesignCheck] = [
    check_named_generate_blocks,
]
```

Severity should be one of:

| Severity | Use for |
|---|---|
| `error` | Rules that should fail the command. |
| `warning` | Rules that should be reported but not fail the command. |
| `info` | Informational design guidance. |

Rule IDs should be stable. Suggested ranges:

| Range | Category |
|---|---|
| `SVF1xx` | Naming and design conventions. |
| `SVF2xx` | Declaration and signal style. |
| `SVF3xx` | Procedural block, task, and function style. |
| `SVF4xx` | Generate block style. |
| `SVF9xx` | Project-specific temporary rules. |

## Source Discovery

Recursive discovery is implemented in `svformatter/discovery.py`.

Files are included when:

1. Their extension is listed in `HDL_EXTENSIONS`.
2. They are under `TARGET_DIR`.
3. No path segment matches `EXCLUDE_FOLDERS`.
4. The file name or target-relative path does not match `EXCLUDE_GLOBS`.

Examples:

```ini
EXCLUDE_GLOBS = *_tb.sv,generated/*
```

## Development Notes

The project uses only the Python standard library. No package installation is required for normal use.

Run a smoke test from inside this repository by passing an explicit config that points at a folder with `.sv` files:

```bash
python svf.py --conf C:/path/to/svf.conf --dry-run
```
