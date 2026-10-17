import { api } from './api.js';
import { html, icon, raw, pad, fmtDateKo, nowKstLocalInput } from './util.js';
import { empty, busy, guarded, toast, openModal, fieldErrors } from './ui.js';
import { parentFrame } from './parent.js';

export const KIND = { program: '프로그램', event: '행사', closed: '휴무', notice: '안내' };
const WD = '일월화수목금토';
const todayKst = () => nowKstLocalInput().slice(0, 10);
const monthOf = (s) => s.slice(0, 7);
const shiftMonth = (m, n) => { const d = new Date(Date.UTC(+m.slice(0, 4), +m.slice(5) - 1 + n, 1)); return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`; };
const covers = (e, day) => e.start_date <= day && day <= e.end_date;
export const timeText = (e) => (e.start_time ? `${e.start_time}${e.end_time ? `–${e.end_time}` : '~'}` : '종일');
const rangeText = (e) => (e.start_date === e.end_date ? fmtDateKo(e.start_date) : `${fmtDateKo(e.start_date)} ~ ${fmtDateKo(e.end_date)}`);
const kindBadge = (k) => html`<span class="kind kind-${k}">${KIND[k]}</span>`;

/** 월 달력. 종류는 색만이 아니라 글자로도 표시한다. 날짜 칸은 링크라 키보드로 이동할 수 있다. */
function grid(month, events, selected, base) {
  const first = new Date(Date.UTC(+month.slice(0, 4), +month.slice(5) - 1, 1));
  const lead = first.getUTCDay();
  const days = new Date(Date.UTC(+month.slice(0, 4), +month.slice(5), 0)).getUTCDate();
  const today = todayKst();
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(html`<div class="cal-cell blank" aria-hidden="true"></div>`);
  for (let n = 1; n <= days; n++) {
    const day = `${month}-${pad(n)}`;
    const list = events.filter((e) => covers(e, day));
    const label = `${n}일${list.length ? `, 일정 ${list.length}건: ${list.map((e) => `${KIND[e.kind]} ${e.title}`).join(', ')}` : ', 일정 없음'}`;
    cells.push(html`<a class="cal-cell ${day === today ? 'today' : ''}" href="#${base}?month=${month}&day=${day}" ${day === selected ? raw('aria-current="date"') : ''} aria-label="${label}">
      <span class="cal-num">${n}</span>${list.slice(0, 2).map((e) => html`<span class="cal-ev kind-${e.kind}" aria-hidden="true">${e.title}</span>`)}${list.length > 2 ? html`<span class="cal-more" aria-hidden="true">+${list.length - 2}</span>` : ''}</a>`);
  }
  return html`<div class="cal" role="group" aria-label="${+month.slice(5)}월 일정 달력"><div class="cal-head" aria-hidden="true">${[...WD].map((w) => html`<span>${w}</span>`)}</div><div class="cal-body">${cells}</div></div>`;
}

function nav(month, base, extra = '') {
  return html`<div class="cal-nav"><a class="btn secondary sm" href="#${base}?month=${shiftMonth(month, -1)}" aria-label="이전 달">${icon('back')}</a>
    <h2 class="cal-title" aria-live="polite">${month.slice(0, 4)}년 ${+month.slice(5)}월</h2>
    <a class="btn secondary sm" href="#${base}?month=${shiftMonth(month, 1)}" aria-label="다음 달">${icon('arrow')}</a>
    <a class="btn ghost sm" href="#${base}?month=${monthOf(todayKst())}&day=${todayKst()}">오늘</a>${extra}</div>`;
}

const pickDay = (month, events, q) => (q && monthOf(q) === month ? q : monthOf(todayKst()) === month ? todayKst() : events[0]?.start_date > `${month}-00` && monthOf(events[0].start_date) === month ? events[0].start_date : `${month}-01`);

function legend() { return html`<p class="small muted cal-legend">${Object.keys(KIND).map((k) => html`${kindBadge(k)} `)}</p>`; }

function staffDay(e) {
  const staffPrep = e.prep.filter((p) => p.audience === 'staff'), parentPrep = e.prep.filter((p) => p.audience === 'parent');
  const left = staffPrep.filter((p) => !p.done).length;
  return html`<article class="card cal-event" data-event="${e.id}">
    <div class="ev-top">${kindBadge(e.kind)}<b class="ev-title">${e.title}</b>
      ${e.parent_visible ? html`<span class="badge b-ack">${icon('user')} 보호자에게 공개</span>` : html`<span class="badge b-private">${icon('lock')} 직원만 보임</span>`}
      <span class="spacer"></span><button class="btn sm secondary" data-edit="${e.id}">수정</button><button class="btn sm ghost" data-del="${e.id}">삭제</button></div>
    <p class="small muted" style="margin-top:4px">${rangeText(e)} · ${timeText(e)}</p>
    ${e.description ? html`<p style="margin-top:8px">${e.description}</p>` : ''}
    <h4 class="prep-h">직원 준비 항목 ${staffPrep.length ? html`<span class="badge ${left ? 'b-pending' : 'b-ack'}">${left ? `${left}개 남음` : '모두 준비됨'}</span>` : ''}</h4>
    ${staffPrep.length ? html`<ul class="prep">${staffPrep.map((p) => html`<li><label><input type="checkbox" data-prep="${p.id}" ${p.done ? 'checked' : ''}> <span class="${p.done ? 'done' : ''}">${p.text}</span></label>${p.done ? html`<span class="tiny muted">${p.done_by_name} 확인 ${p.done_at.slice(5, 10).replace('-', '/')} ${p.done_at.slice(11, 16)}</span>` : ''}</li>`)}</ul>` : html`<p class="small muted">등록된 준비 항목이 없습니다.</p>`}
    ${parentPrep.length ? html`<h4 class="prep-h">보호자 준비물 안내 <span class="tiny muted">(체크 항목 아님 · 공개 일정에서만 보호자에게 보임)</span></h4><ul class="prep plain">${parentPrep.map((p) => html`<li>${p.text}</li>`)}</ul>` : ''}</article>`;
}

function prepRow(aud, p = {}) {
  return html`<li class="prep-row" data-aud="${aud}" ${p.id ? raw(`data-id="${p.id}"`) : ''}><input class="input" maxlength="80" value="${p.text || ''}" aria-label="${aud === 'staff' ? '직원' : '보호자'} 준비 항목"><button type="button" class="btn ghost sm" data-rm aria-label="항목 삭제">${icon('x')}</button></li>`;
}

function eventForm(ev, defaultDay, onSaved) {
  const e = ev || { title: '', kind: 'event', start_date: defaultDay, end_date: defaultDay, start_time: '', end_time: '', description: '', parent_visible: false, prep: [] };
  const section = (aud, title, hint) => html`<div class="field"><span class="lbl">${title}</span><ul class="prep-edit" data-list="${aud}">${e.prep.filter((p) => p.audience === aud).map((p) => prepRow(aud, p))}</ul>
    <button type="button" class="btn sm secondary" data-add="${aud}">${icon('plus')} 항목 추가</button><p class="hint">${hint}</p></div>`;
  openModal({
    title: ev ? '일정 수정' : '일정 추가', wide: true,
    body: html`<form id="ef" class="stack" novalidate>
      <div class="field"><label for="ef-title">제목</label><input class="input" id="ef-title" name="title" maxlength="60" value="${e.title}"></div>
      <div class="field"><label for="ef-kind">종류</label><select class="input" id="ef-kind" name="kind">${Object.entries(KIND).map(([k, v]) => html`<option value="${k}" ${k === e.kind ? 'selected' : ''}>${v}</option>`)}</select></div>
      <div class="row2"><div class="field"><label for="ef-s">시작 날짜</label><input class="input" type="date" id="ef-s" name="start_date" value="${e.start_date}"></div>
        <div class="field"><label for="ef-e">끝나는 날짜</label><input class="input" type="date" id="ef-e" name="end_date" value="${e.end_date}"></div></div>
      <div class="row2"><div class="field"><label for="ef-st">시작 시간 (비우면 종일)</label><input class="input" type="time" id="ef-st" name="start_time" value="${e.start_time || ''}"></div>
        <div class="field"><label for="ef-et">끝나는 시간</label><input class="input" type="time" id="ef-et" name="end_time" value="${e.end_time || ''}"></div></div>
      <div class="field"><label for="ef-d">설명 <span class="muted small">(보호자 공개 일정이면 보호자도 읽습니다)</span></label><textarea class="input" id="ef-d" name="description" rows="3" maxlength="500">${e.description}</textarea></div>
      <div class="field"><label><input type="checkbox" name="parent_visible" ${e.parent_visible ? 'checked' : ''}> 보호자 일정에 공개</label><p class="hint">체크하지 않으면 직원에게만 보입니다. 이 프로토타입은 보호자에게 알림을 보내지 않으며, 보호자가 앱을 열었을 때 보입니다.</p></div>
      ${section('staff', '직원 준비 항목 (직원 체크리스트)', '최대 10개. 직원 화면에서만 보이고, 완료 체크는 일정 상세에서 합니다.')}
      ${section('parent', '보호자 준비물·안내', '최대 10개. 일정을 보호자에게 공개한 경우에만 문구가 보입니다.')}
      <p class="form-error" id="ef-err" role="alert" hidden></p>
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">${ev ? '저장' : '일정 추가'}</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('#ef'), err = el.querySelector('#ef-err');
      f.addEventListener('click', (x) => {
        const add = x.target.closest('[data-add]'), rm = x.target.closest('[data-rm]');
        if (add) { const ul = f.querySelector(`[data-list="${add.dataset.add}"]`); if (ul.children.length >= 10) { toast('준비 항목은 최대 10개입니다.', 'error'); return; } ul.insertAdjacentHTML('beforeend', prepRow(add.dataset.add).toString()); ul.lastElementChild.querySelector('input').focus(); }
        if (rm) rm.closest('li').remove();
      });
      f.addEventListener('submit', (x) => {
        x.preventDefault(); fieldErrors(f, { errors: [] }); err.hidden = true;
        const v = Object.fromEntries(new FormData(f));
        const prep = [...f.querySelectorAll('.prep-row')].map((li) => ({ id: li.dataset.id ? +li.dataset.id : undefined, audience: li.dataset.aud, text: li.querySelector('input').value.trim() })).filter((p) => p.text);
        const body = { title: v.title, kind: v.kind, start_date: v.start_date, end_date: v.end_date || v.start_date, start_time: v.start_time || null, end_time: v.end_time || null, description: v.description, parent_visible: !!v.parent_visible, prep };
        busy(f.querySelector('[type=submit]'), async () => {
          try { const saved = ev ? await api.updateEvent(ev.id, body) : await api.createEvent(body); close(); toast(ev ? '일정을 저장했습니다.' : '일정을 추가했습니다.'); onSaved(saved); }
          catch (er) { fieldErrors(f, er); if (!(er.errors || []).length || er.errors.some((q) => !f.querySelector(`[name="${q.field}"]`))) { err.textContent = er.message; err.hidden = false; } }
        });
      });
    },
  });
}

