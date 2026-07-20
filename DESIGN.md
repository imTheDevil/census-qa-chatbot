# DESIGN

The *why* behind the architecture — including alternatives considered, honest
production-readiness gaps, and a failure analysis.

## 1. Problem shape

Answer questions about 3 Census 2011 PCA Data Highlights documents (Karnataka,
Odisha, MP) across four modes: **lookup, summary, computation, artifact**. Every
factual claim must be cited (document + page). Keep conversation memory. Execute
code as part of reasoning. Refuse gracefully when the answer isn't present.

## 2. The data drove everything

The PDFs were pre-converted to markdown (Datalab Marker) with `<!-- page N -->`
anchors. **We ignore the PDFs and never OCR** — the markdown is the knowledge base.
Two content shapes:
- **Narrative prose** ("Data Highlights"): state-level facts and many rankings are
  stated in sentences (e.g. "highest sex ratio of 1094 in Udupi").
- **Dense numeric tables**: multi-row headers (`Total/Rural/Urban` ×
  `Persons/Males/Females`), Indian comma grouping, a mixed-in state-total row.

This split — prose vs. tables — is why the system has **two lanes**.

## 3. Architecture: multi-agent, two lanes

```
Orchestrator (routes, delegates, synthesizes, owns conversation memory)
  ├─ research → Retrieval specialist (text lane)
  └─ analyze  → Data specialist (data lane)
```

- **Retrieval specialist**: token-ranked search over page-anchored markdown +
  a section outline. Answers lookups and summaries with structural citations.
- **Data specialist**: queries a clean per-district dataset (built by an ETL) and
  writes/runs pandas/matplotlib. Answers computation and artifacts.
- **Orchestrator**: decomposes the question, delegates (including to **both** for
  mixed queries), and composes the final cited answer under a strict
  "no new figures" constraint.

All three run on one reusable ReAct **engine**; the orchestrator's tools *are* the
specialists ("agents-as-tools"). Framework-free — this is the orchestrator-worker
pattern (equivalent to AutoGen GroupChat / OpenAI Agents handoffs), hand-rolled so
every hop is inspectable.

## 4. Key decisions and the alternatives considered

