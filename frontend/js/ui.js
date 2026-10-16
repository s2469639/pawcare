import { html, icon, fmtTime, fmtWhen, canAct, esc, raw } from './util.js';
import { ApiError } from './api.js';

/** 사진이 있으면 원형 사진, 없거나 불러오지 못하면 이니셜 아바타로 대체 */
export const avatar = (dog, size = '') => {
  const name = dog.name || dog.dog_name || '?';
  const photo = dog.photo || dog.dog_photo;
  return html`<span class="avatar ${size}" style="background:${dog.avatar_color || dog.dog_color || '#A5AE98'}" aria-hidden="true">${name.slice(0, 1)}${photo ? raw(`<img src="${esc(photo)}" alt="" loading="lazy" onerror="this.remove()">`) : ''}</span>`;
};

export const ackBadge = (t) => t.acknowledgment_status === 'pending'
  ? html`<span class="badge b-pending">${icon('clock')} 확인 대기</span>`
  : html`<span class="badge b-ack">${icon('check')} 확인 완료</span>`;

export const actionBadge = (t) => ({
  todo: html`<span class="badge b-todo">${icon('alert')} 조치 필요</span>`,
  in_progress: html`<span class="badge b-progress">${icon('half')} 진행 중</span>`,
  completed: html`<span class="badge b-done">${icon('check')} 조치 완료</span>`,
}[t.action_status]);

export const prioBadge = (t) => (t.priority === 'high' ? html`<span class="badge b-high">우선</span>` : '');

export const stateClass = (t) => t.action_status === 'completed' ? 's-done'
  : t.acknowledgment_status === 'pending' ? 's-pending' : t.action_status === 'todo' ? 's-todo' : 's-progress';

/** 업무 행. quick: 빠른 처리 버튼 노출 여부 */
export function taskRow(t, staff, { quick = true, showDog = true } = {}) {
  const mine = canAct(staff, t);
  let act = '';
  if (quick && t.action_status !== 'completed') {
    const why = `담당자(${t.assignee_name || '-'})만 처리할 수 있습니다`;
    if (t.acknowledgment_status === 'pending') {
      act = html`<button class="btn sm" data-task-act="acknowledge" data-id="${t.id}" ${mine ? '' : html`disabled title="${why}"`}>${icon('check')} 확인 완료</button>`;
    } else if (t.action_status === 'todo') {
      act = html`<button class="btn sm" data-task-act="start" data-id="${t.id}" ${mine ? '' : html`disabled title="${why}"`}>조치 시작</button>`;
    } else {
      act = html`<a class="btn sm" href="#/tasks/${t.id}?complete=1" ${mine ? '' : html`aria-disabled="true" title="${why}"`}>조치 완료 입력</a>`;
    }
  }
  return html`<article class="task-row ${stateClass(t)}" data-task="${t.id}">
    ${showDog ? html`<a class="task-dog" href="#/dogs/${t.dog_id}">${avatar({ name: t.dog_name, avatar_color: t.dog_color, photo: t.dog_photo }, 'sm')}<span>${t.dog_name}</span></a>` : html`<span></span>`}
    <div>
      <a class="task-title" href="#/tasks/${t.id}">${t.title}</a>
      ${t.description ? html`<p class="task-desc">${t.description}</p>` : ''}
      <p class="task-meta">${t.source_record_id ? html`출처 ${fmtTime(t.src_observed_at)} ${t.src_type} 기록 · ` : '직접 등록 · '}담당 ${t.assignee_name ? html`${t.assignee_name} (${t.assignee_role})` : '미지정'} · 등록 ${t.creator_name}, ${fmtWhen(t.created_at)}</p>
    </div>
    <div class="task-status">${ackBadge(t)}${actionBadge(t)}${prioBadge(t)}${t.ai_suggested ? html`<span class="badge b-ai">${icon('spark')} AI 제안 승인</span>` : ''}</div>
    <div class="task-actions">${act}<a class="btn sm secondary" href="#/tasks/${t.id}">상세 보기</a></div>
  </article>`;
}

