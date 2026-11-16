import sys
from pathlib import Path

try:
    import win32com.client
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32"])
    import win32com.client

pst_candidates = [
    Path(r"D:\alpine\MV Star Challenger Email Trail\extracted.pst"),
    Path(r"D:\alpine\MV Star Challenger Email Trail\aqeel_makkani.pst"),
]

outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")
print("Outlook version:", outlook.Version)
print("Existing stores:")
for i in range(1, ns.Stores.Count + 1):
    s = ns.Stores.Item(i)
    try:
        print(f"  - {s.DisplayName} | {s.FilePath}")
    except Exception as e:
        print(f"  - (store {i}) err {e}")

out_dir = Path(r"D:\alpine\MV Star Challenger Email Trail\extracted_emails")
out_dir.mkdir(exist_ok=True)

for pst in pst_candidates:
    print("\nTrying AddStore:", pst)
    if not pst.exists():
        print("  missing")
        continue
    before = {ns.Stores.Item(i).DisplayName for i in range(1, ns.Stores.Count + 1)}
    try:
        ns.AddStore(str(pst))
    except Exception as e:
        print("  AddStore failed:", e)
        continue
    after = {ns.Stores.Item(i).DisplayName for i in range(1, ns.Stores.Count + 1)}
    print("  stores now:", after)
    new_names = after - before
    print("  new stores:", new_names or "(none detected by name)")

    # find store by filepath
    target = None
    for i in range(1, ns.Stores.Count + 1):
        s = ns.Stores.Item(i)
        try:
            fp = (s.FilePath or "").lower()
        except Exception:
            fp = ""
        if pst.name.lower() in fp or str(pst).lower() == fp:
            target = s
            break
    if target is None and new_names:
        for i in range(1, ns.Stores.Count + 1):
            s = ns.Stores.Item(i)
            if s.DisplayName in new_names:
                target = s
                break
    if target is None:
        print("  could not locate added store")
        continue

    root = target.GetRootFolder()
    print("  root:", root.Name, "folders:", root.Folders.Count)

    def walk(folder, depth=0):
        indent = "  " * (depth + 2)
        try:
            n = folder.Items.Count
        except Exception:
            n = "?"
        print(f"{indent}{folder.Name} items={n}")
        # export first few mail items
        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)
            count = items.Count
            for idx in range(1, min(count, 20) + 1):
                it = items.Item(idx)
                try:
                    subj = getattr(it, "Subject", "") or ""
                    sender = getattr(it, "SenderName", "") or ""
                    received = getattr(it, "ReceivedTime", "") or ""
                    print(f"{indent}  MAIL: {received} | {sender} | {subj[:120]}")
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in subj)[:80] or f"msg_{idx}"
                    path = out_dir / f"{safe}_{idx}.txt"
                    body = getattr(it, "Body", "") or ""
                    path.write_text(
                        f"Subject: {subj}\nFrom: {sender}\nReceived: {received}\n\n{body}",
                        encoding="utf-8",
                        errors="ignore",
                    )
                except Exception as e:
                    print(f"{indent}  item err:", e)
        except Exception as e:
            print(f"{indent} items err:", e)
        try:
            for j in range(1, folder.Folders.Count + 1):
                walk(folder.Folders.Item(j), depth + 1)
        except Exception as e:
            print(f"{indent} subfolders err:", e)

    walk(root)

print("\nDone. Exported to", out_dir)
