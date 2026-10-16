/* 데모용 세션(로그인 대체). localStorage는 편의 용도로만 사용하고, 실패해도 동작한다. */
const KEY = 'pawcare.session';
let mem = { role: null, staffId: null };
export const session = {
  get() {
    try { return JSON.parse(localStorage.getItem(KEY)) || mem; } catch { return mem; }
  },
  set(v) {
    mem = { ...this.get(), ...v };
    try { localStorage.setItem(KEY, JSON.stringify(mem)); } catch { /* 무시 */ }
  },
  clear() { mem = { role: null, staffId: null }; try { localStorage.removeItem(KEY); } catch { /* 무시 */ } },
};
