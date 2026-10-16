/* 안전한 HTML 템플릿: 보간되는 값은 기본적으로 이스케이프된다. */
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(s);
export const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const part = (v) => (v == null || v === false ? '' : v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join('') : esc(v));
export function html(strings, ...vals) {
  let out = '';
  strings.forEach((s, i) => { out += s; if (i < vals.length) out += part(vals[i]); });
  return new Raw(out);
}

const P = {
  paw: '<ellipse cx="12" cy="16.5" rx="4.6" ry="3.8"/><circle cx="5.5" cy="11" r="1.8"/><circle cx="9.5" cy="6.8" r="1.8"/><circle cx="14.5" cy="6.8" r="1.8"/><circle cx="18.5" cy="11" r="1.8"/>',
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  dog: '<path d="M4 10c0-3 2-5 5-5h3l3 2 3-1v5l-2 2v5a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-4z"/>',
  pen: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M14 6l4 4"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 21h4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5h.01"/>',
  half: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-6 8-6s8 2 8 6"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
export const icon = (n, cls = '') => raw(`<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[n]}</svg>`);

const WD = '일월화수목금토';
export const pad = (n) => String(n).padStart(2, '0');
export function parseLocal(iso) { return new Date(iso); }
export const fmtTime = (iso) => (iso ? iso.slice(11, 16) : '');
export function fmtDateKo(d) { const x = new Date(d + 'T00:00:00'); return `${x.getFullYear()}년 ${x.getMonth() + 1}월 ${x.getDate()}일 (${WD[x.getDay()]})`; }
export function fmtWhen(iso) {
  if (!iso) return '';
  const today = new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000); // KST 기준 오늘
  const key = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  return iso.slice(0, 10) === key ? `오늘 ${fmtTime(iso)}` : `${+iso.slice(5, 7)}/${+iso.slice(8, 10)} ${fmtTime(iso)}`;
}
export function nowKstLocalInput() {
  const d = new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const FILTERS = [['all', '전체'], ['pending', '확인 대기'], ['todo', '조치 필요'], ['in_progress', '진행 중'], ['completed', '완료']];
export function matchFilter(t, f) {
  switch (f) {
    case 'pending': return t.acknowledgment_status === 'pending' && t.action_status !== 'completed';
    case 'todo': return t.action_status === 'todo';
    case 'in_progress': return t.action_status === 'in_progress';
    case 'completed': return t.action_status === 'completed';
    default: return true;
  }
}
export function groupKey(t) {
  if (t.action_status === 'completed') return 'completed';
  if (t.acknowledgment_status === 'pending') return 'pending';
  return t.action_status === 'todo' ? 'todo' : 'in_progress';
}
export const GROUP_LABEL = { pending: '확인 대기 · 아직 확인하지 않은 업무', todo: '조치 필요 · 확인했지만 아직 조치하지 않은 업무', in_progress: '진행 중', completed: '완료' };
export const canAct = (staff, t) => t.assignee_id == null || t.assignee_id === staff.id || staff.role === '관리자';

/** 받침 유무에 따라 조사를 붙인다. josa('초코', '을', '를') → '초코를', josa('보리', '이', '가') → '보리가' */
export function josa(word, withFinal, noFinal) {
  const c = String(word).trim().slice(-1).charCodeAt(0);
  const hasFinal = c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 !== 0;
  return `${word}${hasFinal ? withFinal : noFinal}`;
}
