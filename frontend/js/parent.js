import { api } from './api.js';
import { html, icon, fmtWhen } from './util.js';
import { avatar, empty, errorBox, demoSelect, guarded } from './ui.js';

/** 보호자 화면: 본인에게 연결된 반려견의 '직원이 공개 승인한' 기록만 보인다. */
export async function parentView({ root, me, demo, demoAccounts, logout, demoSwitch }) {
  root.innerHTML = html`<div class="parent-wrap"><header class="parent-bar">
      <a class="brand dark" href="#/parent"><img src="assets/favicon.svg" width="26" height="26" alt=""><span class="word">PawCare</span></a><span class="spacer"></span>
      ${demo ? html`<label class="small muted" for="who">시연 계정</label>${demoSelect(demoAccounts, me.id)}` : html`<span class="small">${me.name}님</span>`}
      <button class="btn secondary sm" id="logout">${demo ? '처음 화면으로' : '로그아웃'}</button></header>
    <div id="pw"></div></div>`.toString();
  root.querySelector('#logout').addEventListener('click', logout);
  root.querySelector('#who')?.addEventListener('change', (e) => guarded(() => demoSwitch(+e.target.value)));
  const pw = root.querySelector('#pw');
  try {
    const dogs = await api.parentDogs();
    let cur = dogs[0]?.id;
    const paint = async () => {
      const p = cur ? await api.parentPreview(cur) : null;
      pw.innerHTML = html`<h1>${me.name}님의 알림장</h1>
        <p class="muted" style="margin:6px 0 16px">직원이 검토하고 <b>공개 승인한 기록만</b> 보입니다. 이번 프로토타입은 사진·영상 전송, 알림 기능이 없으며, 앱을 열어야 확인할 수 있습니다.</p>
        <div class="callout" style="margin-bottom:16px"><b>공개 범위 원칙</b> · 직원 내부 메모와 업무 인계 내용은 비공개 · 직원이 승인한 기록만 표시 · AI 초안은 승인 전까지 공개되지 않음<br>실제 보호자에게 전송되는 메시지는 없습니다.</div>
        ${dogs.length ? html`<div class="chips" role="group" aria-label="내 반려견" style="margin-bottom:16px">${dogs.map((d) => html`<button class="chip" data-d="${d.id}" aria-pressed="${d.id === cur}">${d.name}</button>`)}</div>` : empty('연결된 반려견이 없습니다', '유치원에 문의해 주세요.')}
        ${p ? html`<div class="phone"><div style="display:flex;gap:12px;align-items:center;margin-bottom:10px">${avatar(p.dog)}<div><div class="serif" style="font-weight:700;font-size:18px">${p.dog.name}</div><div class="small muted">${p.dog.breed} · ${p.dog.age_text}</div></div></div>
          <p class="tiny muted" style="margin-bottom:4px">알림장</p>
          ${p.records.length ? p.records.map((r) => html`<div class="rec"><span class="badge b-ack">${r.record_type}</span><p style="margin-top:4px">${r.parent_text}</p><p class="tiny muted">공개 승인 ${fmtWhen(r.parent_approved_at)}</p></div>`)
            : empty('공개된 기록이 없습니다', '직원이 기록을 공개 승인하면 이곳에 표시됩니다.')}</div>` : ''}`.toString();
      pw.querySelectorAll('[data-d]').forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.d; paint(); }));
    };
    await paint();
  } catch (e) {
    pw.innerHTML = errorBox(e).toString();
    pw.querySelector('[data-retry]')?.addEventListener('click', () => location.reload());
  }
}
