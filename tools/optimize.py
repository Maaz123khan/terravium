#!/usr/bin/env python3
"""
Terravium page optimizer — run after any CSS/JS/content change:
    python3 tools/optimize.py

What it does (all idempotent — safe to run again and again):
  1. Generates WebP variants of every images/*.jpg story photo
     (-sm 280w for thumbs, -md 760w for cards, -lg 1600w for heroes).
     Original JPGs stay (used by og:image, Twitter cards and Pinterest pins).
  2. Minifies css/style.css and js/main.js (sources stay untouched).
  3. Inlines the minified CSS into every page (kills the render-blocking
     stylesheet request) and preloads the two above-fold fonts.
  4. Removes the Google Fonts links (fonts are self-hosted in /fonts now).
  5. Removes the translate <script> tag (main.js lazy-loads it on demand,
     saving ~99 KB on first load).
  6. Points pages at js/main.min.js.
  7. Swaps <img> sources to right-sized WebP variants (by their width attr)
     and gives above-the-fold heroes fetchpriority="high".
"""

import os
import re
import glob
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

WEBP_SIZES = {"sm": 280, "md": 640, "lg": 1440}
JPEG_QUALITY = 82


# ---------------------------------------------------------------- images
def make_webp():
    made = 0
    for jpg in sorted(glob.glob("images/*.jpg")):
        base = jpg[:-4]
        try:
            im = Image.open(jpg).convert("RGB")
        except Exception as e:
            print("  ! could not open %s (%s)" % (jpg, e))
            continue
        w, h = im.size
        for tag, target in WEBP_SIZES.items():
            out = "%s-%s.webp" % (base, tag)
            if os.path.exists(out):
                continue
            if w <= target:
                tw, th = w, h
            else:
                tw = target
                th = round(h * target / w)
            q = 80 if tag == "sm" else (74 if tag == "md" else 76)
            im.resize((tw, th), Image.LANCZOS).save(out, "WEBP", quality=q, method=6)
            made += 1
    print("  webp variants: %d new files" % made)


# ---------------------------------------------------------------- minify
def minify_css(css):
    css = re.sub(r"/\*[\s\S]*?\*/", "", css)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};:,>])\s*", r"\1", css)
    css = css.replace(";}", "}")
    return css.strip()


def minify_js(js):
    try:
        import rjsmin
        return rjsmin.jsmin(js)
    except ImportError:
        print("  ! rjsmin missing — keeping readable JS")
        return js


def build_minified():
    css = open("css/style.css", encoding="utf-8").read()
    open("css/style.min.css", "w", encoding="utf-8").write(minify_css(css))
    js = open("js/main.js", encoding="utf-8").read()
    open("js/main.min.js", "w", encoding="utf-8").write(minify_js(js))
    print("  minified: css/style.min.css (%d B), js/main.min.js (%d B)"
          % (os.path.getsize("css/style.min.css"), os.path.getsize("js/main.min.js")))


# ---------------------------------------------------------------- pages
PRELOADS = ('<link rel="preload" as="font" type="font/woff2" href="fonts/fraunces-600.woff2" crossorigin>\n'
            '<link rel="preload" as="font" type="font/woff2" href="fonts/inter-var.woff2" crossorigin>')

GOOGLE_FONT_LINKS = [
    re.compile(r'<link rel="preconnect" href="https://fonts\.googleapis\.com">\n?'),
    re.compile(r'<link rel="preconnect" href="https://fonts\.gstatic\.com"[^>]*>\n?'),
    re.compile(r'<link href="https://fonts\.googleapis\.com/css2[^"]*" rel="stylesheet">\n?'),
]


