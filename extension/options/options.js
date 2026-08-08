'use strict';

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function renderForm(profile) {
  const groups = new Map();
  for (const def of FIELD_DEFS) {
    if (!groups.has(def.group)) groups.set(def.group, []);
    groups.get(def.group).push(def);
  }

  $('#profile-form').innerHTML = [...groups].map(([group, defs]) => `
    <fieldset class="${group === 'identity' ? 'sensitive' : ''}">
      <legend>${esc(GROUP_LABELS[group] || group)}</legend>
      ${defs.map((def) => `
        <label class="field">
          <span>${esc(def.label)}</span>
          <input type="${def.inputType === 'date' ? 'date' : 'text'}"
                 name="${def.key}"
                 value="${esc(profile[def.key] || '')}"
                 autocomplete="off">
        </label>`).join('')}
    </fieldset>`).join('');
}

async function renderOverrides() {
  const { overrides = {} } = await chrome.storage.local.get('overrides');
  const hosts = Object.keys(overrides).filter((h) => Object.keys(overrides[h]).length);
  if (!hosts.length) {
    $('#overrides-section').hidden = true;
    return;
  }
  $('#overrides-section').hidden = false;
  const labels = Object.fromEntries(FIELD_DEFS.map((d) => [d.key, d.label]));
  $('#overrides').innerHTML = hosts.map((host) => `
    <div class="override-host">
      <strong>${esc(host)}</strong>
      ${Object.entries(overrides[host]).map(([sig, key]) => `
        <div class="override">
          <code>${esc(sig)}</code> → ${esc(labels[key] || key)}
          <button class="ghost small" data-host="${esc(host)}"
                  data-sig="${esc(sig)}">unut</button>
        </div>`).join('')}
    </div>`).join('');
}

async function save() {
  const profile = {};
  for (const input of $('#profile-form').querySelectorAll('input')) {
    const value = input.value.trim();
    if (value) profile[input.name] = value;
  }
  await chrome.storage.local.set({ profile });
  $('#saved').hidden = false;
  setTimeout(() => { $('#saved').hidden = true; }, 1800);
}

async function exportProfile() {
  const { profile = {} } = await chrome.storage.local.get('profile');
  const blob = new Blob([JSON.stringify(profile, null, 2)],
    { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  await chrome.downloads?.download?.({ url, filename: 'basvuru-profili.json' })
    ?? window.open(url);
}

async function clearAll() {
  // Deliberately blunt: this wipes identity data, so it asks first.
  if (!window.confirm(
    'Profildeki tüm bilgiler ve site eşlemeleri silinecek. Emin misin?')) return;
  await chrome.storage.local.clear();
  renderForm({});
  await renderOverrides();
  $('#saved').hidden = false;
  $('#saved').textContent = 'silindi';
}

$('#save').addEventListener('click', (e) => { e.preventDefault(); save(); });
$('#export').addEventListener('click', (e) => { e.preventDefault(); exportProfile(); });
$('#clear').addEventListener('click', (e) => { e.preventDefault(); clearAll(); });

$('#overrides').addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-sig]');
  if (!button) return;
  const { overrides = {} } = await chrome.storage.local.get('overrides');
  delete overrides[button.dataset.host]?.[button.dataset.sig];
  await chrome.storage.local.set({ overrides });
  renderOverrides();
});

(async function init() {
  const { profile = {} } = await chrome.storage.local.get('profile');
  renderForm(profile);
  await renderOverrides();
})();
