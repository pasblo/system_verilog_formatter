from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from svformatter.config import RuntimeConfig
from svformatter.models import Finding, FormatResult


def print_report(
    runtime: RuntimeConfig,
    discovered_files: list[Path],
    format_results: list[FormatResult],
    findings: list[Finding],
    dry_run: bool,
    formatting_enabled: bool,
    checks_enabled: bool,
) -> None:
    print()
    print("SystemVerilog Formatter Report")
    print("=" * 32)
    print(f"Config       : {_display_path(runtime.conf.path, runtime.scripts_dir)}")
    print(f"Target       : {_display_path(runtime.target_dir, runtime.project_root)}")
    print(f"Files scanned: {len(discovered_files)}")

    if formatting_enabled:
        _print_formatting_section(format_results, runtime, dry_run)
    else:
        print()
        print("Formatting")
        print("-" * 10)
        print("Skipped (--check-only).")

    if checks_enabled:
        _print_checks_section(findings, runtime)
    else:
        print()
        print("Design Checks")
        print("-" * 13)
        print("Skipped (--format-only).")


def _print_formatting_section(format_results: list[FormatResult], runtime: RuntimeConfig, dry_run: bool) -> None:
    changed = [result for result in format_results if result.changed]
    failed = [result for result in format_results if result.error]

    print()
    print("Formatting")
    print("-" * 10)
    print(f"Mode         : {'dry-run' if dry_run else 'write'}")
    print(f"Changed      : {len(changed)}")
    print(f"Unchanged    : {len(format_results) - len(changed) - len(failed)}")
    print(f"Failed       : {len(failed)}")

    if changed:
        print()
        print("Changed files:")
        for result in changed:
            rules = ", ".join(result.applied_rules) if result.applied_rules else "unknown"
            print(f"  - {_display_path(result.path, runtime.project_root)} ({rules})")

    if failed:
        print()
        print("Formatting failures:")
        for result in failed:
            print(f"  - {_display_path(result.path, runtime.project_root)}: {result.error}")


def _print_checks_section(findings: list[Finding], runtime: RuntimeConfig) -> None:
    counts = Counter(finding.severity for finding in findings)

    print()
    print("Design Checks")
    print("-" * 13)
    if not findings:
        print("No findings.")
        return

    print(
        "Findings     : "
        f"{counts.get('error', 0)} error(s), "
        f"{counts.get('warning', 0)} warning(s), "
        f"{counts.get('info', 0)} info"
    )

    grouped: dict[Path, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.path].append(finding)

    print()
    for path, path_findings in grouped.items():
        print(_display_path(path, runtime.project_root))
        for finding in path_findings:
            location = f"{finding.line}:{finding.column}"
            print(f"  {location} [{finding.severity.upper()}] {finding.rule}: {finding.message}")
            if finding.detail:
                print(f"    {finding.detail}")


def _display_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)
