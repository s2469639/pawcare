import { api, ApiError } from './api.js';
import { html, icon, fmtDateKo, raw } from './util.js';
import { skeleton, errorBox, toast, busy, guarded, demoSelect } from './ui.js';
import { roleView } from './role.js';
import { loginView, registerView } from './auth.js';
import { dashboardView } from './dashboard.js';
import { dogsView, dogDetailView } from './dogs.js';
import { recordNewView, aiView } from './records.js';
import { tasksView, taskDetailView } from './tasks.js';
import { parentView } from './parent.js';
import { notesView } from './notes.js';
import { routineView } from './routine.js';
import { calendarView, parentCalendarView } from './calendar.js';

const app = document.getElementById('app');
// me: 로그인한 계정(없으면 null). 세션 자체는 HttpOnly 쿠키라 JS에서 읽을 수 없고, 서버(/api/auth/me)에 물어 확인한다.
const state = { loaded: false, me: null, demo: false, demoAccounts: [], shell: false, seq: 0, flash: null };

const routes = [
  [/^\/$/, roleView, { open: true }],
  [/^\/login$/, loginView, { open: true }],
  [/^\/register$/, registerView, { open: true }],
  [/^\/parent$/, parentView, { role: 'parent' }],
  [/^\/parent\/calendar$/, parentCalendarView, { role: 'parent' }],
  [/^\/dashboard$/, dashboardView, { role: 'staff', shell: true, nav: 'dashboard' }],
  [/^\/dogs$/, dogsView, { role: 'staff', shell: true, nav: 'dogs' }],
  [/^\/dogs\/(\d+)$/, dogDetailView, { role: 'staff', shell: true, nav: 'dogs' }],
  [/^\/record\/new$/, recordNewView, { role: 'staff', shell: true, nav: 'record' }],
  [/^\/tasks$/, tasksView, { role: 'staff', shell: true, nav: 'tasks' }],
  [/^\/tasks\/(\d+)$/, taskDetailView, { role: 'staff', shell: true, nav: 'tasks' }],
  [/^\/ai(?:\/(\d+))?$/, aiView, { role: 'staff', shell: true, nav: 'ai' }],
  [/^\/notes$/, notesView, { role: 'staff', shell: true, nav: 'notes' }],
  [/^\/calendar$/, calendarView, { role: 'staff', shell: true, nav: 'calendar' }],
  [/^\/routine(?:\/(\d+))?$/, routineView, { role: 'staff', shell: true, nav: 'routine' }],
];

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, qs = ''] = raw.split('?');
  return { path, query: Object.fromEntries(new URLSearchParams(qs)) };
}
const go = (h) => { location.hash = h; };
const homeFor = (me) => (me ? (me.role === 'parent' ? '/parent' : '/dashboard') : '/');

async function loadAuth() {
  if (state.loaded) return;
  try { state.demo = (await api.config()).demo_mode; } catch { state.demo = false; }
  state.me = (await api.me()).account;       // 로그인하지 않았으면 null
  state.loaded = true;
}

/** 로그인·전환·가입 후 호출: 화면 상태를 새 계정에 맞게 갱신 */
function setMe(account) { state.me = account; state.loaded = true; state.shell = false; }

async function logout() {
  try { await api.logout(); } catch { /* 이미 만료됐어도 화면에서는 로그아웃 처리 */ }
  state.me = null; state.shell = false;
  go('/');
}

async function demoSwitch(accountId) {
  const { account } = await api.demoLogin(accountId);
  setMe(account);
  toast(`${account.role === 'staff' ? `${account.staff.role} · ${account.name}` : `보호자 · ${account.name}`}(으)로 전환했습니다.`);
  const here = parseHash().path;
  if (account.role === 'parent' && here !== '/parent') go('/parent');
  else if (account.role === 'staff' && here === '/parent') go('/dashboard');
  else render({ keepScroll: true });
}

const NAV = [
  ['dashboard', '/dashboard', '오늘의 업무', 'home'], ['routine', '/routine', '오늘의 일과', 'clock'], ['calendar', '/calendar', '캘린더', 'cal'], ['tasks', '/tasks', '업무 인계', 'list'],
  ['dogs', '/dogs', '반려견', 'dog'], ['record', '/record/new', '돌봄 기록 작성', 'pen'], ['ai', '/ai', 'AI 업무 정리', 'spark'], ['notes', '/notes', '내 메모', 'pen'],
];

