'use strict';

// Source data is English; these are the fields worth showing first, with the
// captions used in the UI.
const FIELD_ORDER = [
  ['Academic admission requirements', 'Akademik kabul şartları'],
  ['Admission information', 'Kabul şartları — resmî sayfa'],
  ['English language skills', 'İngilizce şartı'],
  ['German language skills', 'Almanca şartı'],
  ['Application periods', 'Başvuru dönemleri'],
  ['Submit application via', 'Başvuru nereden yapılır'],
  ['Tuition fees', 'Harç'],
  ['Tuition fees per semester', 'Dönemlik harç'],
  ['Semester contribution', 'Dönemlik katkı payı'],
  ['Costs of living', 'Yaşam maliyeti'],
  ['Scholarships', 'Burslar'],
  ['Programme duration', 'Süre'],
  ['ECTS credits', 'ECTS'],
  ['Beginning', 'Başlangıç'],
  ['Study mode', 'Öğrenim şekli'],
  ['Location', 'Konum'],
  ['Field of study', 'Alan'],
  ['Institution type', 'Kurum türü'],
];

const STATUS_LABELS = {
  interested: 'İlgileniyorum',
  preparing: 'Hazırlanıyorum',
  submitted: 'Gönderildi',
  accepted: 'Kabul',
  rejected: 'Red',
  withdrawn: 'Vazgeçtim',
};

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz',
  'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Some fields (notably the Dutch "Admission information") are bare URLs.
