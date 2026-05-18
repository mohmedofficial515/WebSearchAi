// ---- Tabs ----
const tabs = document.querySelectorAll('.tab');
const forms = document.querySelectorAll('.form');
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => x.classList.remove('active'));
  forms.forEach(f => f.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('form-' + t.dataset.tab).classList.add('active');

  // Hide the live monitor + history list when the tab uses the panel
  // full-width (providers settings, archive browser). Each adds its own
  // content; the monitor on the right would just be empty/distracting.
  const wide = t.dataset.tab === 'providers' || t.dataset.tab === 'archive';
  document.getElementById('task-history-section').style.display = wide ? 'none' : '';
  document.getElementById('right-monitor').style.display = wide ? 'none' : '';
  document.getElementById('left-panel').style.flex = wide ? '1' : '';
  document.getElementById('main-layout').classList.toggle('providers-mode', wide);

  if (t.dataset.tab === 'archive') loadArchive();
  if (t.dataset.tab === 'accounts') loadAccounts();
}));

// ---- Accounts ledger (persistent temp-signup) ----
async function loadAccounts() {
  const ul = document.getElementById('accounts-list');
  if (!ul) return;
  ul.innerHTML = '<li class="muted" style="padding:8px">جارٍ التحميل…</li>';
  try {
    const r = await fetch('/api/accounts');
    if (!r.ok) throw new Error(r.status);
    const items = await r.json();
    if (!items.length) {
      ul.innerHTML = '<li class="muted" style="padding:8px">لا توجد حسابات بعد — استخدم تبويب <b>📧 تسجيل</b>.</li>';
      return;
    }
    ul.innerHTML = items.map(a => `
      <li class="archive-item" dir="rtl" lang="ar">
        <div class="archive-item-head">
          <b>${escapeHtml(a.profile_name || '?')}</b>
          <span class="pill ${a.verified ? 'ok' : ''}" style="font-size:10px">
            ${a.verified ? '✓ مفعّل' : '— غير مفعّل'}
          </span>
        </div>
        <div class="muted" style="font-size:12px">${escapeHtml(a.site_url || '')}</div>
        <div style="font-family:monospace;direction:ltr;text-align:left;font-size:12px;margin-top:4px">
          ${escapeHtml(a.email || '')}
        </div>
        <div class="archive-item-actions" style="margin-top:6px">
          <button type="button" class="ghost" data-forget="${escapeHtml(a.profile_name)}">🗑 حذف</button>
        </div>
      </li>
    `).join('');
    ul.querySelectorAll('[data-forget]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const slug = btn.dataset.forget;
        if (!confirm(`حذف الحساب "${slug}"؟ سيُحذف ملف الجلسة نهائيًا.`)) return;
        const r = await fetch('/api/accounts/' + encodeURIComponent(slug), {method: 'DELETE'});
        if (r.ok) loadAccounts();
      });
    });
  } catch (e) {
    ul.innerHTML = `<li class="muted" style="padding:8px">تعذّر التحميل: ${escapeHtml(String(e))}</li>`;
  }
}
document.getElementById('accounts-refresh')?.addEventListener('click', loadAccounts);

// ---- Form serializer ----
function formToJson(form) {
  const obj = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === 'checkbox') obj[el.name] = el.checked;
    else if (el.type === 'number') obj[el.name] = Number(el.value || 0);
    else obj[el.name] = el.value || null;
  }
  return obj;
}

// ---- Submit handlers ----
const endpoints = {
  'form-run': '/api/run',
  'form-signup': '/api/signup',
  'form-login': '/api/login',
  'form-explore': '/api/explore',
  'form-clone': '/api/clone',
  'form-components': '/api/find-components',
  'form-tokens': '/api/design-tokens',
  'form-tempsignup': '/api/temp-signup',
};

for (const [formId, url] of Object.entries(endpoints)) {
  const form = document.getElementById(formId);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = formToJson(form);
    if (formId === 'form-run' && payload.headless === false) delete payload.headless;
    const r = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!r.ok) { alert('Failed: ' + r.status); return; }
    const data = await r.json();

    // Cache hit — server returned the archived result directly. Render
    // it immediately instead of attaching to a live WebSocket stream.
    if (data.cached && data.result) {
      addTask(data.task_id, (formId.replace('form-', '')) + ' (cached)');
      updateTaskPill(data.task_id, 'succeeded');
      resetLive(data.task_id);
      _live.goal = data.result.goal || payload.goal || null;
      _live.result = data.result;
      _live.plan = data.result.plan || null;
      _live.steps = Array.isArray(data.result.steps) ? data.result.steps.map(s => ({...s})) : [];
      if (_live.plan) renderPlan(_live.plan);
      document.getElementById('result-box').textContent = JSON.stringify(data.result, null, 2);
      renderReport();
      renderSources();
      renderMetaRow();
      setStatus('cached');
      document.getElementById('active-title').textContent =
        (_live.goal ? truncate(_live.goal, 70) : 'Task ' + data.task_id) +
        ` · cache hit ${(data.cache_score * 100).toFixed(0)}%`;
      return;
    }

    addTask(data.task_id, formId.replace('form-', ''));
    attach(data.task_id);
  });
}

// ---- Task list ----
function addTask(task_id, kind) {
  const ul = document.getElementById('task-list');
  const li = document.createElement('li');
  li.dataset.id = task_id;
  li.innerHTML = `<span><b>${kind}</b> · ${task_id}</span><span class="pill" style="background:#1a1e2b">queued</span>`;
  li.addEventListener('click', () => attach(task_id));
  ul.prepend(li);
}

// ---- Live stream ----
let ws = null;
let activeTaskId = null;

function attach(task_id) {
  activeTaskId = task_id;
  document.getElementById('active-title').textContent = 'Task ' + task_id;
  resetLive(task_id);
  setStatus('running');

  if (ws) try { ws.close(); } catch {}
  const wsURL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/' + task_id;
  ws = new WebSocket(wsURL);
  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
  ws.onerror = () => { console.warn('WS error'); };

  // If the task is already completed in the DB, pull it once so the
  // user sees the report without needing the live stream to have fired.
  fetch('/api/tasks/' + task_id).then(r => r.ok ? r.json() : null).then(t => {
    if (!t || !t.result) return;
    _live.result = t.result;
    _live.goal = t.result.goal || (t.params && t.params.goal) || null;
    if (t.result.plan) { _live.plan = t.result.plan; renderPlan(t.result.plan); }
    if (Array.isArray(t.result.steps)) _live.steps = t.result.steps.map(s => ({ ...s }));
    document.getElementById('result-box').textContent = JSON.stringify(t.result, null, 2);
    renderReport();
    renderSources();
    renderMetaRow();
    if (_live.goal) document.getElementById('active-title').textContent = truncate(_live.goal, 80);
  }).catch(() => {});
}

