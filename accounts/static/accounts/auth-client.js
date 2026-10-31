// Same-origin browser module. Use the existing frontend's /api development proxy.
// No authentication credentials or tokens are stored in localStorage.
let csrfToken;

export class ApiError extends Error {
  constructor(status, errors, retryAfter = null) {
    super(errors.detail || `Request failed (${status})`);
    this.status = status;
    this.errors = errors;
    this.retryAfter = retryAfter;
  }
}

export async function refreshCsrf() {
  const response = await fetch('/api/auth/csrf/', {
    credentials: 'same-origin', cache: 'no-store',
  });
  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, data);
  csrfToken = data.csrfToken;
  return csrfToken;
}

export async function apiRequest(path, { method = 'GET', data } = {}) {
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) {
    throw new Error('Only this application\'s same-origin /api/ paths are allowed.');
  }
  method = method.toUpperCase();
  const headers = { Accept: 'application/json' };
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!csrfToken) await refreshCsrf();
    headers['X-CSRFToken'] = csrfToken;
  }
  if (data !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, {
    method, headers, credentials: 'same-origin', cache: 'no-store',
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new ApiError(response.status, payload, response.headers.get('Retry-After'));
  return payload;
}

export const signup = (email, password) => apiRequest('/api/auth/signup/', {
  method: 'POST', data: { email, password },
});

export async function login(email, password) {
  const user = await apiRequest('/api/auth/login/', {
    method: 'POST', data: { email, password },
  });
  // Django rotates the CSRF secret when login establishes the session.
  await refreshCsrf();
  return user;
}

export async function logout() {
  await apiRequest('/api/auth/logout/', { method: 'POST', data: {} });
  csrfToken = undefined;
}

export const currentUser = () => apiRequest('/api/auth/me/');
export const requestPasswordReset = email => apiRequest('/api/auth/password-reset/', {
  method: 'POST', data: { email },
});
export const confirmPasswordReset = (uid, token, newPassword) =>
  apiRequest('/api/auth/password-reset/confirm/', {
    method: 'POST', data: { uid, token, new_password: newPassword },
  });
