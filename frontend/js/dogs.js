import { api, ApiError } from './api.js';
import { html, icon, fmtTime, fmtWhen, josa } from './util.js';
import { avatar, taskRow, empty, ackBadge, actionBadge, busy, guarded, toast, openModal, fieldErrors, showFieldError } from './ui.js';
import { bindTaskActions } from './tasks.js';
import { photoField, bindPhotoField } from './cropper.js';

const CTX_LABELS = [['meal', '식사 관련 주의사항'], ['sensitivity', '알레르기·민감성 정보'], ['behavior', '행동 관련 주의사항'], ['owner_request', '보호자 요청사항'], ['other', '기타 돌봄 참고사항']];
const STATUS = [['all', '전체'], ['needs_check', '확인 필요'], ['has_task', '진행할 업무 있음'], ['clear', '열린 업무 없음']];

const dogCard = (d) => html`<a class="dog-card ${d.needs_check_count ? 'needs' : ''}" href="#/dogs/${d.id}">
  <div class="top">${avatar(d)}<div><div class="name">${d.name}</div><div class="small muted">${d.breed} · ${d.age_text}</div></div>
    ${d.needs_check_count ? html`<span class="badge b-pending" style="margin-left:auto">${icon('clock')} 확인 ${d.needs_check_count}</span>` : ''}</div>
  <div class="row"><b>오늘</b><span>${d.today_status ? html`${d.today_status.record_type} · ${fmtTime(d.today_status.observed_at)} ${d.today_status.structured_value && d.today_status.structured_value !== '직접 입력' ? d.today_status.structured_value : d.today_status.content.slice(0, 36)}` : '오늘 기록 없음'}</span></div>
  <div class="row"><b>업무</b><span>${d.open_task_count ? `진행할 업무 ${d.open_task_count}건` : '열린 업무 없음'}</span></div>
  <div class="row"><b>주의</b><span>${d.caution ? html`${icon('shield')} ${d.caution}` : '등록된 주의사항 없음'}</span></div></a>`;

