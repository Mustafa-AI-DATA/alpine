"""Entity / doc-type tagging for scalable RAG metadata."""

from __future__ import annotations

import re
from pathlib import Path

VESSEL_PATTERNS = [
    (r"\bstar\s*challenger\b", "MV Star Challenger"),
    (r"\bzhong\s*chang\s*528\b", "MV Zhong Chang 528"),
    (r"\bjing\s*dian\s*chen\s*guang\b", "MV Jing Dian Chen Guang"),
]

PORT_PATTERNS = [
    (r"\bport\s*qasim\b|\bpqa\b|\bbin\s*qasim\b|\bpqepct\b|\bpqepc\b", "Port Qasim"),
    (r"\bkarachi\b|\bkpt\b", "Karachi"),
]

DOC_TYPE_RULES = [
    ("tariff", ("port tariiff", "port tariff", "pqa & kpt", "general port tariff")),
    ("terminal_params", ("terminal parameters", "port qasim terminal")),
    ("crewing_sop", ("crewing", "crew change", "sop for crewing", "emails sent for crewing")),
    ("spares", ("spares clearance",)),
    ("cargo_enquiry", ("wheat cargo", "standard enquries", "standard enquiries", "peas")),
    ("pre_arrival", ("pre arrival", "pre-arrival", "ship documents for pakistan", "fal", "psw")),
    ("vessel_email", ("extracted_emails", "email trail", "star challenger")),
]


def detect_vessels(text: str) -> list[str]:
    found = []
    low = text.lower()
    for pat, name in VESSEL_PATTERNS:
        if re.search(pat, low, re.I) and name not in found:
            found.append(name)
    # generic MV. NAME capture (limited)
    for m in re.finditer(r"\bMV\.?\s+([A-Z][A-Za-z0-9 \-]{2,40})", text):
        name = "MV " + re.sub(r"\s+", " ", m.group(1)).strip(" -/.")
        if len(name) > 5 and name not in found and "star" not in name.lower():
            # keep shortlist; avoid noise
            if any(k in name.upper() for k in ("ZHONG", "JING", "CHALLENGER")):
                found.append(name)
    return found


def detect_ports(text: str) -> list[str]:
    found = []
    low = text.lower()
    for pat, name in PORT_PATTERNS:
        if re.search(pat, low, re.I) and name not in found:
            found.append(name)
    return found


def detect_doc_type(source: str, text: str = "") -> str:
    blob = f"{source} {text[:500]}".lower().replace("\\", "/")
    for dtype, keys in DOC_TYPE_RULES:
        if any(k in blob for k in keys):
            return dtype
    if source.lower().endswith((".eml", ".txt")):
        return "email"
    if source.lower().endswith((".xls", ".xlsx", ".csv")):
        return "spreadsheet"
    if source.lower().endswith((".pdf", ".doc", ".docx")):
        return "document"
    return "general"


