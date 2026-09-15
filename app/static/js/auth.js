// Refresh-on-load pattern: every page reads the refresh token from
// localStorage, exchanges it for a fresh access token, and holds that
// access token in a page-lifetime variable only (never localStorage).

let _accessToken = null;
let _refreshPromise = null;
let _currentUser = null;

const PUBLIC_PATHS = ["/login"];

function _getRefreshToken() {
  try {
    return localStorage.getItem("refresh_token");
  } catch (e) {
    return null;
  }
}

function setRefreshToken(token) {
  try {
    localStorage.setItem("refresh_token", token);
  } catch (e) {
    // ignore storage failures (private browsing, etc.)
  }
}

function clearSession() {
  try {
    localStorage.removeItem("refresh_token");
  } catch (e) {
    // ignore
  }
  _accessToken = null;
  _currentUser = null;
}

function redirectToLogin() {
  clearSession();
  if (!PUBLIC_PATHS.includes(window.location.pathname)) {
    window.location.href = "/login";
  }
}

async function _refresh() {
  const refreshToken = _getRefreshToken();
  if (!refreshToken) {
    return null;
  }
  try {
    const response = await fetch("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      return null;
    }
    const data = await response.json();
    setRefreshToken(data.refresh_token);
    _accessToken = data.access_token;
    return _accessToken;
  } catch (e) {
    return null;
  }
}

// Ensures a fresh access token, refreshing once per page load. Concurrent
// callers share the same in-flight refresh request.
async function getAccessToken() {
  if (_accessToken) {
    return _accessToken;
  }
  if (!_refreshPromise) {
    _refreshPromise = _refresh();
  }
  const token = await _refreshPromise;
  if (!token && !PUBLIC_PATHS.includes(window.location.pathname)) {
    redirectToLogin();
  }
  return token;
}

async function requireAuth() {
  const token = await getAccessToken();
  if (!token) {
    return null;
  }
  try {
    _currentUser = await apiFetch("/auth/me");
  } catch (e) {
    redirectToLogin();
    return null;
  }
  return _currentUser;
}

async function logout() {
  const refreshToken = _getRefreshToken();
  try {
    await apiFetch("/auth/logout", {
      method: "POST",
      body: refreshToken ? { refresh_token: refreshToken } : undefined,
    });
  } catch (e) {
    // ignore — still clear local session below
  }
  clearSession();
  window.location.href = "/login";
}
