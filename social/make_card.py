"""Make a Facebook picture card (1080x1350 PNG) in the site's look.

Usage:  python3 social/make_card.py card.json social/img/2026-10-22-weekend.png

card.json fields:
  theme:    "pine" (dark green), "sunset" (warm orange), "cream" (light), or "night" (dark blue)
  kicker:   small label on top, e.g. "This weekend"
  title:    big headline, e.g. "Oct 23-25 around SE Oklahoma"
  subtitle: optional short line under the headline
  items:    optional, up to 6: [{"cat": "festivals|music|shows|markets|community|sports", "title": "...", "meta": "Sat 6 PM · Wilburton"}]
  big:      optional large statement or question instead of a list, e.g. "Fish fry or chili cook-off?"
  footer:   optional, defaults to the site address
Text only: no emoji (the renderer has no emoji font).
"""
import json, sys, html, pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ICONS = json.load(open(HERE / "icons.json"))
THEMES = {
    "pine":   {"bg": "#1d4a37", "bg2": "#143426", "ink": "#f4f1ea", "muted": "#bcd3c4", "accent": "#f39a5b", "card": "rgba(255,255,255,.08)"},
    "sunset": {"bg": "#b4461d", "bg2": "#7c2e12", "ink": "#fff7ee", "muted": "#ffd9bf", "accent": "#f6c453", "card": "rgba(255,255,255,.12)"},
    "cream":  {"bg": "#f3ead8", "bg2": "#e8dcc2", "ink": "#17201b", "muted": "#56625a", "accent": "#b4461d", "card": "rgba(29,74,55,.08)"},
    "night":  {"bg": "#1b2b33", "bg2": "#0f181d", "ink": "#f2efe6", "muted": "#a9bcc6", "accent": "#f6c453", "card": "rgba(255,255,255,.08)"},
}
CATCOL = {"festivals": "#f39a5b", "music": "#b9a3f0", "shows": "#f29cc6", "markets": "#7fd3a2", "community": "#8cc4ee", "sports": "#f0cb62"}

CSS = """
@font-face{font-family:Barlow;font-weight:800;src:url("FONTDIR/BarlowCondensed-ExtraBold.ttf")}
@font-face{font-family:Barlow;font-weight:600;src:url("FONTDIR/BarlowCondensed-SemiBold.ttf")}
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1350px;overflow:hidden;background:linear-gradient(170deg,BG 0%,BG2 100%);color:INK;font-family:"Liberation Sans",Arial,sans-serif;position:relative}
.wrap{position:absolute;inset:0;padding:78px 76px 0;display:flex;flex-direction:column;gap:26px}
.kick{align-self:flex-start;background:ACCENT;color:#1a1208;font:800 34px/1 Barlow;letter-spacing:.08em;text-transform:uppercase;padding:14px 22px 11px;border-radius:8px}
h1{font:800 H1SIZEpx/.95 Barlow;text-transform:uppercase;letter-spacing:-.01em}
.sub{font:600 40px/1.15 Barlow;color:MUTED;letter-spacing:.02em}
.list{display:flex;flex-direction:column;gap:14px;margin-top:4px}
.it{display:flex;gap:22px;align-items:center;background:CARD;border-radius:18px;padding:16px 22px}
.ic{width:70px;height:70px;flex:none;border-radius:16px;background:rgba(0,0,0,.18);display:grid;place-items:center}
.ic svg{width:42px;height:42px}
.t{font:800 42px/1.05 Barlow;letter-spacing:.01em}
.m{font-size:27px;color:MUTED;margin-top:6px}
.big{font:800 150px/.98 Barlow;text-transform:uppercase;margin-top:70px}
.ridge{position:absolute;left:0;right:0;bottom:0;height:250px}
.foot{position:absolute;left:76px;bottom:44px;font:800 38px/1 Barlow;text-transform:uppercase;letter-spacing:.04em;color:#f4f1ea}
.foot small{display:block;font:600 30px/1 Barlow;letter-spacing:.03em;color:#d8e6dc;margin-top:8px;text-transform:none}
.sun{position:absolute;right:110px;bottom:128px;width:104px;height:104px;border-radius:50%;background:#e87c48}
"""

