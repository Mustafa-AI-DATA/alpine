"""Load Alpine docs/emails and upsert into Pinecone with rich metadata."""

from __future__ import annotations

import email
import hashlib
import re
import time
from email import policy
from pathlib import Path

from openai import OpenAI
from pinecone import Pinecone

from config import (
    CHAT_MODEL,
    DATA_DIRS,
    DATA_FILES,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    EMBED_MODEL,
    PINECONE_API_KEY,
    PINECONE_CLOUD,
    PINECONE_INDEX,
    PINECONE_REGION,
    ROOT,
)
from metadata_utils import build_record_metadata, detect_doc_type

NAMESPACE = "ops"


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    """Paragraph-aware chunking; keeps more structure than whitespace-collapse-only."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    # Prefer splitting on blank lines / row boundaries
    parts = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) + 1 <= size:
            buf = f"{buf}\n{part}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(part) <= size:
                buf = part
            else:
                # hard wrap long part
                i = 0
                while i < len(part):
                    chunks.append(part[i : i + size])
                    i += max(size - overlap, 1)
                buf = ""
    if buf:
        chunks.append(buf)
    # secondary overlap windows for long single chunks already handled
    return chunks


def chunk_tariff_rows(text: str) -> list[str]:
    """One/few tariff rows per chunk so rate lines stay retrievable."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header = ""
    chunks = []
    for ln in lines:
        if ln.lower().startswith("sheet:") or "port charges" in ln.lower() or ln.lower().startswith("s#"):
            header = ln
            continue
        if "|" in ln or re.match(r"^\d+(\.0)?\s", ln):
            body = f"{header}\n{ln}" if header else ln
            # attach neighboring context: keep as single-row chunk + short prefix
            chunks.append(
                "Port tariff row (PQA & KPT, effective 02-06-2023).\n"
                "Use for Port Qasim / Karachi rate lookups and GRT/day calculations.\n"
                + body
            )
    # also keep a compact summary chunk
    if lines:
        chunks.insert(
            0,
            "PORT CHARGES OF PQA & KPT EFFECTIVE FROM 02-06-2023. "
            "Covers Port Qasim (PQA) and Karachi Port (KPT): pilotage, berth fee, port dues, "
            "tugs, anchorage, pipeline, shifting, cancellation, Sindh Sales Tax 13%. "
            "Rates are primarily GRT-based.",
        )
    return chunks or chunk_text(text)


