# Terravium — World Magazine

**Lightweight • No framework • No database • Easy to deploy • SEO-ready • Responsive • Low maintenance**

A complete, production-ready digital magazine: **25 standalone HTML pages** (news,
essays, recipes, features), live BBC world headlines, a 105-language switcher,
Pinterest-ready share buttons, an RSS feed, and a daily auto-update pipeline.
No frameworks, no build step, no databases — pure HTML/CSS/JS that scores highly
on PageSpeed and deploys anywhere static hosting exists.

> **⚠️ Demo content notice:** the 16 stories, their photos, and the "Terravium Desk"
> byline are **sample content for demonstration**. Replace them with your own
> content and licensed photography before commercial use (see §10).

**Buyer quick guide:** run it (§1) · deploy it (§2) · set your contacts + domain
(§3) · understand the content system (§4) · how live news works (§5) · replace the
demo content (§10).

---

## 1. Quick start (local)

```bash
cd terravium
python3 server.py        # → http://localhost:8000  (adds the /api/live news proxy)
```

Any other static server works too (`npx serve`, `python3 -m http.server`, VS Code
Live Server…). The site is fully functional either way — `server.py` just adds
same-origin proxies so live news and the contact relay work in strict environments.

## 2. Deploy to Vercel (free tier, ~5 minutes)

1. Create a free GitHub account → **New repository** → name it `terravium` → Public.
2. **Add file → Upload files** → drag everything in this folder → **Commit**.
3. Create a free Vercel account → **Continue with GitHub** → **Add New → Project** →
   Import the repo → leave all settings as-is → **Deploy**.
4. Live in ~1 minute at `https://your-project.vercel.app`.

The `api/` folder (two tiny serverless functions) is auto-detected by Vercel:

| Function | Purpose |
|---|---|
| `api/live.js` | Same-origin live-news proxy (BBC World + Wikipedia) |
| `api/submit.js` | Same-origin relay for the contact/newsletter forms |

GitHub Pages and Netlify also work — the site degrades gracefully to in-browser
fetching without the functions.

## 3. Make it yours (5-minute checklist)

| What | Where | Currently |
|---|---|---|
| Contact email | `js/config.js` (2 lines), plus every page's header/footer, `contact.html`, `privacy.html`, `terms.html`, `js/main.js` (mailto + Gmail buttons) | `hello@terravium.site` (placeholder) |
| Phone | same places | `+92 300 0000000` (placeholder) |
| WhatsApp | same places | `https://wa.me/923000000000` (placeholder) |
| Domain | every page's canonical/og:url, `sitemap.xml`, `robots.txt`, `rss.xml`, `tools/refresh_live.py` (`SITE`), `js/main.js` | `https://terravium.site` |

Swap everything at once:

```bash
grep -rl 'terravium.site' . | xargs sed -i 's|terravium.site|YOUR-DOMAIN.com|g'
grep -rl 'hello@terravium.site' . | xargs sed -i 's|hello@terravium.site|you@YOUR-DOMAIN.com|g'
python3 tools/refresh_live.py    # regenerates rss.xml + sitemap cleanly
```

Colours/fonts: CSS variables at the top of `css/style.css` (`--accent`, `--bg`,
`--ink`, font faces in `/fonts`). Photos: drop replacements into `images/`.

## 4. Content workflow

**The site updates itself.** The GitHub Action (`.github/workflows/daily-update.yml`)
refreshes the live-news sections, `rss.xml`, `sitemap.xml` and the daily snapshot
every morning — no manual work. (Note: GitHub's web uploader skips dot-folders, so
create this file via *Add file → Create new file* → name it
`.github/workflows/daily-update.yml` → paste the contents → commit.)

**Add a story:** copy any post page (e.g. `reading-slowly.html`) to a new
keyword-slug file, edit title/meta/body/hero, then add an entry to `posts.json` —
the story automatically appears on the homepage and in the news/blogs feeds
(`js/main.js` injects cards from the manifest). Full recipe in §7.

**Contact/newsletter forms:** zero-account FormSubmit — the inbox address in
`js/config.js` is the account. First submission triggers a one-time
"Activate Form" email; click it once and messages flow to the inbox forever.
Swap in MailerLite (free) later for automated daily newsletter sends from
`rss.xml` — instructions in §8.

## 5. How the live-news system works

The world-news sections (homepage strip, News page, World Live) never show an
empty state — they load through a **4-layer fallback chain**, in this order:

1. **`/api/live`** — same-origin proxy (`server.py` locally, `api/live.js` on
   Vercel). Server-side fetch of BBC World + Google News + the Wikimedia daily
   feed, so it works even where browsers block third-party APIs.
2. **In-browser direct fetch** — if no proxy exists (e.g. GitHub Pages), the
   browser fetches the same feeds directly.
3. **`js/live-data.js`** — a JSON snapshot baked into the repo (refreshed daily).
4. **Baked HTML** — the daily refresh also writes the latest headlines directly
   into the page HTML, so even no-JavaScript visitors see fresh news.

