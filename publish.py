#!/usr/bin/env python3
"""Publish one Pop Culture Digest day to the RSS feed.
Usage: publish.py /workspace/digest-YYYY-MM-DD [--no-push] [--classic]
Reader layout (content:encoded, clean HTML) is the default when the day folder has content.py;
--classic forces the old email-HTML description."""
import sys, os, re, json, glob, shutil, subprocess, html, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from email.utils import format_datetime
REPO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(REPO, "docs")
BASE = "https://johnmacgaffey.github.io/pop-culture-digest"
TZ = ZoneInfo("America/Chicago")
STYLE = ('<meta name="viewport" content="width=device-width, initial-scale=1">'
 '<style>html,body{margin:0;padding:0;background:#fff}body>*{max-width:100%!important}'
 'img{max-width:100%;height:auto}</style>')

def find_file(src, cid):
    dirs = [os.path.join(src, "images"), src]
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, cid + ".*"))):
            return f
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, cid + "*"))):
            if os.path.isfile(f): return f
    return None

def from_b64(src, cid, outdir):
    import base64
    for j in glob.glob(os.path.join(src, "*.json")):
        try: data = json.load(open(j))
        except Exception: continue
        if isinstance(data, dict): data = data.get("attachments", [])
        if not isinstance(data, list): continue
        for a in data:
            if isinstance(a, dict) and a.get("contentId") == cid and a.get("content"):
                name = cid + os.path.splitext(a.get("filename", ".jpg"))[1]
                open(os.path.join(outdir, name), "wb").write(base64.b64decode(a["content"]))
                return name
    return None

def url_from_json(src, cid):
    for j in glob.glob(os.path.join(src, "*.json")):
        try: txt = open(j).read()
        except Exception: continue
        m = re.search(r'"contentId"\s*:\s*"%s"[^}]*?"url"\s*:\s*"([^"]+)"' % re.escape(cid), txt) or \
            re.search(r'"url"\s*:\s*"([^"]+)"[^}]*?"contentId"\s*:\s*"%s"' % re.escape(cid), txt)
        if m: return m.group(1)
    if cid.startswith("fav_"):
        dom = cid[4:]
        if "." not in dom: dom += ".com"
        return "https://www.google.com/s2/favicons?domain=%s&sz=64" % dom
    return None

def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        f.write(r.read())

def link_label(fav, name):
    f = fav.replace("fav_", "").split(".")[0]
    if f == "youtube": return "Trailer on YouTube" if name.lower() == "trailer" else name + " on YouTube"
    if f == "spotify": return "Listen on Spotify"
    return "Read at " + name

def reader_html(src, ds, out):
    import runpy
    c = runpy.run_path(os.path.join(src, "content.py"))
    def img(cid):
        f = glob.glob(os.path.join(out, "images", cid + ".*"))
        return (BASE + "/" + ds + "/images/" + os.path.basename(f[0]), f[0]) if f else (None, None)
    h = []
    if c.get("intro"): h.append("<p>%s</p>" % c["intro"])
    for st in c["stories"]:
        h.append("<h2>%s</h2>" % st["head"])
        h.append("<p><strong>%s</strong></p>" % html.escape(st.get("cat", "")))
        u, _ = img(st.get("img", ""))
        if u: h.append('<img src="%s" alt="%s">' % (u, html.escape(st.get("alt", ""), quote=True)))
        h += ["<p>%s</p>" % p for p in st.get("paras", [])]
        if st.get("links"):
            h.append("<ul>" + "".join('<li><a href="%s">%s</a></li>' % (html.escape(l[2], quote=True), html.escape(link_label(l[0], l[1])))
                                    for l in st["links"]) + "</ul>")
    if c.get("bottom"):
        h.append("<h2>Bottom of the news</h2><ul>" + "".join("<li>%s</li>" % b for b in c["bottom"]) + "</ul>")
    summary = "Today: " + "; ".join(st.get("head_txt") or re.sub("<[^>]+>", "", st["head"]) for st in c["stories"]) + "."
    lead = img(c["stories"][0].get("img", ""))
    enc = {"url": lead[0], "length": os.path.getsize(lead[1]),
           "type": "image/png" if lead[1].endswith(".png") else "image/jpeg"} if lead[0] else None
    return "\n".join(h), html.unescape(summary), enc

