#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Terravium — static site server with a built-in live-news API.

  · Serves every file in this folder (HTML/CSS/JS/images).
  · GET /api/live  → fresh world news fetched server-side (BBC World RSS →
    Google News fallback, plus the Wikimedia daily feed), cached 10 minutes.

Because /api/live is same-origin, it works even in restricted preview frames
where the browser cannot call third-party APIs directly — that's what keeps
the site showing "live" instead of "offline".

Run:  python3 server.py          (port 8000)
      PORT=9000 python3 server.py
"""
import html as html_lib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from tools.live_sources import build_live_data  # noqa: E402

CACHE_TTL = 600  # seconds
_cache = {"ts": 0.0, "data": None}
_lock = threading.Lock()

ART_TTL = 900  # seconds — article metadata cache
_art_cache = {}
_art_lock = threading.Lock()


def _meta_tag(text, attr, value):
    """Content of <meta attr="value" ... content="...">, either attribute order."""
    for pat in (
        r'<meta[^>]*?\s%s=["\']%s["\'][^>]*?content=["\']([^"\']*)["\']' % (attr, re.escape(value)),
        r'<meta[^>]*?content=["\']([^"\']*)["\'][^>]*?\s%s=["\']%s["\']' % (attr, re.escape(value)),
    ):
        m = re.search(pat, text, re.I | re.S)
        if m:
            return html_lib.unescape(m.group(1)).strip()
    return ""


def _private_host(host):
    return (not host or host == "localhost" or host.startswith("127.") or host.startswith("10.")
            or host.startswith("192.168.") or host.startswith("169.254.") or host == "::1")


def get_article(url):
    """Fetch a story's public metadata (title/description/image) for the reader page."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or _private_host(parts.hostname):
        return {"ok": False, "error": "unsupported url"}
    with _art_lock:
        hit = _art_cache.get(url)
        if hit and (time.time() - hit[0]) < ART_TTL:
            return hit[1]
    data = {"ok": False, "error": "fetch failed"}
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TerraviumReader/1.0; +https://terravium.site/)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read(2 * 1024 * 1024)  # cap at 2 MB
            text = raw.decode(r.headers.get_content_charset() or "utf-8", "replace")
        title = _meta_tag(text, "property", "og:title") or _meta_tag(text, "name", "twitter:title")
        if not title:
            m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            title = html_lib.unescape(m.group(1)).strip() if m else ""
        desc = (_meta_tag(text, "property", "og:description")
                or _meta_tag(text, "name", "description")
                or _meta_tag(text, "name", "twitter:description"))
        image = _meta_tag(text, "property", "og:image") or _meta_tag(text, "name", "twitter:image")
        if image:
            image = urllib.parse.urljoin(url, image)
        site = _meta_tag(text, "property", "og:site_name") or parts.netloc.replace("www.", "")
        published = _meta_tag(text, "property", "article:published_time")
        data = {"ok": True, "url": url, "title": title, "desc": desc,
                "image": image, "site": site, "published": published}
    except Exception as e:
        data = {"ok": False, "error": str(e)}
    with _art_lock:
        _art_cache[url] = (time.time(), data)
    return data


def get_live():
    with _lock:
        if _cache["data"] is not None and (time.time() - _cache["ts"]) < CACHE_TTL:
            return _cache["data"]
    data = build_live_data()  # network calls happen outside the lock
    if data["headlines"] or data["wiki"]:
        with _lock:
            _cache["ts"] = time.time()
            _cache["data"] = data
        return data
    with _lock:
        if _cache["data"] is not None:      # serve stale rather than fail
            return _cache["data"]
    return data


class TerraviumHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # ---------- /api/submit : same-origin form relay ----------
    # The preview frame (and some strict networks) block direct browser calls to
    # third-party services. The browser posts to THIS same-origin endpoint and
    # the server forwards the payload to FormSubmit — exactly like /api/live.
    FORM_TARGET = "https://formsubmit.co/ajax/hello@terravium.site"

    _submit_hits = {}
    _submit_lock = threading.Lock()

    def _allow_submit(self):
        ip = self.client_address[0] if self.client_address else "?"
        now = time.time()
        with TerraviumHandler._submit_lock:
            hits = [t for t in TerraviumHandler._submit_hits.get(ip, []) if now - t < 300]
            if len(hits) >= 8:                      # max 8 submissions / 5 min / IP
                TerraviumHandler._submit_hits[ip] = hits
                return False
            hits.append(now)
            TerraviumHandler._submit_hits[ip] = hits
            if len(TerraviumHandler._submit_hits) > 500:   # keep the table small
                TerraviumHandler._submit_hits = {ip: hits}
            return True

    def _submit_api(self):
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                self._send_json({"ok": False, "error": "invalid json"}, 400)
                return
            if not isinstance(payload, dict):
                self._send_json({"ok": False, "error": "invalid body"}, 400)
                return
            if str(payload.get("_honey", "")).strip():
                # spam bot filled the honeypot → pretend success, discard silently
                self._send_json({"success": "true", "dropped": "honeypot"})
                return
            if not self._allow_submit():
                self._send_json({"ok": False, "error": "too many requests, try later"}, 429)
                return
            req = urllib.request.Request(
                self.FORM_TARGET,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json",
                         "User-Agent": "TerraviumFormRelay/1.0"},
                method="POST")
            body, status = "", 502
            for attempt in (1, 2):                     # one retry — rides out blips
                try:
                    with urllib.request.urlopen(req, timeout=15) as r:
                        body = r.read(64 * 1024).decode("utf-8", "replace") or "{}"
                        status = r.status
                        break
                except Exception as up:
                    body, status = "", getattr(up, "code", None) or 502
                    if attempt == 1:
                        time.sleep(2)
            try:
                self._send_json(json.loads(body or "{}"), status)
            except Exception:
                if 200 <= status < 300:
                    self._send_json({"success": "true", "raw": body[:200]}, status)
                else:
                    self._send_json({"ok": False, "error": "relay unavailable",
                                     "upstream": status}, 502)
        except Exception as e:
            code = getattr(e, "code", None) or 502
            try:
                self._send_json({"ok": False, "error": "relay unavailable", "upstream": code}, 502)
            except Exception:
                pass

    def do_POST(self):
        if self.path.split("?", 1)[0] == "/api/submit":
            self._submit_api()
        else:
            try:
                self.send_error(405, "Method Not Allowed")
            except Exception:
                pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _api(self):
        try:
            self._send_json(get_live())
        except Exception as e:  # pragma: no cover
            try:
                self._send_json({"error": str(e)}, 500)
            except Exception:
                pass

    def _article_api(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        url = (q.get("u") or [""])[0]
        try:
            self._send_json(get_article(url))
        except Exception as e:
            try:
                self._send_json({"ok": False, "error": str(e)}, 500)
            except Exception:
                pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/live":
            self._api()
        elif path == "/api/article":
            self._article_api()
        else:
            super().do_GET()

    def do_HEAD(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/live":
            self._api()
        elif path == "/api/article":
            self._article_api()
        else:
            super().do_HEAD()

    def log_message(self, fmt, *args):  # keep the console readable
        if self.path.startswith("/api"):
            pass  # silent


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), TerraviumHandler)
    print("Terravium running → http://0.0.0.0:%d  (live API at /api/live)" % port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
