import { api } from './api.js';
import { html, icon, fmtTime, fmtDateKo } from './util.js';
import { avatar, taskRow, empty } from './ui.js';
import { bindTaskActions } from './tasks.js';

const range = (b) => `${b.start_time}–${b.end_time}`;

/** 일과 구간 타임라인. 대시보드와 일과 화면에서 같이 쓴다. */
export function routineStrip(r, selectedId, { compact = false } = {}) {
  return html`<ol class="routine ${compact ? 'compact' : ''}" aria-label="오늘의 일과 구간">${r.blocks.map((b) => html`<li>
    <a class="rblock ${b.id === r.current_block_id ? 'now' : ''}" href="#/routine/${b.id}" ${b.id === selectedId ? html`aria-current="true"` : ''}>
      <span class="rtime">${range(b)}</span>
      <span class="rname">${b.name}</span>
      <span class="rmeta">
        ${b.id === r.current_block_id ? html`<span class="badge b-pending">${icon('clock')} 지금</span>` : ''}
        ${b.handoff_label ? html`<span class="badge b-high">인계</span>` : ''}
        <span class="rcount ${b.record_count ? '' : 'zero'}">${b.record_count ? `기록 ${b.record_count}건 · ${b.dog_count}/${b.dogs_total}마리` : '기록 없음'}</span>
      </span></a></li>`)}</ol>`;
}

export const programLine = (r) => html`<span class="program">${icon('spark')} 오늘의 프로그램 · ${r.program.weekday}요일 <b>${r.program.title}</b> — ${r.program.detail}</span>`;

export async function routineView(ctx) {
  const { root, staff, params } = ctx;
  const r = await api.routine();
  const sel = +params[0] || r.default_block_id;
  if (!sel) { root.innerHTML = empty('일과 구간이 없습니다', '').toString(); return; }
  const d = await api.routineBlock(sel);
  const b = d.block, total = d.dogs.length;
  const dogs = [...d.dogs].sort((x, y) => (x.records.length > 0) - (y.records.length > 0));   // 기록이 없는 아이를 위로
  const h = d.handoff;
  root.innerHTML = html`
    <div class="page-head"><div><h1>오늘의 일과</h1><p>${fmtDateKo(r.date)} · 구간별로 기록 현황과 인계 시점을 확인합니다.</p></div><div>${programLine(r)}</div></div>
    ${r.open ? '' : html`<p class="callout" style="margin-bottom:14px">지금은 영업시간(${r.blocks[0].start_time}–${r.blocks.at(-1).end_time}) 밖입니다. 오늘 가장 최근에 기록이 있는 구간을 보여드려요. 다른 구간을 눌러 확인할 수 있습니다.</p>`}
    ${routineStrip(r, sel)}
    <section class="section" aria-labelledby="bt"><div class="head"><div><h2 id="bt">${b.name} <span class="muted small">${range(b)}</span></h2><p class="small muted" style="margin-top:2px">${b.description}</p></div>
      <a class="btn" href="#/record/new?block=${b.id}">${icon('pen')} 이 구간 기록 작성</a></div>
      ${h ? html`<div class="card handoff" role="region" aria-label="인계 시점"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span class="badge b-high">인계 시점 ${h.at}</span><b>${h.label}</b></div>
        <p style="margin:8px 0 10px">이어받을 일: <b>확인 대기 ${h.counts.pending}건</b> · 확인했지만 조치 필요 ${h.counts.todo}건 · 진행 중 ${h.counts.in_progress}건</p>
        ${h.tasks.length ? html`<div class="task-list">${h.tasks.map((t) => taskRow(t, staff))}</div>` : html`<p class="muted small">넘겨받을 업무가 없습니다.</p>`}</div>` : ''}
      <p class="small muted" style="margin:14px 0 8px">이 구간에 기록이 있는 반려견 <b>${d.with_record}/${total}</b>마리 ${b.record_type ? html`· 이 구간의 기본 기록 유형: ${b.record_type}` : ''}</p>
      <div class="panel" style="padding:4px 16px"><ul class="timeline" style="margin:0">${dogs.map((x) => html`<li style="grid-template-columns:150px 1fr auto;align-items:center">
        <a class="task-dog" href="#/dogs/${x.id}">${avatar(x, 'sm')}<span>${x.name}</span></a>
        <div>${x.records.length ? html`<span class="badge b-ack">${icon('check')} 기록 ${x.records.length}건</span> <span class="small">${fmtTime(x.records[0].observed_at)} ${x.records[0].record_type}${x.records[0].structured_value && x.records[0].structured_value !== '직접 입력' ? ` · ${x.records[0].structured_value}` : ''} — ${x.records[0].content.slice(0, 60)}</span>`
          : html`<span class="badge b-pending">${icon('clock')} 아직 기록 없음</span>`}${x.open_task_count ? html` <span class="badge b-todo">진행할 업무 ${x.open_task_count}</span>` : ''}</div>
        <a class="btn sm secondary" href="#/record/new?dog=${x.id}&block=${b.id}">기록 작성</a></li>`)}</ul></div>
    </section>`.toString();
  bindTaskActions(root, ctx);
}
