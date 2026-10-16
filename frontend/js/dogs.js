import { api, ApiError } from './api.js';
import { html, icon, fmtTime, fmtWhen, josa, esc } from './util.js';
import { avatar, taskRow, empty, ackBadge, actionBadge, busy, guarded, toast, openModal, fieldErrors, showFieldError } from './ui.js';
import { bindTaskActions } from './tasks.js';
import { photoField, bindPhotoField } from './cropper.js';
import { thumbs, openMediaViewer, processImage, uploadAll, MAX_PER_RECORD } from './media.js';

const CTX_LABELS = [['meal', '식사 관련 주의사항'], ['sensitivity', '알레르기·민감성 정보'], ['behavior', '행동 관련 주의사항'], ['owner_request', '보호자 요청사항'], ['other', '기타 돌봄 참고사항']];
const STATUS = [['all', '재원 중'], ['needs_check', '확인 필요'], ['has_task', '진행할 업무 있음'], ['clear', '열린 업무 없음'], ['discharged', '퇴원']];

const dogCard = (d) => html`<a class="dog-card ${d.needs_check_count ? 'needs' : ''}" href="#/dogs/${d.id}">
  <div class="top">${avatar(d)}<div><div class="name">${d.name}</div><div class="small muted">${d.breed} · ${d.age_text}</div></div>
    ${d.discharged ? html`<span class="badge b-done" style="margin-left:auto">${d.purged_at ? '자료 삭제됨' : `퇴원 · 삭제 D-${Math.max(d.purge_days_left ?? 0, 0)}`}</span>` : d.needs_check_count ? html`<span class="badge b-pending" style="margin-left:auto">${icon('clock')} 확인 ${d.needs_check_count}</span>` : ''}</div>
  <div class="row"><b>오늘</b><span>${d.today_status ? html`${d.today_status.record_type} · ${fmtTime(d.today_status.observed_at)} ${d.today_status.structured_value && d.today_status.structured_value !== '직접 입력' ? d.today_status.structured_value : d.today_status.content.slice(0, 36)}` : '오늘 기록 없음'}</span></div>
  <div class="row"><b>업무</b><span>${d.open_task_count ? `진행할 업무 ${d.open_task_count}건` : '열린 업무 없음'}</span></div>
  <div class="row"><b>주의</b><span>${d.caution ? html`${icon('shield')} ${d.caution}` : '등록된 주의사항 없음'}</span></div></a>`;

export async function dogsView(ctx) {
  const { root } = ctx;
  let q = '', status = 'all';
  root.innerHTML = html`<div class="page-head"><div><h1>반려견</h1><p>오늘 돌봄 중인 반려견을 찾고 프로필로 이동합니다.</p></div><button class="btn" id="add-dog">${icon('plus')} 반려견 등록</button></div>
    <div class="toolbar"><label class="sr" for="q">이름 검색</label><input id="q" class="input search" type="search" placeholder="이름으로 검색" autocomplete="off">
    <div class="chips" role="group" aria-label="상태 필터">${STATUS.map(([k, l]) => html`<button class="chip" data-s="${k}" aria-pressed="${k === 'all'}">${l}</button>`)}</div></div>
    <div id="purge-panel"></div><div id="grid" class="dog-grid" aria-live="polite"></div>`.toString();
  const grid = root.querySelector('#grid');
  root.querySelector('#add-dog').addEventListener('click', () => registerDogModal(ctx));
  let seq = 0;
  const load = async () => {
    const my = ++seq;
    try {
      const dogs = await api.dogs({ q, status });
      if (my !== seq) return;
      grid.innerHTML = (dogs.length ? dogs.map(dogCard) : [empty(status === 'discharged' ? '퇴원 처리된 반려견이 없습니다' : '조건에 맞는 반려견이 없습니다', status === 'discharged' ? '' : '검색어나 필터를 바꿔 보세요.')]).join('');
      await paintPurgePanel(ctx, root.querySelector('#purge-panel'), status === 'discharged', load);
    } catch (e) { grid.innerHTML = `<div class="errbox" role="alert">${e.message}</div>`; }
  };
  let t;
  root.querySelector('#q').addEventListener('input', (e) => { q = e.target.value; clearTimeout(t); t = setTimeout(load, 180); });
  root.querySelectorAll('[data-s]').forEach((b) => b.addEventListener('click', () => { status = b.dataset.s; root.querySelectorAll('[data-s]').forEach((x) => x.setAttribute('aria-pressed', x === b)); load(); }));
  await load();
}

