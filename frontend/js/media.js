/* 기록에 첨부하는 사진: 브라우저에서 리사이즈 → 서버로 한 장씩 업로드, 썸네일·뷰어(태그 수정·삭제). */
import { api } from './api.js';
import { html, icon, esc, fmtWhen } from './util.js';
import { openModal, toast } from './ui.js';

export const MAX_PER_RECORD = 10;
const SIDE = 1600, LIMIT = 1_900_000, MAX_INPUT = 30 * 1024 * 1024;

async function decode(file) {
  try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch { /* 아래에서 대체 */ }
  return new Promise((res, rej) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => { URL.revokeObjectURL(url); res(img); };
    img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('decode')); };
    img.src = url;
  });
}

/** 사진 파일 → 긴 변 1600px 이하의 WebP(미지원 브라우저는 JPEG) Blob. 다시 그리므로 EXIF는 이 단계에서도 사라진다. */
export async function processImage(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) throw new Error(`${file.name}: JPG, PNG, WebP 사진만 사용할 수 있습니다. (아이폰 HEIC는 JPG로 변환해 주세요)`);
  if (file.size > MAX_INPUT) throw new Error(`${file.name}: 사진이 너무 큽니다. (30MB 이하)`);
  let bmp;
  try { bmp = await decode(file); } catch { throw new Error(`${file.name}: 열 수 없는 사진입니다.`); }
  const k = Math.min(1, SIDE / Math.max(bmp.width, bmp.height));
  const cv = document.createElement('canvas');
  cv.width = Math.max(1, Math.round(bmp.width * k)); cv.height = Math.max(1, Math.round(bmp.height * k));
  cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
  const enc = (type, q) => new Promise((r) => cv.toBlob(r, type, q));
  for (const q of [0.85, 0.7, 0.55]) {
    let b = await enc('image/webp', q);
    if (!b || b.type !== 'image/webp') b = await enc('image/jpeg', q);
    if (b && b.size <= LIMIT) return b;
  }
  throw new Error(`${file.name}: 사진 용량을 줄이지 못했습니다.`);
}

export async function uploadAll(recordId, items, dogIds, onProgress = () => {}) {
  const failed = [];
  let n = 0;
  for (const it of items) {
    try { await api.uploadMedia(recordId, it.blob, dogIds); } catch (e) { failed.push({ item: it, message: e.message }); }
    onProgress(++n, items.length);
  }
  return failed;
}

export const thumbs = (media, recId) => (media.length ? html`<div class="thumbs" ${recId ? html`data-rec="${recId}"` : ''}>${media.map((m, i) => html`<button type="button" class="thumb" data-media-open="${i}" aria-label="사진 ${i + 1} 크게 보기 (${m.dog_names.join(', ')})"><img src="/api/media/${m.id}/file?size=thumb" alt="" loading="lazy"></button>`)}</div>` : '');

// ---------------- 기록 작성 폼의 사진 첨부 필드 ----------------
export function photoAttachField(dogs) {
  return html`<div class="field" data-field="photos"><span class="lbl">사진 첨부 <span class="muted small">(선택 · 최대 ${MAX_PER_RECORD}장)</span></span>
    <div class="photo-grid" id="pa-grid"></div>
    <div><label class="btn secondary sm" for="pa-file">${icon('plus')} 사진 선택</label><input type="file" id="pa-file" class="sr" accept="image/jpeg,image/png,image/webp" multiple></div>
    <div id="pa-tags" hidden><p class="small muted" style="margin:10px 0 6px">사진에 함께 찍힌 아이를 모두 선택해 주세요. (기본: 기록의 반려견)</p>
      <div class="chips" role="group" aria-label="사진에 찍힌 반려견">${dogs.map((d) => html`<button type="button" class="chip" data-tag="${d.id}" aria-pressed="false">${d.name}</button>`)}</div></div>
    <p class="hint">기록을 저장하면 함께 올라가고, 보호자에게는 직원이 공개 승인하기 전까지 보이지 않습니다. 위치 등 사진 속 정보는 올릴 때 제거됩니다.</p></div>`;
}

