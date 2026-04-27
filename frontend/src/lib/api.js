const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);

function resolveApiBase() {
  const fallback = 'http://127.0.0.1:8000';
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

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function isNetworkError(error) {
  const message = error?.message || String(error || '');
  return (
    error instanceof TypeError ||
    /failed to fetch|networkerror|load failed/i.test(message)
  );
}

export async function apiFetch(path, options = {}) {
  const {
    retries,
    retryDelayMs = 450,
    ...fetchOptions
  } = options;
  const method = String(fetchOptions.method || 'GET').toUpperCase();
  const idempotent = method === 'GET' || method === 'HEAD' || method === 'OPTIONS';
  const maxRetries = retries ?? (idempotent ? 8 : 0);

  let lastError;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      return await fetch(apiUrl(path), {
        cache: 'no-store',
        ...fetchOptions,
        headers: fetchOptions.headers
      });
    } catch (error) {
      lastError = error;
      if (!isNetworkError(error) || attempt === maxRetries) break;
      await delay(retryDelayMs * (attempt + 1));
    }
  }

  throw lastError;
}

export function describeApiError(error) {
  const message = error?.message || String(error || 'Unknown error');
  if (isNetworkError(error)) {
    return (
      `Backend is not reachable at ${API_BASE}. ` +
      'If you just started it, wait for "Application startup complete" and refresh. ' +
      'Command: cd backend; python -m uvicorn main:app --reload --port 8000'
    );
  }
  return message;
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
