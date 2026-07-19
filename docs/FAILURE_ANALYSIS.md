# Failure Analysis

The full failure analysis (3 inputs where the system breaks or degrades, each with
root cause and a proposed fix) lives in **[DESIGN.md §9](../DESIGN.md#9-failure-analysis-3-inputs-that-break-or-degrade)**.

Summary of the three cases:
- **A.** "literacy rate in Karnataka" → may report the *female* rate (68.08%) instead
  of the *overall* rate (75.36%) — breakdown ambiguity in the prose.
- **B.** "summarize literacy AND chart the top districts" → may answer only one half —
  the orchestrator under-decomposes a mixed intent.
- **C.** "agricultural labourers in MP districts" → degrades to the raw multi-header
  CSVs — the metric isn't covered by the ETL yet.
