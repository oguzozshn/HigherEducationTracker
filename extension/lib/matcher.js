'use strict';

// Deciding which profile item belongs in which input.
//
// Scoring rather than a first-match rule, because forms disagree about where
// they put the truth: some label properly, some only set `name`, some only put
// text in a placeholder. Each signal contributes, the best-scoring profile key
// wins, and anything below THRESHOLD is left alone — an empty field is a much
// smaller problem than a confidently wrong one.

const THRESHOLD = 45;

const WEIGHTS = {
  autocomplete: 100,   // the only signal the page states on purpose
  label: 50,
  name: 45,
  placeholder: 40,
  ariaLabel: 40,
  inputType: 20,
};

// A signal that matches a keyword exactly, end to end, is worth more than one
// that merely contains it: a placeholder reading exactly "Voornaam" says what
// the box is for, while a label mentioning "birth" somewhere could be either
// date or place. Without this bonus no single weak signal clears THRESHOLD,
// and placeholder-only forms — common on portals — go unfilled.
const EXACT_BONUS = 20;

// A multi-word keyword found inside a longer string is nearly as decisive as
// an exact match — "date of birth" buried in "please enter date of birth"
// leaves little room for doubt — so it earns a smaller bonus of its own.
// Single words get none: "birth" alone could be the date or the place.
const PHRASE_BONUS = 10;

function normalise(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[_\-.[\]]+/g, ' ')          // form_field[first-name] -> form field first name
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Visible text of the label bound to an input, if any. */
function labelTextFor(el, doc) {
  const parts = [];
  if (el.id) {
    const byFor = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (byFor) parts.push(byFor.textContent);
  }
  const wrapping = el.closest('label');
  if (wrapping) parts.push(wrapping.textContent);
  if (!parts.length) {
    // Fall back to whatever the surrounding cell or row says.
    const container = el.closest('td, th, .form-group, .field, li, p, div');
    if (container && container.textContent && container.textContent.length < 200) {
      parts.push(container.textContent);
    }
  }
  return normalise(parts.join(' '));
}

function describeInput(el, doc) {
  // autocomplete is NOT put through normalise(): that collapses hyphens, and
  // every token in the spec contains one ("given-name", "postal-code"), so
  // normalising it silently destroys the strongest signal a form gives.
  // The attribute may also carry section/billing prefixes, hence the split.
  const autocompleteTokens = String(el.getAttribute('autocomplete') || '')
    .toLowerCase().trim().split(/\s+/).filter(Boolean);

  return {
    el,
    type: (el.getAttribute('type') || el.tagName).toLowerCase(),
    autocompleteTokens,
    rawName: normalise(el.getAttribute('name')),
    name: normalise(`${el.getAttribute('name') || ''} ${el.id || ''}`),
    placeholder: normalise(el.getAttribute('placeholder')),
    ariaLabel: normalise(el.getAttribute('aria-label')),
    label: labelTextFor(el, doc),
  };
}

/**
 * A stable key for remembering a user's correction on a given site.
 *
 * `name` alone is preferred over name+id because frameworks mint ids per
 * render (React's ":r3:", Angular's suffixes); including them would make every
 * learned mapping expire on the next page load.
 */
function signatureOf(desc) {
  return desc.rawName || normalise(desc.el && desc.el.id)
    || desc.label || desc.placeholder || desc.ariaLabel || '';
}

/** True when this input must never be touched, regardless of score. */
function isBlocked(desc, NEVER_FILL, NEVER_FILL_TYPES) {
  if (NEVER_FILL_TYPES.has(desc.type)) return true;
  const haystack = [desc.name, desc.label, desc.placeholder, desc.ariaLabel,
    desc.autocomplete].join(' ');
  return NEVER_FILL.test(haystack);
}

function isFillable(el) {
  if (el.disabled || el.readOnly) return false;
  if (el.getAttribute('aria-hidden') === 'true') return false;
  const rects = el.getClientRects();
  if (rects.length === 0) return false;                 // not laid out
  return true;
}

