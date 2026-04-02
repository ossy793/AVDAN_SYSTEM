/**
 * ADVAN Platform — Centralised API Client
 * All HTTP calls go through this module.
 * Automatically attaches Authorization header from stored JWT.
 */

// In production (Vercel), set window.API_BASE_URL before this script loads,
// or it falls back to the Render backend URL via the meta tag below.
// For local dev it defaults to localhost.
const API_BASE = (
  window.API_BASE_URL ||
  document.querySelector('meta[name="api-base"]')?.content ||
  (location.hostname === 'localhost' || location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000/api'
    : 'https://avdan-system.onrender.com/api')
);

const api = (() => {

  function getToken() {
    return localStorage.getItem('advan_access_token');
  }

  function getHeaders(extra = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...extra,
    };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
  }

  async function request(method, path, body = null, opts = {}) {
    const url = `${API_BASE}${path}`;
    const options = {
      method,
      headers: getHeaders(opts.headers || {}),
    };
    if (body !== null) {
      options.body = JSON.stringify(body);
    }

    let response;
    try {
      // Allow up to 60s for cold-start wakeup on free hosting tiers
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 60000);
      try {
        response = await fetch(url, { ...options, signal: controller.signal });
      } finally {
        clearTimeout(timer);
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        throw new ApiError(0, 'Request timed out. The server may be waking up — please try again.');
      }
      throw new ApiError(0, 'Network error. Please check your connection.');
    }

    // If 401, try to refresh token silently
    if (response.status === 401 && !opts._retry) {
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        return request(method, path, body, { ...opts, _retry: true });
      } else {
        // Force logout — reload current portal page to show its login screen
        authStore.clear();
        window.location.reload();
        return;
      }
    }

    let data;
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (!response.ok) {
      // Pydantic 422 returns detail as an array of validation error objects
      let detail = data.detail;
      if (Array.isArray(detail)) {
        detail = detail.map(e => `${e.loc ? e.loc.slice(1).join('.') + ': ' : ''}${e.msg}`).join('; ');
      }
      throw new ApiError(response.status, detail || 'An error occurred.');
    }

    return data;
  }

  async function tryRefreshToken() {
    const refresh = localStorage.getItem('advan_refresh_token');
    if (!refresh) return false;
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem('advan_access_token', data.access_token);
      localStorage.setItem('advan_refresh_token', data.refresh_token);
      return true;
    } catch {
      return false;
    }
  }

  async function uploadFile(path, formData) {
    // Do NOT set Content-Type — browser sets it automatically with the multipart boundary
    const headers = {};
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData });
    } catch {
      throw new ApiError(0, 'Network error. Please check your connection.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new ApiError(response.status, data.detail || 'Upload failed.');
    }
    return data;
  }

  return {
    get:        (path, opts)        => request('GET',    path, null, opts),
    post:       (path, body, opts)  => request('POST',   path, body, opts),
    patch:      (path, body, opts)  => request('PATCH',  path, body, opts),
    put:        (path, body, opts)  => request('PUT',    path, body, opts),
    delete:     (path, opts)        => request('DELETE', path, null, opts),
    uploadFile: (path, formData)    => uploadFile(path, formData),
  };
})();

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

// ── Auth store ────────────────────────────────────────────────────────────────
const authStore = {
  save(tokenResponse) {
    localStorage.setItem('advan_access_token',  tokenResponse.access_token);
    localStorage.setItem('advan_refresh_token', tokenResponse.refresh_token);
    localStorage.setItem('advan_role',          tokenResponse.role);
    localStorage.setItem('advan_user_id',       tokenResponse.user_id);
    // roles is an array — e.g. ["customer", "vendor"]
    const roles = tokenResponse.roles && tokenResponse.roles.length
      ? tokenResponse.roles
      : [tokenResponse.role];
    localStorage.setItem('advan_roles', JSON.stringify(roles));
  },
  clear() {
    ['advan_access_token','advan_refresh_token','advan_role','advan_roles','advan_user_id']
      .forEach(k => localStorage.removeItem(k));
  },
  getRole()   { return localStorage.getItem('advan_role'); },
  getRoles()  {
    try { return JSON.parse(localStorage.getItem('advan_roles') || '[]'); }
    catch { return [this.getRole()].filter(Boolean); }
  },
  hasRole(role) { return this.getRoles().includes(role); },
  getUserId() { return localStorage.getItem('advan_user_id'); },
  isLoggedIn(){ return !!localStorage.getItem('advan_access_token'); },
};

// ── UI helpers ────────────────────────────────────────────────────────────────
function showAlert(containerSelector, message, type = 'error') {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  container.innerHTML = `
    <div class="alert alert-${type}">
      <span>${escapeHtml(message)}</span>
    </div>`;
  setTimeout(() => { if (container) container.innerHTML = ''; }, 5000);
}

function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `alert alert-${type}`;
  toast.style.cssText = `
    position:fixed; bottom:24px; right:24px; z-index:9999;
    max-width:320px; animation: modal-in .2s ease;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function formatNGN(amount) {
  return '₦' + Number(amount).toLocaleString('en-NG', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  });
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-NG', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function statusBadge(status) {
  return `<span class="badge badge-${status.toLowerCase()}">${status.replace(/_/g,' ')}</span>`;
}

function setLoading(btn, loading) {
  if (loading) {
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px;margin:0;display:inline-block;"></span>';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
    btn.disabled = false;
  }
}

function navigate(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const page = document.getElementById(pageId);
  if (page) page.classList.add('active');
  const navEl = document.querySelector(`[data-page="${pageId}"]`);
  if (navEl) navEl.classList.add('active');
  window.scrollTo(0, 0);
}
