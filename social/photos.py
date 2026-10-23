"""Find free-to-use photos of places on Wikimedia Commons, with author and license.

Search:    python3 social/photos.py search "Heavener Runestone" [max]
Download:  python3 social/photos.py get "File:Some photo.jpg" social/photos/heavener-runestone.jpg

"get" saves the photo (1280px wide) and a .json next to it with the title, author, license,
source page and a ready-made credit line, e.g. "Photo: Jane Smith, CC BY-SA 4.0".
Only public domain, CC0, CC BY and CC BY-SA photos are returned. Always open the photo and
read its description before using it: make sure it really shows the place you're posting about.
"""
import json, re, sys, html, urllib.parse, urllib.request, pathlib

API = "https://commons.wikimedia.org/w/api.php"
UA = "SEOKEvents/1.0 (https://jcow1den.github.io/seok-events/; jcow1den@users.noreply.github.com)"
OK = re.compile(r"^(public domain|pd\b|pd-|cc0|cc by(-sa)? \d)", re.I)


def call(params):
    params.update(format="json", formatversion="2")
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=30))


def clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def info(page, width):
    ii = (page.get("imageinfo") or [{}])[0]
    m = ii.get("extmetadata") or {}
    v = lambda k: clean((m.get(k) or {}).get("value", ""))
    lic = v("LicenseShortName")
    author = v("Artist") or v("Credit")
    if v("AttributionRequired") == "false" and not author:
        author = "Wikimedia Commons"
    return {
        "title": page["title"],
        "page": ii.get("descriptionurl", ""),
        "description": v("ImageDescription")[:400],
        "date": v("DateTimeOriginal") or v("DateTime"),
        "author": author[:80],
        "license": lic,
        "license_url": v("LicenseUrl"),
        "usable": bool(OK.match(lic)) and "nc" not in lic.lower() and "nd" not in lic.lower().split(),
        "size": [ii.get("width"), ii.get("height")],
        "url": (ii.get("url") or "").split("?")[0],
        "credit": "Photo: %s, %s" % (author[:60] or "Wikimedia Commons", lic) if lic else "",
    }


def search(q, n=12):
    d = call({"action": "query", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6,
              "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|extmetadata|size"})
    out = [info(p, 1600) for p in (d.get("query") or {}).get("pages", [])]
    return [x for x in out if x["usable"] and x["size"][0] and x["size"][0] >= 1000]


def get(title, dest):
    d = call({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|extmetadata|size"})
    x = info(d["query"]["pages"][0], 1600)
    if not x["usable"]:
        sys.exit("Not usable: license is %r" % x["license"])
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = x["url"]
    if x["size"][0] and x["size"][0] > 1280:  # Wikimedia asks for its standard thumbnail sizes instead of originals
        name = url.rsplit("/", 1)[1]
        url = url.replace("/wikipedia/commons/", "/wikipedia/commons/thumb/", 1) + "/1280px-" + name
    import subprocess, time
    for wait in (0, 20, 60):  # Wikimedia sometimes says "too many requests"; wait and try again
        time.sleep(wait)
        r = subprocess.run(["curl", "-sSf", "-m", "120", "-A", UA, "-o", str(dest), url], capture_output=True, text=True)
        if r.returncode == 0:
            break
    else:
        sys.exit("Download failed: " + r.stderr.strip())
    try:  # keep files small and upright
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(dest)).convert("RGB")
        if im.width > 1280:
            im = im.resize((1280, round(im.height * 1280 / im.width)), Image.LANCZOS)
        im.save(dest, "JPEG", quality=85)
    except ImportError:
        pass
    dest.with_suffix(".json").write_text(json.dumps(x, indent=1))
    print(json.dumps(x, indent=1))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12), indent=1))
    elif len(sys.argv) == 4 and sys.argv[1] == "get":
        get(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
