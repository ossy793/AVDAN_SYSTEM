/**
 * ADVAN Rider App — Application Logic
 * Handles GPS tracking, order lifecycle, earnings.
 */

let riderMap = null;
let riderMarker = null;
let locationInterval = null;
let isOnline = false;

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
  document.getElementById('registerForm').addEventListener('submit', handleRegister);
  document.getElementById('profileSetupForm').addEventListener('submit', handleProfileSetup);

  document.getElementById('showRegister').addEventListener('click', e => {
    e.preventDefault();
    document.getElementById('login-form').classList.add('hidden');
    document.getElementById('register-form').classList.remove('hidden');
    document.getElementById('auth-alert').innerHTML = '';
  });
  document.getElementById('showLogin').addEventListener('click', e => {
    e.preventDefault();
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('login-form').classList.remove('hidden');
    document.getElementById('auth-alert').innerHTML = '';
  });

  if (authStore.isLoggedIn()) {
    showApp();
  }
});

async function handleLogin(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  setLoading(btn, true);
  try {
    const data = await api.post('/auth/login', {
      email: document.getElementById('loginEmail').value.trim(),
      password: document.getElementById('loginPassword').value,
    });
    if (!(data.roles || [data.role]).includes('rider')) {
      showAlert('#auth-alert', 'This portal is for riders only. Register as a rider first.', 'error');
      return;
    }
    authStore.save(data);
    showApp();
  } catch (err) {
    showAlert('#auth-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  setLoading(btn, true);
  try {
    await api.post('/auth/register', {
      email: document.getElementById('regEmail').value.trim(),
      phone: document.getElementById('regPhone').value.trim(),
      first_name: document.getElementById('regFirst').value.trim(),
      last_name: document.getElementById('regLast').value.trim(),
      password: document.getElementById('regPassword').value,
      role: 'rider',
    });
    showAlert('#auth-alert', 'Account created! Please sign in.', 'success');
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('login-form').classList.remove('hidden');
    e.target.reset();
  } catch (err) {
    showAlert('#auth-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

async function handleProfileSetup(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  setLoading(btn, true);
  try {
    await api.post('/auth/rider/profile', {
      vehicle_type: document.getElementById('setupVType').value,
      plate_number: document.getElementById('setupPlate').value.trim() || null,
      bank_account_number: document.getElementById('setupBankAcc').value.trim() || null,
      bank_code: document.getElementById('setupBankCode').value.trim() || null,
      bank_name: document.getElementById('setupBankName').value.trim() || null,
    });
    document.getElementById('profile-setup').classList.add('hidden');
    _mountApp();
  } catch (err) {
    showAlert('#setup-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function logout() {
  if (locationInterval) clearInterval(locationInterval);
  authStore.clear();
  location.reload();
}

async function showApp() {
  document.getElementById('auth-gate').classList.add('hidden');

  // First-time riders need to complete their vehicle profile before accessing the app
  const profile = await api.get('/rider/profile').catch(() => null);
  if (!profile) {
    document.getElementById('profile-setup').classList.remove('hidden');
    return;
  }

  _mountApp();
}

async function _mountApp() {
  document.getElementById('app').classList.remove('hidden');
  try {
    const user = await api.get('/auth/me');
    document.getElementById('user-name').textContent = `${user.first_name} ${user.last_name}`;
    document.getElementById('user-email').textContent = user.email;
    document.getElementById('user-avatar').textContent = user.first_name[0].toUpperCase();
  } catch {}
  loadDashboard();
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const profile = await api.get('/rider/profile').catch(() => null);
    if (!profile) {
      document.getElementById('approval-banner').innerHTML = `
        <div class="alert alert-warning mb-md">
          ⚠️ Your rider profile is not set up. <a href="#" onclick="loadProfile(); navigate('page-profile')">Complete setup</a> to receive deliveries.
        </div>`;
      return;
    }

    if (!profile.is_approved) {
      document.getElementById('approval-banner').innerHTML = `
        <div class="alert alert-warning mb-md">
          ⏳ Your account is <strong>pending admin approval</strong>. You'll be able to take deliveries once approved.
        </div>`;
    }

    isOnline = profile.is_available;
    updateAvailabilityUI();

    document.getElementById('stat-deliveries').textContent = profile.total_deliveries;
    document.getElementById('stat-rating').textContent = Number(profile.rating).toFixed(1) + ' ★';
    document.getElementById('stat-status').textContent = profile.is_available ? 'Online' : 'Offline';

    const wallet = await api.get('/rider/wallet').catch(() => ({ balance: 0 }));
    document.getElementById('stat-balance').textContent = formatNGN(wallet.balance);

    // Active order
    const active = await api.get('/rider/orders/active').catch(() => ({ active_order: null }));
    if (active.active_order) {
      renderActiveAssignment(active.active_order);
      initRiderMap(active.active_order);
    }

    if (isOnline && profile.is_approved) {
      startLocationTracking();
    }
  } catch (err) {
    console.error('Dashboard load error:', err);
  }
}

function updateAvailabilityUI() {
  const btn = document.getElementById('availabilityBtn');
  if (isOnline) {
    btn.innerHTML = '<span class="online-indicator"></span> Online';
    btn.className = 'btn btn-sm btn-success';
  } else {
    btn.textContent = '⏵ Go Online';
    btn.className = 'btn btn-sm btn-ghost';
  }
  document.getElementById('stat-status').textContent = isOnline ? 'Online' : 'Offline';
}

async function toggleAvailability() {
  // Ensure profile exists before toggling availability
  try { await api.get('/rider/profile'); }
  catch {
    showToast('Set up your rider profile first.', 'warning');
    loadProfile();
    navigate('page-profile');
    return;
  }
  try {
    if (isOnline) {
      await api.post('/rider/offline');
      isOnline = false;
      if (locationInterval) { clearInterval(locationInterval); locationInterval = null; }
      showToast('You are now offline.', 'warning');
    } else {
      await api.post('/rider/online');
      isOnline = true;
      startLocationTracking();
      showToast('You are now online!', 'success');
    }
    updateAvailabilityUI();
  } catch (err) { showToast(err.message, 'error'); }
}

function renderActiveAssignment(order) {
  const el = document.getElementById('active-assignment');
  el.innerHTML = `
    <div class="delivery-card">
      <div class="text-sm" style="opacity:.85">Active Delivery</div>
      <div style="font-size:var(--text-xl);font-weight:700">${escapeHtml(order.reference)}</div>
      <div class="delivery-address">📍 ${escapeHtml(order.delivery_address)}</div>
      <div style="margin-top:8px;opacity:.85">${formatNGN(order.delivery_fee)} delivery fee</div>
      <div class="delivery-actions">
        ${order.status === 'rider_assigned' ? `
          <button class="btn btn-confirm" onclick="confirmPickup('${order.id}')">✓ Confirm Pickup</button>` : ''}
        ${order.status === 'picked_up' ? `
          <button class="btn btn-confirm" onclick="arrivedHub('${order.id}')">🏠 Arrived at Hub</button>` : ''}
        ${order.status === 'hub_verified' ? `
          <button class="btn btn-confirm" onclick="markInTransit('${order.id}')">🚀 Start Delivery</button>` : ''}
        ${order.status === 'in_transit' ? `
          <button class="btn btn-confirm" onclick="confirmDelivery('${order.id}')">✅ Confirm Delivery</button>` : ''}
      </div>
    </div>`;

  document.getElementById('live-map-card').classList.remove('hidden');
}

// ── Order Actions ─────────────────────────────────────────────────────────────
async function confirmPickup(id) {
  try {
    await api.post(`/rider/orders/${id}/pickup`);
    showToast('Pickup confirmed!', 'success');
    loadDashboard();
  } catch (err) { showToast(err.message, 'error'); }
}

async function arrivedHub(id) {
  try {
    await api.post(`/rider/orders/${id}/arrived-hub`);
    showToast('Arrived at hub. Wait for verification.', 'success');
    loadDashboard();
  } catch (err) { showToast(err.message, 'error'); }
}

async function markInTransit(id) {
  try {
    await api.post(`/rider/orders/${id}/in-transit`);
    showToast('Delivery started!', 'success');
    loadDashboard();
  } catch (err) { showToast(err.message, 'error'); }
}

async function confirmDelivery(id) {
  if (!confirm('Confirm delivery to customer?')) return;
  try {
    await api.post(`/rider/orders/${id}/deliver`);
    showToast('Delivery confirmed! Payment released to your wallet.', 'success');
    loadDashboard();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── GPS Tracking ──────────────────────────────────────────────────────────────
function startLocationTracking() {
  if (!navigator.geolocation) return;
  if (locationInterval) return;

  function sendLocation() {
    navigator.geolocation.getCurrentPosition(
      pos => {
        const { latitude, longitude } = pos.coords;
        api.post('/rider/location', { latitude, longitude }).catch(() => {});
        if (riderMarker) {
          riderMarker.setLatLng([latitude, longitude]);
        } else if (riderMap) {
          const icon = L.divIcon({ html: '🏍️', className: '', iconSize: [30, 30] });
          riderMarker = L.marker([latitude, longitude], { icon })
            .bindPopup('Your location').addTo(riderMap);
          riderMap.setView([latitude, longitude], 14);
        }
      },
      err => console.warn('GPS error:', err.message),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  sendLocation();
  locationInterval = setInterval(sendLocation, 15000);  // update every 15s
}

function initRiderMap(order) {
  const mapEl = document.getElementById('rider-map');
  if (!riderMap) {
    riderMap = L.map('rider-map').setView([6.5244, 3.3792], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(riderMap);
  }
  if (order.delivery_latitude && order.delivery_longitude) {
    const destIcon = L.divIcon({ html: '📍', className: '', iconSize: [30, 30] });
    L.marker([order.delivery_latitude, order.delivery_longitude], { icon: destIcon })
      .bindPopup('Delivery destination').addTo(riderMap);
    riderMap.setView([order.delivery_latitude, order.delivery_longitude], 14);
  }
}

// ── Current Order Detail ──────────────────────────────────────────────────────
async function loadCurrentOrder() {
  const el = document.getElementById('current-order-detail');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/rider/orders/active');
    const order = data.active_order;
    if (!order) {
      el.innerHTML = '<div class="empty-state"><div class="icon">🚗</div><h3>No active delivery</h3><p>Go online to receive assignments.</p></div>';
      return;
    }
    el.innerHTML = `
      <div class="card">
        <div class="flex justify-between mb-md">
          <strong class="text-lg">${escapeHtml(order.reference)}</strong>
          ${statusBadge(order.status)}
        </div>
        <div class="form-group">
          <div class="form-label">Delivery Address</div>
          <div>${escapeHtml(order.delivery_address)}</div>
        </div>
        ${order.delivery_notes ? `<div class="form-group"><div class="form-label">Notes</div><div>${escapeHtml(order.delivery_notes)}</div></div>` : ''}
        <div class="flex justify-between mt-md">
          <div><div class="form-label">Order Value</div><div class="font-bold">${formatNGN(order.total_amount)}</div></div>
          <div><div class="form-label">Your Fee</div><div class="font-bold" style="color:var(--color-success)">${formatNGN(order.delivery_fee)}</div></div>
        </div>
        <hr style="margin:16px 0;border-color:var(--color-border)" />
        <h4>Order Items</h4>
        ${(order.items || []).map(i => `
          <div class="flex justify-between mt-md text-sm">
            <span>${escapeHtml(i.product_name)} x${i.quantity}</span>
            <span>${formatNGN(i.subtotal)}</span>
          </div>`).join('')}
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  const list = document.getElementById('history-list');
  list.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/rider/orders?per_page=30');
    const orders = data.items || [];
    if (!orders.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">📋</div><h3>No deliveries yet</h3></div>';
      return;
    }
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = orders.map(o => `
      <div class="history-item">
        <div class="history-icon">${o.status === 'delivered' ? '✅' : '📦'}</div>
        <div style="flex:1">
          <div class="font-bold">${escapeHtml(o.reference)}</div>
          <div class="text-sm text-muted">${escapeHtml(o.delivery_address)}</div>
          <div class="text-sm text-muted">${formatDate(o.created_at)}</div>
        </div>
        <div style="text-align:right">
          ${statusBadge(o.status)}
          <div class="text-sm font-bold mt-md" style="color:var(--color-success)">${formatNGN(o.delivery_fee)}</div>
        </div>
      </div>`).join('');
    list.innerHTML = '';
    list.appendChild(card);
  } catch (err) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Wallet ────────────────────────────────────────────────────────────────────
async function loadWallet() {
  const el = document.getElementById('wallet-details');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const wallet = await api.get('/rider/wallet');
    el.innerHTML = `
      <div style="background:linear-gradient(135deg,var(--color-primary),var(--color-primary-dk));color:#fff;border-radius:var(--radius-xl);padding:var(--space-xl);margin-bottom:var(--space-xl)">
        <div style="font-size:var(--text-sm);opacity:.85">Total Earnings</div>
        <div style="font-size:40px;font-weight:900">₦${Number(wallet.balance).toLocaleString('en-NG',{minimumFractionDigits:2})}</div>
      </div>
      <div class="card mb-md">
        <h3 class="card-title mb-md">Request Payout</h3>
        <div class="flex gap-sm">
          <input type="number" id="payoutAmount" class="form-control" placeholder="Amount (₦)" min="100" style="flex:1" />
          <button class="btn btn-success" onclick="requestPayout()">Withdraw</button>
        </div>
        <p class="form-hint">Transferred to your registered bank account.</p>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function requestPayout() {
  const amount = parseFloat(document.getElementById('payoutAmount').value);
  if (!amount || amount < 100) { showToast('Minimum ₦100.', 'error'); return; }
  try {
    await api.post('/rider/payout', { amount });
    showToast('Payout initiated!', 'success');
    loadWallet();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Profile ───────────────────────────────────────────────────────────────────
async function loadProfile() {
  const el = document.getElementById('profile-details');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    let profile;
    try { profile = await api.get('/rider/profile'); } catch { profile = null; }

    if (!profile) {
      el.innerHTML = `
        <div class="card">
          <h3 class="card-title mb-md">Setup Rider Profile</h3>
          <form id="riderProfileForm">
            <div class="form-group"><label class="form-label">Vehicle Type</label>
              <select id="vType" class="form-control">
                <option value="motorcycle">Motorcycle</option>
                <option value="bicycle">Bicycle</option>
                <option value="car">Car</option>
                <option value="van">Van</option>
              </select>
            </div>
            <div class="form-group"><label class="form-label">Plate Number</label><input type="text" id="plate" class="form-control" /></div>
            <div class="form-group"><label class="form-label">Bank Account</label><input type="text" id="bankAcc" class="form-control" /></div>
            <div class="form-group"><label class="form-label">Bank Code</label><input type="text" id="bankCode" class="form-control" placeholder="e.g. 058" /></div>
            <div class="form-group"><label class="form-label">Bank Name</label><input type="text" id="bankName" class="form-control" /></div>
            <button type="submit" class="btn btn-primary">Save Profile</button>
          </form>
        </div>`;
      document.getElementById('riderProfileForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
          await api.post('/auth/rider/profile', {
            vehicle_type: document.getElementById('vType').value,
            plate_number: document.getElementById('plate').value.trim() || null,
            bank_account_number: document.getElementById('bankAcc').value.trim() || null,
            bank_code: document.getElementById('bankCode').value.trim() || null,
            bank_name: document.getElementById('bankName').value.trim() || null,
          });
          showToast('Profile created!', 'success');
          loadProfile();
        } catch (err) { showToast(err.message, 'error'); }
      });
      return;
    }

    el.innerHTML = `
      <div class="card">
        <div class="flex items-center gap-md mb-md">
          <div style="width:64px;height:64px;background:var(--color-primary);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;color:#fff">🏍️</div>
          <div>
            <div class="font-bold" style="font-size:var(--text-lg)" id="profile-name">—</div>
            <span class="badge ${profile.is_approved ? 'badge-paid' : 'badge-pending'}">${profile.is_approved ? 'Approved' : 'Pending Approval'}</span>
          </div>
        </div>
        <div class="stats-grid" style="grid-template-columns:1fr 1fr;gap:12px">
          <div class="stat-card"><div class="stat-value">${profile.total_deliveries}</div><div class="stat-label">Deliveries</div></div>
          <div class="stat-card"><div class="stat-value">${Number(profile.rating).toFixed(1)}★</div><div class="stat-label">Rating</div></div>
        </div>
        <hr style="margin:16px 0;border-color:var(--color-border)" />
        <div class="flex justify-between text-sm"><span class="text-muted">Vehicle</span><span class="font-bold">${profile.vehicle_type.toUpperCase()}</span></div>
        <div class="flex justify-between text-sm mt-md"><span class="text-muted">Plate</span><span>${escapeHtml(profile.plate_number || '—')}</span></div>
        <div class="flex justify-between text-sm mt-md"><span class="text-muted">Bank</span><span>${escapeHtml(profile.bank_name || '—')}</span></div>
      </div>`;
    try {
      const user = await api.get('/auth/me');
      document.getElementById('profile-name').textContent = `${user.first_name} ${user.last_name}`;
    } catch {}
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Navigation ────────────────────────────────────────────────────────────────
const _origNavigate = navigate;
window.navigate = function(pageId) {
  _origNavigate(pageId);
  const map = {
    'page-dashboard': 'Dashboard',
    'page-current': 'Current Order',
    'page-history': 'Delivery History',
    'page-wallet': 'Earnings',
    'page-profile': 'My Profile',
  };
  document.getElementById('topbar-title').textContent = map[pageId] || 'ADVAN Rider';
};
