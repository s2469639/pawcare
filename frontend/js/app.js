import { api, ApiError } from './api.js';
import { session } from './session.js';
import { html, icon, fmtDateKo, raw } from './util.js';
import { skeleton, errorBox, toast, busy, guarded } from './ui.js';
import { roleView } from './role.js';
import { dashboardView } from './dashboard.js';
import { dogsView, dogDetailView } from './dogs.js';
import { recordNewView, aiView } from './records.js';
import { tasksView, taskDetailView } from './tasks.js';
import { parentView } from './parent.js';

const app = document.getElementById('app');
const state = { allStaff: [], staff: null, shell: false, seq: 0 };

const routes = [
  [/^\/$/, roleView, { shell: false }],
  [/^\/parent$/, parentView, { shell: false }],
  [/^\/dashboard$/, dashboardView, { nav: 'dashboard' }],
  [/^\/dogs$/, dogsView, { nav: 'dogs' }],
  [/^\/dogs\/(\d+)$/, dogDetailView, { nav: 'dogs' }],
  [/^\/record\/new$/, recordNewView, { nav: 'record' }],
  [/^\/tasks$/, tasksView, { nav: 'tasks' }],
  [/^\/tasks\/(\d+)$/, taskDetailView, { nav: 'tasks' }],
  [/^\/ai(?:\/(\d+))?$/, aiView, { nav: 'ai' }],
];

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, qs = ''] = raw.split('?');
  return { path, query: Object.fromEntries(new URLSearchParams(qs)) };
}
const go = (h) => { location.hash = h; };

function logout(msg) {
  session.clear(); state.shell = false;
  if (msg) toast(msg, 'error');
  go('/');
}

const NAV = [
  ['dashboard', '/dashboard', '오늘의 업무', 'home'], ['tasks', '/tasks', '업무 인계', 'list'],
  ['dogs', '/dogs', '반려견', 'dog'], ['record', '/record/new', '돌봄 기록 작성', 'pen'], ['ai', '/ai', 'AI 업무 정리', 'spark'],
];

function mountShell() {
  app.innerHTML = html`<div class="shell">
    <aside class="side">
      <a class="brand" href="#/dashboard"><img src="assets/favicon.svg" width="28" height="28" alt=""><span class="word">PawCare</span></a>
      <nav class="nav" aria-label="주요 메뉴" id="nav"></nav>
      <div class="foot"><div id="org"></div><p class="tiny" style="margin:8px 0">프로토타입 · 모든 데이터는 가상입니다</p>
        <button id="reset">데모 데이터 초기화</button> · <a href="#/" style="color:inherit">역할 선택</a></div>
    </aside>
    <div class="main-col">
      <header class="topbar">
        <span class="date" id="date"></span><span class="spacer"></span>
        <div class="staff-switch"><label for="who">시연 담당자</label><select id="who" class="input" style="width:auto"></select></div>
        <a class="bell" id="bell" href="#/tasks?filter=pending" aria-label="확인 대기 업무">${icon('bell')}</a>
      </header>
      <main id="view" tabindex="-1"></main>
    </div></div>`.toString();
  document.getElementById('who').addEventListener('change', (e) => {
    session.set({ staffId: +e.target.value });
    const s = state.allStaff.find((x) => x.id === +e.target.value);
    toast(`${s.role} · ${s.name}(으)로 전환했습니다.`);
    render({ keepScroll: true });
  });
  document.getElementById('reset').addEventListener('click', (e) => {
    if (!confirm('샘플 데이터를 처음 상태로 되돌립니다. 지금까지 입력한 내용이 사라집니다. 계속할까요?')) return;
    busy(e.target, () => guarded(async () => { await api.reset(); toast('샘플 데이터를 초기화했습니다.'); go('/dashboard'); render(); }));
  });
  state.shell = true;
}

function paintChrome(nav, mine) {
  const s = state.staff;
  document.getElementById('date').textContent = fmtDateKo(new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000).toISOString().slice(0, 10));
  document.getElementById('org').textContent = state.allStaff.find((x) => x.id === s.id)?.org_name || '';
  const groups = {};
  state.allStaff.forEach((x) => (groups[x.org_name] ||= []).push(x));
  document.getElementById('who').innerHTML = Object.entries(groups).map(([org, list]) =>
    `<optgroup label="${org.replace(/"/g, '')}${list[0].org_id !== s.org_id ? ' (다른 유치원 · 격리 확인용)' : ''}">` +
    list.map((x) => `<option value="${x.id}" ${x.id === s.id ? 'selected' : ''}>${x.role} · ${x.name}</option>`).join('') + '</optgroup>').join('');
  document.getElementById('nav').innerHTML = NAV.map(([k, href, label, ic]) =>
    html`<a href="#${href}" ${k === nav ? raw('aria-current="page"') : ''}>${icon(ic)} ${label}${k === 'tasks' && mine > 0 ? html`<span class="count" aria-label="내 확인 대기 ${mine}건">${mine}</span>` : ''}</a>`).join('');
  const bell = document.getElementById('bell');
  bell.innerHTML = html`${icon('bell')}${mine > 0 ? html`<span class="dot">${mine}</span>` : ''}`.toString();
  bell.setAttribute('aria-label', `내게 배정된 확인 대기 업무 ${mine}건`);
  bell.title = `내게 배정된 확인 대기 업무 ${mine}건`;
}

async function render({ keepScroll = false } = {}) {
  const my = ++state.seq;
  const { path, query } = parseHash();
  const hit = routes.map(([re, view, opt]) => [path.match(re), view, opt]).find(([m]) => m);
  if (!hit) { go('/'); return; }
  const [m, view, opt] = hit;
  const sess = session.get();
  if (opt.shell === false) {
    state.shell = false;
    app.innerHTML = '';
    document.title = 'PawCare — AI Care Work Manager';
    await view({ root: app, params: m.slice(1), query, go, rerender: render, session: sess });
    return;
  }
  if (sess.role !== 'teacher' || !sess.staffId) { go('/'); return; }
  try {
    if (!state.shell || !document.getElementById('view')) mountShell();
    const root = document.getElementById('view');
    const y = window.scrollY;
    if (!keepScroll) { root.innerHTML = skeleton(); window.scrollTo(0, 0); }
    state.allStaff = await api.demoStaff();
    state.staff = state.allStaff.find((x) => x.id === sess.staffId);
    if (!state.staff) { logout('직원 정보를 찾을 수 없어 처음 화면으로 돌아갑니다.'); return; }
    const dash = await api.dashboard();
    if (my !== state.seq) return;
    paintChrome(opt.nav, dash.counts.mine_pending);
    const ctx = { root, params: m.slice(1), query, staff: state.staff, allStaff: state.allStaff, dash, go, rerender: (o) => render({ keepScroll: true, ...o }) };
    await view(ctx);
    if (my !== state.seq) return;
    if (keepScroll) window.scrollTo(0, y);
  } catch (e) {
    if (my !== state.seq) return;
    if (e instanceof ApiError && e.status === 401) { logout(e.message); return; }
    const root = document.getElementById('view') || app;
    root.innerHTML = errorBox(e).toString();
    root.querySelector('[data-retry]')?.addEventListener('click', () => render());
  }
}

window.addEventListener('hashchange', () => render());
render();
