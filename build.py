"""Build the Southeast Oklahoma Events site.

Edit events.json, then run:  python3 build.py
Writes index.html, events.ics (calendar feed), and sitemap.xml.

Event fields: id, date (YYYY-MM-DD), endDate (optional), title,
category (festivals|music|shows|markets|community|sports), area, time, venue,
address ("street, Town, OK 74501"), description, and optional flags:
free, kids, indoor, featured, unconfirmed.
Optional details for Google (only when a source confirms them): performer (list of names),
organizer (name), offers ({"low": 15} or {"low": 15, "high": 25}, in US dollars).
"""
import json, sys, re
from datetime import datetime, timezone, date, timedelta

SITE = "https://jcow1den.github.io/seok-events/"
FALLBACK_TOWNS = {"Longtown": "Eufaula", "Hochatown": "Broken Bow"}  # towns without their own ZIP code

events = json.load(open("events.json"))
towns = json.load(open("towns.json"))
lookup = {t[0].lower(): t for t in towns}


def town_of(addr):
    parts = [p.strip() for p in addr.split(",")]
    return parts[-2] if len(parts) >= 2 else ""


ids = set()
for e in events:
    if e["id"] in ids:
        sys.exit(f"Duplicate event id {e['id']}")
    ids.add(e["id"])
    for f in ("date", "title", "category", "area", "address"):
        if not e.get(f):
            sys.exit(f"Event {e['id']} is missing {f}")
    town = town_of(e["address"])
    t = lookup.get(FALLBACK_TOWNS.get(town, town).lower())
    if not t:
        sys.exit(f"No coordinates for town '{town}' in event {e['id']}. Add it to FALLBACK_TOWNS.")
    e["town"] = town
    e["lat"], e["lon"] = t[1], t[2]

# Drop events that have already ended (Central time)
today = (datetime.now(timezone.utc) - timedelta(hours=6)).date().isoformat()
live = [e for e in events if (e.get("endDate") or e["date"]) >= today]


# ---------- Google event data (schema.org) ----------
def postal(addr):
    parts = [p.strip() for p in addr.split(",")]
    out = {"@type": "PostalAddress", "addressRegion": "OK", "addressCountry": "US"}
    if len(parts) >= 2:
        out["addressLocality"] = parts[-2]
        m = re.search(r"\b(\d{5})\b", parts[-1])
        if m:
            out["postalCode"] = m.group(1)
        street = ", ".join(parts[:-2])
        if street and "to be announced" not in street.lower():
            out["streetAddress"] = street
    return out


ld = []
for e in live:
    if e.get("unconfirmed"):
        continue  # only send Google events confirmed by a source
    item = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": e["title"],
        "startDate": e["date"],
        "endDate": e.get("endDate") or e["date"],
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {"@type": "Place", "name": (e.get("venue") if e.get("venue") and "to be announced" not in e["venue"].lower() else e["town"]), "address": postal(e["address"])},
        "description": ((e.get("time") + ". ") if e.get("time") else "") + e.get("description", ""),
        "image": [SITE + "icons/event-1x1.png", SITE + "icons/event-4x3.png", SITE + "icons/event-16x9.png"],
        "url": SITE + "#" + e["id"],
    }
    if e.get("performer"):
        item["performer"] = [{"@type": "PerformingGroup" if " band" in n.lower() or n.lower().startswith("the ") else "Person", "name": n}
                             for n in e["performer"]]
    if e.get("organizer"):
        item["organizer"] = {"@type": "Organization", "name": e["organizer"]}
    if e.get("offers") and not e.get("free"):
        o = e["offers"]
        offer = {"@type": "AggregateOffer" if o.get("high") else "Offer", "priceCurrency": "USD", "url": SITE + "#" + e["id"],
                 "availability": "https://schema.org/InStock"}
        if o.get("high"):
            offer.update(lowPrice=o["low"], highPrice=o["high"])
        else:
            offer["price"] = o["low"]
        item["offers"] = offer
    if e.get("free"):
        item["isAccessibleForFree"] = True
        item["offers"] = {"@type": "Offer", "price": 0, "priceCurrency": "USD", "url": SITE + "#" + e["id"],
                          "availability": "https://schema.org/InStock"}
    ld.append(item)
ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")