// Runs on already-escaped text, so the matched substring is safe to embed.
const linkify = (escaped) => escaped.replace(
  /https?:\/\/[^\s<]+/g,
  (u) => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`);

async function api(path, options) {
  const res = await fetch('/api/' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json();
  if (data && data.error) throw new Error(data.error);
  return data;
}

function daysLeft(iso) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(iso + 'T00:00:00') - today) / 86400000);
}

function formatDaysLeft(n) {
  if (n === 0) return 'bugün';
  if (n === 1) return 'yarın';
  if (n < 30) return `${n} gün kaldı`;
  if (n < 365) return `${Math.round(n / 30)} ay kaldı`;
  return `${(n / 365).toFixed(1)} yıl kaldı`;
}

// ---------------------------------------------------------------- views

let currentView = 'search';

function showView(name) {
  currentView = name;
  document.querySelectorAll('nav button').forEach(
    (b) => b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(
    (v) => v.classList.toggle('active', v.id === 'view-' + name));
  if (name === 'shortlist') loadShortlist();
  if (name === 'calendar') loadCalendar();
}

document.querySelectorAll('nav button').forEach(
  (b) => b.addEventListener('click', () => showView(b.dataset.view)));

// ---------------------------------------------------------------- search

function programCard(p, extra = '') {
  const tags = [];
  if (p.subject) tags.push(`<span class="tag">${esc(p.subject)}</span>`);
  if (p.duration) tags.push(`<span class="tag">${esc(p.duration)}</span>`);
  (p.languages || []).forEach((l) => tags.push(`<span class="tag">${esc(l)}</span>`));
  if (p.tuition) {
    const free = /no tuition|none/i.test(p.tuition);
    tags.push(`<span class="tag ${free ? 'free' : ''}">${esc(p.tuition)}</span>`);
  }
  if (p.shortlisted) tags.push('<span class="tag star">kısa listede</span>');
  return `<div class="card" data-id="${p.id}" role="button" tabindex="0">
      <h3>${esc(p.name)}</h3>
      <div class="sub">${esc(p.university || '')} — ${esc(p.city || '')}, ${esc(p.country)}</div>
      <div class="meta">${tags.join('')}</div>${extra}
    </div>`;
}

let searchTimer = null;

async function loadResults() {
  const params = new URLSearchParams();
  if ($('#q').value.trim()) params.set('q', $('#q').value.trim());
  if ($('#city').value.trim()) params.set('city', $('#city').value.trim());
  if ($('#country').value) params.set('country', $('#country').value);
  if ($('#free').checked) params.set('free', '1');

  const box = $('#results');
  box.innerHTML = '<div class="spinner">aranıyor…</div>';
  try {
    const rows = await api('programs?' + params);
    box.innerHTML = rows.length
      ? rows.map((p) => programCard(p)).join('')
      : `<div class="empty">Sonuç yok.<br><br>
         Henüz veri çekmediysen terminalde:<br>
         <code>python -m het ingest de --subject "computer science"</code></div>`;
  } catch (err) {
    box.innerHTML = `<div class="empty">Hata: ${esc(err.message)}</div>`;
  }
}

['#q', '#city'].forEach((sel) => $(sel).addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadResults, 220);
}));
$('#country').addEventListener('change', loadResults);
$('#free').addEventListener('change', loadResults);

// ---------------------------------------------------------------- shortlist

async function loadShortlist() {
  const box = $('#shortlist');
  box.innerHTML = '<div class="spinner">yükleniyor…</div>';
  const rows = await api('shortlist');
  if (!rows.length) {
    box.innerHTML = `<div class="empty">Kısa liste boş.
      "Ara" sekmesinden bir program açıp ekle.</div>`;
    return;
  }
  box.innerHTML = rows.map((p) => {
    const pct = p.checklist_total ? (100 * p.checklist_done / p.checklist_total) : 0;
    let extra = `<div class="meta">
        <span class="tag star">${esc(STATUS_LABELS[p.status] || p.status)}</span>`;
    if (p.next_deadline) {
      const n = daysLeft(p.next_deadline.date);
      extra += `<span class="tag due">${esc(p.next_deadline.date)} · ${formatDaysLeft(n)}</span>`;
    }
    extra += `<span class="tag">belgeler ${p.checklist_done}/${p.checklist_total}</span></div>
      <div class="progress"><div style="width:${pct}%"></div></div>`;
    return programCard(p, extra);
  }).join('');
}

// ---------------------------------------------------------------- calendar

async function loadCalendar() {
  const box = $('#calendar');
  box.innerHTML = '<div class="spinner">yükleniyor…</div>';
  const all = $('#all-deadlines').checked ? '1' : '0';
  const rows = await api('deadlines?all=' + all);
  if (!rows.length) {
    box.innerHTML = `<div class="empty">Yaklaşan tarih yok.
      ${all === '1' ? '' : 'Kısa listene program ekle veya yukarıdaki kutuyu işaretle.'}</div>`;
    return;
  }
  let html = '';
  let lastMonth = '';
  for (const d of rows) {
    const date = new Date(d.date + 'T00:00:00');
    const monthKey = `${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
    if (monthKey !== lastMonth) {
      html += `<div class="month">${monthKey}</div>`;
      lastMonth = monthKey;
    }
    const n = daysLeft(d.date);
    const badge = d.confidence === 'exact'
      ? '<span class="tag exact">kesin</span>'
      : '<span class="tag warn">metinden</span>';
    html += `<div class="dl ${n < 45 ? 'soon' : ''}" data-id="${d.program_id}" role="button" tabindex="0">
        <span class="day">${date.getDate()} ${MONTHS[date.getMonth()].slice(0, 3)}</span>
        <span>
          <strong>${esc(d.name)}</strong> ${badge}<br>
          <span class="sub">${esc(d.university || '')} — ${esc(d.label || '')}</span>
        </span>
        <span class="days-left">${formatDaysLeft(n)}</span>
      </div>`;
  }
  box.innerHTML = html;
}

$('#all-deadlines').addEventListener('change', loadCalendar);

// ---------------------------------------------------------------- detail

let openId = null;

function closeDetail() {
  openId = null;
  $('#detail').classList.remove('open');
  $('#overlay').classList.remove('open');
}

$('#overlay').addEventListener('click', closeDetail);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetail(); });

document.addEventListener('click', (e) => {
  const card = e.target.closest('.card, .dl');
  if (card && card.dataset.id) openDetail(Number(card.dataset.id));
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest?.('.card, .dl');
  if (card && card.dataset.id) {
    e.preventDefault();
    openDetail(Number(card.dataset.id));
  }
});

