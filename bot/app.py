"""Alpine Ops Bot — entity-aware RAG + deterministic tariff calc (Stage 1)."""

from __future__ import annotations

import json
import re

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
from retrieve import retrieve
from tariff import calculate_charges, detect_charge_types, format_calculation

NAMESPACE = "ops"
app = Flask(__name__)

_index = None
_llm = None

SYSTEM = """You are Alpine Marine Ops Assistant (Stage 1) — internal ops desk style.

HARD RULES:
1. Answer ONLY from the provided Context and any Calculation block. Do not invent rates or documents.
2. Do NOT mention vessels, ports, or cases that are not in the user question AND not required by the Context.
3. Especially: do NOT bring up "MV Star Challenger" / "MV Star" unless the user asked about that vessel or the Context is exclusively about it and relevant.
4. If Context contains the answer, use it. Never say "data not available" when Context clearly has the figures or lists.
5. For tariff numbers, prefer the Calculation block when present; keep every figure from it.
6. Cite source filenames briefly at the end (from Context labels / Calculation).
7. Stage 1: retrieve/answer and, if asked, EMAIL DRAFT only. NEVER send or claim you emailed a client.
8. If asked to send to a client, refuse send and offer a draft instead.
9. Multi-parameter questions: address each parameter (port, GRT, days, charge type) explicitly.
10. Do not open with filler ("Sure!", "Certainly", "Based on the available data…"). Lead with the answer.

ANSWER STYLE (always):
- Tone: professional maritime ops — clear, direct, scannable. Short sentences.
- Structure every reply like this (omit empty sections):
  1) **Direct answer** — 1–2 lines stating the result / verdict first.
  2) **Details** — bullets or a tight numbered list (docs, steps, rate lines).
  3) **Assumptions / gaps** — only if something is missing or estimated (one short line each).
  4) **Source** — filename(s) only.
- Use markdown: **bold** key figures and section labels; `-` bullets; blank line between sections.
- Tariff / cost replies: put **Estimated total** near the top, then breakdown bullets with amounts, then notes.
- Document / SOP lists: group by category if Context does; do not dump unrelated email narrative.
- Email drafts: label **DRAFT — not sent**, then Subject + body ready to paste. No commentary wrapping the draft.
- If Context is partial: answer what is known first, then list what is still needed — never refuse the whole question when part is answerable.
- Keep replies under ~180 words unless the user asked for a full draft or long checklist.
"""

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Alpine Marine | Ops Assistant</title>
  <link rel="icon" href="https://www.alpinemarine.com/content/upload/images/favicon.gif" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --alpine-blue: #006fd2;
      --alpine-blue-deep: #003d82;
      --alpine-navy: #272f48;
      --alpine-gold: #e6b422;
      --bg: #eef3f9;
      --panel: #ffffff;
      --line: #d5e2ef;
      --text: #272f48;
      --muted: #6b7794;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      font-family: Poppins, "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    .topbar {
      background: #fff;
      border-bottom: 3px solid var(--alpine-gold);
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .topbar-inner {
      max-width: 1080px;
      margin: 0 auto;
      padding: 0.95rem 1.4rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }
    .brand-wrap {
      display: flex;
      align-items: center;
      gap: 1rem;
      text-decoration: none;
      color: inherit;
    }
    .brand-wrap img {
      height: 48px;
      width: auto;
      display: block;
    }
    .brand-meta {
      border-left: 1px solid #dbe5f0;
      padding-left: 1rem;
      line-height: 1.2;
    }
    .brand-meta strong {
      display: block;
      color: var(--alpine-blue);
      font-size: 0.92rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .brand-meta span {
      display: block;
      margin-top: 0.15rem;
      color: var(--muted);
      font-size: 0.7rem;
      font-weight: 400;
    }
    .top-links {
      display: flex;
      align-items: center;
      gap: 1.15rem;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .top-links a {
      color: var(--alpine-blue);
      text-decoration: none;
      font-size: 0.8rem;
      font-weight: 500;
    }
    .top-links a:hover { color: var(--alpine-blue-deep); }
    .top-links .phone {
      font-weight: 600;
      white-space: nowrap;
    }
    .hero {
      background: linear-gradient(180deg, #0084ea 0%, var(--alpine-blue) 45%, var(--alpine-blue-deep) 100%);
      color: #fff;
      padding: 2rem 1.4rem 1.85rem;
      position: relative;
      overflow: hidden;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto -10% -40% 40%;
      height: 180%;
      background: radial-gradient(circle at center, rgba(255,255,255,0.12), transparent 55%);
      pointer-events: none;
    }
    .hero-inner {
      max-width: 1080px;
      margin: 0 auto;
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 1.5rem;
      align-items: end;
    }
    .tagline {
      margin: 0 0 0.85rem;
      font-weight: 300;
      line-height: 1.05;
      letter-spacing: 0.01em;
    }
    .tagline .line {
      display: block;
      font-size: clamp(0.95rem, 1.8vw, 1.15rem);
      opacity: 0.9;
    }
    .tagline .emph {
      display: block;
      font-size: clamp(2rem, 4.5vw, 3.1rem);
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 0.05rem 0 0.35rem;
    }
    .hero-copy p.copy {
      margin: 0;
      max-width: 28rem;
      font-weight: 300;
      font-size: 0.92rem;
      line-height: 1.55;
      opacity: 0.95;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 1rem;
      justify-content: flex-end;
    }
    .chip {
      border: 1px solid rgba(255,255,255,0.4);
      background: rgba(255,255,255,0.1);
      color: #fff;
      border-radius: 2px;
      padding: 0.4rem 0.75rem;
      font-size: 0.72rem;
      font-weight: 500;
      cursor: pointer;
      font-family: inherit;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .chip:hover {
      background: rgba(255,255,255,0.2);
      border-color: var(--alpine-gold);
    }
    main {
      flex: 1;
      width: 100%;
      max-width: 1080px;
      margin: 0 auto;
      padding: 1.25rem 1.4rem 1.6rem;
      display: flex;
      flex-direction: column;
      gap: 0.9rem;
      min-height: 0;
    }
    .section-label {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .section-label h2 {
      margin: 0;
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--alpine-navy);
    }
    .section-label p {
      margin: 0;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.45;
    }
    #chat {
      flex: 1;
      min-height: 420px;
      max-height: calc(100vh - 340px);
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding: 1.1rem;
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 3px solid var(--alpine-blue);
      box-shadow: 0 10px 30px rgba(39,47,72,0.06);
    }
    .msg {
      padding: 0.85rem 1rem;
      border-radius: 2px;
      max-width: min(88%, 760px);
      line-height: 1.55;
      font-size: 0.9rem;
    }
    .user {
      align-self: flex-end;
      background: var(--alpine-blue);
      color: #fff;
      white-space: pre-wrap;
    }
    .bot {
      align-self: flex-start;
      background: #f5f8fc;
      border: 1px solid var(--line);
      color: var(--text);
    }
    .bot .md p { margin: 0 0 0.55rem; }
    .bot .md p:last-child { margin-bottom: 0; }
    .bot .md strong { color: var(--alpine-navy); font-weight: 600; }
    .bot .md ul, .bot .md ol {
      margin: 0.2rem 0 0.55rem;
      padding-left: 1.15rem;
    }
    .bot .md li { margin: 0.2rem 0; }
    .bot .md .draft-block {
      margin-top: 0.35rem;
      padding: 0.65rem 0.75rem;
      background: #fff;
      border-left: 3px solid var(--alpine-gold);
      border: 1px solid var(--line);
      border-left: 3px solid var(--alpine-gold);
      white-space: pre-wrap;
      font-size: 0.86rem;
    }
    .sources {
      margin-top: 0.55rem;
      padding-top: 0.45rem;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.72rem;
    }
    .composer {
      display: flex;
      gap: 0.65rem;
      background: var(--panel);
      border: 1px solid var(--line);
      padding: 0.55rem;
      box-shadow: 0 8px 24px rgba(39,47,72,0.05);
    }
    .composer input {
      flex: 1;
      border: 0;
      outline: none;
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: 0.95rem;
      padding: 0.6rem 0.7rem;
    }
    .composer button {
      border: 0;
      border-radius: 2px;
      background: var(--alpine-blue);
      color: #fff;
      font-weight: 600;
      font-family: inherit;
      padding: 0.75rem 1.35rem;
      cursor: pointer;
      letter-spacing: 0.02em;
    }
    .composer button:hover { background: var(--alpine-blue-deep); }
    .composer button:disabled { opacity: 0.6; cursor: wait; }
    footer {
      background: var(--alpine-navy);
      padding: 1.1rem 1.4rem;
      text-align: center;
      color: rgba(255,255,255,0.72);
      font-size: 0.74rem;
      line-height: 1.55;
    }
    footer a { color: #fff; text-decoration: none; }
    footer a:hover { color: var(--alpine-gold); }
    footer .gold-line {
      width: 48px;
      height: 2px;
      background: var(--alpine-gold);
      margin: 0 auto 0.75rem;
    }
    @media (max-width: 820px) {
      .hero-inner { grid-template-columns: 1fr; }
      .chips { justify-content: flex-start; }
    }
    @media (max-width: 640px) {
      .brand-meta { display: none; }
      .top-links a:not(.phone) { display: none; }
      .brand-wrap img { height: 40px; }
      #chat { max-height: calc(100vh - 380px); min-height: 300px; }
      .hero { padding: 1.5rem 1.1rem 1.4rem; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <a class="brand-wrap" href="https://www.alpinemarine.com/en" target="_blank" rel="noopener">
        <img src="https://www.alpinemarine.com/content/logo-alpine.png" alt="Alpine Marine Services" />
        <div class="brand-meta">
          <strong>Ops Assistant</strong>
          <span>Stage 1 · Draft-only · Internal</span>
        </div>
      </a>
      <div class="top-links">
        <a href="https://www.alpinemarine.com/en" target="_blank" rel="noopener">Website</a>
        <a href="https://www.alpinemarine.com/en/contact" target="_blank" rel="noopener">Contact</a>
        <a class="phone" href="tel:+922135611051">+92 21 3561 1051</a>
      </div>
    </div>
  </div>

  <section class="hero">
    <div class="hero-inner">
      <div class="hero-copy">
        <p class="tagline" aria-label="Anchoring Trust Harbouring Excellence">
          <span class="line">Anchoring</span>
          <span class="emph">Trust</span>
          <span class="line">Harbouring</span>
          <span class="emph">Excellence</span>
        </p>
        <p class="copy">Ask about port tariffs, crewing SOP, pre-arrival documents, and spares. Stage 1 returns grounded answers and email drafts only — no client send.</p>
      </div>
      <div class="chips">
        <button type="button" class="chip" data-q="Port Qasim berth fee for 25000 GRT, 3 days">Port Qasim / KPT tariffs</button>
        <button type="button" class="chip" data-q="Crew change SOP for on-signer and off-signer">Crew change SOP</button>
        <button type="button" class="chip" data-q="Pakistan pre-arrival mandatory documents list">Pre-arrival docs</button>
        <button type="button" class="chip" data-q="Draft an email with Pakistan pre-arrival document list">Email draft</button>
      </div>
    </div>
  </section>

  <main>
    <div class="section-label">
      <h2>Ops Assistant</h2>
      <p>Example: “Port Qasim berth fee for 25000 GRT, 3 days” · “On-signer mandatory documents”</p>
    </div>
    <div id="chat"></div>
    <form class="composer" id="f">
      <input id="q" placeholder="Ask Alpine Ops Assistant…" autocomplete="off" />
      <button type="submit">Ask</button>
    </form>
  </main>

  <footer>
    <div class="gold-line"></div>
    © 2026 Alpine Marine Services Pvt Ltd., All rights reserved ·
    <a href="https://www.alpinemarine.com/en" target="_blank" rel="noopener">alpinemarine.com</a><br />
    36-A/5 Beach Hotel Road, Lalazar Drive, Karachi 74000 Pakistan
  </footer>

  <script>
    const chat = document.getElementById('chat');
    const form = document.getElementById('f');
    const input = document.getElementById('q');
    const btn = form.querySelector('button');

    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function renderMarkdown(text) {
      const raw = String(text || '');
      const draftSplit = raw.match(/^(.*?)(\*\*DRAFT[^*]*\*\*[\s\S]*)$/i);
      let main = raw;
      let draft = '';
      if (draftSplit) {
        main = draftSplit[1].trim();
        draft = draftSplit[2].trim();
      }
      const lines = escapeHtml(main).split('\n');
      const out = [];
      let listType = null;
      const closeList = () => {
        if (listType) { out.push(listType === 'ol' ? '</ol>' : '</ul>'); listType = null; }
      };
      for (const line of lines) {
        const bold = (t) => t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        const mNum = line.match(/^\s*\d+\.\s+(.+)$/);
        const mBul = line.match(/^\s*[-•]\s+(.+)$/);
        if (mNum) {
          if (listType !== 'ol') { closeList(); out.push('<ol>'); listType = 'ol'; }
          out.push('<li>' + bold(mNum[1]) + '</li>');
          continue;
        }
        if (mBul) {
          if (listType !== 'ul') { closeList(); out.push('<ul>'); listType = 'ul'; }
          out.push('<li>' + bold(mBul[1]) + '</li>');
          continue;
        }
        closeList();
        if (!line.trim()) { out.push(''); continue; }
        out.push('<p>' + bold(line) + '</p>');
      }
      closeList();
      let html = '<div class="md">' + out.join('') + '</div>';
      if (draft) {
        html += '<div class="draft-block">' + escapeHtml(draft).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>') + '</div>';
      }
      return html;
    }

    function add(role, text, sources) {
      const div = document.createElement('div');
      div.className = 'msg ' + role;
      if (role === 'bot') div.innerHTML = renderMarkdown(text);
      else div.textContent = text;
      if (sources && sources.length) {
        const s = document.createElement('div');
        s.className = 'sources';
        s.textContent = 'Sources: ' + sources.join(' · ');
        div.appendChild(s);
      }
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    add('bot', '**Ready.** Ask about port tariffs, crewing SOP, or pre-arrival docs — or tap a chip above.');

    document.querySelectorAll('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        input.value = chip.dataset.q || chip.textContent;
        input.focus();
      });
    });

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


def _maybe_tariff_calc(question: str, entities: dict) -> tuple[str | None, dict | None]:
    if not (entities.get("wants_calc") or entities.get("wants_tariff")):
        return None, None
    # Need GRT (or explicit calc intent with numbers)
    grt = entities.get("grt")
    days = entities.get("days")
    if grt is None and not re.search(r"\b(calculate|how much|total)\b", question.lower()):
        # Still allow rate lookup without calc
        if days is None:
            return None, None
    port = (entities.get("ports") or [None])[0]
    # Default Port Qasim if tariff asked without port but "qasim" missing — only if question implies PQA sheet
    if port is None and re.search(r"\b(pqa|qasim|bin qasim)\b", question.lower()):
        port = "Port Qasim"
    if port is None and re.search(r"\b(kpt|karachi)\b", question.lower()):
        port = "Karachi"
    if port is None and (grt is not None or entities.get("wants_calc")):
        port = "Port Qasim"

    if grt is None and entities.get("nrt") is not None:
        result = calculate_charges(port=port, grt=None, nrt=entities.get("nrt"), days=days or 1)
        return format_calculation(result), result

    if grt is None:
        return None, None

    include = detect_charge_types(question)
    result = calculate_charges(
        port=port,
        grt=grt,
        nrt=entities.get("nrt"),
        days=days or 1.0,
        include=include,
    )
    return format_calculation(result), result


def _build_user_prompt(question: str, hits: list[dict], entities: dict, calc_text: str | None) -> str:
    ctx_parts = []
    for h in hits:
        label = h.get("source") or "unknown"
        dtype = h.get("doc_type") or ""
        vessel = h.get("vessel") or ""
        port = h.get("port") or ""
        meta = f"[source: {label} | doc_type: {dtype} | vessel: {vessel} | port: {port}]"
        ctx_parts.append(f"{meta}\n{h.get('text') or ''}")
    context = "\n\n".join(ctx_parts) if ctx_parts else "(no retrieval hits)"

    entity_note = {
        "vessels_in_question": entities.get("vessels") or [],
        "ports_in_question": entities.get("ports") or [],
        "mention_star_challenger": bool(entities.get("mention_star")),
        "stage": "1_draft_only",
    }

    blocks = [
        f"Entity constraints (JSON): {json.dumps(entity_note)}",
        f"Context:\n{context}",
        (
            "Format reminder: lead with the direct answer; then Details as bullets; "
            "then Assumptions/gaps only if needed; end with Source filenames. "
            "Use **bold** for key totals and labels. No filler openers."
        ),
    ]
    if calc_text:
        blocks.append(
            "Calculation (authoritative — use these exact numbers; do not recalculate):\n"
            + calc_text
        )
    if entities.get("wants_draft"):
        blocks.append(
            "User requested an email draft. Output: short lead line, then "
            "**DRAFT — not sent**, then Subject: and Body ready to paste. "
            "Do not claim it was sent."
        )
    if entities.get("wants_calc") or entities.get("wants_tariff"):
        blocks.append(
            "Tariff reply: put Estimated total first, then breakdown bullets, then notes/source."
        )
    blocks.append(f"Question: {question}")
    return "\n\n".join(blocks)


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "stage": 1, "index": PINECONE_INDEX})


@app.post("/api/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400
    if not PINECONE_API_KEY or not DEEPSEEK_API_KEY:
        return jsonify({"error": "API keys missing in .env"}), 500

    # Phase-2 guard: refuse autonomous send
    if re.search(r"\b(send|email this to|mail it to|dispatch to client)\b", question.lower()) and re.search(
        r"\b(client|owner|charterer|master|captain)\b", question.lower()
    ):
        if not re.search(r"\bdraft\b", question.lower()):
            return jsonify(
                {
                    "answer": (
                        "Stage 1 does not send emails to clients. "
                        "I can prepare an email DRAFT for your review/outbox. "
                        "Client send is planned for Phase 2. "
                        "Please ask me to draft the email instead."
                    ),
                    "sources": [],
                    "stage": 1,
                }
            )

    try:
        hits, entities = retrieve(get_index(), NAMESPACE, question, k=8)
    except Exception as e:
        return jsonify({"error": f"Pinecone retrieve failed: {e}. Run ingest.py first."}), 500

    calc_text, calc_result = _maybe_tariff_calc(question, entities)

    # If we have a successful calculation and weak context, still answer from calc
    if calc_result and calc_result.get("ok") and (
        entities.get("wants_calc")
        or (entities.get("grt") is not None and entities.get("wants_tariff"))
    ):
        # For pure calc questions, return deterministic answer directly (most reliable)
        if entities.get("wants_calc") or entities.get("grt") is not None:
            sources = ["Port Tariiff of PQA & KPT.xls"]
            for h in hits:
                src = h.get("source") or ""
                if src and src not in sources and (
                    "tariiff" in src.lower() or "tariff" in src.lower()
                ):
                    sources.append(src)
            # Optionally enrich with LLM phrasing but keep numbers from calc
            try:
                completion = get_llm().chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {
                            "role": "user",
                            "content": _build_user_prompt(question, hits, entities, calc_text),
                        },
                    ],
                    temperature=0.1,
                )
                answer = (completion.choices[0].message.content or "").strip()
                # Safety: if model still hedges "no data", fall back to calc text
                if re.search(r"not (available|in (the )?(data|record|context))|do not have", answer.lower()):
                    answer = calc_text or answer
            except Exception:
                answer = calc_text or "Calculation completed."
            return jsonify(
                {
                    "answer": answer,
                    "sources": sources[:5],
                    "calculation": calc_result,
                    "stage": 1,
                }
            )

    if not hits and not calc_text:
        return jsonify(
            {
                "answer": "No indexed data found for this query. Run python ingest.py, or rephrase with port/vessel/topic.",
                "sources": [],
                "stage": 1,
            }
        )

    try:
        completion = get_llm().chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": _build_user_prompt(question, hits, entities, calc_text),
                },
            ],
            temperature=0.15,
        )
        answer = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        return jsonify({"error": f"DeepSeek failed: {e}"}), 500

    if calc_text and re.search(r"not (available|in (the )?(data|record|context))", answer.lower()):
        answer = calc_text

    sources = []
    if calc_result and calc_result.get("ok"):
        sources.append("Port Tariiff of PQA & KPT.xls")
    for h in hits:
        src = h.get("source") or ""
        if src and src not in sources:
            sources.append(src)

    return jsonify(
        {
            "answer": answer,
            "sources": sources[:6],
            "calculation": calc_result,
            "entities": {
                "vessels": entities.get("vessels"),
                "ports": entities.get("ports"),
                "doc_types": entities.get("doc_types"),
            },
            "stage": 1,
        }
    )


if __name__ == "__main__":
    print("Alpine Ops Bot -> http://127.0.0.1:7860")
    app.run(host="127.0.0.1", port=7860, debug=False)
