/**
 * ADVAN Admin Console — Full Platform Oversight
 */

let currentPage = 'page-overview';

document.addEventListener('DOMContentLoaded', () => {
  if (authStore.isLoggedIn()) showApp();
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
  document.getElementById('hubForm').addEventListener('submit', handleCreateHub);
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
    if (data.role !== 'admin') {
      showAlert('#auth-alert', 'Admin accounts only.', 'error');
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

function logout() { authStore.clear(); location.reload(); }

async function showApp() {
  document.getElementById('auth-gate').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  try {
    const user = await api.get('/auth/me');
    document.getElementById('user-name').textContent = `${user.first_name} ${user.last_name}`;
    document.getElementById('user-email').textContent = user.email;
    document.getElementById('user-avatar').textContent = user.first_name[0].toUpperCase();
  } catch {}
  loadOverview();
}

function refreshCurrent() {
  const fns = {
    'page-overview': loadOverview,
    'page-users': loadUsers,
    'page-vendors': loadVendors,
    'page-riders': loadRiders,
    'page-orders': loadOrders,
    'page-payments': loadPayments,
    'page-hubs': loadHubs,
    'page-escrow': loadEscrow,
  };
  if (fns[currentPage]) fns[currentPage]();
}

// ── Overview ──────────────────────────────────────────────────────────────────
async function loadOverview() {
  try {
    const stats = await api.get('/admin/analytics');
    document.getElementById('overview-stats').innerHTML = `
      <div class="stat-card">
        <div class="stat-icon">👥</div>
        <div class="stat-value">${stats.total_users.toLocaleString()}</div>
        <div class="stat-label">Total Users</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-icon" style="background:rgba(37,99,235,.1)">📦</div>
        <div class="stat-value">${stats.total_orders.toLocaleString()}</div>
        <div class="stat-label">Total Orders</div>
      </div>
      <div class="stat-card green">
        <div class="stat-icon" style="background:rgba(22,163,74,.1)">✅</div>
        <div class="stat-value">${stats.delivered_orders.toLocaleString()}</div>
        <div class="stat-label">Delivered</div>
      </div>
      <div class="stat-card amber">
        <div class="stat-icon" style="background:rgba(217,119,6,.1)">⏳</div>
        <div class="stat-value">${stats.active_orders.toLocaleString()}</div>
        <div class="stat-label">Active Orders</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🏪</div>
        <div class="stat-value">${stats.total_vendors.toLocaleString()}</div>
        <div class="stat-label">Vendors</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🚴</div>
        <div class="stat-value">${stats.total_riders.toLocaleString()}</div>
        <div class="stat-label">Riders</div>
      </div>
      <div class="stat-card green" style="grid-column:span 2">
        <div class="stat-icon" style="background:rgba(22,163,74,.1)">💰</div>
        <div class="revenue-display">${formatNGN(stats.total_revenue_ngn)}</div>
        <div class="stat-label">Total Revenue Processed</div>
      </div>`;
    document.getElementById('last-refresh').textContent = 'Updated ' + new Date().toLocaleTimeString();

    // Recent orders
    const orders = await api.get('/admin/orders?per_page=5');
    document.getElementById('recent-orders').innerHTML = (orders.items || []).length
      ? `<div class="table-wrap"><table>
          <thead><tr><th>Reference</th><th>Status</th><th>Amount</th><th>Date</th></tr></thead>
          <tbody>${(orders.items || []).map(o => `<tr>
            <td><code style="font-size:12px">${escapeHtml(o.reference)}</code></td>
            <td>${statusBadge(o.status)}</td>
            <td>${formatNGN(o.total_amount)}</td>
            <td>${formatDate(o.created_at)}</td>
          </tr>`).join('')}</tbody>
        </table></div>`
      : '<div class="empty-state" style="padding:24px"><div class="icon">📦</div><h3>No orders</h3></div>';

    // Pending vendors
    const vendors = await api.get('/admin/vendors?approved=false&per_page=5');
    document.getElementById('pending-vendors').innerHTML = (vendors.items || []).length
      ? (vendors.items || []).map(v => `
          <div class="flex justify-between items-center" style="padding:12px 0;border-bottom:1px solid var(--color-border)">
            <div>
              <div class="font-bold">${escapeHtml(v.business_name)}</div>
              <div class="text-sm text-muted">${formatDate(v.created_at)}</div>
            </div>
            <button class="btn btn-success btn-sm" onclick="approveVendor('${v.id}')">Approve</button>
          </div>`).join('')
      : '<div class="empty-state" style="padding:24px"><div class="icon">✅</div><h3>All vendors approved</h3></div>';

    // Orders awaiting rider assignment (vendor_confirmed)
    const awaitingRider = await api.get('/admin/orders?status=vendor_confirmed&per_page=5').catch(() => ({ items: [] }));
    const awaitingEl = document.getElementById('awaiting-rider');
    if (awaitingEl) {
      awaitingEl.innerHTML = (awaitingRider.items || []).length
        ? (awaitingRider.items || []).map(o => `
            <div class="flex justify-between items-center" style="padding:12px 0;border-bottom:1px solid var(--color-border)">
              <div>
                <div style="font-family:var(--font-mono);font-size:var(--text-sm);font-weight:700">${escapeHtml(o.reference)}</div>
                <div class="text-sm text-muted">${formatNGN(o.total_amount)} · ${formatDate(o.created_at)}</div>
              </div>
              <div class="action-row">
                <button class="btn btn-ghost btn-sm" onclick="openTrackModal('${o.id}')">🔍 Track</button>
                <button class="btn btn-primary btn-sm" onclick="openAssignRiderModal('${o.id}','${escapeHtml(o.reference)}')">Assign Rider</button>
              </div>
            </div>`).join('')
        : '<div class="empty-state" style="padding:24px"><div class="icon">🚴</div><h3>No pending assignments</h3></div>';
    }
  } catch (err) {
    document.getElementById('overview-stats').innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Users ─────────────────────────────────────────────────────────────────────
async function loadUsers() {
  const el = document.getElementById('users-table');
  el.innerHTML = '<div class="spinner"></div>';
  const role = document.getElementById('user-role-filter')?.value || '';
  try {
    const data = await api.get(`/admin/users?per_page=30${role ? '&role=' + role : ''}`);
    const users = data.items || [];
    el.innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
            <tbody>${users.map(u => `<tr>
              <td>${escapeHtml(u.first_name)} ${escapeHtml(u.last_name)}</td>
              <td>${escapeHtml(u.email)}</td>
              <td>${escapeHtml(u.phone)}</td>
              <td><span class="user-role-chip role-${u.role}">${u.role}</span></td>
              <td><span class="badge ${u.is_active ? 'badge-paid' : 'badge-cancelled'}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
              <td>${formatDate(u.created_at)}</td>
              <td><div class="action-row">
                ${u.is_active
                  ? `<button class="btn btn-danger btn-sm" onclick="deactivateUser('${u.id}')">Deactivate</button>`
                  : `<button class="btn btn-success btn-sm" onclick="activateUser('${u.id}')">Activate</button>`}
              </div></td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function activateUser(id) {
  try { await api.patch(`/admin/users/${id}/activate`); showToast('User activated', 'success'); loadUsers(); }
  catch (err) { showToast(err.message, 'error'); }
}

async function deactivateUser(id) {
  if (!confirm('Deactivate this user?')) return;
  try { await api.patch(`/admin/users/${id}/deactivate`); showToast('User deactivated', 'warning'); loadUsers(); }
  catch (err) { showToast(err.message, 'error'); }
}

// ── Vendors ───────────────────────────────────────────────────────────────────
async function loadVendors() {
  const el = document.getElementById('vendors-table');
  el.innerHTML = '<div class="spinner"></div>';
  const approved = document.getElementById('vendor-filter')?.value;
  try {
    const url = `/admin/vendors?per_page=30${approved !== undefined && approved !== '' ? '&approved=' + approved : ''}`;
    const data = await api.get(url);
    const vendors = data.items || [];
    el.innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Business</th><th>Address</th><th>Bank</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
            <tbody>${vendors.map(v => `<tr>
              <td><strong>${escapeHtml(v.business_name)}</strong></td>
              <td>${escapeHtml(v.business_address)}</td>
              <td>${escapeHtml(v.bank_name || '—')}</td>
              <td><span class="badge ${v.is_approved ? 'badge-paid' : 'badge-pending'}">${v.is_approved ? 'Approved' : 'Pending'}</span></td>
              <td>${formatDate(v.created_at)}</td>
              <td><div class="action-row">
                ${!v.is_approved
                  ? `<button class="btn btn-success btn-sm" onclick="approveVendor('${v.id}')">Approve</button>`
                  : `<button class="btn btn-danger btn-sm" onclick="suspendVendor('${v.id}')">Suspend</button>`}
              </div></td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function approveVendor(id) {
  try { await api.post(`/admin/vendors/${id}/approve`); showToast('Vendor approved!', 'success'); loadVendors(); loadOverview(); }
  catch (err) { showToast(err.message, 'error'); }
}
async function suspendVendor(id) {
  if (!confirm('Suspend this vendor?')) return;
  try { await api.post(`/admin/vendors/${id}/suspend`); showToast('Vendor suspended', 'warning'); loadVendors(); }
  catch (err) { showToast(err.message, 'error'); }
}

// ── Riders ────────────────────────────────────────────────────────────────────
async function loadRiders() {
  const el = document.getElementById('riders-table');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/admin/riders?per_page=30');
    const riders = data.items || [];
    el.innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Rider ID</th><th>Vehicle</th><th>Plate</th><th>Rating</th><th>Deliveries</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>${riders.map(r => `<tr>
              <td><code style="font-size:11px">${r.user_id.toString().slice(0,8)}…</code></td>
              <td>${r.vehicle_type.toUpperCase()}</td>
              <td>${escapeHtml(r.plate_number || '—')}</td>
              <td>${Number(r.rating).toFixed(1)}★</td>
              <td>${r.total_deliveries}</td>
              <td>
                <span class="badge ${r.is_approved ? 'badge-paid' : 'badge-pending'}">${r.is_approved ? 'Approved' : 'Pending'}</span>
                <span class="badge ${r.is_available ? 'badge-in_transit' : 'badge-cancelled'}">${r.is_available ? 'Online' : 'Offline'}</span>
              </td>
              <td>${!r.is_approved ? `<button class="btn btn-success btn-sm" onclick="approveRider('${r.id}')">Approve</button>` : '—'}</td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function approveRider(id) {
  try { await api.post(`/admin/riders/${id}/approve`); showToast('Rider approved!', 'success'); loadRiders(); }
  catch (err) { showToast(err.message, 'error'); }
}

// ── Orders ────────────────────────────────────────────────────────────────────
async function loadOrders() {
  const el = document.getElementById('orders-table');
  el.innerHTML = '<div class="spinner"></div>';
  const status = document.getElementById('orders-status-filter')?.value || '';
  try {
    const data = await api.get(`/admin/orders?per_page=30${status ? '&status=' + status : ''}`);
    const orders = data.items || [];

    // Highlight VENDOR_CONFIRMED orders that need rider assignment
    const needsAssignment = orders.filter(o => o.status === 'vendor_confirmed');
    let alertHtml = '';
    if (needsAssignment.length) {
      alertHtml = `<div class="alert alert-warning" style="margin-bottom:var(--space-md)">
        <strong>${needsAssignment.length} order(s) awaiting rider assignment</strong> — vendor has accepted, assign a rider to proceed.
      </div>`;
    }

    el.innerHTML = alertHtml + `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Reference</th><th>Status</th><th>Amount</th><th>Address</th><th>Date</th><th>Actions</th></tr></thead>
            <tbody>${orders.map(o => `<tr${o.status === 'vendor_confirmed' ? ' style="background:rgba(232,74,28,.04)"' : ''}>
              <td><code style="font-family:var(--font-mono);font-size:12px">${escapeHtml(o.reference)}</code></td>
              <td>${statusBadge(o.status)}</td>
              <td>${formatNGN(o.total_amount)}</td>
              <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(o.delivery_address)}</td>
              <td>${formatDate(o.created_at)}</td>
              <td>
                <div class="action-row">
                  <button class="btn btn-ghost btn-sm" onclick="openTrackModal('${o.id}')">🔍 Track</button>
                  ${o.status === 'vendor_confirmed'
                    ? `<button class="btn btn-primary btn-sm" onclick="openAssignRiderModal('${o.id}','${escapeHtml(o.reference)}')">Assign Rider</button>`
                    : ''}
                </div>
              </td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Rider assignment map modal ────────────────────────────────────────────────
let _assignOrderId = null;
let _assignMap = null;
let _assignVendorMarker = null;
let _assignRiderMarkers = {};   // riderId -> L.marker
let _assignSelectedRiderId = null;
let _assignRiders = [];

// Haversine distance in km
function _haversine(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// Geocode an address via Nominatim (returns {lat, lng} or null)
async function _geocodeAddress(address) {
  try {
    const q = encodeURIComponent(address + ', Lagos, Nigeria');
    const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${q}`, {
      headers: { 'Accept-Language': 'en' }
    });
    const data = await res.json();
    if (data && data[0]) return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
  } catch {}
  return null;
}

function _assignSelectRider(riderId) {
  _assignSelectedRiderId = riderId;

  // Update list UI
  document.querySelectorAll('.assign-rider-item').forEach(el => {
    el.classList.toggle('selected', el.dataset.riderId === riderId);
    const dot = el.querySelector('.assign-rider-dot');
    if (dot) {
      if (el.dataset.riderId === riderId) {
        dot.className = 'assign-rider-dot dot-selected';
      } else {
        dot.className = 'assign-rider-dot ' + (el.dataset.hasGps === '1' ? 'dot-available' : 'dot-no-gps');
      }
    }
  });

  // Update map markers
  Object.entries(_assignRiderMarkers).forEach(([rid, marker]) => {
    const isSelected = rid === riderId;
    const icon = isSelected ? _riderIconSelected() : _riderIconAvailable();
    marker.setIcon(icon);
    if (isSelected) marker.openPopup();
  });

  document.getElementById('assignRiderBtn').disabled = false;
}

function _riderIconAvailable() {
  return L.divIcon({
    className: '',
    html: '<div style="width:24px;height:24px;border-radius:50%;background:#16A34A;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4)"></div>',
    iconSize: [24, 24], iconAnchor: [12, 12],
  });
}

function _riderIconSelected() {
  return L.divIcon({
    className: '',
    html: '<div style="width:28px;height:28px;border-radius:50%;background:#2563EB;border:3px solid #fff;box-shadow:0 2px 8px rgba(37,99,235,.6)"></div>',
    iconSize: [28, 28], iconAnchor: [14, 14],
  });
}

function _vendorIcon() {
  return L.divIcon({
    className: '',
    html: '<div style="width:28px;height:28px;border-radius:6px;background:#D97706;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-size:14px">🏪</div>',
    iconSize: [28, 28], iconAnchor: [14, 14],
  });
}

async function openAssignRiderModal(orderId, reference) {
  _assignOrderId = orderId;
  _assignSelectedRiderId = null;
  _assignRiders = [];
  _assignRiderMarkers = {};

  document.getElementById('assign-order-ref').textContent = reference;
  document.getElementById('assign-modal-alert').innerHTML = '';
  document.getElementById('assign-rider-list').innerHTML = '';
  document.getElementById('assign-map-status').textContent = 'Loading map data…';
  document.getElementById('assignRiderBtn').disabled = true;
  document.getElementById('assign-rider-modal').style.display = 'flex';

  // Init or reset map
  if (_assignMap) {
    _assignMap.remove();
    _assignMap = null;
  }

  // Wait two animation frames so the browser finishes layout after display:flex
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  // Compute height directly from viewport — flex child offsetHeight is unreliable before first paint
  const mapDiv = document.getElementById('assign-map');
  const shellH = Math.min(700, window.innerHeight - 32);
  mapDiv.style.height = shellH + 'px';
  mapDiv.style.width = '100%';

  _assignMap = L.map('assign-map', { preferCanvas: true }).setView([6.5244, 3.3792], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(_assignMap);
  _assignMap.invalidateSize();

  try {
    const data = await api.get(`/admin/orders/${orderId}/map-data`);
    _assignRiders = data.riders || [];

    // ── Vendor marker ────────────────────────────────────────────────────
    let vendorLatLng = null;
    const vendor = data.vendor;
    if (vendor) {
      if (vendor.latitude && vendor.longitude) {
        vendorLatLng = [vendor.latitude, vendor.longitude];
      } else {
        document.getElementById('assign-map-status').textContent = 'Locating vendor…';
        const geo = await _geocodeAddress(vendor.business_address);
        if (geo) vendorLatLng = [geo.lat, geo.lng];
      }
      if (vendorLatLng) {
        _assignVendorMarker = L.marker(vendorLatLng, { icon: _vendorIcon(), zIndexOffset: 1000 })
          .addTo(_assignMap)
          .bindPopup(`<strong>${escapeHtml(vendor.business_name)}</strong><br><small>${escapeHtml(vendor.business_address)}</small>`);
        _assignMap.setView(vendorLatLng, 13);
      }
    }

    // ── Rider markers + list ─────────────────────────────────────────────
    if (!_assignRiders.length) {
      document.getElementById('assign-map-status').textContent = 'No available riders — approve and set riders online first.';
      return;
    }

    const bounds = vendorLatLng ? [vendorLatLng] : [];

    // Calculate distances and sort by distance (GPS riders first)
    _assignRiders.forEach(r => {
      r._hasGps = r.current_latitude !== null && r.current_longitude !== null;
      r._distKm = (r._hasGps && vendorLatLng)
        ? _haversine(vendorLatLng[0], vendorLatLng[1], r.current_latitude, r.current_longitude)
        : null;
    });
    _assignRiders.sort((a, b) => {
      if (a._hasGps && !b._hasGps) return -1;
      if (!a._hasGps && b._hasGps) return 1;
      if (a._distKm !== null && b._distKm !== null) return a._distKm - b._distKm;
      return b.rating - a.rating;
    });

    // Add markers
    _assignRiders.forEach(r => {
      if (!r._hasGps) return;
      const ll = [r.current_latitude, r.current_longitude];
      bounds.push(ll);
      const distStr = r._distKm !== null ? `${r._distKm.toFixed(1)} km from vendor` : '';
      const marker = L.marker(ll, { icon: _riderIconAvailable() })
        .addTo(_assignMap)
        .bindPopup(`<strong>${escapeHtml(r.name)}</strong><br>${r.vehicle_type.toUpperCase()} · ${r.plate_number || 'No plate'}<br>${r.rating.toFixed(1)}★ · ${r.total_deliveries} deliveries${distStr ? '<br>' + distStr : ''}`)
        .on('click', () => _assignSelectRider(r.id));
      _assignRiderMarkers[r.id] = marker;
    });

    if (bounds.length > 1) {
      _assignMap.fitBounds(bounds, { padding: [40, 40] });
    }

    // Build sidebar list
    const listEl = document.getElementById('assign-rider-list');
    listEl.innerHTML = _assignRiders.map(r => {
      const distLabel = r._distKm !== null ? `${r._distKm.toFixed(1)} km away` : (r._hasGps ? 'Locating…' : 'No GPS signal');
      const dotClass = r._hasGps ? 'dot-available' : 'dot-no-gps';
      return `<div class="assign-rider-item${r._hasGps ? '' : ' no-gps'}" data-rider-id="${r.id}" data-has-gps="${r._hasGps ? '1' : '0'}" onclick="_assignSelectRider('${r.id}')">
        <div class="assign-rider-dot ${dotClass}"></div>
        <div style="min-width:0">
          <div class="assign-rider-name">${escapeHtml(r.name)}</div>
          <div class="assign-rider-meta">${r.vehicle_type.toUpperCase()} · ${escapeHtml(r.plate_number || 'No plate')} · ${r.rating.toFixed(1)}★ · ${r.total_deliveries} trips</div>
          <div class="assign-rider-dist">${distLabel}</div>
        </div>
      </div>`;
    }).join('');

    const gpsCount = _assignRiders.filter(r => r._hasGps).length;
    document.getElementById('assign-map-status').textContent =
      `${_assignRiders.length} rider${_assignRiders.length !== 1 ? 's' : ''} available · ${gpsCount} with live GPS`;

  } catch (err) {
    document.getElementById('assign-map-status').textContent = '';
    showAlert('#assign-modal-alert', err.message, 'error');
  }
}

function closeAssignRiderModal() {
  document.getElementById('assign-rider-modal').style.display = 'none';
  if (_assignMap) { _assignMap.remove(); _assignMap = null; }
  _assignOrderId = null;
  _assignSelectedRiderId = null;
  _assignRiders = [];
  _assignRiderMarkers = {};
}

async function confirmAssignRider() {
  if (!_assignSelectedRiderId) {
    showAlert('#assign-modal-alert', 'Please select a rider from the list or map.', 'error');
    return;
  }
  const btn = document.getElementById('assignRiderBtn');
  setLoading(btn, true);
  try {
    await api.post(`/admin/orders/${_assignOrderId}/assign-rider?rider_id=${_assignSelectedRiderId}`);
    closeAssignRiderModal();
    showToast('Rider assigned successfully! They have been notified.', 'success');
    loadOrders();
  } catch (err) {
    showAlert('#assign-modal-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

// ── Order live tracking ───────────────────────────────────────────────────────
let _trackMap = null;
let _trackPollInterval = null;
let _trackOrderId = null;
let _trackRiderMarker = null;
let _trackGeoCache = {};   // address -> {lat,lng}

const TRACK_STAGES = [
  { key: 'created',       label: 'Order Placed',       icon: '🛒', ts: 'created_at' },
  { key: 'paid',          label: 'Payment Confirmed',  icon: '💳', ts: null },
  { key: 'vendor',        label: 'Vendor Accepted',    icon: '🏪', ts: 'vendor_accepted_at', failTs: 'vendor_rejected_at', failLabel: 'Vendor Rejected' },
  { key: 'rider',         label: 'Rider Assigned',     icon: '🚴', ts: 'rider_assigned_at' },
  { key: 'picked_up',     label: 'Picked Up',          icon: '📦', ts: 'picked_up_at' },
  { key: 'hub',           label: 'At Agent Hub',       icon: '🏠', ts: 'hub_verified_at', pendingLabel: 'Awaiting Hub Scan' },
  { key: 'in_transit',    label: 'In Transit',         icon: '🚚', ts: 'in_transit_at' },
  { key: 'delivered',     label: 'Delivered',          icon: '✅', ts: 'delivered_at' },
];

const ACTIVE_STATUSES = new Set([
  'paid','vendor_confirmed','preparing','ready_for_pickup',
  'rider_assigned','picked_up','at_hub','hub_verified','in_transit'
]);

function _trackIcon(emoji, color, pulse = false) {
  return L.divIcon({
    className: '',
    html: `<div class="${pulse ? 'rider-live-dot' : ''}" style="width:30px;height:30px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;font-size:14px">${emoji}</div>`,
    iconSize: [30, 30], iconAnchor: [15, 15],
  });
}

async function _trackGeocode(address) {
  if (!address) return null;
  if (_trackGeoCache[address]) return _trackGeoCache[address];
  try {
    const q = encodeURIComponent(address + ', Lagos, Nigeria');
    const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${q}`, {
      headers: { 'Accept-Language': 'en' }
    });
    const data = await res.json();
    if (data && data[0]) {
      const result = { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
      _trackGeoCache[address] = result;
      return result;
    }
  } catch {}
  return null;
}

function _renderTrackTimeline(d) {
  const terminalFail = ['vendor_rejected','cancelled','disputed','refunded'].includes(d.status);
  let html = '';
  let passedActive = false;

  for (const stage of TRACK_STAGES) {
    const ts = stage.ts ? d[stage.ts] : null;
    const failTs = stage.failTs ? d[stage.failTs] : null;

    let state = 'pending';
    let label = stage.label;
    let timeStr = '';

    if (failTs) {
      state = 'failed';
      label = stage.failLabel || label;
      timeStr = formatDate(failTs);
    } else if (ts) {
      state = passedActive ? 'done' : 'done';
      timeStr = formatDate(ts);
      // Mark as active (current) if this is the latest completed stage and order not finished
      if (!passedActive && ACTIVE_STATUSES.has(d.status)) {
        // find if any later stage has a ts
        const laterIdx = TRACK_STAGES.indexOf(stage);
        const hasLater = TRACK_STAGES.slice(laterIdx + 1).some(s => s.ts && d[s.ts]);
        if (!hasLater) { state = 'active'; passedActive = true; }
      }
    } else if (d.status === 'delivered' || d.status === 'paid') {
      // special: paid has no ts field — infer from status
      if (stage.key === 'paid' && ['paid','vendor_confirmed','preparing','ready_for_pickup','rider_assigned','picked_up','at_hub','hub_verified','in_transit','delivered'].includes(d.status)) {
        state = 'done';
      }
    }

    // Active step for stages without explicit ts
    if (stage.key === 'paid' && state === 'pending' && ACTIVE_STATUSES.has(d.status)) state = 'done';

    html += `<li class="track-step ${state}">
      <div class="track-step-dot">${stage.icon}</div>
      <div>
        <div class="track-step-label">${label}</div>
        ${timeStr ? `<div class="track-step-time">${timeStr}</div>` : (state === 'active' ? '<div class="track-step-time" style="color:var(--color-primary)">In progress…</div>' : '')}
      </div>
    </li>`;

    if (failTs) break; // stop timeline at failure
  }
  return html;
}

function _renderTrackActors(d) {
  let html = '';
  if (d.customer) {
    html += `<div class="track-actor"><div class="track-actor-icon">👤</div><div>
      <div class="track-actor-name">${escapeHtml(d.customer.name)}</div>
      <div class="track-actor-sub">Customer · ${escapeHtml(d.customer.phone || '—')}</div>
    </div></div>`;
  }
  if (d.vendor) {
    html += `<div class="track-actor"><div class="track-actor-icon">🏪</div><div>
      <div class="track-actor-name">${escapeHtml(d.vendor.name)}</div>
      <div class="track-actor-sub">Vendor · ${escapeHtml(d.vendor.address || '—')}</div>
    </div></div>`;
  }
  if (d.rider) {
    html += `<div class="track-actor"><div class="track-actor-icon">🚴</div><div>
      <div class="track-actor-name">${escapeHtml(d.rider.name)}</div>
      <div class="track-actor-sub">${escapeHtml((d.rider.vehicle || '').toUpperCase())} · ${escapeHtml(d.rider.plate || 'No plate')} · ${escapeHtml(d.rider.phone || '—')}</div>
    </div></div>`;
  }
  if (d.hub) {
    html += `<div class="track-actor"><div class="track-actor-icon">🏠</div><div>
      <div class="track-actor-name">${escapeHtml(d.hub.name)}</div>
      <div class="track-actor-sub">Agent Hub · ${escapeHtml(d.hub.area || d.hub.address || '—')}</div>
    </div></div>`;
  }
  return html || '<div class="text-sm text-muted">No actor info yet</div>';
}

async function _buildTrackMap(d) {
  const bounds = [];

  // Vendor marker
  let vendorLL = null;
  if (d.vendor) {
    if (d.vendor.latitude && d.vendor.longitude) {
      vendorLL = [d.vendor.latitude, d.vendor.longitude];
    } else {
      const g = await _trackGeocode(d.vendor.address);
      if (g) vendorLL = [g.lat, g.lng];
    }
    if (vendorLL) {
      bounds.push(vendorLL);
      L.marker(vendorLL, { icon: _trackIcon('🏪', '#D97706'), zIndexOffset: 500 })
        .addTo(_trackMap)
        .bindPopup(`<strong>${escapeHtml(d.vendor.name)}</strong><br><small>Vendor · ${escapeHtml(d.vendor.address)}</small>`);
    }
  }

  // Hub marker
  if (d.hub && d.hub.latitude && d.hub.longitude) {
    const hubLL = [d.hub.latitude, d.hub.longitude];
    bounds.push(hubLL);
    L.marker(hubLL, { icon: _trackIcon('🏠', '#7C3AED'), zIndexOffset: 500 })
      .addTo(_trackMap)
      .bindPopup(`<strong>${escapeHtml(d.hub.name)}</strong><br><small>Agent Hub · ${escapeHtml(d.hub.address)}</small>`);
  }

  // Delivery destination marker
  let destLL = null;
  if (d.delivery_latitude && d.delivery_longitude) {
    destLL = [d.delivery_latitude, d.delivery_longitude];
  } else {
    const g = await _trackGeocode(d.delivery_address);
    if (g) destLL = [g.lat, g.lng];
  }
  if (destLL) {
    bounds.push(destLL);
    L.marker(destLL, { icon: _trackIcon('📍', '#16A34A'), zIndexOffset: 500 })
      .addTo(_trackMap)
      .bindPopup(`<strong>Delivery Address</strong><br><small>${escapeHtml(d.delivery_address)}</small>`);
  }

  // Rider marker (live)
  if (d.rider && d.rider.latitude && d.rider.longitude) {
    const rLL = [d.rider.latitude, d.rider.longitude];
    bounds.push(rLL);
    _trackRiderMarker = L.marker(rLL, { icon: _trackIcon('🚴', '#2563EB', true), zIndexOffset: 1000 })
      .addTo(_trackMap)
      .bindPopup(`<strong>${escapeHtml(d.rider.name)}</strong><br><small>Rider · Live location</small>`);
  }

  if (bounds.length > 1) {
    _trackMap.fitBounds(bounds, { padding: [50, 50] });
  } else if (bounds.length === 1) {
    _trackMap.setView(bounds[0], 14);
  } else {
    _trackMap.setView([6.5244, 3.3792], 12);
  }
}

function _updateTrackUI(d) {
  document.getElementById('track-ref').textContent = d.reference;
  document.getElementById('track-status-badge').innerHTML = statusBadge(d.status);
  document.getElementById('track-amount').textContent = formatNGN(d.total_amount);
  document.getElementById('track-timeline').innerHTML = _renderTrackTimeline(d);
  document.getElementById('track-actors').innerHTML = _renderTrackActors(d);
  document.getElementById('track-items').innerHTML = (d.items || []).map(i =>
    `<div class="track-item-row"><span>${escapeHtml(i.name)} ×${i.qty}</span><span>${formatNGN(i.subtotal)}</span></div>`
  ).join('') || '<div class="text-sm text-muted">No items</div>';
}

async function openTrackModal(orderId) {
  _trackOrderId = orderId;
  _trackRiderMarker = null;

  document.getElementById('track-modal').style.display = 'flex';
  document.getElementById('track-ref').textContent = 'Loading…';
  document.getElementById('track-status-badge').innerHTML = '';
  document.getElementById('track-amount').textContent = '';
  document.getElementById('track-timeline').innerHTML = '<div class="spinner" style="margin:8px 0"></div>';
  document.getElementById('track-actors').innerHTML = '';
  document.getElementById('track-items').innerHTML = '';
  document.getElementById('track-poll-status').textContent = '';

  // Init map
  if (_trackMap) { _trackMap.remove(); _trackMap = null; }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const mapDiv = document.getElementById('track-map');
  mapDiv.style.height = Math.min(700, window.innerHeight - 32) + 'px';
  mapDiv.style.width = '100%';
  _trackMap = L.map('track-map', { preferCanvas: true }).setView([6.5244, 3.3792], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(_trackMap);
  _trackMap.invalidateSize();

  try {
    const d = await api.get(`/admin/orders/${orderId}/live-track`);
    _updateTrackUI(d);
    await _buildTrackMap(d);

    const isLive = ACTIVE_STATUSES.has(d.status);
    if (isLive) {
      document.getElementById('track-poll-status').textContent = '● Live — refreshing every 5s';
      _trackPollInterval = setInterval(async () => {
        try {
          const fresh = await api.get(`/admin/orders/${_trackOrderId}/live-track`);
          _updateTrackUI(fresh);
          // Update rider marker if GPS changed
          if (fresh.rider && fresh.rider.latitude && fresh.rider.longitude) {
            const rLL = [fresh.rider.latitude, fresh.rider.longitude];
            if (_trackRiderMarker) {
              _trackRiderMarker.setLatLng(rLL);
            } else {
              _trackRiderMarker = L.marker(rLL, { icon: _trackIcon('🚴', '#2563EB', true), zIndexOffset: 1000 })
                .addTo(_trackMap)
                .bindPopup(`<strong>${escapeHtml(fresh.rider.name)}</strong><br><small>Rider · Live location</small>`);
            }
          }
          // Stop polling if order reached terminal state
          if (!ACTIVE_STATUSES.has(fresh.status)) {
            clearInterval(_trackPollInterval);
            _trackPollInterval = null;
            document.getElementById('track-poll-status').textContent = 'Order completed';
          }
        } catch {}
      }, 5000);
    } else {
      document.getElementById('track-poll-status').textContent = d.status === 'delivered' ? 'Delivered' : '';
    }
  } catch (err) {
    document.getElementById('track-timeline').innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function closeTrackModal() {
  document.getElementById('track-modal').style.display = 'none';
  if (_trackPollInterval) { clearInterval(_trackPollInterval); _trackPollInterval = null; }
  if (_trackMap) { _trackMap.remove(); _trackMap = null; }
  _trackOrderId = null;
  _trackRiderMarker = null;
}

// ── Payments ──────────────────────────────────────────────────────────────────
async function loadPayments() {
  const el = document.getElementById('payments-table');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/admin/payments?per_page=30');
    const payments = data.items || [];
    el.innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Reference</th><th>Amount</th><th>Status</th><th>Channel</th><th>Date</th></tr></thead>
            <tbody>${payments.map(p => `<tr>
              <td><code style="font-size:12px">${escapeHtml(p.reference)}</code></td>
              <td class="font-bold">${formatNGN(p.amount)}</td>
              <td><span class="badge ${p.status === 'paid' ? 'badge-paid' : p.status === 'pending' ? 'badge-pending' : 'badge-cancelled'}">${p.status}</span></td>
              <td>${escapeHtml(p.channel || '—')}</td>
              <td>${formatDate(p.created_at)}</td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Hubs ──────────────────────────────────────────────────────────────────────
async function loadHubs() {
  const el = document.getElementById('hubs-list');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const hubs = await api.get('/admin/hubs');
    if (!hubs.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">🏠</div><h3>No agent hubs created yet</h3></div>';
      return;
    }
    el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:var(--space-lg)">
      ${hubs.map(h => `
        <div class="hub-card">
          <div class="hub-card-header">
            <div>
              <div class="hub-name">${escapeHtml(h.name)}</div>
              <div class="hub-area">${escapeHtml(h.area || 'Lagos')}</div>
            </div>
            <span class="badge ${h.is_active ? 'badge-paid' : 'badge-cancelled'}">${h.is_active ? 'Active' : 'Inactive'}</span>
          </div>
          <div class="text-sm text-muted">${escapeHtml(h.address)}</div>
          ${h.phone ? `<div class="text-sm mt-md">📞 ${escapeHtml(h.phone)}</div>` : ''}
          ${h.latitude ? `<div class="text-sm mt-md">📍 ${h.latitude}, ${h.longitude}</div>` : ''}
          <div class="text-sm mt-md text-muted">Capacity: ${h.capacity} packages/day</div>
        </div>`).join('')}
    </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

let _hubMap = null;
let _hubMarker = null;

function openHubModal() {
  document.getElementById('hubLat').value = '';
  document.getElementById('hubLng').value = '';
  document.getElementById('hub-map-coords').textContent = 'No location selected';
  document.getElementById('hub-modal').classList.add('open');

  // Init map after modal is visible
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (_hubMap) { _hubMap.remove(); _hubMap = null; _hubMarker = null; }
    const mapDiv = document.getElementById('hub-map');
    mapDiv.style.height = '220px';
    _hubMap = L.map('hub-map').setView([6.5244, 3.3792], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(_hubMap);
    _hubMap.invalidateSize();

    _hubMap.on('click', function(e) {
      const { lat, lng } = e.latlng;
      document.getElementById('hubLat').value = lat.toFixed(7);
      document.getElementById('hubLng').value = lng.toFixed(7);
      document.getElementById('hub-map-coords').textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
      if (_hubMarker) {
        _hubMarker.setLatLng(e.latlng);
      } else {
        _hubMarker = L.marker(e.latlng, {
          icon: L.divIcon({
            className: '',
            html: '<div style="width:24px;height:24px;border-radius:50%;background:#D97706;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4)"></div>',
            iconSize: [24, 24], iconAnchor: [12, 12],
          })
        }).addTo(_hubMap);
      }
    });
  }));
}

function closeHubModal() {
  document.getElementById('hub-modal').classList.remove('open');
  if (_hubMap) { _hubMap.remove(); _hubMap = null; _hubMarker = null; }
}

async function handleCreateHub(e) {
  e.preventDefault();
  const btn = document.getElementById('hubSubmitBtn');
  setLoading(btn, true);
  try {
    await api.post('/admin/hubs', {
      name: document.getElementById('hubName').value.trim(),
      address: document.getElementById('hubAddress').value.trim(),
      area: document.getElementById('hubArea').value.trim() || null,
      phone: document.getElementById('hubPhone').value.trim() || null,
      latitude: parseFloat(document.getElementById('hubLat').value) || null,
      longitude: parseFloat(document.getElementById('hubLng').value) || null,
      capacity: parseInt(document.getElementById('hubCapacity').value) || 100,
    });
    closeHubModal();
    showToast('Agent hub created!', 'success');
    loadHubs();
  } catch (err) {
    showAlert('#hub-modal-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

// ── Escrow ────────────────────────────────────────────────────────────────────
async function loadEscrow() {
  const el = document.getElementById('escrow-table');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/admin/escrows?per_page=30');
    const escrows = data.items || [];
    el.innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Order ID</th><th>Total Held</th><th>Vendor</th><th>Rider</th><th>Platform</th><th>Status</th><th>Held At</th></tr></thead>
            <tbody>${escrows.map(e => `<tr>
              <td><code style="font-size:11px">${e.order_id.toString().slice(0,8)}…</code></td>
              <td class="font-bold">${formatNGN(e.total_held)}</td>
              <td>${e.vendor_amount != null ? formatNGN(e.vendor_amount) : '—'}</td>
              <td>${e.rider_amount != null ? formatNGN(e.rider_amount) : '—'}</td>
              <td>${e.platform_amount != null ? formatNGN(e.platform_amount) : '—'}</td>
              <td><span class="badge ${e.status === 'held' ? 'badge-pending' : e.status === 'released' ? 'badge-paid' : 'badge-cancelled'}">${e.status}</span></td>
              <td>${formatDate(e.held_at)}</td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Navigation ────────────────────────────────────────────────────────────────
const _origNavigate = navigate;
window.navigate = function(pageId) {
  currentPage = pageId;
  _origNavigate(pageId);
  const map = {
    'page-overview':  'Platform Overview',
    'page-users':     'All Users',
    'page-vendors':   'Vendor Management',
    'page-riders':    'Rider Management',
    'page-orders':    'All Orders',
    'page-payments':  'Payments',
    'page-hubs':      'Agent Hubs',
    'page-escrow':    'Escrow Monitor',
  };
  document.getElementById('topbar-title').textContent = map[pageId] || 'Admin';
};
