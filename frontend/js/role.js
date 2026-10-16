import { api } from './api.js';
import { session } from './session.js';
import { html, icon } from './util.js';
import { busy, guarded } from './ui.js';

export async function roleView({ root, go }) {
  root.innerHTML = html`<div class="landing">
    <div class="word"><img src="assets/favicon.svg" alt="" width="44" height="44">PawCare</div>
    <p class="tag">돌봄의 맥락은 이어지고, 확인할 일은 명확해지도록.<br><span class="small muted">반려견 유치원·호텔 직원을 위한 AI Care Work Manager</span></p>
    <div class="roles">
      <button class="role primary" id="teacher">${icon('paw')}<h2>선생님으로 시작하기</h2>
        <p>돌봄 기록을 남기고, 다음 담당자에게 인계하고, 확인과 조치까지 이어서 관리합니다.</p>
        <span class="go">직원 대시보드로 이동 ${icon('arrow')}</span></button>
      <a class="role secondary" id="parent" href="#/parent">${icon('user')}<h2>보호자로 시작하기</h2>
        <p>직원이 검토하고 공개 승인한 기록만 볼 수 있는 구조를 미리 볼 수 있습니다.</p>
        <span class="go">안내 보기 ${icon('arrow')}</span></a>
    </div>
    <div class="flow" aria-label="PawCare의 업무 흐름"><span class="step">돌봄 기록</span>→<span class="step">후속 업무 제안</span>→<span class="step">담당자 확인</span>→<span class="step">조치 완료</span></div>
    <p class="fine">포트폴리오용 프로토타입입니다. 모든 반려견·보호자·직원 정보는 가상의 데이터이며, 실제 알림이나 메시지는 전송되지 않습니다.</p>
  </div>`.toString();
  root.querySelector('#parent').addEventListener('click', () => session.set({ role: 'parent' }));
  const btn = root.querySelector('#teacher');
  btn.addEventListener('click', () => busy(btn, () => guarded(async () => {
    const staff = await api.demoStaff();
    const saved = session.get().staffId;
    const pick = staff.find((s) => s.id === saved) || staff[0];
    session.set({ role: 'teacher', staffId: pick.id });
    go('/dashboard');
  })));
}