function setStatus(s) {
  const pill = document.getElementById('status-pill');
  pill.textContent = s;
  pill.className = 'status ' + s;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ===================== Live-monitor session state =====================

// Per-task buffer of everything that comes off the WebSocket. We rebuild
// the views from this single source of truth instead of mutating the DOM
// piecemeal — makes tab switching and post-task replay free.
let _live = {
  task_id: null,
  goal: null,
  status: 'idle',
  plan: null,
  steps: [],          // array of {step, action, ok, note, perception}
  extractions: [],    // strings (raw extraction tool output)
  verdict: null,
  result: null,
  shot_url: null,
};

function resetLive(task_id) {
  _live = {
    task_id, goal: null, status: 'queued',
    plan: null, steps: [], extractions: [],
    verdict: null, result: null, shot_url: null,
  };
  document.getElementById('report-empty').style.display = '';
  document.getElementById('report-article').style.display = 'none';
  document.getElementById('timeline').innerHTML = '';
  document.getElementById('plan-card').innerHTML = '<div class="muted">No plan yet.</div>';
  document.getElementById('sources-list').innerHTML = '<div class="muted">No sources yet.</div>';
  document.getElementById('result-box').textContent = '—';
  document.getElementById('monitor-meta-row').innerHTML = '';
  document.getElementById('shot').innerHTML = '<em>Connecting…</em>';
}

// ===================== Monitor sub-tabs =====================

document.querySelectorAll('.mtab').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.mtab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.mpanel').forEach(p => p.classList.remove('active'));
    b.classList.add('active');
    document.getElementById('mpanel-' + b.dataset.mtab).classList.add('active');
  });
});

// ===================== Event handler — the WebSocket entry point =====

function handleEvent(ev) {
  const t = ev.type;
  if (t === 'task_start') {
    _live.goal = ev.data.goal || '';
    document.getElementById('active-title').textContent =
      _live.goal ? truncate(_live.goal, 80) : ('Task ' + _live.task_id);
    addTimelineEntry({ icon: '▶', title: 'Task started', detail: _live.goal, cls: 'evt-plan' });
  }
  else if (t === 'plan') {
    _live.plan = ev.data;
    renderPlan(ev.data);
    addTimelineEntry({
      icon: '🗺',
      title: 'Plan created',
      detail: `${(ev.data.subtasks || []).length} subtasks`,
      cls: 'evt-plan',
    });
  }
  else if (t === 'perception') {
    const step = ev.data.step;
    _live.steps[step - 1] = _live.steps[step - 1] || { step };
    _live.steps[step - 1].perception = ev.data;
    if (ev.data.screenshot && ev.task_id) {
      _live.shot_url = `/api/artifact/${ev.task_id}/${ev.data.screenshot}?_=${Date.now()}`;
      document.getElementById('shot').innerHTML = `<img src="${_live.shot_url}" alt="live screenshot" />`;
    }
  }
  else if (t === 'decision') {
    const step = ev.data.step, a = ev.data.action || {};
    _live.steps[step - 1] = Object.assign(_live.steps[step - 1] || { step }, { action: a });
    const info = describeAction(a);
    addTimelineEntry({
      step,
      icon: info.icon,
      title: info.title,
      detail: info.detail,
      cls: '',
    });
  }
  else if (t === 'action_result') {
    const step = ev.data.step;
    _live.steps[step - 1] = Object.assign(_live.steps[step - 1] || { step },
      { ok: ev.data.ok, note: ev.data.note });
    // Update the last timeline entry's status indicator
    markLastTimelineEntry(ev.data.ok ? 'ok' : 'fail', ev.data.note);
  }
  else if (t === 'verdict') {
    _live.verdict = ev.data;
    addTimelineEntry({
      icon: ev.data.success ? '✅' : '❌',
      title: 'Verdict: ' + (ev.data.success ? 'SUCCESS' : 'FAIL'),
      detail: `confidence ${(ev.data.confidence * 100).toFixed(0)}% — ${ev.data.reason || ''}`,
      cls: 'evt-verdict ' + (ev.data.success ? 'ok' : 'fail'),
      wrap: true,
    });
  }
  else if (t === 'task_end') {
    _live.result = ev.data;
    document.getElementById('result-box').textContent = JSON.stringify(ev.data, null, 2);
    renderReport();
    renderSources();
    renderMetaRow();
  }
  else if (t === 'status') {
    _live.status = ev.data.status || 'idle';
    setStatus(_live.status);
    updateTaskPill(ev.task_id, _live.status);
    if (ev.data.status === 'failed' && ev.data.error) {
      addTimelineEntry({ icon: '⚠', title: 'ERROR', detail: ev.data.error, cls: 'fail', wrap: true });
    }
    if (ev.data.result) {
      _live.result = ev.data.result;
      document.getElementById('result-box').textContent = JSON.stringify(ev.data.result, null, 2);
      renderReport();
      renderSources();
      renderMetaRow();
    }
  }
}

// ===================== Action describer =====================
// Produces the icon/title/detail shown in the timeline for each
// decision. Keeps the timeline readable by collapsing long arguments
// like the full search_web result list down to just the query.

function describeAction(a) {
  if (!a || !a.action) return { icon: '?', title: '(unknown action)', detail: '' };
  switch (a.action) {
    case 'search_web':
      return { icon: '🔍', title: 'Web search', detail: a.query || '' };
    case 'goto':
      return { icon: '🌐', title: 'Open URL', detail: a.url || '' };
    case 'click':
      return { icon: '🖱', title: 'Click', detail: `element #${a.index}` };
    case 'type':
      return { icon: '⌨', title: 'Type', detail: `into #${a.index}: ${truncate(a.text || '', 60)}` };
    case 'press':
      return { icon: '⏎', title: 'Key press', detail: a.key || '' };
    case 'scroll':
      return { icon: '↕', title: 'Scroll', detail: `${a.direction || 'down'} ${a.amount || ''}` };
    case 'wait':
      return { icon: '⏳', title: 'Wait', detail: `${a.seconds || a.ms || ''}` };
    case 'extract':
      return { icon: '📋', title: 'Extract', detail: a.what || 'page content' };
    case 'open_tab':
      return { icon: '🗂', title: 'Open tab', detail: a.url || '' };
    case 'switch_tab':
      return { icon: '↔', title: 'Switch tab', detail: a.tab_id || `index ${a.index}` };
    case 'close_tab':
      return { icon: '✕', title: 'Close tab', detail: a.tab_id || '' };
    case 'list_tabs':
      return { icon: '📑', title: 'List tabs', detail: '' };
    case 'done':
      return { icon: '✅', title: 'Done', detail: truncate(a.summary || '', 120) };
    case 'fail':
      return { icon: '❌', title: 'Fail', detail: a.reason || '' };
    default:
      return { icon: '·', title: a.action, detail: '' };
  }
}

// ===================== Timeline (compact) =====================

