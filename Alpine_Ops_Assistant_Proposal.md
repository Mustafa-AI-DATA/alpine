# Product Proposal  
## Alpine Ops Assistant — AI Operations Desk for Alpine Marine Services

**Prepared for:** Alpine Marine Services Pvt Ltd  
**Product:** Alpine Ops Assistant  
**Live demo:** https://alpine-ops-bot.vercel.app  
**Website alignment:** https://www.alpinemarine.com/en  
**Date:** 25 November 2026  
**Status:** Stage 1 live (internal) · Stages 2–3 proposed  

---

### 1. Executive summary

Alpine Ops Assistant is an internal AI operations desk trained on Alpine’s own emails, SOPs, pre-arrival documentation, crewing procedures, and port tariff sheets (PQA / KPT).

**Today (Stage 1):** staff can ask operational questions and get grounded answers plus **email drafts only**. Nothing is sent to clients automatically.

**After two further steps (Stage 2 then Stage 3):** the same assistant will sit on the live mailbox path — reading inbound ops mail, drafting replies from Alpine knowledge, and (with controls) helping every relevant email thread — **only after mailbox Two-Step / MFA verification is enabled** for secure connection.

---

### 2. Problem we solve

| Today without the product | With Alpine Ops Assistant |
|---|---|
| Tariff / SOP answers depend on who is online | Instant, consistent answers from indexed Alpine files |
| Pre-arrival / crewing replies rewritten from scratch | Draft ready in Alpine tone, from past trails & SOPs |
| Risk of wrong vessel / wrong rate in hurry | Entity filters + deterministic tariff calculator |
| Knowledge stuck in inboxes and Excel | Searchable ops memory that grows with ingest |

---

### 3. What is live now — Stage 1 (current)

**Scope**

- Chat UI branded to Alpine Marine (logo, colours, tagline)
- Answers from indexed Alpine emails & documents only (grounded RAG)
- **Port tariff estimates** (e.g. Port Qasim / KPT berth by GRT × days) with clear breakdown
- Crewing SOP / pre-arrival document answers
- **Email DRAFT only** — labelled “not sent”; ops reviews and sends manually
- Hard block: “send to client” is refused in Stage 1

**What Stage 1 does *not* do**

- Does not connect to live Outlook / mailbox send
- Does not auto-reply to every inbound email
- Does not replace human approval on client communication

---

### 4. Roadmap — two steps to “live on every email”

```
Stage 1 (NOW)          Stage 2                    Stage 3
Internal Q&A     →     Secure mailbox connect  →  Live on every ops email
+ drafts only          + approve-before-send      + assist each thread
```

#### Stage 2 — Secure mailbox + human-approved send

**Goal:** Connect the assistant to Alpine’s ops mailbox so drafts can be placed in Outlook / sent **only after a human clicks Approve**.

**What Alpine must enable**

1. **Two-Step Verification (2FA / MFA)** on the Microsoft 365 / Google Workspace account used for ops mail  
2. App registration / OAuth consent by Alpine IT admin  
3. Named mailbox(es) or shared mailbox access for Port Agency / Husbandry / Crewing (as agreed)  
4. Written send policy: who may approve; which folders / senders are in scope  

**Why 2FA is mandatory**  
Live email access without MFA is a security risk. Stage 2 will **not** go live until Two-Step Verification is ON for the connected account(s). This protects Alpine’s client correspondence and meets normal enterprise mailbox standards.

**Stage 2 deliverables**

- Mailbox connect (read + draft / send-on-approve)
- “Approve & send” / “Edit & send” / “Discard” in UI or Outlook add-in
- Audit log: who approved what, when
- Still **no** fully silent auto-send to clients unless Stage 3 policy allows it

#### Stage 3 — Live assist on every relevant email

**Goal:** For every inbound ops email in scope, the assistant:

- Detects intent (tariff, pre-arrival docs, crewing, spares, PDA, etc.)
- Pulls the right Alpine knowledge
- Prepares a reply draft **on that thread**
- Optional: auto-file / tag / escalate; optional supervised auto-send for low-risk templates only

**Controls (required before go-live)**

- Allow-list of folders / mailboxes  
- Block-list of clients / topics (legal, claims, commercial disputes → human only)  
- Confidence threshold: low confidence → draft only, never send  
- Daily digest of assisted emails for ops manager  

---

### 5. Security & compliance (email go-live prerequisites)