export function bindPhotoAttach(root, { getDogId }) {
  const grid = root.querySelector('#pa-grid'), file = root.querySelector('#pa-file'), tagBox = root.querySelector('#pa-tags');
  const state = { items: [], tags: new Set(), custom: false };
  const paintTags = () => root.querySelectorAll('[data-tag]').forEach((b) => b.setAttribute('aria-pressed', state.tags.has(+b.dataset.tag)));
  const sync = () => { if (!state.custom) { state.tags = new Set(getDogId() ? [getDogId()] : []); paintTags(); } };
  const paint = () => {
    grid.innerHTML = state.items.map((it, i) => `<div class="pa-item"><img src="${esc(it.url)}" alt="선택한 사진 ${i + 1}"><button type="button" class="pa-x" data-rm="${i}" aria-label="사진 ${i + 1} 빼기">✕</button></div>`).join('');
    tagBox.hidden = state.items.length === 0;
    grid.querySelectorAll('[data-rm]').forEach((b) => b.addEventListener('click', () => { const [it] = state.items.splice(+b.dataset.rm, 1); URL.revokeObjectURL(it.url); paint(); }));
  };
  file.addEventListener('change', async () => {
    const files = [...file.files]; file.value = '';
    const room = MAX_PER_RECORD - state.items.length;
    if (files.length > room) toast(`사진은 최대 ${MAX_PER_RECORD}장까지 첨부할 수 있어요. ${room}장만 추가합니다.`, 'error');
    for (const f of files.slice(0, Math.max(0, room))) {
      try { const blob = await processImage(f); state.items.push({ blob, url: URL.createObjectURL(blob), name: f.name }); }
      catch (e) { toast(e.message, 'error'); }
    }
    sync(); paint();
  });
  root.querySelectorAll('[data-tag]').forEach((b) => b.addEventListener('click', () => {
    state.custom = true; const id = +b.dataset.tag;
    state.tags.has(id) ? state.tags.delete(id) : state.tags.add(id); paintTags();
  }));
  sync();
  return {
    get items() { return state.items; },
    tagIds() { return [...state.tags]; },
    onDogChange: sync,
    clear() { state.items.forEach((it) => URL.revokeObjectURL(it.url)); state.items = []; state.custom = false; sync(); paint(); },
  };
}

// ---------------- 뷰어 ----------------
export async function openMediaViewer(list, start, ctx) {
  const dogs = await api.dogs();
  let i = start;
  let changed = false;
  let pending = Promise.resolve();       // 진행 중인 변경 요청(창을 바로 닫아도 끝난 뒤 목록을 새로고침한다)
  const close = openModal({
    title: '사진', wide: true,
    body: '<div id="mv"></div>',
    onClose: () => { document.removeEventListener('keydown', onKey); pending.finally(() => { if (changed) ctx.rerender(); }); },
    onMount(el) {
      const paint = () => {
        const m = list[i];
        el.querySelector('#mv').innerHTML = html`<figure class="viewer"><img src="/api/media/${m.id}/file" alt="${m.dog_names.join(', ')} 사진"><figcaption class="small muted">${fmtWhen(m.created_at)} 업로드 · ${i + 1}/${list.length}</figcaption></figure>
          <p class="small" style="margin:10px 0 6px"><b>찍힌 아이</b> <span class="muted">(눌러서 바꾸기)</span></p>
          <div class="chips" role="group" aria-label="사진에 찍힌 반려견">${dogs.map((d) => html`<button type="button" class="chip" data-t="${d.id}" aria-pressed="${m.dog_ids.includes(d.id)}">${d.name}</button>`)}</div>
          <div class="mf" style="justify-content:space-between"><button type="button" class="btn secondary" id="prev" ${i === 0 ? 'disabled' : ''}>이전</button>
            <span style="display:flex;gap:8px"><button type="button" class="btn ghost" id="del">사진 삭제</button><button type="button" class="btn secondary" id="next" ${i === list.length - 1 ? 'disabled' : ''}>다음</button></span></div>`.toString();
        el.querySelector('#prev').addEventListener('click', () => { i--; paint(); });
        el.querySelector('#next').addEventListener('click', () => { i++; paint(); });
        el.querySelectorAll('[data-t]').forEach((b) => b.addEventListener('click', () => {
          const id = +b.dataset.t, cur = new Set(m.dog_ids);
          cur.has(id) ? cur.delete(id) : cur.add(id);
          if (!cur.size) { toast('찍힌 아이는 한 마리 이상이어야 해요.', 'error'); return; }
          pending = (async () => {
            try { const u = await api.tagMedia(m.id, [...cur]); Object.assign(m, u); changed = true; if (el.isConnected) paint(); }
            catch (e) { toast(e.message, 'error'); }
          })();
        }));
        el.querySelector('#del').addEventListener('click', () => {
          if (!confirm('이 사진을 삭제할까요? 되돌릴 수 없습니다.')) return;
          pending = (async () => {
            try {
              await api.deleteMedia(m.id); changed = true; toast('사진을 삭제했습니다.');
              const at = list.indexOf(m); if (at >= 0) list.splice(at, 1);
              if (!el.isConnected) return;                       // 이미 창을 닫았다면 화면 갱신은 닫힘 처리에서
              if (!list.length) { close(); return; }
              i = Math.min(i, list.length - 1); paint();
            } catch (e) { toast(e.message, 'error'); }
          })();
        });
      };
      paint();
    },
  });
  function onKey(e) {
    if (document.querySelectorAll('.overlay').length !== 1) return;     // 다른 창(확인 등)이 위에 있으면 무시
    if (e.key === 'ArrowLeft' && i > 0) document.querySelector('#prev')?.click();
    if (e.key === 'ArrowRight' && i < list.length - 1) document.querySelector('#next')?.click();
  }
  document.addEventListener('keydown', onKey);
}
