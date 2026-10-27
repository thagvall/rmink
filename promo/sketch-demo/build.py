import sys
from pathlib import Path

sp = Path(sys.argv[1])
s = (sp / "template.html").read_text()
dead = """const both = (L, k, opacity) => { this_.set(L[k].same.cur, opacity, "show"); this_.set(L[k].new.cur, opacity, "show"); };
let this_ = null;
"""
if dead in s:
    s = s.replace(dead, "")
    (sp / "template.html").write_text(s)
out = (
    s.replace("__DATA5__", (sp / "data5.json").read_text())
    .replace("__DATA4__", (sp / "data4.json").read_text())
    .replace("__DATA3__", (sp / "data3.json").read_text())
    .replace("__DATA2__", (sp / "data2.json").read_text())
    .replace("__DATA__", (sp / "data.json").read_text())
)
(sp / "skiss-till-ritning.html").write_text(out)
head = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font:14px system-ui}</style></head><body>'
(sp / "preview.html").write_text(head + out + "</body></html>")