async function openDetail(id, refresh = false) {
  openId = id;
  $('#detail').classList.add('open');
  $('#overlay').classList.add('open');
  $('#detail-body').innerHTML =
    '<div class="spinner">detay sayfası çekiliyor…<br><small>ilk açılışta birkaç saniye sürer</small></div>';
  try {
    const p = await api(`programs/${id}${refresh ? '?refresh=1' : ''}`);
    if (openId === id) renderDetail(p);
  } catch (err) {
    $('#detail-body').innerHTML = `<div class="empty">Hata: ${esc(err.message)}</div>`;
  }
}

function renderDetail(p) {
  const shown = new Set(FIELD_ORDER.map(([k]) => k));
  const fieldsHtml = FIELD_ORDER
    .filter(([key]) => p.fields[key])
    .map(([key, caption]) => `<div class="field">
        <div class="label">${esc(caption)}</div>
        <div class="value">${linkify(esc(p.fields[key]))}</div>
      </div>`).join('');

  const otherKeys = Object.keys(p.fields).filter((k) => !shown.has(k));
  const otherHtml = otherKeys.length ? `<details class="block">
      <summary style="cursor:pointer;color:var(--muted);font-size:13px">
        Diğer ${otherKeys.length} alan</summary>
      <div style="margin-top:10px">${otherKeys.map((k) => `<div class="field">
        <div class="label">${esc(k)}</div>
        <div class="value">${linkify(esc(p.fields[k]))}</div>
      </div>`).join('')}</div></details>` : '';

  const deadlinesHtml = p.deadlines.length ? p.deadlines.map((d) => {
    const n = daysLeft(d.date);
    // An exact date came straight out of a date field; a parsed one was read
    // out of prose and is the reader's cue to double-check.
    const exact = d.confidence === 'exact';
    const badge = exact
      ? '<span class="tag exact">kesin</span>'
      : '<span class="tag warn">metinden çıkarıldı</span>';
    const note = exact
      ? 'Kaynak bu tarihi doğrudan tarih alanı olarak yayımlıyor.'
      : `şu metinden çıkarıldı: “${esc(d.source_text)}”`;
    return `<div class="field">
        <div class="label">${esc(d.date)} · ${esc(d.label)}
          <span class="tag due">${formatDaysLeft(n)}</span> ${badge}</div>
        <div class="src">${note}</div>
      </div>`;
  }).join('') : '<div class="empty">Tarih çıkarılamadı — başvuru dönemleri alanını oku.</div>';

  const done = p.checklist.filter((c) => c.done).length;
  const checklistHtml = p.checklist.map((c) => `<label class="item ${c.done ? 'done' : ''}">
      <input type="checkbox" data-item="${c.id}" ${c.done ? 'checked' : ''}>
      <span class="body">
        <span class="name">${esc(c.label)}</span>
        ${c.detail ? `<div class="why">${esc(c.detail)}</div>` : ''}
      </span>
      ${c.auto ? '' : `<button class="icon" data-del="${c.id}" title="Sil">×</button>`}
    </label>`).join('');

  const inList = p.shortlist !== null;
  const statusOptions = Object.entries(STATUS_LABELS).map(([v, label]) =>
    `<option value="${v}" ${inList && p.shortlist.status === v ? 'selected' : ''}>${label}</option>`
  ).join('');

  $('#detail-body').innerHTML = `
    <div class="detail-head">
      <div>
        <h2>${esc(p.name)}</h2>
        <div class="sub">${esc(p.university || '')} — ${esc(p.city || '')}, ${esc(p.country)}
          ${p.degree ? ' · ' + esc(p.degree) : ''}</div>
      </div>
      <button class="icon" id="close-detail" style="margin-left:auto;font-size:22px">×</button>
    </div>

    <section class="block">
      <div class="filters" style="margin-bottom:0">
        ${inList
          ? `<select id="status-select">${statusOptions}</select>
             <button class="ghost" id="remove-shortlist">Kısa listeden çıkar</button>`
          : '<button class="primary" id="add-shortlist">Kısa listeye ekle</button>'}
        <button class="ghost" id="refresh-detail" style="margin-left:auto">Yenile</button>
      </div>
    </section>

    <section class="block">
      <h4>Belge listesi (${done}/${p.checklist.length})</h4>
      <div class="note">Bu liste, programın kendi gereklilik metninden otomatik
        üretildi. Başlangıç noktasıdır, tam liste değildir — resmî sayfayla karşılaştır.</div>
      ${checklistHtml}
      <div class="add-row">
        <input type="text" id="new-item" placeholder="Kendi maddeni ekle…">
        <button class="ghost" id="add-item">Ekle</button>
      </div>
    </section>

    <section class="block">
      <h4>Çıkarılan tarihler</h4>
      ${deadlinesHtml}
    </section>

    <section class="block">
      <h4>Gereklilikler</h4>
      ${fieldsHtml || '<div class="empty">Detay alınamadı.</div>'}
    </section>

    ${otherHtml}

    <section class="block">
      <h4>Kaynaklar</h4>
      <div class="links">
        ${p.detail_url ? `<a href="${esc(p.detail_url)}" target="_blank" rel="noopener">DAAD sayfası</a>` : ''}
        ${p.website ? `<a href="${esc(p.website)}" target="_blank" rel="noopener">Üniversitenin resmî sayfası</a>` : ''}
      </div>
    </section>`;

  wireDetail(p);
}

