from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__:
    from .svformatter.checks import run_checks
    from .svformatter.config import resolve_runtime_config
    from .svformatter.discovery import discover_sv_files
    from .svformatter.formatter import format_file
    from .svformatter.reporting import print_report
else:
    from svformatter.checks import run_checks
    from svformatter.config import resolve_runtime_config
    from svformatter.discovery import discover_sv_files
    from svformatter.formatter import format_file
    from svformatter.reporting import print_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="svf.py",
        description="Format and check SystemVerilog sources in a configured project folder.",
    )
    parser.add_argument(
        "--conf",
        help="Configuration file name/path. Relative paths are resolved from the host scripts directory.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Run design checks without applying formatting changes.",
    )
    parser.add_argument(
        "--format-only",
        action="store_true",
        help="Run formatting without design checks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report files that would be reformatted without writing changes.",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="Print discovered SystemVerilog files and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check_only and args.format_only:
        parser.error("--check-only and --format-only cannot be used together")

    tool_dir = Path(__file__).resolve().parent

    try:
        runtime = resolve_runtime_config(tool_dir, args.conf)
        sv_files = discover_sv_files(runtime)
    except Exception as exc:
        print(f"svf: configuration error: {exc}", file=sys.stderr)
        return 1

    if args.list_files:
        for path in sv_files:
            print(path)
        return 0

    apply_formatting = not args.check_only
    run_design_checks = not args.format_only

    format_results = []
    findings = []

    if apply_formatting:
        for source_path in sv_files:
            format_results.append(format_file(source_path, runtime, dry_run=args.dry_run))

    if run_design_checks:
        findings = run_checks(sv_files, runtime)

    print_report(
        runtime=runtime,
        discovered_files=sv_files,
        format_results=format_results,
        findings=findings,
        dry_run=args.dry_run,
        formatting_enabled=apply_formatting,
        checks_enabled=run_design_checks,
    )

    if any(result.error for result in format_results):
        return 1
    if any(finding.severity == "error" for finding in findings):
        return 1
    if args.dry_run and any(result.changed for result in format_results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