def build_day(src, reader=True):
    raw = open(os.path.join(src, "digest.html"), encoding="utf-8").read()
    m = re.search(r"<title>([^<]+)", raw)
    title = html.unescape(m.group(1).strip()) if m else "Pop Culture Digest"
    d = re.search(r"\w+day, (\w+ \d+, \d{4})", title)
    date = datetime.strptime(d.group(1), "%B %d, %Y").date() if d else \
        datetime.strptime(re.search(r"\d{4}-\d\d-\d\d", src).group(0), "%Y-%m-%d").date()
    ds = date.isoformat()
    out = os.path.join(ROOT, ds); shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "images"))
    problems = []
    def repl(mo):
        cid = mo.group(1)
        f = find_file(src, cid)
        if f:
            name = cid + os.path.splitext(f)[1]
            shutil.copy(f, os.path.join(out, "images", name))
            return "images/" + name
        n = from_b64(src, cid, os.path.join(out, "images"))
        if n: return "images/" + n
        u = url_from_json(src, cid)
        if u:
            ext = ".png" if cid.startswith("fav_") else ".jpg"
            try:
                fetch(u, os.path.join(out, "images", cid + ext)); return "images/" + cid + ext
            except Exception as e:
                problems.append(f"{ds}: {cid} download failed ({e}); hotlinked")
                return u
        problems.append(f"{ds}: no file for cid:{cid}")
        return ""
    page = re.sub(r"cid:([^\"'\s)]+)", repl, raw)
    page = page.replace("<head>", "<head>" + STYLE, 1) if "<head>" in page else STYLE + page
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page)
    body = re.search(r"<body[^>]*>(.*)</body>", page, re.S)
    body = body.group(1) if body else page
    body = re.sub(r'(src=["\'])images/', r'\g<1>%s/%s/images/' % (BASE, ds), body)
    pub = datetime(date.year, date.month, date.day, 8, 0, tzinfo=TZ)
    meta = {"date": ds, "title": title, "link": f"{BASE}/{ds}/",
            "pubDate": format_datetime(pub), "description": body}
    if reader and os.path.exists(os.path.join(src, "content.py")):
        meta["content"], meta["summary"], meta["enclosure"] = reader_html(src, ds, out)
    json.dump(meta, open(os.path.join(out, "item.json"), "w"), ensure_ascii=False)
    return ds, problems

def rebuild():
    items = sorted((json.load(open(f)) for f in glob.glob(os.path.join(ROOT, "*/item.json"))),
                   key=lambda i: i["date"], reverse=True)
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:media="http://search.yahoo.com/mrss/"><channel>',
         '<title>Pop Culture Digest</title>', f'<link>{BASE}/</link>',
         '<description>John\'s daily pop culture magazine.</description><language>en-us</language>',
         f'<atom:link href="{BASE}/feed.xml" rel="self" type="application/rss+xml"/>']
    cd = lambda t: "<![CDATA[%s]]>" % t.replace("]]>", "]]]]><![CDATA[>")
    for i in items:
        e = ["<item>", "<title>%s</title>" % html.escape(i["title"]), "<link>%s</link>" % i["link"],
             '<guid isPermaLink="true">%s</guid>' % i["link"], "<pubDate>%s</pubDate>" % i["pubDate"]]
        if i.get("content"):
            e.append("<description>%s</description>" % html.escape(i["summary"]))
            e.append("<content:encoded>%s</content:encoded>" % cd(i["content"]))
            if i.get("enclosure"):
                en = i["enclosure"]
                e.append('<enclosure url="%s" length="%d" type="%s"/>' % (en["url"], en["length"], en["type"]))
                e.append('<media:content url="%s" medium="image" type="%s"/>' % (en["url"], en["type"]))
        else:
            e.append("<description>%s</description>" % cd(i["description"]))
        e.append("</item>")
        x.append("".join(e))
    x.append("</channel></rss>")
    open(os.path.join(ROOT, "feed.xml"), "w", encoding="utf-8").write("\n".join(x))
    lis = "".join(f'<li><a href="{i["date"]}/">{html.escape(i["title"])}</a></li>' for i in items)
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">{STYLE}<title>Pop Culture Digest</title>'
        f'<link rel="alternate" type="application/rss+xml" title="Pop Culture Digest" href="{BASE}/feed.xml">'
        '<style>body{font-family:-apple-system,Helvetica,Arial,sans-serif;padding:16px}li{margin:8px 0}</style></head>'
        f'<body><h1>Pop Culture Digest</h1><p><a href="feed.xml">RSS feed</a></p><ul>{lis}</ul></body></html>')
    open(os.path.join(ROOT, ".nojekyll"), "w").close()

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    push = "--no-push" not in sys.argv
    probs = []
    for src in args:
        ds, p = build_day(os.path.abspath(src), reader="--classic" not in sys.argv); probs += p; print("built", ds)
    rebuild()
    for p in probs: print("WARN", p)
    if push:
        g = lambda *c: subprocess.run(["git", "-C", REPO, *c], check=True)
        g("add", "-A")
        if subprocess.run(["git", "-C", REPO, "diff", "--cached", "--quiet"]).returncode:
            g("commit", "-qm", "Publish " + ", ".join(os.path.basename(a) for a in args))
        g("push", "-q", "origin", "main")
main()
