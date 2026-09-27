// Direct backend connection (no proxy) — FastAPI with CORS enabled
export const API_URL = 'http://127.0.0.1:8000/api';

// Fired when the backend rejects a request with 401 (expired/invalid JWT).
// The app listens for this event, logs the user out, and shows the login
// view with a clear "session expired" notice.
export const AUTH_EXPIRED_EVENT = 'rapiddoc:auth-expired';

// Always read the CURRENT token from storage at call time so a refreshed or
// re-issued token is used instead of a stale captured value.
export const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export const notifyAuthExpired = () => {
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
};

// Returns true (and notifies once) when the response is a 401 so call sites
// can stop their spinners with a clear message instead of hanging.
export const isAuthExpired = (res) => {
  if (res && res.status === 401) {
    notifyAuthExpired();
    return true;
  }
  return false;
};

/**
 * Safe fetch utility to parse JSON responses without throwing 'Unexpected end of JSON input'
 */
export const safeFetchJson = async (url, options = {}) => {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = {};
  if (text && text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: `Server response (${res.status}): Invalid or non-JSON response.` };
    }
  }
  if (!res.ok) {
    throw new Error(data.detail || `Request failed with status ${res.status}`);
  }
  return data;
};
