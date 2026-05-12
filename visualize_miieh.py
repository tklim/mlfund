import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np

# Read cleaned data
df = pd.read_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/miieh_analysis.csv")

# Convert numeric columns
numeric_cols = ['lookback_years', 'offset_months', 'adaptive_return_pct', 'sharpe', 'max_dd_pct', 
                'excess_return_pct', 'last_short_ema', 'last_long_ema', 'last_stop_loss',
                'last_cooldown', 'last_drawdown_exit_pct', 'last_reentry_rebound_pct',
                'last_rsi_oversold', 'last_rsi_overbought', 'trade_count', 'win_rate_pct']

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Remove rows with no lookback_years
df = df.dropna(subset=['lookback_years'])

print(f"Analyzing {len(df)} MIIEH runs")
print(f"Lookback years range: {df['lookback_years'].min()} - {df['lookback_years'].max()}")
print(f"Offset months range: {df['offset_months'].min()} - {df['offset_months'].max()}")

# Create output directory
output_dir = Path("C:/Users/tklim/OpenWork/mlfund/outputs/charts")
output_dir.mkdir(parents=True, exist_ok=True)

# Set style
plt.style.use('seaborn-v0_8-darkgrid')

# Chart 1: Adaptive Return vs Lookback Years (grouped by offset months)
plt.figure(figsize=(12, 6))
for offset in sorted(df['offset_months'].unique()):
    subset = df[df['offset_months'] == offset]
    plt.plot(subset['lookback_years'], subset['adaptive_return_pct'], 
             marker='o', label=f'Offset {int(offset)}M', linewidth=2)

plt.xlabel('Lookback Years')
plt.ylabel('Adaptive Return (%)')
plt.title('MIIEH: Adaptive Return vs Lookback Years (by Offset)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_return_vs_lookback.png', dpi=150)
plt.close()

# Chart 2: Sharpe Ratio vs Lookback Years
plt.figure(figsize=(12, 6))
for offset in sorted(df['offset_months'].unique()):
    subset = df[df['offset_months'] == offset]
    plt.plot(subset['lookback_years'], subset['sharpe'], 
             marker='s', label=f'Offset {int(offset)}M', linewidth=2)

plt.xlabel('Lookback Years')
plt.ylabel('Sharpe Ratio')
plt.title('MIIEH: Sharpe Ratio vs Lookback Years (by Offset)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_sharpe_vs_lookback.png', dpi=150)
plt.close()

# Chart 3: Max Drawdown vs Lookback Years
plt.figure(figsize=(12, 6))
for offset in sorted(df['offset_months'].unique()):
    subset = df[df['offset_months'] == offset]
    plt.plot(subset['lookback_years'], subset['max_dd_pct'], 
             marker='^', label=f'Offset {int(offset)}M', linewidth=2)

plt.xlabel('Lookback Years')
plt.ylabel('Max Drawdown (%)')
plt.title('MIIEH: Max Drawdown vs Lookback Years (by Offset)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_dd_vs_lookback.png', dpi=150)
plt.close()

# Chart 4: Parameter Heatmap - EMA pairs
plt.figure(figsize=(10, 8))
scatter = plt.scatter(df['last_short_ema'], df['last_long_ema'], 
                      c=df['adaptive_return_pct'], cmap='RdYlGn', 
                      s=100, alpha=0.7, edgecolors='black')

plt.xlabel('Short EMA')
plt.ylabel('Long EMA')
plt.title('MIIEH: EMA Parameters vs Adaptive Return')
plt.colorbar(scatter, label='Adaptive Return (%)')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(output_dir / 'miieh_ema_heatmap.png', dpi=150)
plt.close()