RIDGE = """<svg class="ridge" viewBox="0 0 1080 250" preserveAspectRatio="none">
<path d="M0 120 L90 78 L170 98 L260 52 L360 92 L450 60 L560 96 L650 46 L760 88 L860 58 L960 94 L1080 70 L1080 250 L0 250Z" fill="#7fa58e"/>
<path d="M0 150 L110 116 L210 138 L320 98 L430 134 L540 110 L640 140 L750 102 L860 136 L980 112 L1080 130 L1080 250 L0 250Z" fill="#3f7259"/>
<path d="M0 180 L140 150 L280 172 L420 144 L560 170 L700 148 L840 172 L980 152 L1080 166 L1080 250 L0 250Z" fill="#1d4a37"/></svg>"""


def icon(k, color):
    attrs, body = ICONS.get(k, ICONS["festivals"])
    return '<svg viewBox="0 0 24 24"%s style="color:%s">%s</svg>' % (attrs, color, body)


def render(spec, out):
    th = THEMES.get(spec.get("theme", "pine"), THEMES["pine"])
    e = lambda s: html.escape(str(s or ""))
    items = (spec.get("items") or [])[:6]
    import base64
    font = lambda f: "data:font/ttf;base64," + base64.b64encode((HERE / "fonts" / f).read_bytes()).decode()
    css = (CSS.replace("BG2", th["bg2"]).replace("BG", th["bg"]).replace("INK", th["ink"]).replace("MUTED", th["muted"])
              .replace("ACCENT", th["accent"]).replace("CARD", th["card"]).replace("H1SIZE", "92" if spec.get("big") else "100"))
    # fonts go in last so the color replacements above can't touch the embedded font data
    css = (css.replace("FONTDIR/BarlowCondensed-ExtraBold.ttf", font("BarlowCondensed-ExtraBold.ttf"))
              .replace("FONTDIR/BarlowCondensed-SemiBold.ttf", font("BarlowCondensed-SemiBold.ttf")))
    rows = "".join('<div class="it"><div class="ic">%s</div><div><div class="t">%s</div><div class="m">%s</div></div></div>'
                   % (icon(i.get("cat", "festivals"), CATCOL.get(i.get("cat"), th["accent"])), e(i.get("title")), e(i.get("meta"))) for i in items)
    parts = ['<div class="kick">%s</div>' % e(spec.get("kicker", "Southeast Oklahoma Events")), "<h1>%s</h1>" % e(spec.get("title"))]
    if spec.get("subtitle"): parts.append('<div class="sub">%s</div>' % e(spec["subtitle"]))
    if spec.get("big"): parts.append('<div class="big">%s</div>' % e(spec["big"]))
    if rows: parts.append('<div class="list">%s</div>' % rows)
    doc = ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body><div class="sun"></div>%s'
           '<div class="wrap">%s</div><div class="foot">Southeast Oklahoma Events<small>%s</small></div></body></html>'
           % (css, RIDGE, "".join(parts), e(spec.get("footer", "jcow1den.github.io/seok-events"))))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        pg.set_content(doc)
        pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(300)
        bottom = pg.evaluate("Math.max(...[...document.querySelectorAll('.wrap > *')].map(n => n.getBoundingClientRect().bottom))")
        pg.screenshot(path=out)
        b.close()
    if bottom > 1100:
        print("WARNING: text runs into the mountains at the bottom (%dpx). Use fewer items or shorter text, then render again." % bottom)
    print("wrote", out)


if __name__ == "__main__":
    render(json.load(open(sys.argv[1])), sys.argv[2])
