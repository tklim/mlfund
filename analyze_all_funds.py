import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np

# Load full run history
df = pd.read_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/backtest_run_history.csv")

# Exclude specific funds (edit this list as needed)
exclude_funds = ['HWFL_HWFlexi']  # Add fund labels to exclude
if exclude_funds:
    df = df[~df['fund_label'].isin(exclude_funds)]
    print(f"Excluded funds: {exclude_funds}")

# Convert numeric columns
numeric_cols = ['lookback_years', 'offset_months', 'adaptive_return_pct', 'adaptive_annualized_return_pct', 
                'sharpe', 'max_dd_pct', 'excess_return_pct', 'excess_annualized_return_pct',
                'last_short_ema', 'last_long_ema', 'last_stop_loss',
                'last_cooldown', 'last_drawdown_exit_pct', 'last_reentry_rebound_pct',
                'trade_count', 'win_rate_pct', 'best_ga_pop_size', 'best_ga_generations']

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

print(f"Total runs: {len(df)}")
print(f"Funds: {df['fund_label'].unique()}")
print(f"Columns: {len(df.columns)}")

# Create output directory
output_dir = Path("C:/Users/tklim/OpenWork/mlfund/outputs/charts")
output_dir.mkdir(parents=True, exist_ok=True)

# Summary 1: Avg return by fund (annualized)
print("\n=== Avg Annualized Return by Fund ===")
fund_stats = df.groupby('fund_label').agg({
    'adaptive_annualized_return_pct': ['mean', 'std', 'count'],
    'sharpe': 'mean',
    'max_dd_pct': 'mean'
}).round(2)
print(fund_stats)

# Chart 1: Annualized Return by fund (boxplot)
plt.figure(figsize=(12, 6))
df.boxplot(column='adaptive_annualized_return_pct', by='fund_label', grid=True, ax=plt.gca())
plt.title('Adaptive Annualized Return Distribution by Fund')
plt.suptitle('')
plt.xlabel('Fund')
plt.ylabel('Annualized Return (%)')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(output_dir / 'allfunds_return_boxplot.png', dpi=150)
plt.close()

# Chart 2: Sharpe by fund
plt.figure(figsize=(12, 6))
fund_sharpe = df.groupby('fund_label')['sharpe'].mean().sort_values(ascending=False)
fund_sharpe.plot(kind='bar', color='skyblue', edgecolor='black')
plt.title('Average Sharpe Ratio by Fund')
plt.xlabel('Fund')
plt.ylabel('Sharpe Ratio')
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig(output_dir / 'allfunds_sharpe_bar.png', dpi=150)
plt.close()

# Chart 3: Annualized Return vs Lookback (all funds)
plt.figure(figsize=(12, 6))
for fund in df['fund_label'].unique()[:5]:  # Top 5 funds
    subset = df[df['fund_label'] == fund]
    avg = subset.groupby('lookback_years')['adaptive_annualized_return_pct'].mean()
    plt.plot(avg.index, avg.values, marker='o', label=fund[:15], linewidth=2)

plt.xlabel('Lookback Years')
plt.ylabel('Avg Annualized Return (%)')
plt.title('Annualized Return vs Lookback Years (Top 5 Funds)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'allfunds_return_vs_lookback.png', dpi=150)
plt.close()

# Chart 4: Annualized Return vs Offset (all funds)
plt.figure(figsize=(12, 6))
for fund in df['fund_label'].unique()[:5]:
    subset = df[df['fund_label'] == fund]
    avg = subset.groupby('offset_months')['adaptive_annualized_return_pct'].mean()
    plt.plot(avg.index, avg.values, marker='s', label=fund[:15], linewidth=2)

plt.xlabel('Offset Months')
plt.ylabel('Avg Annualized Return (%)')
plt.title('Annualized Return vs Offset Months (Top 5 Funds)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'allfunds_return_vs_offset.png', dpi=150)
plt.close()

# Chart 5: Pop/Gen vs Annualized Return (all funds heatmap)
pivot = df.pivot_table(
    values='adaptive_annualized_return_pct',
    index='best_ga_generations',
    columns='best_ga_pop_size',
    aggfunc='mean'
)

plt.figure(figsize=(10, 6))
heatmap = plt.imshow(pivot.values, cmap='RdYlGn', aspect='auto')
plt.xticks(range(len(pivot.columns)), pivot.columns)
plt.yticks(range(len(pivot.index)), pivot.index)
plt.xlabel('Population Size')
plt.ylabel('Generations')
plt.title('All Funds: Avg Annualized Return by Pop Size & Generations')
plt.colorbar(heatmap, label='Avg Annualized Return (%)')
plt.tight_layout()
plt.savefig(output_dir / 'allfunds_pop_gen_heatmap.png', dpi=150)
plt.close()

# Chart 6: EMA parameters distribution
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.hist(df['last_short_ema'].dropna(), bins=20, alpha=0.7, color='blue', edgecolor='black')
ax1.set_xlabel('Short EMA')
ax1.set_ylabel('Count')
ax1.set_title('Short EMA Distribution (All Funds)')
ax1.grid(True, alpha=0.3)

ax2.hist(df['last_long_ema'].dropna(), bins=20, alpha=0.7, color='red', edgecolor='black')
ax2.set_xlabel('Long EMA')
ax2.set_ylabel('Count')
ax2.set_title('Long EMA Distribution (All Funds)')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(output_dir / 'allfunds_ema_dist.png', dpi=150)
plt.close()

# Summary 2: Best runs per fund (annualized)
print("\n=== Best Run per Fund (Highest Annualized Return) ===")
best_runs = df.loc[df.groupby('fund_label')['adaptive_annualized_return_pct'].idxmax()]
print(best_runs[['fund_label', 'adaptive_annualized_return_pct', 'lookback_years', 'offset_months', 
                 'last_short_ema', 'last_long_ema', 'last_stop_loss']].to_string())

# Save summary
summary = df.groupby('fund_label').agg({
    'adaptive_annualized_return_pct': ['mean', 'std', 'min', 'max', 'count'],
    'sharpe': 'mean',
    'max_dd_pct': 'mean',
    'lookback_years': 'mean',
    'offset_months': 'mean'
}).round(2)
summary.to_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/all_funds_summary.csv")
print("\nSaved summary to outputs/tunings/all_funds_summary.csv")

print(f"\nGenerated 6 charts in {output_dir}")