export async function dogDetailView(ctx) {
  const { root, staff, params } = ctx;
  let d;
  try { d = await api.dog(params[0]); } catch (e) {
    if (e instanceof ApiError && e.status === 404) { root.innerHTML = empty('반려견을 찾을 수 없습니다', '삭제되었거나 다른 유치원의 반려견일 수 있습니다.', html`<br><a class="btn" href="#/dogs">반려견 목록으로</a>`).toString(); return; }
    throw e;
  }
  const open = d.tasks.filter((t) => t.action_status !== 'completed');
  const g = await api.guardians(d.id);
  const tagged = await api.dogMedia(d.id, 'today');
  root.innerHTML = html`
    <a class="crumb" href="#/dogs">${icon('back')} 반려견 목록</a>
    <div class="card"><div class="dog-head">${avatar(d, 'lg')}
      <div class="grow"><h1>${d.name}</h1><p class="muted">${d.breed} · ${d.age_text} · 보호자 ${d.owner_name} <span class="tiny">(샘플)</span></p>
        <p style="margin-top:6px">${open.length ? html`<span class="badge b-todo">진행할 업무 ${open.length}건</span>` : html`<span class="badge b-done">열린 업무 없음</span>`} ${d.consent_at ? '' : html`<span class="badge b-pending">${icon('lock')} 동의 미확인 · 공개 불가</span>`}</p></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">${d.attending ? html`<a class="btn" href="#/record/new?dog=${d.id}">${icon('pen')} 돌봄 기록 작성</a>` : html`<button class="btn" disabled title="퇴원 처리된 반려견에는 새 기록을 남길 수 없습니다">${icon('pen')} 돌봄 기록 작성</button>`}
        <button class="btn secondary" id="goto-tasks">후속 업무 확인 (${open.length})</button><button class="btn secondary" id="edit">프로필 수정</button>
        ${staff.role === '관리자' ? (d.attending ? html`<button class="btn ghost" id="discharge">퇴원 처리</button>` : (d.discharged && !d.purged_at ? html`<button class="btn ghost" id="readmit">재입원 처리</button>` : '')) : ''}</div></div></div>
    ${d.purged_at ? html`<p class="callout clay" style="margin-top:12px" role="status"><b>자료 삭제 완료</b> · ${fmtWhen(d.purged_at)}에 사진·영상 파일과 보호자 연결을 삭제했습니다. 글 기록과 업무 이력은 남아 있습니다.</p>`
      : d.discharged ? html`<p class="callout clay" style="margin-top:12px" role="status"><b>퇴원 처리됨</b> (${fmtWhen(d.discharged_at)}) · 사진·영상 파일과 보호자 연결은 <b>${d.purge_after.slice(0, 10)}</b>(D-${d.purge_days_left})에 삭제될 예정입니다. 그때까지 보호자는 이미 공개된 사진을 볼 수 있어요.</p>` : ''}

    <section class="section"><div class="head"><h2>지속적으로 확인해야 할 돌봄 정보</h2></div>
      <p class="callout" style="margin-bottom:10px">장기 참고사항입니다. 오늘의 기록과 구분되며, 직원이 직접 입력한 내용만 담기고 AI가 자동으로 바꾸지 않습니다. (샘플 데이터)</p>
      <div class="panel" style="padding:4px 18px"><div class="kv">${CTX_LABELS.flatMap(([k, l]) => [html`<div class="k">${l}</div>`, html`<div>${d.care_context[k] || html`<span class="muted">입력된 내용 없음</span>`}</div>`])}</div></div></section>

    <section class="section"><div class="head"><h2>오늘의 돌봄 기록</h2><span class="small muted">${d.records_today.length}건</span></div>
      <div class="panel" style="padding:4px 18px">${d.records_today.length ? html`<ul class="timeline">${d.records_today.map((r) => html`<li><div class="t">${fmtTime(r.observed_at)}</div><div class="body">
        <div><span class="badge b-done">${r.record_type}</span>${r.block_name ? html` <span class="badge b-ack">${r.block_name}</span>` : ''} ${r.structured_value && r.structured_value !== '직접 입력' ? html`<b>${r.structured_value}</b>` : ''} <span class="small muted">· ${r.author_name} (${r.author_role})</span></div>
        <p style="margin-top:4px">${r.content}</p>
        ${thumbs(r.media, r.id)}
        <div class="tags">${r.tasks.map((t) => html`<a class="link-task" href="#/tasks/${t.id}">${icon('list')} ${t.title} · ${t.acknowledgment_status === 'pending' ? '확인 대기' : '확인 완료'} / ${{ todo: '조치 필요', in_progress: '진행 중', completed: '조치 완료' }[t.action_status]}</a>`)}
          ${r.tasks.length ? '' : html`<a class="btn sm secondary" href="#/ai/${r.id}">${icon('spark')} 후속 업무 제안</a>`}
          ${r.media.length < MAX_PER_RECORD && d.attending ? html`<button class="btn sm ghost" data-add-photo="${r.id}">${icon('plus')} 사진 추가</button>` : ''}${r.parent_status === 'approved' ? html`<span class="badge b-ack">${icon('check')} 보호자 공개됨${r.media.some((m) => m.shared_dog_ids.length) ? ` · 사진 ${r.media.filter((m) => m.shared_dog_ids.length).length}장` : ''}</span><button class="btn sm ghost" data-approve="${r.id}">공개 내용 수정</button><button class="btn sm ghost" data-revoke="${r.id}">공개 취소</button>` : html`<span class="badge b-private">${icon('lock')} 내부 기록</span><button class="btn sm ghost" data-approve="${r.id}">보호자 공개 승인…</button>`}</div></div></li>`)}</ul>`
        : html`<div style="padding:14px 0">${empty('오늘 작성된 기록이 없습니다', '', html`<br><a class="btn" href="#/record/new?dog=${d.id}">돌봄 기록 작성</a>`)}</div>`}</div></section>

    <section class="section" id="dog-photos" aria-labelledby="photos-title"><div class="head"><h2 id="photos-title">오늘 찍힌 사진</h2><span class="small muted">${tagged.length}장 · 직원만 볼 수 있어요</span></div>
      ${tagged.length ? html`<div class="panel" style="padding:14px 18px"><div class="thumbs big" data-tagged="1">${tagged.map((m, i) => html`<button type="button" class="thumb" data-media-open="${i}" aria-label="사진 ${i + 1} 크게 보기 (${m.dog_names.join(', ')})"><img src="/api/media/${m.id}/file?size=thumb" alt="" loading="lazy"></button>`)}</div><p class="hint small muted" style="margin-top:8px">이 아이가 함께 찍힌 사진이 모입니다. 다른 아이의 기록에 첨부된 단체 사진도 포함돼요.</p></div>`
        : empty('오늘 찍힌 사진이 없습니다', '돌봄 기록을 작성할 때 사진을 첨부하거나, 기록 옆의 "사진 추가"를 눌러 보세요.')}</section>

    <section class="section" id="dog-tasks"><div class="head"><h2>처리해야 할 업무</h2></div>
      ${d.tasks.length ? html`<div class="task-list">${d.tasks.map((t) => taskRow(t, staff, { showDog: false }))}</div>` : empty('이 반려견의 업무가 없습니다', '기록을 바탕으로 후속 업무를 만들 수 있습니다.')}</section>

    <section class="section" id="guardians" aria-labelledby="gt"><div class="head"><h2 id="gt">보호자 계정</h2><button class="btn secondary" id="invite">${icon('plus')} 초대 코드 만들기</button></div>
      ${d.consent_at ? html`<p class="callout" style="margin-bottom:10px">${icon('check')} 보호자 동의 확인됨 (${fmtWhen(d.consent_at)}) · 사진 공유와 퇴원 후 3개월 뒤 삭제에 대한 동의를 받은 것으로 기록되어 있습니다.</p>`
        : html`<div class="callout clay" style="margin-bottom:10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span><b>보호자 동의가 확인되지 않았습니다.</b> 동의를 받기 전에는 이 아이의 글·사진을 보호자에게 공개할 수 없습니다.</span><button class="btn sm" id="consent">동의 확인 기록</button></div>`}
      <div class="panel" style="padding:4px 18px">
        ${g.guardians.length ? html`<ul class="timeline">${g.guardians.map((p) => html`<li style="grid-template-columns:1fr auto"><div><b>${p.name}</b> <span class="small muted">${p.email}</span></div><span class="badge b-ack">${icon('check')} 가입됨</span></li>`)}</ul>`
          : html`<p class="muted small" style="padding:14px 0">아직 가입한 보호자가 없습니다. 초대 코드를 만들어 보호자에게 전달해 주세요.</p>`}
        ${g.invites.length ? html`<hr class="sep" style="margin:0"><p class="small muted" style="padding:10px 0 2px">최근 초대 코드 (코드 원문은 만든 직후 한 번만 볼 수 있습니다)</p>
          <ul class="timeline">${g.invites.map((i) => html`<li style="grid-template-columns:1fr auto;align-items:center"><div class="small">${fmtWhen(i.created_at)} 생성 · ${i.status === 'used' ? `${fmtWhen(i.used_at)} 사용됨` : `${fmtWhen(i.expires_at)}까지`}</div>
            <div>${i.status === 'active' ? html`<span class="badge b-pending">${icon('clock')} 사용 대기</span> <button class="btn sm ghost" data-revoke-invite="${i.id}">취소</button>` : i.status === 'used' ? html`<span class="badge b-done">${icon('check')} 사용됨</span>` : html`<span class="badge b-done">만료됨</span>`}</div></li>`)}</ul>` : ''}
      </div></section>`.toString();

  root.querySelector('#goto-tasks').addEventListener('click', () => root.querySelector('#dog-tasks').scrollIntoView({ behavior: 'smooth' }));
  root.querySelector('#edit').addEventListener('click', () => profileModal(ctx, d));
  root.querySelector('#discharge')?.addEventListener('click', () => dischargeModal(ctx, d, open.length));
  root.querySelector('#readmit')?.addEventListener('click', (e) => busy(e.currentTarget, () => guarded(async () => {
    if (!confirm(`${josa(d.name, '을', '를')} 재입원 처리할까요? 삭제 예정이 취소되고 다시 기록·사진을 남길 수 있습니다.`)) return;
    await api.readmit(d.id); toast(`${josa(d.name, '을', '를')} 재입원 처리했습니다.`); ctx.rerender();
  })));
  root.querySelector('#consent')?.addEventListener('click', (e) => busy(e.currentTarget, () => guarded(async () => {
    if (!confirm('보호자에게 사진 공유와 퇴원 후 3개월 뒤 삭제에 대한 동의를 받았나요? 확인하면 동의 확인 시각이 기록됩니다.')) return;
    await api.recordConsent(d.id); toast('보호자 동의 확인을 기록했습니다.'); ctx.rerender();
  })));
  root.querySelector('#invite').addEventListener('click', (e) => busy(e.currentTarget, () => guarded(async () => {
    const inv = await api.createInvite(d.id);
    inviteModal(ctx, inv);
  })));
  root.querySelectorAll('[data-revoke-invite]').forEach((b) => b.addEventListener('click', () => busy(b, () => guarded(async () => {
    await api.revokeInvite(+b.dataset.revokeInvite); toast('초대 코드를 취소했습니다.'); ctx.rerender();
  }))));
  root.querySelectorAll('.thumbs[data-rec] [data-media-open]').forEach((b) => b.addEventListener('click', () => {
    const rec = d.records_today.find((r) => r.id === +b.closest('.thumbs').dataset.rec);
    openMediaViewer(rec.media, +b.dataset.mediaOpen, ctx);
  }));
  root.querySelectorAll('[data-tagged] [data-media-open]').forEach((b) => b.addEventListener('click', () => openMediaViewer(tagged, +b.dataset.mediaOpen, ctx)));
  const picker = Object.assign(document.createElement('input'), { type: 'file', accept: 'image/jpeg,image/png,image/webp', multiple: true });
  let addTo = null;
  root.querySelectorAll('[data-add-photo]').forEach((b) => b.addEventListener('click', () => { addTo = d.records_today.find((r) => r.id === +b.dataset.addPhoto); picker.click(); }));
  picker.addEventListener('change', () => guarded(async () => {
    const files = [...picker.files]; picker.value = '';
    const rec = addTo; if (!rec || !files.length) return;
    const room = MAX_PER_RECORD - rec.media.length;
    if (files.length > room) toast(`한 기록에는 최대 ${MAX_PER_RECORD}장까지 첨부할 수 있어요. ${room}장만 올립니다.`, 'error');
    const items = [];
    for (const f of files.slice(0, room)) { try { items.push({ blob: await processImage(f) }); } catch (e) { toast(e.message, 'error'); } }
    if (!items.length) return;
    toast(`사진 ${items.length}장을 올리는 중…`);
    const failed = await uploadAll(rec.id, items, [d.id]);
    toast(failed.length ? `${failed.length}장을 올리지 못했습니다. ${failed[0].message}` : `사진 ${items.length}장을 첨부했습니다.`, failed.length ? 'error' : 'ok');
    ctx.rerender();
  }));
  bindTaskActions(root, ctx);
  root.querySelectorAll('[data-approve]').forEach((b) => b.addEventListener('click', () => approveModal(ctx, d.records_today.find((r) => r.id === +b.dataset.approve), d)));
  root.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', () => busy(b, () => guarded(async () => { await api.parentApproval(+b.dataset.revoke, { action: 'revoke' }); toast('보호자 공개를 취소했습니다.'); ctx.rerender(); }))));
}

async function approveModal(ctx, r, d) {
  const dogs = await api.dogs();
  const consent = Object.fromEntries(dogs.map((x) => [x.id, !!x.consent_at]));
  const approved = r.parent_status === 'approved';
  // 기본 선택: 이미 승인했다면 기존 공개 대상, 처음이면 '이 기록의 아이'가 찍힌 사진만 그 아이 보호자에게
  const checked = (m, id) => (approved ? m.shared_dog_ids.includes(id) : id === r.dog_id);
  openModal({
    title: approved ? '공개 내용 수정' : '보호자 공개 승인', wide: r.media.length > 0,
    body: html`<form class="stack" novalidate><p class="callout">직원 내부 기록과 업무 인계 내용은 공개되지 않습니다. 아래 문구와 <b>선택한 사진</b>만, 선택한 아이의 보호자에게 보입니다. (실제 알림 전송은 없고, 보호자가 앱을 열면 보입니다)</p>
      <div class="quote"><p class="small muted">내부 기록 원문</p><p>${r.content}</p></div>
      <div class="field"><label for="pt">보호자에게 보여줄 문구 ${r.media.length ? html`<span class="muted small">(사진만 공개하려면 비워도 됩니다)</span>` : '*'}</label>
        <textarea class="input" id="pt" name="parent_text" maxlength="500">${approved ? r.parent_text : r.content}</textarea>
        <p class="hint">내부 인계 표현(예: 담당자 지정)은 직접 지우거나 고쳐 주세요. 이 문구는 <b>${d.name}</b>의 보호자에게만 보입니다.</p></div>
      ${r.media.length ? html`<div class="field" data-field="media"><span class="lbl">공개할 사진</span>
        <p class="hint">사진마다 어느 아이의 보호자에게 보일지 고르세요. 아무도 고르지 않은 사진은 공개되지 않습니다. 다른 집 아이가 찍힌 사진은 그 아이의 보호자에게 보낼 때만 체크하세요.</p>
        <div class="share-list">${r.media.map((m, i) => html`<div class="share-row"><img src="/api/media/${m.id}/file?size=thumb" alt="사진 ${i + 1}">
          <div><p class="small muted">사진 ${i + 1} · 찍힌 아이: ${m.dog_names.join(', ')}</p>
            <div class="checks">${m.dog_ids.map((id, k) => html`<label class="check"><input type="checkbox" data-m="${m.id}" value="${id}" ${checked(m, id) && consent[id] ? 'checked' : ''} ${consent[id] ? '' : 'disabled'}> ${m.dog_names[k]}의 보호자${consent[id] ? '' : html` <span class="muted">(동의 미확인)</span>`}</label>`)}</div></div></div>`)}</div></div>` : ''}
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">${approved ? '공개 내용 저장' : '공개 승인'}</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        const media = r.media.map((m) => ({ media_id: m.id, dog_ids: [...f.querySelectorAll(`[data-m="${m.id}"]:checked`)].map((c) => +c.value) })).filter((m) => m.dog_ids.length);
        const text = f.parent_text.value.trim();
        if (!text && !media.length) { showFieldError(f, 'parent_text', '보호자에게 보여줄 문구를 입력하거나 공개할 사진을 선택해 주세요.'); return; }
        busy(f.querySelector('[type=submit]'), async () => {
          try {
            await api.parentApproval(r.id, { action: 'approve', parent_text: text, media });
            close(); toast(media.length ? `보호자 공개를 저장했습니다. (사진 ${media.length}장)` : '보호자 공개를 저장했습니다.'); ctx.rerender();
          } catch (err) { if (err instanceof ApiError && err.errors.length) fieldErrors(f, err); else toast(err.message, 'error'); }
        });
      });
    },
  });
}