function addTimelineEntry({ step, icon, title, detail, cls = '', wrap = false }) {
  const ol = document.getElementById('timeline');
  const li = document.createElement('li');
  li.className = cls;
  li.innerHTML = `
    <span class="tl-icon">${escapeHtml(icon || '·')}</span>
    <div class="tl-main">
      <div class="tl-title">${escapeHtml(title || '')}</div>
      ${detail ? `<div class="tl-detail ${wrap ? 'wrap' : ''}">${escapeHtml(detail)}</div>` : ''}
    </div>
    ${step != null ? `<span class="tl-step-no">#${step}</span>` : '<span></span>'}
  `;
  ol.appendChild(li);
  ol.scrollTop = ol.scrollHeight;
}

function markLastTimelineEntry(status, note) {
  const ol = document.getElementById('timeline');
  const last = ol.lastElementChild;
  if (!last) return;
  last.classList.add(status);
  if (status === 'fail' && note) {
    const d = last.querySelector('.tl-detail') || (() => {
      const x = document.createElement('div'); x.className = 'tl-detail wrap';
      last.querySelector('.tl-main').appendChild(x); return x;
    })();
    d.classList.add('wrap');
    d.textContent = truncate(String(note), 220);
  }
}

// ===================== Plan card =====================

function renderPlan(plan) {
  const box = document.getElementById('plan-card');
  if (!plan) { box.innerHTML = '<div class="muted">No plan yet.</div>'; return; }
  const sc = (plan.success_criteria || []).map(s => `<li>${escapeHtml(s)}</li>`).join('');
  const st = (plan.subtasks || []).map(s => `<li>${escapeHtml(s)}</li>`).join('');
  box.innerHTML = `
    <h3>${escapeHtml(plan.goal || '(no goal)')}</h3>
    ${plan.starting_url ? `<div class="muted" style="font-size:12px;margin-top:4px">starts at <a href="${escapeHtml(plan.starting_url)}" target="_blank" style="color:var(--accent)">${escapeHtml(plan.starting_url)}</a></div>` : ''}
    ${sc ? `<div class="plan-criteria"><h4>Success criteria</h4><ul>${sc}</ul></div>` : ''}
    ${st ? `<div class="plan-subtasks"><h4 style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:0 0 8px">Subtasks</h4><ol>${st}</ol></div>` : ''}
  `;
}

// ===================== Sources panel =====================

function renderSources() {
  const box = document.getElementById('sources-list');
  const links = collectSources();
  if (!links.length) {
    box.innerHTML = '<div class="muted">No sources yet.</div>';
    return;
  }
  box.innerHTML = links.map(s => `
    <a class="source-card" href="${escapeHtml(s.url)}" target="_blank" rel="noopener">
      <div class="source-favicon"><img src="https://www.google.com/s2/favicons?domain=${escapeHtml(hostOf(s.url))}&sz=32" alt="" onerror="this.style.display='none'"/></div>
      <div>
        <div class="source-title">${escapeHtml(s.title || s.url)}</div>
        <div class="source-url">${escapeHtml(s.url)}</div>
        ${s.snippet ? `<div class="source-snippet">${escapeHtml(s.snippet)}</div>` : ''}
      </div>
    </a>
  `).join('');
}

// Pull every URL the agent encountered: from search_web results,
// goto actions, and links inside the final summary. Dedupes by URL.
function collectSources() {
  const seen = new Map();
  const add = (url, title, snippet) => {
    if (!url || !/^https?:\/\//i.test(url)) return;
    const u = url.split('#')[0];
    if (seen.has(u)) {
      // Upgrade to a better title/snippet if we have one now
      const prev = seen.get(u);
      if (!prev.title && title) prev.title = title;
      if (!prev.snippet && snippet) prev.snippet = snippet;
    } else {
      seen.set(u, { url: u, title: title || '', snippet: snippet || '' });
    }
  };

  // From every step
  for (const st of _live.steps || []) {
    const a = st.action || {};
    if (a.url) add(a.url, st.perception?.title || '', '');
    if (a.action === 'search_web' && st.note) {
      // search_web result note is "N results for ...\n{json}"
      const m = String(st.note).match(/\[[\s\S]*\]/);
      if (m) {
        try {
          const arr = JSON.parse(m[0]);
          if (Array.isArray(arr)) {
            arr.forEach(r => add(r.url, r.title, r.snippet));
          }
        } catch {}
      }
    }
  }
  // From extractions (when the LLM emitted search_web results in extract)
  for (const ex of _live.result?.extractions || []) {
    if (typeof ex !== 'string') continue;
    const m = ex.match(/\[[\s\S]*\]/);
    if (m) {
      try {
        const arr = JSON.parse(m[0]);
        if (Array.isArray(arr)) arr.forEach(r => add(r.url, r.title, r.snippet));
      } catch {}
    }
  }
  return Array.from(seen.values());
}

function hostOf(url) {
  try { return new URL(url).hostname; } catch { return ''; }
}

// ===================== Meta row (pills under title) =====================

function renderMetaRow() {
  const box = document.getElementById('monitor-meta-row');
  const r = _live.result;
  if (!r) { box.innerHTML = ''; return; }
  const bits = [];
  if (r.success === true) bits.push('<span class="meta-pill ok">✓ success</span>');
  else if (r.success === false) bits.push('<span class="meta-pill bad">✗ failed</span>');
  if (typeof r.confidence === 'number') bits.push(`<span class="meta-pill">confidence ${(r.confidence * 100).toFixed(0)}%</span>`);
  if (Array.isArray(r.steps)) bits.push(`<span class="meta-pill">${r.steps.length} steps</span>`);
  if (r.task_id) bits.push(`<span class="meta-pill">${escapeHtml(r.task_id)}</span>`);
  box.innerHTML = bits.join('');
}

// ===================== REPORT — the centerpiece =====================
//
// The summary can arrive as:
//   • a STRING (plain text or markdown)            → markdown-rendered body
//   • a JSON-stringified object                     → parse + render as hero card
//   • a real OBJECT (some LLMs send it that way)    → render as hero card
// The hero card auto-detects common fields:
//   { app_name | title | name }    → big title
//   { description | summary | tagline }  → subtitle paragraph
//   { features | benefits | pros }  → checked list
//   plus any remaining string-array sections rendered below as
//   "label → bullets" pairs. Everything else falls through to the
//   markdown body or, as a final fallback, a code block.

function renderReport() {
  const r = _live.result;
  // ── Components result — has its own viewer.html ───────────────────
  // Bypass the markdown report path; render a "open the gallery"
  // hero card with quick stats and an iframe of the viewer itself.
  if (r && r.viewer_html && Array.isArray(r.variants)) {
    document.getElementById('report-empty').style.display = 'none';
    document.getElementById('report-article').style.display = '';
    _renderComponentsResult(r);
    return;
  }

  if (!r || !r.summary) {
    document.getElementById('report-empty').style.display = '';
    document.getElementById('report-article').style.display = 'none';
    return;
  }
  document.getElementById('report-empty').style.display = 'none';
  document.getElementById('report-article').style.display = '';

  // ── Research mode shortcut ─────────────────────────────────────────
  // If the agent went through the search-first research flow, the
  // server has a much richer pre-rendered Arabic Markdown report. Fetch
  // and render that instead of stitching one from `summary` + scratch.
  const taskId = _live.taskId || r.task_id;
  const isResearch = !!(r.plan && r.plan.research);
  if (taskId && isResearch) {
    fetch(`/api/tasks/${encodeURIComponent(taskId)}/report`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data || !data.markdown) return _renderReportLegacy(r);
        const hero = document.getElementById('report-hero');
        const body = document.getElementById('report-body');
        const footer = document.getElementById('report-footer');
        hero.innerHTML = '';
        footer.innerHTML = '';
        body.innerHTML = `<div class="ar-report" dir="rtl" lang="ar">${renderMarkdown(data.markdown)}</div>`;
        const fbits = [];
        if (typeof r.confidence === 'number') fbits.push(`<span class="footer-bit">Confidence: ${(r.confidence * 100).toFixed(0)}%</span>`);
        if (Array.isArray(r.steps)) fbits.push(`<span class="footer-bit">${r.steps.length} steps</span>`);
        if (r.task_id) fbits.push(`<span class="footer-bit">Task ${r.task_id}</span>`);
        fbits.push(`<span class="footer-bit">${new Date().toLocaleString()}</span>`);
        footer.innerHTML = fbits.join('');
      })
      .catch(() => _renderReportLegacy(r));
    return;
  }

  _renderReportLegacy(r);
}

// ── Components / gallery result renderer ───────────────────────────────────
// Used when the task was `find_components`. The skill writes a complete
// `viewer.html` to the artifacts dir; we expose it via the existing
// `/artifacts` static mount and embed it in an iframe so the user gets
// the full UX (sidebar, syntax-highlighted JSX, RTL descriptions) without
// leaving the dashboard.
function _renderComponentsResult(r) {
  const hero = document.getElementById('report-hero');
  const body = document.getElementById('report-body');
  const footer = document.getElementById('report-footer');
  // outputs/components/<slug>/viewer.html  →  /artifacts/components/<slug>/viewer.html
  const viewerUrl = artifactUrl(r.viewer_html);
  const hostsSeen = new Set(r.variants.map(v => v.source_host)).size;

  hero.innerHTML = `
    <div class="report-hero" dir="rtl" lang="ar">
      <span class="report-hero-tag">🎨 معرض مكوّنات</span>
      <h1 class="report-hero-title">${escapeHtml(r.query || 'مكوّنات')}</h1>
      <div class="report-hero-meta" style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px">
        <span class="footer-bit"><strong>${r.variants.length}</strong> إصدار</span>
        <span class="footer-bit"><strong>${hostsSeen}</strong> مصدر</span>
        ${viewerUrl ? `<a class="footer-bit" href="${escapeHtml(viewerUrl)}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">↗ افتح المعرض في تبويب جديد</a>` : ''}
      </div>
    </div>`;

  body.innerHTML = viewerUrl
    ? `<iframe src="${escapeHtml(viewerUrl)}" style="width:100%;height:80vh;border:1px solid var(--border);border-radius:12px;background:#0b0d12" sandbox="allow-scripts allow-popups allow-same-origin"></iframe>`
    : `<div class="muted">تعذّر تحديد مسار <code>viewer.html</code> داخل المخرجات.</div>`;

  footer.innerHTML = `
    <span class="footer-bit">المخرجات: <code>${escapeHtml(r.out_dir || '')}</code></span>
    <span class="footer-bit">${new Date().toLocaleString()}</span>`;
}

// Convert an absolute output path (Windows or POSIX) into the URL the
// FastAPI `/artifacts` mount serves it under.
function artifactUrl(absPath) {
  if (!absPath) return '';
  const norm = String(absPath).replace(/\\/g, '/');
  // Find "outputs/" in the path — anything after is the relative artifact URL.
  const m = norm.match(/\/outputs\/(.+)$/i) || norm.match(/^outputs\/(.+)$/i);
  return m ? '/artifacts/' + m[1] : '';
}

function _renderReportLegacy(r) {
  let summary = r.summary;
  // Try to parse JSON-shaped strings into real objects
  if (typeof summary === 'string') {
    const trimmed = summary.trim();
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) ||
        (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
      try { summary = JSON.parse(trimmed); } catch {}
    }
  }

  const hero = document.getElementById('report-hero');
  const body = document.getElementById('report-body');
  const footer = document.getElementById('report-footer');
  hero.innerHTML = '';
  body.innerHTML = '';
  footer.innerHTML = '';

  if (summary && typeof summary === 'object') {
    hero.innerHTML = buildHeroFromObject(summary, r.goal);
  } else {
    // Plain markdown/text
    const md = String(summary);
    hero.innerHTML = `
      <div class="report-hero">
        <span class="report-hero-tag">${escapeHtml(_live.goal ? 'Goal' : 'Result')}</span>
        <h1 class="report-hero-title">${escapeHtml(_live.goal || 'Result')}</h1>
      </div>`;
    body.innerHTML = renderMarkdown(md);
  }

  // Footer pills (timestamp, confidence, etc.)
  const fbits = [];
  if (typeof r.confidence === 'number') fbits.push(`<span class="footer-bit">Confidence: ${(r.confidence * 100).toFixed(0)}%</span>`);
  if (Array.isArray(r.steps)) fbits.push(`<span class="footer-bit">${r.steps.length} steps</span>`);
  if (r.task_id) fbits.push(`<span class="footer-bit">Task ${r.task_id}</span>`);
  fbits.push(`<span class="footer-bit">${new Date().toLocaleString()}</span>`);
  footer.innerHTML = fbits.join('');
}

function buildHeroFromObject(obj, fallbackGoal) {
  // Extract well-known fields, case-insensitive on the keys.
  const lookup = (...keys) => {
    for (const k of keys) {
      const found = Object.keys(obj).find(x => x.toLowerCase() === k.toLowerCase());
      if (found && obj[found]) return obj[found];
    }
    return null;
  };
  const title = lookup(
    'app_name', 'site_name', 'product_name', 'company_name',
    'title', 'name', 'goal', 'topic',
  ) || fallbackGoal || 'Result';
  const desc = lookup(
    'description', 'summary', 'tagline', 'slogan', 'platform_slogan',
    'overview', 'analysis', 'about', 'page_description', 'introduction',
  );
  const features = lookup(
    'features', 'unique_features', 'key_features', 'main_features',
    'benefits', 'pros', 'advantages', 'capabilities', 'highlights',
    'user_engagement_features', 'selling_points', 'unique_selling_points',
  );

  let html = `<div class="report-hero">`;
  html += `<span class="report-hero-tag">Final report</span>`;
  html += `<h1 class="report-hero-title">${escapeHtml(String(title))}</h1>`;

  if (desc) {
    if (typeof desc === 'string') {
      html += `<p class="report-hero-desc">${escapeHtml(desc)}</p>`;
    } else if (typeof desc === 'object') {
      // Nested analysis object — render its values inline
      html += `<p class="report-hero-desc">${renderInlineObject(desc)}</p>`;
    }
  }

  if (features) {
    html += `<div class="report-hero-features"><h4>Key features</h4><ul>`;
    html += renderFeatureList(features);
    html += `</ul></div>`;
  }

  // Any remaining keys that look like content sections — render them.
  const consumed = new Set(
    ['app_name','site_name','product_name','company_name','title','name','goal','topic',
     'description','summary','tagline','slogan','platform_slogan','overview','analysis','about','page_description','introduction',
     'features','unique_features','key_features','main_features','benefits','pros','advantages','capabilities','highlights','user_engagement_features','selling_points','unique_selling_points',
    ].map(s => s.toLowerCase())
  );
  for (const [k, v] of Object.entries(obj)) {
    if (consumed.has(k.toLowerCase())) continue;
    if (v == null || v === '') continue;
    const label = humanizeKey(k);
    html += `<div class="report-hero-section"><h4>${escapeHtml(label)}</h4>`;
    if (Array.isArray(v)) {
      // Use the same checkmark-list styling as Key features
      html += `<ul class="report-section-list">${renderFeatureList(v)}</ul>`;
    } else if (typeof v === 'object') {
      html += renderNestedObject(v);
    } else {
      html += `<p>${escapeHtml(String(v))}</p>`;
    }
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}

function renderFeatureList(value) {
  if (Array.isArray(value)) {
    return value.map(item => {
      if (typeof item === 'string') return `<li>${escapeHtml(item)}</li>`;
      if (typeof item === 'object' && item) {
        // Pick the most likely "main text" field. Many LLM outputs use
        // a single-key object like {feature: "..."} or {benefit: "..."},
        // so we fall through to the first string value as a last resort.
        const primary =
          item.title || item.name || item.label || item.feature ||
          item.benefit || item.advantage || item.point || item.text ||
          item.value;
        const txt = primary || (Object.values(item).find(v => typeof v === 'string')) || JSON.stringify(item);
        const sub = item.description || item.detail || item.note || '';
        const link = item.url || item.link;
        const linkBit = link ? ` <a href="${escapeHtml(link)}" target="_blank" rel="noopener" style="color:var(--accent)">↗</a>` : '';
        return `<li><strong>${escapeHtml(String(txt))}</strong>${sub ? ' — ' + escapeHtml(String(sub)) : ''}${linkBit}</li>`;
      }
      return `<li>${escapeHtml(String(item))}</li>`;
    }).join('');
  }
  if (typeof value === 'object' && value) {
    return Object.entries(value).map(([k, v]) => {
      if (Array.isArray(v)) {
        return `<li><strong>${escapeHtml(humanizeKey(k))}:</strong><ul style="margin:6px 0 0;padding-left:18px">${v.map(x => `<li>${escapeHtml(String(x))}</li>`).join('')}</ul></li>`;
      }
      return `<li><strong>${escapeHtml(humanizeKey(k))}:</strong> ${escapeHtml(String(v))}</li>`;
    }).join('');
  }
  return `<li>${escapeHtml(String(value))}</li>`;
}

function renderNestedObject(obj) {
  return Object.entries(obj).map(([k, v]) => {
    if (Array.isArray(v)) {
      return `<p><strong>${escapeHtml(humanizeKey(k))}:</strong></p><ul>${v.map(x => `<li>${escapeHtml(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul>`;
    }
    if (typeof v === 'object' && v) {
      return `<p><strong>${escapeHtml(humanizeKey(k))}:</strong> ${escapeHtml(JSON.stringify(v))}</p>`;
    }
    return `<p><strong>${escapeHtml(humanizeKey(k))}:</strong> ${escapeHtml(String(v))}</p>`;
  }).join('');
}