function keywordHit(haystack, keywords) {
  // Longer keywords first so "place of birth" beats "birth".
  for (const kw of [...keywords].sort((a, b) => b.length - a.length)) {
    if (!haystack) continue;
    if (haystack === kw) return { weight: 1.0, exact: true, phrase: false };
    if (haystack.includes(kw)) {
      const phrase = kw.includes(' ');
      return { weight: phrase ? 0.95 : 0.8, exact: false, phrase };
    }
  }
  return null;
}

function scoreFor(def, desc) {
  let score = 0;
  let anyExact = false;
  let anyPhrase = false;
  const why = [];

  const acHit = (desc.autocompleteTokens || []).find(
    (token) => (def.autocomplete || []).includes(token));
  if (acHit) {
    score += WEIGHTS.autocomplete;
    why.push(`autocomplete="${acHit}"`);
  }

  for (const [source, weight] of [
    ['label', WEIGHTS.label], ['name', WEIGHTS.name],
    ['placeholder', WEIGHTS.placeholder], ['ariaLabel', WEIGHTS.ariaLabel],
  ]) {
    const hit = keywordHit(desc[source], def.keywords || []);
    if (hit) {
      score += weight * hit.weight;
      anyExact = anyExact || hit.exact;
      anyPhrase = anyPhrase || hit.phrase;
      why.push(source);
    }
  }
  if (anyExact) score += EXACT_BONUS;
  else if (anyPhrase) score += PHRASE_BONUS;
  if (def.inputType && desc.type === def.inputType) {
    score += WEIGHTS.inputType;
    why.push(`type=${desc.type}`);
  }
  return { score, why };
}

/**
 * Work out what would be filled where.
 *
 * @param opts.overrides  {signature: profileKey | '__skip__'} learned per site
 * @param opts.includeSensitive  fill identity documents as well
 * @returns [{key, label, value, selector, score, why, sensitive, overridden}]
 */
function buildPlan(doc, profile, defs, blocked, opts = {}) {
  const { NEVER_FILL, NEVER_FILL_TYPES } = blocked;
  const overrides = opts.overrides || {};
  const byKey = new Map(defs.map((d) => [d.key, d]));

  const inputs = [...doc.querySelectorAll('input, select, textarea')];
  const candidates = [];

  for (const el of inputs) {
    const desc = describeInput(el, doc);
    if (isBlocked(desc, NEVER_FILL, NEVER_FILL_TYPES)) continue;
    if (!isFillable(el)) continue;

    const signature = signatureOf(desc);
    const override = overrides[signature];
    if (override === '__skip__') continue;

    let best = null;
    if (override && byKey.has(override)) {
      best = { def: byKey.get(override), score: 999, why: ['bu site için sen eşledin'] };
    } else {
      for (const def of defs) {
        const { score, why } = scoreFor(def, desc);
        if (score >= THRESHOLD && (!best || score > best.score)) {
          best = { def, score, why };
        }
      }
    }
    if (!best) continue;

    const value = profile[best.def.key];
    if (value === undefined || value === null || value === '') continue;
    if (best.def.sensitive && !opts.includeSensitive) continue;

    candidates.push({
      el,
      key: best.def.key,
      label: best.def.label,
      value: String(value),
      score: best.score,
      why: best.why,
      signature,
      sensitive: Boolean(best.def.sensitive),
      overridden: Boolean(override),
    });
  }

  // One input per profile item: if a page has several plausible homes for the
  // same value, filling all of them is how the wrong box gets filled.
  const bestPerKey = new Map();
  for (const c of candidates) {
    const current = bestPerKey.get(c.key);
    if (!current || c.score > current.score) bestPerKey.set(c.key, c);
  }
  return [...bestPerKey.values()];
}

if (typeof module !== 'undefined') {
  module.exports = { buildPlan, describeInput, scoreFor, normalise,
    signatureOf, isBlocked, THRESHOLD };
}