def read_eml(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    parts = []
    for key in ("From", "To", "Cc", "Subject", "Date"):
        if msg.get(key):
            parts.append(f"{key}: {msg.get(key)}")
    texts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    texts.append(part.get_content())
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    texts.append(payload.decode(part.get_content_charset() or "utf-8", "ignore"))
    else:
        try:
            texts.append(msg.get_content())
        except Exception:
            payload = msg.get_payload(decode=True) or b""
            texts.append(payload.decode("utf-8", "ignore"))
    parts.append("\n".join(texts))
    return "\n".join(parts)


def read_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(lines)


def read_xls(path: Path) -> str:
    import xlrd

    book = xlrd.open_workbook(str(path))
    lines = []
    for sheet in book.sheets():
        lines.append(f"Sheet: {sheet.name}")
        for r in range(sheet.nrows):
            row = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
            if any(row):
                lines.append(" | ".join(row))
    return "\n".join(lines)


def read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_documents() -> list[dict]:
    docs: list[dict] = []

    def add(path: Path, text: str):
        text = text.strip()
        if len(text) < 40:
            return
        rel = str(path.relative_to(ROOT)).replace("\\", "/") if path.is_relative_to(ROOT) else path.name
        docs.append({"source": rel, "text": text, "doc_type": detect_doc_type(rel, text)})

    for folder in DATA_DIRS:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            try:
                if ext == ".txt":
                    add(path, read_txt(path))
                elif ext == ".eml":
                    add(path, read_eml(path))
            except Exception as e:
                print("skip", path.name, e)

    for path in DATA_FILES:
        if not path.exists():
            continue
        ext = path.suffix.lower()
        try:
            if ext == ".eml":
                add(path, read_eml(path))
            elif ext == ".docx":
                add(path, read_docx(path))
            elif ext == ".xls":
                add(path, read_xls(path))
        except Exception as e:
            print("skip", path.name, e)

    pdf = ROOT / "Port Qasim Terminal Parameters.pdf"
    if pdf.exists():
        try:
            from pypdf import PdfReader

            pages = [(page.extract_text() or "") for page in PdfReader(str(pdf)).pages]
            add(pdf, "\n".join(pages))
        except Exception as e:
            print("pdf skip", e)

    return docs


def ensure_index(pc: Pinecone):
    names = {i["name"] for i in pc.list_indexes()}
    if PINECONE_INDEX not in names:
        print("Creating index", PINECONE_INDEX, "with model", EMBED_MODEL)
        pc.create_index_for_model(
            name=PINECONE_INDEX,
            cloud=PINECONE_CLOUD,
            region=PINECONE_REGION,
            embed={
                "model": EMBED_MODEL,
                "field_map": {"text": "chunk_text"},
            },
        )
        for _ in range(30):
            desc = pc.describe_index(PINECONE_INDEX)
            status = getattr(desc, "status", None) or {}
            ready = status.get("ready") if isinstance(status, dict) else getattr(status, "ready", False)
            if ready:
                break
            time.sleep(2)
    return pc.Index(PINECONE_INDEX)


def main():
    if not PINECONE_API_KEY:
        raise SystemExit("Missing PINECONE_API_KEY in .env")

    print("Loading documents...")
    docs = load_documents()
    print(f"Loaded {len(docs)} source files")
    by_type: dict[str, int] = {}
    for d in docs:
        by_type[d["doc_type"]] = by_type.get(d["doc_type"], 0) + 1
    print("doc_type counts:", by_type)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = ensure_index(pc)

    # Clear namespace so old poorly-tagged vectors do not keep biasing retrieval
    try:
        print(f"Clearing namespace '{NAMESPACE}' before re-ingest...")
        index.delete(delete_all=True, namespace=NAMESPACE)
        time.sleep(2)
    except Exception as e:
        print("namespace clear skipped/failed:", e)

    batch = []
    total = 0
    for doc in docs:
        if doc["doc_type"] == "tariff" or doc["source"].lower().endswith(".xls"):
            pieces = chunk_tariff_rows(doc["text"])
        else:
            pieces = chunk_text(doc["text"])

        for i, chunk in enumerate(pieces):
            meta = build_record_metadata(doc["source"], chunk)
            # Force tariff doc_type for xls rows
            if doc["doc_type"] == "tariff":
                meta["doc_type"] = "tariff"
                if meta.get("port") == "NONE":
                    meta["port"] = "MULTI"
            uid = hashlib.md5(f"{doc['source']}:{i}:{chunk[:100]}".encode()).hexdigest()
            batch.append(
                {
                    "_id": uid,
                    "chunk_text": chunk[:3500],
                    **meta,
                    "chunk": i,
                }
            )
            total += 1
            if len(batch) >= 90:
                index.upsert_records(namespace=NAMESPACE, records=batch)
                print(f"upserted {total} chunks...")
                batch = []

    if batch:
        index.upsert_records(namespace=NAMESPACE, records=batch)

    print(f"DONE. Upserted {total} chunks into '{PINECONE_INDEX}' / ns '{NAMESPACE}'")

    if DEEPSEEK_API_KEY:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        try:
            r = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": "Reply with OK only."}],
                max_tokens=5,
            )
            print("DeepSeek OK:", (r.choices[0].message.content or "").strip())
        except Exception as e:
            print("DeepSeek check failed:", e)


if __name__ == "__main__":
    main()