| Requirement | Owner | Notes |
|---|---|---|
| Two-Step Verification / MFA ON | Alpine IT / mailbox owner | **Blocking** for Stage 2–3 |
| Least-privilege mailbox access | Alpine IT | Shared mailbox preferred over personal |
| Admin consent for OAuth app | Alpine IT | Microsoft / Google |
| Send approval policy signed | Alpine Ops + Management | Who can release client mail |
| No secrets in chat logs | Vendor | API keys stay in secure env; `.env` never shared |
| Data residency / retention | Joint | Agree retention of drafts & audit logs |

---

### 6. Suggested AI approach — Local LLM vs OpenAI / Gemini (cost & security)

Alpine Ops Assistant does **not** dump the full email archive into the language model. Architecture is **RAG + vectors**:

1. Alpine emails / SOPs / tariffs are converted into **embeddings (vectors)** and stored in **Pinecone**  
2. On each question, only the **relevant short chunks** are retrieved  
3. The LLM (OpenAI, Gemini, DeepSeek, etc.) writes the **answer / draft** from those chunks  
4. Ops gets a **real, usable response** — without hosting a full private model on Alpine servers  

#### Option A — Local LLM (on Alpine / your own servers)

| | |
|---|---|
| **Where cost sits** | On **Alpine’s system**: GPU/CPU server, electricity, cooling, IT maintenance, model upgrades, downtime risk |
| **CapEx / OpEx** | High one-time hardware + ongoing admin (often **Rs several lakh+** in hardware alone for usable quality) |
| **Quality** | Weaker unless expensive hardware + strong open models are maintained |
| **When it makes sense** | Strict air-gapped policy with no external API allowed |

**Suggestion:** Local LLM is possible later if Alpine IT mandates it — but **cost and ops burden stay on Alpine’s infrastructure**, not on cheap per-query API bills.

#### Option B — Cloud LLM (OpenAI / Gemini / current DeepSeek) + Pinecone *(recommended)*

| | |
|---|---|
| **Where cost sits** | **API usage only** (pay for questions / drafts processed) — capped monthly in PKR as in §7 |
| **Security** | Source files are **not** stored as a full searchable dump inside OpenAI/Gemini. Knowledge lives as **vectors in Pinecone**; the model sees **only retrieved snippets** for that query |
| **Response quality** | Strong commercial models → clear tariff / SOP / email drafts (as in Stage 1 demo) |
| **Scaling** | No Alpine GPU farm; Stage 2–3 email volume scales with API, not new servers |

**Security point for management:**  
Vectors are mathematical representations used for search — the live path is *retrieve → answer*. Combined with MFA on mailbox (Stage 2+), approve-before-send, and audit logs, this is the practical enterprise path for a Pakistani ops company that wants **security + lower running cost**.

#### Side-by-side (for decision makers)

| Point | Local LLM | OpenAI / Gemini + Pinecone |
|---|---|---|
| Main cost | Alpine hardware & IT time | API usage (PKR monthly, can be capped) |
| Data pattern | Full model + files on your box | Vectors in Pinecone; snippets only to LLM |
| Answers | Possible, quality depends on hardware | Real ops-grade answers (current Stage 1) |
| Go-live Stage 2–3 | Harder / slower / costlier | Faster; same mailbox MFA rules apply |
| **Our suggestion** | Only if policy forces air-gap | **Preferred for Alpine — lower cost, secure RAG design** |

**Recommendation to Alpine:** Stay on **cloud LLM + Pinecone vectors** for Stages 1–3. Keep **local LLM** as an optional Phase-later upgrade if board/IT require full on-prem inference — with a separate hardware & support quote at that time.

---

### 7. Commercial charges (proposed) — **PKR only**

**Billing currency: Pakistani Rupee (PKR).**  
Pricing is kept **practical for a Karachi ops company** — enough to run the product properly, not inflated “AI buzz” numbers. Goal: Alpine can approve a **small first payment now**, use Stage 1, then unlock Stage 2–3 when MFA is ready.  
Tax: **+ SST / sales tax as applicable** (separate on invoice).  
Cloud AI API cost stays low (usage-based); see §6.

#### A. First payment (to lock & continue) — ask this first

| Item | Amount (PKR) | Against |
|---|---|---|
| **Advance / first payment** | **Rs 75,000** | Stage 1 activation + 1st month retainer + roadmap kickoff |
| Balance of Month 1 (if any) | — | Included in the Rs 75,000 for standard Stage 1 start |

After this payment: Stage 1 stays live for Alpine ops; feedback cycle starts; Stage 2 planning begins once MFA is ON.

#### B. One-time setup when moving to email (PKR)