function wireDetail(p) {
  $('#close-detail').addEventListener('click', closeDetail);
  $('#refresh-detail').addEventListener('click', () => openDetail(p.id, true));

  const addBtn = $('#add-shortlist');
  if (addBtn) {
    addBtn.addEventListener('click', async () => {
      await api('shortlist', {
        method: 'POST',
        body: JSON.stringify({ program_id: p.id, status: 'interested' }),
      });
      openDetail(p.id);
      loadResults();
    });
  }

  const removeBtn = $('#remove-shortlist');
  if (removeBtn) {
    removeBtn.addEventListener('click', async () => {
      await api('shortlist/' + p.id, { method: 'DELETE' });
      openDetail(p.id);
      loadResults();
    });
  }

  const statusSelect = $('#status-select');
  if (statusSelect) {
    statusSelect.addEventListener('change', async () => {
      await api('shortlist', {
        method: 'POST',
        body: JSON.stringify({ program_id: p.id, status: statusSelect.value }),
      });
      if (currentView === 'shortlist') loadShortlist();
    });
  }

  $('#detail-body').querySelectorAll('input[data-item]').forEach((box) => {
    box.addEventListener('change', async () => {
      await api('checklist/' + box.dataset.item, {
        method: 'PATCH',
        body: JSON.stringify({ done: box.checked }),
      });
      box.closest('.item').classList.toggle('done', box.checked);
    });
  });

  $('#detail-body').querySelectorAll('button[data-del]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      await api('checklist/' + btn.dataset.del, { method: 'DELETE' });
      openDetail(p.id);
    });
  });

  const addItem = async () => {
    const label = $('#new-item').value.trim();
    if (!label) return;
    await api('checklist', {
      method: 'POST',
      body: JSON.stringify({ program_id: p.id, label }),
    });
    openDetail(p.id);
  };
  $('#add-item').addEventListener('click', addItem);
  $('#new-item').addEventListener('keydown', (e) => { if (e.key === 'Enter') addItem(); });
}

// ---------------------------------------------------------------- boot

(async function init() {
  try {
    const stats = await api('stats');
    $('#stats').textContent =
      `${stats.programs} program · kısa listede ${stats.shortlist}`;
    stats.countries.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = c;
      $('#country').appendChild(opt);
    });
  } catch (err) {
    $('#stats').textContent = 'veritabanına ulaşılamadı';
  }
  loadResults();
})();