# ---------- Worth the drive (big shows outside the region; never mixed into local lists, calendar, or Google data) ----------
try:
    drive = [d for d in json.load(open("drive.json")) if (d.get("endDate") or d["date"]) >= today]
except FileNotFoundError:
    drive = []
for d in drive:
    if d.get("kind") not in ("shows", "festivals", "family", "sports"):
        sys.exit(f"Worth-the-drive item {d.get('id')} needs kind: shows, festivals, family, or sports")
    for f in ("id", "date", "title", "city", "venue", "address", "lat", "lon", "url"):
        if d.get(f) in (None, ""):
            sys.exit(f"Worth-the-drive item {d.get('id')} is missing {f}")

# ---------- index.html ----------
tpl = open("template.html").read()
html = (tpl.replace("__EVENTS__", json.dumps(live, ensure_ascii=False).replace("</", "<\\/"))
           .replace("__TOWNS__", json.dumps(towns, ensure_ascii=False))
           .replace("__JSONLD__", ld_json)
           .replace("__DRIVE__", json.dumps(drive, ensure_ascii=False).replace("</", "<\\/"))
           .replace("__BUILT__", today))
open("index.html", "w").write(html)


# ---------- events.ics ----------
def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    b = line.encode("utf-8")
    if len(b) <= 74:
        return line
    out, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > 74:
            out.append(cur.decode("utf-8"))
            cur = b" " + cb
        else:
            cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Southeast Oklahoma Events//EN", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", "X-WR-CALNAME:Southeast Oklahoma Events", "X-WR-TIMEZONE:America/Chicago",
         "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
def open_dates(e):
    """Each date the event is open. Events with openDays (0=Sun ... 6=Sat) list only those weekdays."""
    d, last = date.fromisoformat(e["date"]), date.fromisoformat(e.get("endDate") or e["date"])
    out = []
    while d <= last:
        if not e.get("openDays") or (d.isoweekday() % 7) in e["openDays"]:
            out.append(d)
        d += timedelta(days=1)
    return out


for e in live:
    if e.get("openDays"):
        # One calendar entry per open day, so a weekends-only festival doesn't fill the weekdays
        for d in open_dates(e):
            if d.isoformat() < today:
                continue
            desc = "\n".join(filter(None, [e.get("time"), e.get("description"), SITE + "#" + e["id"]]))
            lines += ["BEGIN:VEVENT", f"UID:{e['id']}-{d.strftime('%Y%m%d')}@seok-events", f"DTSTAMP:{stamp}",
                      "DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"),
                      "DTEND;VALUE=DATE:" + (d + timedelta(days=1)).strftime("%Y%m%d"),
                      "SUMMARY:" + esc(e["title"]), "DESCRIPTION:" + esc(desc),
                      "LOCATION:" + esc(", ".join(filter(None, [e.get("venue"), e["address"]]))),
                      "URL:" + SITE + "#" + e["id"], "TRANSP:TRANSPARENT", "END:VEVENT"]
        continue
    end = date.fromisoformat(e.get("endDate") or e["date"]) + timedelta(days=1)
    desc = "\n".join(filter(None, [e.get("time"), e.get("description"),
                                   "Confirm details with the host before you go." if e.get("unconfirmed") else "",
                                   SITE + "#" + e["id"]]))
    title = e["title"] + (f" ({e['time']})" if e.get("time") and not e.get("endDate") else "")
    lines += ["BEGIN:VEVENT", f"UID:{e['id']}@seok-events", f"DTSTAMP:{stamp}",
              "DTSTART;VALUE=DATE:" + e["date"].replace("-", ""),
              "DTEND;VALUE=DATE:" + end.isoformat().replace("-", ""),
              "SUMMARY:" + esc(title), "DESCRIPTION:" + esc(desc),
              "LOCATION:" + esc(", ".join(filter(None, [e.get("venue"), e["address"]]))),
              "URL:" + SITE + "#" + e["id"], "TRANSP:TRANSPARENT", "END:VEVENT"]