function renderInlineObject(obj) {
  // Best-effort: pull a single descriptive string out of an analysis object
  const candidates = ['conclusion','description','summary','meaning','text'];
  for (const c of candidates) {
    const k = Object.keys(obj).find(x => x.toLowerCase() === c);
    if (k && typeof obj[k] === 'string') return escapeHtml(obj[k]);
  }
  return escapeHtml(JSON.stringify(obj).slice(0, 400));
}

function humanizeKey(k) {
  return String(k).replace(/[_\-]+/g, ' ').replace(/^./, c => c.toUpperCase());
}

function truncate(s, n) {
  s = String(s ?? '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

function renderMarkdown(md) {
  if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });
    return DOMPurify.sanitize(marked.parse(md));
  }
  // Fallback when CDN failed: escape and convert newlines.
  return '<pre style="white-space:pre-wrap">' + escapeHtml(md) + '</pre>';
}

// ===================== Report actions =====================

document.getElementById('report-copy-md')?.addEventListener('click', () => {
  const r = _live.result;
  if (!r) return;
  let md = `# ${r.goal || 'Task'}\n\n`;
  const summary = r.summary;
  if (typeof summary === 'object' && summary) {
    md += '```json\n' + JSON.stringify(summary, null, 2) + '\n```';
  } else {
    md += String(summary || '');
  }
  if (typeof r.confidence === 'number') md += `\n\n_Confidence: ${(r.confidence * 100).toFixed(0)}%_`;
  navigator.clipboard.writeText(md).then(
    () => alert('Copied to clipboard'),
    () => alert('Copy failed')
  );
});
document.getElementById('report-rerun')?.addEventListener('click', () => {
  if (!_live.goal) return;
  document.querySelector('[data-tab="run"]').click();
  const ta = document.querySelector('#form-run [name="goal"]');
  if (ta) { ta.value = _live.goal; ta.focus(); ta.dispatchEvent(new Event('input')); }
});

