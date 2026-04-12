/* ---- Navigation ---- */
async function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));

  const section = document.getElementById('section-' + name);
  if (section) section.classList.add('active');

  const tab = document.querySelector('.nav-tab[href="#' + name + '"]');
  if (tab) tab.classList.add('active');

  if (name === 'match') await loadMatchState();
  if (name === 'extract') await loadExtractCards();
  if (name === 'review') await initReview();
  updateExportCount();
}

async function handleHash() {
  const hash = location.hash.slice(1) || 'match';
  if (hash.startsWith('review/')) {
    const cardId = decodeURIComponent(hash.slice(7));
    await showSection('review');
    reviewJumpTo(cardId);
  } else {
    await showSection(hash);
  }
  updateExportCount();
}

window.addEventListener('hashchange', handleHash);

/* ---- Match ---- */
let matchData = null;
let findMatchFilename = null;
let findMatchCandidates = [];

async function scanImages() {
  var btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = 'Scanning...';

  var resp = await fetch('/api/match/scan');
  matchData = await resp.json();

  btn.disabled = false;
  btn.textContent = 'Re-scan';
  renderMatchUI();
}

async function loadMatchState() {
  var resp = await fetch('/api/match/state');
  var data = await resp.json();
  if (data.pairs.length > 0 || data.unmatched.length > 0) {
    matchData = data;
    document.getElementById('scan-btn').textContent = 'Re-scan';
    renderMatchUI();
  } else {
    await scanImages();
  }
}

function formatFileSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return bytes + ' B';
}

function formatMeta(meta) {
  var parts = [meta.width + ' \u00d7 ' + meta.height + ' px'];
  if (meta.dpi) parts.push(meta.dpi + ' DPI');
  parts.push(formatFileSize(meta.file_size_bytes));
  return parts.join(' \u00b7 ');
}

function scoreClass(score) {
  if (score >= 80) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

function escapeAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/'/g, '&#39;').replace(/"/g, '&quot;');
}

function openOverlay(src) {
  var overlay = document.getElementById('image-overlay');
  document.getElementById('overlay-img').src = src;
  overlay.classList.add('visible');
}

function closeOverlay() {
  document.getElementById('image-overlay').classList.remove('visible');
}

function clickableImg(src) {
  return 'onclick="event.stopPropagation(); openOverlay(\'' + escapeAttr(src) + '\')"';
}

