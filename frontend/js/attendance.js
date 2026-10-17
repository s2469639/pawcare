import { api } from './api.js';
import { html, icon, fmtTime, fmtDateKo } from './util.js';
import { avatar, empty, busy, guarded, toast, openModal, fieldErrors } from './ui.js';

export const WEEKDAYS = '월화수목금토일';
/** 이용 요일 선택(유치원). 선택하지 않으면 자동 출석 예정이 없고, 필요한 날 직접 추가한다. */
export const daysField = (days = []) => html`<div class="field" data-field="attend_days"><span class="lbl" id="days-l">이용 요일</span>
  <div class="days" role="group" aria-labelledby="days-l">${[...WEEKDAYS].map((w, i) => html`<label><input type="checkbox" name="attend_days" value="${i}" ${days.includes(i) ? 'checked' : ''}>${w}</label>`)}</div>
  <p class="hint">정해 두면 그날 자동으로 출석 예정이 됩니다. 쿠폰제처럼 요일이 불규칙하면 비워 두고 출석부에서 오늘 직접 추가하세요.</p></div>`;
export const readDays = (form) => [...form.querySelectorAll('[name=attend_days]:checked')].map((c) => +c.value);
const SOURCE = { weekday: '정기 요일', stay: '숙박 기간', manual: '직접 추가' };

const srcBadge = (d) => (d.source ? html`<span class="badge b-done">${SOURCE[d.source]}</span>` : '');

function row(d, buttons) {
  return html`<li class="att-row" data-dog="${d.id}"><a class="task-dog" href="#/dogs/${d.id}">${avatar(d, 'sm')}<span>${d.name}</span></a>
    <div class="att-info">${d.status === 'present' ? html`<span class="badge b-ack">${icon('check')} 등원 ${fmtTime(d.checkin_at)}</span>${d.checkout_at ? html` <span class="badge b-done">하원 ${fmtTime(d.checkout_at)}${d.pickup_by ? ` · ${d.pickup_by}` : ''}</span>` : ''}${d.checkout_at && d.note ? html`<span class="small muted"> ${d.note}</span>` : ''}`
      : d.status === 'absent' ? html`<span class="badge ${d.absent_contacted ? 'b-done' : 'b-pending'}">결석 · ${d.absent_contacted ? '사전 연락 있음' : '연락 없음'}</span>${d.note ? html` <span class="small muted">${d.note}</span>` : ''}`
      : srcBadge(d)}</div>
    <div class="att-actions">${buttons}</div></li>`;
}

const btn = (act, label, cls = 'secondary') => html`<button class="btn sm ${cls}" data-act="${act}">${label}</button>`;

function section(title, list, buttons, hint = '') {
  return html`<section class="section" aria-label="${title}"><div class="head"><h2>${title} <span class="badge b-done">${list.length}</span></h2>${hint}</div>
    ${list.length ? html`<div class="panel" style="padding:4px 16px"><ul class="att-list">${list.map((d) => row(d, buttons(d)))}</ul></div>` : ''}</section>`;
}

function checkoutModal(d, done) {
  openModal({
    title: `${d.name} 하원 처리`,
    body: html`<form class="stack" novalidate><p class="small muted">등원 ${fmtTime(d.checkin_at)}. 하원 시각은 지금으로 기록됩니다.</p>
      <div class="field"><label for="co-by">데려간 사람 <span class="muted small">(선택)</span></label><input class="input" id="co-by" name="pickup_by" maxlength="40" placeholder="예: 보호자 본인, 가족"></div>
      <div class="field"><label for="co-note">하원 전달사항 <span class="muted small">(선택)</span></label><textarea class="input" id="co-note" name="note" rows="3" maxlength="200" placeholder="예: 오후에 물을 많이 마셨어요"></textarea></div>
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">하원 처리</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        busy(f.querySelector('[type=submit]'), async () => {
          try { await api.attCheckout(d.id, { pickup_by: f.pickup_by.value, note: f.note.value }); close(); toast(`${d.name} 하원 처리했습니다.`); done(); }
          catch (er) { fieldErrors(f, er); if (!(er.errors || []).length) toast(er.message, 'error'); }
        });
      });
    },
  });
}

function absentModal(d, done) {
  openModal({
    title: `${d.name} 결석 처리`,
    body: html`<form class="stack" novalidate>
      <label class="check"><input type="checkbox" name="contacted"> 보호자가 미리 연락했어요</label>
      <div class="field"><label for="ab-note">사유 메모 <span class="muted small">(선택)</span></label><input class="input" id="ab-note" name="note" maxlength="100" placeholder="예: 병원 방문, 여행"></div>
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">결석 처리</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        busy(f.querySelector('[type=submit]'), async () => {
          try { await api.attAbsent(d.id, { contacted: f.contacted.checked, note: f.note.value }); close(); toast(`${d.name} 결석 처리했습니다.`); done(); }
          catch (er) { fieldErrors(f, er); if (!(er.errors || []).length) toast(er.message, 'error'); }
        });
      });
    },
  });
}

