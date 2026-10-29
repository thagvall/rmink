# ruff: noqa: E501
"""Swimlane chains for the business diagrams: role × phase × step.

The layout follows the chain pictures of the Riksbyggen project
(docs/begreppskatalog/scripts/kedja_bas.py there):
- One lane per role, with the role in bold and the role's system under it.
- One column per phase, with a heading.
- Each step is a card in three rows: a numbered verb ("3 · tolkar"), a title
  band coloured by the system the step happens in, and up to three short lines.
- A verb starting with "!" is drawn red: the step happens outside rmink today
  (on paper, by e-mail, at the municipality) or is planned.
- "Färg = system" and a footnote go under the chain.

The chains in verksamhet.py are plain data and call ``chain``; a change of
style here reaches every picture.
"""

from __future__ import annotations

from drawio import FONT, Diagram, esc

FS = 16
HEADING = "#1F4E79"
X0, STEP, EW = 230, 284, 240  # first column, column step, card width
LANE_X, LANE_W = 20, 196
Y0 = 92
CARD_H = 26 + 30 + 74

# The whole series' palette; each chain picks its keys.
PALETTE = {
    "platta": ("#F2F2F2", "#404040", "reMarkable-platta"),
    "moln": ("#DEEAF6", "#2E75B6", "reMarkable Cloud"),
    "rmink": ("#E2EFDA", "#548235", "rmink (webb, /rounds, MCP)"),
    "claude": ("#FCE4D6", "#C55A11", "Claude (AI)"),
    "kb": ("#FFF2CC", "#BF8F00", "Kunskapsbas (BFS 2024, PBL, material)"),
    "kommun": ("#E4DFEC", "#7030A0", "Kommunens e-tjänst · byggnadsnämnd"),
    "dok": ("#EDEDED", "#7F7F7F", "Papper · e-post · utanför rmink"),
    "webb": ("#DAEEF3", "#31859C", "rmink.vercel.app (webbläsare, telefon)"),
}


def _bold(text: str) -> str:
    """'**Roll**\\nsystem' → HTML with the first part bold."""
    out = []
    for line in text.split("\n"):
        if line.startswith("**") and line.endswith("**"):
            out.append(f"<b>{esc(line[2:-2])}</b>")
        else:
            out.append(esc(line))
    return "<br>".join(out)


def _card(
    d: Diagram, frames: dict, lanes: dict, sid, lane, col, system, verb, title, lines, copy=False
):
    fill, stroke, _ = PALETTE[system]
    y_lane, h_lane = lanes[lane]
    x, y = X0 + col * STEP, y_lane + (h_lane - CARD_H) / 2
    red = verb.startswith("!")
    verb = verb.lstrip("!")
    dash = "dashed=1;" if copy else ""
    base = f"rounded=0;{dash}whiteSpace=wrap;html=1;strokeColor={stroke};strokeWidth=2;fontFamily={FONT};fontSize={FS};"
    d.raw(
        x,
        y,
        EW,
        26,
        esc(verb),
        base
        + f"fillColor=#FFFFFF;align=left;verticalAlign=middle;spacingLeft=8;fontStyle=2;fontColor={'#C00000' if red else '#595959'};",
        hint=sid + "_verb",
    )
    d.raw(
        x,
        y + 26,
        EW,
        30,
        esc(title),
        base + f"fillColor={fill};align=center;verticalAlign=middle;fontStyle=1;",
        hint=sid + "_title",
    )
    d.raw(
        x,
        y + 56,
        EW,
        74,
        "<br>".join(esc(t) for t in lines),
        base
        + "fillColor=#FFFFFF;align=left;verticalAlign=top;spacingLeft=8;spacingTop=2;fontColor=#262626;",
        hint=sid + "_body",
    )
    # an invisible frame round the card for the arrows to attach to
    frames[sid] = d.raw(
        x, y, EW, CARD_H, "", "rounded=0;fillColor=none;strokeColor=none;", hint=sid
    )


def chain(
    name: str,
    title: str,
    roles: list[tuple[str, str, int]],
    columns: list[str],
    steps: list[tuple],
    links: list[tuple],
    systems: list[str],
    note: str = "",
    subtitle: str = "",
) -> Diagram:
    """roles: [(id, "**Roll**\\nsystem", lane height)]
    steps: [(id, lane, column, system, verb, title, [up to 3 lines][, copy])]
    links: [(from, to, label, (exitX, exitY, entryX, entryY))]"""
    d = Diagram(name, title, subtitle, title_color=HEADING, title_size=26)
    width = X0 + len(columns) * STEP
    for i, c in enumerate(columns):
        d.text(
            X0 + i * STEP,
            Y0 - 34,
            EW,
            26,
            f"<b>{esc(c)}</b>",
            size=FS + 1,
            color=HEADING,
            align="center",
        )
    lanes, y = {}, Y0
    for n, (rid, text, h) in enumerate(roles):
        lanes[rid] = (y, h)
        d.raw(
            LANE_X,
            y,
            width - LANE_X,
            h,
            "",
            f"rounded=0;fillColor={'#F7F7F7' if n % 2 else '#FFFFFF'};strokeColor=#BFBFBF;",
            hint="lane_" + rid,
        )
        d.text(LANE_X + 8, y + 10, LANE_W - 12, h - 16, _bold(text), size=FS, color=HEADING)
        y += h
    frames: dict[str, str] = {}
    for s in steps:
        _card(d, frames, lanes, *s)
    for frm, to, text, (ex, ey, nx, ny) in links:
        d.edge(
            frames[frm],
            frames[to],
            text,
            color="#404040",
            exit=(ex, ey),
            entry=(nx, ny),
            extra="rounded=0;strokeWidth=2;fontSize=14;fontColor=#404040;",
        )
    # legend: colour = system
    y += 14
    d.text(LANE_X, y, 180, 26, "<b>Färg = system:</b>", size=FS)
    per_row = 3
    step_x = (width - 200) // per_row
    for i, key in enumerate(systems):
        fill, stroke, label_ = PALETTE[key]
        row, col = divmod(i, per_row)
        x = 200 + col * step_x
        d.raw(
            x,
            y + 3 + row * 30,
            26,
            20,
            "",
            f"rounded=0;fillColor={fill};strokeColor={stroke};strokeWidth=2;",
        )
        d.text(x + 34, y + row * 30, step_x - 40, 26, esc(label_), size=FS)
    y += -(-len(systems) // per_row) * 30 + 6
    if note:
        d.text(
            LANE_X,
            y,
            width - 40,
            28 * (note.count("\n") + 1),
            "<i>" + "<br>".join(esc(x) for x in note.split("\n")) + "</i>",
            size=FS - 1,
            color="#595959",
        )
    return d
