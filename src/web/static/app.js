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

  renderExtractList(data.cards.map(c => ({ ...c, icon: c.status === 'done' ? 'done' : 'queued', statusText: c.status === 'done' ? 'Done' : '' })));
  updateExtractBtn();

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
    const isPolling = !!extractPollInterval;
    const cls = c.icon === 'done' ? ' done' : c.icon === 'progress' ? ' in-progress' : c.icon === 'error' ? '' : (isPolling ? ' queued' : '');
    item.className = 'card-item' + cls;

    const iconMap = { done: '&#10003;', error: '&#10007;', progress: '&#9679;', queued: '&#9675;' };
    const cardName = c.name || c.card_id || '';
    const encodedName = encodeURIComponent(cardName);
    let checkbox = '';
    if ((c.icon === 'queued' || c.icon === 'done') && !isPolling) {
      checkbox = '<input type="checkbox" class="extract-check" data-card="' + cardName.replace(/"/g, '&quot;') + '" onchange="updateExtractBtn()" style="margin-right:4px;">';
    }
    if (c.icon === 'done') {
      item.style.cursor = 'pointer';
      item.onclick = function(e) { if (e.target.classList.contains('extract-check')) return; location.hash = 'review/' + encodedName; };
    }
    item.innerHTML =
      checkbox +
      '<span class="icon ' + c.icon + '">' + (iconMap[c.icon] || '') + '</span>' +
      '<span class="name">' + cardName + '</span>' +
      (c.icon !== 'queued' ? '<span class="status-text">' + (c.statusText || c.status || '') + '</span>' : '');

    list.appendChild(item);
  });
}

function getSelectedCards() {
  return Array.from(document.querySelectorAll('.extract-check:checked')).map(cb => cb.dataset.card);
}

function updateExtractBtn() {
  const selected = getSelectedCards().length;
  const btn = document.getElementById('extract-btn');
  btn.textContent = selected > 0 ? 'Extract Selected (' + selected + ')' : 'Extract Selected';
  btn.disabled = selected === 0;
}

function toggleSelectAll(checked) {
  document.querySelectorAll('.extract-check').forEach(cb => { cb.checked = checked; });
  updateExtractBtn();
}

async function triggerExtractSelected() {
  const cards = getSelectedCards();
  if (cards.length === 0) return;
  const errorEl = document.getElementById('extract-error');
  errorEl.style.display = 'none';
  const resp = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cards: cards }),
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

  extractStartTime = Date.now();
  if (extractPollInterval) clearInterval(extractPollInterval);
  extractPollInterval = setInterval(pollExtractStatus, 1500);
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(updateTimerDisplay, 1000);
  pollExtractStatus();
}

let extractStartTime = null;
let timerInterval = null;

function formatElapsed(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? m + 'm ' + sec + 's' : sec + 's';
}

function updateTimerDisplay() {
  const totalEl = document.getElementById('extract-elapsed');
  if (totalEl && extractStartTime) {
    totalEl.textContent = 'Total: ' + formatElapsed(Date.now() - extractStartTime);
  }
}

async function pollExtractStatus() {
  const [statusResp, cardsResp] = await Promise.all([
    fetch('/api/extract/status'),
    fetch('/api/extract/cards'),
  ]);
  const status = await statusResp.json();
  const allCards = (await cardsResp.json()).cards;

  if (!extractStartTime) extractStartTime = Date.now();

  // Update summary
  const summary = document.getElementById('extract-summary');
  summary.innerHTML =
    '<span>' + status.done.length + ' done</span>' +
    (status.in_flight.length > 0 ? '<span>' + status.in_flight.length + ' in progress</span>' : '') +
    '<span>' + status.queue.length + ' queued</span>' +
    (status.errors.length > 0 ? '<span style="color:#e74c3c;">' + status.errors.length + ' error(s)</span>' : '') +
    '<span id="extract-elapsed" style="margin-left:auto; color:#666;"></span>';

  // Update in-flight cards display
  const inFlightEl = document.getElementById('in-flight-cards');
  if (status.in_flight.length > 0) {
    inFlightEl.style.display = '';
    let html = '';
    status.in_flight.forEach(function(card) {
      const stageLabel = card.stage.replace(/_/g, ' ');
      html += '<div class="in-flight-item">' +
        '<div class="dot"></div>' +
        '<span class="name">' + card.card_id + '</span>' +
        '<span class="label">' + stageLabel + '</span>' +
        '</div>';
    });
    inFlightEl.innerHTML = html;
  } else {
    inFlightEl.style.display = 'none';
  }

  // Build worker status map for card list
  var workerMap = {};
  status.done.forEach(function(name) { workerMap[name] = { icon: 'done', statusText: 'Done' }; });
  status.in_flight.forEach(function(card) {
    var stageLabel = card.stage.replace(/_/g, ' ');
    workerMap[card.card_id] = { icon: 'progress', statusText: stageLabel };
  });
  status.errors.forEach(function(e) { workerMap[e.card_id] = { icon: 'error', statusText: e.reason }; });
  status.queue.forEach(function(name) { workerMap[name] = { icon: 'queued', statusText: 'Queued' }; });

  // Merge: show all cards, overlay worker status on matching ones
  var merged = allCards.map(function(c) {
    var w = workerMap[c.name];
    if (w) return { name: c.name, icon: w.icon, statusText: w.statusText, status: w.icon };
    return { name: c.name, icon: c.status === 'done' ? 'done' : 'queued', statusText: c.status === 'done' ? 'Done' : c.status, status: c.status };
  });
  renderExtractList(merged);

  // Update total elapsed
  updateTimerDisplay();

  // Check if done
  if (status.status === 'idle' || status.status === 'cancelled') {
    clearInterval(extractPollInterval);
    extractPollInterval = null;
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    extractStartTime = null;
    document.getElementById('extract-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = 'none';
    renderExtractList(merged);
    updateExtractBtn();
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
  btn.textContent = '\u00d7';
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
