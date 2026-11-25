# Alpine Ops Bot

RAG assistant for Alpine Marine operations docs and emails (pre-arrival, crewing SOP, port tariffs, vessel trails).

## Stack

- **Flask** chat UI (`bot/app.py`)
- **Pinecone** vector index (hosted embeddings)
- **DeepSeek** chat completions
- Optional **docs viewer** (`viewer/app.py`)

## Setup

1. Copy `.env.example` to `.env` and fill keys:

```env
PINECONE_API_KEY=...
DEEPSEEK_API_KEY=...
PINECONE_INDEX=alpine-ops
```

2. Install and ingest:

```bat
cd bot
pip install -r requirements.txt
python ingest.py
python app.py
```

Open http://127.0.0.1:7860

Or run `bot\run.bat`.

## Docs viewer

```bat
cd viewer
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5055

## Stage 1 scope

- Retrieve / answer from indexed emails & docs
- Deterministic **PQA/KPT tariff calculations** (GRT, days, charge type)
- **Email drafts only** — no autonomous send to clients (Phase 2)

## After adding data

```bat
cd bot
python ingest.py
```

Ingest clears and rebuilds the `ops` namespace with metadata (`doc_type`, `vessel`, `port`) so retrieval stays precise as volume grows.

## Example test queries

- `Port Qasim berth fee for 25000 GRT for 3 days`
- `What are on-signer mandatory documents for crew change?`
- `Draft an email listing Pakistan pre-arrival ship documents`
- `Send this to the client` → refused (Stage 1); offers draft instead

## Notes

- `.env` is gitignored — never commit API keys.
- Large `.pst` / `.zip` exports are gitignored; place source data under the project folder before ingest.
- Star Challenger emails are tagged; they are suppressed unless the user asks about that vessel.