function updateTaskPill(task_id, status) {
  const li = document.querySelector(`#task-list li[data-id="${task_id}"] .pill`);
  if (!li) return;
  li.textContent = status;
  li.style.background = ({
    running: '#1d2a44', succeeded: '#1a3a2a', failed: '#3a1d1d', cancelled: '#332b1a'
  })[status] || '#1a1e2b';
}

// ===================== PROVIDERS =====================

const _speedIcon = { fast: '⚡', medium: '🔄', slow: '🐢', local: '💻' };
const _speedLabel = { fast: '⚡ Fast', medium: '🔄 Medium', slow: '🐢 Slow', local: '💻 Local' };
function _stars(n) { return '★'.repeat(n) + '☆'.repeat(5 - n); }

function buildProviderCard(p) {
  const isFree = p.tier === 'free' || p.tier === 'local';
  const tierLabel = p.tier === 'local' ? 'Local' : p.tier === 'free' ? 'Free' : 'Paid';
  const tierClass = p.tier === 'free' ? 'tier-free' : p.tier === 'local' ? 'tier-local' : 'tier-paid';

  // models is now array of {id, stars, speed, vision, ctx_k} objects from API
  const modelsHtml = p.models.map(m => {
    const id = typeof m === 'string' ? m : m.id;
    const stars = typeof m === 'object' ? m.stars || 3 : 3;
    const vis   = typeof m === 'object' && m.vision;
    const speed = typeof m === 'object' ? m.speed || 'medium' : 'medium';
    const ctx   = typeof m === 'object' && m.ctx_k ? ` ${m.ctx_k}K` : '';
    return `<option value="${escapeHtml(id)}" data-stars="${stars}" data-vision="${vis}" data-speed="${speed}">[${_stars(stars)}] ${escapeHtml(id)}${ctx}${vis ? ' 👁' : ''} ${_speedIcon[speed] || ''}</option>`;
  }).join('');

  const keyRowHtml = p.key_field ? `
    <div class="pcard-key-row">
      <input type="password" id="key-${p.name}" class="pcard-key"
        placeholder="${escapeHtml(p.key_placeholder || '')}"
        autocomplete="off" />
      <button class="pcard-test-btn" data-provider="${p.name}">Test</button>
    </div>` : `
    <div class="pcard-key-row">
      <input type="text" id="key-${p.name}" class="pcard-key"
        placeholder="http://localhost:11434"
        value="http://localhost:11434" />
      <button class="pcard-test-btn" data-provider="${p.name}">Test</button>
    </div>`;

  const modelRowHtml = p.model_field ? `
    <select id="model-${p.name}" class="pcard-model" onchange="onModelChange('${p.name}', this)">${modelsHtml}</select>
    <div class="pcard-model-meta" id="modelmeta-${p.name}"></div>` : '';

  const capsHtml = [
    p.supports_vision ? '<span class="cap">👁 Vision</span>' : '',
    p.supports_embed ? '<span class="cap">📐 Embed</span>' : '',
  ].filter(Boolean).join('');

  return `
  <div class="pcard ${isFree ? 'pcard-free' : ''}" id="pcard-${p.name}">
    <div class="pcard-top">
      <div class="pcard-title">
        <span class="pcard-emoji">${p.emoji}</span>
        <span class="pcard-name">${escapeHtml(p.label)}</span>
        <span class="pcard-tier ${tierClass}">${tierLabel}</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px">
        <button class="pcard-set-active-btn" id="setactive-${p.name}" data-provider="${p.name}" onclick="setActiveProvider('${p.name}')">Set Active</button>
        <span class="pcard-dot" id="dot-${p.name}" title="Not configured">○</span>
      </div>
    </div>
    <p class="pcard-desc">${escapeHtml(p.desc)}</p>
    <div class="pcard-meta-row">
      <span class="pcard-free-info">🎁 ${escapeHtml(p.free_info)}</span>
      ${capsHtml}
    </div>
    <a class="pcard-link" href="${escapeHtml(p.signup_url)}" target="_blank" rel="noopener">
      → Get API key at ${escapeHtml(p.signup_url.replace('https://', ''))}
    </a>
    ${keyRowHtml}
    ${modelRowHtml}
    <div class="pcard-msg" id="msg-${p.name}"></div>
    <pre class="pcard-reply" id="reply-${p.name}" style="display:none"></pre>
  </div>`;
}