def extract_query_entities(question: str) -> dict:
    """Parse user question for vessels, ports, intent hints."""
    q = question.strip()
    low = q.lower()
    vessels = detect_vessels(q)
    ports = detect_ports(q)

    wants_tariff = bool(
        re.search(
            r"\b(tariff|pilotage|berth\s*fee|port\s*dues|anchorage|grt|nrt|calculate|rate|charges?|cost|"
            r"kitna\s+(lagega|hoga)|total\s+rate)\b",
            low,
        )
    )
    wants_crewing = bool(re.search(r"\b(crew|on-?signer|off-?signer|oktb|landing\s*permit)\b", low))
    wants_spares = bool(re.search(r"\bspares?\b", low))
    wants_prearrival = bool(
        re.search(
            r"\b(pre-?arrival|psw|fal|ship documents|document list|pakistan\s+call|"
            r"pre\s*arrival\s+document)\b",
            low,
        )
    )
    wants_draft = bool(
        re.search(
            r"\b(draft\s+(an?\s+)?email|write\s+(an?\s+)?email|compose\s+(an?\s+)?email|email\s+draft|"
            r"email\s+draft\s+taiyar|draft\s+taiyar|taiyar\s+karo|outbox|outlook\s+ke\s+liye)\b",
            low,
        )
    )
    wants_calc = bool(
        re.search(
            r"\b(calculate|computation|how\s+much|total\s+(cost|rate)|step-?by-?step|"
            r"for\s+\d+\s*(days?|din)|"
            r"\d+\s*(days?|din)\s*(ke\s+liye)?)\b",
            low,
        )
    ) or (wants_tariff and bool(re.search(r"\b\d+(\.\d+)?\s*(grt|nrt|days?|din)\b", low)))

    # Meta / policy-only questions (empty retrieval). Do NOT flag draft requests
    # that merely say "send mat karo", or factual Qs that also say "don't invent".
    is_policy = False
    if not wants_draft and not wants_tariff and not wants_calc and not wants_prearrival:
        is_policy = bool(
            re.search(
                r"(send\s+kar\s+sakte|khud\s+se\s+email\s+send|"
                r"record\s+mein\s+koi\s+value|rule\s+nahi\s+milta|"
                r"kisi\s+vessel\s+ka\s+naam\s+nahi|kyun\s+kar\s+rahe|"
                r"why\s+.*(mv\s*star|star\s*challenger)|"
                r"can\s+you\s+send|"
                r"if\s+(no|not).*(data|record|rule))",
                low,
            )
        )

    doc_types: list[str] = []
    if wants_tariff or wants_calc:
        doc_types.append("tariff")
    if wants_crewing:
        doc_types.append("crewing_sop")
    if wants_spares:
        doc_types.append("spares")
    if wants_prearrival or (wants_draft and not wants_tariff):
        doc_types.append("pre_arrival")

    grt = None
    nrt = None
    days = None
    m = re.search(r"\b(\d{3,6}(?:\.\d+)?)\s*grt\b", low)
    if m:
        grt = float(m.group(1))
    m = re.search(r"\bgrt\s*[:=]?\s*(\d{3,6}(?:\.\d+)?)\b", low)
    if m and grt is None:
        grt = float(m.group(1))
    m = re.search(r"\b(\d{3,6}(?:\.\d+)?)\s*nrt\b", low)
    if m:
        nrt = float(m.group(1))
    m = re.search(r"\bnrt\s*[:=]?\s*(\d{3,6}(?:\.\d+)?)\b", low)
    if m and nrt is None:
        nrt = float(m.group(1))
    m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*days?\b", low)
    if m:
        days = float(m.group(1))
    m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*din\b", low)
    if m and days is None:
        days = float(m.group(1))
    m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*din\s*ke\s*liye\b", low)
    if m and days is None:
        days = float(m.group(1))

    # Only true if user is asking ABOUT that vessel — not meta "why mention Star"
    mention_star = bool(
        re.search(r"\bstar\s*challenger\b|\bmv\.?\s*star\b|\bmt\.?\s*star\b", low)
    ) and not bool(
        re.search(r"(kyun|why).{0,40}(star|naam\s+nahi)|naam\s+nahi\s+liya", low)
    )

    return {
        "vessels": vessels,
        "ports": ports,
        "doc_types": doc_types,
        "wants_tariff": wants_tariff,
        "wants_crewing": wants_crewing,
        "wants_spares": wants_spares,
        "wants_prearrival": wants_prearrival,
        "wants_draft": wants_draft,
        "wants_calc": wants_calc or (grt is not None and wants_tariff),
        "grt": grt,
        "nrt": nrt,
        "days": days,
        "mention_star": mention_star,
        "is_policy": is_policy,
        "source_path": "",
    }


def build_record_metadata(source: str, text: str) -> dict:
    vessels = detect_vessels(f"{source} {text[:2000]}")
    ports = detect_ports(f"{source} {text[:2000]}")
    doc_type = detect_doc_type(source, text)
    # Pinecone metadata: use scalars / lists of strings carefully
    vessel = vessels[0] if vessels else "NONE"
    port = ports[0] if len(ports) == 1 else ("MULTI" if ports else "NONE")
    return {
        "source": source.replace("\\", "/"),
        "doc_type": doc_type,
        "vessel": vessel,
        "port": port,
        "vessels": ", ".join(vessels) if vessels else "NONE",
        "ports": ", ".join(ports) if ports else "NONE",
        "filename": Path(source).name,
    }
