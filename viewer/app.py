"""Alpine docs localhost viewer — open emails, PDFs, Word, Excel in browser."""

from __future__ import annotations

import email
import html
import mimetypes
import os
import re
import zipfile
from email import policy
from pathlib import Path

from flask import Flask, Response, abort, redirect, render_template_string, request, send_file, url_for

ROOT = Path(__file__).resolve().parent.parent
SKIP_NAMES = {".git", "__pycache__", "viewer"}
SKIP_PREFIXES = ("_try_open",)

app = Flask(__name__)


def safe_path(rel: str) -> Path:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    target = (ROOT / rel).resolve()
    if not str(target).startswith(str(ROOT.resolve())):
        abort(400, "Invalid path")
    return target


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def list_entries(folder: Path) -> list[dict]:
    items = []
    try:
        children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return items
    for p in children:
        if p.name in SKIP_NAMES or p.name.startswith(SKIP_PREFIXES):
            continue
        if p.suffix.lower() in {".pyc"}:
            continue
        rel = p.relative_to(ROOT).as_posix()
        items.append(
            {
                "name": p.name,
                "rel": rel,
                "is_dir": p.is_dir(),
                "size": human_size(p.stat().st_size) if p.is_file() else "—",
                "ext": p.suffix.lower() if p.is_file() else "folder",
                "viewable": is_viewable(p),
            }
        )
    return items


def is_viewable(p: Path) -> bool:
    if p.is_dir():
        return True
    return p.suffix.lower() in {
        ".pdf",
        ".eml",
        ".msg",
        ".docx",
        ".doc",
        ".xls",
        ".xlsx",
        ".txt",
        ".csv",
        ".html",
        ".htm",
        ".zip",
        ".pst",
        ".tmp",
    }