function onModelChange(providerName, selEl) {
  const metaDiv = document.getElementById('modelmeta-' + providerName);
  if (!metaDiv) return;
  const opt = selEl ? selEl.options[selEl.selectedIndex] : null;
  if (!opt) return;
  const stars = Number(opt.dataset.stars || 3);
  const vision = opt.dataset.vision === 'true';
  const speed  = opt.dataset.speed || 'medium';
  metaDiv.innerHTML = `
    <span class="model-stars">${_stars(stars)}</span>
    ${vision
      ? '<span class="model-badge vis">👁 Vision</span>'
      : '<span class="model-badge novs">📝 Text only</span>'}
    <span class="model-badge spd">${_speedLabel[speed] || speed}</span>
  `;
}

function setActiveProvider(name) {
  const sel = document.getElementById('provider-selector');
  if (sel) sel.value = name;
  document.querySelectorAll('.pcard').forEach(c => c.classList.remove('pcard-active'));
  document.querySelectorAll('.pcard-set-active-btn').forEach(b => {
    b.classList.toggle('btn-active', b.dataset.provider === name);
  });
  const card = document.getElementById('pcard-' + name);
  if (card) { card.classList.add('pcard-active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
}

function setProviderDot(name, configured) {
  const dot = document.getElementById('dot-' + name);
  if (!dot) return;
  dot.textContent = configured ? '●' : '○';
  dot.style.color = configured ? 'var(--ok)' : 'var(--muted)';
  dot.title = configured ? 'Configured' : 'Not configured';
}

async function loadProviders() {
  try {
    const r = await fetch('/api/providers');
    if (!r.ok) return;
    const data = await r.json();

    // Update badge
    const badge = document.getElementById('active-provider-badge');
    if (badge) badge.textContent = data.active === 'auto' ? 'Auto Provider' : data.active;

    // Set selector
    const sel = document.getElementById('provider-selector');
    if (sel && data.active) sel.value = data.active;

    // Build cards
    const container = document.getElementById('provider-cards');
    container.innerHTML = data.providers.map(buildProviderCard).join('');

    // Populate current values
    data.providers.forEach(p => {
      if (p.key_field) {
        const keyEl = document.getElementById('key-' + p.name);
        if (keyEl && p.key_hint) {
          keyEl.placeholder = p.key_hint || keyEl.placeholder;
          if (p.is_configured) keyEl.dataset.configured = '1';
        }
      }
      if (p.model_field) {
        const modelEl = document.getElementById('model-' + p.name);
        if (modelEl && p.current_model) {
          modelEl.value = p.current_model;
          onModelChange(p.name, modelEl);
        }
      }
      setProviderDot(p.name, p.is_configured);
    });

    // Highlight active provider card
    setTimeout(() => setActiveProvider(data.active), 60);

    // Wire test buttons
    container.querySelectorAll('.pcard-test-btn').forEach(btn => {
      btn.addEventListener('click', () => testProvider(btn.dataset.provider));
    });

    // Load live models for all configured providers
    data.providers.forEach(p => {
      if (p.is_configured && p.model_field) {
        loadProviderModels(p.name);
      }
    });

  } catch (e) {
    console.warn('loadProviders failed', e);
  }
}

async function testProvider(name) {
  const btn = document.querySelector(`[data-provider="${name}"].pcard-test-btn`);
  const msg = document.getElementById('msg-' + name);
  if (!btn || !msg) return;

  // Save key first so the test uses the entered value
  const keyEl = document.getElementById('key-' + name);
  const modelEl = document.getElementById('model-' + name);
  const payload = {};
  if (keyEl?.value) {
    const meta = providerMeta[name];
    if (meta?.key_field) payload[meta.key_field] = keyEl.value;
    else if (name === 'ollama') payload['ollama_base_url'] = keyEl.value;
  }
  if (modelEl?.value && providerMeta[name]?.model_field) {
    payload[providerMeta[name].model_field] = modelEl.value;
  }
  if (Object.keys(payload).length) {
    await fetch('/api/providers/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
  }

  btn.textContent = '…';
  btn.disabled = true;
  msg.textContent = 'Testing connection…';
  msg.className = 'pcard-msg';

  try {
    const r = await fetch('/api/providers/test/' + name);
    const data = await r.json();
    btn.disabled = false;
    btn.textContent = 'Test';
    const replyEl = document.getElementById('reply-' + name);
    if (data.ok) {
      const modelLabel = data.model ? ` [${data.model}]` : '';
      msg.textContent = `✓ Connected · ${data.latency_ms}ms${modelLabel}`;
      msg.className = 'pcard-msg ok';
      setProviderDot(name, true);
      if (replyEl && data.reply) {
        replyEl.textContent = data.reply;
        replyEl.style.display = 'block';
      }
    } else {
      msg.textContent = `✗ ${data.error || 'Unknown error'}`;
      msg.className = 'pcard-msg fail';
      if (replyEl) replyEl.style.display = 'none';
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Test';
    msg.textContent = '✗ Network error';
    msg.className = 'pcard-msg fail';
  }
}

// Cache of provider metadata for test helper
let providerMeta = {};

async function initProviderMeta() {
  try {
    const r = await fetch('/api/providers');
    if (!r.ok) return;
    const data = await r.json();
    data.providers.forEach(p => { providerMeta[p.name] = p; });
  } catch {}
}

async function loadOpenRouterModels() {
  const sel = document.getElementById('model-openrouter');
  if (!sel) return;

  const currentVal = sel.value;
  sel.disabled = true;

  // Add a loading option
  const loadingOpt = document.createElement('option');
  loadingOpt.value = '';
  loadingOpt.textContent = '⏳ Loading live models…';
  sel.insertBefore(loadingOpt, sel.firstChild);
  sel.value = '';

  try {
    const r = await fetch('/api/providers/openrouter/models');
    const data = await r.json();

    sel.innerHTML = '';
    data.models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      const ctx = m.context_length ? ` · ${Math.round(m.context_length / 1000)}K ctx` : '';
      const vis = m.supports_vision ? ' 👁' : '';
      opt.textContent = `${m.id}${ctx}${vis}`;
      sel.appendChild(opt);
    });

    // Restore previously selected value, or keep first
    if (currentVal && [...sel.options].some(o => o.value === currentVal)) {
      sel.value = currentVal;
    }

    const src = data.source === 'live' ? '🟢 Live' : '🟡 Fallback';
    const msg = document.getElementById('msg-openrouter');
    if (msg && !msg.classList.contains('ok')) {
      msg.textContent = `${src} — ${data.models.length} free models available`;
      msg.className = 'pcard-msg';
    }
  } catch {
    sel.innerHTML = '';
    // Restore static fallback options from providerMeta
    (providerMeta['openrouter']?.models || []).forEach(id => {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = id;
      sel.appendChild(opt);
    });
    if (currentVal) sel.value = currentVal;
  } finally {
    sel.disabled = false;
  }
}

async function loadProviderModels(name) {
  if (name === 'openrouter') { return loadOpenRouterModels(); }

  const sel = document.getElementById('model-' + name);
  if (!sel) return;

  const currentVal = sel.value;

  try {
    const r = await fetch('/api/providers/' + name + '/models');
    const data = await r.json();
    if (!data.ok || !data.models.length) return;

    sel.innerHTML = '';
    data.models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      const ctx = m.context_length ? ` · ${Math.round(m.context_length / 1000)}K` : '';
      const vis = m.supports_vision ? ' 👁' : '';
      opt.textContent = `${m.id}${ctx}${vis}`;
      sel.appendChild(opt);
    });

    if (currentVal && [...sel.options].some(o => o.value === currentVal)) {
      sel.value = currentVal;
    }
    onModelChange(name, sel);
  } catch {}
}

