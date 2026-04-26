export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

export async function parseErrorResponse(res) {
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  if (Array.isArray(body.detail)) {
    return body.detail.map(e => {
      const where = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : '';
      return where ? `${where}: ${e.msg}` : e.msg;
    }).join('; ');
  }
  if (typeof body.detail === 'string') return body.detail;
  if (body.detail) return JSON.stringify(body.detail);
  return res.statusText;
}
