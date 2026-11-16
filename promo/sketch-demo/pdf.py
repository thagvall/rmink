"""Turn the sketch-to-drawing demo page into a clickable PDF, one page per step.

    python3 promo/sketch-demo/pdf.py      # writes docs/skiss-till-ritning.pdf (needs Google Chrome)

Chrome loads skiss-till-ritning.html with a script added at the end. The
script steps every demo to its end state (no animation), copies the tablets,
the actors, the text and the detail of each step, and lays them out as print
pages. The strokes stay vector, so the PDF zooms. Everything links: the
contents, the step chips on every page, the scenario cards and previous/next.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "docs" / "skiss-till-ritning.pdf"
sys.path.insert(0, str(ROOT / "docs" / "diagrams"))

from pdf import chrome, wordmark  # noqa: E402  (docs/diagrams/pdf.py)

CSS = r"""
@page { size: A4 landscape; margin: 0; }
html { font-size: 11.5px; }
:root { --bg: #ffffff; }
body { background: #fff !important; padding: 0 !important; margin: 0; font-size: 11.5px;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
*, *::before, *::after { transition: none !important; animation: none !important; }
.wrap { display: block !important; max-width: none !important; }
a { color: var(--accent); text-decoration: none; }
.pg { position: relative; width: 297mm; height: 210mm; overflow: hidden; break-after: page;
  padding: 18mm 10mm 12mm; display: flex; flex-direction: column; }
.pg:last-child { break-after: auto; }
.hdr { position: absolute; top: 0; left: 0; right: 0; height: 12mm; padding: 0 10mm; display: flex;
  align-items: center; gap: 10px; border-bottom: 1px solid var(--rule); }
.hdr .wm { height: 7.5mm; width: auto; }
.hdr .crumb { font-size: 9pt; color: var(--muted); }
.hdr .crumb b { color: var(--ink); }
.hdr .home { margin-left: auto; font-size: 9pt; border: 1px solid var(--rule); border-radius: 99px; padding: 2px 10px; }
.ftr { position: absolute; bottom: 0; left: 0; right: 0; height: 9mm; padding: 0 10mm; display: flex;
  align-items: center; justify-content: space-between; font-size: 8.5pt; color: var(--muted); }
.ftr .nav a { margin-left: 14px; }

/* cover */
.cover { justify-content: center; align-items: flex-start; padding: 0 28mm; }
.cover .wm { width: 70mm; height: auto; margin-bottom: 10mm; }
.cover h1 { font-size: 34pt; max-width: 210mm; }
.cover .lede { font-size: 13pt; color: var(--muted); max-width: 190mm; margin-top: 6mm; }
.cover .demos { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12mm; }
.cover .demos a { border: 1px solid var(--rule); border-radius: 99px; padding: 5px 14px; font-weight: 600; color: var(--ink); }
.cover .demos a b { color: var(--accent); font-family: var(--mono); font-weight: 500; margin-right: 6px; }
.cover .meta { position: absolute; bottom: 14mm; left: 28mm; right: 28mm; font-size: 9pt; color: var(--muted); }

/* contents */
.tochead { display: flex; align-items: flex-end; gap: 14px; border-bottom: 2px solid var(--ink); padding-bottom: 3mm; margin-bottom: 5mm; }
.tochead .wm { height: 17mm; width: auto; }
.tochead h2 { font-size: 22pt; font-weight: 400; margin-bottom: 1.5mm; }
.toc { columns: 3; column-gap: 9mm; }
.toc .blk { break-inside: avoid; margin-bottom: 5mm; }
.toc .bt { display: block; font-weight: 700; font-size: 11pt; color: var(--ink); margin-bottom: 1.5mm; }
.toc .bt small { display: block; font-family: var(--mono); font-weight: 400; font-size: 7.5pt; color: var(--muted); letter-spacing: .06em; text-transform: uppercase; }
.toc .r { display: flex; gap: 6px; align-items: baseline; font-size: 9.5pt; padding: .9mm 0; color: var(--ink); }
.toc .r .n { font-family: var(--mono); color: var(--accent); width: 5mm; }
.toc .r .d { flex: 1; border-bottom: 1px dotted var(--rule); transform: translateY(-3px); }
.toc .r .p { color: var(--muted); font-variant-numeric: tabular-nums; }
.tocnote { margin: auto 0 3mm; font-size: 9pt; color: var(--muted); border-top: 1px solid var(--rule); padding-top: 3mm; }

/* demo opener */
.opener { display: grid; grid-template-columns: minmax(0, 1fr) 110mm; gap: 12mm; align-items: center; height: 100%; }
.opener .scen-head { max-width: none; gap: 3mm; }
.opener h2 { font-size: 26pt; }
.opener .scen-head p { font-size: 11pt; }
.opener .concept { font-size: 10pt; }
.opener .list { display: grid; gap: 1.5mm; margin-top: 4mm; }
.opener .list a { display: flex; gap: 8px; align-items: baseline; color: var(--ink); font-size: 10.5pt; }
.opener .list a b { font-family: var(--mono); font-weight: 500; color: var(--accent); width: 6mm; }
.opener .thumb { display: grid; justify-items: center; gap: 2mm; }
.opener .thumb .cap { font-family: var(--mono); font-size: 8pt; color: var(--muted); }
.opener .thumb { min-width: 0; overflow: hidden; }
.opener .thumb .dev > .tablet { width: 92mm; }
.opener .thumb .duo { gap: 3mm; }
.opener .thumb .duo .tablet, .opener .thumb .duo .viewer { max-width: 53mm; padding: 6px 5px 9px; border-radius: 8px; }
.opener .thumb .duo .phone { max-width: 42mm; padding: 6px 5px 8px; border-radius: 14px; }

/* step page */
.step { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 9mm; flex: 1; min-height: 0; }
.dev { display: flex; align-items: center; justify-content: center; min-height: 0; }
.dev .tablet { width: 128mm; max-width: 100%; padding: 14px 12px 20px; border-radius: 16px; box-shadow: none; }
.dev .duo { width: 100%; gap: 5mm; align-items: center; }
.step.two { grid-template-columns: 186mm minmax(0, 1fr); gap: 7mm; }
.dev .duo .tablet { width: 100%; max-width: 90mm; padding: 9px 7px 13px; border-radius: 11px; }
.dev .duo .viewer { max-width: 90mm; box-shadow: none; }
.dev .duo .phone { max-width: 70mm; box-shadow: none; padding: 9px 7px 12px; border-radius: 22px; }
.dev .phone-duo { grid-template-columns: minmax(0, .8fr) minmax(0, 1fr); }
.dev .duo-label { font-size: 8pt; margin-top: 2mm; }
.side { display: flex; flex-direction: column; gap: 4mm; min-height: 0; }
.side .copy { min-height: 0 !important; gap: 2mm; }
.side h2 { font-size: 17pt; }
.side .copy p { font-size: 10.5pt; line-height: 1.45; }
.side .detail { gap: 1.6mm; }
.side .row { padding: 4px 8px; font-size: 9.2pt; }
.side .stat strong { font-size: 20pt; }
.side .cmp table { font-size: 9pt; }
.side .cmp th, .side .cmp td { padding: 4px 8px; }
.side .actor { padding: 5px 4px; font-size: 8.5pt; }
.chips { margin-top: auto; display: flex; flex-wrap: wrap; gap: 4px; }
.chips a.chip { color: var(--muted); }
.chips a.chip[aria-current] { color: var(--ink); }

/* scenarios and facts */
.pg .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4mm; }
.pg .card { padding: 4mm; gap: 2mm; }
.pg .card p { font-size: 9pt; }
.pg .card h3 { font-size: 10.5pt; }
.pg .card svg { height: 62px; }
.pg .facts { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9mm; margin-top: 6mm; }
.pg .facts ul { font-size: 10pt; }
.pg footer { margin-top: auto; font-size: 9pt; }
.sechead { display: grid; gap: 2mm; margin-bottom: 5mm; max-width: 220mm; }
.sechead h2 { font-size: 20pt; }
.sechead p { color: var(--muted); font-size: 10.5pt; }
"""

# Runs in the demo page after its own script: step every demo, copy what each
# step shows and replace the page with print pages.
JS = r"""
(() => {
  const WM = __WM__;
  const NAMES = { flode: "Skiss till revision 2", varianter: "Varianter A och B", nedslag: "Nedslag i en detalj",
                  pappersskiss: "Pappersskiss via mobilen", export: "Export och delning" };
  const header = document.querySelector("header");
  const strip = node => { node.querySelectorAll('[opacity="0"]').forEach(n => n.remove()); return node; };
  const demos = players.map((p, i) => {
    const sec = p.root, id = sec.id;
    const head = sec.querySelector(".scen-head");
    const steps = p.steps.map((s, k) => {
      p.go(k, false);
      const dev = strip((sec.querySelector(".duo") || sec.querySelector(".tablet")).cloneNode(true));
      return { title: s.title, chip: s.chip || s.title, dev: dev.outerHTML,
               pipe: sec.querySelector(".pipeline").outerHTML,
               text: s.text, detail: sec.querySelector('[data-role="detail"]').innerHTML };
    });
    return { id, n: i + 1, name: NAMES[id] || id, head: head ? head.innerHTML : null, steps };
  });
  const scen = document.getElementById("scenarier");
  const facts = document.querySelector(".facts").outerHTML;
  const foot = document.querySelector("footer").outerHTML;

  // Page numbers: cover, contents, then per demo an opener and its steps, then scenarios and facts.
  let n = 3;
  demos.forEach(d => { d.page = n++; d.steps.forEach(s => (s.page = n++)); });
  const scenPage = n++, factsPage = n++, total = n - 1;
  const flat = demos.flatMap(d => d.steps.map((s, k) => ({ a: `${d.id}-${k + 1}` })));
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const hdr = crumb => `<div class="hdr">${WM}<span class="crumb">${crumb}</span><a class="home" href="#innehall">☰ Innehåll</a></div>`;
  const ftr = (p, nav = "") => `<div class="ftr"><span>rmink · skiss till ritning</span><span class="nav">${nav}</span><span>${p} / ${total}</span></div>`;
  const chips = (d, cur) => `<nav class="chips">${d.steps.map((s, k) =>
    `<a class="chip" href="#${d.id}-${k + 1}"${k === cur ? ' aria-current="step"' : ""}><b>${k + 1}</b>${esc(s.chip)}</a>`).join("")}</nav>`;
  const scenLink = href => { const d = demos.find(x => "#" + x.id === href); return d ? `#${d.id}` : "#scenarier"; };

  const pages = [];
  pages.push(`<section class="pg cover">${WM}
    <h1>${header.querySelector("h1").innerHTML}</h1>
    <p class="lede">${header.querySelector(".lede").innerHTML}</p>
    <div class="demos">${demos.map(d => `<a href="#${d.id}"><b>${d.n}</b>${d.name}</a>`).join("")}<a href="#scenarier"><b>+</b>Alla scenarier</a></div>
    <div class="meta">Interaktiv PDF ur demosidan · <a href="https://rmink.vercel.app/sketch">rmink.vercel.app/sketch</a> · <a href="https://github.com/thagvall/rmink">github.com/thagvall/rmink</a></div>
  </section>`);

  pages.push(`<section class="pg" id="innehall">
    <div class="tochead">${WM}<h2>Innehåll</h2></div>
    <div class="toc">${demos.map(d => `<div class="blk"><a class="bt" href="#${d.id}"><small>Demo ${d.n}</small>${d.name}</a>
      ${d.steps.map((s, k) => `<a class="r" href="#${d.id}-${k + 1}"><span class="n">${k + 1}</span>${esc(s.title)}<span class="d"></span><span class="p">${s.page}</span></a>`).join("")}</div>`).join("")}
      <div class="blk"><a class="bt" href="#scenarier"><small>Översikt</small>Scenarier och fakta</a>
        <a class="r" href="#scenarier"><span class="n">8</span>Åtta sätt att använda det<span class="d"></span><span class="p">${scenPage}</span></a>
        <a class="r" href="#fakta"><span class="n">·</span>Färg, roller och att verifiera<span class="d"></span><span class="p">${factsPage}</span></a></div>
    </div>
    <p class="tocnote">Allt är klickbart: innehållet, stegknapparna längst ner på varje stegsida, scenariokorten, ☰ Innehåll och Föregående/Nästa. Bilderna är riktiga pennstreck från rmink i vektorform, så det går att zooma in.</p>
    ${ftr(2)}
  </section>`);

  demos.forEach(d => {
    const last = d.steps[d.steps.length - 1];
    const head = d.head || `<span class="eyebrow">Scenario 1, 2, 3 och 8 · fas 1</span><h2>${d.name}</h2><p>${header.querySelector(".lede").innerHTML}</p>`;
    pages.push(`<section class="pg" id="${d.id}">${hdr(`<b>Demo ${d.n}</b> · ${d.name}`)}
      <div class="opener"><div><div class="scen-head">${head}</div>
        <div class="list">${d.steps.map((s, k) => `<a href="#${d.id}-${k + 1}"><b>${k + 1}</b>${esc(s.title)}</a>`).join("")}</div></div>
        <a class="thumb" href="#${d.id}-${d.steps.length}"><div class="dev">${last.dev}</div><span class="cap">Slutläget · steg ${d.steps.length}</span></a></div>
      ${ftr(d.page, `<a href="#${d.id}-1">Börja →</a>`)}</section>`);
    d.steps.forEach((s, k) => {
      const a = `${d.id}-${k + 1}`, i = flat.findIndex(f => f.a === a);
      const nav = (i > 0 ? `<a href="#${flat[i - 1].a}">← Föregående</a>` : "") + (i < flat.length - 1 ? `<a href="#${flat[i + 1].a}">Nästa →</a>` : `<a href="#scenarier">Scenarier →</a>`);
      pages.push(`<section class="pg" id="${a}">${hdr(`<b>Demo ${d.n}</b> · ${d.name}`)}
        <div class="step${s.dev.includes('class="duo') ? " two" : ""}"><div class="dev">${s.dev}</div>
          <div class="side panel">${s.pipe}
            <div class="copy"><span class="stepnum">Steg ${k + 1} av ${d.steps.length}</span><h2>${esc(s.title)}</h2><p>${esc(s.text)}</p></div>
            <div class="detail">${s.detail}</div>
            ${chips(d, k)}</div></div>
        ${ftr(s.page, nav)}</section>`);
    });
  });

  const head = scen.querySelector(".scen-head");
  const cards = scen.querySelector("#scenarios").cloneNode(true);
  cards.querySelectorAll("a[href^='#']").forEach(x => x.setAttribute("href", scenLink(x.getAttribute("href"))));
  pages.push(`<section class="pg" id="scenarier">${hdr("<b>Scenarier</b>")}
    <div class="sechead">${head.innerHTML}</div><div class="grid">${cards.innerHTML}</div>
    ${ftr(scenPage, `<a href="#fakta">Nästa →</a>`)}</section>`);
  pages.push(`<section class="pg" id="fakta">${hdr("<b>Fakta</b>")}
    <div class="sechead"><span class="eyebrow">Bra att veta</span><h2>Färg, roller och vad som ska verifieras</h2></div>
    ${facts}${foot}${ftr(factsPage, `<a href="#scenarier">← Föregående</a>`)}</section>`);

  document.querySelector(".wrap").innerHTML = pages.join("");
  document.body.dataset.ready = "1";
})();
"""


def main() -> None:
    src = (HERE / "skiss-till-ritning.html").read_text()
    # The demo's own stylesheet and script come first; the print rules and the paging script after.
    page = src + f"<style>{CSS}</style><script>{JS.replace('__WM__', json.dumps(wordmark()))}</script>"
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "demo.html"
        html.write_text(page)
        subprocess.run(
            [chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
             "--generate-pdf-document-outline", "--virtual-time-budget=20000",
             "--run-all-compositor-stages-before-draw", f"--print-to-pdf={OUT}", html.as_uri()],
            check=True, capture_output=True,
        )
    pages = re.findall(rb"/Type\s*/Page[^s]", OUT.read_bytes())
    print(f"{OUT.relative_to(ROOT)}: {len(pages)} sidor")


if __name__ == "__main__":
    main()
