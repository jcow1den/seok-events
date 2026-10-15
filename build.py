"""Build the Southeast Oklahoma Events site.

Edit events.json, then run:  python3 build.py
Writes index.html, events.ics (calendar feed), and sitemap.xml.

Event fields: id, date (YYYY-MM-DD), endDate (optional), title,
category (festivals|music|markets|community|sports), area, time, venue,
address ("street, Town, OK 74501"), description, and optional flags:
free, kids, indoor, featured, unconfirmed.
Optional details for Google (only when a source confirms them): performer (list of names),
organizer (name), offers ({"low": 15} or {"low": 15, "high": 25}, in US dollars).
"""
import json, sys, re
from datetime import datetime, timezone, date, timedelta

SITE = "https://jcow1den.github.io/seok-events/"
FALLBACK_TOWNS = {"Longtown": "Eufaula"}  # towns without their own ZIP code

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
        if street:
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
        "location": {"@type": "Place", "name": e.get("venue") or e["town"], "address": postal(e["address"])},
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

# ---------- index.html ----------
tpl = open("template.html").read()
html = (tpl.replace("__EVENTS__", json.dumps(live, ensure_ascii=False).replace("</", "<\\/"))
           .replace("__TOWNS__", json.dumps(towns, ensure_ascii=False))
           .replace("__JSONLD__", ld_json)
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
for e in live:
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

# ---------- sitemap.xml ----------
open("sitemap.xml", "w").write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    f"  <url><loc>{SITE}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>\n</urlset>\n")

print(f"Built: {len(live)} upcoming events ({len(events) - len(live)} past dropped), "
      f"{len(ld)} sent to Google, calendar feed and sitemap updated.")
