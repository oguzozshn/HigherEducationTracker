'use strict';

// The popup is the consent step: it shows exactly what would go where, lets
// each item be unticked or re-mapped, and only then fills. Nothing happens to
// the page from merely opening it.

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let tabId = null;
let host = '';
let currentPlan = [];

async function getTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function loadStore() {
  const { profile = {}, overrides = {} } = await chrome.storage.local.get(
    ['profile', 'overrides']);
  return { profile, overrides };
}

function truncate(value, n = 42) {
  const v = String(value);
  return v.length > n ? `${v.slice(0, n)}…` : v;
}

function renderPlan(plan) {
  if (!plan.length) {
    $('#plan').innerHTML =
      `<div class="empty">Bu sayfada eşleşen alan bulunamadı.<br>
       Profilin boşsa önce <a href="#" class="opt">doldur</a>.</div>`;
    $('#actions').hidden = true;
    return;
  }
  const options = FIELD_DEFS.map((d) =>
    `<option value="${d.key}">${esc(d.label)}</option>`).join('');

  $('#plan').innerHTML = plan.map((item) => `
    <div class="item ${item.sensitive ? 'sensitive' : ''}">
      <input type="checkbox" class="pick" data-id="${item.id}" checked>
      <div class="body">
        <div class="row">
          <span class="val">${esc(truncate(item.value))}</span>
          <span class="arrow">→</span>
          <select class="remap" data-id="${item.id}" data-sig="${esc(item.signature)}">
            ${options.replace(`value="${item.key}"`, `value="${item.key}" selected`)}
          </select>
        </div>
        <div class="meta">
          ${esc(item.fieldName || item.tag)}
          ${item.overridden ? ' · <b>senin eşlemen</b>' : ` · ${esc(item.why)}`}
          ${item.sensitive ? ' · <b>hassas</b>' : ''}
        </div>
      </div>
    </div>`).join('');
  $('#actions').hidden = false;
}

async function scan() {
  const { profile, overrides } = await loadStore();
  if (!Object.values(profile).some((v) => v)) {
    $('#status').innerHTML =
      'Profil boş. <a href="#" class="opt">Profili doldur</a> ki doldurulacak bir şey olsun.';
    return;
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['lib/fields.js', 'lib/matcher.js', 'content/content.js'],
    });
  } catch (error) {
    $('#status').textContent =
      'Bu sayfaya erişilemiyor (tarayıcı ayar sayfaları ve eklenti mağazası korumalıdır).';
    return;
  }

  const response = await chrome.tabs.sendMessage(tabId, {
    type: 'scan',
    profile,
    overrides: overrides[host] || {},
    includeSensitive: $('#include-sensitive').checked,
  });

  if (!response?.ok) {
    $('#status').textContent = `Tarama başarısız: ${response?.error || 'bilinmeyen hata'}`;
    return;
  }
  currentPlan = response.plan;
  const sensitiveCount = currentPlan.filter((i) => i.sensitive).length;
  $('#status').textContent =
    `${currentPlan.length} alan eşleşti${sensitiveCount ? ` (${sensitiveCount} hassas)` : ''}.`;
  renderPlan(currentPlan);
}

async function apply() {
  const picked = new Set([...document.querySelectorAll('.pick:checked')]
    .map((el) => el.dataset.id));
  const items = currentPlan.filter((i) => picked.has(i.id));
  if (!items.length) {
    $('#status').textContent = 'Hiçbir alan seçilmedi.';
    return;
  }
  const response = await chrome.tabs.sendMessage(tabId, { type: 'fill', items });
  if (!response?.ok) {
    $('#status').textContent = `Doldurulamadı: ${response?.error}`;
    return;
  }
  let text = `${response.filled} alan dolduruldu.`;
  if (response.skipped.length) text += ` Atlanan: ${response.skipped.join('; ')}`;
  $('#status').textContent = text;
}

/** Remembering a correction is what makes the next visit to a portal quick. */
async function remap(event) {
  const select = event.target;
  const { overrides = {} } = await chrome.storage.local.get('overrides');
  overrides[host] = overrides[host] || {};
  overrides[host][select.dataset.sig] = select.value;
  await chrome.storage.local.set({ overrides });
  $('#status').textContent = 'Eşleme bu site için kaydedildi. Yeniden tarandı.';
  await scan();
}

document.addEventListener('click', (event) => {
  if (event.target.id === 'open-options' || event.target.classList.contains('opt')) {
    event.preventDefault();
    chrome.runtime.openOptionsPage();
  }
});

$('#apply').addEventListener('click', apply);
$('#include-sensitive').addEventListener('change', scan);
document.addEventListener('change', (event) => {
  if (event.target.classList.contains('remap')) remap(event);
});

(async function init() {
  const tab = await getTab();
  tabId = tab.id;
  try { host = new URL(tab.url).hostname; } catch { host = ''; }
  $('#sensitive-row').hidden = false;
  await scan();
})();
