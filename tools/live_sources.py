# -*- coding: utf-8 -*-
"""Terravium — shared live-news source logic (Python stdlib only).

Used by:
  · server.py            → serves /api/live with fresh data (10-min memory cache)
  · tools/refresh_live.py→ writes the js/live-data.js snapshot + bakes fresh
                            headlines into the HTML pages (run daily by the
                            GitHub Action so the site renews itself).
"""
import json
import re
import html as htmllib
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

HEADLINE_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Google News", "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en"),
]
WIKI_FEEDS = [
    "https://api.wikimedia.org/feed/v1/wikipedia/en/featured/",
    "https://en.wikipedia.org/api/rest_v1/feed/featured/",
]
UA = "TerraviumBot/1.0 (+live world news module; contact: hello@terravium.site)"


def http_get(url, timeout=20):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url, timeout=20):
    return json.loads(http_get(url, timeout).decode("utf-8"))


def strip_tags(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def clip(s, n):
    s = s or ""
    return s if len(s) <= n else re.sub(r"\s+\S*$", "", s[: n - 1]).strip() + "\u2026"


def rel_time(dt):
    now = datetime.now(timezone.utc)
    try:
        s = int((now - dt).total_seconds())
    except Exception:
        return ""
    if s < 0:
        s = 0
    if s < 60:
        return "just now"
    m = s // 60
    if m < 60:
        return "%dm ago" % m
    h = m // 60
    if h < 24:
        return "%dh ago" % h
    return "%dd ago" % (h // 24)


# ------------------------------------------------------------------ headlines
def _map_item(item):
    title = (item.findtext("title") or "").strip()
    m = re.match(r"^(.{20,})\s-\s[^-]{2,28}$", title)
    if m:
        title = m.group(1).strip()
    link = (item.findtext("link") or "").strip()
    desc = clip(strip_tags(item.findtext("description") or ""), 140)
    img = ""
    thumb = item.find("{http://search.yahoo.com/mrss/}thumbnail")
    if thumb is not None and thumb.get("url"):
        img = thumb.get("url")
    date, t = "", ""
    try:
        d = parsedate_to_datetime(item.findtext("pubDate") or "")
        date = d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        t = rel_time(d)
    except Exception:
        pass
    return {"title": title, "url": link, "desc": desc, "img": img, "date": date, "time": t}


def fetch_headlines():
    """Try each RSS feed in order; return {source, items:[...]} or None."""
    for name, url in HEADLINE_FEEDS:
        try:
            root = ET.fromstring(http_get(url))
            items = [_map_item(i) for i in root.iter("item")]
            items = [i for i in items if i["title"] and i["url"]]
            if items:
                return {"source": name, "items": items[:20]}
        except Exception:
            continue
    return None


# ------------------------------------------------------------------ wikipedia
def _page_url(x):
    try:
        return x["content_urls"]["desktop"]["page"]
    except Exception:
        return "https://en.wikipedia.org"


def _today_path():
    return datetime.now(timezone.utc).strftime("%Y/%m/%d")


def fetch_wiki():
    """Wikimedia 'featured' feed → mapped dict, or None."""
    for base in WIKI_FEEDS:
        try:
            w = http_json(base + _today_path())
        except Exception:
            continue
        out = {}
        out["news"] = [
            {
                "text": clip(strip_tags(n.get("story", "")), 230),
                "url": (n.get("links") and _page_url(n["links"][0]))
                       or "https://en.wikipedia.org/wiki/Portal:Current_events",
            }
            for n in w.get("news", [])
        ][:8]
        out["otd"] = []
        for n in w.get("onthisday", [])[:40]:
            pages = n.get("pages") or []
            out["otd"].append({
                "year": n.get("year"),
                "text": clip(strip_tags(n.get("text", "")), 210),
                "url": _page_url(pages[0]) if pages else "https://en.wikipedia.org",
            })
        im = w.get("image") or {}
        desc = im.get("description")
        if isinstance(desc, list):
            desc = " ".join(desc)
        img = ""
        if isinstance(im.get("thumbnail"), dict):
            img = im["thumbnail"].get("source", "")
        if not img and isinstance(im.get("image"), dict):
            img = im["image"].get("source", "")
        out["potd"] = None
        if img:
            title = re.sub(r"^File:", "", im.get("title", "Picture of the day"))
            title = re.sub(r"\.(jpe?g|png|gif|tiff?|webm|ogg|svg)$", "", title, flags=re.I)
            out["potd"] = {
                "img": img,
                "title": title.replace("_", " "),
                "desc": clip(desc or "", 170),
                "url": im.get("file_page") or "https://commons.wikimedia.org/wiki/Main_Page",
            }
        t = w.get("tfa") or {}
        out["tfa"] = None
        if t.get("titles"):
            out["tfa"] = {
                "title": t["titles"].get("normalized", "Today\u2019s featured article"),
                "extract": clip(t.get("extract", ""), 300),
                "img": (t.get("thumbnail") or {}).get("source", ""),
                "url": _page_url(t),
            }
        out["mostread"] = [
            {
                "title": (a.get("titles") or {}).get("normalized", a.get("title", "")),
                "url": _page_url(a),
            }
            for a in (w.get("mostread", {}).get("articles", []))
        ][:10]
        return out
    return None


def build_live_data():
    """Dict shaped exactly like the browser-side cache."""
    return {
        "ts": int(time.time() * 1000),
        "headlines": fetch_headlines(),
        "wiki": fetch_wiki(),
    }
