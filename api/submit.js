/* ============================================================
   TERRAVIUM — /api/submit  (Vercel serverless function)
   Same-origin relay to FormSubmit, mirroring server.py: lets the
   contact + newsletter forms work even where browsers can't call
   third-party services directly. Fixed target, honeypot guarded.
   ============================================================ */
'use strict';

var FORM_TARGET = 'https://formsubmit.co/ajax/hello@terravium.site';

module.exports = async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') {
    res.statusCode = 405;
    return res.end(JSON.stringify({ ok: false, error: 'POST only' }));
  }
  var body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body || '{}'); } catch (e) { body = null; }
  }
  if (!body || typeof body !== 'object') {
    res.statusCode = 400;
    return res.end(JSON.stringify({ ok: false, error: 'invalid body' }));
  }
  if (String(body._honey || '').trim()) {
    /* spam bot filled the honeypot → pretend success, discard silently */
    return res.end(JSON.stringify({ success: 'true', dropped: 'honeypot' }));
  }
  try {
    var r = await fetch(FORM_TARGET, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body)
    });
    var text = await r.text();
    res.statusCode = r.status;
    res.end(text || '{"success":"true"}');
  } catch (e) {
    res.statusCode = 502;
    res.end(JSON.stringify({ ok: false, error: 'relay unavailable' }));
  }
};
