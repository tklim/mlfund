#!/usr/bin/env bash

# Balanced first 50/50 run group: 3 three-year and 2 five-year funds.

set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
backtest_script="$repo_root/scripts/backtest-ema-ga10-index.py"
log_file="$repo_root/run50a.log"
python_cmd="${PYTHON:-python3}"
repeat=false

if [[ "${1:-}" == "--repeat" ]]; then
    repeat=true
elif [[ "${1:-}" == "--once" || -z "${1:-}" ]]; then
    repeat=false
else
    printf 'Usage: %s [--once|--repeat]\n' "$0" >&2
    exit 2
fi

if [[ ! -f "$backtest_script" ]]; then
    printf 'Backtest script not found: %s\n' "$backtest_script" >&2
    exit 1
fi

files=(
    APCR_AsiaPacificREIT_nav_3Y.csv
    HWFL_HWFlexi_nav_3Y.csv
    MAKGCF_GreaterChina_nav_3Y.csv
    APCR_AsiaPacificREIT_nav_5Y.csv
    HWFL_HWFlexi_nav_5Y.csv
)
lookbacks=(1 2 3)
offsets=(3 6 9 12)

run_one() {
    local number="$1"
    local file="$2"
    local data_file="$repo_root/data/$file"

    if [[ ! -f "$data_file" ]]; then
        printf 'Missing data file: %s\n' "$data_file" >&2
        return 1
    fi

    {
        printf '[%s]\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf '%s. %s\n' "$number" "$file"
    } >> "$log_file"

    for lookback in "${lookbacks[@]}"; do
        for offset in "${offsets[@]}"; do
            printf '\n%s\n' "$(printf '=%.0s' {1..72})"
            printf 'Running %s: lookback-years=%s, offset-months=%s\n' "$file" "$lookback" "$offset"

            "$python_cmd" "$backtest_script" \
                --lookback-years "$lookback" \
                --offset-months "$offset" \
                --pop_ranges 50 \
                --gen_ranges 50 \
                --ga-search-preset grid \
                --price-column TotalReturn \
                --reuse-tuned-params \
                --data-file "$data_file"
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
