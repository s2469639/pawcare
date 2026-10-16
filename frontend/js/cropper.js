/* 사진 선택 → 원형 가이드 안에서 위치·확대 조절 → 512×512 정사각형으로 잘라 Blob 반환. 외부 라이브러리 없음. */
import { html, raw, esc } from './util.js';
import { openModal, toast } from './ui.js';

const VIEW = 300, D = 260, OUT = 512, MAX_INPUT = 20 * 1024 * 1024, MAX_UPLOAD = 1_000_000;

async function decode(file) {
  try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch { /* 아래에서 대체 */ }
  return new Promise((res, rej) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => { URL.revokeObjectURL(url); res(img); };
    img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('decode')); };
    img.src = url;
  });
}

async function toBlob(canvas) {
  const enc = (type, q) => new Promise((r) => canvas.toBlob(r, type, q));
  for (const q of [0.9, 0.8, 0.7, 0.55]) {
    let b = await enc('image/webp', q);
    if (!b || b.type !== 'image/webp') b = await enc('image/jpeg', q);   // webp 인코딩을 지원하지 않는 브라우저
    if (b && b.size <= MAX_UPLOAD) return b;
  }
  return null;
}

/** 파일을 받아 자른 Blob을 반환한다. 취소하면 null. */
export async function cropImage(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { toast('JPG, PNG, WebP 사진만 사용할 수 있습니다. (아이폰 HEIC 사진은 JPG로 변환해 주세요)', 'error'); return null; }
  if (file.size > MAX_INPUT) { toast('사진이 너무 큽니다. 20MB 이하의 사진을 선택해 주세요.', 'error'); return null; }
  let img;
  try { img = await decode(file); } catch { toast('이 사진을 열 수 없습니다. 다른 사진을 선택해 주세요.', 'error'); return null; }
  const iw = img.width, ih = img.height, s0 = D / Math.min(iw, ih);
  let zoom = 1, ox = 0, oy = 0;

  return new Promise((resolve) => {
    let settled = false;
    const done = (v) => { if (!settled) { settled = true; resolve(v); } };
    openModal({
      title: '프로필 사진 자르기',
      onClose: () => done(null),
      body: html`<div class="cropper">
        <canvas id="cv" width="${VIEW}" height="${VIEW}" tabindex="0" role="img" aria-label="사진 위치 조절. 드래그하거나 방향키로 이동, +/- 키로 확대"></canvas>
        <label class="small muted" for="zm">확대</label>
        <input id="zm" type="range" min="1" max="3" step="0.01" value="1" aria-label="확대 비율">
        <p class="hint">원 안에 보이는 부분이 프로필 사진이 됩니다. 사진을 끌어서 얼굴을 가운데에 맞춰 주세요.</p>
        <div class="mf"><button type="button" class="btn secondary" data-close>취소</button><button type="button" class="btn" id="ok">적용</button></div></div>`.toString(),
      onMount(el, closeModal) {
        const cv = el.querySelector('#cv'), ctx = cv.getContext('2d'), zm = el.querySelector('#zm');
        const clamp = () => {
          const mx = Math.max(0, (iw * s0 * zoom - D) / 2), my = Math.max(0, (ih * s0 * zoom - D) / 2);
          ox = Math.min(mx, Math.max(-mx, ox)); oy = Math.min(my, Math.max(-my, oy));
        };
        const draw = () => {
          clamp();
          const sc = s0 * zoom, dx = VIEW / 2 + ox - (iw * sc) / 2, dy = VIEW / 2 + oy - (ih * sc) / 2;
          ctx.clearRect(0, 0, VIEW, VIEW);
          ctx.drawImage(img, dx, dy, iw * sc, ih * sc);
          ctx.save(); ctx.fillStyle = 'rgba(38,56,47,.55)'; ctx.beginPath();
          ctx.rect(0, 0, VIEW, VIEW); ctx.arc(VIEW / 2, VIEW / 2, D / 2, 0, Math.PI * 2, true); ctx.fill('evenodd');
          ctx.restore();
          ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(VIEW / 2, VIEW / 2, D / 2, 0, Math.PI * 2); ctx.stroke();
        };
        let drag = null;
        cv.addEventListener('pointerdown', (e) => { cv.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, ox, oy }; });
        cv.addEventListener('pointermove', (e) => { if (!drag) return; const k = VIEW / cv.getBoundingClientRect().width; ox = drag.ox + (e.clientX - drag.x) * k; oy = drag.oy + (e.clientY - drag.y) * k; draw(); });
        const end = () => { drag = null; };
        cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
        const setZoom = (z) => { zoom = Math.min(3, Math.max(1, z)); zm.value = zoom; draw(); };
        zm.addEventListener('input', () => setZoom(+zm.value));
        cv.addEventListener('wheel', (e) => { e.preventDefault(); setZoom(zoom - e.deltaY * 0.002); }, { passive: false });
        cv.addEventListener('keydown', (e) => {
          const step = 12, m = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
          if (m) { e.preventDefault(); ox += m[0]; oy += m[1]; draw(); }
          else if (e.key === '+' || e.key === '=') setZoom(zoom + 0.1);
          else if (e.key === '-') setZoom(zoom - 0.1);
        });
        el.querySelector('#ok').addEventListener('click', async (ev) => {
          ev.target.disabled = true;
          const sc = s0 * zoom, dx = VIEW / 2 + ox - (iw * sc) / 2, dy = VIEW / 2 + oy - (ih * sc) / 2;
          const out = document.createElement('canvas'); out.width = out.height = OUT;
          out.getContext('2d').drawImage(img, (VIEW / 2 - D / 2 - dx) / sc, (VIEW / 2 - D / 2 - dy) / sc, D / sc, D / sc, 0, 0, OUT, OUT);
          const blob = await toBlob(out);
          if (!blob) { toast('사진을 1MB 이하로 줄이지 못했습니다. 다른 사진을 선택해 주세요.', 'error'); ev.target.disabled = false; return; }
          done(blob); closeModal();
        });
        draw(); cv.focus();
      },
    });
  });
}