lines.append("END:VCALENDAR")
open("events.ics", "w", newline="").write("\r\n".join(fold(l) for l in lines) + "\r\n")

# ---------- christmas/index.html (plain HTML holiday guide, Nov 14 to Dec 24) ----------
import html as _h
from pathlib import Path
XS, XE = "2026-11-14", "2026-12-24"
XT = [("parade", "Christmas parades"), ("lights", "Christmas lights and drive throughs"), ("tree", "Tree lightings"),
      ("market", "Christmas markets"), ("santa", "Visits with Santa"), ("more", "More holiday fun")]
AREAS = {"ada-holdenville": "Ada & Holdenville", "atoka": "Atoka", "durant": "Durant", "eufaula": "Eufaula & Checotah",
         "hugo-antlers": "Hugo & Antlers", "idabel-broken-bow": "Idabel & Broken Bow", "mcalester": "McAlester",
         "okmulgee-east": "Okmulgee & Henryetta", "poteau": "Poteau", "wilburton": "Wilburton"}


def xin(e):
    return e.get("xmas") and not e.get("unconfirmed") and e.get("source") and e["date"] <= XE and (e.get("endDate") or e["date"]) >= max(XS, today)


def xdate(e):
    d1 = date.fromisoformat(e["date"])
    s = d1.strftime("%a %b ") + str(d1.day)
    if e.get("endDate") and e["endDate"] != e["date"]:
        d2 = date.fromisoformat(e["endDate"])
        s += " to " + d2.strftime("%b ") + str(d2.day) + (", " + str(d2.year) if d2.year != d1.year else "")
    return s


def xitem(e, place, link):
    x = _h.escape
    bits = [f'<li id="x-{x(e["id"])}"><h4>{x(e["title"])}</h4>',
            f'<p class="when"><b>{x(xdate(e))}</b>' + (f' · {x(e["time"])}' if e.get("time") else "") + "</p>",
            f'<p class="where">{x(place)}</p>']
    if e.get("description"):
        bits.append(f"<p>{x(e['description'])}</p>")
    bits.append(f'<p class="src"><a href="{link}">More on the event site</a>' +
                (" · Free" if e.get("free") else "") + "</p></li>")
    return "".join(bits)


xl = sorted([e for e in events if xin(e)], key=lambda e: (e["date"], e["title"]))
xd = sorted([d for d in json.load(open("drive.json")) if xin(d)], key=lambda e: (e["date"], e["title"]))
secs, toc, xcount = [], [], 0
for k, label in XT:
    items = [e for e in xl if e["xmas"] == k]
    if not items:
        continue
    xcount += len(items)
    toc.append(f'<a href="#{k}">{label} ({len(items)})</a>')
    lis = "".join(xitem(e, f'{e.get("venue") or e["town"]}, {e["address"]}' if e.get("venue") and e["venue"] not in e["address"] else e["address"], _h.escape(e["source"])) for e in items)
    secs.append(f'<section id="{k}"><h2>{label}</h2><ul>{lis}</ul></section>')
if xd:
    toc.append(f'<a href="#drive">OKC, Tulsa and DFW ({len(xd)})</a>')
    lis = "".join(xitem(d, f'{d["venue"]}, {d["address"]}', _h.escape(d.get("url") or d["source"])) for d in xd)
    secs.append(f'<section id="drive"><h2>Worth the drive: OKC, Tulsa and DFW</h2><ul>{lis}</ul></section>')