# Chart 5: Stop Loss & Drawdown Exit vs Return
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.scatter(df['last_stop_loss'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax1.set_xlabel('Stop Loss (%)')
ax1.set_ylabel('Adaptive Return (%)')
ax1.set_title('MIIEH: Stop Loss vs Return')
ax1.grid(True, alpha=0.3)

ax2.scatter(df['last_drawdown_exit_pct'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax2.set_xlabel('Drawdown Exit (%)')
ax2.set_ylabel('Adaptive Return (%)')
ax2.set_title('MIIEH: Drawdown Exit vs Return')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(output_dir / 'miieh_sl_ddx_vs_return.png', dpi=150)
plt.close()

# Chart 6: RBR & Cooldown vs Return
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.scatter(df['last_reentry_rebound_pct'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax1.set_xlabel('Reentry Rebound (%)')
ax1.set_ylabel('Adaptive Return (%)')
ax1.set_title('MIIEH: Reentry Rebound vs Return')
ax1.grid(True, alpha=0.3)

ax2.scatter(df['last_cooldown'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax2.set_xlabel('Cooldown (periods)')
ax2.set_ylabel('Adaptive Return (%)')
ax2.set_title('MIIEH: Cooldown vs Return')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(output_dir / 'miieh_rbr_cd_vs_return.png', dpi=150)
plt.close()

# Chart 7: RSI Oversold/Overbought vs Return
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.scatter(df['last_rsi_oversold'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax1.set_xlabel('RSI Oversold')
ax1.set_ylabel('Adaptive Return (%)')
ax1.set_title('MIIEH: RSI Oversold vs Return')
ax1.grid(True, alpha=0.3)

ax2.scatter(df['last_rsi_overbought'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax2.set_xlabel('RSI Overbought')
ax2.set_ylabel('Adaptive Return (%)')
ax2.set_title('MIIEH: RSI Overbought vs Return')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(output_dir / 'miieh_rsi_vs_return.png', dpi=150)
plt.close()

# Chart 8: Trade Count & Win Rate vs Return
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.scatter(df['trade_count'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax1.set_xlabel('Trade Count')
ax1.set_ylabel('Adaptive Return (%)')
ax1.set_title('MIIEH: Trade Count vs Return')
ax1.grid(True, alpha=0.3)

ax2.scatter(df['win_rate_pct'], df['adaptive_return_pct'], 
            c=df['lookback_years'], cmap='viridis', s=80, alpha=0.7)
ax2.set_xlabel('Win Rate (%)')
ax2.set_ylabel('Adaptive Return (%)')
ax2.set_title('MIIEH: Win Rate vs Return')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(output_dir / 'miieh_trades_vs_return.png', dpi=150)
plt.close()

# Chart 9: Summary boxplot - Returns by lookback
plt.figure(figsize=(10, 6))
df.boxplot(column='adaptive_return_pct', by='lookback_years', grid=True, ax=plt.gca())
plt.title('MIIEH: Adaptive Return Distribution by Lookback Years')
plt.suptitle('')
plt.xlabel('Lookback Years')
plt.ylabel('Adaptive Return (%)')
plt.tight_layout()
plt.savefig(output_dir / 'miieh_return_boxplot.png', dpi=150)
plt.close()

print(f"\nGenerated 9 charts in {output_dir}")
print("\nKey patterns found:")

# Analyze patterns
print("\n1. Best performing lookback years:")
best_lookback = df.groupby('lookback_years')['adaptive_return_pct'].mean().sort_values(ascending=False)
print(best_lookback)

print("\n2. Best performing offset months:")
if 'offset_months' in df.columns:
    best_offset = df.groupby('offset_months')['adaptive_return_pct'].mean().sort_values(ascending=False)
    print(best_offset)

print("\n3. Parameter ranges in top 25% returns:")
top_quartile = df[df['adaptive_return_pct'] >= df['adaptive_return_pct'].quantile(0.75)]
print(f"Short EMA: {top_quartile['last_short_ema'].min():.1f} - {top_quartile['last_short_ema'].max():.1f}")
print(f"Long EMA: {top_quartile['last_long_ema'].min():.1f} - {top_quartile['last_long_ema'].max():.1f}")
print(f"Stop Loss: {top_quartile['last_stop_loss'].min():.2f}% - {top_quartile['last_stop_loss'].max():.2f}%")
print(f"Drawdown Exit: {top_quartile['last_drawdown_exit_pct'].min():.2f}% - {top_quartile['last_drawdown_exit_pct'].max():.2f}%")
print(f"Reentry Rebound: {top_quartile['last_reentry_rebound_pct'].min():.2f}% - {top_quartile['last_reentry_rebound_pct'].max():.2f}%")
