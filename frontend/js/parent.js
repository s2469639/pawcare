import { api } from './api.js';
import { html, icon, fmtWhen, fmtDateKo } from './util.js';
import { avatar, empty, errorBox, demoSelect, guarded, openModal } from './ui.js';

const thumbUrl = (id) => `/api/parent/media/${id}/file?size=thumb`;
const fullUrl = (id) => `/api/parent/media/${id}/file`;

/** 공개된 사진 확대 보기(이전/다음, 저장). 보호자는 자기 아이에게 공개된 사진만 열 수 있다. */
function openPhotoViewer(list, start) {
  let i = start;
  const close = openModal({
    title: '사진', wide: true, body: '<div id="pv"></div>',
    onClose: () => document.removeEventListener('keydown', onKey),
    onMount(el) {
      const paint = () => {
        const m = list[i];
        el.querySelector('#pv').innerHTML = html`<figure class="viewer"><img src="${fullUrl(m.id)}" alt="공개된 사진 ${i + 1}"><figcaption class="small muted">${i + 1}/${list.length}</figcaption></figure>
          <div class="mf" style="justify-content:space-between"><button type="button" class="btn secondary" id="prev" ${i === 0 ? 'disabled' : ''}>이전</button>
            <span style="display:flex;gap:8px"><a class="btn secondary" href="${fullUrl(m.id)}" download="pawcare-photo-${m.id}.webp">사진 저장</a><button type="button" class="btn secondary" id="next" ${i === list.length - 1 ? 'disabled' : ''}>다음</button></span></div>`.toString();
        el.querySelector('#prev').addEventListener('click', () => { i--; paint(); });
        el.querySelector('#next').addEventListener('click', () => { i++; paint(); });
      };
      paint();
    },
  });
  function onKey(e) {
    if (e.key === 'ArrowLeft' && i > 0) document.querySelector('#prev')?.click();
    if (e.key === 'ArrowRight' && i < list.length - 1) document.querySelector('#next')?.click();
  }
  document.addEventListener('keydown', onKey);
  return close;
}

const photoGrid = (media, key) => (media.length ? html`<div class="thumbs big" data-grid="${key}">${media.map((m, i) => html`<button type="button" class="thumb" data-open="${key}:${i}" aria-label="사진 ${i + 1} 크게 보기"><img src="${thumbUrl(m.id)}" alt="" loading="lazy"></button>`)}</div>` : '');
const newBadge = (x) => (x.is_new ? html`<span class="badge b-pending">새 알림장</span>` : '');

/** 보호자 화면: 본인에게 연결된 반려견의 '직원이 공개 승인한' 글과 사진만 보인다. */
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
    let dogs = await api.parentDogs();
    let cur = dogs[0]?.id;
    const paint = async () => {
      const p = cur ? await api.parentPreview(cur) : null;
      const totalNew = dogs.reduce((n, d) => n + d.unseen, 0);
      // 날짜별로 묶기: 승인한 기록(글+사진)과 함께 찍힌 사진
      const items = p ? [...p.records.map((r) => ({ kind: 'rec', at: r.parent_approved_at, r })), ...(p.group_photos.length ? Object.values(p.group_photos.reduce((a, g) => { (a[g.shared_at] ||= { kind: 'grp', at: g.shared_at, photos: [], is_new: false }); a[g.shared_at].photos.push(g); a[g.shared_at].is_new ||= g.is_new; return a; }, {})) : [])].sort((a, b) => (a.at < b.at ? 1 : -1)) : [];
      const days = [...new Set(items.map((x) => x.at.slice(0, 10)))];
      const photoLists = {};
      pw.innerHTML = html`<h1>${me.name}님의 알림장</h1>
        <p class="muted" style="margin:6px 0 12px">직원이 검토하고 <b>공개 승인한 글과 사진만</b> 보입니다. 직원 내부 메모와 업무 인계 내용, 승인 전 사진은 보이지 않습니다.</p>
        <p class="callout" style="margin-bottom:14px">${totalNew ? html`<b>새 알림장 ${totalNew}건</b> · ` : ''}이 프로토타입에는 푸시·메시지 알림이 없어서, 앱(웹앱)을 열어야 새 알림장을 확인할 수 있습니다.</p>
        ${dogs.length ? html`<div class="chips" role="group" aria-label="내 반려견" style="margin-bottom:16px">${dogs.map((d) => html`<button class="chip" data-d="${d.id}" aria-pressed="${d.id === cur}">${d.name}${d.unseen ? html` <span class="n" style="opacity:1;font-weight:700">새 ${d.unseen}</span>` : ''}</button>`)}</div>` : empty('연결된 반려견이 없습니다', '유치원에 문의해 주세요.')}
        ${p ? html`<div class="feed"><div style="display:flex;gap:12px;align-items:center;margin-bottom:14px">${avatar(p.dog)}<div><div class="serif" style="font-weight:700;font-size:20px">${p.dog.name}</div><div class="small muted">${p.dog.breed} · ${p.dog.age_text}</div></div></div>
          ${items.length ? days.map((day) => html`<h3 class="feed-day">${fmtDateKo(day)}</h3>${items.filter((x) => x.at.slice(0, 10) === day).map((x, n) => {
            const key = `${day}-${n}`;
            if (x.kind === 'rec') { photoLists[key] = x.r.media; return html`<article class="feed-card"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="badge b-ack">${x.r.record_type}</span>${newBadge(x.r)}<span class="tiny muted" style="margin-left:auto">${fmtWhen(x.at)} 공개</span></div>
              ${x.r.parent_text ? html`<p style="margin-top:8px">${x.r.parent_text}</p>` : ''}${photoGrid(x.r.media, key)}</article>`; }
            photoLists[key] = x.photos; return html`<article class="feed-card"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="badge b-done">${icon('user')} 친구들과 함께 찍힌 사진</span>${newBadge(x)}<span class="tiny muted" style="margin-left:auto">${fmtWhen(x.at)} 공개</span></div>${photoGrid(x.photos, key)}</article>`;
          })}`)
          : empty('공개된 알림장이 없습니다', '직원이 기록과 사진을 공개 승인하면 이곳에 표시됩니다.')}</div>` : ''}`.toString();
      pw.querySelectorAll('[data-d]').forEach((b) => b.addEventListener('click', () => { cur = +b.dataset.d; paint(); }));
      pw.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => { const [k, i] = [b.dataset.open.slice(0, b.dataset.open.lastIndexOf(':')), +b.dataset.open.split(':').pop()]; openPhotoViewer(photoLists[k], i); }));
      // 열어 본 것으로 기록(이번 화면에서는 '새 알림장' 표시를 그대로 보여주고, 다음에 열 때부터 사라진다)
      if (p && dogs.find((d) => d.id === cur)?.unseen) { api.markSeen(cur).then(() => { dogs.find((d) => d.id === cur).unseen = 0; }).catch(() => {}); }
    };
    await paint();
  } catch (e) {
    pw.innerHTML = errorBox(e).toString();
    pw.querySelector('[data-retry]')?.addEventListener('click', () => location.reload());
  }
}
