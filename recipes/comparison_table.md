# Comparison table

Produce a clean, readable table comparing values across categories or documents
(e.g. urban vs rural breakdown, or a metric across the three states).

## When to use
The user asks to "build a table", "tabulate", "summarize as a table", or compare
several values side by side.

## Steps
1. Locate the data with `list_tables` (or pull individual figures via
   `search_documents` if the numbers live in prose).
2. Read + inspect the CSV(s); coerce the numeric columns with
   `pd.to_numeric(..., errors="coerce")`.
3. Build a tidy dataframe with only the columns that answer the question. Rename
   columns to human-readable labels.
4. Print the table as GitHub-flavored markdown (`df.to_markdown(index=False)`) so the
   UI renders it inline. Optionally also save a CSV artifact via `save_path`.

## Code template
```python
import pandas as pd

df = pd.read_csv("data/processed/tables/<pick_from_list_tables>.csv")
print(df.head()); print(df.columns.tolist())   # inspect first

out = df[["<category>", "<rural_col>", "<urban_col>"]].copy()
out.columns = ["District", "Rural", "Urban"]
for c in ["Rural", "Urban"]:
    out[c] = pd.to_numeric(out[c], errors="coerce")
out = out.dropna()

print(out.to_markdown(index=False))            # rendered inline in chat
out.to_csv(save_path("comparison_table.csv"), index=False)
```

## Citing
Cite the source document + page for each figure. If combining multiple tables, cite
each source.
