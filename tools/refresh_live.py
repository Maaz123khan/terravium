#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Terravium — daily auto-refresh.

1. Fetches the live world news (BBC World RSS → Google News, Wikimedia daily feed).
2. Writes the snapshot to js/live-data.js  → the site ALWAYS has news to show,
   even with no internet in the visitor's browser.
3. Bakes the freshest headlines directly into the HTML pages (between
   <!--TERRAVIUM:bake:...--> markers) so crawlers and no-JS visitors see real
   content — great for SEO.

Run it daily via the included GitHub Action (.github/workflows/daily-update.yml)
or manually:  python3 tools/refresh_live.py
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.live_sources import build_live_data  # noqa: E402

SITE = "https://terravium.site"
STATIC_PAGES = {"index.html", "world.html", "news.html", "blogs.html", "faq.html",
                "contact.html", "privacy.html", "terms.html", "read.html"}

BAKE_TARGETS = {
    "index-strip": ("index.html", 5),
    "news-headlines": ("news.html", 6),
    "world-headlines": ("world.html", 12),
}


def esc(s):
    return escape(str(s or ""), quote=True)


def xml_esc(s):
    return escape(str(s or ""), quote=True)


def rfc822(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def parse_posts():
    """Read every post page's SEO metadata → list of dicts (newest first)."""
    posts = []
    for path in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        name = os.path.basename(path)
        if name in STATIC_PAGES:
            continue
        src = open(path, encoding="utf-8").read()
        def pick(pat, default=""):
            m = re.search(pat, src, re.S)
            return m.group(1).strip() if m else default
        posts.append({
            "title": pick(r"<title>(.*?) \| Terravium</title>", name),
            "link": pick(r'<link rel="canonical" href="(.*?)"', SITE + "/" + name),
            "desc": pick(r'<meta name="description" content="(.*?)"'),
            "pub": pick(r'article:published_time" content="(.*?)"'),
            "cat": pick(r'<span aria-current="page">(.*?)</span>'),
        })
    posts.sort(key=lambda p: p["pub"], reverse=True)
    return posts


def build_rss(headlines):
    """Full site feed: a fresh 'daily digest' item (today's world headlines)
    followed by the magazine's posts. Regenerated every day by the Action —
    this is what RSS-to-email services (e.g. MailerLite) send to subscribers."""
    now = datetime.now(timezone.utc)
    items = []

    if headlines and headlines.get("items"):
        its = headlines["items"][:8]
        today = now.strftime("%A %-d %B %Y") if os.name != "nt" else now.strftime("%A %d %B %Y")
        li = "".join("<li><a href=\"%s\">%s</a></li>" % (xml_esc(i["url"]), xml_esc(i["title"]))
                     for i in its)
        digest_html = ("<p>Today's top world headlines from the Terravium world desk:</p><ul>%s</ul>"
                       "<p><a href=\"%s/world.html\">Read them live on Terravium World</a> — "
                       "updated continuously, every day.</p>") % (li, SITE)
        items.append("""    <item>
      <title>The Terravium Daily — %s</title>
      <link>%s/world.html</link>
      <guid isPermaLink="false">%s#daily-%s</guid>
      <pubDate>%s</pubDate>
      <description>%s</description>
      <category>World News</category>
    </item>""" % (xml_esc(today), SITE, SITE, now.strftime("%Y-%m-%d"),
                  format_datetime(now), xml_esc(digest_html)))

    for p in parse_posts():
        items.append("""    <item>
      <title>%s</title>
      <link>%s</link>
      <guid>%s</guid>
      <pubDate>%s</pubDate>
      <description>%s</description>
      <category>%s</category>
    </item>""" % (xml_esc(p["title"]), xml_esc(p["link"]), xml_esc(p["link"]),
                  rfc822(p["pub"]), xml_esc(p["desc"]), xml_esc(p["cat"])))

    feed = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Terravium — World News, Recipes, Stories &amp; Essays</title>
    <link>%s</link>
    <description>Live world news updated daily, famous food recipes cooked step by step, and essays on travel, culture, technology and cities — from every corner of the earth.</description>
    <language>en</language>
    <lastBuildDate>%s</lastBuildDate>
    <ttl>60</ttl>
    <atom:link href="%s/rss.xml" rel="self" type="application/rss+xml"/>
%s
  </channel>
</rss>
""" % (SITE, format_datetime(now), SITE, "\n".join(items))
    with open(os.path.join(ROOT, "rss.xml"), "w", encoding="utf-8") as f:
        f.write(feed)
    return len(items)


def bake_masthead_date():
    """Keep the topbar date fresh in the HTML source (no-JS fallback);
    the client-side script shows each visitor their local date anyway."""
    today = datetime.now().strftime('%A, %-d %B %Y')
    n = 0
    for f in glob.glob(os.path.join(ROOT, '*.html')):
        s = open(f, encoding='utf-8').read()
        s2, k = re.subn(r'(<time id="todayDate">)[^<]*(</time>)', r'\g<1>' + today + r'\g<2>', s)
        if k:
            open(f, 'w', encoding='utf-8').write(s2)
            n += 1
    return n


def build_sitemap():
    """Regenerate sitemap.xml from the actual files — so posts uploaded by the
    owner enter the sitemap automatically within a day."""
    pages = ["index.html", "world.html", "news.html", "blogs.html"] + \
            [os.path.basename(p) for p in sorted(glob.glob(os.path.join(ROOT, "*.html")))
             if os.path.basename(p) not in STATIC_PAGES] + \
            ["faq.html", "contact.html", "privacy.html", "terms.html"]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for pg in pages:
        loc = SITE + "/" + ("" if pg == "index.html" else pg)
        daily = pg in ("index.html", "world.html", "news.html")
        sm.append("  <url>")
        sm.append("    <loc>%s</loc>" % loc)
        sm.append("    <changefreq>daily</changefreq>" if daily else "    <changefreq>weekly</changefreq>")
        sm.append("    <priority>1.0</priority>" if pg == "index.html"
                  else ("    <priority>0.9</priority>" if pg in ("world.html", "news.html")
                        else "    <priority>0.8</priority>"))
        sm.append("  </url>")
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")
    return len(pages)


def card_html(it, src):
    media = ""
    if it.get("img"):
        media = ('<a class="live-card-media" href="%s" target="_blank" rel="noopener noreferrer" '
                 'tabindex="-1" aria-hidden="true"><img src="%s" alt="" loading="lazy"></a>'
                 % (esc(it["url"]), esc(it["img"])))
    time_ = esc(it.get("time", ""))
    return ('<article class="live-card">%s<div class="live-card-body">'
            '<div class="live-card-meta"><span class="live-src">%s</span>%s</div>'
            '<h3><a href="%s" target="_blank" rel="noopener noreferrer">%s</a></h3>%s</div></article>'
            % (media, esc(src),
               ("<time class=\"live-time\">%s</time>" % time_) if time_ else "",
               esc(it["url"]), esc(it["title"]),
               ("<p class=\"live-card-desc\">%s</p>" % esc(it["desc"])) if it.get("desc") else ""))


def strip_item(it, src):
    time_ = esc(it.get("time", ""))
    return ('<a class="live-strip-item" href="%s" target="_blank" rel="noopener noreferrer">'
            '<span class="live-src">%s</span><span class="live-strip-title">%s</span>%s</a>'
            % (esc(it["url"]), esc(src), esc(it["title"]),
               ("<time class=\"live-time\">%s</time>" % time_) if time_ else ""))


def tfa_html(t):
    media = ""
    if t.get("img"):
        media = ('<a class="live-tfa-media" href="%s" target="_blank" rel="noopener noreferrer" '
                 'tabindex="-1" aria-hidden="true"><img src="%s" alt="" loading="lazy"></a>'
                 % (esc(t["url"]), esc(t["img"])))
    return ('<article class="live-tfa">%s<div class="live-tfa-body">'
            '<div class="live-card-meta"><span class="live-src">Wikipedia</span>'
            '<time class="live-time">today</time></div>'
            '<h3><a href="%s" target="_blank" rel="noopener noreferrer">%s</a></h3>'
            '<p class="live-tfa-extract">%s</p>'
            '<p style="margin:0"><a class="btn btn-ghost btn-sm" href="%s" target="_blank" '
            'rel="noopener noreferrer">Read today\u2019s pick →</a></p></div></article>'
            % (media, esc(t["url"]), esc(t["title"]), esc(t["extract"]), esc(t["url"])))


def bake(page, key, html):
    path = os.path.join(ROOT, page)
    src = open(path, encoding="utf-8").read()
    start = "<!--TERRAVIUM:bake:%s:start-->" % key
    end = "<!--TERRAVIUM:bake:%s:end-->" % key
    if start not in src or end not in src:
        return False
    pre, rest = src.split(start, 1)
    _, post = rest.split(end, 1)
    open(path, "w", encoding="utf-8").write(pre + start + "\n" + html + end + post)
    return True


def main():
    data = build_live_data()
    wrote, baked = [], []

    if data["headlines"] or data["wiki"]:
        snap = json.dumps(data, ensure_ascii=False)
        snap = snap.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        snap = snap.replace("</", "<\\/")   # safe inside a <script> tag
        with open(os.path.join(ROOT, "js", "live-data.js"), "w", encoding="utf-8") as f:
            f.write("/* Terravium live snapshot — regenerated automatically every day. */\n")
            f.write("window.TERRAVIUM_SNAPSHOT = " + snap + ";\n")
        wrote.append("js/live-data.js")

    h = data["headlines"]
    if h:
        items = h["items"]
        for key, (page, count) in BAKE_TARGETS.items():
            block = "\n      ".join(strip_item(it, h["source"]) for it in items[:count]) \
                if key == "index-strip" else \
                "\n      ".join(card_html(it, h["source"]) for it in items[:count])
            if bake(page, key, block):
                baked.append("%s (%d items)" % (page, min(count, len(items))))

    if data["wiki"] and data["wiki"].get("tfa"):
        if bake("blogs.html", "blogs-tfa", tfa_html(data["wiki"]["tfa"])):
            baked.append("blogs.html (today's read)")

    try:
        n_items = build_rss(h)
        wrote.append("rss.xml (%d items)" % n_items)
    except Exception as e:
        print("  rss.xml          : FAILED (%s)" % e)

    try:
        n_pages = build_sitemap()
        wrote.append("sitemap.xml (%d urls)" % n_pages)
    except Exception as e:
        print("  sitemap.xml      : FAILED (%s)" % e)

    try:
        n_dates = bake_masthead_date()
        wrote.append("topbar date on %d pages" % n_dates)
    except Exception as e:
        print("  sitemap.xml      : FAILED (%s)" % e)

    print("Terravium daily refresh report")
    print("  headlines source :", (h or {}).get("source", "FAILED"))
    print("  wiki feed        :", "ok" if data["wiki"] else "FAILED")
    print("  wrote            :", ", ".join(wrote) or "nothing")
    print("  baked            :", "; ".join(baked) or "nothing")
    return 0 if (h or data["wiki"]) else 1


if __name__ == "__main__":
    sys.exit(main())
