'use strict';

// Runs only after the user clicks the extension icon (activeTab). It scans on
// request, fills on request, and does nothing else — in particular it never
// clicks anything, never calls form.submit(), and never sends a key that could
// submit a form. Pressing send stays a human act.

(() => {
  if (window.__hetFillerReady) return;      // re-injection on every popup open
  window.__hetFillerReady = true;

  const MARK = 'data-het-field';
  let counter = 0;

  /**
   * Assign values the way the page's own JavaScript expects.
   *
   * Frameworks track their inputs through the native value setter; assigning
   * `el.value` directly updates the DOM but leaves React/Vue state stale, so
   * the field looks filled and submits empty. Going through the prototype
   * setter and then dispatching input/change avoids that.
   */
  function setValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function setSelect(el, value) {
    const wanted = String(value).trim().toLowerCase();
    const option = [...el.options].find((o) =>
      o.value.trim().toLowerCase() === wanted ||
      o.textContent.trim().toLowerCase() === wanted) ||
      [...el.options].find((o) =>
        o.textContent.trim().toLowerCase().includes(wanted));
    if (!option) return false;
    el.value = option.value;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  /** Dates: HTML date inputs only accept YYYY-MM-DD. */
  function coerceDate(el, value) {
    if (el.type !== 'date') return value;
    const trimmed = String(value).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
    const dmy = trimmed.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (dmy) {
      const [, d, m, y] = dmy;
      return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
    }
    return null;                            // unparseable: leave the field be
  }

  function highlight(el, ok) {
    const previous = el.style.outline;
    el.style.outline = ok ? '2px solid #1a7f47' : '2px solid #b4530a';
    el.style.outlineOffset = '1px';
    setTimeout(() => { el.style.outline = previous; }, 2500);
  }

  function scan(message) {
    document.querySelectorAll(`[${MARK}]`).forEach(
      (el) => el.removeAttribute(MARK));

    const plan = buildPlan(
      document, message.profile, FIELD_DEFS,
      { NEVER_FILL, NEVER_FILL_TYPES },
      { overrides: message.overrides, includeSensitive: message.includeSensitive },
    );

    return plan.map((item) => {
      const id = `f${++counter}`;
      item.el.setAttribute(MARK, id);
      return {
        id,
        key: item.key,
        label: item.label,
        value: item.value,
        score: item.score,
        why: item.why.join(', '),
        signature: item.signature,
        sensitive: item.sensitive,
        overridden: item.overridden,
        tag: item.el.tagName.toLowerCase(),
        fieldName: item.el.getAttribute('name') || item.el.id || '',
      };
    });
  }

  function fill(message) {
    let filled = 0;
    const skipped = [];
    for (const item of message.items) {
      const el = document.querySelector(`[${MARK}="${item.id}"]`);
      if (!el) { skipped.push(`${item.label}: alan kayboldu`); continue; }

      let ok = true;
      if (el.tagName === 'SELECT') {
        ok = setSelect(el, item.value);
        if (!ok) skipped.push(`${item.label}: listede eşleşen seçenek yok`);
      } else {
        const value = coerceDate(el, item.value);
        if (value === null) {
          ok = false;
          skipped.push(`${item.label}: tarih biçimi çevrilemedi`);
        } else {
          setValue(el, value);
        }
      }
      highlight(el, ok);
      if (ok) filled += 1;
    }
    return { filled, skipped };
  }

  // Exposed so the test page can exercise the real functions rather than a
  // copy of them; the fiddly parts (date coercion, option matching) are
  // exactly the ones that fail quietly.
  window.__hetFiller = { setValue, setSelect, coerceDate, scan, fill, MARK };

  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((message, _sender, respond) => {
      try {
        if (message.type === 'scan') respond({ ok: true, plan: scan(message) });
        else if (message.type === 'fill') respond({ ok: true, ...fill(message) });
        else respond({ ok: false, error: 'bilinmeyen istek' });
      } catch (error) {
        respond({ ok: false, error: String(error) });
      }
      return true;
    });
  }
})();