function renderMatchUI() {
  if (!matchData) return;

  // Summary
  var summary = document.getElementById('match-summary');
  var parts = [];
  if (matchData.confirmed_count > 0) parts.push('<span class="confirmed">\u2713 ' + matchData.confirmed_count + ' confirmed</span>');
  if (matchData.needs_review > 0) parts.push('<span class="review">\u26a0 ' + matchData.needs_review + ' needs review</span>');
  if (matchData.unmatched_count > 0) parts.push('<span class="unmatched-count">\u2717 ' + matchData.unmatched_count + ' unmatched</span>');
  summary.innerHTML = parts.join(' &middot; ');

  // Show/hide buttons
  document.getElementById('confirm-all-btn').style.display = matchData.needs_review > 0 ? '' : 'none';
  document.getElementById('proceed-extract-btn').style.display = matchData.all_resolved ? '' : 'none';

  // Pair list
  var pairList = document.getElementById('match-pair-list');
  pairList.innerHTML = '';
  matchData.pairs.forEach(function(pair) {
    var row = document.createElement('div');
    row.className = 'match-pair-row';

    var isConfirmed = pair.status === 'confirmed' || pair.status === 'auto_confirmed';
    var statusText = isConfirmed ? '\u2713 Confirmed' : 'Needs review';
    var statusClass = isConfirmed ? 'auto' : 'review';

    var ea = escapeAttr(pair.image_a.filename);
    var eb = escapeAttr(pair.image_b.filename);

    row.innerHTML =
      '<div class="match-pair-header">' +
        '<span class="match-score ' + scoreClass(pair.score) + '">' + pair.score + '%</span>' +
        '<span class="match-status-text ' + statusClass + '">' + statusText + '</span>' +
      '</div>' +
      '<div class="match-pair-images">' +
        '<div class="match-image-card">' +
          '<img src="/images/' + encodeURIComponent(pair.image_a.filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(pair.image_a.filename)) + '>' +
          '<div class="match-image-meta">' +
            '<div class="filename">' + pair.image_a.filename + '</div>' +
            '<div class="details">' + formatMeta(pair.image_a) + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="match-pair-link">\u21c4</div>' +
        '<div class="match-image-card">' +
          '<img src="/images/' + encodeURIComponent(pair.image_b.filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(pair.image_b.filename)) + '>' +
          '<div class="match-image-meta">' +
            '<div class="filename">' + pair.image_b.filename + '</div>' +
            '<div class="details">' + formatMeta(pair.image_b) + '</div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="match-pair-actions">' +
        '<button class="btn" style="border:1px solid #ccc; background:#fff; color:#555;" onclick="swapPair(\'' + ea + '\', \'' + eb + '\')">Swap</button>' +
        '<button class="btn btn-danger" onclick="unmatchPair(\'' + ea + '\', \'' + eb + '\')">Unmatch</button>' +
        (isConfirmed ? '' : '<button class="btn btn-success" onclick="confirmPair(\'' + ea + '\', \'' + eb + '\')">Confirm \u2713</button>') +
      '</div>';

    pairList.appendChild(row);
  });

  // Unmatched
  var unmatchedDiv = document.getElementById('match-unmatched');
  unmatchedDiv.innerHTML = '';
  if (matchData.unmatched.length > 0) {
    unmatchedDiv.innerHTML = '<div class="match-unmatched-title">Unmatched Images (' + matchData.unmatched.length + ')</div>';
    var grid = document.createElement('div');
    grid.className = 'match-unmatched-grid';
    matchData.unmatched.forEach(function(img) {
      var card = document.createElement('div');
      card.className = 'match-unmatched-card';
      card.innerHTML =
        '<img src="/images/' + encodeURIComponent(img.filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(img.filename)) + '>' +
        '<div class="filename">' + img.filename + '</div>' +
        '<div class="details">' + formatMeta(img) + '</div>' +
        '<button class="btn btn-primary" style="font-size:11px; padding:4px 8px;" onclick="openFindMatch(\'' + escapeAttr(img.filename) + '\')">Find match...</button>';
      grid.appendChild(card);
    });
    unmatchedDiv.appendChild(grid);
  }

  // Singles
  if (matchData.singles && matchData.singles.length > 0) {
    var singlesTitle = document.createElement('div');
    singlesTitle.className = 'match-unmatched-title';
    singlesTitle.style.color = '#888';
    singlesTitle.style.marginTop = '16px';
    singlesTitle.textContent = 'Singles (' + matchData.singles.length + ')';
    unmatchedDiv.appendChild(singlesTitle);
    var sGrid = document.createElement('div');
    sGrid.className = 'match-unmatched-grid';
    matchData.singles.forEach(function(single) {
      var card = document.createElement('div');
      card.className = 'match-unmatched-card';
      card.style.borderColor = '#888';
      card.innerHTML =
        '<img src="/images/' + encodeURIComponent(single.filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(single.filename)) + '>' +
        '<div class="filename">' + single.filename + '</div>' +
        '<div class="details" style="color:#888;">Marked as single</div>';
      sGrid.appendChild(card);
    });
    unmatchedDiv.appendChild(sGrid);
  }
}

