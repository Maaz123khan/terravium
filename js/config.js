/* ============================================================
   TERRAVIUM — SITE CONFIGURATION
   ============================================================
   The contact + newsletter forms use FormSubmit
   (https://formsubmit.co) — a delivery service that needs NO
   ACCOUNT. The inbox address below IS the account.

   One-time activation: send yourself one test message from the
   contact page. FormSubmit emails the owner an "Activate Form"
   button — click it once, and every future message arrives
   directly in that inbox.

   >>> BUYERS: replace hello@terravium.site below (both lines)
   with your own email address. That is the only change needed.
   ============================================================ */
(function () {
  'use strict';
  window.TERRAVIUM_CONFIG = {

    /* Contact form → messages land directly in this inbox. */
    CONTACT_ENDPOINT: 'https://formsubmit.co/ajax/hello@terravium.site',

    /* Newsletter → subscribers' email addresses arrive in the same
       inbox (subject: "[Terravium] Newsletter subscribe") so your
       daily-dispatch list starts building from day one.
       Want fully automated daily emails? Create a free MailerLite
       account and replace this with your MailerLite form endpoint
       (see README.md — 15 minutes). */
    NEWSLETTER_ENDPOINT: 'https://formsubmit.co/ajax/hello@terravium.site',

    /* How the subscribe request is sent:
       'json' → POST {"email": …}   (FormSubmit, MailerLite, Formspree)
       'form' → POST email=…        (many classic endpoints)
       'nav'  → plain form post, page navigates (works with any service) */
    NEWSLETTER_MODE: 'json'
  };
})();