/** 직원 캘린더: 한 달 일정을 보고, 선택한 날의 준비 항목을 체크한다. */
export async function calendarView(ctx) {
  const { root, query, go } = ctx;
  const month = /^\d{4}-(0[1-9]|1[0-2])$/.test(query.month || '') ? query.month : monthOf(todayKst());
  const { events } = await api.calendar(month);
  const sel = pickDay(month, events, query.day);
  const dayEvents = events.filter((e) => covers(e, sel));
  const openPrep = events.reduce((n, e) => n + e.prep.filter((p) => p.audience === 'staff' && !p.done).length, 0);
  root.innerHTML = html`
    <div class="page-head"><div><h1>캘린더</h1><p>반 전체 일정을 미리 보고 준비합니다. 이번 달 남은 직원 준비 항목 <b>${openPrep}</b>개</p></div>
      <button class="btn" id="add">${icon('plus')} 일정 추가</button></div>
    ${nav(month, '/calendar')}${legend()}
    ${grid(month, events, sel, '/calendar')}
    <section class="section" aria-labelledby="dt"><div class="head"><h2 id="dt">${fmtDateKo(sel)}</h2></div>
      ${dayEvents.length ? dayEvents.map(staffDay) : empty('이 날은 일정이 없습니다', '일정 추가 버튼으로 등록할 수 있어요.')}</section>`.toString();
  const again = (saved) => {      // 저장한 일정이 있는 날로 이동(주소가 같으면 다시 그린다)
    const d = saved?.start_date || sel, target = `#/calendar?month=${monthOf(d)}&day=${d}`;
    if (location.hash === target) ctx.rerender(); else go(target.slice(1));
  };
  root.querySelector('#add').addEventListener('click', () => eventForm(null, sel, again));
  root.querySelectorAll('[data-edit]').forEach((b) => b.addEventListener('click', () => eventForm(events.find((e) => e.id === +b.dataset.edit), sel, again)));
  root.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => {
    const e = events.find((x) => x.id === +b.dataset.del);
    if (!confirm(`'${e.title}' 일정을 삭제할까요? 준비 항목도 함께 삭제되며 되돌릴 수 없습니다.`)) return;
    busy(b, () => guarded(async () => { await api.deleteEvent(e.id); toast('일정을 삭제했습니다.'); ctx.rerender(); }));
  }));
  root.querySelectorAll('[data-prep]').forEach((c) => c.addEventListener('change', () => busy(c, async () => { await guarded(() => api.togglePrep(+c.dataset.prep)); ctx.rerender(); })));
}