async function confirmPair(a, b) {
  await fetch('/api/match/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function unmatchPair(a, b) {
  await fetch('/api/match/unmatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function confirmAllPairs() {
  await fetch('/api/match/confirm-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function swapPair(a, b) {
  await fetch('/api/match/swap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
  // Flash the swapped pair to give visual feedback
  var rows = document.querySelectorAll('.match-pair-row');
  rows.forEach(function(row) {
    // b is now image_a after swap
    if (row.querySelector('.filename') && row.querySelector('.filename').textContent === b) {
      row.style.transition = 'background 0.3s';
      row.style.background = '#e8f5e9';
      setTimeout(function() { row.style.background = '#fff'; }, 600);
    }
  });
}

async function openFindMatch(filename) {
  findMatchFilename = filename;
  document.getElementById('match-pair-list').style.display = 'none';
  document.getElementById('match-unmatched').style.display = 'none';
  document.querySelector('.match-controls').style.display = 'none';

  var panel = document.getElementById('find-match-panel');
  panel.style.display = '';
  document.getElementById('find-match-name').textContent = filename;

  // Show selected image
  var selectedDiv = document.getElementById('find-match-selected');
  selectedDiv.innerHTML =
    '<img src="/images/' + encodeURIComponent(filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(filename)) + '>' +
    '<div><div style="font-weight:600;">' + filename + '</div></div>';

  // Fetch scores
  var resp = await fetch('/api/match/scores', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: filename }),
  });
  findMatchCandidates = await resp.json();

  document.getElementById('find-match-filter').value = '';
  renderFindMatchCandidates(findMatchCandidates);
}

function renderFindMatchCandidates(candidates) {
  var container = document.getElementById('find-match-candidates');
  container.innerHTML = '';
  candidates.forEach(function(c) {
    var div = document.createElement('div');
    div.className = 'find-match-candidate';
    div.innerHTML =
      '<img src="/images/' + encodeURIComponent(c.filename) + '" alt="" ' + clickableImg('/images/' + encodeURIComponent(c.filename)) + '>' +
      '<div class="info">' +
        '<div class="filename">' + c.filename + '</div>' +
        '<div class="details">' + formatMeta(c) + '</div>' +
      '</div>' +
      '<div class="score-and-action">' +
        '<span class="match-score ' + scoreClass(c.score) + '">' + c.score + '%</span>' +
        '<button class="btn btn-success" style="font-size:11px; padding:3px 10px;" onclick="manualPair(\'' + escapeAttr(findMatchFilename) + '\', \'' + escapeAttr(c.filename) + '\')">Pair</button>' +
      '</div>';
    container.appendChild(div);
  });

  if (candidates.length === 0) {
    container.innerHTML = '<div style="color:#888; padding:16px; text-align:center;">No other unmatched images</div>';
  }
}

function filterFindMatch() {
  var query = document.getElementById('find-match-filter').value.toLowerCase();
  var filtered = findMatchCandidates.filter(function(c) {
    return c.filename.toLowerCase().includes(query);
  });
  renderFindMatchCandidates(filtered);
}

async function manualPair(a, b) {
  await fetch('/api/match/pair', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  // Auto-confirm the manual pair so user doesn't have to confirm again
  await fetch('/api/match/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_a: a, image_b: b }),
  });
  closeFindMatch();
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

async function markSingleFromPanel() {
  await fetch('/api/match/single', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: findMatchFilename }),
  });
  closeFindMatch();
  var resp = await fetch('/api/match/state');
  matchData = await resp.json();
  renderMatchUI();
}