function profileModal(ctx, d) {
  openModal({
    title: `${d.name} 프로필 수정`,
    body: html`<form class="stack" novalidate>
      ${photoField({ photo: d.photo, name: d.name })}
      <div class="row2"><div class="field"><label for="p-breed">견종 *</label><input class="input" id="p-breed" name="breed" value="${d.breed}" maxlength="40"></div>
        <div class="field"><label for="p-birth">생년월일 *</label><input class="input" id="p-birth" name="birth_date" type="date" value="${d.birth_date}"></div></div>
      <div class="field"><label for="p-owner">보호자 이름 *</label><input class="input" id="p-owner" name="owner_name" value="${d.owner_name}" maxlength="40"></div>
      ${CTX_LABELS.map(([k, l]) => html`<div class="field"><label for="c-${k}">${l}</label><textarea class="input" style="min-height:60px" id="c-${k}" name="ctx_${k}" maxlength="300">${d.care_context[k] || ''}</textarea></div>`)}
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">저장</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      const photo = bindPhotoField(f);
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        const v = Object.fromEntries(new FormData(f));
        let bad = false;
        for (const [k, m] of [['breed', '견종을 입력해 주세요.'], ['birth_date', '생년월일을 입력해 주세요.'], ['owner_name', '보호자 이름을 입력해 주세요.']]) if (!v[k].trim()) { showFieldError(f, k, m); bad = true; }
        if (bad) return;
        const care_context = Object.fromEntries(CTX_LABELS.map(([k]) => [k, v[`ctx_${k}`]]));
        busy(f.querySelector('[type=submit]'), async () => {
          try {
            await api.patchDog(d.id, { breed: v.breed.trim(), birth_date: v.birth_date, owner_name: v.owner_name.trim(), care_context });
            if (photo.blob) await api.uploadPhoto(d.id, photo.blob); else if (photo.remove) await api.deletePhoto(d.id);
            close(); toast('프로필을 저장했습니다.'); ctx.rerender();
          } catch (err) { if (err instanceof ApiError && err.errors.length) fieldErrors(f, err); else toast(err.message, 'error'); }
        });
      });
    },
  });
}

/** 새 반려견 등록 (사진은 선택) */
function registerDogModal(ctx) {
  openModal({
    title: '새 반려견 등록',
    body: html`<form class="stack" novalidate>
      ${photoField({ photo: null, name: '?' })}
      <div class="row2"><div class="field"><label for="r-name">이름 *</label><input class="input" id="r-name" name="name" maxlength="20" autocomplete="off"></div>
        <div class="field"><label for="r-breed">견종 *</label><input class="input" id="r-breed" name="breed" maxlength="40" placeholder="예: 푸들, 믹스견"></div></div>
      <div class="row2"><div class="field"><label for="r-birth">생년월일 *</label><input class="input" id="r-birth" name="birth_date" type="date"><p class="hint">정확한 날짜를 모르면 대략적인 날짜를 입력하세요.</p></div>
        <div class="field"><label for="r-owner">보호자 이름 *</label><input class="input" id="r-owner" name="owner_name" maxlength="40"></div></div>
      <label class="check consent-check"><input type="checkbox" name="consent_confirmed"> 보호자에게 <b>사진 공유</b>와 <b>퇴원 후 3개월 뒤 삭제</b>에 대한 동의를 받았습니다. <span class="muted small">(체크하지 않으면 나중에 프로필에서 확인을 기록하기 전까지 공개할 수 없습니다)</span></label>
      <details class="field"><summary class="small">돌봄 참고사항 입력 (선택)</summary><div class="stack" style="margin-top:10px">
        <p class="callout">직원이 직접 확인한 내용만 입력하세요. AI가 추정해서 채우지 않습니다.</p>
        ${CTX_LABELS.map(([k, l]) => html`<div class="field"><label for="rc-${k}">${l}</label><textarea class="input" style="min-height:56px" id="rc-${k}" name="ctx_${k}" maxlength="300"></textarea></div>`)}</div></details>
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">등록</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      const photo = bindPhotoField(f);
      const prevEl = f.querySelector('#pp-prev');
      f.name.addEventListener('input', () => { prevEl.dataset.initial = f.name.value.trim().slice(0, 1) || '?'; if (!prevEl.querySelector('img')) prevEl.firstChild.textContent = prevEl.dataset.initial; });
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        const v = Object.fromEntries(new FormData(f));
        let bad = false;
        for (const [k, m] of [['name', '이름을 입력해 주세요.'], ['breed', '견종을 입력해 주세요.'], ['birth_date', '생년월일을 입력해 주세요.'], ['owner_name', '보호자 이름을 입력해 주세요.']]) if (!(v[k] || '').trim()) { showFieldError(f, k, m); bad = true; }
        if (bad) { f.querySelector('.err')?.focus(); return; }
        const care_context = Object.fromEntries(CTX_LABELS.map(([k]) => [k, v[`ctx_${k}`] || '']));
        busy(f.querySelector('[type=submit]'), async () => {
          let dog;
          try {
            dog = await api.createDog({ name: v.name.trim(), breed: v.breed.trim(), birth_date: v.birth_date, owner_name: v.owner_name.trim(), care_context, consent_confirmed: !!v.consent_confirmed });
          } catch (err) { if (err instanceof ApiError && err.errors.length) fieldErrors(f, err); else toast(err.message, 'error'); return; }
          let photoFailed = false;
          if (photo.blob) { try { await api.uploadPhoto(dog.id, photo.blob); } catch { photoFailed = true; } }
          close();
          if (photoFailed) toast(`${josa(dog.name, '을', '를')} 등록했지만 사진을 올리지 못했습니다. 프로필 수정에서 다시 올려 주세요.`, 'error');
          else toast(`${josa(dog.name, '을', '를')} 등록했습니다.`);
          ctx.go(`/dogs/${dog.id}`);
        });
      });
    },
  });
}

