"""Extract emails from Star Challenger PST into readable text/HTML for the viewer."""

from __future__ import annotations

import html as html_lib
import re
import sys
from pathlib import Path

import pypff

PST = Path(r"C:\alpine_pst\star.pst")
OUT = Path(r"D:\alpine\MV Star Challenger Email Trail\extracted_emails")
OUT.mkdir(parents=True, exist_ok=True)

# clear old failed extracts
for old in OUT.glob("*.txt"):
    try:
        old.unlink()
    except OSError:
        pass


def safe_name(s: str, i: int) -> str:
    s = (s or f"message_{i}").strip()
    s = re.sub(r"[^\w\s\-@.]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()[:90]
    return s or f"message_{i}"


def body_of(msg) -> str:
    for getter in ("get_plain_text_body", "get_html_body", "get_rtf_body"):
        try:
            fn = getattr(msg, getter, None)
            if not fn:
                continue
            raw = fn()
            if not raw:
                continue
            if isinstance(raw, bytes):
                text = raw.decode("utf-8", "ignore")
            else:
                text = str(raw)
            if getter == "get_html_body":
                text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
                text = re.sub(r"(?s)<br\s*/?>", "\n", text)
                text = re.sub(r"(?s)</p>", "\n\n", text)
                text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = html_lib.unescape(text).replace("\xa0", " ")
            text = re.sub(r"[ \t]+\n", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if text.strip():
                return text.strip()
        except Exception:
            continue
    return "(no body)"


def walk(folder, depth=0, stats=None):
    if stats is None:
        stats = {"folders": 0, "msgs": 0, "saved": 0, "errors": 0}
    stats["folders"] += 1
    name = folder.get_name() or "(root)"
    n = folder.get_number_of_sub_messages()
    print(f"{'  ' * depth}FOLDER: {name}  messages={n}")
    for i in range(n):
        try:
            msg = folder.get_sub_message(i)
            subj = msg.get_subject() or ""
            sender = ""
            try:
                sender = msg.get_sender_name() or ""
            except Exception:
                pass
            delivered = ""
            try:
                delivered = str(msg.get_delivery_time() or "")
            except Exception:
                pass
            body = body_of(msg)
            stats["msgs"] += 1
            fname = f"{stats['saved']:04d}_{safe_name(subj, i)}.txt"
            path = OUT / fname
            path.write_text(
                f"Subject: {subj}\nFrom: {sender}\nDate: {delivered}\nFolder: {name}\n\n{body}",
                encoding="utf-8",
                errors="ignore",
            )
            stats["saved"] += 1
            if stats["saved"] <= 15 or stats["saved"] % 50 == 0:
                print(f"{'  ' * depth}  [{stats['saved']}] {sender[:40]} | {subj[:80]}")
        except Exception as e:
            stats["errors"] += 1
            print(f"{'  ' * depth}  ERR msg {i}: {e}")
    for i in range(folder.get_number_of_sub_folders()):
        try:
            walk(folder.get_sub_folder(i), depth + 1, stats)
        except Exception as e:
            print(f"{'  ' * depth} subfolder err: {e}")
    return stats


def main() -> int:
    if not PST.exists():
        print("Missing", PST)
        return 1
    print("Opening", PST, "size", PST.stat().st_size)
    f = pypff.file()
    f.open(str(PST))
    root = f.get_root_folder()
    stats = walk(root)
    f.close()
    print("DONE", stats)
    print("OUT", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