xtitle = "Christmas in Southeast Oklahoma 2026: Parades, Lights, Markets and Santa"
xdesc = (f"{xcount} Christmas parades, light displays, tree lightings, markets and visits with Santa across southeast Oklahoma "
         "from Nov 14 to Dec 24, 2026, with dates, times and addresses. Plus the big ones in OKC, Tulsa and DFW.")
xpage = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{xtitle}</title>
<meta name="description" content="{_h.escape(xdesc)}">
<link rel="canonical" href="{SITE}christmas/">
<meta name="theme-color" content="#1d4a37">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Southeast Oklahoma Events">
<meta property="og:title" content="{xtitle}">
<meta property="og:description" content="{_h.escape(xdesc)}">
<meta property="og:url" content="{SITE}christmas/">
<meta property="og:image" content="{SITE}icons/share.png">
<link rel="icon" href="../icons/icon-192.png">
<style>
:root{{--bg:#edf0ec;--surface:#fff;--ink:#17201b;--muted:#56625a;--line:#d5ddd6;--pine:#1d4a37;--clay:#b4461d}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0f1412;--surface:#181e1b;--ink:#e6ece7;--muted:#97a39b;--line:#2a332e;--pine:#69b58f;--clay:#ee8c60;color-scheme:dark}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:16px}}
header{{background:var(--pine);color:#fff}}
header a{{color:#fff}}
h1{{font:800 clamp(30px,8vw,48px)/1 "Arial Narrow",Arial,sans-serif;text-transform:uppercase;margin:8px 0}}
h2{{font:800 24px/1.1 "Arial Narrow",Arial,sans-serif;text-transform:uppercase;margin:28px 0 8px;border-bottom:3px solid var(--clay);padding-bottom:4px}}
h3{{margin:18px 0 6px;font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
h4{{margin:0 0 4px;font-size:17px;line-height:1.25}}
nav.toc{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}}
nav.toc a{{background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:7px 12px;color:var(--ink);text-decoration:none;font-weight:600;font-size:14px}}
ul{{list-style:none;margin:0;padding:0}}
li{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 10px}}
li p{{margin:2px 0}}
.when{{color:var(--clay)}} .where,.src{{color:var(--muted);font-size:14px}}
a{{color:var(--pine)}}
footer{{color:var(--muted);font-size:14px;padding:24px 0}}
</style>
</head>
<body>
<header><div class="wrap">
<p><a href="../">‹ All southeast Oklahoma events</a></p>
<h1>Christmas in Southeast Oklahoma 2026</h1>
<p>Parades, lights, tree lightings, markets and Santa from McAlester to Durant to Broken Bow, Nov 14 to Dec 24. Every listing links to the event's own page or the town's tourism site, so check there for weather changes.</p>
</div></header>
<main class="wrap">
<nav class="toc" aria-label="Guide sections">{"".join(toc)}</nav>
{"".join(secs)}
</main>
<footer class="wrap">Updated {today}. Know of a parade or light display we missed? Message the Southeast Oklahoma Area Events page on Facebook. <a href="../">See every event this week</a>.</footer>
</body>
</html>
"""
Path("christmas").mkdir(exist_ok=True)
open("christmas/index.html", "w").write(xpage)

# ---------- sitemap.xml ----------
open("sitemap.xml", "w").write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    f"  <url><loc>{SITE}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>\n"
    f"  <url><loc>{SITE}christmas/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>\n</urlset>\n")

# Plain-text sitemap: one URL per line (the simplest format Google accepts)
open("sitemap.txt", "w").write(SITE + "\n" + SITE + "christmas/\n")

print(f"Built: {len(live)} upcoming events ({len(events) - len(live)} past dropped), "
      f"{len(ld)} sent to Google, calendar feed and sitemap updated. Christmas guide: {xcount} local + {len(xd)} out of town.")