function closeFindMatch() {
  document.getElementById('find-match-panel').style.display = 'none';
  document.getElementById('match-pair-list').style.display = '';
  document.getElementById('match-unmatched').style.display = '';
  document.querySelector('.match-controls').style.display = '';
  findMatchFilename = null;
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
    const cardId = c.card_id || '';
    const displayName = c.derived_name || [c.front, c.back].filter(Boolean).join(', ') || cardId;
    let checkbox = '';
    if ((c.icon === 'queued' || c.icon === 'done') && !isPolling) {
      checkbox = '<input type="checkbox" class="extract-check" data-card="' + cardId.replace(/"/g, '&quot;') + '" onchange="updateExtractBtn()" style="margin-right:4px;">';
    }
    if (c.icon === 'done') {
      item.style.cursor = 'pointer';
      item.onclick = function(e) { if (e.target.classList.contains('extract-check')) return; location.hash = 'review/' + encodeURIComponent(cardId); };
    }
    item.innerHTML =
      checkbox +
      '<span class="icon ' + c.icon + '">' + (iconMap[c.icon] || '') + '</span>' +
      '<span class="name">' + displayName + '</span>' +
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
    var w = workerMap[c.card_id];
    if (w) return { card_id: c.card_id, derived_name: c.derived_name, front: c.front, back: c.back, icon: w.icon, statusText: w.statusText, status: w.icon };
    return { card_id: c.card_id, derived_name: c.derived_name, front: c.front, back: c.back, icon: c.status === 'done' ? 'done' : 'queued', statusText: c.status === 'done' ? 'Done' : c.status, status: c.status };
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
  }
  await loadReviewCard(reviewIndex);
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
  document.getElementById('review-derived-name').textContent = reviewCurrentCard.derived_name || '';
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

  // Reset dirty tracking on all form fields
  ['f-first_name', 'f-last_name', 'f-birth_date', 'f-birth_place',
   'f-death_date', 'f-death_place', 'f-age_at_death'].forEach(function(id) {
    document.getElementById(id).oninput = function() {
      markFormDirty();
      computeDerivedName();
    };
  });

  showSide('back');
}

function addSpouseInput(value) {
  const container = document.getElementById('spouses-list');
  const div = document.createElement('div');
  div.className = 'spouse-entry';
  const input = document.createElement('input');
  input.value = value;
  input.oninput = markFormDirty;
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

function computeDerivedName() {
  var months = {
    '01': 'januari', '02': 'februari', '03': 'maart', '04': 'april',
    '05': 'mei', '06': 'juni', '07': 'juli', '08': 'augustus',
    '09': 'september', '10': 'oktober', '11': 'november', '12': 'december'
  };
  var parts = [];
  var lastName = document.getElementById('f-last_name').value.trim();
  var firstName = document.getElementById('f-first_name').value.trim();
  var birthPlace = document.getElementById('f-birth_place').value.trim();
  var deathDate = document.getElementById('f-death_date').value.trim();

  if (lastName) parts.push(lastName);
  if (firstName) parts.push(firstName);
  if (birthPlace) parts.push(birthPlace);
  parts.push('bidprentje');

  if (deathDate && deathDate.match(/^\d{4}-\d{2}-\d{2}$/)) {
    var dateParts = deathDate.split('-');
    var month = months[dateParts[1]];
    if (month) parts.push(dateParts[2] + ' ' + month + ' ' + dateParts[0]);
  }

  document.getElementById('review-derived-name').textContent = parts.join(' ');
}

function markFormDirty() {
  const btn = document.getElementById('approve-btn');
  if (btn.textContent === 'Saved!') {
    btn.textContent = 'Approve';
    btn.classList.remove('btn-success');
    btn.classList.add('btn-primary');
  }
}

/* ---- Export ---- */
async function updateExportCount() {
  const resp = await fetch('/api/export/count');
  const data = await resp.json();
  const btn = document.getElementById('export-btn');
  btn.textContent = 'Export (' + data.count + ')';
  btn.disabled = data.count === 0;
}

async function triggerExport() {
  const btn = document.getElementById('export-btn');
  btn.disabled = true;
  btn.textContent = 'Exporting...';

  const resp = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  const data = await resp.json();

  btn.textContent = 'Exported ' + data.exported + ' cards!';
  setTimeout(function() {
    updateExportCount();
  }, 2000);
}

/* ---- Init ---- */
handleHash();
