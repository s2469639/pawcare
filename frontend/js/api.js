/* 모든 데이터 변경은 백엔드 API를 통해 저장한다. */
import { session } from './session.js';

export class ApiError extends Error {
  constructor(message, status = 0, errors = []) { super(message); this.status = status; this.errors = errors; }
  fieldError(name) { return this.errors.find((e) => e.field === name)?.message; }
}

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const sid = session.get().staffId;
  if (sid) headers['X-Staff-Id'] = String(sid);
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해 주세요.');
  }
  let data = null;
  try { data = await res.json(); } catch { /* 본문 없음 */ }
  if (!res.ok) throw new ApiError(data?.detail && typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다.', res.status, data?.errors || []);
  return data;
}

const q = (o) => { const p = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null)); return p.size ? `?${p}` : ''; };

export const api = {
  demoStaff: () => request('GET', '/api/demo/staff'),
  reset: () => request('POST', '/api/demo/reset'),
  staff: () => request('GET', '/api/staff'),
  dashboard: () => request('GET', '/api/dashboard'),
  dogs: (params = {}) => request('GET', `/api/dogs${q(params)}`),
  dog: (id) => request('GET', `/api/dogs/${id}`),
  patchDog: (id, b) => request('PATCH', `/api/dogs/${id}`, b),
  records: (params = {}) => request('GET', `/api/records${q(params)}`),
  record: (id) => request('GET', `/api/records/${id}`),
  createRecord: (b) => request('POST', '/api/records', b),
  parentApproval: (id, b) => request('PATCH', `/api/records/${id}/parent-approval`, b),
  tasks: (params = {}) => request('GET', `/api/tasks${q(params)}`),
  task: (id) => request('GET', `/api/tasks/${id}`),
  createTask: (b) => request('POST', '/api/tasks', b),
  patchTask: (id, b) => request('PATCH', `/api/tasks/${id}`, b),
  taskAction: (id, action_type, note) => request('POST', `/api/tasks/${id}/actions`, { action_type, note }),
  suggest: (record_id) => request('POST', '/api/ai/suggest-tasks', { record_id }),
  parentDogs: () => request('GET', '/api/parent/dogs'),
  parentPreview: (id) => request('GET', `/api/parent/dogs/${id}/preview`),
};
