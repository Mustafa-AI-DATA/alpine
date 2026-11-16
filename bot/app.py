"""Alpine Ops Bot — local RAG chat over Pinecone + DeepSeek."""

from __future__ import annotations

from flask import Flask, jsonify, render_template_string, request
from openai import OpenAI
from pinecone import Pinecone

from config import (
    CHAT_MODEL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    PINECONE_API_KEY,
    PINECONE_INDEX,
)

NAMESPACE = "ops"
app = Flask(__name__)

_index = None
_llm = None

SYSTEM = """You are Alpine Marine Ops Assistant.
Answer ONLY from the provided context (emails, SOPs, tariffs, port docs).
If the answer is not in the context, say you do not have that information in the current data.
Be concise and practical. Prefer exact figures, document lists, and process steps.
When useful, mention the source filename from context metadata."""

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Alpine Ops Bot</title>
  <style>
    :root {
      --bg:#0f1a24; --panel:#162533; --line:#2a4558; --text:#e8eef3;
      --muted:#8aa0b2; --accent:#2f9e88;
    }
    * { box-sizing: border-box; }
    body {
      margin:0; font-family:"Segoe UI", system-ui, sans-serif; color:var(--text);
      background: radial-gradient(900px 400px at 0% 0%, #1a3a4a, transparent), var(--bg);
      min-height:100vh; display:flex; flex-direction:column;
    }
    header {
      padding:1rem 1.25rem; border-bottom:1px solid var(--line);
      display:flex; justify-content:space-between; align-items:center;
      background:rgba(15,26,36,.9);
    }
    .brand { font-weight:700; letter-spacing:.04em; }
    .brand span { color:var(--accent); }
    main { flex:1; max-width:900px; width:100%; margin:0 auto; padding:1rem; display:flex; flex-direction:column; }
    #chat { flex:1; overflow:auto; display:flex; flex-direction:column; gap:.75rem; padding-bottom:1rem; }
    .msg { padding:.9rem 1rem; border-radius:12px; border:1px solid var(--line); max-width:92%; white-space:pre-wrap; line-height:1.45; }
    .user { align-self:flex-end; background:#1c3a34; }
    .bot { align-self:flex-start; background:var(--panel); }
    .sources { margin-top:.6rem; color:var(--muted); font-size:.82rem; }
    form { display:flex; gap:.6rem; }
    input {
      flex:1; padding:.85rem 1rem; border-radius:10px; border:1px solid var(--line);
      background:#0b141c; color:var(--text); font-size:1rem;
    }
    button {
      padding:.85rem 1.1rem; border:0; border-radius:10px; background:var(--accent);
      color:#06221c; font-weight:700; cursor:pointer;
    }
    button:disabled { opacity:.6; cursor:wait; }
    .hint { color:var(--muted); font-size:.85rem; margin-bottom:.75rem; }
  </style>
</head>
<body>
  <header>
    <div class="brand">ALPINE <span>Ops Bot</span></div>
    <div style="color:var(--muted);font-size:.85rem">RAG · DeepSeek · Pinecone</div>
  </header>
  <main>
    <div class="hint">Ask about pre-arrival docs, crewing SOP, tariffs, spares, Star Challenger trail.</div>
    <div id="chat"></div>
    <form id="f">
      <input id="q" placeholder="Ask a question..." autocomplete="off" />
      <button type="submit">Ask</button>
    </form>
  </main>
  <script>
    const chat = document.getElementById('chat');
    const form = document.getElementById('f');
    const input = document.getElementById('q');
    const btn = form.querySelector('button');

    function add(role, text, sources) {
      const div = document.createElement('div');
      div.className = 'msg ' + role;
      div.textContent = text;
      if (sources && sources.length) {
        const s = document.createElement('div');
        s.className = 'sources';
        s.textContent = 'Sources: ' + sources.join(' · ');
        div.appendChild(s);
      }
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      add('user', q);
      input.value = '';
      btn.disabled = true;
      try {
        const r = await fetch('/api/ask', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({question: q})
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Request failed');
        add('bot', data.answer, data.sources || []);
      } catch (err) {
        add('bot', 'Error: ' + err.message);
      } finally {
        btn.disabled = false;
        input.focus();
      }
    });
  </script>
</body>
</html>
"""


def get_index():
    global _index
    if _index is None:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _index = pc.Index(PINECONE_INDEX)
    return _index


def get_llm():
    global _llm
    if _llm is None:
        _llm = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _llm


def retrieve(question: str, k: int = 6) -> list[dict]:
    res = get_index().search(
        namespace=NAMESPACE,
        query={"inputs": {"text": question}, "top_k": k},
        fields=["chunk_text", "source"],
    )
    hits = []
    result = res.get("result") if isinstance(res, dict) else getattr(res, "result", None)
    hits_raw = []
    if isinstance(result, dict):
        hits_raw = result.get("hits") or []
    elif result is not None:
        hits_raw = getattr(result, "hits", []) or []
    else:
        # older SDK shape
        hits_raw = (res.get("matches") if isinstance(res, dict) else []) or []

    for m in hits_raw:
        if isinstance(m, dict):
            fields = m.get("fields") or m.get("metadata") or {}
            hits.append(
                {
                    "score": m.get("_score") or m.get("score") or 0,
                    "source": fields.get("source", ""),
                    "text": fields.get("chunk_text") or fields.get("text") or "",
                }
            )
        else:
            fields = getattr(m, "fields", None) or {}
            if hasattr(fields, "get"):
                source = fields.get("source", "")
                text = fields.get("chunk_text") or fields.get("text") or ""
            else:
                source = getattr(fields, "source", "")
                text = getattr(fields, "chunk_text", "") or getattr(fields, "text", "")
            hits.append(
                {
                    "score": getattr(m, "_score", None) or getattr(m, "score", 0) or 0,
                    "source": source,
                    "text": text,
                }
            )
    return hits


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.post("/api/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400
    if not PINECONE_API_KEY or not DEEPSEEK_API_KEY:
        return jsonify({"error": "API keys missing in .env"}), 500

    try:
        hits = retrieve(question)
    except Exception as e:
        return jsonify({"error": f"Pinecone retrieve failed: {e}. Run ingest.py first."}), 500

    if not hits:
        return jsonify(
            {
                "answer": "No indexed data found. Run python ingest.py first.",
                "sources": [],
            }
        )

    context = "\n\n".join(
        f"[source: {h['source']}]\n{h['text']}" for h in hits if h.get("text")
    )
    try:
        completion = get_llm().chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
            temperature=0.2,
        )
        answer = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        return jsonify({"error": f"DeepSeek failed: {e}"}), 500

    sources = []
    for h in hits:
        src = h.get("source") or ""
        if src and src not in sources:
            sources.append(src)
    return jsonify({"answer": answer, "sources": sources[:5]})


if __name__ == "__main__":
    print("Alpine Ops Bot -> http://127.0.0.1:7860")
    app.run(host="127.0.0.1", port=7860, debug=False)