/** 폼에 넣는 사진 선택 필드. bindPhotoField(root)로 동작을 연결한다. */
export function photoField({ photo, name }) {
  return html`<div class="field photo-field" data-field="photo"><span class="lbl">프로필 사진 <span class="muted small">(선택)</span></span>
    <div class="photo-row"><span class="avatar lg" id="pp-prev" data-initial="${(name || '?').slice(0, 1)}" data-has="${photo ? '1' : ''}" style="background:#A5AE98">${(name || '?').slice(0, 1)}${photo ? raw(`<img src="${esc(photo)}" alt="">`) : ''}</span>
      <div><label class="btn secondary sm" for="pp-file">사진 선택</label><input type="file" id="pp-file" class="sr" accept="image/jpeg,image/png,image/webp">
        <button type="button" class="btn ghost sm" id="pp-remove" ${photo ? '' : 'hidden'}>사진 삭제</button>
        <p class="hint">어떤 비율의 사진이든 올릴 수 있어요. 선택하면 원형 가이드 안에서 정사각형으로 잘라 줍니다. (JPG·PNG·WebP)</p></div></div></div>`;
}

export function bindPhotoField(root) {
  const prev = root.querySelector('#pp-prev'), file = root.querySelector('#pp-file'), rm = root.querySelector('#pp-remove');
  const state = { blob: null, remove: false };
  let url = null;
  const show = (src) => { prev.innerHTML = esc(prev.dataset.initial) + (src ? `<img src="${esc(src)}" alt="">` : ''); };
  file.addEventListener('change', async () => {
    const f = file.files[0]; file.value = '';
    if (!f) return;
    const blob = await cropImage(f);
    if (!blob) return;
    if (url) URL.revokeObjectURL(url);
    url = URL.createObjectURL(blob);
    state.blob = blob; state.remove = false; show(url); rm.hidden = false;
  });
  rm.addEventListener('click', () => { state.blob = null; state.remove = !!prev.dataset.has; show(null); rm.hidden = true; });
  return state;
}
