"""Generate the "How it works" infographic as animated SVG (light + dark).

Usage: python3 docs/assets/src/architecture.py <lucide-static icons dir>
  e.g. npm i --no-save lucide-static@0.460.0
       python3 docs/assets/src/architecture.py node_modules/lucide-static/icons
Writes docs/assets/architecture-light.svg and docs/assets/architecture-dark.svg.
Icons: Lucide (ISC licence). Animation is slow and stops under prefers-reduced-motion.
"""
import re
import sys
from pathlib import Path

ICONS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("node_modules/lucide-static/icons")
OUT = Path(__file__).resolve().parent.parent
W, H = 1280, 868
LANES = [108, 288, 468, 648]          # lane tops; each lane is 160 tall
NODE_W, NODE_H, STEP = 150, 78, 177.5
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

THEMES = {
    "light": dict(
        bg="#F6F4FF", lane="#FFFFFF", lane_line="#E9E4F7", node="#FBFAFF", node_line="#E4DFF5",
        ink="#16131F", muted="#5B5670", arrow="#A49DBA", pill="#EFE8FF", pill_ink="#6D28D9",
        card="#16131F", card_ink="#FFFFFF", card_muted="#C9C4DA", card_line="#2E2940", lime="#C8F031",
        gate="#FFF4E8", gate_ink="#9A3412",
        tints=dict(scout=("#E5EDFF", "#1D4ED8"), mama=("#EFE8FF", "#6D28D9"), res=("#DDF5F1", "#0F766E"),
                   vam=("#FFE6F1", "#BE185D"), wri=("#FFEDE0", "#C2410C"), alo=("#E2F6E8", "#15803D"),
                   you=("#C8F031", "#16131F"))),
    "dark": dict(
        bg="#0F0D16", lane="#17141F", lane_line="#2A2538", node="#1D1928", node_line="#342E46",
        ink="#F4F2FA", muted="#A9A3BE", arrow="#6E6787", pill="#2A1B4D", pill_ink="#C4B5FD",
        card="#1D1928", card_ink="#F4F2FA", card_muted="#A9A3BE", card_line="#342E46", lime="#C8F031",
        gate="#2B1D14", gate_ink="#FDBA74",
        tints=dict(scout=("#1B2A52", "#93B4FF"), mama=("#2A1B4D", "#C4B5FD"), res=("#12332E", "#5EEAD4"),
                   vam=("#3D1730", "#F9A8D4"), wri=("#3B2215", "#FDBA74"), alo=("#143322", "#86EFAC"),
                   you=("#C8F031", "#16131F"))),
}

# (lane, slot, icon, title, subtitle, tint)
NODES = [
    (0, 0, "radar", "Scout", "news · tenders", "scout"),
    (0, 1, "link-2", "Resolve", "match ≥ 0.90", "scout"),
    (0, 2, "gauge", "Score", "tiers A · B · C", "mama"),
    (0, 3, "bot", "VAM", "risk · next step", "vam"),
    (0, 4, "shuffle", "Allocate", "fair proposal", "alo"),
    (2, 4, "sun", "/mama-day", "one command", "mama"),
    (2, 3, "search", "Research", "cited facts", "res"),
    (2, 2, "lightbulb", "Recommend", "product fit", "res"),
    (2, 1, "pen-line", "Draft", "in your tone", "wri"),
    (2, 0, "mail-check", "Review", "ready to send", "wri"),
    (3, 0, "send", "Approve", "then it sends", "you"),
    (3, 1, "inbox", "Replies", "triage replies", "mama"),
    (3, 2, "handshake", "Handover", "notes · CRM", "alo"),
    (3, 3, "trending-up", "Weekly", "calibrate · PR", "mama"),
]
LANE_LABELS = [("moon", "02:00 · Overnight, on the runner"), ("user-check", "08:30 · Manager"),
               ("sun", "08:45 · Each rep"), ("send", "09:00–11:30 · Send window · /mama-send")]
CYCLE = 15  # seconds for the spotlight to walk the whole loop


