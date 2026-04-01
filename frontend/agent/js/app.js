/**
 * ADVAN Agent Hub Portal — Application Logic
 */

let currentOrderIdForMsg = null;
let _orderDetailMap = null;   // Leaflet map instance for the order detail modal
let _modalOrderId = null;     // currently open order's id

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
  document.getElementById('registerForm').addEventListener('submit', handleRegister);

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

  if (authStore.isLoggedIn()) showApp();
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
    if (!(data.roles || [data.role]).includes('agent')) {
      showAlert('#auth-alert', 'This portal is for hub agents only. Register as an agent first.', 'error');
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
      role: 'agent',
    });
    showAlert('#auth-alert', 'Account created! Sign in to continue.', 'success');
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('login-form').classList.remove('hidden');
    e.target.reset();
  } catch (err) {
    showAlert('#auth-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function logout() { authStore.clear(); location.reload(); }

async function showApp() {
  document.getElementById('auth-gate').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  try {
    const user = await api.get('/auth/me');
    document.getElementById('user-name').textContent = `${user.first_name} ${user.last_name}`;
    document.getElementById('user-avatar').textContent = user.first_name[0].toUpperCase();

    const hub = await api.get('/agent/hub').catch(() => null);
    if (hub) {
      document.getElementById('hub-name').textContent = hub.name;
    } else {
      // Agent registered but not yet assigned to a hub by admin
      document.getElementById('hub-name').textContent = 'Pending hub assignment';
      _showPendingHubBanner();
    }
  } catch {}
  loadDashboard();
}

function _showPendingHubBanner() {
  // Insert a prominent banner at the top of every page section
  const banner = `
    <div id="pending-hub-banner" class="alert alert-warning mb-md" style="margin:16px 16px 0">
      ⏳ <strong>Your account is pending hub assignment.</strong>
      An admin will assign you to a hub. You'll have full access once assigned.
    </div>`;
  document.querySelector('.main-content').insertAdjacentHTML('afterbegin', banner);
}

async function loadDashboard() {
  try {
    const allOrders = await api.get('/agent/orders?per_page=50');
    const orders = allOrders.items || [];
    const incoming   = orders.filter(o => o.status === 'at_hub').length;
    const pending    = orders.filter(o => o.status === 'at_hub').length;
    const verified   = orders.filter(o => o.status === 'hub_verified').length;
    const dispatched = orders.filter(o => ['in_transit','delivered'].includes(o.status)).length;
    document.getElementById('stat-incoming').textContent   = incoming;
    document.getElementById('stat-pending').textContent    = pending;
    document.getElementById('stat-verified').textContent   = verified;
    document.getElementById('stat-dispatched').textContent = dispatched;
    renderVerifyQueue(orders.filter(o => o.status === 'at_hub'), 'verify-queue-preview');
  } catch (err) {
    console.error('Dashboard error:', err);
  }
}

// ── Incoming ──────────────────────────────────────────────────────────────────
async function loadIncoming() {
  const el = document.getElementById('incoming-list');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/agent/orders?status=at_hub&per_page=50');
    const orders = data.items || [];
    if (!orders.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">📥</div><h3>No incoming packages</h3></div>';
      return;
    }
    el.innerHTML = orders.map(o => renderPackageCard(o)).join('');
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Verify Queue ──────────────────────────────────────────────────────────────
async function loadToVerify() {
  const el = document.getElementById('verify-list');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/agent/orders?status=at_hub&per_page=50');
    const orders = data.items || [];
    if (!orders.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">✅</div><h3>All packages verified!</h3></div>';
      return;
    }
    el.innerHTML = orders.map(o => renderPackageCard(o, true)).join('');
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Dispatch Queue (hub_verified orders — assign rider + map) ─────────────────
async function loadDispatchQueue() {
  const el = document.getElementById('dispatch-list');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/agent/orders?status=hub_verified&per_page=50');
    const orders = data.items || [];
    if (!orders.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">🗺️</div><h3>No orders awaiting dispatch</h3><p>All verified packages have been assigned riders.</p></div>';
      return;
    }
    el.innerHTML = orders.map(o => renderDispatchCard(o)).join('');
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Dispatched ────────────────────────────────────────────────────────────────
async function loadDispatched() {
  const el = document.getElementById('dispatched-list');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/agent/orders?status=in_transit&per_page=50');
    const orders = data.items || [];
    if (!orders.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">🚀</div><h3>None dispatched yet</h3></div>';
      return;
    }
    el.innerHTML = orders.map(o => renderPackageCard(o)).join('');
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Card renderers ────────────────────────────────────────────────────────────
function renderVerifyQueue(orders, containerId) {
  const el = document.getElementById(containerId);
  if (!orders.length) {
    el.innerHTML = '<div class="empty-state" style="padding:24px"><div class="icon">✅</div><h3>No packages awaiting verification</h3></div>';
    return;
  }
  el.innerHTML = orders.slice(0, 5).map(o => `
    <div class="package-card urgent">
      <div class="package-header">
        <span class="package-ref">${escapeHtml(o.reference)}</span>
        ${statusBadge(o.status)}
      </div>
      <div class="text-sm text-muted">${escapeHtml(o.delivery_address)}</div>
      <div class="text-sm mt-md">${formatNGN(o.total_amount)}</div>
      <div class="package-actions">
        <button class="btn btn-success btn-sm" onclick="verifyPackage('${o.id}')">✓ Verify & Package</button>
        <button class="btn btn-ghost btn-sm" onclick="showOrderDetail('${o.id}')">View Details</button>
      </div>
    </div>`).join('');
}

function renderPackageCard(order, showVerifyAction = false) {
  return `
    <div class="package-card ${showVerifyAction ? 'urgent' : order.status === 'hub_verified' ? 'verified' : ''}">
      <div class="package-header">
        <span class="package-ref">${escapeHtml(order.reference)}</span>
        ${statusBadge(order.status)}
      </div>
      <div>
        <div class="text-sm text-muted">Delivery to</div>
        <div class="text-sm font-bold">${escapeHtml(order.delivery_address)}</div>
      </div>
      <div class="flex justify-between mt-md">
        <div class="text-sm"><span class="text-muted">Order value: </span><strong>${formatNGN(order.total_amount)}</strong></div>
        <div class="text-sm text-muted">${formatDate(order.created_at)}</div>
      </div>
      <div class="package-actions">
        ${showVerifyAction && order.status === 'at_hub' ? `
          <button class="btn btn-success" onclick="verifyPackage('${order.id}')">✓ Verify & Package</button>` : ''}
        <button class="btn btn-ghost btn-sm" onclick="showOrderDetail('${order.id}')">View Details</button>
        <button class="btn btn-ghost btn-sm" onclick="sendMessageTo('${order.id}')">💬 Message</button>
      </div>
    </div>`;
}

function renderDispatchCard(order) {
  return `
    <div class="package-card verified">
      <div class="package-header">
        <span class="package-ref">${escapeHtml(order.reference)}</span>
        ${statusBadge(order.status)}
      </div>
      <div>
        <div class="text-sm text-muted">Delivery to</div>
        <div class="text-sm font-bold">${escapeHtml(order.delivery_address)}</div>
      </div>
      <div class="flex justify-between mt-md">
        <div class="text-sm"><span class="text-muted">Order value: </span><strong>${formatNGN(order.total_amount)}</strong></div>
        <div class="text-sm text-muted">${formatDate(order.created_at)}</div>
      </div>
      <div class="package-actions">
        <button class="btn btn-primary btn-sm" onclick="showOrderDetail('${order.id}', true)">🗺️ Map &amp; Assign Rider</button>
        <button class="btn btn-ghost btn-sm" onclick="sendMessageTo('${order.id}')">💬 Message</button>
      </div>
    </div>`;
}

// ── Verify ────────────────────────────────────────────────────────────────────
async function verifyPackage(orderId) {
  if (!confirm('Confirm that you have physically verified and packaged this order?')) return;
  try {
    await api.post(`/agent/orders/${orderId}/verify`);
    showToast('Order verified! Ready to assign a rider for delivery.', 'success');
    loadDashboard();
    loadToVerify();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Order Detail Modal with Leaflet Map ───────────────────────────────────────
async function showOrderDetail(orderId, showAssign = false) {
  _modalOrderId = orderId;

  const modal = document.getElementById('order-modal');
  modal.style.display = 'flex';

  // Reset content
  document.getElementById('modal-order-meta').innerHTML = '<div class="spinner"></div>';
  document.getElementById('modal-map-wrap').classList.add('hidden');
  document.getElementById('modal-no-map').classList.add('hidden');
  document.getElementById('modal-order-items').innerHTML = '';
  document.getElementById('modal-rider-section').classList.add('hidden');
  document.getElementById('modal-rider-alert').innerHTML = '';

  // Destroy stale map
  if (_orderDetailMap) { _orderDetailMap.remove(); _orderDetailMap = null; }

  try {
    const order = await api.get(`/agent/orders/${orderId}`);
    document.getElementById('modal-order-ref').textContent = order.reference;

    // Meta
    document.getElementById('modal-order-meta').innerHTML = `
      <div class="flex gap-md" style="flex-wrap:wrap;margin-bottom:12px">
        <div><div class="form-label">Status</div>${statusBadge(order.status)}</div>
        <div><div class="form-label">Total</div><strong>${formatNGN(order.total_amount)}</strong></div>
        <div><div class="form-label">Delivery Fee</div><strong>${formatNGN(order.delivery_fee)}</strong></div>
        <div><div class="form-label">Placed</div><span class="text-sm">${formatDate(order.created_at)}</span></div>
      </div>
      <div class="form-group">
        <div class="form-label">Delivery Address</div>
        <div>${escapeHtml(order.delivery_address)}</div>
      </div>
      ${order.delivery_notes ? `<div class="form-group"><div class="form-label">Notes</div><div class="text-sm">${escapeHtml(order.delivery_notes)}</div></div>` : ''}`;

    // Map
    if (order.delivery_latitude && order.delivery_longitude) {
      document.getElementById('modal-map-wrap').classList.remove('hidden');
      // Use setTimeout so the div is visible before Leaflet measures it
      setTimeout(() => _renderOrderMap(order.delivery_latitude, order.delivery_longitude, order.delivery_address), 50);
    } else {
      document.getElementById('modal-no-map').classList.remove('hidden');
    }

    // Items
    const items = order.items || [];
    if (items.length) {
      document.getElementById('modal-order-items').innerHTML = `
        <div class="form-label" style="margin-bottom:8px">Order Items</div>
        <div class="card" style="padding:12px">
          ${items.map(i => `
            <div class="flex justify-between text-sm" style="padding:6px 0;border-bottom:1px solid var(--color-border)">
              <span>${escapeHtml(i.product_name)} <span class="text-muted">x${i.quantity}</span></span>
              <strong>${formatNGN(i.subtotal)}</strong>
            </div>`).join('')}
        </div>`;
    }

    // Rider assignment (hub_verified only)
    if (order.status === 'hub_verified' || showAssign) {
      document.getElementById('modal-rider-section').classList.remove('hidden');
      await _loadAvailableRiders();
    }

  } catch (err) {
    document.getElementById('modal-order-meta').innerHTML =
      `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function _renderOrderMap(lat, lng, address) {
  _orderDetailMap = L.map('order-detail-map').setView([lat, lng], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
  }).addTo(_orderDetailMap);

  const icon = L.divIcon({
    html: '<div style="font-size:28px;line-height:1">📍</div>',
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 30],
  });
  L.marker([lat, lng], { icon })
    .bindPopup(`<strong>Delivery Location</strong><br>${escapeHtml(address)}`)
    .openPopup()
    .addTo(_orderDetailMap);
}

async function _loadAvailableRiders() {
  const sel = document.getElementById('riderSelect');
  sel.innerHTML = '<option value="">Loading riders…</option>';
  document.getElementById('assignRiderBtn').disabled = true;
  try {
    const riders = await api.get('/agent/riders');
    if (!riders.length) {
      sel.innerHTML = '<option value="">No available riders right now</option>';
      return;
    }
    sel.innerHTML = '<option value="">— Select a rider —</option>' +
      riders.map(r =>
        `<option value="${r.id}">${escapeHtml(r.name)} · ${r.vehicle_type} · ${escapeHtml(r.plate_number)} · ⭐${Number(r.rating).toFixed(1)}</option>`
      ).join('');
    document.getElementById('assignRiderBtn').disabled = false;
  } catch (err) {
    sel.innerHTML = '<option value="">Error loading riders</option>';
    showAlert('#modal-rider-alert', err.message, 'error');
  }
}

async function doAssignRider() {
  const riderId = document.getElementById('riderSelect').value;
  if (!riderId) { showAlert('#modal-rider-alert', 'Please select a rider first.', 'error'); return; }
  if (!_modalOrderId) return;

  const btn = document.getElementById('assignRiderBtn');
  setLoading(btn, true);
  try {
    await api.post(`/agent/orders/${_modalOrderId}/assign-rider?rider_id=${riderId}`);
    showToast('Rider assigned! They will be notified to collect the package.', 'success');
    closeOrderModal();
    loadDispatchQueue();
    loadDashboard();
  } catch (err) {
    showAlert('#modal-rider-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function closeOrderModal() {
  document.getElementById('order-modal').style.display = 'none';
  if (_orderDetailMap) { _orderDetailMap.remove(); _orderDetailMap = null; }
  _modalOrderId = null;
}

// ── Messages ──────────────────────────────────────────────────────────────────
function sendMessageTo(orderId) {
  currentOrderIdForMsg = orderId;
  document.getElementById('msgOrderId').value = orderId;
  navigate('page-messages');
  loadOrderMessages();
}

async function loadOrderMessages() {
  const orderId = document.getElementById('msgOrderId').value.trim();
  if (!orderId) return;
  currentOrderIdForMsg = orderId;
  const container = document.getElementById('messages-container');
  container.innerHTML = '<div class="spinner"></div>';
  try {
    const msgs = await api.get(`/agent/messages/${orderId}`);
    if (!msgs.length) {
      container.innerHTML = '<div class="text-muted text-sm" style="padding:16px">No messages yet.</div>';
    } else {
      const myId = authStore.getUserId();
      container.innerHTML = msgs.map(m => `
        <div class="message-bubble ${m.sender_id === myId ? 'message-sent' : 'message-received'}">
          ${escapeHtml(m.content)}
          <div style="font-size:10px;opacity:.7;margin-top:4px">${formatDate(m.created_at)}</div>
        </div>`).join('');
    }
    document.getElementById('message-compose').classList.remove('hidden');
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function sendMessage() {
  const content = document.getElementById('msgContent').value.trim();
  if (!content || !currentOrderIdForMsg) return;
  try {
    await api.post('/agent/messages', { order_id: currentOrderIdForMsg, content });
    document.getElementById('msgContent').value = '';
    loadOrderMessages();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Navigation ────────────────────────────────────────────────────────────────
const _origNavigate = navigate;
window.navigate = function(pageId) {
  _origNavigate(pageId);
  const map = {
    'page-dashboard':  'Hub Dashboard',
    'page-incoming':   'Incoming Packages',
    'page-verify':     'Verify Queue',
    'page-dispatch':   'Dispatch Queue',
    'page-dispatched': 'Dispatched',
    'page-messages':   'Messages',
  };
  document.getElementById('topbar-title').textContent = map[pageId] || 'ADVAN Hub';
};

// Close modal on backdrop click
document.addEventListener('click', e => {
  if (e.target === document.getElementById('order-modal')) closeOrderModal();
});
