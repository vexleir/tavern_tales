const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);

function resolveApiBase() {
  const fallback = 'http://localhost:8000';
  const configured = import.meta.env.VITE_API_BASE || fallback;
  try {
    const parsed = new URL(configured, window.location.origin);
    if (!LOCAL_HOSTS.has(parsed.hostname)) {
      console.warn(`Ignoring non-local VITE_API_BASE (${parsed.origin}); using ${fallback}`);
      return fallback;
    }
    return parsed.origin;
  } catch {
    return fallback;
  }
}

export const API_BASE = resolveApiBase();

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

export function apiFetch(path, options = {}) {
  return fetch(apiUrl(path), {
    cache: 'no-store',
    ...options,
    headers: options.headers
  });
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