**The daily update workflow** (fully automatic after setup):
`.github/workflows/daily-update.yml` runs at 01:17 UTC every day →
`tools/refresh_live.py` re-fetches all feeds → rewrites `js/live-data.js`,
`rss.xml` (daily digest, 17 items), `sitemap.xml` (rebuilt from the actual
files), the baked headline sections, and the masthead date on every page →
commits and pushes → Vercel (if connected) redeploys automatically.
It can also be triggered manually from the repo's **Actions** tab.
*(Note: GitHub's web uploader skips dot-folders — create the workflow file via
"Add file → Create new file" → `.github/workflows/daily-update.yml` → paste.)*

## 6. File map

```
terravium/
├── index.html … terms.html     25 public pages (16 are full SEO stories)
├── read.html                   Live-story reader (noindex)
├── posts.json                  Story manifest → feeds homepage/news/blogs cards
├── css/style.css               Design system (source) · style.min.css (generated)
├── js/main.js                  All behaviour · main.min.js (generated, pages use this)
├── js/config.js                Endpoints — the one file buyers edit first
├── js/live-data.js             Daily news snapshot (regenerated by the Action)
├── fonts/                      Self-hosted Fraunces + Inter (woff2)
├── images/                     JPG originals (og:/Pinterest) + WebP variants
├── api/                        Vercel functions: live.js, submit.js
├── server.py                   Local dev server + same-origin proxies
├── tools/                      refresh_live.py (daily bake) · optimize.py (minify/
│                               WebP/inline) · live_sources.py (news sources)
├── .github/workflows/          Daily auto-update Action
├── sitemap.xml · robots.txt · rss.xml · vercel.json · site.webmanifest
```

## 7. Adding a story (5-step recipe)

1. Copy a post page to a keyword slug, e.g. `best-museums-europe.html`.
2. Edit `<title>` (≤60 chars, ends `| Terravium`), meta description (120–158 chars),
   `og:url`, `article:published_time`, canonical, the JSON-LD blocks, headline,
   standfirst, byline, date, hero image, body. One H1 → H2s → H3s.
3. Add the photo to `images/` (and run `python3 tools/optimize.py` to make WebP
   variants) — point the hero `<img>` at the `-lg.webp`, keep the JPG in
   `data-pin-media` (Pinterest) and `og:image`.
4. Add a card in `news.html` (or `blogs.html`) + homepage latest grid, or simply
   add an entry to `posts.json` and the feeds pick it up automatically.
5. Link it into neighbours' "Newer/Older story" pagers and add the URL to
   `sitemap.xml` (or wait for the daily Action to rebuild the sitemap).

## 8. Automated daily newsletter (optional)

1. Free MailerLite account → create an email-only embedded form → copy its
   submissions URL into `NEWSLETTER_ENDPOINT` in `js/config.js`.
2. Campaigns → Create → **RSS campaign** → feed `https://YOUR-DOMAIN/rss.xml` →
   schedule daily → activate. The Action refreshes `rss.xml` every morning;
   MailerLite mails it to every subscriber automatically.

## 9. Performance & SEO (already built in)

- Zero render-blocking requests (minified CSS inlined per page, self-hosted
  preloaded fonts), right-sized lazy WebP images, `fetchpriority` heroes,
  lazy-loaded Google Translate (105 languages, in the top bar).
- Per-page SEO: unique titles/descriptions, canonical, Open Graph + Twitter
  cards, Article/NewsArticle + BreadcrumbList JSON-LD, FAQPage schema,
  `sitemap.xml` (auto-rebuilt daily), `rss.xml` daily digest.
- After editing `css/style.css` or `js/main.js`, run
  **`python3 tools/optimize.py`** (re-minifies and refreshes the inlined copies),
  then re-upload the changed files.

## 10. Demo content — what the buyer must replace

Everything in the repository runs, but the following is **sample/demo content**
provided to demonstrate the product — it is not proprietary editorial content:

| Item | Where | Action before commercial use |
|---|---|---|
| The 16 stories/essays/recipes | the 16 `*.html` post pages + cards in `news.html` / `blogs.html` / `index.html` | Replace with your own content |
| Story photos | `images/*.jpg` + generated `-sm/-md/-lg.webp` variants | **Demo placeholder imagery — verify licensing or replace with your own photography** |
| "Terravium Desk — Editorial Team" byline | every post page, `posts.json`, JSON-LD | Replace with your real author(s) |
| Contact details | `js/config.js`, page headers/footers, `contact.html`, `privacy.html`, `terms.html` | Placeholders: `hello@terravium.site`, `+92 300 0000000`, `wa.me/923000000000` |
| Domain | canonicals, `sitemap.xml`, `robots.txt`, `rss.xml`, `tools/refresh_live.py`, `js/config.js` docs | `https://terravium.site` — swap to your domain (one command, §3) |
| FAQ answers | `faq.html` | Review/edit to match your policies |

Live news headlines are fetched from public feeds (BBC World, Google News,
Wikimedia) at runtime — they are not bundled content and need no replacement.

## 11. Security & privacy

- No API keys, no secrets, no databases, no user accounts anywhere.
- Contact forms use honeypots + validation + an automatic fallback screen
  (Gmail compose / email app / WhatsApp / copy) — no message is ever lost.
- `privacy.html` and `terms.html` describe exactly what the site does.
- Update their contact/jurisdiction lines when you add your own details.

---

© 2026 Terravium Digital. Sample content is provided for demonstration —
replace it with your own before commercial use.
