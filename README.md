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

## Notes

- `.env` is gitignored — never commit API keys.
- Large `.pst` / `.zip` exports are gitignored; place source data under the project folder before ingest.
