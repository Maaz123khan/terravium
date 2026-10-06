/* ============================================================
   TERRAVIUM — /api/live  (Vercel serverless function)
   Same JSON shape as server.py's /api/live, so js/main.js works
   unchanged on Vercel. Zero dependencies (Node 18+ fetch).
   ============================================================ */
'use strict';

var HEADLINE_FEEDS = [
  ['BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml'],
  ['Google News', 'https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en']
];
var WIKI_FEEDS = [
  'https://api.wikimedia.org/feed/v1/wikipedia/en/featured/',
  'https://en.wikipedia.org/api/rest_v1/feed/featured/'
];

var ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

function decodeEntities(s) {
  return String(s || '').replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, function (m, e) {
    if (e[0] === '#') {
      var code = (e[1] === 'x' || e[1] === 'X') ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return String.fromCharCode(code);
    }
    return ENTITIES[e.toLowerCase()] || m;
  });
}

function stripTags(s) {
  return decodeEntities(String(s || '').replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
}

function clip(s, n) {
  s = String(s || '');
  if (s.length <= n) return s;
  return s.slice(0, n - 1).replace(/\s+\S*$/, '').trim() + '\u2026';
}

function relTime(d) {
  var s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (s < 60) return 'just now';
  var m = Math.floor(s / 60);
  if (m < 60) return m + 'm ago';
  var h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}

function parseRss(xml) {
  var items = [];
  (xml.match(/<item[\s\S]*?<\/item>/gi) || []).forEach(function (b) {
    function pick(tag) {
      var m = b.match(new RegExp('<' + tag + '[^>]*>([\\s\\S]*?)</' + tag + '>', 'i'));
      if (!m) return '';
      var t = m[1].trim();
      var c = t.match(/^<!\[CDATA\[([\s\S]*)\]\]>$/);
      if (c) t = c[1];
      return t;
    }
    var title = decodeEntities(pick('title'));
    var gm = title.match(/^(.{20,})\s-\s[^-]{2,28}$/);
    if (gm) title = gm[1].trim();
    var link = pick('link');
    if (!title || !link) return;
    var desc = clip(stripTags(pick('description')), 140);
    var img = '';
    var im = b.match(/<media:thumbnail[^>]*\surl="([^"]+)"/i);
    if (im) img = im[1];
    var date = '', t = '';
    var d = pick('pubDate') ? new Date(pick('pubDate')) : null;
    if (d && !isNaN(d.getTime())) {
      date = d.toISOString().replace(/\.\d{3}Z$/, 'Z');
      t = relTime(d);
    }
    items.push({ title: title, url: link, desc: desc, img: img, date: date, time: t });
  });
  return items;
}

async function fetchHeadlines() {
  for (var i = 0; i < HEADLINE_FEEDS.length; i++) {
    var name = HEADLINE_FEEDS[i][0], url = HEADLINE_FEEDS[i][1];
    try {
      var r = await fetch(url, { headers: { 'User-Agent': 'TerraviumBot/1.0 (live world news module)' } });
      if (!r.ok) continue;
      var items = parseRss(await r.text());
      if (items.length) return { source: name, items: items.slice(0, 20) };
    } catch (e) { /* try next feed */ }
  }
  return null;
}

function pageUrl(x) {
  try { return x.content_urls.desktop.page; } catch (e) { return 'https://en.wikipedia.org'; }
}

async function fetchWiki() {
  var now = new Date();
  var path = now.getUTCFullYear() + '/' + String(now.getUTCMonth() + 1).padStart(2, '0') + '/' + String(now.getUTCDate()).padStart(2, '0');
  for (var i = 0; i < WIKI_FEEDS.length; i++) {
    try {
      var r = await fetch(WIKI_FEEDS[i] + path, { headers: { 'User-Agent': 'TerraviumBot/1.0 (live world news module)' } });
      if (!r.ok) continue;
      var w = await r.json();
      var out = {};
      out.news = (w.news || []).slice(0, 8).map(function (n) {
        return {
          text: clip(stripTags(n.story || ''), 230),
          url: (n.links && n.links[0]) ? pageUrl(n.links[0]) : 'https://en.wikipedia.org/wiki/Portal:Current_events'
        };
      });
      out.otd = (w.onthisday || []).slice(0, 40).map(function (n) {
        var pages = n.pages || [];
        return {
          year: n.year,
          text: clip(stripTags(n.text || ''), 210),
          url: pages.length ? pageUrl(pages[0]) : 'https://en.wikipedia.org'
        };
      });
      var im = w.image || {};
      var desc = im.description;
      if (Array.isArray(desc)) desc = desc.join(' ');
      var img = (im.thumbnail && im.thumbnail.source) || (im.image && im.image.source) || '';
      out.potd = null;
      if (img) {
        var title = String(im.title || 'Picture of the day').replace(/^File:/, '')
          .replace(/\.(jpe?g|png|gif|tiff?|webm|ogg|svg)$/i, '').replace(/_/g, ' ');
        out.potd = {
          img: img, title: title, desc: clip(desc || '', 170),
          url: im.file_page || 'https://commons.wikimedia.org/wiki/Main_Page'
        };
      }
      var t = w.tfa || {};
      out.tfa = null;
      if (t.titles) {
        out.tfa = {
          title: t.titles.normalized || 'Today\u2019s featured article',
          extract: clip(t.extract || '', 300),
          img: (t.thumbnail && t.thumbnail.source) || '',
          url: pageUrl(t)
        };
      }
      out.mostread = (((w.mostread || {}).articles) || []).slice(0, 10).map(function (a) {
        return { title: (a.titles && a.titles.normalized) || a.title || '', url: pageUrl(a) };
      });
      return out;
    } catch (e) { /* try next feed */ }
  }
  return null;
}

module.exports = async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=0, s-maxage=600, stale-while-revalidate=600');
  try {
    var headlines = await fetchHeadlines();
    var wiki = await fetchWiki();
    res.statusCode = 200;
    res.end(JSON.stringify({ ts: Date.now(), headlines: headlines, wiki: wiki }));
  } catch (e) {
    res.statusCode = 200;
    res.end(JSON.stringify({ ts: Date.now(), headlines: null, wiki: null }));
  }
};
