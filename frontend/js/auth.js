import { api, ApiError } from './api.js';
import { html, icon } from './util.js';
import { busy, toast, fieldErrors, showFieldError } from './ui.js';

const home = (account) => (account.role === 'parent' ? '/parent' : '/dashboard');

function shell(title, sub, body) {
  return html`<div class="auth-wrap"><a class="brand dark" href="#/"><img src="assets/favicon.svg" width="30" height="30" alt=""><span class="word">PawCare</span></a>
    <div class="card auth-card"><h1>${title}</h1><p class="muted" style="margin:4px 0 16px">${sub}</p>${body}</div></div>`;
}

export async function loginView({ root, go, me, demo, demoAccounts, setMe, query, flash }) {
  if (me) { go(home(me)); return; }
  const as = query.as === 'parent' ? '보호자' : query.as === 'staff' ? '직원' : '';
  const accounts = demo ? await api.demoAccounts() : [];
  root.innerHTML = shell(`${as} 로그인`.trim(), '가입한 이메일과 비밀번호를 입력하세요.', html`
    ${flash ? html`<p class="callout clay" role="alert" style="margin-bottom:14px">${flash}</p>` : ''}
    <form class="stack" id="f" novalidate>
      <div class="field"><label for="email">이메일</label><input class="input" id="email" name="email" type="email" autocomplete="username" maxlength="254"></div>
      <div class="field"><label for="pw">비밀번호</label><input class="input" id="pw" name="password" type="password" autocomplete="current-password" maxlength="200"></div>
      <p class="form-error" id="form-err" role="alert" hidden></p>
      <button class="btn" type="submit">로그인</button>
    </form>
    <p class="small muted" style="margin-top:14px">보호자이신가요? 직원에게 받은 초대 코드로 <a href="#/register"><b>가입</b></a>할 수 있습니다.</p>
    ${demo ? html`<hr class="sep"><h3 style="margin-bottom:8px">데모 계정으로 입장</h3>
      <p class="small muted" style="margin-bottom:10px">데모 모드입니다. 모두 가상의 계정이며 공개 비밀번호를 쓰므로 인터넷에 공개하지 마세요.</p>
      <div class="chips" style="gap:8px">${accounts.map((a) => html`<button type="button" class="chip" data-demo="${a.id}">${a.role === 'staff' ? `${a.staff_role} · ${a.name}` : `보호자 · ${a.name}`}</button>`)}</div>` : ''}`).toString();

  const f = root.querySelector('#f'), err = root.querySelector('#form-err');
  f.addEventListener('submit', (e) => {
    e.preventDefault(); fieldErrors(f, { errors: [] }); err.hidden = true;
    const v = Object.fromEntries(new FormData(f));
    let bad = false;
    if (!v.email.trim()) { showFieldError(f, 'email', '이메일을 입력해 주세요.'); bad = true; }
    if (!v.password) { showFieldError(f, 'password', '비밀번호를 입력해 주세요.'); bad = true; }
    if (bad) return;
    busy(f.querySelector('[type=submit]'), async () => {
      try {
        const { account } = await api.login(v.email, v.password);
        setMe(account); go(home(account));
      } catch (e2) {
        err.textContent = e2.message; err.hidden = false;      // 401(자격 증명 오류)·429(시도 제한) 메시지를 그대로 보여준다
        f.password.value = ''; f.password.focus();
      }
    });
  });
  root.querySelectorAll('[data-demo]').forEach((b) => b.addEventListener('click', () => busy(b, async () => {
    try { const { account } = await api.demoLogin(+b.dataset.demo); setMe(account); go(home(account)); }
    catch (e2) { toast(e2.message, 'error'); }
  })));
  f.email.focus();
}

export async function registerView({ root, go, me, setMe, query }) {
  if (me) { go(home(me)); return; }
  root.innerHTML = shell('보호자 가입', '직원에게 받은 초대 코드로 가입하면 우리 아이의 알림장을 볼 수 있어요.', html`
    <form class="stack" id="f" novalidate>
      <div class="field"><label for="code">초대 코드 *</label><input class="input mono" id="code" name="code" maxlength="20" autocomplete="off" placeholder="예: AB3K-9QXP" value="${query.code || ''}"><p class="hint">대소문자·하이픈은 상관없습니다. 코드는 한 번만 쓸 수 있고 7일 뒤 만료됩니다.</p></div>
      <div class="field"><label for="name">이름 *</label><input class="input" id="name" name="name" maxlength="30" autocomplete="name"></div>
      <div class="field"><label for="email">이메일 *</label><input class="input" id="email" name="email" type="email" maxlength="254" autocomplete="username"></div>
      <div class="field"><label for="pw">비밀번호 *</label><input class="input" id="pw" name="password" type="password" maxlength="128" autocomplete="new-password"><p class="hint">8자 이상. 이메일이나 흔한 비밀번호는 사용할 수 없습니다.</p></div>
      <div class="field"><label for="pw2">비밀번호 확인 *</label><input class="input" id="pw2" name="password2" type="password" maxlength="128" autocomplete="new-password"></div>
      <button class="btn" type="submit">가입하고 시작하기</button>
    </form>
    <p class="small muted" style="margin-top:14px">이미 계정이 있으신가요? <a href="#/login"><b>로그인</b></a></p>`).toString();
  const f = root.querySelector('#f');
  f.addEventListener('submit', (e) => {
    e.preventDefault(); fieldErrors(f, { errors: [] });
    const v = Object.fromEntries(new FormData(f));
    let bad = false;
    for (const [k, m] of [['code', '초대 코드를 입력해 주세요.'], ['name', '이름을 입력해 주세요.'], ['email', '이메일을 입력해 주세요.'], ['password', '비밀번호를 입력해 주세요.']]) if (!(v[k] || '').trim()) { showFieldError(f, k, m); bad = true; }
    if (!bad && v.password !== v.password2) { showFieldError(f, 'password2', '비밀번호가 서로 다릅니다.'); bad = true; }
    if (bad) { f.querySelector('.err')?.focus(); return; }
    busy(f.querySelector('[type=submit]'), async () => {
      try {
        const { account } = await api.register({ code: v.code, name: v.name, email: v.email, password: v.password });
        setMe(account); toast(`${account.name}님, 가입을 환영합니다.`); go(home(account));
      } catch (e2) {
        if (e2 instanceof ApiError && e2.errors.length) fieldErrors(f, e2); else showFieldError(f, 'code', e2.message);
      }
    });
  });
  f.code.focus();
}