// Provider selector change → highlight card
document.getElementById('provider-selector')?.addEventListener('change', (e) => {
  setActiveProvider(e.target.value);
});

// Save All button
document.getElementById('save-providers')?.addEventListener('click', async () => {
  const btn = document.getElementById('save-providers');
  const payload = {
    llm_provider: document.getElementById('provider-selector')?.value || 'auto',
  };

  const names = ['groq','gemini','cohere','openrouter','mistral','openai','anthropic'];
  names.forEach(name => {
    const keyEl = document.getElementById('key-' + name);
    const modelEl = document.getElementById('model-' + name);
    const meta = providerMeta[name];
    if (!meta) return;
    if (keyEl?.value && meta.key_field) payload[meta.key_field] = keyEl.value;
    if (modelEl?.value && meta.model_field) payload[meta.model_field] = modelEl.value;
  });

  // Ollama URL
  const ollamaKey = document.getElementById('key-ollama');
  if (ollamaKey?.value) payload['ollama_base_url'] = ollamaKey.value;

  try {
    const r = await fetch('/api/providers/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (data.ok) {
      btn.textContent = '✓ Saved!';
      // Update badge
      const badge = document.getElementById('active-provider-badge');
      const sel = document.getElementById('provider-selector');
      if (badge && sel) badge.textContent = sel.value === 'auto' ? 'Auto Provider' : sel.value;
      setTimeout(() => { btn.textContent = '💾 Save All'; }, 2000);
    }
  } catch {
    btn.textContent = '✗ Error';
    setTimeout(() => { btn.textContent = '💾 Save All'; }, 2000);
  }
});

// ===================== Archive =====================

let _archiveCheckTimer = null;
let _archiveSuggest = null; // currently-suggested archive record

async function loadArchive() {
  const ul = document.getElementById('archive-results');
  ul.innerHTML = '<div class="archive-empty">Loading…</div>';
  try {
    const r = await fetch('/api/archive?limit=50');
    if (!r.ok) throw new Error('http ' + r.status);
    const items = await r.json();
    renderArchiveList(items.map(it => ({ ...it, score: null, matched_terms: [] })));
  } catch (e) {
    ul.innerHTML = `<div class="archive-empty">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function searchArchive(q) {
  const ul = document.getElementById('archive-results');
  if (!q || !q.trim()) { return loadArchive(); }
  ul.innerHTML = '<div class="archive-empty">Searching…</div>';
  try {
    const r = await fetch('/api/archive/search?q=' + encodeURIComponent(q));
    if (!r.ok) throw new Error('http ' + r.status);
    const data = await r.json();
    renderArchiveList(data.matches);
  } catch (e) {
    ul.innerHTML = `<div class="archive-empty">Search failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderArchiveList(items) {
  const ul = document.getElementById('archive-results');
  if (!items || !items.length) {
    ul.innerHTML = '<div class="archive-empty">No archived tasks yet.<br/>Successful runs are saved here automatically.</div>';
    return;
  }
  ul.innerHTML = items.map(it => {
    const score = (typeof it.score === 'number')
      ? `<span class="arch-score">${(it.score * 100).toFixed(0)}%</span>`
      : '';
    const date = it.created_at
      ? new Date(it.created_at * 1000).toLocaleString()
      : '';
    const terms = (it.matched_terms || []).length
      ? `<div class="arch-terms">${
          it.matched_terms.map(t => `<span class="arch-term">${escapeHtml(t)}</span>`).join('')
        }</div>`
      : '';
    return `
      <li data-id="${escapeHtml(it.task_id)}">
        <div class="arch-row1">
          <span style="color:var(--muted);font-size:11px">${escapeHtml(date)}</span>
          ${score}
        </div>
        <div class="arch-goal">${escapeHtml(it.goal || '')}</div>
        <div class="arch-summary">${escapeHtml(it.summary || '')}</div>
        ${terms}
      </li>`;
  }).join('');
  ul.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => openArchiveModal(li.dataset.id));
  });
}

