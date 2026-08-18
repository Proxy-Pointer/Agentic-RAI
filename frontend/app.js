/* ═══════════════════════════════════════════════════════════════════════
   NovaCorp Responsible AI Demo — Frontend Logic
   Handles: SSE stream, chat, HITL, ACL viewer, safety log, audit
═══════════════════════════════════════════════════════════════════════ */

const API = '';  // Same origin

// ── State ────────────────────────────────────────────────────────────────────
let currentUser = 'alice';
let activeTab   = 'chat';
let isProcessing = false;
let eventSource  = null;
let requestStartTime = {};

// Safety counters
let safetyDirect   = 0;
let safetyIndirect = 0;

// HITL pending count
let hitlPendingCount = 0;

// Governance log (recent classifications)
let govLog = [];

// ── SSE Connection ───────────────────────────────────────────────────────────
function connectSSE() {
  if (eventSource) eventSource.close();

  eventSource = new EventSource(`${API}/api/stream`);

  eventSource.onopen = () => {
    setConnStatus('connected', 'Live');
  };

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleEvent(data);
    } catch (_) {}
  };

  eventSource.onerror = () => {
    setConnStatus('error', 'Disconnected');
    setTimeout(connectSSE, 3000);
  };
}

function setConnStatus(state, label) {
  const dot   = document.getElementById('conn-dot');
  const lbl   = document.getElementById('conn-label');
  dot.className = `status-dot ${state}`;
  lbl.textContent = label;
}

// ── Event Router ─────────────────────────────────────────────────────────────
function handleEvent(data) {
  if (data.type === 'heartbeat') return;

  if (data.type === 'trace') {
    appendTrace(data);
    updateMetrics(data);
  }

  if (data.type === 'response' || data.type === 'blocked' || data.type === 'hitl' || data.type === 'supervised') {
    finishProcessing(data);
  }

  if (data.type === 'hitl_result') {
    handleHITLResult(data);
  }

  // Safety events
  if (data.type === 'trace') {
    if (data.status === 'blocked' && data.agent === 'safety_guard') {
      if (data.event === 'pre_filter_blocked') {
        safetyDirect++;
        logSafetyEvent('DIRECT', data.detail, data.request_id);
      }
      if (data.event === 'indirect_injection') {
        safetyIndirect++;
        logSafetyEvent('INDIRECT', data.detail, data.request_id);
      }
    }
    updateSafetyCounters();

    // Governance log
    if (data.event === 'classified') {
      const tierMatch = data.detail.match(/Tier:\s*(\w+)/);
      if (tierMatch) {
        addGovEntry(data.request_id, currentUser, tierMatch[1], data.detail);
      }
    }
  }
}

