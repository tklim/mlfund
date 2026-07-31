#!/usr/bin/env python3
"""Git merge driver for the append-only backtest run history CSV.

Git calls this script as: merge_backtest_run_history.py <ancestor> <current> <other>
It replaces <current> with the union of every CSV row from all three versions,
sorted by run_id. Only exact duplicate rows are removed, so independently
produced run records are never silently overwritten.
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path


class HistoryFormatError(ValueError):
    """Raised when a history input cannot be safely merged."""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists() or path.stat().st_size == 0:
        return [], []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if not reader.fieldnames:
                return [], []
            headers = list(reader.fieldnames)
            if len(headers) != len(set(headers)):
                raise HistoryFormatError(f"{path}: duplicate CSV header names")
            if "run_id" not in headers:
                raise HistoryFormatError(f"{path}: missing required run_id column")

            rows = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    raise HistoryFormatError(f"{path}:{line_number}: too many CSV fields")
                normalized = {key: value or "" for key, value in row.items() if key is not None}
                if not normalized.get("run_id"):
                    raise HistoryFormatError(f"{path}:{line_number}: missing run_id value")
                rows.append(normalized)
    except (csv.Error, UnicodeError) as error:
        raise HistoryFormatError(f"{path}: invalid CSV ({error})") from error
    return headers, rows


def merged_headers(*header_lists: list[str]) -> list[str]:
    result: list[str] = []
    for headers in header_lists:
        for header in headers:
            if header not in result:
                result.append(header)
    return result


def row_key(row: dict[str, str], headers: list[str]) -> tuple[str, ...]:
    return tuple(row.get(header, "") for header in headers)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: merge_backtest_run_history.py <ancestor> <current> <other>", file=sys.stderr)
        return 2

    ancestor_path, current_path, other_path = map(Path, argv[1:])
    try:
        ancestor_headers, ancestor_rows = read_csv(ancestor_path)
        current_headers, current_rows = read_csv(current_path)
        other_headers, other_rows = read_csv(other_path)
    except HistoryFormatError as error:
        print(f"backtest-run-history merge failed: {error}", file=sys.stderr)
        return 1
    headers = merged_headers(ancestor_headers, current_headers, other_headers)

    seen: set[tuple[str, ...]] = set()
    merged_rows: list[dict[str, str]] = []
    for row in [*ancestor_rows, *current_rows, *other_rows]:
        key = row_key(row, headers)
        if key not in seen:
            seen.add(key)
            merged_rows.append(row)

    merged_rows.sort(key=lambda row: row["run_id"])

    current_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=current_path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=headers, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows({header: row.get(header, "") for header in headers} for row in merged_rows)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, current_path)

    added = len(merged_rows) - len({row_key(row, headers) for row in ancestor_rows})
    print(
        f"backtest-run-history merge: {len(merged_rows)} unique rows "
        f"({added} rows added beyond ancestor)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
