# Bar chart

Produce a bar chart comparing a numeric measure across categories (e.g. districts,
states, or rural vs urban).

## When to use
The user asks to "chart", "plot", "compare visually", or "show a graph" of a measure
across several categories.

## Steps
1. Find the data: call `list_tables` (filter by keyword, e.g. "population",
   "literacy", "sex ratio") and pick the CSV whose name + page match the question.
2. Inspect before plotting: read the CSV with pandas and `print(df.head())` and
   `print(df.columns.tolist())`. Census CSVs often have multi-row headers — identify
   the real header/data rows before charting.
3. Select and clean the category + value columns. Values are already comma-stripped,
   but may be strings — coerce with `pd.to_numeric(..., errors="coerce")` and drop NaNs.
4. Plot and save to the artifacts dir via `save_path`.

## Code template
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/processed/tables/<pick_from_list_tables>.csv")
print(df.head()); print(df.columns.tolist())   # inspect first

cat_col, val_col = "<category_column>", "<value_column>"
d = df[[cat_col, val_col]].copy()
d[val_col] = pd.to_numeric(d[val_col], errors="coerce")
d = d.dropna().sort_values(val_col, ascending=False).head(15)

fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(d[cat_col].astype(str), d[val_col])
ax.set_ylabel(val_col); ax.set_title("<title>")
plt.xticks(rotation=45, ha="right"); plt.tight_layout()
plt.savefig(save_path("bar_chart.png"), dpi=120)
print("saved", save_path("bar_chart.png"))
```

## Citing
Cite the source table's document + page (shown by `list_tables`) for the numbers
the chart is built from.