function mountShell() {
  app.innerHTML = html`<div class="shell">
    <aside class="side">
      <a class="brand" href="#/dashboard"><img src="assets/favicon.svg" width="28" height="28" alt=""><span class="word">PawCare</span></a>
      <nav class="nav" aria-label="주요 메뉴" id="nav"></nav>
      <div class="foot"><div id="org"></div>
        <p class="tiny" style="margin:8px 0">프로토타입 · 모든 데이터는 가상입니다</p>
        ${state.demo ? html`<button id="reset">데모 데이터 초기화</button> · ` : ''}<button id="logout">${state.demo ? '처음 화면으로' : '로그아웃'}</button></div>
    </aside>
    <div class="main-col">
      <header class="topbar">
        <span class="date" id="date"></span><span class="spacer"></span>
        <div class="staff-switch" id="who-wrap"></div>
        <a class="bell" id="bell" href="#/tasks?filter=pending" aria-label="확인 대기 업무">${icon('bell')}</a>
      </header>
      <main id="view" tabindex="-1"></main>
    </div></div>`.toString();
  document.getElementById('logout').addEventListener('click', logout);
  document.getElementById('reset')?.addEventListener('click', (e) => {
    if (!confirm('샘플 데이터를 처음 상태로 되돌립니다. 지금까지 입력한 내용이 사라집니다. 계속할까요?')) return;
    busy(e.target, () => guarded(async () => {
      await api.reset();                                   // 서버의 모든 세션도 함께 초기화되므로 같은 데모 계정으로 다시 들어간다
      setMe((await api.demoLogin(state.me.id)).account);
      toast('샘플 데이터를 초기화했습니다.'); go('/dashboard'); render();
    }));
  });
  state.shell = true;
}

function paintChrome(nav, mine) {
  const me = state.me;
  document.getElementById('date').textContent = fmtDateKo(new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000).toISOString().slice(0, 10));
  document.getElementById('org').textContent = me.org_name;
  const wrap = document.getElementById('who-wrap');
  if (state.demo) {
    wrap.innerHTML = html`<label for="who">시연 계정</label>${demoSelect(state.demoAccounts, me.id)}`.toString();
    wrap.querySelector('#who').addEventListener('change', (e) => guarded(() => demoSwitch(+e.target.value)));
  } else {
    wrap.innerHTML = html`<span class="who-name">${me.staff.role} · <b>${me.name}</b></span>`.toString();
  }
  document.getElementById('nav').innerHTML = NAV.map(([k, href, label, ic]) =>
    html`<a href="#${href}" ${k === nav ? raw('aria-current="page"') : ''}>${icon(ic)} ${label}${k === 'tasks' && mine > 0 ? html`<span class="count" aria-label="내 확인 대기 ${mine}건">${mine}</span>` : ''}</a>`).join('');
  const bell = document.getElementById('bell');
  bell.innerHTML = html`${icon('bell')}${mine > 0 ? html`<span class="dot">${mine}</span>` : ''}`.toString();
  bell.setAttribute('aria-label', `내게 배정된 확인 대기 업무 ${mine}건`);
  bell.title = `내게 배정된 확인 대기 업무 ${mine}건`;
}

function toLogin(message) {
  state.me = null; state.shell = false; state.flash = message || '로그인이 필요합니다.';
  go('/login');
}

async function render({ keepScroll = false } = {}) {
  const my = ++state.seq;
  const { path, query } = parseHash();
  const hit = routes.map(([re, view, opt]) => [path.match(re), view, opt]).find(([m]) => m);
  if (!hit) { go('/'); return; }
  const [m, view, opt] = hit;
  try {
    await loadAuth();
    if (my !== state.seq) return;
    if (state.demo && state.me) state.demoAccounts = await api.demoAccounts();
    // 경로 보호: 로그인이 필요한 화면은 로그인 후, 역할이 다르면 자기 홈으로
    if (opt.role && !state.me) { toLogin(); return; }
    if (opt.role && state.me.role !== opt.role) { go(homeFor(state.me)); return; }
    const flash = state.flash; state.flash = null;
    const base = { params: m.slice(1), query, go, me: state.me, demo: state.demo, demoAccounts: state.demoAccounts, flash, setMe, logout, demoSwitch, rerender: (o) => render({ keepScroll: true, ...o }) };

    if (!opt.shell) {                        // 로그인·가입·역할 선택·보호자 화면(사이드바 없음)
      state.shell = false;
      app.innerHTML = '';
      document.title = 'PawCare — AI Care Work Manager';
      await view({ root: app, ...base });
      return;
    }
    if (!state.shell || !document.getElementById('view')) mountShell();
    const root = document.getElementById('view');
    const y = window.scrollY;
    if (!keepScroll) { root.innerHTML = skeleton(); window.scrollTo(0, 0); }
    const dash = await api.dashboard();
    if (my !== state.seq) return;
    paintChrome(opt.nav, dash.counts.mine_pending);
    await view({ root, staff: state.me.staff, dash, ...base });
    if (my !== state.seq) return;
    if (keepScroll) window.scrollTo(0, y);
  } catch (e) {
    if (my !== state.seq) return;
    if (e instanceof ApiError && e.status === 401) { toLogin('로그인이 만료되었습니다. 다시 로그인해 주세요.'); return; }
    const root = document.getElementById('view') || app;
    root.innerHTML = errorBox(e).toString();
    root.querySelector('[data-retry]')?.addEventListener('click', () => render());
  }
}

window.addEventListener('hashchange', () => render());
render();