/** 초대 코드는 이 창에서 한 번만 보여준다(서버에는 해시만 저장됨). */
function inviteModal(ctx, inv) {
  const link = `${location.origin}/#/register`;
  openModal({
    title: `${inv.dog_name} 보호자 초대 코드`,
    body: html`<div class="stack"><p class="callout clay"><b>이 코드는 지금만 볼 수 있어요.</b> 창을 닫으면 다시 확인할 수 없고, 필요하면 새로 만들어야 합니다.</p>
      <div class="invite-code" aria-label="초대 코드">${inv.code}</div>
      <p class="small muted">${fmtWhen(inv.expires_at)}까지, 한 번만 사용할 수 있습니다. 보호자가 아래 주소에서 코드를 입력해 가입합니다.<br><span class="mono">${link}</span></p>
      <div class="mf"><button type="button" class="btn secondary" id="copy">코드 복사</button><button type="button" class="btn" data-close>확인</button></div></div>`.toString(),
    onMount(el, close) {
      el.querySelector('#copy').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(inv.code); toast('초대 코드를 복사했습니다.'); }
        catch { toast('복사하지 못했습니다. 코드를 직접 선택해 복사해 주세요.', 'error'); }
      });
    },
    onClose: () => ctx.rerender(),
  });
}

/** '퇴원' 필터에서 보이는 삭제 예정 현황과(관리자) 삭제 대상 정리 실행 */
async function paintPurgePanel(ctx, el, show, reload) {
  if (!show) { el.innerHTML = ''; return; }
  const list = await api.discharged();
  const due = list.filter((x) => x.due);
  const admin = ctx.staff.role === '관리자';
  el.innerHTML = html`<div class="card" style="margin-bottom:14px"><h3>삭제 예정 현황</h3>
    <p class="small muted" style="margin:4px 0 8px">퇴원 처리 후 <b>3개월</b>이 지나면 사진·영상 파일과 보호자 연결이 삭제됩니다. 글 기록과 업무 이력은 남습니다. 삭제는 되돌릴 수 없습니다.</p>
    ${list.length ? html`<ul class="timeline">${list.map((x) => html`<li style="grid-template-columns:1fr auto;align-items:center"><div><b>${x.name}</b> <span class="small muted">퇴원 ${fmtWhen(x.discharged_at)} · 삭제 예정 ${x.purge_after.slice(0, 10)}</span></div>
      <span class="badge ${x.purged_at ? 'b-done' : x.due ? 'b-pending' : 'b-todo'}">${x.purged_at ? '자료 삭제 완료' : x.due ? '삭제 기한 지남' : `D-${x.purge_days_left}`}</span></li>`)}</ul>` : html`<p class="muted small">퇴원 처리된 반려견이 없습니다.</p>`}
    ${due.length ? html`<div style="margin-top:10px"><button class="btn clay" id="purge" ${admin ? '' : 'disabled'}>삭제 대상 정리 실행 (${due.length}마리)</button> ${admin ? '' : html`<span class="small muted">관리자만 실행할 수 있어요.</span>`}</div>` : ''}</div>`.toString();
  el.querySelector('#purge')?.addEventListener('click', (e) => {
    if (!confirm(`삭제 기한이 지난 ${due.length}마리(${due.map((x) => x.name).join(', ')})의 사진·영상 파일과 보호자 연결을 삭제합니다. 되돌릴 수 없습니다. 계속할까요?`)) return;
    busy(e.currentTarget, () => guarded(async () => {
      const r = await api.purge();
      toast(`${r.count}마리의 자료를 삭제했습니다.`);
      await reload();
    }));
  });
}