def patch_img(m):
    tag = m.group(0)
    srcm = re.search(r'src="(images/[^"]+\.(?:jpe?g|png))"', tag)
    if not srcm:
        return tag
    src = srcm.group(1)
    if ".webp" in src or "-sm." in src or "-md." in src or "-lg." in src:
        return tag
    wm = re.search(r'width="(\d+)"', tag)
    w = int(wm.group(1)) if wm else 800
    base = re.sub(r"\.(jpe?g|png)$", "", src, flags=re.I)
    if w <= 300:
        new = base + "-sm.webp"
    elif w <= 900:
        new = base + "-md.webp"
    else:
        new = base + "-lg.webp"
    tag = tag.replace('src="%s"' % src, 'src="%s"' % new)
    # above-the-fold heroes: highest priority, never lazy
    if w >= 1000:
        tag = re.sub(r'\s+loading="lazy"', "", tag)
        if "fetchpriority" not in tag:
            tag = tag.replace("<img ", '<img fetchpriority="high" decoding="async" ', 1)
    return tag


def patch_page(path, mincss):
    s = open(path, encoding="utf-8").read()
    orig = s

    # 1. drop Google Fonts links
    for rx in GOOGLE_FONT_LINKS:
        s = rx.sub("", s)

    # 2. drop the translate <script> (lazy-loaded on demand now)
    s = s.replace('<script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit" defer></script>\n', "")

    # 3. inline the CSS (or refresh the previously-inlined copy) — font
    #    preloads are stripped first so they are never duplicated
    s = re.sub(r'<link rel="preload" as="font"[^>]*>\n?', "", s)
    link = '<link rel="stylesheet" href="css/style.css">'
    if link in s:
        s = s.replace(link, PRELOADS + "\n<style data-tv-inline>" + mincss + "</style>")
    else:
        s = re.sub(r'<style data-tv-inline>[\s\S]*?</style>',
                   lambda m: "<style data-tv-inline>" + mincss + "</style>", s, count=1)
        s = s.replace("<style data-tv-inline>",
                      PRELOADS + "\n<style data-tv-inline>", 1)

    # 4. minified JS
    s = s.replace('src="js/main.js"', 'src="js/main.min.js"')

    # 5. right-sized WebP images + LCP priority
    s = re.sub(r"<img\b[^>]*>", patch_img, s)

    # 6. heading order: hero-mini cards must be h2 (page h1 -> h3 would skip)
    if "hero-mini" in s:
        s = re.sub(r'(<a class="hero-mini"[^>]*>(?:(?!</a>).)*?)<h3>((?:(?!</a>).)*?)</h3>',
                   r"\1<h2>\2</h2>", s, flags=re.S)

    # 7. heading order: drawer section labels start the page — use h2, not h3
    s = s.replace('<div class="drawer-block drawer-contact">\n    <h3>Get in touch</h3>',
                  '<div class="drawer-block drawer-contact">\n    <h2>Get in touch</h2>')
    s = s.replace('<h3>Follow Terravium</h3>', '<h2>Follow Terravium</h2>')

    # 8. absolute social/structured-data image URLs
    s = re.sub(r'(og:image|twitter:image)" content="images/', r'\1" content="https://terravium.site/images/', s)

    def abs_ld(m):
        return m.group(0).replace('"images/', '"https://terravium.site/images/')
    s = re.sub(r'<script type="application/ld\+json">[\s\S]*?</script>', abs_ld, s)

    if s != orig:
        open(path, "w", encoding="utf-8").write(s)
        return True
    return False


def heading_report():
    """List pages whose heading sequence skips levels (h1 -> h3 etc.)."""
    bad = []
    for f in sorted(glob.glob("*.html")):
        s = open(f, encoding="utf-8").read()
        s = re.sub(r"<script[\s\S]*?</script>", "", s)  # ignore JS template strings
        levels = [int(m.group(1)[1]) for m in re.finditer(r"<(h[1-6])\b", s)]
        if not levels:
            continue
        prev = levels[0]  # the first heading may be any level
        for lv in levels[1:]:
            if lv - prev > 1:
                bad.append((f, prev, lv))
                break
            prev = lv
    return bad


def main():
    print("Terravium optimizer")
    make_webp()
    build_minified()
    mincss = open("css/style.min.css", encoding="utf-8").read()
    changed = 0
    for f in sorted(glob.glob("*.html")):
        if patch_page(f, mincss):
            changed += 1
    print("  pages updated: %d/%d" % (changed, len(glob.glob("*.html"))))
    bad = heading_report()
    print("  heading-order issues:", bad if bad else "NONE ✓")


if __name__ == "__main__":
    main()
