import { api } from './api.js';
import { html, icon, FILTERS, matchFilter, groupKey, GROUP_LABEL, fmtWhen, fmtTime, canAct } from './util.js';
import { taskRow, empty, ackBadge, actionBadge, prioBadge, avatar, busy, guarded, toast, openModal, fieldErrors, showFieldError } from './ui.js';
import { ApiError } from './api.js';

/** 목록 행의 [확인 완료]/[조치 시작] 버튼 처리 */
export function bindTaskActions(root, ctx) {
  root.querySelectorAll('[data-task-act]').forEach((b) => b.addEventListener('click', () => busy(b, () => guarded(async () => {
    const act = b.dataset.taskAct;
    await api.taskAction(+b.dataset.id, act);
    toast(act === 'acknowledge' ? '확인 완료로 변경했습니다. 조치 상태는 그대로입니다.' : '조치를 시작했습니다.');
    ctx.rerender();
  }))));
}

export async function tasksView(ctx) {
  const { root, staff, query } = ctx;
  const f = FILTERS.some(([k]) => k === query.filter) ? query.filter : 'all';
  const mineOnly = query.mine === '1';
  const [tasks, members] = await Promise.all([api.tasks(), api.staff()]);
  const assignee = +query.assignee || 0;
  const base = tasks.filter((t) => (!mineOnly || t.assignee_id === staff.id) && (!assignee || t.assignee_id === assignee));
  const list = base.filter((t) => matchFilter(t, f));
  const href = (o) => { const p = { filter: f, mine: mineOnly ? '1' : '', assignee: assignee || '', ...o }; const s = new URLSearchParams(Object.entries(p).filter(([k, v]) => v && !(k === 'filter' && v === 'all'))).toString(); return `#/tasks${s ? `?${s}` : ''}`; };
  root.innerHTML = html`
    <div class="page-head"><div><h1>업무 인계</h1><p>기록에서 만들어진 후속 업무가 확인되고 조치될 때까지 이어지는 곳입니다. 확인 완료와 조치 완료는 별개입니다.</p></div>
      <button class="btn" id="new-task">${icon('plus')} 업무 직접 등록</button></div>
    <div class="toolbar">
      <div class="chips" role="group" aria-label="상태 필터">${FILTERS.map(([k, label]) => html`<a class="chip" href="${href({ filter: k })}" ${f === k ? html`aria-current="true"` : ''}>${label} <span class="n">${base.filter((t) => matchFilter(t, k)).length}</span></a>`)}</div>
      <a class="chip" href="${href({ mine: mineOnly ? '' : '1' })}" aria-pressed="${mineOnly}">내 담당만</a>
      <label class="sr" for="asg">담당자 필터</label>
      <select id="asg" class="input" style="width:auto"><option value="">모든 담당자</option>${members.map((m) => html`<option value="${m.id}" ${m.id === assignee ? 'selected' : ''}>${m.role} · ${m.name}</option>`)}</select>
    </div>
    ${list.length ? ['pending', 'todo', 'in_progress', 'completed'].map((k) => [k, list.filter((t) => groupKey(t) === k)]).filter(([, l]) => l.length)
      .map(([k, l]) => html`<div class="group-label">${GROUP_LABEL[k]} <span class="badge b-done">${l.length}</span></div><div class="task-list">${l.map((t) => taskRow(t, staff))}</div>`)
      : empty('조건에 맞는 업무가 없습니다', '필터를 바꾸거나 새 업무를 등록해 보세요.')}`.toString();
  root.querySelector('#asg').addEventListener('change', (e) => { location.hash = href({ assignee: e.target.value }).slice(1); });
  root.querySelector('#new-task').addEventListener('click', () => openTaskModal(ctx, {}));
  bindTaskActions(root, ctx);
}