/** 퇴원 처리(관리자) */
function dischargeModal(ctx, d, openTasks) {
  openModal({
    title: `${d.name} 퇴원 처리`,
    body: html`<form class="stack" novalidate>
      <p class="callout clay"><b>퇴원 처리하면 다음과 같이 바뀝니다.</b></p>
      <ul class="small" style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px">
        <li>새 돌봄 기록·사진·업무를 만들 수 없고, 새로 보호자에게 공개할 수도 없습니다.</li>
        <li>이미 공개된 사진은 보호자가 <b>삭제 예정일까지</b> 계속 볼 수 있습니다.</li>
        <li><b>퇴원 3개월 뒤</b> 이 아이의 사진·영상 파일과 보호자 연결이 삭제됩니다. 글 기록과 업무 이력은 남습니다.</li>
        <li>삭제 전에는 "재입원 처리"로 되돌릴 수 있고, 삭제된 뒤에는 되돌릴 수 없습니다.</li>
        ${openTasks ? html`<li>아직 끝나지 않은 업무가 <b>${openTasks}건</b> 있습니다. 필요하면 먼저 처리해 주세요.</li>` : ''}</ul>
      <label class="check consent-check"><input type="checkbox" name="ok"> 위 내용을 확인했고, 보호자에게 사전에 동의를 받았음을 확인합니다.</label>
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn clay" type="submit">퇴원 처리</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        if (!f.ok.checked) { showFieldError(f, 'ok', '내용을 확인했다면 체크해 주세요.'); return; }
        busy(f.querySelector('[type=submit]'), () => guarded(async () => { await api.discharge(d.id); close(); toast(`${josa(d.name, '을', '를')} 퇴원 처리했습니다.`); ctx.rerender(); }));
      });
    },
  });
}
