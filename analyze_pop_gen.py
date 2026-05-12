import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Load MIIEH data
df = pd.read_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/miieh_analysis.csv")

# Get pop/gen and return columns
cols = ['best_ga_pop_size', 'best_ga_generations', 'adaptive_return_pct', 'lookback_years', 'offset_months']
df = df[[col for col in cols if col in df.columns]].copy()

# Convert to numeric
for col in cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna(subset=['best_ga_pop_size', 'best_ga_generations', 'adaptive_return_pct'])

print(f"Analyzing {len(df)} MIIEH runs with pop/gen data")

# Create pivot table: average return by pop size and gen count
pivot = df.pivot_table(
    values='adaptive_return_pct',
    index='best_ga_generations',
    columns='best_ga_pop_size',
    aggfunc='mean'
)

# Create heatmap
plt.figure(figsize=(10, 6))
heatmap = plt.imshow(pivot.values, cmap='RdYlGn', aspect='auto')

# Set ticks and labels
plt.xticks(range(len(pivot.columns)), pivot.columns)
plt.yticks(range(len(pivot.index)), pivot.index)
plt.xlabel('Population Size')
plt.ylabel('Generations')
plt.title('MIIEH: Adaptive Return by Pop Size & Generations')
plt.colorbar(heatmap, label='Avg Adaptive Return (%)')

# Annotate cells with values
for i in range(len(pivot.index)):
    for j in range(len(pivot.columns)):
        val = pivot.values[i, j]
        if not np.isnan(val):
            plt.text(j, i, f"{val:.1f}", ha='center', va='center', color='black' if val < -10 else 'white')

plt.tight_layout()
plt.savefig("C:/Users/tklim/OpenWork/mlfund/outputs/charts/miieh_pop_gen_heatmap.png", dpi=150)
plt.close()

# Scatter plot: pop vs gen, color by return
plt.figure(figsize=(10, 6))
scatter = plt.scatter(
    df['best_ga_pop_size'], 
    df['best_ga_generations'],
    c=df['adaptive_return_pct'], 
    cmap='RdYlGn',
    s=100, 
    alpha=0.7,
    edgecolors='black'
)

plt.xlabel('Population Size')
plt.ylabel('Generations')
plt.title('MIIEH: Pop Size vs Generations (Color = Adaptive Return)')
plt.colorbar(scatter, label='Adaptive Return (%)')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("C:/Users/tklim/OpenWork/mlfund/outputs/charts/miieh_pop_gen_scatter.png", dpi=150)
plt.close()

# Find best pop/gen combos
print("\nTop 5 Pop/Gen combos (highest avg return):")
top_combos = df.groupby(['best_ga_pop_size', 'best_ga_generations'])['adaptive_return_pct'].mean().sort_values(ascending=False).head(5)
print(top_combos)

print("\nTop 5 Pop/Gen combos (least negative return):")
print(top_combos)

# Save summary
summary = df.groupby(['best_ga_pop_size', 'best_ga_generations'])['adaptive_return_pct'].agg(['mean', 'count']).reset_index()
summary.to_csv("C:/Users/tklim/OpenWork/mlfund/outputs/tunings/miieh_pop_gen_summary.csv", index=False)
print("\nSaved summary to outputs/tunings/miieh_pop_gen_summary.csv")