/** 오늘의 출석부: 출석 예정 → 등원 체크 → 하원, 또는 결석. */
export async function attendanceView(ctx) {
  const { root } = ctx;
  const v = await api.attendance();
  const by = (s) => v.dogs.filter((d) => d.status === s);
  const expected = by('expected'), present = by('present'), absent = by('absent'), none = by(null);
  const s = v.summary;
  root.innerHTML = html`
    <div class="page-head"><div><h1>오늘의 출석부</h1><p>${fmtDateKo(v.date)} · 등원 체크한 아이가 일과 화면과 일괄 기록의 대상이 됩니다.</p></div></div>
    <div class="stats" role="list">
      <div class="stat" role="listitem"><div class="label">${icon('clock')} 출석 예정</div><div class="num">${s.expected}</div><div class="sub">마리 · 아직 등원 전</div></div>
      <div class="stat" role="listitem"><div class="label">${icon('check')} 출석</div><div class="num">${s.present}</div><div class="sub">마리 · 하원 ${s.checked_out}</div></div>
      <div class="stat" role="listitem"><div class="label">${icon('alert')} 결석</div><div class="num">${s.absent}</div><div class="sub">마리</div></div>
      <div class="stat" role="listitem"><div class="label">${icon('dog')} 오늘 일정 없음</div><div class="num">${s.none}</div><div class="sub">마리 · 필요하면 직접 추가</div></div>
    </div>
    ${section('출석 예정', expected, () => html`${btn('checkin', '등원 체크', '')}${btn('absent', '결석')}`,
      expected.length > 1 ? html`<button class="btn sm" id="all-in">${icon('check')} 예정된 아이 모두 등원 체크</button>` : '')}
    ${expected.length === 0 && s.present === 0 && s.absent === 0 ? html`<p class="callout" style="margin-top:14px">오늘 출석 예정인 아이가 없습니다. 아이마다 <b>이용 요일</b>(프로필 수정)을 정해 두면 그날 자동으로 출석 예정이 됩니다. 아래에서 오늘 직접 추가할 수도 있어요.</p>` : ''}
    ${section('출석', present, (d) => html`${d.checkout_at ? '' : btn('checkout', '하원 처리', '')}${btn('undo', '되돌리기', 'ghost')}`)}
    ${section('결석', absent, () => html`${btn('checkin', '등원 체크')}${btn('undo', '되돌리기', 'ghost')}`)}
    ${section('오늘 일정 없는 아이', none, () => html`${btn('add', '오늘 추가')}${btn('checkin', '바로 등원 체크')}`)}
    ${v.dogs.length === 0 ? empty('재원 중인 반려견이 없습니다', '반려견을 먼저 등록해 주세요.') : ''}`.toString();

  const again = () => ctx.rerender();
  const dogOf = (el) => v.dogs.find((d) => d.id === +el.closest('[data-dog]').dataset.dog);
  root.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => {
    const d = dogOf(b), act = b.dataset.act;
    if (act === 'checkout') return checkoutModal(d, again);
    if (act === 'absent') return absentModal(d, again);
    const call = { checkin: () => api.attCheckin(d.id), add: () => api.attAdd(d.id), undo: () => api.attUndo(d.id) }[act];
    busy(b, () => guarded(async () => { await call(); if (act === 'checkin') toast(`${d.name} 등원 체크했습니다.`); }).then(() => again()));
  }));
  root.querySelector('#all-in')?.addEventListener('click', (e) => busy(e.target.closest('button'), () => guarded(async () => {
    for (const d of expected) await api.attCheckin(d.id);
    toast(`${expected.length}마리를 등원 체크했습니다.`);
  }).then(() => again())));
}