export const empty = (title, text, cta = '') => html`<div class="empty"><strong>${title}</strong>${text}${cta}</div>`;
export const skeleton = (n = 3) => html`<div aria-busy="true" aria-label="불러오는 중">${Array.from({ length: n }, () => html`<div class="skeleton"></div>`)}</div>`;
export const errorBox = (e) => html`<div class="errbox" role="alert"><h3>화면을 불러오지 못했습니다</h3><p class="muted" style="margin:6px 0 12px">${e.message || '알 수 없는 오류'}</p><button class="btn secondary" data-retry>다시 시도</button></div>`;

export function toast(msg, type = 'ok') {
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : ''}`;
  el.setAttribute('role', type === 'error' ? 'alert' : 'status');
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), type === 'error' ? 6000 : 3500);
}

/** 중복 제출 방지: 실행 중에는 버튼을 잠근다. */
export async function busy(btn, fn) {
  if (btn.disabled) return;
  btn.disabled = true; btn.classList.add('busy');
  try { return await fn(); } finally { btn.disabled = false; btn.classList.remove('busy'); }
}

export async function guarded(fn, { onAuth } = {}) {
  try { return await fn(); } catch (e) {
    if (e instanceof ApiError && e.status === 401 && onAuth) onAuth();
    toast(e.message || '오류가 발생했습니다.', 'error');
    return undefined;
  }
}

export function fieldErrors(root, err) {
  root.querySelectorAll('.error').forEach((n) => n.remove());
  root.querySelectorAll('.err').forEach((n) => { n.classList.remove('err'); n.removeAttribute('aria-invalid'); });
  (err.errors || []).forEach((e) => showFieldError(root, e.field, e.message));
}
export function showFieldError(root, name, message) {
  const inp = root.querySelector(`[name="${name}"]`);
  const wrap = (inp && inp.closest('.field')) || root.querySelector(`[data-field="${name}"]`);
  if (!wrap) { toast(message, 'error'); return; }
  if (inp) { inp.classList.add('err'); inp.setAttribute('aria-invalid', 'true'); }
  const p = document.createElement('p');
  p.className = 'error'; p.id = `err-${name}`; p.textContent = message;
  wrap.appendChild(p);
  if (inp) inp.setAttribute('aria-describedby', p.id);
}

export function openModal({ title, body, onMount, onClose, wide = false }) {
  const prev = document.activeElement;
  const ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML = `<div class="modal${wide ? ' wide' : ''}" role="dialog" aria-modal="true" aria-labelledby="mt"><div class="mh"><h2 id="mt">${esc(title)}</h2><button class="btn ghost sm" data-close aria-label="닫기">✕</button></div><div class="mb">${body}</div></div>`;
  document.body.appendChild(ov);
  const close = () => { if (!ov.isConnected) return; ov.remove(); document.removeEventListener('keydown', onKey); prev?.focus?.(); onClose?.(); };
  // 모달이 겹쳐 열린 경우 ESC는 가장 위의 창만 닫는다
  const onKey = (e) => { if (e.key === 'Escape' && [...document.querySelectorAll('.overlay')].pop() === ov) close(); };
  document.addEventListener('keydown', onKey);
  ov.addEventListener('mousedown', (e) => { if (e.target === ov) close(); });
  ov.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', close));
  onMount?.(ov.querySelector('.mb'), close);
  (ov.querySelector('input, textarea, select') || ov.querySelector('button')).focus();
  return close;
}

/** 데모 모드의 계정 전환 드롭다운(직원·보호자 공용). 옵션 라벨은 '역할 · 이름'. */
export function demoSelect(accounts, meId) {
  const groups = {};
  accounts.forEach((a) => (groups[a.org_name] ||= []).push(a));
  return html`<select id="who" class="input" style="width:auto" aria-label="데모 계정 전환">${Object.entries(groups).map(([org, list]) =>
    html`<optgroup label="${org}">${list.map((a) => html`<option value="${a.id}" ${a.id === meId ? 'selected' : ''}>${a.role === 'staff' ? `${a.staff_role} · ${a.name}` : `보호자 · ${a.name} (${a.dogs || '-'})`}</option>`)}</optgroup>`)}</select>`;
}
