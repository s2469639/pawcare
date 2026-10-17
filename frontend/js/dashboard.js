import { html, icon, FILTERS, matchFilter, groupKey, GROUP_LABEL } from './util.js';
import { taskRow, empty } from './ui.js';
import { bindTaskActions } from './tasks.js';
import { api } from './api.js';
import { routineStrip, programLine } from './routine.js';
import { KIND, timeText } from './calendar.js';

export async function dashboardView(ctx) {
  const { root, dash, staff, query } = ctx;
  const f = FILTERS.some(([k]) => k === query.filter) ? query.filter : 'all';
  const c = dash.counts;
  const list = dash.tasks.filter((t) => matchFilter(t, f));
  const order = ['pending', 'todo', 'in_progress', 'completed'];
  const groups = order.map((k) => [k, list.filter((t) => groupKey(t) === k)]).filter(([, l]) => l.length);
  const [routine, up] = await Promise.all([api.routine(), api.calendarUpcoming(7)]);
  const nothingToCheck = c.needs_ack === 0 && c.todo === 0 && c.in_progress === 0;

  root.innerHTML = html`
    <div class="page-head"><div><h1>오늘의 업무</h1>
      <p>${staff.name}님(${staff.role}) · 내게 배정된 확인 대기 업무 <b>${c.mine_pending}</b>건</p></div></div>
    <div class="stats" role="list">
      <div class="stat" role="listitem"><div class="label">${icon('dog')} 오늘 돌봄 중인 반려견</div><div class="num">${dash.attending_dogs}</div><div class="sub">마리 · <a href="#/attendance">출석 예정 ${dash.attendance.expected}</a></div></div>
      <a class="stat ${c.needs_ack ? 'alert' : ''}" role="listitem" href="#/dashboard?filter=pending"><div class="label">${icon('clock')} 확인이 필요한 업무</div><div class="num">${c.needs_ack}</div><div class="sub">내게 배정 ${c.mine_pending}건 · 조치 필요 ${c.todo}건</div></a>
      <a class="stat" role="listitem" href="#/dashboard?filter=in_progress"><div class="label">${icon('half')} 조치 진행 중</div><div class="num">${c.in_progress}</div><div class="sub">건</div></a>
      <a class="stat" role="listitem" href="#/dashboard?filter=completed"><div class="label">${icon('check')} 완료된 업무</div><div class="num">${c.completed}</div><div class="sub">전체 ${c.total}건 중</div></a>
    </div>
    ${dash.stay ? html`<p class="callout" style="margin-top:14px" role="status">${icon('dog')} 숙박 현황 · 숙박 중 <b>${dash.stay.staying}</b>마리 · 오늘 입실 <b>${dash.stay.checkin_today}</b> · 오늘 퇴실 <b>${dash.stay.checkout_today}</b> · 입실 예정 <b>${dash.stay.upcoming}</b></p>` : ''}
    <section class="section" aria-labelledby="rt"><div class="head"><h2 id="rt">오늘의 일과</h2><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${programLine(routine)}<a class="btn sm secondary" href="#/routine">구간별 기록 현황 ${icon('arrow')}</a></div></div>
      ${routineStrip(routine, null, { compact: true })}</section>
    <section class="section" aria-labelledby="up"><div class="head"><h2 id="up">다가오는 일정 <span class="muted small">7일 이내</span></h2><a class="btn sm secondary" href="#/calendar">캘린더 열기 ${icon('arrow')}</a></div>
      ${up.events.length ? html`<p class="small muted" style="margin-bottom:8px">아직 끝내지 않은 직원 준비 항목 <b>${up.open_prep_total}</b>개</p><div class="panel" style="padding:4px 16px"><ul class="upcoming">${up.events.map((e) => html`<li><a href="#/calendar?month=${e.start_date.slice(0, 7)}&day=${e.start_date}"><span class="kind kind-${e.kind}">${KIND[e.kind]}</span> <b>${e.title}</b></a> <span class="small muted">${e.start_date.slice(5).replace('-', '/')}${e.end_date !== e.start_date ? `~${e.end_date.slice(5).replace('-', '/')}` : ''} · ${timeText(e)}</span> ${e.open_prep ? html`<span class="badge b-pending">준비 ${e.open_prep}개 남음</span>` : html`<span class="badge b-done">준비 항목 없음·완료</span>`}</li>`)}</ul></div>` : html`<p class="muted small">7일 안에 등록된 일정이 없습니다.</p>`}</section>
    <div class="section"><div class="quick">
      <a class="btn" href="#/record/new">${icon('pen')} 돌봄 기록 작성</a>
      <a class="btn secondary" href="#/dogs">${icon('dog')} 반려견 목록</a>
      <a class="btn secondary" href="#/tasks">${icon('list')} 업무 인계 목록</a>
      <a class="btn secondary" href="#/ai">${icon('spark')} AI 업무 정리</a>
    </div></div>
    <section class="section" aria-labelledby="tl"><div class="head"><h2 id="tl">${f === 'all' ? '지금 확인할 업무' : '업무 목록'}</h2>
      <div class="chips" role="group" aria-label="업무 필터">${FILTERS.map(([k, label]) => html`<a class="chip" href="#/dashboard${k === 'all' ? '' : `?filter=${k}`}" ${f === k ? html`aria-current="true"` : ''}>${label} <span class="n">${dash.tasks.filter((t) => matchFilter(t, k)).length}</span></a>`)}</div></div>
      ${nothingToCheck && f === 'all' ? html`<div class="callout" style="margin-bottom:12px">현재 확인이 필요한 업무가 없습니다. 새로운 돌봄 기록을 작성해 보세요.</div>` : ''}
      ${list.length === 0
        ? (f === 'all' ? empty('아직 등록된 업무가 없습니다', '돌봄 기록을 작성하면 후속 업무를 제안받을 수 있어요.', html`<br><a class="btn" href="#/record/new">돌봄 기록 작성</a>`)
          : empty('이 상태의 업무가 없습니다', '다른 필터를 선택해 보세요.'))
        : groups.map(([k, l]) => html`${f === 'all' ? html`<div class="group-label">${GROUP_LABEL[k]} <span class="badge b-done">${l.length}</span></div>` : ''}<div class="task-list">${l.map((t) => taskRow(t, staff))}</div>`)}
    </section>`.toString();
  bindTaskActions(root, ctx);
}