export async function dogsView(ctx) {
  const { root } = ctx;
  let q = '', status = 'all';
  root.innerHTML = html`<div class="page-head"><div><h1>반려견</h1><p>오늘 돌봄 중인 반려견을 찾고 프로필로 이동합니다.</p></div><button class="btn" id="add-dog">${icon('plus')} 반려견 등록</button></div>
    <div class="toolbar"><label class="sr" for="q">이름 검색</label><input id="q" class="input search" type="search" placeholder="이름으로 검색" autocomplete="off">
    <div class="chips" role="group" aria-label="상태 필터">${STATUS.map(([k, l]) => html`<button class="chip" data-s="${k}" aria-pressed="${k === 'all'}">${l}</button>`)}</div></div>
    <div id="grid" class="dog-grid" aria-live="polite"></div>`.toString();
  const grid = root.querySelector('#grid');
  root.querySelector('#add-dog').addEventListener('click', () => registerDogModal(ctx));
  let seq = 0;
  const load = async () => {
    const my = ++seq;
    try {
      const dogs = await api.dogs({ q, status });
      if (my !== seq) return;
      grid.innerHTML = (dogs.length ? dogs.map(dogCard) : [empty('조건에 맞는 반려견이 없습니다', '검색어나 필터를 바꿔 보세요.')]).join('');
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
  root.innerHTML = html`
    <a class="crumb" href="#/dogs">${icon('back')} 반려견 목록</a>
    <div class="card"><div class="dog-head">${avatar(d, 'lg')}
      <div class="grow"><h1>${d.name}</h1><p class="muted">${d.breed} · ${d.age_text} · 보호자 ${d.owner_name} <span class="tiny">(샘플)</span></p>
        <p style="margin-top:6px">${open.length ? html`<span class="badge b-todo">진행할 업무 ${open.length}건</span>` : html`<span class="badge b-done">열린 업무 없음</span>`}</p></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn" href="#/record/new?dog=${d.id}">${icon('pen')} 돌봄 기록 작성</a>
        <button class="btn secondary" id="goto-tasks">후속 업무 확인 (${open.length})</button><button class="btn secondary" id="edit">프로필 수정</button></div></div></div>

    <section class="section"><div class="head"><h2>지속적으로 확인해야 할 돌봄 정보</h2></div>
      <p class="callout" style="margin-bottom:10px">장기 참고사항입니다. 오늘의 기록과 구분되며, 직원이 직접 입력한 내용만 담기고 AI가 자동으로 바꾸지 않습니다. (샘플 데이터)</p>
      <div class="panel" style="padding:4px 18px"><div class="kv">${CTX_LABELS.flatMap(([k, l]) => [html`<div class="k">${l}</div>`, html`<div>${d.care_context[k] || html`<span class="muted">입력된 내용 없음</span>`}</div>`])}</div></div></section>

    <section class="section"><div class="head"><h2>오늘의 돌봄 기록</h2><span class="small muted">${d.records_today.length}건</span></div>
      <div class="panel" style="padding:4px 18px">${d.records_today.length ? html`<ul class="timeline">${d.records_today.map((r) => html`<li><div class="t">${fmtTime(r.observed_at)}</div><div class="body">
        <div><span class="badge b-done">${r.record_type}</span>${r.block_name ? html` <span class="badge b-ack">${r.block_name}</span>` : ''} ${r.structured_value && r.structured_value !== '직접 입력' ? html`<b>${r.structured_value}</b>` : ''} <span class="small muted">· ${r.author_name} (${r.author_role})</span></div>
        <p style="margin-top:4px">${r.content}</p>
        <div class="tags">${r.tasks.map((t) => html`<a class="link-task" href="#/tasks/${t.id}">${icon('list')} ${t.title} · ${t.acknowledgment_status === 'pending' ? '확인 대기' : '확인 완료'} / ${{ todo: '조치 필요', in_progress: '진행 중', completed: '조치 완료' }[t.action_status]}</a>`)}
          ${r.tasks.length ? '' : html`<a class="btn sm secondary" href="#/ai/${r.id}">${icon('spark')} 후속 업무 제안</a>`}
          ${r.parent_status === 'approved' ? html`<span class="badge b-ack">${icon('check')} 보호자 공개 승인됨</span><button class="btn sm ghost" data-revoke="${r.id}">공개 취소</button>` : html`<span class="badge b-private">${icon('lock')} 내부 기록</span><button class="btn sm ghost" data-approve="${r.id}">보호자 공개 승인…</button>`}</div></div></li>`)}</ul>`
        : html`<div style="padding:14px 0">${empty('오늘 작성된 기록이 없습니다', '', html`<br><a class="btn" href="#/record/new?dog=${d.id}">돌봄 기록 작성</a>`)}</div>`}</div></section>

    <section class="section" id="dog-tasks"><div class="head"><h2>처리해야 할 업무</h2></div>
      ${d.tasks.length ? html`<div class="task-list">${d.tasks.map((t) => taskRow(t, staff, { showDog: false }))}</div>` : empty('이 반려견의 업무가 없습니다', '기록을 바탕으로 후속 업무를 만들 수 있습니다.')}</section>

    <section class="section" id="guardians" aria-labelledby="gt"><div class="head"><h2 id="gt">보호자 계정</h2><button class="btn secondary" id="invite">${icon('plus')} 초대 코드 만들기</button></div>
      <div class="panel" style="padding:4px 18px">
        ${g.guardians.length ? html`<ul class="timeline">${g.guardians.map((p) => html`<li style="grid-template-columns:1fr auto"><div><b>${p.name}</b> <span class="small muted">${p.email}</span></div><span class="badge b-ack">${icon('check')} 가입됨</span></li>`)}</ul>`
          : html`<p class="muted small" style="padding:14px 0">아직 가입한 보호자가 없습니다. 초대 코드를 만들어 보호자에게 전달해 주세요.</p>`}
        ${g.invites.length ? html`<hr class="sep" style="margin:0"><p class="small muted" style="padding:10px 0 2px">최근 초대 코드 (코드 원문은 만든 직후 한 번만 볼 수 있습니다)</p>
          <ul class="timeline">${g.invites.map((i) => html`<li style="grid-template-columns:1fr auto;align-items:center"><div class="small">${fmtWhen(i.created_at)} 생성 · ${i.status === 'used' ? `${fmtWhen(i.used_at)} 사용됨` : `${fmtWhen(i.expires_at)}까지`}</div>
            <div>${i.status === 'active' ? html`<span class="badge b-pending">${icon('clock')} 사용 대기</span> <button class="btn sm ghost" data-revoke-invite="${i.id}">취소</button>` : i.status === 'used' ? html`<span class="badge b-done">${icon('check')} 사용됨</span>` : html`<span class="badge b-done">만료됨</span>`}</div></li>`)}</ul>` : ''}
      </div></section>`.toString();

  root.querySelector('#goto-tasks').addEventListener('click', () => root.querySelector('#dog-tasks').scrollIntoView({ behavior: 'smooth' }));
  root.querySelector('#edit').addEventListener('click', () => profileModal(ctx, d));
  root.querySelector('#invite').addEventListener('click', (e) => busy(e.currentTarget, () => guarded(async () => {
    const inv = await api.createInvite(d.id);
    inviteModal(ctx, inv);
  })));
  root.querySelectorAll('[data-revoke-invite]').forEach((b) => b.addEventListener('click', () => busy(b, () => guarded(async () => {
    await api.revokeInvite(+b.dataset.revokeInvite); toast('초대 코드를 취소했습니다.'); ctx.rerender();
  }))));
  bindTaskActions(root, ctx);
  root.querySelectorAll('[data-approve]').forEach((b) => b.addEventListener('click', () => approveModal(ctx, d.records_today.find((r) => r.id === +b.dataset.approve))));
  root.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', () => busy(b, () => guarded(async () => { await api.parentApproval(+b.dataset.revoke, { action: 'revoke' }); toast('보호자 공개를 취소했습니다.'); ctx.rerender(); }))));
}

function approveModal(ctx, r) {
  openModal({
    title: '보호자 공개 승인',
    body: html`<form class="stack" novalidate><p class="callout">직원 내부 기록과 업무 인계 내용은 공개되지 않습니다. 아래 문구만 보호자 미리보기에 표시됩니다. (실제 전송 기능은 없습니다)</p>
      <div class="quote"><p class="small muted">내부 기록 원문</p><p>${r.content}</p></div>
      <div class="field"><label for="pt">보호자에게 보여줄 문구 *</label><textarea class="input" id="pt" name="parent_text" maxlength="500">${r.content}</textarea><p class="hint">내부 인계 표현(예: 담당자 지정)은 직접 지우거나 고쳐 주세요.</p></div>
      <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button class="btn" type="submit">공개 승인</button></div></form>`.toString(),
    onMount(el, close) {
      const f = el.querySelector('form');
      f.addEventListener('submit', (e) => {
        e.preventDefault(); fieldErrors(f, { errors: [] });
        const v = f.parent_text.value.trim();
        if (!v) { showFieldError(f, 'parent_text', '보호자에게 보여줄 문구를 입력해 주세요.'); return; }
        busy(f.querySelector('[type=submit]'), () => guarded(async () => { await api.parentApproval(r.id, { action: 'approve', parent_text: v }); close(); toast('보호자 미리보기에 공개하도록 승인했습니다.'); ctx.rerender(); }));
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
            dog = await api.createDog({ name: v.name.trim(), breed: v.breed.trim(), birth_date: v.birth_date, owner_name: v.owner_name.trim(), care_context });
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
