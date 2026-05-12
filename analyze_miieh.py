import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np
import re

# Read run history
history_file = Path("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/backtest_run_history.csv")
if not history_file.exists():
    print("Run history file not found")
    exit()

df = pd.read_csv(history_file)

# Filter MIIEH runs
miieh = df[df['fund_label'].str.contains('MIIEH', na=False)].copy()

if miieh.empty:
    print("No MIIEH runs found")
    exit()

print(f"Found {len(miieh)} MIIEH runs")
print("\nColumns available:", miieh.columns.tolist())

# Convert numeric columns
numeric_cols = ['lookback_years', 'offset_months', 'adaptive_return_pct', 'sharpe', 'max_dd_pct', 
                'excess_return_pct', 'last_short_ema', 'last_long_ema', 'last_stop_loss',
                'last_cooldown', 'last_drawdown_exit_pct', 'last_reentry_rebound_pct']

for col in numeric_cols:
    if col in miieh.columns:
        miieh[col] = pd.to_numeric(miieh[col], errors='coerce')

# Extract lookback and offset from log file names if columns missing
if 'lookback_years' not in miieh.columns or miieh['lookback_years'].isna().all():
    print("Extracting lookback_years from log file names...")
    def extract_lookback(log_file):
        if pd.isna(log_file):
            return np.nan
        match = re.search(r'_(\d+\.?\d*)Y-', str(log_file))
        return float(match.group(1)) if match else np.nan
    
    if 'log_file' in miieh.columns:
        miieh['lookback_years'] = miieh['log_file'].apply(extract_lookback)

if 'offset_months' not in miieh.columns or miieh['offset_months'].isna().all():
    print("Extracting offset_months from log file names...")
    def extract_offset(log_file):
        if pd.isna(log_file):
            return np.nan
        match = re.search(r'Y-(\d+)M-', str(log_file))
        return int(match.group(1)) if match else np.nan
    
    if 'log_file' in miieh.columns:
        miieh['offset_months'] = miieh['log_file'].apply(extract_offset)

print("\nSample data:")
print(miieh[['lookback_years', 'offset_months', 'adaptive_return_pct', 'sharpe', 'max_dd_pct']].head(10))

# Save cleaned data for visualization
miieh.to_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/miieh_analysis.csv", index=False)
print("\nSaved cleaned data to outputs/tunings/miieh_analysis.csv")