LAYOUT = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title }} · Alpine Viewer</title>
  <style>
    :root {
      --bg: #0f1a24;
      --panel: #162533;
      --panel2: #1c3040;
      --line: #2a4558;
      --text: #e8eef3;
      --muted: #8aa0b2;
      --accent: #2f9e88;
      --accent2: #c4a35a;
      --danger: #c45c5c;
      --chip: #243848;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background:
        radial-gradient(1200px 500px at 10% -10%, #1a3a4a 0%, transparent 55%),
        radial-gradient(900px 400px at 100% 0%, #24301f 0%, transparent 50%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    header {
      display: flex; align-items: center; justify-content: space-between; gap: 1rem;
      padding: 1rem 1.5rem; border-bottom: 1px solid var(--line);
      background: rgba(15,26,36,.85); backdrop-filter: blur(8px);
      position: sticky; top: 0; z-index: 10;
    }
    .brand { font-weight: 700; letter-spacing: .04em; font-size: 1.05rem; }
    .brand span { color: var(--accent); }
    .crumb a { color: var(--muted); text-decoration: none; }
    .crumb a:hover { color: var(--accent); }
    .crumb .sep { color: var(--line); margin: 0 .35rem; }
    main { padding: 1.25rem 1.5rem 3rem; max-width: 1200px; margin: 0 auto; }
    .card {
      background: linear-gradient(180deg, var(--panel), var(--panel2));
      border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: .85rem 1rem; text-align: left; border-bottom: 1px solid var(--line); }
    th { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }
    tr:hover td { background: rgba(47,158,136,.06); }
    a.rowlink { color: var(--text); text-decoration: none; font-weight: 600; }
    a.rowlink:hover { color: var(--accent); }
    .chip {
      display: inline-block; font-size: .72rem; padding: .2rem .5rem;
      border-radius: 999px; background: var(--chip); color: var(--muted);
      text-transform: uppercase; letter-spacing: .04em;
    }
    .chip.folder { color: var(--accent2); }
    .chip.eml, .chip.msg { color: #7eb8ff; }
    .chip.pdf { color: #ff8f8f; }
    .chip.docx, .chip.doc { color: #7ec8ff; }
    .chip.xls, .chip.xlsx { color: #8fd68f; }
    .actions a {
      color: var(--accent); text-decoration: none; font-size: .85rem; margin-right: .75rem;
    }
    .actions a.dl { color: var(--muted); }
    .meta { color: var(--muted); font-size: .9rem; margin-bottom: 1rem; }
    .viewer {
      background: #0b141c; border: 1px solid var(--line); border-radius: 12px;
      padding: 1.25rem; white-space: pre-wrap; line-height: 1.55; overflow: auto;
    }
    .email-head {
      background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
      padding: 1rem 1.25rem; margin-bottom: 1rem;
    }
    .email-head div { margin: .25rem 0; }
    .email-head .k { color: var(--muted); display: inline-block; min-width: 5rem; }
    iframe.pdf {
      width: 100%; height: 80vh; border: 1px solid var(--line); border-radius: 12px; background: #111;
    }
    table.data { font-size: .9rem; }
    table.data th { background: #12202c; position: sticky; top: 0; }
    .warn {
      border: 1px solid #6a3a3a; background: #2a1717; color: #f0c2c2;
      padding: 1rem 1.25rem; border-radius: 12px; margin-bottom: 1rem;
    }
    .oknote {
      border: 1px solid #2f5a4a; background: #14241f; color: #b7e0d4;
      padding: 1rem 1.25rem; border-radius: 12px; margin-bottom: 1rem;
    }
    .toolbar { display: flex; gap: .75rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .btn {
      display: inline-block; padding: .55rem 1rem; border-radius: 8px;
      background: var(--accent); color: #06221c; text-decoration: none; font-weight: 700;
    }
    .btn.ghost { background: transparent; border: 1px solid var(--line); color: var(--text); }
  </style>
</head>
<body>
  <header>
    <div class="brand">ALPINE <span>Docs Viewer</span></div>
    <div class="crumb">{{ crumb|safe }}</div>
  </header>
  <main>
    {{ body|safe }}
  </main>
</body>
</html>
"""


def page(title: str, crumb: str, body: str) -> str:
    return render_template_string(LAYOUT, title=title, crumb=crumb, body=body)


def crumb_for(rel: str) -> str:
    parts = [p for p in rel.split("/") if p]
    bits = [f'<a href="{url_for("browse")}">alpine</a>']
    acc = []
    for part in parts:
        acc.append(part)
        bits.append('<span class="sep">/</span>')
        bits.append(f'<a href="{url_for("browse", path="/".join(acc))}">{html.escape(part)}</a>')
    return "".join(bits)


@app.get("/")
def home():
    return redirect(url_for("browse"))


@app.get("/browse/")
@app.get("/browse/<path:path>")
def browse(path: str = ""):
    folder = safe_path(path)
    if folder.is_file():
        return redirect(url_for("view_file", path=path))
    if not folder.exists() or not folder.is_dir():
        abort(404)

    rows = []
    for item in list_entries(folder):
        if item["is_dir"]:
            href = url_for("browse", path=item["rel"])
            open_link = f'<a class="rowlink" href="{href}">{html.escape(item["name"])}/</a>'
            action = f'<a href="{href}">Open</a>'
        else:
            href = url_for("view_file", path=item["rel"])
            dl = url_for("download", path=item["rel"])
            open_link = f'<a class="rowlink" href="{href}">{html.escape(item["name"])}</a>'
            action = f'<a href="{href}">View</a> <a class="dl" href="{dl}">Download</a>'
        rows.append(
            f"""
            <tr>
              <td><span class="chip {html.escape(item['ext'].lstrip('.'))}">{html.escape(item['ext'])}</span></td>
              <td>{open_link}</td>
              <td>{html.escape(item['size'])}</td>
              <td class="actions">{action}</td>
            </tr>
            """
        )

    body = f"""
      <p class="meta">Local folder: <code>{html.escape(str(folder))}</code> · {len(rows)} items</p>
      <div class="card">
        <table>
          <thead><tr><th>Type</th><th>Name</th><th>Size</th><th>Actions</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan="4">Empty folder</td></tr>'}</tbody>
        </table>
      </div>
    """
    return page("Browse", crumb_for(path), body)


def render_eml(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    fields = []
    for key in ("From", "To", "Cc", "Subject", "Date"):
        val = msg.get(key)
        if val:
            fields.append(
                f'<div><span class="k">{key}</span> {html.escape(str(val))}</div>'
            )
    texts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    texts.append(part.get_content())
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    texts.append(payload.decode(part.get_content_charset() or "utf-8", "ignore"))
            elif ctype == "text/html" and not texts:
                try:
                    raw = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    raw = payload.decode(part.get_content_charset() or "utf-8", "ignore")
                # keep simple text extract
                import re

                t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
                t = re.sub(r"(?s)<br\s*/?>", "\n", t)
                t = re.sub(r"(?s)</p>", "\n\n", t)
                t = re.sub(r"(?s)<[^>]+>", " ", t)
                texts.append(html.unescape(re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", t))).strip())
    else:
        try:
            texts.append(msg.get_content())
        except Exception:
            payload = msg.get_payload(decode=True) or b""
            texts.append(payload.decode("utf-8", "ignore"))

    body_text = "\n\n".join(t for t in texts if t).strip() or "(No plain text body found)"
    return f"""
      <div class="email-head">{''.join(fields)}</div>
      <div class="viewer">{html.escape(body_text)}</div>
    """


def render_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        parts.append("")
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    text = "\n".join(parts) or "(Empty document)"
    return f'<div class="viewer">{html.escape(text)}</div>'


def render_xls(path: Path) -> str:
    import xlrd

    book = xlrd.open_workbook(str(path))
    blocks = []
    for sheet in book.sheets():
        rows_html = []
        for r in range(min(sheet.nrows, 500)):
            cells = []
            for c in range(sheet.ncols):
                val = sheet.cell_value(r, c)
                cells.append(f"<td>{html.escape(str(val))}</td>")
            rows_html.append(f"<tr>{''.join(cells)}</tr>")
        blocks.append(
            f"<h3 style='margin:1rem 0 .5rem'>{html.escape(sheet.name)}</h3>"
            f"<div class='card' style='overflow:auto;max-height:70vh'>"
            f"<table class='data'><tbody>{''.join(rows_html)}</tbody></table></div>"
        )
    return "".join(blocks) or "<p>Empty workbook</p>"


def render_xlsx(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    blocks = []
    for sheet in wb.worksheets:
        rows_html = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= 500:
                break
            cells = "".join(f"<td>{html.escape('' if v is None else str(v))}</td>" for v in row)
            rows_html.append(f"<tr>{cells}</tr>")
        blocks.append(
            f"<h3 style='margin:1rem 0 .5rem'>{html.escape(sheet.title)}</h3>"
            f"<div class='card' style='overflow:auto;max-height:70vh'>"
            f"<table class='data'><tbody>{''.join(rows_html)}</tbody></table></div>"
        )
    return "".join(blocks) or "<p>Empty workbook</p>"


def render_zip(path: Path) -> str:
    rows = []
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            rows.append(
                f"<tr><td>{html.escape(info.filename)}</td>"
                f"<td>{human_size(info.file_size)}</td></tr>"
            )
    return (
        '<div class="oknote">ZIP listing only — download the archive to extract fully.</div>'
        f'<div class="card"><table><thead><tr><th>Path</th><th>Size</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_text(path: Path) -> str:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", "ignore")
    # plain view: decode leftover HTML entities from email extracts
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return f'<div class="viewer">{html.escape(text[:200000])}</div>'


@app.get("/view/<path:path>")
def view_file(path: str):
    target = safe_path(path)
    if not target.exists() or not target.is_file():
        abort(404)

    ext = target.suffix.lower()
    dl = url_for("download", path=path)
    toolbar = f"""
      <div class="toolbar">
        <a class="btn ghost" href="{url_for('browse', path=str(target.parent.relative_to(ROOT).as_posix()) if target.parent != ROOT else '')}">← Back</a>
        <a class="btn" href="{dl}">Download</a>
      </div>
      <p class="meta">{html.escape(target.name)} · {human_size(target.stat().st_size)}</p>
    """

    try:
        if ext == ".pdf":
            content = f'<iframe class="pdf" src="{url_for("raw_file", path=path)}"></iframe>'
        elif ext == ".eml":
            content = render_eml(target)
        elif ext == ".docx":
            content = render_docx(target)
        elif ext == ".xls":
            content = render_xls(target)
        elif ext == ".xlsx":
            content = render_xlsx(target)
        elif ext == ".zip":
            content = render_zip(target)
        elif ext in {".txt", ".csv", ".html", ".htm"}:
            content = render_text(target)
        elif ext == ".doc":
            content = (
                '<div class="warn">Old .doc format — browser text extract limited. '
                "Use Download and open in Word, or convert to .docx.</div>"
                f'<p><a class="btn" href="{dl}">Download .doc</a></p>'
            )
        elif ext in {".pst", ".tmp"} or target.name.endswith(".pst.tmp"):
            extracted = ROOT / "MV Star Challenger Email Trail" / "extracted_emails"
            extracted_count = (
                len(list(extracted.glob("*.txt"))) if extracted.is_dir() else 0
            )
            # Small/temp dumps are usually incomplete; large valid PSTs may be extracted already
            size_mb = target.stat().st_size / (1024 * 1024)
            if extracted_count > 0 and size_mb > 50:
                href = url_for(
                    "browse",
                    path="MV Star Challenger Email Trail/extracted_emails",
                )
                content = (
                    f'<div class="oknote"><strong>PST ready.</strong> '
                    f"{extracted_count} emails extracted from this Outlook file.</div>"
                    f'<p><a class="btn" href="{href}">Open extracted emails →</a></p>'
                    f'<p class="meta">File size: {size_mb:.1f} MB · binary PST (not text)</p>'
                )
            elif size_mb < 50 or target.name.endswith(".pst.tmp"):
                content = (
                    '<div class="warn"><strong>Cannot open this Outlook dump.</strong><br>'
                    "File looks incomplete/corrupt (.pst.tmp / small dump). "
                    "Use the full .pst export if available.</div>"
                )
            else:
                content = (
                    '<div class="warn">PST is binary — not shown as text. '
                    "Run extraction, then open the extracted_emails folder.</div>"
                    f'<p><a class="btn" href="{dl}">Download PST</a></p>'
                )
        else:
            content = (
                '<div class="warn">No in-browser preview for this type. Download to open.</div>'
                f'<p><a class="btn" href="{dl}">Download</a></p>'
            )
    except Exception as e:
        content = f'<div class="warn">Failed to render: {html.escape(str(e))}</div>'

    return page(target.name, crumb_for(path), toolbar + content)


@app.get("/raw/<path:path>")
def raw_file(path: str):
    target = safe_path(path)
    if not target.exists() or not target.is_file():
        abort(404)
    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return send_file(target, mimetype=mime, conditional=True)


@app.get("/download/<path:path>")
def download(path: str):
    target = safe_path(path)
    if not target.exists() or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=True, download_name=target.name)


if __name__ == "__main__":
    print(f"Alpine root: {ROOT}")
    print("Open http://127.0.0.1:5055")
    app.run(host="127.0.0.1", port=5055, debug=False)