async function openArchiveModal(task_id) {
  const modal = document.getElementById('archive-modal');
  const content = document.getElementById('archive-modal-content');
  document.getElementById('archive-modal-title').textContent = 'Task ' + task_id;
  content.innerHTML = 'Loading…';
  modal.style.display = '';
  try {
    const r = await fetch('/api/archive/' + encodeURIComponent(task_id));
    if (!r.ok) throw new Error('http ' + r.status);
    const d = await r.json();
    content.innerHTML = renderArchiveDetail(d);
    content.querySelector('#archive-replay')?.addEventListener('click', () => {
      // Pre-fill the Run form with this goal, switch tab, focus
      document.querySelector('[data-tab="run"]').click();
      const ta = document.querySelector('#form-run [name="goal"]');
      if (ta) { ta.value = d.goal || ''; ta.focus(); ta.dispatchEvent(new Event('input')); }
      modal.style.display = 'none';
    });
    content.querySelector('#archive-delete')?.addEventListener('click', async () => {
      if (!confirm('Delete this archived task permanently?')) return;
      await fetch('/api/archive/' + encodeURIComponent(task_id), { method: 'DELETE' });
      modal.style.display = 'none';
      loadArchive();
    });
  } catch (e) {
    content.innerHTML = `<div class="archive-empty">Failed: ${escapeHtml(e.message)}</div>`;
  }
}

function renderArchiveDetail(d) {
  const conf = (typeof d.confidence === 'number')
    ? (d.confidence * 100).toFixed(0) + '%' : '—';
  const date = d.created_at ? new Date(d.created_at * 1000).toLocaleString() : '';
  const extractions = (d.extractions || []).slice(0, 5)
    .map(e => `<pre>${escapeHtml(String(e).slice(0, 1500))}</pre>`).join('') || '<em>(none)</em>';
  const plan = d.plan ? `<pre>${escapeHtml(JSON.stringify(d.plan, null, 2))}</pre>` : '<em>(no plan saved)</em>';
  const result = d.result ? `<pre>${escapeHtml(JSON.stringify(d.result, null, 2))}</pre>` : '<em>(no raw result)</em>';

  return `
    <div class="summary-meta">
      <span>${d.success ? '✅ success' : '❌ failed'}</span>
      <span>confidence ${conf}</span>
      <span>${escapeHtml(date)}</span>
    </div>
    <h4>Goal</h4>
    <div>${escapeHtml(d.goal || '')}</div>
    <h4>Summary</h4>
    <div style="white-space:pre-wrap">${escapeHtml(d.summary || '(empty)')}</div>
    <h4>Extractions</h4>
    ${extractions}
    <h4>Plan</h4>
    ${plan}
    <h4>Full result JSON</h4>
    ${result}
    <div class="modal-actions">
      <button class="primary" id="archive-replay">↻ Replay this goal in Run</button>
      <button class="ghost" id="archive-delete">🗑 Delete</button>
    </div>`;
}

// ===================== Smart cache-hit suggestion =====================

// As the user types a goal, debounce and ask the server if there's an
// archived task with the same intent. If so, surface a "Reuse result"
// button that drops them straight into the saved answer.
function scheduleArchiveCheck() {
  if (_archiveCheckTimer) clearTimeout(_archiveCheckTimer);
  _archiveCheckTimer = setTimeout(checkArchiveSuggestion, 450);
}

async function checkArchiveSuggestion() {
  const ta = document.querySelector('#form-run [name="goal"]');
  const box = document.getElementById('archive-suggest');
  const goal = (ta?.value || '').trim();
  if (goal.length < 8) { box.style.display = 'none'; _archiveSuggest = null; return; }
  try {
    const r = await fetch('/api/archive/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, threshold: 0.45 }),
    });
    if (!r.ok) return;
    const data = await r.json();
    const m = data.match;
    if (!m) { box.style.display = 'none'; _archiveSuggest = null; return; }
    _archiveSuggest = m;
    document.getElementById('archive-suggest-score').textContent =
      (m.score * 100).toFixed(0) + '% match';
    document.getElementById('archive-suggest-goal').textContent =
      '“' + (m.goal || '') + '”';
    document.getElementById('archive-suggest-summary').textContent =
      m.summary || '(no summary)';
    box.style.display = '';
  } catch {}
}

document.getElementById('archive-suggest-reuse')?.addEventListener('click', () => {
  if (!_archiveSuggest) return;
  openArchiveModal(_archiveSuggest.task_id);
  document.getElementById('archive-suggest').style.display = 'none';
});
document.getElementById('archive-suggest-dismiss')?.addEventListener('click', () => {
  document.getElementById('archive-suggest').style.display = 'none';
});

// Wire input listener on the goal textarea
document.querySelector('#form-run [name="goal"]')?.addEventListener('input', scheduleArchiveCheck);

// Archive search box
document.getElementById('archive-q')?.addEventListener('input', (e) => {
  if (_archiveCheckTimer) clearTimeout(_archiveCheckTimer);
  _archiveCheckTimer = setTimeout(() => searchArchive(e.target.value), 250);
});
document.getElementById('archive-refresh')?.addEventListener('click', loadArchive);

// Modal close handlers
document.getElementById('archive-modal-close')?.addEventListener('click', () => {
  document.getElementById('archive-modal').style.display = 'none';
});
document.getElementById('archive-modal-backdrop')?.addEventListener('click', () => {
  document.getElementById('archive-modal').style.display = 'none';
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') document.getElementById('archive-modal').style.display = 'none';
});

// ---- On load ----
(async () => {
  try {
    const r = await fetch('/api/tasks');
    if (!r.ok) return;
    const tasks = await r.json();
    tasks.slice(-15).reverse().forEach(t => {
      addTask(t.task_id, t.kind);
      updateTaskPill(t.task_id, t.status);
    });
  } catch {}

  await initProviderMeta();
  await loadProviders();
})();