| Item | Scope | Proposed (PKR) |
|---|---|---|
| **Stage 1 build** (already delivered) | RAG, tariff calc, Alpine UI, hosting | **Included** (covered via first payment / Stage 1 retainer) |
| **Stage 2 integration** | Mailbox OAuth, approve-to-send, audit log | **Rs 150,000 – 200,000** |
| **Stage 3 automation** | Per-email assist, rules, confidence gates, digest | **Rs 200,000 – 275,000** |
| **Stage 2 + 3 together** (bundle) | Both setups if approved in one go | **Rs 320,000 – 425,000** *(save vs buying separate)* |

#### C. Monthly retainer — PKR / month

| Package | Includes | Proposed / month (PKR) |
|---|---|---|
| **Ops Desk — Stage 1** | Hosted bot, light ingest updates, support | **Rs 40,000 – 50,000** |
| **Mailbox Assist — Stage 2** | Stage 1 + 1 mailbox + approve-to-send | **Rs 65,000 – 85,000** |
| **Live Mail Ops — Stage 3** | Stage 2 + in-scope every-email assist + monthly tuning | **Rs 95,000 – 125,000** |

*Suggested start:* **Rs 45,000 / month** Stage 1 after the Rs 75,000 first payment (first month folded into advance as above).

#### D. Usage / extras (PKR) — keep light

| Item | Proposed (PKR) |
|---|---|
| AI API (Pinecone + LLM) | Usually **inside retainer**; if heavy use, cap **Rs 15,000 – 25,000 / month** extra |
| Extra mailbox | **+ Rs 15,000 / month** |
| Extra named user seat | **+ Rs 3,000 / month** |
| Big PST re-ingest | **Rs 25,000 – 40,000** per major load |
| New tariff / SOP pack wiring | **Rs 15,000 – 25,000** |
| Ops training (2 hrs) | **Rs 15,000** |

#### E. Simple year picture (honest, closable)

| Path | Rough Year-1 (PKR) |
|---|---|
| **Stage 1 only** (12 × ~45k) | **~5.5 – 6 lakh** |
| **+ Stage 2** (setup ~1.75 lakh + higher retainer part-year) | **~8 – 10 lakh** |
| **Full Stage 1→3** (bundle setup + Stage 3 retainer) | **~15 – 18 lakh** — not 9 lakh *per setup line* |

**Commercial ask in the meeting:** approve **Rs 75,000 first payment** → continue Stage 1 → enable MFA → then Stage 2 quote at **~1.5–2 lakh** setup when ready.

---

### 8. What Alpine must do before Stage 2 kickoff

1. Confirm ops mailbox(es) to connect (e.g. agency / husbandry / crewing).  
2. Turn **ON Two-Step Verification** for that account / tenant.  
3. Nominate IT contact for OAuth admin consent.  
4. Nominate Ops owner for send-approval rules.  
5. Confirm preferred package (Stage 2 only vs Stage 2+3).  

---

### 9. Success measures

- Tariff / pre-arrival answers match Alpine sheets (spot checks ≥ 90%)  
- Draft turnaround for standard queries: **&lt; 1 minute**  
- Stage 2: zero client sends without human approve  
- Stage 3: ≥ 70% of in-scope inbound mails get a usable draft same day  
- No MFA / no go-live on live mail  

---

### 10. Recommendation

| Step | Action | Timing |
|---|---|---|
| **Now** | Approve **Rs 75,000 first payment** → Stage 1 live use on https://alpine-ops-bot.vercel.app | This meeting / this week |
| **Model choice** | Prefer **OpenAI / Gemini (or DeepSeek) + Pinecone**; local LLM only if IT mandates | With first payment |
| **Step 1 of 2** | Enable **Two-Step Verification**; Stage 2 setup **~Rs 1.5–2 lakh** + approve-to-send | After MFA |
| **Step 2 of 2** | Stage 3 — every in-scope email (**~Rs 2–2.75 lakh** setup, or bundle) | After Stage 2 stable |

---

### 11. Acceptance

| | Name | Signature | Date |
|---|---|---|---|
| Alpine Marine — Commercial / Ops | | | |
| Alpine Marine — IT (MFA / mailbox) | | | |
| Product / Delivery | | | |

---

**Contact for this proposal:** DigiGrey / project delivery team for Alpine Ops Assistant  

*This document is a commercial proposal, not a binding contract until a countersigned PKR quote / SOW is issued. All commercial figures above are in PKR. Hosting, AI API FX, SST/sales tax, and Microsoft/Google mailbox policies may adjust the final invoice.*
