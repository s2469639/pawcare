import { api, ApiError } from './api.js';
import { html, icon, fmtTime, fmtWhen, nowKstLocalInput, esc } from './util.js';
import { empty, busy, guarded, toast, fieldErrors, showFieldError, skeleton, avatar } from './ui.js';
import { openTaskModal } from './tasks.js';
import { photoAttachField, bindPhotoAttach, uploadAll } from './media.js';

const TYPES = ['식사', '배변', '활동', '행동', '특이사항', '기타'];
const QUICK = {
  식사: ['잘 먹음', '평소보다 적게 먹음', '먹지 않음', '직접 입력'],
  배변: ['정상', '평소와 다름', '관찰 필요', '직접 입력'],
  활동: ['평소와 비슷함', '활발함', '활동량이 적음', '직접 입력'],
};

export async function recordNewView(ctx) {
  const { root, query, staff } = ctx;
  const [dogs, members, routine] = await Promise.all([api.dogs(), api.staff(), api.routine()]);
  const blocks = routine.blocks;
  const preset = blocks.find((b) => String(b.id) === query.block);
  let type = preset && QUICK[preset.record_type] ? preset.record_type : '식사';
  const blockAt = (local) => { const t = (local || '').slice(11, 16); return blocks.find((b) => b.start_time <= t && t < b.end_time); };
  root.innerHTML = html`<div class="page-head"><div><h1>돌봄 기록 작성</h1><p>선택형 입력으로 빠르게 남기고, 필요한 경우에만 메모를 덧붙입니다.</p></div></div>
    <div id="done"></div>
    <form class="form" id="f" novalidate>
      <div class="field"><label for="dog">반려견 *</label><select class="input" id="dog" name="dog_id"><option value="">선택하세요</option>${dogs.map((d) => html`<option value="${d.id}" ${String(d.id) === query.dog ? 'selected' : ''}>${d.name} (${d.breed})</option>`)}</select></div>
      <div class="field" data-field="record_type"><span class="lbl" id="tl">기록 유형 *</span><div class="seg" role="radiogroup" aria-labelledby="tl">${TYPES.map((t, i) => html`<input type="radio" name="record_type" id="t${i}" value="${t}" ${t === type ? 'checked' : ''}><label for="t${i}">${t}</label>`)}</div></div>
      <div class="field" data-field="structured_value" id="quick"></div>
      <div class="field"><label for="content">상세 메모</label><textarea class="input" id="content" name="content" maxlength="1000" placeholder="예: 점심을 평소보다 적게 먹었습니다. 오후 담당자는 …"></textarea>
        <p class="hint">다음 담당자가 해야 할 일이 있다면 문장에 적어 주세요. 기록을 저장해도 업무는 자동으로 만들어지지 않습니다.</p></div>
      ${photoAttachField(dogs)}
      <div class="field"><label for="block">일과 구간</label><select class="input" id="block" name="block_id"></select>
        <p class="hint">기록 시각에 맞춰 자동으로 정해지고, 필요하면 직접 바꿀 수 있어요.</p></div>
      <div class="row2"><div class="field"><label for="at">기록 시각</label><input class="input" type="datetime-local" id="at" name="observed_at" value="${nowKstLocalInput()}"></div>
        <div class="field"><label for="author">기록 작성자</label><select class="input" id="author" name="author_id">${members.map((m) => html`<option value="${m.id}" ${m.id === staff.id ? 'selected' : ''}>${m.role} · ${m.name}</option>`)}</select></div></div>
      <div><button class="btn" type="submit">기록 저장</button> <a class="btn ghost" href="#/dashboard">취소</a></div>
    </form>`.toString();
  const f = root.querySelector('#f'), quick = root.querySelector('#quick');
  const paintQuick = () => {
    const opts = QUICK[type];
    quick.innerHTML = opts ? html`<span class="lbl" id="ql">관찰 값</span><div class="seg" role="radiogroup" aria-labelledby="ql">${opts.map((o, i) => html`<input type="radio" name="structured_value" id="q${i}" value="${o}"><label for="q${i}">${o}</label>`)}</div>
      <p class="hint">직원이 관찰한 상태를 남기는 선택지입니다. 선택한 값만으로 건강 이상을 판단하지 않습니다.</p>`.toString() : '';
  };
  paintQuick();
  const blockSel = f.querySelector('#block');
  const paintBlocks = () => {
    const auto = blockAt(f.observed_at.value);
    const keep = blockSel.value;
    blockSel.innerHTML = `<option value="">자동 — ${esc(auto ? auto.name : '해당 구간 없음(영업시간 외)')}</option>` +
      blocks.map((b) => `<option value="${b.id}">${esc(b.name)} (${b.start_time}–${b.end_time})</option>`).join('');
    blockSel.value = keep && blocks.some((b) => String(b.id) === keep) ? keep : '';
  };
  paintBlocks();
  if (preset) blockSel.value = String(preset.id);
  f.observed_at.addEventListener('input', paintBlocks);
  const photos = bindPhotoAttach(f, { getDogId: () => +f.dog_id.value || null });
  f.dog_id.addEventListener('change', () => photos.onDogChange());
  f.querySelectorAll('[name=record_type]').forEach((r) => r.addEventListener('change', () => { type = r.value; paintQuick(); }));
  f.addEventListener('submit', (e) => {
    e.preventDefault(); fieldErrors(f, { errors: [] });
    const v = Object.fromEntries(new FormData(f));
    let bad = false;
    if (!v.dog_id) { showFieldError(f, 'dog_id', '반려견을 선택해 주세요.'); bad = true; }
    const content = (v.content || '').trim();
    if (!content && !v.structured_value) { showFieldError(f, QUICK[type] ? 'structured_value' : 'content', QUICK[type] ? '관찰 값을 선택하거나 상세 메모를 입력해 주세요.' : '기록 내용을 입력해 주세요.'); bad = true; }
    else if (v.structured_value === '직접 입력' && !content) { showFieldError(f, 'content', "'직접 입력'을 선택한 경우 상세 메모를 입력해 주세요."); bad = true; }
    if (bad) return;
    busy(f.querySelector('[type=submit]'), async () => {
      try {
        const rec = await api.createRecord({ dog_id: +v.dog_id, record_type: v.record_type, structured_value: v.structured_value || null, content, observed_at: v.observed_at || null, author_id: +v.author_id, block_id: v.block_id ? +v.block_id : null });
        toast('돌봄 기록을 저장했습니다.');
        const dog = dogs.find((d) => d.id === rec.dog_id);
        root.querySelector('#done').innerHTML = html`<div class="card" style="max-width:680px;margin-bottom:18px" role="status"><h2>${dog.name}의 기록을 저장했습니다</h2>
          <p class="muted" style="margin:6px 0 12px">${fmtTime(rec.observed_at)} · ${rec.block_name ? `${rec.block_name} · ` : ''}${rec.record_type}${rec.structured_value ? ` · ${rec.structured_value}` : ''} — ${rec.content}</p>
          <p class="small muted" style="margin-bottom:12px">저장만으로 후속 업무가 생기지는 않습니다. 필요하면 아래에서 후속 업무를 제안받을 수 있습니다.</p>
          <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn" href="#/ai/${rec.id}">${icon('spark')} 후속 업무 제안 받기</a><a class="btn secondary" href="#/dogs/${dog.id}">${dog.name} 프로필 보기</a><button class="btn ghost" id="again">기록 더 작성</button></div></div>`.toString();
        root.querySelector('#again').addEventListener('click', () => { root.querySelector('#done').innerHTML = ''; f.content.value = ''; f.querySelectorAll('[name=structured_value]').forEach((x) => { x.checked = false; }); f.dog_id.focus(); });
        root.querySelector('#done').scrollIntoView({ block: 'start' });
        f.content.value = '';
        const pending = photos.items.slice(), tagIds = photos.tagIds();
        if (pending.length) {
          const status = document.createElement('p');
          status.className = 'small'; status.setAttribute('role', 'status'); status.style.marginTop = '10px';
          root.querySelector('#done .card').appendChild(status);
          const run = async (list) => {
            status.textContent = `사진 올리는 중… (0/${list.length})`;
            const failed = await uploadAll(rec.id, list, tagIds, (n, total) => { status.textContent = `사진 올리는 중… (${n}/${total})`; });
            if (!failed.length) { status.textContent = `사진 ${list.length}장을 첨부했습니다.`; return; }
            status.innerHTML = `<b>사진 ${failed.length}장을 올리지 못했습니다.</b> <span class="muted">${esc(failed[0].message)}</span> <button type="button" class="btn sm secondary" id="retry-up">다시 올리기</button>`;
            status.querySelector('#retry-up').addEventListener('click', (ev) => { ev.target.disabled = true; run(failed.map((x) => x.item)); });
          };
          photos.clear();
          await run(pending);
        }
      } catch (err) {
        if (err instanceof ApiError && err.errors.length) fieldErrors(f, err);
        else if (err.status === 422) showFieldError(f, 'content', err.message);
        else toast(err.message, 'error');
      }
    });
  });
}