def icon(name, x, y, size, color, sw=2):
    raw = (ICONS / f"{name}.svg").read_text()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.S).group(1)
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.S).strip()
    s = size / 24
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.4f})" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{inner}</g>')


def node_xy(lane, slot):
    return 70 + slot * STEP, LANES[lane] + 56


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(name, t):
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-labelledby="t d" font-family="{FONT}">')
    a('<title id="t">How Sales Mama works</title>')
    a('<desc id="d">Overnight, scouts find signals, resolve.py links them to accounts, score.py tiers them, VAMs set '
      'next steps and allocate.py proposes a split. At 08:30 the manager approves. At 08:45 each rep runs /mama-day: '
      'research, recommend, draft. In the send window the rep reviews and approves the batch and Sales Mama sends it; replies, '
      'handover and the weekly review feed back into tomorrow\'s scores.</desc>')
    a(f'''<style>
  .flow {{ stroke-dasharray: 3 7; animation: flow 2.8s linear infinite; }}
  .loop {{ stroke-dasharray: 2 8; animation: flow 4s linear infinite; }}
  .glow {{ opacity: 0; animation: glow {CYCLE}s ease-in-out infinite; }}
  .pulse {{ animation: pulse 2.4s ease-in-out infinite; transform-origin: center; transform-box: fill-box; }}
  @keyframes flow {{ to {{ stroke-dashoffset: -40; }} }}
  @keyframes glow {{ 0% {{ opacity: 0; }} 2% {{ opacity: 1; }} 9% {{ opacity: 1; }} 13% {{ opacity: 0; }} 100% {{ opacity: 0; }} }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: .35; transform: scale(.7); }} }}
  @media (prefers-reduced-motion: reduce) {{ .flow, .loop, .glow, .pulse {{ animation: none; }} }}
</style>''')
    a(f'<defs><marker id="ah-{name}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" '
      f'orient="auto-start-reverse"><path d="M1.5 1.5L8.5 5L1.5 8.5" fill="none" stroke="{t["arrow"]}" '
      f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>')
    a(f'<rect width="{W}" height="{H}" rx="28" fill="{t["bg"]}"/>')

    # header
    a(f'<text x="40" y="52" font-size="26" font-weight="800" fill="{t["ink"]}" letter-spacing="-0.5">How Sales Mama works</text>')
    a(f'<text x="40" y="78" font-size="14.5" fill="{t["muted"]}">One loop a day. Agents prepare, people decide.</text>')

    # lanes
    for i, top in enumerate(LANES):
        a(f'<rect x="40" y="{top}" width="920" height="160" rx="24" fill="{t["lane"]}" stroke="{t["lane_line"]}"/>')
        ic, label = LANE_LABELS[i]
        pw = 46 + len(label) * 7.1
        lx = 240 if i == 3 else 58          # keep the send-window label clear of the incoming arrow
        a(f'<rect x="{lx}" y="{top + 16}" width="{pw:.0f}" height="28" rx="14" fill="{t["pill"]}"/>')
        a(icon(ic, lx + 10, top + 22, 16, t["pill_ink"]))
        a(f'<text x="{lx + 34}" y="{top + 35}" font-size="12.5" font-weight="700" fill="{t["pill_ink"]}">{esc(label)}</text>')
        if i == 0:
            a(f'<circle class="pulse" cx="{58 + pw + 14:.0f}" cy="{top + 30}" r="5" fill="{t["lime"]}"/>')

    # human gate (lane 2, left)
    gy = LANES[1] + 56
    a(f'<rect x="70" y="{gy}" width="500" height="{NODE_H}" rx="18" fill="{t["gate"]}"/>')
    a(icon("lock", 88, gy + 27, 24, t["gate_ink"]))
    a(f'<text x="126" y="{gy + 31}" font-size="14" font-weight="700" fill="{t["gate_ink"]}">Human gate</text>')
    a(f'<text x="126" y="{gy + 51}" font-size="12.5" fill="{t["gate_ink"]}">Nothing is assigned until the manager approves.</text>')
    a(f'<text x="126" y="{gy + 67}" font-size="12.5" fill="{t["gate_ink"]}">Unsure company matches wait in the review queue.</text>')

    # connectors (drawn under nodes)
    def line(d, cls="flow"):
        a(f'<path class="{cls}" d="{d}" fill="none" stroke="{t["arrow"]}" stroke-width="2" '
          f'stroke-linecap="round" marker-end="url(#ah-{name})"/>')

    cy = [LANES[i] + 56 + NODE_H / 2 for i in range(4)]
    for s in range(4):                      # lane 1 left → right
        x0, _ = node_xy(0, s)
        line(f"M{x0 + NODE_W + 5:.1f} {cy[0]} H{x0 + STEP - 6:.1f}")
    line(f"M855 {LANES[0] + 56 + NODE_H + 4} V{LANES[1] + 52}")         # allocate → manager
    line(f"M855 {LANES[1] + 56 + NODE_H + 4} V{LANES[2] + 52}")         # manager → /mama-day
    for s in range(4, 0, -1):               # lane 3 right → left
        x0, _ = node_xy(2, s)
        line(f"M{x0 - 5:.1f} {cy[2]} H{x0 - STEP + NODE_W + 6:.1f}")
    line(f"M145 {LANES[2] + 56 + NODE_H + 4} V{LANES[3] + 52}")         # mailbox → press send
    for s in range(3):                      # lane 4 left → right
        x0, _ = node_xy(3, s)
        line(f"M{x0 + NODE_W + 5:.1f} {cy[3]} H{x0 + STEP - 6:.1f}")
    wx, _ = node_xy(3, 3)                   # weekly → back to score (the learning loop)
    sx, _ = node_xy(0, 2)
    line(f"M{wx + NODE_W + 5:.1f} {cy[3]} H975 V96 H{sx + NODE_W / 2:.1f} V{LANES[0] + 52}", cls="loop")
    a(f'<text x="967" y="90" text-anchor="end" font-size="12" font-weight="600" fill="{t["muted"]}">'
      f'calibrates tomorrow\'s scores</text>')

    # manager node (lane 2, right)
    mx, my, mw = 600, LANES[1] + 56, 330
    bg, fg = t["tints"]["mama"]
    a(f'<rect class="glow" style="animation-delay:{5 * CYCLE / 15:.2f}s" x="{mx - 5}" y="{my - 5}" width="{mw + 10}" '
      f'height="{NODE_H + 10}" rx="22" fill="none" stroke="{fg}" stroke-width="2.5"/>')
    a(f'<rect x="{mx}" y="{my}" width="{mw}" height="{NODE_H}" rx="18" fill="{t["node"]}" stroke="{t["node_line"]}"/>')
    a(f'<rect x="{mx + 14}" y="{my + 19}" width="40" height="40" rx="12" fill="{bg}"/>')
    a(icon("user-check", mx + 24, my + 29, 20, fg))
    a(f'<text x="{mx + 66}" y="{my + 35}" font-size="14.5" font-weight="700" font-family="{MONO}" fill="{t["ink"]}">/mama-manager</text>')
    a(f'<text x="{mx + 66}" y="{my + 55}" font-size="12.5" fill="{t["muted"]}">approve allocation · clear review queue</text>')

    # step nodes, in loop order for the spotlight
    order = {n: k for k, n in enumerate(NODES)}
    for n in NODES:
        lane, slot, ic, title, sub, tint = n
        k = order[n] + (1 if order[n] >= 5 else 0)        # slot 5 in the walk is the manager
        x, y = node_xy(lane, slot)
        bg, fg = t["tints"][tint]
        a(f'<rect class="glow" style="animation-delay:{k * CYCLE / 15:.2f}s" x="{x - 5:.1f}" y="{y - 5}" '
          f'width="{NODE_W + 10}" height="{NODE_H + 10}" rx="22" fill="none" stroke="{fg if tint != "you" else t["lime"]}" stroke-width="2.5"/>')
        a(f'<rect x="{x:.1f}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="18" fill="{t["node"]}" stroke="{t["node_line"]}"/>')
        a(f'<rect x="{x + 12:.1f}" y="{y + 19}" width="40" height="40" rx="12" fill="{bg}"/>')
        a(icon(ic, x + 22, y + 29, 20, fg))
        mono = title.startswith("/")
        a(f'<text x="{x + 62:.1f}" y="{y + 35}" font-size="{13.5 if mono or len(title) > 8 else 14.5}" font-weight="700" '
          f'{"font-family=" + chr(34) + MONO + chr(34) + " " if mono else ""}fill="{t["ink"]}">{esc(title)}</text>')
        a(f'<text x="{x + 62:.1f}" y="{y + 55}" font-size="11.5" fill="{t["muted"]}">{esc(sub)}</text>')

    # right panel: the repo is the system
    px, pw = 990, 250
    a(f'<rect x="{px}" y="{LANES[0]}" width="{pw}" height="412" rx="24" fill="{t["card"]}" stroke="{t["card_line"]}"/>')
    a(icon("git-branch", px + 22, LANES[0] + 22, 20, t["lime"]))
    a(f'<text x="{px + 52}" y="{LANES[0] + 38}" font-size="15" font-weight="800" fill="{t["card_ink"]}">The repo is the system</text>')
    rows = [("book-open", "knowledge/", "truth · manager only"), ("archive", "raw/", "sources · never edited"),
            ("notebook-pen", "wiki/", "memory · agents write"), ("scroll-text", "log/", "append-only activity")]
    for i, (ic, path, what) in enumerate(rows):
        ry = LANES[0] + 68 + i * 74
        a(f'<rect x="{px + 18}" y="{ry}" width="{pw - 36}" height="62" rx="16" fill="none" stroke="{t["card_line"]}"/>')
        a(icon(ic, px + 32, ry + 19, 22, t["lime"]))
        a(f'<text x="{px + 68}" y="{ry + 27}" font-size="14" font-weight="700" font-family="{MONO}" fill="{t["card_ink"]}">{path}</text>')
        a(f'<text x="{px + 68}" y="{ry + 46}" font-size="12" fill="{t["card_muted"]}">{what}</text>')
    a(f'<text x="{px + 22}" y="{LANES[0] + 392}" font-size="12.5" font-weight="600" fill="{t["lime"]}">0 servers · 0 databases · git sync</text>')

    # right panel: guardrails
    gy0 = LANES[0] + 432
    a(f'<rect x="{px}" y="{gy0}" width="{pw}" height="{LANES[3] + 160 - gy0}" rx="24" fill="{t["lane"]}" stroke="{t["lane_line"]}"/>')
    a(icon("shield-check", px + 22, gy0 + 22, 20, t["tints"]["alo"][1]))
    a(f'<text x="{px + 52}" y="{gy0 + 38}" font-size="15" font-weight="800" fill="{t["ink"]}">Guardrails</text>')
    rules = ["Sends only what reps approve", "Every fact cites a source", "Manager approves each lead",
             "Suppression checked first", "Scores computed by scripts", "Web text is data, not orders"]
    for i, r in enumerate(rules):
        ry = gy0 + 70 + i * 30
        a(f'<circle cx="{px + 30}" cy="{ry - 4}" r="4" fill="{t["tints"]["alo"][1]}"/>')
        a(f'<text x="{px + 44}" y="{ry}" font-size="13" fill="{t["ink"]}">{r}</text>')

    # footer
    a(f'<text x="40" y="{H - 30}" font-size="12.5" fill="{t["muted"]}">Agents: Scout · Researcher · VAM · Writer · Allocator'
      f'  —  maths in scripts, judgement in the LLM, decisions with people. Times shown for Singapore.</text>')
    a('</svg>')
    return "\n".join(o)


for name, theme in THEMES.items():
    path = OUT / f"architecture-{name}.svg"
    path.write_text(build(name, theme))
    print(f"wrote {path.relative_to(OUT.parent.parent)}")
