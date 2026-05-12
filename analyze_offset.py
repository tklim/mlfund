import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Load MIIEH data
df = pd.read_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/miieh_analysis.csv")

# Convert numeric
df['offset_months'] = pd.to_numeric(df['offset_months'], errors='coerce')
df['adaptive_return_pct'] = pd.to_numeric(df['adaptive_return_pct'], errors='coerce')
df['lookback_years'] = pd.to_numeric(df['lookback_years'], errors='coerce')
df['sharpe'] = pd.to_numeric(df['sharpe'], errors='coerce')
df['max_dd_pct'] = pd.to_numeric(df['max_dd_pct'], errors='coerce')

df = df.dropna(subset=['offset_months', 'adaptive_return_pct'])

print(f"Analyzing {len(df)} MIIEH runs")
print(f"Offset months: {sorted(df['offset_months'].unique())}")

# Create output directory
output_dir = Path("C:/Users/tklim/OpenWork/mlfund/outputs/charts")
output_dir.mkdir(parents=True, exist_ok=True)

# Chart 1: Offset Months vs Adaptive Return (with lookback grouping)
plt.figure(figsize=(12, 6))

for lookback in sorted(df['lookback_years'].unique()):
    subset = df[df['lookback_years'] == lookback]
    offset_means = subset.groupby('offset_months')['adaptive_return_pct'].mean()
    plt.plot(offset_means.index, offset_means.values, 
             marker='o', label=f'{lookback}Y lookback', linewidth=2, markersize=8)

plt.xlabel('Offset Months')
plt.ylabel('Avg Adaptive Return (%)')
plt.title('MIIEH: Offset Months vs Adaptive Return (by Lookback)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_offset_vs_return.png', dpi=150)
plt.close()

# Chart 2: Offset Months vs Sharpe Ratio
plt.figure(figsize=(12, 6))

for lookback in sorted(df['lookback_years'].unique()):
    subset = df[df['lookback_years'] == lookback]
    offset_means = subset.groupby('offset_months')['sharpe'].mean()
    plt.plot(offset_means.index, offset_means.values, 
             marker='s', label=f'{lookback}Y lookback', linewidth=2, markersize=8)

plt.xlabel('Offset Months')
plt.ylabel('Avg Sharpe Ratio')
plt.title('MIIEH: Offset Months vs Sharpe Ratio (by Lookback)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_offset_vs_sharpe.png', dpi=150)
plt.close()

# Chart 3: Offset Months vs Max Drawdown
plt.figure(figsize=(12, 6))

for lookback in sorted(df['lookback_years'].unique()):
    subset = df[df['lookback_years'] == lookback]
    offset_means = subset.groupby('offset_months')['max_dd_pct'].mean()
    plt.plot(offset_means.index, offset_means.values, 
             marker='^', label=f'{lookback}Y lookback', linewidth=2, markersize=8)

plt.xlabel('Offset Months')
plt.ylabel('Avg Max Drawdown (%)')
plt.title('MIIEH: Offset Months vs Max Drawdown (by Lookback)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_offset_vs_dd.png', dpi=150)
plt.close()

# Chart 4: Boxplot - Return distribution by offset
plt.figure(figsize=(10, 6))
df.boxplot(column='adaptive_return_pct', by='offset_months', grid=True, ax=plt.gca())
plt.title('MIIEH: Adaptive Return Distribution by Offset Months')
plt.suptitle('')
plt.xlabel('Offset Months')
plt.ylabel('Adaptive Return (%)')
plt.tight_layout()
plt.savefig(output_dir / 'miieh_offset_boxplot.png', dpi=150)
plt.close()

# Print summary statistics
print("\n=== Offset Months Analysis ===")
offset_stats = df.groupby('offset_months').agg({
    'adaptive_return_pct': ['mean', 'std', 'count'],
    'sharpe': 'mean',
    'max_dd_pct': 'mean'
}).round(2)

print(offset_stats)

print("\n=== Best Offset (by avg return) ===")
best_offset = df.groupby('offset_months')['adaptive_return_pct'].mean().sort_values(ascending=False)
print(best_offset)

print("\n=== Best Offset by Lookback ===")
for lookback in sorted(df['lookback_years'].unique()):
    subset = df[df['lookback_years'] == lookback]
    best = subset.groupby('offset_months')['adaptive_return_pct'].mean().sort_values(ascending=False)
    print(f"\n{lookback}Y lookback:")
    print(best.head(3))
