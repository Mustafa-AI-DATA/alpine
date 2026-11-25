"""Entity-aware retrieval with doc-type routing and Star-bias control."""

from __future__ import annotations

from typing import Any

from metadata_utils import extract_query_entities


def _as_dict_hit(m: Any) -> dict:
    if isinstance(m, dict):
        fields = m.get("fields") or m.get("metadata") or {}
        return {
            "score": float(m.get("_score") or m.get("score") or 0),
            "source": fields.get("source", "") or "",
            "text": fields.get("chunk_text") or fields.get("text") or "",
            "doc_type": fields.get("doc_type", "") or "",
            "vessel": fields.get("vessel", "") or "",
            "port": fields.get("port", "") or "",
        }
    fields = getattr(m, "fields", None) or {}
    if hasattr(fields, "get"):
        return {
            "score": float(getattr(m, "_score", None) or getattr(m, "score", 0) or 0),
            "source": fields.get("source", "") or "",
            "text": fields.get("chunk_text") or fields.get("text") or "",
            "doc_type": fields.get("doc_type", "") or "",
            "vessel": fields.get("vessel", "") or "",
            "port": fields.get("port", "") or "",
        }
    return {
        "score": float(getattr(m, "_score", None) or getattr(m, "score", 0) or 0),
        "source": getattr(fields, "source", "") or "",
        "text": getattr(fields, "chunk_text", "") or getattr(fields, "text", "") or "",
        "doc_type": getattr(fields, "doc_type", "") or "",
        "vessel": getattr(fields, "vessel", "") or "",
        "port": getattr(fields, "port", "") or "",
    }


def _search_raw(index, namespace: str, text: str, top_k: int, flt: dict | None = None) -> list[dict]:
    query: dict[str, Any] = {"inputs": {"text": text}, "top_k": top_k}
    if flt:
        query["filter"] = flt
    try:
        res = index.search(
            namespace=namespace,
            query=query,
            fields=["chunk_text", "source", "doc_type", "vessel", "port"],
        )
    except Exception:
        # Older indexes may not have new metadata fields yet
        res = index.search(
            namespace=namespace,
            query={"inputs": {"text": text}, "top_k": top_k},
            fields=["chunk_text", "source"],
        )
    result = res.get("result") if isinstance(res, dict) else getattr(res, "result", None)
    if isinstance(result, dict):
        hits_raw = result.get("hits") or []
    elif result is not None:
        hits_raw = getattr(result, "hits", []) or []
    else:
        hits_raw = (res.get("matches") if isinstance(res, dict) else []) or []
    return [_as_dict_hit(m) for m in hits_raw]


def _expand_queries(question: str, entities: dict) -> list[str]:
    qs = [question]
    if entities.get("wants_tariff") or entities.get("wants_calc"):
        port = (entities.get("ports") or ["Port Qasim"])[0]
        qs.append(f"{port} port tariff berth fee pilotage port dues anchorage GRT")
        qs.append("PORT CHARGES OF PQA & KPT General Port Tariff")
    if entities.get("wants_crewing"):
        qs.append("crew change SOP on-signer off-signer mandatory documents OKTB")
    if entities.get("wants_spares"):
        qs.append("spares clearance Karachi airport charges consignee documents")
    if entities.get("wants_prearrival"):
        qs.append("Pakistan call ship documents PSW FAL forms pre-arrival list")
    # de-dupe preserve order
    out, seen = [], set()
    for q in qs:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def _is_star_chunk(h: dict) -> bool:
    blob = f"{h.get('source','')} {h.get('vessel','')} {h.get('text','')}".lower()
    return "star challenger" in blob or "mv star" in blob or "\\extracted_emails\\" in blob.replace("/", "\\").lower() or "/extracted_emails/" in blob.replace("\\", "/").lower()


def _dedupe(hits: list[dict]) -> list[dict]:
    out, seen = [], set()
    for h in hits:
        key = (h.get("source", ""), (h.get("text") or "")[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def retrieve(index, namespace: str, question: str, k: int = 8) -> tuple[list[dict], dict]:
    entities = extract_query_entities(question)
    queries = _expand_queries(question, entities)

    collected: list[dict] = []

    # 1) Targeted doc_type searches first (high precision)
    for dtype in entities.get("doc_types") or []:
        for q in queries[:2]:
            flt = {"doc_type": {"$eq": dtype}}
            collected.extend(_search_raw(index, namespace, q, top_k=6, flt=flt))

    # 2) Port filter if present
    for port in entities.get("ports") or []:
        collected.extend(
            _search_raw(
                index,
                namespace,
                question,
                top_k=6,
                flt={"port": {"$eq": port}},
            )
        )

    # 3) Vessel-specific if named
    for vessel in entities.get("vessels") or []:
        collected.extend(
            _search_raw(
                index,
                namespace,
                question,
                top_k=6,
                flt={"vessel": {"$eq": vessel}},
            )
        )

    # 4) Broad search
    for q in queries:
        collected.extend(_search_raw(index, namespace, q, top_k=k))

    collected = _dedupe(collected)

    # Hard ban Star Challenger when user did not name that vessel
    allow_star = bool(entities.get("mention_star")) or any(
        "star" in (v or "").lower() for v in (entities.get("vessels") or [])
    )
    if not allow_star:
        collected = [h for h in collected if not _is_star_chunk(h)]

    # Prefer tariff/crewing/pre_arrival chunks when those intents are active
    preferred_types = set(entities.get("doc_types") or [])
    if preferred_types:
        preferred = [h for h in collected if h.get("doc_type") in preferred_types]
        other = [h for h in collected if h.get("doc_type") not in preferred_types]
        collected = preferred + other

    # Policy / meta questions: do not ground on vessel email trails
    if entities.get("is_policy"):
        collected = []

    # Draft / pre-arrival with empty pool after Star ban: retry topic search
    if not collected and (entities.get("wants_draft") or entities.get("wants_prearrival")):
        for q in (
            "Pakistan call ship documents PSW FAL forms pre-arrival list",
            "pre-arrival mandatory documents for Pakistan port call",
            "list of ship documents for Pakistan call",
        ):
            collected.extend(_search_raw(index, namespace, q, top_k=8))
        collected = _dedupe(collected)
        if not allow_star:
            collected = [h for h in collected if not _is_star_chunk(h)]

    # Sort by score desc
    collected.sort(key=lambda h: h.get("score", 0), reverse=True)
    return collected[:k], entities