/** 업무 직접 등록(또는 수정) 모달 */
export async function openTaskModal(ctx, { dog_id, source_record_id, task } = {}) {
  const [dogs, members] = await Promise.all([api.dogs(), api.staff()]);
  const t = task || {};
  openModal({
    title: task ? '업무 수정' : '업무 직접 등록',
    body: html`<form class="stack" novalidate>
      ${task ? '' : html`<div class="field"><label for="m-dog">반려견 *</label><select class="input" id="m-dog" name="dog_id"><option value="">선택하세요</option>${dogs.map((d) => html`<option value="${d.id}" ${d.id === dog_id ? 'selected' : ''}>${d.name} (${d.breed})</option>`)}</select></div>`}
      <div class="field"><label for="m-title">업무 제목 *</label><input class="input" id="m-title" name="title" maxlength="80" value="${t.title || ''}"></div>
      <div class="field"><label for="m-desc">업무 설명</label><textarea class="input" id="m-desc" name="description" maxlength="500">${t.description || ''}</textarea></div>
      <div class="row2"><div class="field"><label for="m-asg">담당자</label><select class="input" id="m-asg" name="assignee_id"><option value="">미지정</option>${members.map((m) => html`<option value="${m.id}" ${m.id === t.assignee_id ? 'selected' : ''}>${m.role} · ${m.name}</option>`)}</select></div>
        <div class="field"><label for="m-pri">우선순위</label><select class="input" id="m-pri" name="priority">${[['normal', '보통'], ['high', '높음'], ['low', '낮음']].map(([v, l]) => html`<option value="${v}" ${(t.priority || 'normal') === v ? 'selected' : ''}>${l}</option>`)}</select></div></div>
      ${source_record_id ? html`<p class="small muted">원본 기록 #${source_record_id}과 연결되어 등록됩니다.</p>` : ''}
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">${task ? '저장' : '업무 등록'}</button></div>
    </form>`.toString(),
    onMount(el, close) {
      const form = el.querySelector('form');
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const v = Object.fromEntries(new FormData(form));
        fieldErrors(form, { errors: [] });
        const submit = form.querySelector('[type=submit]');
        busy(submit, async () => {
          try {
            if (!task && !v.dog_id) { showFieldError(form, 'dog_id', '반려견을 선택해 주세요.'); return; }
            if (!v.title.trim()) { showFieldError(form, 'title', '업무 제목을 입력해 주세요.'); return; }
            const body = { title: v.title, description: v.description, assignee_id: v.assignee_id ? +v.assignee_id : null, priority: v.priority };
            const res = task ? await api.patchTask(task.id, body) : await api.createTask({ ...body, dog_id: +v.dog_id, source_record_id });
            close(); toast(task ? '업무를 수정했습니다.' : '업무를 등록했습니다. 담당자의 확인을 기다립니다.');
            if (!task) ctx.go(`/tasks/${res.id}`); else ctx.rerender();
          } catch (err) {
            if (err instanceof ApiError && err.errors.length) fieldErrors(form, err); else toast(err.message, 'error');
          }
        });
      });
    },
  });
}

export async function taskDetailView(ctx) {
  const { root, staff, query, params } = ctx;
  const [t, members] = await Promise.all([api.task(params[0]), api.staff()]);
  const mine = canAct(staff, t);
  const done = t.action_status === 'completed';
  const why = `담당자(${t.assignee_name || '-'})만 처리할 수 있습니다. 상단에서 시연 담당자를 전환하거나 담당자를 변경하세요.`;
  const ackBtn = t.acknowledgment_status === 'pending' && !done;
  root.innerHTML = html`
    <a class="crumb" href="#/tasks">${icon('back')} 업무 인계</a>
    <div class="detail">
      <div class="stack">
        <div class="card">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px"><a class="task-dog" href="#/dogs/${t.dog_id}">${avatar({ name: t.dog_name, avatar_color: t.dog_color, photo: t.dog_photo }, 'sm')} ${t.dog_name}</a>${prioBadge(t)}${t.ai_suggested ? html`<span class="badge b-ai">${icon('spark')} AI 제안을 직원이 승인</span>` : ''}</div>
          <h1>${t.title}</h1>
          <p style="margin-top:8px">${t.description || html`<span class="muted">설명 없음</span>`}</p>
          ${done ? '' : html`<p style="margin-top:10px"><button class="btn sm secondary" id="edit">${icon('pen')} 제목·설명 수정</button></p>`}
          <hr class="sep">
          <h3 style="margin-bottom:8px">원본 기록</h3>
          ${t.source_record_id ? html`<div class="quote"><p class="small muted">${fmtWhen(t.src_observed_at)} · ${t.src_type} 기록 #${t.source_record_id}</p><p>${t.src_content}</p></div>` : html`<p class="muted small">원본 기록 없이 직접 등록한 업무입니다.</p>`}
        </div>
        <div class="statebox" aria-label="업무 상태">
          <div><div class="cap">확인 상태 — 담당자가 인계 내용을 봤는가</div>${ackBadge(t)}<div class="when">${t.acknowledged_at ? `${t.ack_by_name} · ${fmtWhen(t.acknowledged_at)}` : '아직 확인하지 않았습니다'}</div></div>
          <div><div class="cap">조치 상태 — 실제로 수행했는가</div>${actionBadge(t)}<div class="when">${t.completed_at ? `완료 ${fmtWhen(t.completed_at)}` : '확인만으로는 조치 완료가 되지 않습니다'}</div></div>
        </div>
        ${done ? html`<div class="card"><h3>조치 결과</h3><p style="margin-top:6px">${t.completion_note}</p><p class="small muted" style="margin-top:6px">완료 시각 ${fmtWhen(t.completed_at)}</p></div>` : html`
        <div class="card" id="act-card"><h3>처리</h3>
          ${mine ? '' : html`<p class="callout clay" style="margin:10px 0">${why}</p>`}
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin:12px 0">
            ${ackBtn ? html`<button class="btn" id="ack" ${mine ? '' : 'disabled'}>${icon('check')} 확인 완료</button>` : ''}
            ${t.action_status === 'todo' ? html`<button class="btn secondary" id="start" ${mine ? '' : 'disabled'}>조치 시작</button>` : ''}
          </div>
          <form id="complete" novalidate>
            <div class="field"><label for="note">조치 결과 * <span class="muted small">(실제로 수행한 내용을 직접 입력하세요)</span></label>
              <textarea class="input" id="note" name="note" maxlength="500" placeholder="예: 오후 배변 상태를 확인했습니다. 기록 결과: …" ${mine ? '' : 'disabled'}></textarea></div>
            <p style="margin-top:10px"><button class="btn clay" type="submit" ${mine ? '' : 'disabled'}>${icon('check')} 조치 완료</button></p>
          </form>
        </div>`}
      </div>
      <aside class="stack">
        <div class="card"><h3>담당자</h3>
          <p style="margin:6px 0 10px">${t.assignee_name ? html`<b>${t.assignee_name}</b> <span class="muted">${t.assignee_role}</span>` : '미지정'}</p>
          ${done ? '' : html`<label class="small muted" for="asg">담당자 변경</label>
          <div style="display:flex;gap:6px;margin-top:4px"><select id="asg" class="input" style="min-width:0"><option value="">미지정</option>${members.map((m) => html`<option value="${m.id}" ${m.id === t.assignee_id ? 'selected' : ''}>${m.role} · ${m.name}</option>`)}</select><button class="btn secondary" id="reassign">변경</button></div>
          <p class="tiny muted" style="margin-top:6px">담당자를 바꿔도 확인·조치 상태는 그대로 유지됩니다.</p>`}
          <hr class="sep"><p class="small muted">등록 ${t.creator_name} (${t.creator_role})<br>${fmtWhen(t.created_at)}</p></div>
        <div class="card"><h3 style="margin-bottom:10px">변경 이력</h3>
          <ol class="log">${t.logs.map((l) => html`<li><span class="who">${l.actor_name}</span> <span class="muted">${LABEL[l.action_type] || l.action_type}</span><div class="at">${fmtWhen(l.created_at)}</div>${l.note && !['created', 'acknowledge', 'start'].includes(l.action_type) ? html`<div>${l.note}</div>` : ''}</li>`)}</ol>
          ${done ? '' : html`<form id="memo" class="stack" style="margin-top:6px" novalidate><label class="sr" for="memo-t">메모</label><input class="input" id="memo-t" name="note" maxlength="500" placeholder="메모 남기기"><button class="btn sm secondary">메모 추가</button></form>`}
        </div>
      </aside>
    </div>`.toString();

  const run = (btn, fn) => busy(btn, () => guarded(fn));
  root.querySelector('#ack')?.addEventListener('click', (e) => run(e.currentTarget, async () => { await api.taskAction(t.id, 'acknowledge'); toast('확인 완료로 변경했습니다. 조치 상태는 그대로입니다.'); ctx.rerender(); }));
  root.querySelector('#start')?.addEventListener('click', (e) => run(e.currentTarget, async () => { await api.taskAction(t.id, 'start'); toast('조치를 시작했습니다.'); ctx.rerender(); }));
  root.querySelector('#reassign')?.addEventListener('click', (e) => run(e.currentTarget, async () => {
    const v = root.querySelector('#asg').value;
    await api.patchTask(t.id, { assignee_id: v ? +v : null }); toast('담당자를 변경했습니다. 확인·조치 상태는 유지됩니다.'); ctx.rerender();
  }));
  root.querySelector('#edit')?.addEventListener('click', () => openTaskModal(ctx, { task: t }));
  const form = root.querySelector('#complete');
  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    fieldErrors(form, { errors: [] });
    const note = form.note.value.trim();
    if (!note) { showFieldError(form, 'note', '조치 결과를 입력해야 조치 완료로 변경할 수 있습니다.'); form.note.focus(); return; }
    run(form.querySelector('[type=submit]'), async () => { await api.taskAction(t.id, 'complete', note); toast('조치 완료로 기록했습니다.'); ctx.rerender(); });
  });
  root.querySelector('#memo')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const note = e.target.note.value.trim();
    if (!note) { showFieldError(e.target, 'note', '메모 내용을 입력해 주세요.'); return; }
    run(e.target.querySelector('button'), async () => { await api.taskAction(t.id, 'comment', note); ctx.rerender(); });
  });
  if (query.complete === '1') { root.querySelector('#note')?.focus(); root.querySelector('#act-card')?.scrollIntoView({ block: 'center' }); }
}

const LABEL = { created: '업무를 등록했습니다', acknowledge: '확인 완료로 변경했습니다', start: '조치를 시작했습니다', complete: '조치 완료로 기록했습니다', reassign: '담당자를 변경했습니다', edit: '업무 내용을 수정했습니다', comment: '메모를 남겼습니다' };
