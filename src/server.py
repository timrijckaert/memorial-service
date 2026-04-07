import json
import mimetypes
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from src.extract import _extract_one
from src.merge import find_pairs, merge_all
from src.review import list_cards, load_card, save_card

APP_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memorial Card Digitizer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #333; }

  /* Navigation */
  .nav-bar { display: flex; background: #1a1a2e; border-bottom: 1px solid #333; }
  .nav-tab { padding: 12px 24px; color: #888; cursor: pointer; font-size: 14px; font-weight: 600; border-bottom: 2px solid transparent; text-decoration: none; }
  .nav-tab:hover { color: #ccc; }
  .nav-tab.active { color: #fff; border-bottom-color: #4a90d9; }

  /* Sections */
  .section { display: none; min-height: calc(100vh - 45px); }
  .section.active { display: block; }

  /* Merge section */
  .merge-section { padding: 24px; }
  .merge-controls { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
  .merge-hint { color: #888; font-size: 14px; margin-bottom: 16px; }
  .merge-hint code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; }
  .merge-summary { margin-bottom: 16px; font-size: 14px; }
  .merge-summary .ok { color: #27ae60; }
  .merge-summary .err { color: #e74c3c; }
  .merge-summary .skip { color: #888; }
  .pairs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
  .pair-card { background: #fff; border-radius: 8px; overflow: hidden; border: 1px solid #ddd; }
  .pair-card.error { border-color: #e74c3c; border-style: dashed; }
  .pair-card.merged { border-color: #27ae60; }
  .pair-images { display: flex; height: 150px; background: #f0f0f0; }
  .pair-images img { flex: 1; object-fit: cover; max-width: 50%; }
  .pair-images .merged-img { max-width: 100%; }
  .pair-images .placeholder { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; font-size: 12px; background: #e8e8e8; }
  .pair-images .placeholder.missing { background: #fde8e8; color: #e74c3c; }
  .pair-name { padding: 8px 12px; font-size: 13px; }
  .pair-name .status { font-size: 11px; margin-left: 4px; }

  /* Extract section */
  .extract-section { padding: 24px; }
  .extract-controls { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
  .extract-controls label { font-size: 13px; color: #666; display: flex; align-items: center; gap: 4px; }
  .extract-summary { display: flex; gap: 16px; margin-bottom: 16px; font-size: 13px; color: #888; }
  .current-card { background: #fff; border: 2px solid #4a90d9; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .current-card .card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .current-card .card-header .dot { width: 8px; height: 8px; border-radius: 50%; background: #4a90d9; animation: pulse 1s infinite; }
  .current-card .card-header .name { font-weight: 600; }
  .current-card .card-header .label { color: #4a90d9; font-size: 12px; margin-left: auto; }
  .pipeline-steps { display: flex; gap: 4px; margin-bottom: 12px; }
  .pipeline-step { flex: 1; padding: 6px; border-radius: 4px; font-size: 11px; text-align: center; background: #f0f0f0; color: #999; }
  .pipeline-step.done { background: #e8f5e9; color: #27ae60; }
  .pipeline-step.active { background: #e3f2fd; color: #4a90d9; border: 1px solid #4a90d9; }
  .ocr-preview { background: #f8f8f8; border-radius: 4px; padding: 8px; font-size: 12px; color: #666; font-family: monospace; max-height: 100px; overflow: auto; white-space: pre-wrap; }
  .card-list { display: flex; flex-direction: column; gap: 4px; }
  .card-item { display: flex; align-items: center; padding: 8px 12px; background: #fff; border-radius: 6px; border: 1px solid #ddd; gap: 12px; font-size: 13px; }
  .card-item.in-progress { border-color: #4a90d9; }
  .card-item.queued { opacity: 0.5; }
  .card-item .icon { font-size: 14px; width: 20px; text-align: center; }
  .card-item .icon.done { color: #27ae60; }
  .card-item .icon.error { color: #e74c3c; }
  .card-item .icon.progress { color: #4a90d9; }
  .card-item .icon.queued { color: #999; }
  .card-item .name { flex: 1; }
  .card-item .status-text { font-size: 11px; color: #888; }
  .card-item .review-link { color: #4a90d9; font-size: 11px; text-decoration: underline; cursor: pointer; }
  .extract-error-msg { background: #fde8e8; border: 1px solid #e74c3c; border-radius: 6px; padding: 12px; color: #c0392b; font-size: 14px; margin-bottom: 16px; }

  /* Review section */
  .review-section { display: none; height: calc(100vh - 45px); }
  .review-section.active { display: flex; }
  .review-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 24px; background: #fff; border-bottom: 1px solid #ddd; }
  .review-nav { display: flex; gap: 8px; align-items: center; }
  .review-nav button { padding: 6px 16px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; }
  .review-nav button:hover { background: #eee; }
  .review-nav button:disabled { opacity: 0.4; cursor: default; }
  .review-counter { font-size: 14px; color: #666; min-width: 80px; text-align: center; }
  .review-main { display: flex; flex: 1; overflow: hidden; }
  .image-panel { flex: 1; display: flex; flex-direction: column; border-right: 1px solid #ddd; background: #222; }
  .image-toggle { display: flex; background: #333; }
  .image-toggle button { flex: 1; padding: 8px; border: none; background: #333; color: #aaa; cursor: pointer; font-size: 13px; }
  .image-toggle button.active { background: #555; color: #fff; }
  .image-container { flex: 1; display: flex; align-items: center; justify-content: center; overflow: auto; padding: 16px; }
  .image-container img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .form-panel { flex: 1; overflow-y: auto; padding: 24px; background: #fff; }
  .form-group { margin-bottom: 16px; }
  .form-group label { display: block; font-size: 12px; font-weight: 600; color: #666; text-transform: uppercase; margin-bottom: 4px; }
  .form-group input { width: 100%; padding: 8px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .form-group input:focus { outline: none; border-color: #4a90d9; }
  .section-title { font-size: 14px; font-weight: 600; color: #333; margin: 20px 0 12px; padding-bottom: 4px; border-bottom: 1px solid #eee; }
  .notes-list { list-style: none; padding: 0; }
  .notes-list li { font-size: 13px; color: #666; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
  .spouse-entry { display: flex; gap: 6px; margin-bottom: 6px; }
  .spouse-entry input { flex: 1; padding: 8px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .spouse-entry input:focus { outline: none; border-color: #4a90d9; }
  .spouse-entry button { padding: 4px 10px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; color: #999; }
  .spouse-entry button:hover { background: #fee; color: #c00; border-color: #c00; }
  .no-image { color: #888; font-style: italic; }
  .no-cards-msg { padding: 40px; text-align: center; color: #888; font-size: 16px; }

  /* Shared */
  .btn { padding: 10px 24px; border: none; border-radius: 6px; font-weight: 600; font-size: 14px; cursor: pointer; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-primary { background: #4a90d9; color: #fff; }
  .btn-primary:hover:not(:disabled) { background: #3a7bc8; }
  .btn-danger { background: #e74c3c; color: #fff; }
  .btn-danger:hover:not(:disabled) { background: #c0392b; }
  .btn-success { background: #27ae60; color: #fff; }
  .btn-success:hover:not(:disabled) { background: #219a52; }
  .add-spouse-btn { padding: 6px 12px; border: 1px dashed #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; color: #666; }
  .add-spouse-btn:hover { border-color: #4a90d9; color: #4a90d9; }

  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
</head>
<body>

<!-- Navigation -->
<nav class="nav-bar">
  <a class="nav-tab" href="#merge" onclick="showSection('merge')">Merge</a>
  <a class="nav-tab" href="#extract" onclick="showSection('extract')">Extract</a>
  <a class="nav-tab" href="#review" onclick="showSection('review')">Review</a>
</nav>

<!-- Merge Section -->
<div id="section-merge" class="section merge-section">
  <div class="merge-controls">
    <button id="merge-btn" class="btn btn-primary" onclick="triggerMerge()">Merge All</button>
    <span id="merge-pair-count" style="color:#888; font-size:14px;"></span>
  </div>
  <p class="merge-hint">Drop your scanned front &amp; back images in the <code>input/</code> folder and refresh the page.</p>
  <div id="merge-summary" class="merge-summary" style="display:none;"></div>
  <div id="pairs-grid" class="pairs-grid"></div>
</div>

<!-- Extract Section -->
<div id="section-extract" class="section extract-section">
  <div class="extract-controls">
    <button id="extract-btn" class="btn btn-primary" onclick="triggerExtract()">Extract All</button>
    <button id="cancel-btn" class="btn btn-danger" onclick="cancelExtract()" style="display:none;">Cancel</button>
    <label><input type="checkbox" id="force-extract"> Force re-extract</label>
    <span id="extract-count" style="color:#888; font-size:14px;"></span>
  </div>
  <div id="extract-error" class="extract-error-msg" style="display:none;"></div>
  <div id="extract-summary" class="extract-summary" style="display:none;"></div>
  <div id="current-card" class="current-card" style="display:none;">
    <div class="card-header">
      <div class="dot"></div>
      <span class="name" id="current-name"></span>
      <span class="label">Currently processing</span>
    </div>
    <div class="pipeline-steps" id="pipeline-steps">
      <div class="pipeline-step" data-step="ocr_front">OCR Front</div>
      <div class="pipeline-step" data-step="ocr_back">OCR Back</div>
      <div class="pipeline-step" data-step="date_verify">Date Verify</div>
      <div class="pipeline-step" data-step="llm_extract">LLM Extract</div>
    </div>
  </div>
  <div id="extract-card-list" class="card-list"></div>
</div>

<!-- Review Section -->
<div id="section-review" class="section review-section">
  <div style="display:flex; flex-direction:column; flex:1;">
    <div class="review-header">
      <div class="review-nav">
        <button id="prev-btn" onclick="reviewNavigate(-1)">&larr; Previous</button>
        <span id="review-counter" class="review-counter">-</span>
        <button id="next-btn" onclick="reviewNavigate(1)">Next &rarr;</button>
      </div>
    </div>
    <div class="review-main">
      <div class="image-panel">
        <div class="image-toggle">
          <button id="front-btn" onclick="showSide('front')">Front</button>
          <button id="back-btn" class="active" onclick="showSide('back')">Back</button>
        </div>
        <div class="image-container">
          <img id="card-image" src="" alt="Card image">
          <span id="no-image" class="no-image" style="display:none">No image available</span>
        </div>
      </div>
      <div class="form-panel">
        <div class="section-title">Person</div>
        <div class="form-group"><label>First Name</label><input id="f-first_name"></div>
        <div class="form-group"><label>Last Name</label><input id="f-last_name"></div>
        <div class="form-group"><label>Birth Date (YYYY-MM-DD)</label><input id="f-birth_date"></div>
        <div class="form-group"><label>Birth Place</label><input id="f-birth_place"></div>
        <div class="form-group"><label>Death Date (YYYY-MM-DD)</label><input id="f-death_date"></div>
        <div class="form-group"><label>Death Place</label><input id="f-death_place"></div>
        <div class="form-group"><label>Age at Death</label><input id="f-age_at_death" type="number"></div>
        <div class="form-group"><label>Spouses</label><div id="spouses-list"></div><button type="button" class="add-spouse-btn" onclick="addSpouseInput('')">+ Add spouse</button></div>
        <div class="section-title">Notes (from LLM)</div>
        <ul id="notes-list" class="notes-list"></ul>
        <button id="approve-btn" class="btn btn-primary" style="width:100%; margin-top:24px;" onclick="approveCard()">Approve</button>
      </div>
    </div>
    <div id="no-cards" class="no-cards-msg" style="display:none;">No cards to review. Run extraction first.</div>
  </div>
</div>

<script>
/* ---- Navigation ---- */
async function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));

  const section = document.getElementById('section-' + name);
  if (section) section.classList.add('active');

  const tab = document.querySelector('.nav-tab[href="#' + name + '"]');
  if (tab) tab.classList.add('active');

  if (name === 'merge') await loadMergePairs();
  if (name === 'extract') await loadExtractCards();
  if (name === 'review') await initReview();
}

async function handleHash() {
  const hash = location.hash.slice(1) || 'merge';
  if (hash.startsWith('review/')) {
    const cardId = decodeURIComponent(hash.slice(7));
    await showSection('review');
    reviewJumpTo(cardId);
  } else {
    await showSection(hash);
  }
}

window.addEventListener('hashchange', handleHash);

/* ---- Merge ---- */
async function loadMergePairs() {
  const resp = await fetch('/api/merge/pairs');
  const data = await resp.json();
  const grid = document.getElementById('pairs-grid');
  const countEl = document.getElementById('merge-pair-count');
  grid.innerHTML = '';
  countEl.textContent = data.pairs.length + ' pair' + (data.pairs.length !== 1 ? 's' : '') + ' detected';

  data.pairs.forEach(pair => {
    const card = document.createElement('div');
    card.className = 'pair-card' + (pair.merged ? ' merged' : '');
    const imgs = document.createElement('div');
    imgs.className = 'pair-images';

    if (pair.merged) {
      const img = document.createElement('img');
      img.className = 'merged-img';
      img.src = '/output-images/' + encodeURIComponent(pair.front);
      imgs.appendChild(img);
    } else {
      const frontImg = document.createElement('img');
      frontImg.src = '/images/' + encodeURIComponent(pair.front);
      const backImg = document.createElement('img');
      backImg.src = '/images/' + encodeURIComponent(pair.back);
      imgs.appendChild(frontImg);
      imgs.appendChild(backImg);
    }

    const name = document.createElement('div');
    name.className = 'pair-name';
    name.innerHTML = pair.name + (pair.merged ? ' <span class="status ok">&#10003; merged</span>' : '');

    card.appendChild(imgs);
    card.appendChild(name);
    grid.appendChild(card);
  });

  data.errors.forEach(err => {
    const card = document.createElement('div');
    card.className = 'pair-card error';
    const imgs = document.createElement('div');
    imgs.className = 'pair-images';
    const ph = document.createElement('div');
    ph.className = 'placeholder missing';
    ph.textContent = 'missing';
    imgs.appendChild(ph);
    const name = document.createElement('div');
    name.className = 'pair-name';
    name.style.color = '#e74c3c';
    name.textContent = err;
    card.appendChild(imgs);
    card.appendChild(name);
    grid.appendChild(card);
  });
}

async function triggerMerge() {
  const btn = document.getElementById('merge-btn');
  btn.disabled = true;
  btn.textContent = 'Merging...';

  const resp = await fetch('/api/merge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  const data = await resp.json();

  const summary = document.getElementById('merge-summary');
  summary.style.display = 'block';
  let parts = [];
  if (data.ok > 0) parts.push('<span class="ok">&#10003; ' + data.ok + ' merged</span>');
  if (data.skipped > 0) parts.push('<span class="skip">' + data.skipped + ' skipped</span>');
  if (data.errors.length > 0) parts.push('<span class="err">&#10007; ' + data.errors.length + ' error(s)</span>');
  let html = parts.join(' &middot; ');
  if (data.errors.length > 0) {
    html += '<ul style="margin-top:8px; padding-left:20px; font-size:13px; color:#e74c3c;">';
    data.errors.forEach(e => { html += '<li>' + e.replace(/</g, '&lt;') + '</li>'; });
    html += '</ul>';
  }
  summary.innerHTML = html;

  btn.disabled = false;
  btn.textContent = 'Merge All';
  loadMergePairs();
}

/* ---- Extract ---- */
let extractPollInterval = null;

async function loadExtractCards() {
  const resp = await fetch('/api/extract/cards');
  const data = await resp.json();
  const countEl = document.getElementById('extract-count');
  const pending = data.cards.filter(c => c.status === 'pending').length;
  const done = data.cards.filter(c => c.status === 'done').length;
  countEl.textContent = data.cards.length + ' card' + (data.cards.length !== 1 ? 's' : '') + ' (' + done + ' done, ' + pending + ' pending)';

  renderExtractList(data.cards.map(c => ({ ...c, icon: c.status === 'done' ? 'done' : 'queued' })));

  // Check if already running
  const statusResp = await fetch('/api/extract/status');
  const status = await statusResp.json();
  if (status.status === 'running' || status.status === 'cancelling') {
    startExtractPolling();
  }
}

function renderExtractList(cards) {
  const list = document.getElementById('extract-card-list');
  list.innerHTML = '';
  cards.forEach(c => {
    const item = document.createElement('div');
    const cls = c.icon === 'done' ? '' : c.icon === 'progress' ? ' in-progress' : c.icon === 'error' ? '' : ' queued';
    item.className = 'card-item' + cls;

    const iconMap = { done: '&#10003;', error: '&#10007;', progress: '&#9679;', queued: '&#9675;' };
    const cardName = c.name || c.card_id || '';
    const encodedName = encodeURIComponent(cardName);
    let actions = '';
    if (c.icon === 'done') actions = '<span class="review-link" onclick="location.hash=\\'review/' + encodedName + '\\'">Review &rarr;</span>';
    if (c.icon === 'queued' && !extractPollInterval) actions = '<span class="review-link" onclick="triggerExtractOne(\\'' + cardName.replace(/'/g, "\\\\'") + '\\')">Extract</span>';
    item.innerHTML =
      '<span class="icon ' + c.icon + '">' + (iconMap[c.icon] || '') + '</span>' +
      '<span class="name">' + cardName + '</span>' +
      '<span class="status-text">' + (c.statusText || c.status || '') + '</span>' +
      actions;

    list.appendChild(item);
  });
}

async function triggerExtract() {
  const force = document.getElementById('force-extract').checked;
  const errorEl = document.getElementById('extract-error');
  errorEl.style.display = 'none';
  const resp = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force: force }),
  });
  const data = await resp.json();
  if (data.status === 'already_running') return;
  if (data.status === 'error') {
    errorEl.textContent = data.error;
    errorEl.style.display = '';
    return;
  }

  startExtractPolling();
}

async function triggerExtractOne(cardName) {
  const force = document.getElementById('force-extract').checked;
  const errorEl = document.getElementById('extract-error');
  errorEl.style.display = 'none';
  const resp = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force: force, card: cardName }),
  });
  const data = await resp.json();
  if (data.status === 'already_running') return;
  if (data.status === 'error') {
    errorEl.textContent = data.error;
    errorEl.style.display = '';
    return;
  }
  startExtractPolling();
}

function startExtractPolling() {
  document.getElementById('extract-btn').style.display = 'none';
  document.getElementById('cancel-btn').style.display = '';
  document.getElementById('extract-summary').style.display = 'flex';

  if (extractPollInterval) clearInterval(extractPollInterval);
  extractPollInterval = setInterval(pollExtractStatus, 1500);
  pollExtractStatus();
}

async function pollExtractStatus() {
  const resp = await fetch('/api/extract/status');
  const status = await resp.json();

  // Update summary
  const summary = document.getElementById('extract-summary');
  summary.innerHTML =
    '<span>' + status.done.length + ' done</span>' +
    (status.current ? '<span>1 in progress</span>' : '') +
    '<span>' + status.queue.length + ' queued</span>' +
    (status.errors.length > 0 ? '<span style="color:#e74c3c;">' + status.errors.length + ' error(s)</span>' : '');

  // Update current card
  const currentEl = document.getElementById('current-card');
  if (status.current) {
    currentEl.style.display = '';
    document.getElementById('current-name').textContent = status.current.card_id;
    const steps = ['ocr_front', 'ocr_back', 'date_verify', 'llm_extract'];
    const currentIdx = steps.indexOf(status.current.step);
    document.querySelectorAll('.pipeline-step').forEach((el, i) => {
      el.className = 'pipeline-step' + (i < currentIdx ? ' done' : i === currentIdx ? ' active' : '');
    });
  } else {
    currentEl.style.display = 'none';
  }

  // Update card list
  let cards = [];
  status.done.forEach(name => cards.push({ name: name, icon: 'done', statusText: 'Done', status: 'done' }));
  if (status.current) cards.push({ name: status.current.card_id, icon: 'progress', statusText: status.current.step.replace('_', ' '), status: 'progress' });
  status.errors.forEach(e => cards.push({ name: e.card_id, icon: 'error', statusText: e.reason, status: 'error' }));
  status.queue.forEach(name => cards.push({ name: name, icon: 'queued', statusText: 'Queued', status: 'queued' }));
  renderExtractList(cards);

  // Check if done
  if (status.status === 'idle' || status.status === 'cancelled') {
    clearInterval(extractPollInterval);
    extractPollInterval = null;
    document.getElementById('extract-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = 'none';
    if (status.status === 'cancelled') {
      document.getElementById('extract-summary').innerHTML += '<span style="color:#e67e22;"> (cancelled)</span>';
    }
  }
}

async function cancelExtract() {
  await fetch('/api/extract/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
}

/* ---- Review ---- */
let reviewCards = [];
let reviewIndex = 0;
let reviewCurrentCard = null;
let reviewCurrentSide = 'back';
let reviewInitialized = false;

async function initReview() {
  const resp = await fetch('/api/cards');
  reviewCards = await resp.json();
  if (reviewCards.length === 0) {
    document.getElementById('no-cards').style.display = '';
    document.querySelector('.review-main').style.display = 'none';
    document.querySelector('.review-header').style.display = 'none';
    return;
  }
  document.getElementById('no-cards').style.display = 'none';
  document.querySelector('.review-main').style.display = '';
  document.querySelector('.review-header').style.display = '';
  if (!reviewInitialized) {
    reviewInitialized = true;
    await loadReviewCard(0);
  }
}

function reviewJumpTo(cardId) {
  const idx = reviewCards.indexOf(cardId);
  if (idx >= 0) loadReviewCard(idx);
}

async function loadReviewCard(index) {
  reviewIndex = index;
  const id = reviewCards[index];
  const resp = await fetch('/api/cards/' + encodeURIComponent(id));
  reviewCurrentCard = await resp.json();

  document.getElementById('review-counter').textContent = (index + 1) + ' / ' + reviewCards.length;
  document.getElementById('prev-btn').disabled = index === 0;
  document.getElementById('next-btn').disabled = index === reviewCards.length - 1;

  const p = reviewCurrentCard.data.person || {};
  document.getElementById('f-first_name').value = p.first_name || '';
  document.getElementById('f-last_name').value = p.last_name || '';
  document.getElementById('f-birth_date').value = p.birth_date || '';
  document.getElementById('f-birth_place').value = p.birth_place || '';
  document.getElementById('f-death_date').value = p.death_date || '';
  document.getElementById('f-death_place').value = p.death_place || '';
  document.getElementById('f-age_at_death').value = p.age_at_death != null ? p.age_at_death : '';

  document.getElementById('spouses-list').innerHTML = '';
  (p.spouses || []).forEach(name => addSpouseInput(name));
  if (!p.spouses || p.spouses.length === 0) addSpouseInput('');

  const notesList = document.getElementById('notes-list');
  notesList.innerHTML = '';
  (reviewCurrentCard.data.notes || []).forEach(note => {
    const li = document.createElement('li');
    li.textContent = note;
    notesList.appendChild(li);
  });

  const btn = document.getElementById('approve-btn');
  btn.textContent = 'Approve';
  btn.classList.remove('btn-success');
  btn.classList.add('btn-primary');

  showSide('back');
}

function addSpouseInput(value) {
  const container = document.getElementById('spouses-list');
  const div = document.createElement('div');
  div.className = 'spouse-entry';
  const input = document.createElement('input');
  input.value = value;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = '\\u00d7';
  btn.onclick = function() { div.remove(); };
  div.appendChild(input);
  div.appendChild(btn);
  container.appendChild(div);
}

function getSpousesFromForm() {
  const inputs = document.querySelectorAll('#spouses-list .spouse-entry input');
  const names = [];
  inputs.forEach(input => { const v = input.value.trim(); if (v) names.push(v); });
  return names;
}

function showSide(side) {
  reviewCurrentSide = side;
  const img = document.getElementById('card-image');
  const noImg = document.getElementById('no-image');
  const src = side === 'front' ? reviewCurrentCard.front_image : reviewCurrentCard.back_image;

  document.getElementById('front-btn').classList.toggle('active', side === 'front');
  document.getElementById('back-btn').classList.toggle('active', side === 'back');

  if (src) {
    img.src = '/images/' + encodeURIComponent(src);
    img.style.display = '';
    noImg.style.display = 'none';
  } else {
    img.style.display = 'none';
    noImg.style.display = '';
  }
}

function reviewNavigate(delta) {
  const next = reviewIndex + delta;
  if (next >= 0 && next < reviewCards.length) loadReviewCard(next);
}

async function approveCard() {
  const ageRaw = document.getElementById('f-age_at_death').value.trim();
  const updated = {
    person: {
      first_name: document.getElementById('f-first_name').value.trim() || null,
      last_name: document.getElementById('f-last_name').value.trim() || null,
      birth_date: document.getElementById('f-birth_date').value.trim() || null,
      birth_place: document.getElementById('f-birth_place').value.trim() || null,
      death_date: document.getElementById('f-death_date').value.trim() || null,
      death_place: document.getElementById('f-death_place').value.trim() || null,
      age_at_death: ageRaw ? parseInt(ageRaw, 10) : null,
      spouses: getSpousesFromForm(),
    },
    notes: reviewCurrentCard.data.notes || [],
    source: {},
  };

  await fetch('/api/cards/' + encodeURIComponent(reviewCards[reviewIndex]), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updated),
  });

  const btn = document.getElementById('approve-btn');
  btn.textContent = 'Saved!';
  btn.classList.remove('btn-primary');
  btn.classList.add('btn-success');
}

/* ---- Init ---- */
handleHash();
</script>
</body>
</html>
"""


class ExtractionWorker:
    """Runs extraction sequentially on a background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = {
            "status": "idle",
            "current": None,
            "done": [],
            "errors": [],
            "queue": [],
        }

    def get_status(self) -> dict:
        with self._lock:
            return {
                "status": self._state["status"],
                "current": dict(self._state["current"]) if self._state["current"] else None,
                "done": list(self._state["done"]),
                "errors": [dict(e) for e in self._state["errors"]],
                "queue": list(self._state["queue"]),
            }

    def start(self, pairs, text_dir, json_dir, conflicts_dir,
              prompt_template, ollama_available, force):
        with self._lock:
            if self._state["status"] == "running":
                return False
            queue_names = [front.stem for front, _ in pairs]
            self._state = {
                "status": "running",
                "current": None,
                "done": [],
                "errors": [],
                "queue": queue_names,
            }
            self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            args=(pairs, text_dir, json_dir, conflicts_dir,
                  prompt_template, ollama_available, force),
            daemon=True,
        )
        thread.start()
        return True

    def cancel(self):
        self._cancel.set()
        with self._lock:
            if self._state["status"] == "running":
                self._state["status"] = "cancelling"

    def _run(self, pairs, text_dir, json_dir, conflicts_dir,
             prompt_template, ollama_available, force):
        for front_path, back_path in pairs:
            if self._cancel.is_set():
                with self._lock:
                    self._state["status"] = "cancelled"
                return

            card_name = front_path.stem

            with self._lock:
                if card_name in self._state["queue"]:
                    self._state["queue"].remove(card_name)
                self._state["current"] = {"card_id": card_name, "step": "ocr_front"}

            # Skip if already extracted and not forcing
            json_output = json_dir / f"{front_path.stem}.json"
            if not force and json_output.exists():
                with self._lock:
                    self._state["done"].append(card_name)
                    self._state["current"] = None
                continue

            result = _extract_one(
                front_path, back_path,
                text_dir, json_dir, conflicts_dir,
                ollama_available, prompt_template,
            )

            with self._lock:
                if result["errors"]:
                    self._state["errors"].append({
                        "card_id": card_name,
                        "reason": "; ".join(result["errors"]),
                    })
                else:
                    self._state["done"].append(card_name)
                self._state["current"] = None

        with self._lock:
            if self._state["status"] != "cancelled":
                self._state["status"] = "idle"


class AppHandler(BaseHTTPRequestHandler):
    """HTTP handler for the memorial card web app."""

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def _serve_image(self, base_dir: Path, filename: str):
        image_path = (base_dir / filename).resolve()
        if not str(image_path).startswith(str(base_dir.resolve())):
            self._send_error(403, "Forbidden")
            return
        if not image_path.exists():
            self._send_error(404, "Image not found")
            return

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = image_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        json_dir = self.server.json_dir
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir

        if self.path == "/":
            body = APP_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/cards":
            self._send_json(list_cards(json_dir))
        elif self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            result = load_card(card_id, json_dir, input_dir)
            if result is None:
                self._send_error(404, "Card not found")
            else:
                self._send_json(result)
        elif self.path.startswith("/images/"):
            filename = unquote(self.path[len("/images/"):])
            self._serve_image(input_dir, filename)
        elif self.path.startswith("/output-images/"):
            filename = unquote(self.path[len("/output-images/"):])
            self._serve_image(output_dir, filename)
        elif self.path == "/api/merge/pairs":
            pairs, errors = find_pairs(input_dir)
            result = {
                "pairs": [
                    {
                        "name": front.stem,
                        "front": front.name,
                        "back": back.name,
                        "merged": (output_dir / front.name).exists(),
                    }
                    for front, back in pairs
                ],
                "errors": errors,
            }
            self._send_json(result)
        elif self.path == "/api/extract/status":
            self._send_json(self.server.worker.get_status())
        elif self.path == "/api/extract/cards":
            pairs, _ = find_pairs(input_dir)
            cards = []
            for front, back in pairs:
                has_json = (json_dir / f"{front.stem}.json").exists()
                cards.append({
                    "name": front.stem,
                    "front": front.name,
                    "back": back.name,
                    "status": "done" if has_json else "pending",
                })
            self._send_json({"cards": cards})
        else:
            self._send_error(404, "Not found")

    def do_PUT(self):
        json_dir = self.server.json_dir

        if self.path.startswith("/api/cards/"):
            card_id = unquote(self.path[len("/api/cards/"):])
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                updated_data = json.loads(body)
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
                return

            json_path = json_dir / f"{card_id}.json"
            if not json_path.exists():
                self._send_error(404, "Card not found")
                return

            save_card(card_id, json_dir, updated_data)
            self._send_json({"status": "saved"})
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        input_dir = self.server.input_dir
        output_dir = self.server.output_dir
        json_dir = self.server.json_dir

        if self.path == "/api/merge":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            force = options.get("force", False)
            pairs, pairing_errors = find_pairs(input_dir)
            ok_count, skipped, merge_errors = merge_all(pairs, output_dir, force=force)
            self._send_json({
                "ok": ok_count,
                "skipped": skipped,
                "errors": pairing_errors + merge_errors,
            })
        elif self.path == "/api/extract":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                options = json.loads(body)
            except json.JSONDecodeError:
                options = {}

            force = options.get("force", False)
            card_filter = options.get("card", None)
            pairs, _ = find_pairs(input_dir)
            if card_filter:
                pairs = [(f, b) for f, b in pairs if f.stem == card_filter]
            text_dir = output_dir / "text"
            text_dir.mkdir(exist_ok=True)
            json_dir.mkdir(exist_ok=True)
            conflicts_dir = output_dir / "date_conflicts"

            # Load prompt template
            prompt_path = input_dir.parent / "prompts" / "extract_person.txt"
            prompt_template = None
            if prompt_path.exists():
                prompt_template = prompt_path.read_text()

            # Check Ollama availability
            ollama_available = False
            if prompt_template:
                try:
                    import ollama as ollama_client
                    ollama_client.list()
                    ollama_available = True
                except Exception:
                    pass

            if not ollama_available and prompt_template:
                self._send_json({"status": "error", "error": "Ollama is not running. Start it with `ollama serve`."}, 503)
                return

            started = self.server.worker.start(
                pairs, text_dir, json_dir, conflicts_dir,
                prompt_template, ollama_available, force,
            )
            if started:
                self._send_json({"status": "started"})
            else:
                self._send_json({"status": "already_running"}, 409)
        elif self.path == "/api/extract/cancel":
            self.server.worker.cancel()
            self._send_json({"status": "cancelling"})
        else:
            self._send_error(404, "Not found")


def make_server(json_dir: Path, input_dir: Path, output_dir: Path, port: int = 0) -> HTTPServer:
    """Create an HTTPServer bound to localhost on the given port."""
    server = HTTPServer(("localhost", port), AppHandler)
    server.json_dir = json_dir
    server.input_dir = input_dir
    server.output_dir = output_dir
    server.worker = ExtractionWorker()
    return server