// ── Trace Panel ──────────────────────────────────────────────────────────────
function appendTrace(data) {
  const log = document.getElementById('trace-log');

  // Clear placeholder
  const placeholder = log.querySelector('div[style]');
  if (placeholder) placeholder.remove();

  const entry = document.createElement('div');
  entry.className = `trace-entry ${data.status}`;
  entry.innerHTML = `
    <span class="trace-t">${data.t_ms}ms</span>
    <span class="trace-agent ${data.agent}">${data.agent}</span>
    <span class="trace-detail">${escHtml(data.detail)}</span>
  `;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function clearTrace() {
  const log = document.getElementById('trace-log');
  log.innerHTML = '<div style="color:var(--text-muted);font-size:0.72rem;padding:8px;">Waiting for query…</div>';
  resetMetrics();
}

function updateMetrics(data) {
  if (!requestStartTime[data.request_id]) {
    requestStartTime[data.request_id] = Date.now();
  }

  const elapsed = Date.now() - requestStartTime[data.request_id];
  document.getElementById('m-latency').textContent = elapsed;

  // Extract chunk count from detail
  const chunkMatch = data.detail && data.detail.match(/(\d+)\s+chunk/);
  if (chunkMatch) {
    document.getElementById('m-chunks').textContent = chunkMatch[1];
  }

  // Extract token count
  const tokMatch = data.detail && data.detail.match(/(\d+)\s+in\s+\/\s+(\d+)\s+out/);
  if (tokMatch) {
    document.getElementById('m-tokens').textContent =
      `${parseInt(tokMatch[1]) + parseInt(tokMatch[2])}`;
  }
}

function resetMetrics() {
  document.getElementById('m-latency').textContent = '—';
  document.getElementById('m-tokens').textContent  = '—';
  document.getElementById('m-chunks').textContent  = '—';
}

// ── Chat ─────────────────────────────────────────────────────────────────────
function handleKey(e) {
  if (!e.shiftKey && e.key === 'Enter') {
    e.preventDefault();
    sendQuery();
  }
  // Auto-resize
  const ta = document.getElementById('query-input');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
}

async function sendQuery(prefillQuery, prefillUser) {
  if (isProcessing) return;

  const queryEl = document.getElementById('query-input');
  const query = prefillQuery || queryEl.value.trim();
  const user  = prefillUser  || currentUser;

  if (!query) return;

  setProcessing(true);
  queryEl.value = '';
  queryEl.style.height = 'auto';
  requestStartTime = {};

  // Show user message
  appendMessage('user', query, null, user);

  // Show typing indicator
  const typingId = showTyping();

  // Track request
  const requestId = crypto.randomUUID();
  requestStartTime[requestId] = Date.now();

  try {
    const resp = await fetch(`${API}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user, query, request_id: requestId }),
    });
    if (!resp.ok) throw new Error('Network error');
    // Response will arrive via SSE
  } catch (err) {
    removeTyping(typingId);
    appendMessage('agent', `⚠️ Connection error: ${err.message}`, 'blocked', user);
    setProcessing(false);
  }

  // Safety: remove typing after 30s if no SSE response
  setTimeout(() => {
    removeTyping(typingId);
    setProcessing(false);
  }, 30000);

  window._lastTypingId = typingId;
}

function finishProcessing(data) {
  removeTyping(window._lastTypingId);
  setProcessing(false);

  const bubbleClass = data.type === 'blocked' ? 'blocked' : data.type === 'hitl' ? 'hitl' : '';
  appendMessage('agent', data.message, bubbleClass, data.user, data.tier);

  if (data.type === 'hitl') {
    showHITLCard(data);
  }

  // Refresh audit if on audit tab
  if (activeTab === 'audit') loadAudit();
}

function appendMessage(role, text, bubbleClass, user, tier) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const tierBadge = tier ? `<span class="tier-badge tier-${tier}">${tier}</span>` : '';
  const metaText  = role === 'user'
    ? `<span>${user || currentUser}</span>`
    : `<span>NovaCorp HR Agent</span>${tierBadge}`;

  div.innerHTML = `
    <div class="message-bubble ${bubbleClass || ''}">${renderMarkdown(text)}</div>
    <div class="msg-meta">${metaText}<span>${new Date().toLocaleTimeString()}</span></div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function renderMarkdown(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
}

function showTyping() {
  const id = 'typing-' + Date.now();
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.id = id;
  div.className = 'message agent';
  div.innerHTML = `<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeTyping(id) {
  if (id) document.getElementById(id)?.remove();
}

function setProcessing(state) {
  isProcessing = state;
  const btn     = document.getElementById('send-btn');
  const label   = document.getElementById('send-label');
  const spinner = document.getElementById('send-spinner');
  btn.disabled   = state;
  label.style.display   = state ? 'none' : 'inline';
  spinner.style.display = state ? 'inline-block' : 'none';
}

// ── HITL Card ─────────────────────────────────────────────────────────────────
function showHITLCard(data) {
  const container = document.getElementById('chat-messages');
  const card = document.createElement('div');
  card.className = 'hitl-card';
  card.id = `hitl-card-${data.task_id}`;
  card.innerHTML = `
    <h3>⚠️ Human Approval Required</h3>
    <span class="risk-tag">HIGH RISK ACTION</span>
    <div class="action-desc">${escHtml(data.message)}</div>
    <div class="hitl-actions">
      <button class="btn btn-success btn-sm" onclick="decideHITL('${data.task_id}', 'approve')">✅ Approve</button>
      <button class="btn btn-danger btn-sm"  onclick="decideHITL('${data.task_id}', 'reject')">❌ Reject</button>
    </div>
  `;
  container.appendChild(card);
  container.scrollTop = container.scrollHeight;

  // Update HITL badge
  hitlPendingCount++;
  updateHITLBadge();
  showTab('hitl');
  loadHITL();
}

async function decideHITL(taskId, action) {
  const note = action === 'reject' ? prompt('Rejection reason (optional):') || '' : '';
  try {
    await fetch(`${API}/api/hitl/${taskId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    });
    document.getElementById(`hitl-card-${taskId}`)?.remove();
    hitlPendingCount = Math.max(0, hitlPendingCount - 1);
    updateHITLBadge();
    loadHITL();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

function handleHITLResult(data) {
  appendMessage('agent', data.message, data.decision === 'APPROVED' ? '' : 'blocked', data.user);
  loadHITL();
  if (activeTab === 'audit') loadAudit();
}

async function loadHITL() {
  try {
    const all = await fetch(`${API}/api/hitl/all`).then(r => r.json());

    const pending = all.filter(t => t.status === 'PENDING');
    const history = all.filter(t => t.status !== 'PENDING');

    hitlPendingCount = pending.length;
    updateHITLBadge();

    const pendingEl = document.getElementById('hitl-pending-list');
    if (pending.length === 0) {
      pendingEl.innerHTML = '<div class="empty-state"><div class="icon">✅</div>No pending approvals.</div>';
    } else {
      pendingEl.innerHTML = pending.map(t => `
        <div class="hitl-card" id="hitl-list-${t.task_id}">
          <h3>⚠️ ${escHtml(t.action_description)}</h3>
          <span class="risk-tag">${escHtml(t.risk_label)}</span>
          <div class="action-desc">
            <strong>User:</strong> ${escHtml(t.user)}<br>
            <strong>Query:</strong> ${escHtml(t.query)}<br>
            <strong>Created:</strong> ${new Date(t.created_at).toLocaleTimeString()}
          </div>
          <div class="hitl-actions">
            <button class="btn btn-success btn-sm" onclick="decideHITL('${t.task_id}', 'approve')">✅ Approve</button>
            <button class="btn btn-danger btn-sm"  onclick="decideHITL('${t.task_id}', 'reject')">❌ Reject</button>
          </div>
        </div>
      `).join('');
    }

    const histEl = document.getElementById('hitl-history-list');
    histEl.innerHTML = history.slice().reverse().map(t => `
      <div class="doc-row">
        <div class="doc-title">
          <div style="font-size:0.8rem;">${escHtml(t.action_description)}</div>
          <div style="font-size:0.72rem;color:var(--text-muted);">${escHtml(t.user)} · ${escHtml(t.query.substring(0,60))}</div>
        </div>
        <span class="outcome-badge outcome-${t.status === 'APPROVED' ? 'SUCCESS' : 'REJECTED'}">${t.status}</span>
        <span style="font-size:0.72rem;color:var(--text-muted);">${t.decided_at ? new Date(t.decided_at).toLocaleTimeString() : ''}</span>
      </div>
    `).join('') || '<div style="color:var(--text-muted);font-size:0.82rem;">No decisions yet.</div>';

  } catch (e) {
    console.error('HITL load error:', e);
  }
}

function updateHITLBadge() {
  const badge = document.getElementById('hitl-badge');
  if (hitlPendingCount > 0) {
    badge.style.display = 'inline';
    badge.textContent = hitlPendingCount;
  } else {
    badge.style.display = 'none';
  }
}

// ── ACL / Docs ────────────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    const docs = await fetch(`${API}/api/documents`).then(r => r.json());
    const userAcl  = { alice: 0, bob: 1, admin: 3 }[currentUser] ?? 0;
    const aclLabel = { alice: 'PUBLIC', bob: 'HR_ONLY', admin: 'ALL' }[currentUser] ?? 'PUBLIC';

    document.getElementById('acl-current-user').textContent = currentUser;
    document.getElementById('acl-current-level').textContent = userAcl;

    const list = document.getElementById('docs-list');
    if (docs.length === 0) {
      list.innerHTML = '<div class="empty-state"><div class="icon">📂</div>No documents found. Server may still be seeding.</div>';
      return;
    }

    const ACL_LEVELS = { ALL: 0, HR_ONLY: 1, ADMIN: 2, PII: 3 };

    list.innerHTML = docs.map(doc => {
      const docLevel   = doc.acl_level ?? 0;
      const accessible = docLevel <= userAcl;
      const aclClass   = `acl-${doc.acl}`;

      return `
        <div class="doc-row" style="${!accessible ? 'opacity:0.45' : ''}">
          <div style="width:20px;text-align:center;">${accessible ? '✅' : '🔒'}</div>
          <div class="doc-title">
            <div>${escHtml(doc.title)}</div>
            <div style="font-size:0.72rem;color:var(--text-muted);">acl_level=${docLevel} · ${escHtml(doc.category)}</div>
          </div>
          <span class="doc-acl ${aclClass}">${escHtml(doc.acl)}</span>
          <button class="tamper-toggle ${doc.tampered ? 'tampered' : ''}"
                  onclick="toggleTamper('${escHtml(doc.doc_id)}', this)"
                  title="Toggle tamper state (integrity demo)">
            ${doc.tampered ? '⚠️ Tampered' : '🔐 Intact'}
          </button>
        </div>
      `;
    }).join('');
  } catch (e) {
    document.getElementById('docs-list').innerHTML =
      '<div class="empty-state"><div class="icon">⚠️</div>Could not load documents.</div>';
  }
}

async function toggleTamper(docId, btn) {
  try {
    const result = await fetch(`${API}/api/admin/tamper/${docId}`, { method: 'POST' }).then(r => r.json());
    btn.className = `tamper-toggle ${result.tampered ? 'tampered' : ''}`;
    btn.textContent = result.tampered ? '⚠️ Tampered' : '🔐 Intact';
  } catch(e) { alert('Error: ' + e.message); }
}



// ── Safety Log ────────────────────────────────────────────────────────────────
const safetyEvents = [];

function logSafetyEvent(type, detail, requestId) {
  safetyEvents.unshift({ type, detail, requestId, ts: new Date() });

  const log = document.getElementById('safety-log');
  const placeholder = log.querySelector('.empty-state');
  if (placeholder) placeholder.remove();

  const banner = document.createElement('div');
  banner.className = `alert-banner ${type === 'DIRECT' ? 'alert-danger' : 'alert-warning'}`;
  banner.innerHTML = `
    <span>${type === 'DIRECT' ? '🚫' : '⚡'}</span>
    <div>
      <strong>${type === 'DIRECT' ? 'Direct Injection / Jailbreak' : 'Indirect Injection (in document)'}</strong>
      <div style="margin-top:4px;font-size:0.78rem;">${escHtml(detail)}</div>
      <div style="margin-top:4px;font-size:0.7rem;color:var(--text-muted);">${new Date().toLocaleTimeString()} · req: ${requestId?.substring(0,8)}</div>
    </div>
  `;
  log.prepend(banner);
}

function updateSafetyCounters() {
  document.getElementById('safety-direct-count').textContent   = safetyDirect;
  document.getElementById('safety-indirect-count').textContent = safetyIndirect;
}

// ── Governance Log ────────────────────────────────────────────────────────────
function addGovEntry(requestId, user, tier, detail) {
  govLog.unshift({ requestId, user, tier, detail, ts: new Date() });

  const log = document.getElementById('gov-log');
  const placeholder = log.querySelector('.empty-state');
  if (placeholder) placeholder.remove();

  const entry = document.createElement('div');
  entry.className = 'doc-row';
  entry.innerHTML = `
    <span class="tier-badge tier-${tier}">${tier}</span>
    <div class="doc-title">
      <div style="font-size:0.8rem;">${escHtml(detail.replace(/Tier:\s*\w+\s*—\s*/, ''))}</div>
      <div style="font-size:0.72rem;color:var(--text-muted);">User: ${escHtml(user)} · ${new Date().toLocaleTimeString()}</div>
    </div>
  `;
  log.prepend(entry);
}

// ── Audit ─────────────────────────────────────────────────────────────────────
function renderAuditRows(entries) {
  const tbody = document.getElementById('audit-tbody');
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px;">No matching audit entries.</td></tr>';
    return;
  }
  tbody.innerHTML = entries.slice().reverse().map(e => `
    <tr>
      <td style="font-family:monospace;font-size:0.72rem;white-space:nowrap;">${new Date(e.timestamp).toLocaleTimeString()}</td>
      <td><span class="tier-badge tier-${e.user === 'alice' ? 'AUTONOMOUS' : e.user === 'bob' ? 'SUPERVISED' : 'REQUIRES_HITL'}" style="text-transform:none;">${escHtml(e.user)}</span></td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(e.query)}">${escHtml(e.query.substring(0,50))}${e.query.length>50?'…':''}</td>
      <td><span class="tier-badge tier-${e.autonomy_tier}">${e.autonomy_tier}</span></td>
      <td>${e.safety_pre === 'BLOCKED' ? '<span style="color:var(--danger)">🚫 BLOCKED</span>' : '<span style="color:var(--success)">✅ PASS</span>'}</td>
      <td style="font-family:monospace;">${e.chunks_retrieved}</td>
      <td>${e.hitl_decision ? `<span class="outcome-badge outcome-${e.hitl_decision === 'APPROVED' ? 'SUCCESS' : 'REJECTED'}">${e.hitl_decision}</span>` : '<span style="color:var(--text-muted)">—</span>'}</td>
      <td><span class="outcome-badge outcome-${e.outcome}">${e.outcome}</span></td>
    </tr>
  `).join('');
}

async function loadAudit() {
  // Hide compliance report — show raw audit log table
  document.getElementById('compliance-report').style.display = 'none';
  document.getElementById('audit-content').style.display = 'block';

  const userFilter = document.getElementById('audit-user-filter').value;
  const url = userFilter ? `${API}/api/audit?user=${userFilter}` : `${API}/api/audit`;
  try {
    const entries = await fetch(url).then(r => r.json());
    renderAuditRows(entries);
  } catch (e) {
    console.error('Audit load error:', e);
  }
}

async function showCompliance() {
  showTab('audit');
  // Hide raw audit table, show compliance stats only
  document.getElementById('audit-content').style.display = 'none';
  const reportEl = document.getElementById('compliance-report');
  reportEl.style.display = 'block';

  try {
    const s = await fetch(`${API}/api/audit/summary`).then(r => r.json());
    const grid = document.getElementById('compliance-grid');

    const card = (val, label, color, filterFn) => {
      const el = document.createElement('div');
      el.className = 'stat-card clickable';
      el.title = `Click to filter audit log: ${label}`;
      el.innerHTML = `<div class="stat-val" style="color:${color}">${val}</div><div class="stat-label">${label}</div>`;
      el.onclick = filterFn;
      return el;
    };

    grid.innerHTML = '';
    grid.appendChild(card(s.total_queries,      'Total Queries',       'var(--cyan-400)',   () => filterAudit('all', '')));
    grid.appendChild(card(s.blocked_by_safety,  'Blocked by Safety',   'var(--danger)',     () => filterAudit('outcome', 'BLOCKED_INJECTION')));
    grid.appendChild(card(s.acl_denials,        'ACL Denials',         'var(--warning)',    () => filterAudit('outcome', 'REJECTED')));
    grid.appendChild(card(s.hitl_escalations,   'HITL Escalations',    'var(--hitl)',       () => filterAudit('outcome', 'HITL_PENDING')));
    grid.appendChild(card(s.hitl_approved,      'HITL Approved',       'var(--success)',    () => filterAudit('hitl_decision', 'APPROVED')));
    grid.appendChild(card(s.hitl_rejected,      'HITL Rejected',       'var(--danger)',     () => filterAudit('hitl_decision', 'REJECTED')));
    grid.appendChild(card(s.integrity_failures, 'Integrity Failures',  'var(--purple-300)', () => filterAudit('integrity', 'false')));
    grid.appendChild(card(s.by_user?.alice ?? 0,'Alice Queries',       'var(--success)',    () => filterAudit('user', 'alice')));
    grid.appendChild(card(s.by_user?.bob   ?? 0,'Bob Queries',         'var(--warning)',    () => filterAudit('user', 'bob')));
  } catch (e) { console.error(e); }
}

async function filterAudit(type, value) {
  // Switch to audit log view
  document.getElementById('audit-content').style.display = 'block';
  document.getElementById('compliance-report').style.display = 'none';

  // Fetch all audit entries
  const userFilter = document.getElementById('audit-user-filter');
  const user = (type === 'user') ? value : '';
  userFilter.value = user;

  const url = user ? `${API}/api/audit?user=${user}` : `${API}/api/audit`;
  const rows = await fetch(url).then(r => r.json()).catch(() => []);

  // Apply additional filter
  const filtered = rows.filter(r => {
    if (type === 'all')          return true;
    if (type === 'user')         return true; // already filtered by URL
    if (type === 'outcome')      return r.outcome === value;
    if (type === 'hitl_decision')return r.hitl_decision === value;
    if (type === 'integrity')    return String(r.integrity_ok) === value;
    return true;
  });

  renderAuditRows(filtered);
}


// ── Tab Navigation ────────────────────────────────────────────────────────────
function showTab(name) {
  activeTab = name;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`tab-${name}`)?.classList.add('active');
  document.getElementById(`tab-content-${name}`)?.classList.add('active');

  // Lazy load tab data
  if (name === 'acl')   loadDocuments();
  if (name === 'hitl')  loadHITL();
  if (name === 'audit') loadAudit();
}

// ── User Selector ─────────────────────────────────────────────────────────────
function setUser(user) {
  currentUser = user;
  document.querySelectorAll('.user-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`user-${user}`)?.classList.add('active');

  // Update ACL display if on that tab
  if (activeTab === 'acl') loadDocuments();

  // Append a subtle note to chat
  const container = document.getElementById('chat-messages');
  const note = document.createElement('div');
  note.style.cssText = 'text-align:center;font-size:0.72rem;color:var(--text-muted);padding:4px;';
  note.textContent = `— Switched to ${user} (acl_level=${{'alice':0,'bob':1,'admin':3}[user]}) —`;
  container.appendChild(note);
  container.scrollTop = container.scrollHeight;
}

// ── Quick Test Cases ──────────────────────────────────────────────────────────
function runTC(query, tab) {
  // Always runs as the currently active user — switch persona first, then test
  const tcUser = currentUser;
  showTab(tab === 'hitl' ? 'chat' : tab);
  setTimeout(() => { sendQuery(query, tcUser); }, 50);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  connectSSE();
  loadDocuments();
});
