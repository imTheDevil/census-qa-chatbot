# Census Q&A Chatbot

A multi-agent chatbot that answers questions about India Census 2011 **PCA Data
Highlights** documents (Karnataka, Odisha, Madhya Pradesh). It handles lookups,
summaries, computations, and produces artifacts (charts/tables) — with a citation
(document + page + snippet) on **every** factual claim, and a graceful refusal when
the answer isn't in the documents.

> The **why** behind every decision is in [DESIGN.md](DESIGN.md) (including
> alternatives considered, production-readiness gaps, and a failure analysis).

## What it does

| Type | Example | How it's answered |
|---|---|---|
| Lookup | "What was the literacy rate in Karnataka?" | grep the prose → cite |
| Summary | "Summarize the literacy findings for Odisha" | navigate section outline → cite |
| Computation | "Which district has the highest sex ratio?" | query clean dataset + code |
| Artifact | "Bar chart of the top 10 districts by population" | write + run pandas/matplotlib |
| Mixed | "Summarize literacy **and** chart the top districts" | delegate to both specialists |
| Unanswerable | "What was the GDP of France?" | refuse, don't hallucinate |

## Architecture (short version)

**Multi-agent (orchestrator-worker), hand-rolled — no framework:**

```
            Orchestrator  (routes, delegates, synthesizes, owns memory)
              /                                    \
   Retrieval specialist  (text lane)      Data specialist  (data lane)
   grep + section outline over            clean per-district dataset (ETL)
   page-anchored markdown                 + agent-written pandas/matplotlib
```

- **Text lane** — token-ranked search over page-anchored markdown (facts) + a
  PageIndex-style section outline (summaries). Citations are structural (the page
  marker in the source), not guessed.
- **Data lane** — an ETL normalizes the messy census tables into one clean, tidy
  table per state; the agent writes and runs code over it (never grep numbers).
- No vector DB / no knowledge graph (small, structured, numeric corpus — see
  DESIGN.md for why).

Stack: **FastAPI** (agent API) · **Chainlit** (chat UI, tool-step trace) ·
**NVIDIA NIM** LLM (`openai/gpt-oss-20b`, provider-agnostic OpenAI-compatible client).

## Quick start (Docker — recommended)

You need an LLM API key. Default is **NVIDIA NIM** (free): https://build.nvidia.com
→ open a model → *Get API Key* (`nvapi-...`).

```bash
cp .env.example .env          # then paste your key into LLM_API_KEY
docker compose up             # builds, runs ingestion on boot, starts API + UI
```

- UI: **http://localhost:8501**
- API health: **http://localhost:8000/health**

`docker compose up` brings up both services, runs ingestion once, and shares a
volume so the UI can render charts the API produces.

> On **Docker Desktop** (Mac/Windows) this needs no extra setup. On **Linux with
> Docker Engine**, prefix with `sudo` (or add yourself to the `docker` group) — this
> is standard host-level Docker behavior, not specific to this project.

## Quick start (local dev, conda)

```bash
conda create -y -n censusqa -c conda-forge python=3.12
conda activate censusqa
pip install -r requirements.txt

cp .env.example .env          # add LLM_API_KEY
python -m app.ingestion       # build the index + clean datasets (once)

# two terminals:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
chainlit run ui/chainlit_app.py --port 8501 -w
```

## Configuration (`.env`)

| Var | Default | Notes |
|---|---|---|
| `LLM_API_KEY` | — | required |
| `LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | any OpenAI-compatible endpoint |
| `LLM_MODEL` | `openai/gpt-oss-20b` | tool-use model |
| `ORCHESTRATOR_MODEL` / `RETRIEVAL_MODEL` / `DATA_MODEL` | = `LLM_MODEL` | per-agent overrides |
| `REASONING_EFFORT` | `low` | gpt-oss only |

## Observability

Every answer's **Steps** panel (in the UI) shows exactly which agent and tool fired
and what each returned — e.g. `[orchestrator] analyze` → `[data] describe_datasets`
→ `[data] execute_python`. Full per-turn traces are also saved under
`workspace/sessions/{id}/traces/`.

## Tests

```bash
pytest                        # 47 tests
```
Covers the parts that matter: retrieval + citations, code execution (stdout/stderr,
timeout, artifacts), the ETL parsing, tool dispatch, and the agent loop/orchestrator
(with a scripted LLM — no API key needed).

## Repo layout

```
app/
  agent/       engine (ReAct loop + guards), orchestrator, specialists, prompts, llm
  tools/       search, outline, datasets, recipes, code_exec, base (registry)
  ingestion/   build_corpus, extract_tables, build_district_dataset (ETL), build_outline
  memory/      filesystem session store       observability/ trace models
  models/      Pydantic contracts             main.py  FastAPI app
recipes/       declarative artifact patterns the agent reads at runtime
ui/            Chainlit client
data/markdown/ source census markdown (input)
tests/         retrieval, citations, code-exec, ingestion, dataset, dispatch, agents
```