/** AI 업무 정리: #/ai (분석 대기 기록) 또는 #/ai/:recordId (제안 검토) */
export async function aiView(ctx) {
  const { root, params } = ctx;
  if (!params[0]) {
    const [recs, health] = await Promise.all([api.records({ unlinked: 'true' }), api.health()]);
    root.innerHTML = html`<div class="page-head"><div><h1>AI 업무 정리</h1><p>오늘의 기록 중 아직 후속 업무와 연결되지 않은 기록에서 확인할 일을 제안받습니다. 제안은 직원이 등록하기 전까지 업무가 아닙니다.</p></div></div>
      <div class="card" style="margin-bottom:14px"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h3 style="margin:0">AI 연결 상태</h3><button class="btn sm secondary" id="ai-test">연결 테스트</button></div>
        <p id="ai-test-out" class="small" role="status" style="margin-top:8px">${health.ai_configured ? '키와 모델이 설정되어 있습니다. 실제로 연결되는지는 "연결 테스트"로 확인할 수 있어요.' : '키 또는 모델이 설정되지 않아 지금은 데모 분석(규칙 기반)으로 동작합니다.'}</p></div>
      ${recs.length ? html`<div class="task-list">${recs.map((r) => html`<article class="task-row s-todo" style="grid-template-columns:120px 1fr auto"><a class="task-dog" href="#/dogs/${r.dog_id}">${r.dog_name}</a>
        <div><p class="task-title" style="font-weight:500">${r.content}</p><p class="task-meta">${fmtTime(r.observed_at)} · ${r.record_type}${r.structured_value ? ` · ${r.structured_value}` : ''} · ${r.author_name}</p></div>
        <a class="btn sm" href="#/ai/${r.id}">${icon('spark')} 분석하기</a></article>`)}</div>`
      : empty('정리할 기록이 없습니다', '후속 업무와 연결되지 않은 오늘의 기록이 없습니다.', html`<br><a class="btn" href="#/record/new">돌봄 기록 작성</a>`)}`.toString();
    root.querySelector('#ai-test').addEventListener('click', (e) => busy(e.currentTarget, async () => {
      const out = root.querySelector('#ai-test-out');
      out.textContent = '연결을 확인하는 중…';
      try {
        const r = await api.testAi();
        out.innerHTML = `<b>${r.ok ? '✔ 연결됨' : '✘ 연결 안 됨'}</b> · ${esc(r.message)}${r.model ? ` <span class="muted">(모델: ${esc(r.model)})</span>` : ''}`;
      } catch (err) { out.textContent = err.message; }
    }));
    return;
  }
  const rec = await api.record(params[0]);
  root.innerHTML = html`<a class="crumb" href="#/ai">${icon('back')} AI 업무 정리</a>
    <div class="page-head"><div><h1>${rec.dog_name}의 기록 분석</h1></div></div>
    <div class="card"><p class="small muted">원본 기록 #${rec.id} · ${fmtWhen(rec.observed_at)} · ${rec.record_type}${rec.structured_value ? ` · ${rec.structured_value}` : ''} · ${rec.author_name}</p><div class="quote" style="margin-top:6px"><p>${rec.content}</p></div></div>
    <div id="out" class="section">${skeleton(2)}</div>`.toString();
  const out = root.querySelector('#out');
  let res, members;
  try { [res, members] = await Promise.all([api.suggest(rec.id), api.staff()]); } catch (e) {
    out.innerHTML = html`<div class="errbox" role="alert"><h3>분석하지 못했습니다</h3><p class="muted" style="margin:6px 0 12px">${e.message}</p><button class="btn secondary" id="retry">다시 시도</button> <button class="btn ghost" id="manual0">업무 직접 등록</button></div>`.toString();
    out.querySelector('#retry').addEventListener('click', () => ctx.rerender());
    out.querySelector('#manual0').addEventListener('click', () => openTaskModal(ctx, { dog_id: rec.dog_id, source_record_id: rec.id }));
    return;
  }
  const st = res.suggestions.map(() => ({ s: 'open', taskId: null }));
  const nameOf = (id) => members.find((m) => m.id === id);
  const paint = () => {
    out.innerHTML = html`
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px"><span class="mode ${res.mode === 'gemini' ? 'live' : ''}">${icon('spark')} ${res.mode_label}</span>
        <span class="small muted">AI는 진단하지 않으며, 제안은 직원이 승인하기 전까지 확정된 업무가 아닙니다.</span></div>
      ${res.fallback_note ? html`<p class="callout clay" style="margin-bottom:12px">${res.fallback_note}</p>` : ''}
      <div class="ai-cols card"><div class="ai-col"><h3>기록에 있는 사실</h3><ul>${res.facts.map((x) => html`<li>${x}</li>`)}</ul></div>
        <div class="ai-col"><h3>제안한 행동</h3>${res.suggestions.length ? html`<ul>${res.suggestions.map((x) => html`<li>${x.title}</li>`)}</ul>` : html`<p class="muted small">제안 없음</p>`}</div></div>
      ${res.notice ? html`<p class="callout" style="margin-top:12px">${res.notice} <button class="btn sm secondary" id="manual">업무 직접 등록</button></p>` : ''}
      <div class="stack" style="margin-top:16px">${res.suggestions.map((s, i) => card(s, i))}</div>`.toString();
    out.querySelector('#manual')?.addEventListener('click', () => openTaskModal(ctx, { dog_id: rec.dog_id, source_record_id: rec.id }));
    out.querySelectorAll('[data-i]').forEach((b) => b.addEventListener('click', () => onAct(+b.dataset.i, b.dataset.do, b)));
  };
  const card = (s, i) => {
    const a = nameOf(s.assignee_id), x = st[i];
    if (x.s === 'registered') return html`<div class="sugg done"><span class="badge b-ack">${icon('check')} 업무로 등록됨</span> <b>${s.title}</b> <a class="btn sm secondary" style="margin-left:8px" href="#/tasks/${x.taskId}">업무 보기</a></div>`;
    if (x.s === 'ignored') return html`<div class="sugg done"><span class="badge b-done">무시함</span> <s>${s.title}</s> <span class="small muted">업무가 생성되지 않았습니다.</span> <button class="btn sm ghost" data-i="${i}" data-do="undo">되돌리기</button></div>`;
    if (x.s === 'edit') return html`<div class="sugg"><form data-edit="${i}" class="stack" novalidate><div class="field"><label for="e-t${i}">업무 제목 *</label><input class="input" id="e-t${i}" name="title" value="${s.title}" maxlength="80"></div>
      <div class="field"><label for="e-d${i}">업무 설명</label><textarea class="input" id="e-d${i}" name="description" maxlength="500">${s.description}</textarea></div>
      <div class="row2"><div class="field"><label for="e-a${i}">담당자</label><select class="input" id="e-a${i}" name="assignee_id"><option value="">미지정</option>${members.map((m) => html`<option value="${m.id}" ${m.id === s.assignee_id ? 'selected' : ''}>${m.role} · ${m.name}</option>`)}</select></div>
        <div class="field"><label for="e-p${i}">우선순위</label><select class="input" id="e-p${i}" name="priority">${[['normal', '보통'], ['high', '높음'], ['low', '낮음']].map(([v, l]) => html`<option value="${v}" ${s.priority === v ? 'selected' : ''}>${l}</option>`)}</select></div></div>
      <div class="actions"><button class="btn" type="submit">수정 내용으로 등록</button><button type="button" class="btn secondary" data-i="${i}" data-do="cancel">취소</button></div></form></div>`;
    return html`<div class="sugg"><div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><h3>${s.title}</h3><span class="badge b-pending">${icon('clock')} 확인 필요: 예</span></div>
      <p style="margin-top:6px">${s.description}</p>
      <p class="small" style="margin-top:8px"><b>담당자</b> ${a ? html`${a.name} (${a.role})` : html`<span class="muted">미지정</span>`} ${s.assignee_note ? html`<span class="muted">— ${s.assignee_note}</span>` : ''}</p>
      <div class="quote small" style="margin-top:8px"><span class="muted">근거 (원본 기록 #${s.source_record_id})</span><br>${s.evidence.map((e) => html`“${e}” `)}</div>
      <div class="actions"><button class="btn" data-i="${i}" data-do="register">${icon('check')} 업무로 등록</button><button class="btn secondary" data-i="${i}" data-do="edit">수정하기</button><button class="btn ghost" data-i="${i}" data-do="ignore">제안 무시</button></div></div>`;
  };
  const register = (s, over = {}) => api.createTask({ dog_id: rec.dog_id, source_record_id: rec.id, title: s.title, description: s.description, assignee_id: s.assignee_id, priority: s.priority || 'normal', ai_suggested: true, ...over });
  const onAct = (i, what, btn) => {
    const s = res.suggestions[i];
    if (what === 'edit') { st[i].s = 'edit'; paint(); return; }
    if (what === 'cancel' || what === 'undo') { st[i].s = 'open'; paint(); return; }
    if (what === 'ignore') { st[i].s = 'ignored'; paint(); toast('제안을 무시했습니다. 업무는 생성되지 않았습니다.'); return; }
    busy(btn, () => guarded(async () => { const t = await register(s); st[i] = { s: 'registered', taskId: t.id }; toast('업무로 등록했습니다. 담당자의 확인을 기다립니다.'); paint(); }));
  };
  paint();
  out.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-edit]'); if (!form) return;
    e.preventDefault(); fieldErrors(form, { errors: [] });
    const i = +form.dataset.edit, v = Object.fromEntries(new FormData(form));
    if (!v.title.trim()) { showFieldError(form, 'title', '업무 제목을 입력해 주세요.'); return; }
    busy(form.querySelector('[type=submit]'), () => guarded(async () => {
      const t = await register(res.suggestions[i], { title: v.title.trim(), description: v.description.trim(), assignee_id: v.assignee_id ? +v.assignee_id : null, priority: v.priority });
      st[i] = { s: 'registered', taskId: t.id }; toast('수정한 내용으로 업무를 등록했습니다.'); paint();
    }));
  });
}