### Retrieval: agentic keyword search — NOT a vector DB, NOT GraphRAG
For 3 page-anchored, numeric documents:
- **Vector DB (rejected):** semantic similarity is weak at *exact* numeric lookup
  and at "which district is highest" (that's computation, not similarity), and it
  adds an index + a "retrieved a plausible-but-wrong number" failure mode. Its value
  is fuzziness at scale — the opposite of what we want. Would add it only at
  hundreds+ of documents.
- **GraphRAG (rejected):** built for entity-relationship-heavy corpora and global
  thematic synthesis. Our data is statistical tables + descriptive prose; a knowledge
  graph would be lossy for exact numbers and expensive to build.
- **Chosen:** token-ranked search over the markdown (skips table/TOC/image lines) →
  the page marker *is* the citation. Robust to verbose queries (ranks by term
  overlap, not exact-substring). Synonyms handled by LLM query expansion, not a
  brittle glossary.

### Computation: ETL to a clean schema — NOT freeform parsing of raw tables
The raw census tables have messy multi-row headers, so asking the agent to parse
them per-question was unreliable (it looped and sometimes hand-assembled answers by
grepping single values). **ETL** normalizes the district tables into one tidy CSV
per state (`district, total_pop, rural_pop, urban_pop, males, females,
sex_ratio_2011, literacy_rate_2011`) — done once, deterministically, unit-tested.
The agent then writes *trivial, reliable* pandas. This is the standard pattern:
normalize structured data, don't text-search for numbers. Computation never runs on retrieved
prose snippets.

### Summaries: PageIndex-style outline — NOT blind keyword search
A section tree parsed from the document's **body headings** (not the printed TOC —
its page numbers don't match our marker pages) lets the agent navigate to the right
section (`read_section`) instead of stitching a summary from scattered keyword-search hits.

### Multi-agent orchestrator-worker — NOT single-agent, NOT a framework
- **Single-agent (sufficient, but):** one agent with all 10 tools works, but the
  split on the two lanes is a *real* separation of concerns (different tools, prompts,
  failure modes), each specialist sees ~5 tools (better tool selection for a small
  model), and it's the architecture the brief most values.
- **Framework — AutoGen/LangGraph (rejected):** wouldn't improve data-wrangling
  accuracy (the actual failure source), would re-wrap a working system in new
  abstractions days before submission, and would reduce how well every hop can be
  defended. Hand-rolling the pattern demonstrates deeper understanding.

### Provider/model: NVIDIA NIM + `gpt-oss-20b`
Groq's free tier (8000 TPM) throttled multi-step turns constantly, so we moved to
**NVIDIA NIM** behind a provider-agnostic OpenAI-compatible client. `gpt-oss-20b` is
a fast reasoning model (~sub-second/call) with reliable tool calling; the larger
120b is much slower (medium reasoning effort → minutes/turn) and NVIDIA's llama
models are heavily queued (tens of seconds/call). Per-agent model overrides are
exposed in config.

### Reliability guards (each agent inherits them)
Real-world model behavior forced these; they're a core part of the design:
- **Agent-decided stop** (answer with no tool call) is primary; a step cap is only a
  safety net.
- **Discovery/throttle cap** — after N search/list calls, force computation or an
  answer (stops "search forever" loops).
- **Repeated-call guard** — don't re-run an identical call.
- **Empty-answer nudge** — never return blank; push to answer-or-refuse.
- **Malformed-tool-call recovery** + **argument sanitization** (drop junk keys like
  `{"": ""}`; guide when a required arg is missing).
- **Harmony-token cleaning** — strip gpt-oss channel tokens that leak into tool
  names and answer content.
- **Context trimming** that preserves conversation history (so follow-ups work).

## 5. Contracts

Pydantic models make component boundaries explicit: `Citation`, `ToolCall`,
`ToolResult`, `ExecutionResult`, `AgentResponse`, `Trace`/`Span`, and the ingested
`CorpusManifest`/`TableAsset`.

## 6. Memory & observability

The **filesystem is the working memory**: `workspace/sessions/{id}/` holds
`history.json` (Q&A only — the tool transcript lives in the trace), `artifacts/`
(charts), and `traces/` (full per-turn record). The UI renders each trace as
agent-tagged steps.

## 7. Production readiness — what I'd harden (honest gaps)

The **architecture is production-shaped**; implementation hardening was scoped for
this project. For production:
1. **Sandbox code execution properly.** It's a subprocess with rlimits — enough to
   run the model's analysis code, not a security boundary. Prod → gVisor / nsjail /
   Firecracker or a disposable container per execution.
2. **Move state off local disk.** Sessions/artifacts on the filesystem are
   single-node; prod → object storage (S3) + Postgres/Redis for horizontal scaling.
   Add per-session locking (no concurrency safety today).
3. **Add an evaluation harness.** Unit tests exist, but LLM answer quality needs a
   regression eval set (accuracy + citation correctness) run on every change.
4. **Auth, rate-limiting, cost controls, caching** on the API.
5. **OpenTelemetry / Langfuse** instead of homegrown traces, for aggregation and
   alerting.
6. **Expand ETL coverage + data-quality gates** (currently core metrics only).

## 8. Cut corners (and what I'd do with another day)

- ETL normalizes only the core district metrics (population/sex-ratio/literacy);
  worker and SC/ST tables fall back to the raw messy CSVs.
- No semantic-retrieval fallback (deliberate — see §4); the extension point is clean.
- Single-node filesystem state; subprocess sandbox (see §7).

## 9. Failure analysis (3 inputs that break or degrade)

### A. "What is the literacy rate in Karnataka?" — wrong breakdown
- **Degrades to:** occasionally reports the *female* literacy rate (68.08%) instead
  of the *overall* rate (75.36%).
- **Root cause:** the prose states overall/male/female/rural/urban literacy near each
  other; token search returns several and the LLM can pick the wrong one.
- **Mitigation in place:** prompt instructs "report the overall (Total/Persons)
  figure unless a breakdown is asked."
- **Proper fix:** extract state-level aggregates into structured data too, so the
  overall figure is selected deterministically rather than by the LLM.

### B. "Summarize Karnataka's literacy AND chart the top 5 districts by population." — partial answer
- **Degrades to:** sometimes only the summary *or* only the chart is produced.
- **Root cause:** the orchestrator (small model) under-decomposes a mixed intent and
  delegates once instead of to both specialists.
- **Mitigation in place:** prompt explicitly says mixed questions → call BOTH, and
  preserve the "chart" intent when delegating.
- **Proper fix:** an explicit planning step that enumerates sub-tasks, plus a
  completeness verifier that checks every requested part was answered before replying.

### C. "How many agricultural labourers are there in MP districts?" — metric not in the clean dataset
- **Degrades to:** falls back to the raw multi-header worker CSVs, where the agent may
  misidentify columns and return a wrong or partial number.
- **Root cause:** the ETL normalizes only core metrics; worker/SC/ST tables are still
  raw.
- **Proper fix:** extend the ETL (same verified positional approach) to normalize the
  worker and SC/ST tables into the clean per-district schema.
