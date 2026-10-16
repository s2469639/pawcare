import { api } from './api.js';
import { html, icon } from './util.js';
import { busy, guarded } from './ui.js';

export async function roleView({ root, go, me, demo, setMe }) {
  root.innerHTML = html`<div class="landing">
    <div class="word"><img src="assets/favicon.svg" alt="" width="44" height="44">PawCare</div>
    <p class="tag">돌봄의 맥락은 이어지고, 확인할 일은 명확해지도록.<br><span class="small muted">반려견 유치원·호텔 직원을 위한 AI Care Work Manager</span></p>
    ${me ? html`<p class="callout" style="margin-top:18px">${me.name}님으로 로그인되어 있습니다. <a href="#${me.role === 'parent' ? '/parent' : '/dashboard'}"><b>계속하기</b></a></p>` : ''}
    <div class="roles">
      <button class="role primary" id="teacher">${icon('paw')}<h2>선생님으로 시작하기</h2>
        <p>돌봄 기록을 남기고, 다음 담당자에게 인계하고, 확인과 조치까지 이어서 관리합니다.</p>
        <span class="go">${demo ? '데모 계정으로 바로 입장' : '직원 로그인'} ${icon('arrow')}</span></button>
      <button class="role secondary" id="parent">${icon('user')}<h2>보호자로 시작하기</h2>
        <p>직원이 검토하고 공개 승인한 우리 아이의 기록만 볼 수 있습니다.</p>
        <span class="go">${demo ? '데모 계정으로 바로 입장' : '보호자 로그인'} ${icon('arrow')}</span></button>
    </div>
    <p class="small muted" style="margin-top:14px">${demo ? '데모 모드: 로그인 없이 가상 계정으로 체험합니다.' : '보호자는 직원에게 받은 초대 코드로 가입할 수 있습니다.'} <a href="#/login">${demo ? '이메일로 로그인' : ''}</a>${demo ? '' : html`<a href="#/register">초대 코드로 가입</a>`}</p>
    <div class="flow" aria-label="PawCare의 업무 흐름"><span class="step">돌봄 기록</span>→<span class="step">후속 업무 제안</span>→<span class="step">담당자 확인</span>→<span class="step">조치 완료</span></div>
    <p class="fine">포트폴리오용 프로토타입입니다. 모든 반려견·보호자·직원 정보는 가상의 데이터이며, 실제 알림이나 메시지는 전송되지 않습니다.</p>
  </div>`.toString();

  const enter = (btn, role) => btn.addEventListener('click', () => busy(btn, () => guarded(async () => {
    if (me && me.role === role) { go(role === 'parent' ? '/parent' : '/dashboard'); return; }
    if (!demo) { go(`/login?as=${role}`); return; }
    const accounts = await api.demoAccounts();
    const pick = accounts.find((a) => a.role === role);               // 데모: 첫 번째 직원 / 첫 번째 보호자 계정
    const { account } = await api.demoLogin(pick.id);
    setMe(account);
    go(role === 'parent' ? '/parent' : '/dashboard');
  })));
  enter(root.querySelector('#teacher'), 'staff');
  enter(root.querySelector('#parent'), 'parent');
}
