import { api } from './api.js';
import { html, icon, FILTERS, matchFilter, groupKey, GROUP_LABEL } from './util.js';
import { taskRow, empty } from './ui.js';
import { bindTaskActions } from './tasks.js';

export async function dashboardView(ctx) {
  const { root, dash, staff, query } = ctx;
  const f = FILTERS.some(([k]) => k === query.filter) ? query.filter : 'all';
  const c = dash.counts;
  const list = dash.tasks.filter((t) => matchFilter(t, f));
  const order = ['pending', 'todo', 'in_progress', 'completed'];
  const groups = order.map((k) => [k, list.filter((t) => groupKey(t) === k)]).filter(([, l]) => l.length);
  const nothingToCheck = c.needs_ack === 0 && c.todo === 0 && c.in_progress === 0;

  root.innerHTML = html`
    <div class="page-head"><div><h1>오늘의 업무</h1>
      <p>${staff.name}님(${staff.role}) · 내게 배정된 확인 대기 업무 <b>${c.mine_pending}</b>건</p></div></div>
    <div class="stats" role="list">
      <div class="stat" role="listitem"><div class="label">${icon('dog')} 오늘 돌봄 중인 반려견</div><div class="num">${dash.attending_dogs}</div><div class="sub">마리</div></div>
      <a class="stat ${c.needs_ack ? 'alert' : ''}" role="listitem" href="#/dashboard?filter=pending"><div class="label">${icon('clock')} 확인이 필요한 업무</div><div class="num">${c.needs_ack}</div><div class="sub">내게 배정 ${c.mine_pending}건 · 조치 필요 ${c.todo}건</div></a>
      <a class="stat" role="listitem" href="#/dashboard?filter=in_progress"><div class="label">${icon('half')} 조치 진행 중</div><div class="num">${c.in_progress}</div><div class="sub">건</div></a>
      <a class="stat" role="listitem" href="#/dashboard?filter=completed"><div class="label">${icon('check')} 완료된 업무</div><div class="num">${c.completed}</div><div class="sub">전체 ${c.total}건 중</div></a>
    </div>
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