/** 보호자 캘린더: 공개된 일정과 보호자 준비물만 읽기 전용으로 보인다. */
export async function parentCalendarView(ctx) {
  const { query } = ctx;
  const pw = parentFrame(ctx, 'calendar');
  const month = /^\d{4}-(0[1-9]|1[0-2])$/.test(query.month || '') ? query.month : monthOf(todayKst());
  const { events } = await api.parentCalendar(month);
  const sel = pickDay(month, events, query.day);
  const dayEvents = events.filter((e) => covers(e, sel));
  pw.innerHTML = html`<h1>우리 반 일정</h1>
    <p class="muted" style="margin:6px 0 12px">유치원이 공개한 일정만 보입니다. 이 프로토타입에는 알림이 없어서, 앱을 열어야 확인할 수 있습니다.</p>
    ${nav(month, '/parent/calendar')}${legend()}${grid(month, events, sel, '/parent/calendar')}
    <section class="section" aria-labelledby="pdt"><h2 id="pdt" style="margin-bottom:10px">${fmtDateKo(sel)}</h2>
      ${dayEvents.length ? dayEvents.map((e) => html`<article class="feed-card"><div class="ev-top">${kindBadge(e.kind)}<b class="ev-title">${e.title}</b></div>
        <p class="small muted" style="margin-top:4px">${rangeText(e)} · ${timeText(e)}</p>${e.description ? html`<p style="margin-top:8px">${e.description}</p>` : ''}
        ${e.prep.length ? html`<h4 class="prep-h">준비해 주세요</h4><ul class="prep plain">${e.prep.map((p) => html`<li>${p.text}</li>`)}</ul>` : ''}</article>`) : empty('이 날은 공개된 일정이 없습니다', '')}</section>`.toString();
}
