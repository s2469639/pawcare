import { api } from './api.js';
import { html, icon, fmtWhen } from './util.js';
import { avatar, empty, errorBox } from './ui.js';

export async function parentView({ root }) {
  root.innerHTML = '<div class="parent-wrap" id="pw"></div>';
  const pw = root.querySelector('#pw');
  try {
    const dogs = await api.parentDogs();
    let cur = dogs[0]?.id;
    const paint = async () => {
      const p = cur ? await api.parentPreview(cur) : null;
      pw.innerHTML = html`<a class="crumb" href="#/">${icon('back')} 역할 선택</a>
        <h1>보호자 안내</h1>
        <p class="muted" style="margin:6px 0 16px">이번 프로토타입은 직원 업무 관리가 중심이며, 보호자용 전체 서비스는 아직 구현되지 않았습니다. 아래는 직원이 <b>공개 승인한 기록만</b> 보호자에게 보이는 구조를 미리 보는 화면입니다.</p>
        <div class="callout" style="margin-bottom:16px"><b>공개 범위 원칙</b> · 직원 내부 메모와 업무 인계 내용은 비공개 · 직원이 검토하고 승인한 기록만 표시 · AI 초안은 승인 전까지 공개되지 않음<br>이 화면은 미리보기이며 실제로 보호자에게 전송된 내용이 아닙니다.</div>
        <div class="chips" role="group" aria-label="샘플 반려견" style="margin-bottom:16px">${dogs.map((d) => html`<button class="chip" data-d="${d.id}" aria-pressed="${d.id === cur}">${d.name}</button>`)}</div>
        ${p ? html`<div class="phone"><div style="display:flex;gap:12px;align-items:center;margin-bottom:10px">${avatar(p.dog)}<div><div class="serif" style="font-weight:700;font-size:18px">${p.dog.name}</div><div class="small muted">${p.dog.breed} · ${p.dog.age_text} · 보호자 ${p.dog.owner_name} (샘플)</div></div></div>
          <p class="tiny muted" style="margin-bottom:4px">오늘의 알림장 · 미리보기</p>
          ${p.records.length ? p.records.map((r) => html`<div class="rec"><span class="badge b-ack">${r.record_type}</span><p style="margin-top:4px">${r.parent_text}</p><p class="tiny muted">공개 승인 ${fmtWhen(r.parent_approved_at)}</p></div>`)
            : empty('공개 승인된 기록이 없습니다', '직원이 반려견 프로필에서 기록을 공개 승인하면 이곳에 표시됩니다.')}</div>` : ''}`.toString();
      pw.querySelectorAll('[data-d]').forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.d; paint(); }));
    };
    await paint();
  } catch (e) {
    pw.innerHTML = errorBox(e).toString();
    pw.querySelector('[data-retry]')?.addEventListener('click', () => location.reload());
  }
}
