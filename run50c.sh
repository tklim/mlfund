#!/usr/bin/env bash

# Balanced third 50/50 run group: 2 three-year and 3 five-year funds.

set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
backtest_script="$repo_root/scripts/backtest-ema-ga10-index.py"
log_file="$repo_root/run50c.log"
python_cmd="${PYTHON:-python3}"
repeat=false

if [[ "${1:-}" == "--repeat" ]]; then
    repeat=true
elif [[ "${1:-}" != "--once" && -n "${1:-}" ]]; then
    printf 'Usage: %s [--once|--repeat]\n' "$0" >&2
    exit 2
fi

if [[ ! -f "$backtest_script" ]]; then
    printf 'Backtest script not found: %s\n' "$backtest_script" >&2
    exit 1
fi

files=(
    MAPF_Progress_nav_5Y.csv
    MAUS_RMH_USEquityRMH_nav_5Y.csv
    MGLVH_GlobalLowVolatilityEquityARMHClass_nav_5Y.csv
    MGLVH_GlobalLowVolatilityEquityARMHClass_nav_3Y.csv
    MGPRH_GlobalPerspective_nav_3Y.csv
)
lookbacks=(1 2 3)
offsets=(3 6 9 12)

available_lookbacks() {
    "$python_cmd" - "$1" "${lookbacks[@]}" <<'PY'
import csv
import sys
from datetime import date

path = sys.argv[1]
requested = [int(value) for value in sys.argv[2:]]
with open(path, encoding="utf-8-sig", newline="") as handle:
    dates = [date.fromisoformat(row["Date"]) for row in csv.DictReader(handle) if row.get("Date")]
if not dates:
    raise SystemExit(f"No Date values found in {path}")
start, end = min(dates), max(dates)
for years in requested:
    try:
        required_end = start.replace(year=start.year + years)
    except ValueError:
        required_end = start.replace(year=start.year + years, day=28)
    if required_end < end:
        print(years)
PY
}

run_one() {
    local number="$1"
    local file="$2"
    local data_file="$repo_root/data/$file"

    if [[ ! -f "$data_file" ]]; then
        printf 'Missing data file: %s\n' "$data_file" >&2
        return 1
    fi

    mapfile -t valid_lookbacks < <(available_lookbacks "$data_file")
    if (( ${#valid_lookbacks[@]} == 0 )); then
        printf 'Skipping %s: no requested lookback fits its available history\n' "$file" | tee -a "$log_file"
        return 0
    fi

    {
        printf '[%s]\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf '%s. %s\n' "$number" "$file"
        printf 'Valid lookbacks: %s\n' "${valid_lookbacks[*]}"
    } >> "$log_file"

    for lookback in "${valid_lookbacks[@]}"; do
        for offset in "${offsets[@]}"; do
            {
                printf '\n%s\n' "$(printf '=%.0s' {1..72})"
                printf 'Running %s: lookback-years=%s, offset-months=%s\n' "$file" "$lookback" "$offset"

                "$python_cmd" "$backtest_script" \
                    --lookback-years "$lookback" \
                    --offset-months "$offset" \
                    --pop_ranges 30 \
                    --gen_ranges 15 \
                    --ga-search-preset grid \
                    --price-column TotalReturn \
                    --reuse-tuned-params \
                    --short-ema-bounds 1 100 \
                    --long-ema-bounds 30 600 \
                    --rsi-oversold-bounds 1 49 \
                    --rsi-overbought-bounds 51 99 \
                    --stop-loss-bounds 5 50 \
                    --cooldown-bounds 0 10 \
                    --drawdown-exit-bounds 2.5 99 \
                    --reentry-rebound-bounds 0 10 \
                    --exposure-multiplier-bounds 1.0 1.0 \
                    --data-file "$data_file"
            } 2>&1 | tee -a "$log_file"
        done
    done
}

run_pass() {
    local number=1
    for file in "${files[@]}"; do
        run_one "$number" "$file"
        number=$((number + 1))
    done
}

while :; do
    run_pass
    $repeat || break
done
