import { api } from './api.js';
import { html, icon, fmtWhen } from './util.js';
import { empty, busy, guarded, toast } from './ui.js';

/** 내 메모: 작성한 직원 본인에게만 보이는 비공개 메모. */
export async function notesView(ctx) {
  const { root } = ctx;
  const notes = await api.notes();
  root.innerHTML = html`
    <div class="page-head"><div><h1>내 메모</h1><p>나만 볼 수 있는 메모예요. 관리자와 다른 직원, 보호자에게도 보이지 않습니다.</p></div></div>
    <form class="card stack" id="nf" novalidate>
      <div class="field"><label for="nb">새 메모</label><textarea class="input" id="nb" name="body" rows="3" maxlength="1000" placeholder="잊기 쉬운 것, 인수인계 전에 적어 둘 것 등"></textarea></div>
      <p class="form-error" id="ne" role="alert" hidden></p>
      <div><button class="btn" type="submit">${icon('plus')} 메모 저장</button></div>
    </form>
    <section class="section" aria-labelledby="nl"><div class="head"><h2 id="nl">저장한 메모 <span class="badge b-done">${notes.length}</span></h2></div>
      ${notes.length ? notes.map((n) => html`<article class="card note" data-note="${n.id}" style="margin-bottom:10px">
        <p class="note-body" style="white-space:pre-wrap">${n.body}</p>
        <div class="ev-top" style="margin-top:8px"><span class="tiny muted">${n.updated_at !== n.created_at ? '수정 ' : ''}${fmtWhen(n.updated_at)}</span><span class="spacer"></span>
          <button class="btn sm secondary" data-edit="${n.id}">수정</button><button class="btn sm ghost" data-del="${n.id}">삭제</button></div></article>`)
        : empty('저장한 메모가 없습니다', '위에서 첫 메모를 적어 보세요.')}</section>`.toString();

  const f = root.querySelector('#nf'), err = root.querySelector('#ne');
  f.addEventListener('submit', (e) => {
    e.preventDefault(); err.hidden = true;
    busy(f.querySelector('[type=submit]'), async () => {
      try { await api.createNote(f.body.value); toast('메모를 저장했습니다.'); ctx.rerender(); }
      catch (er) { err.textContent = er.message; err.hidden = false; }
    });
  });
  root.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => {
    if (!confirm('이 메모를 삭제할까요? 되돌릴 수 없습니다.')) return;
    busy(b, () => guarded(async () => { await api.deleteNote(+b.dataset.del); toast('메모를 삭제했습니다.'); ctx.rerender(); }));
  }));
  root.querySelectorAll('[data-edit]').forEach((b) => b.addEventListener('click', () => {
    const card = b.closest('.note'), n = notes.find((x) => x.id === +b.dataset.edit);
    card.innerHTML = html`<form class="stack" novalidate><textarea class="input" aria-label="메모 수정" rows="4" maxlength="1000">${n.body}</textarea>
      <p class="form-error" role="alert" hidden></p><div class="mf"><button type="button" class="btn secondary" data-cancel>취소</button><button class="btn" type="submit">저장</button></div></form>`.toString();
    const ef = card.querySelector('form'), ee = ef.querySelector('.form-error');
    ef.querySelector('textarea').focus();
    ef.querySelector('[data-cancel]').addEventListener('click', () => ctx.rerender());
    ef.addEventListener('submit', (e) => {
      e.preventDefault(); ee.hidden = true;
      busy(ef.querySelector('[type=submit]'), async () => {
        try { await api.updateNote(n.id, ef.querySelector('textarea').value); toast('메모를 저장했습니다.'); ctx.rerender(); }
        catch (er) { ee.textContent = er.message; ee.hidden = false; }
      });
    });
  }));
}
