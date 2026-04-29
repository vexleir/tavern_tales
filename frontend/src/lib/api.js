const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);

function isPrivateIp(hostname) {
  if (LOCAL_HOSTS.has(hostname)) return true;
  if (/^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname)) return true;
  if (/^192\.168\.\d{1,3}\.\d{1,3}$/.test(hostname)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}$/.test(hostname)) return true;
  return false;
}

function resolveApiBase() {
  const configured = import.meta.env.VITE_API_BASE;
  if (configured) {
    try {
      const parsed = new URL(configured, window.location.origin);
      if (!isPrivateIp(parsed.hostname)) {
        console.warn(`Ignoring non-local VITE_API_BASE (${parsed.origin}); deriving from window.location instead.`);
      } else {
        return parsed.origin;
      }
    } catch {
      // fall through to window.location-based default
    }
  }

  // Default: same hostname as the loaded page, port 8000. This makes a guest
  // browser loading the SPA at http://192.168.1.5:5173 talk to the host's
  // backend at http://192.168.1.5:8000 without extra configuration.
  try {
    const here = new URL(window.location.origin);
    if (isPrivateIp(here.hostname)) {
      return `${here.protocol}//${here.hostname}:8000`;
    }
  } catch {
    // ignore
  }
  return 'http://127.0.0.1:8000';
}

export const API_BASE = resolveApiBase();

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

export function wsUrl(path) {
  // Reuse the API_BASE host/port, swap http(s) → ws(s).
  const base = API_BASE.replace(/^http/, 'ws');
  return `${base}${path}`;
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
