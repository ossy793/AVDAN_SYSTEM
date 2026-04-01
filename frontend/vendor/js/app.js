/**
 * ADVAN Vendor Dashboard — Application Logic
 */

let editingProductId = null;
let vendorProfile = null;
let _newOrderPollId = null;
let _lastKnownPaidCount = -1; // track new PAID orders for badge notifications
let _productImageUrl = null;  // holds the current/uploaded image URL for the open modal

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (authStore.isLoggedIn()) {
    showApp();
  }
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
  document.getElementById('registerForm').addEventListener('submit', handleRegister);
  document.getElementById('showRegister').addEventListener('click', e => {
    e.preventDefault();
    document.getElementById('login-form').classList.add('hidden');
    document.getElementById('register-form').classList.remove('hidden');
  });
  document.getElementById('showLogin').addEventListener('click', e => {
    e.preventDefault();
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('login-form').classList.remove('hidden');
  });
  document.getElementById('profileForm').addEventListener('submit', handleProfileSetup);
  document.getElementById('productForm').addEventListener('submit', handleProductSave);
  document.getElementById('prodImageFile').addEventListener('change', handleImagePick);
});

// ── Auth ──────────────────────────────────────────────────────────────────────
async function handleLogin(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  setLoading(btn, true);
  try {
    const data = await api.post('/auth/login', {
      email: document.getElementById('loginEmail').value.trim(),
      password: document.getElementById('loginPassword').value,
    });
    if (!(data.roles || [data.role]).includes('vendor')) {
      showAlert('#auth-alert', 'This portal is for vendors only. Register as a vendor first.', 'error');
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
      role: 'vendor',
    });
    showAlert('#auth-alert', 'Account created! Please sign in.', 'success');
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('login-form').classList.remove('hidden');
  } catch (err) {
    showAlert('#auth-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function logout() { authStore.clear(); location.reload(); }

async function showApp() {
  document.getElementById('auth-gate').classList.add('hidden');
  try {
    const user = await api.get('/auth/me');

    // Guard: user must have vendor role (primary or extra)
    if (!(user.roles || [user.role]).includes('vendor')) {
      authStore.clear();
      document.getElementById('auth-gate').classList.remove('hidden');
      showAlert('#auth-alert', 'This portal is for vendors only. Register as a vendor first.', 'error');
      return;
    }

    document.getElementById('user-name').textContent = `${user.first_name} ${user.last_name}`;
    document.getElementById('user-email').textContent = user.email;
    document.getElementById('user-avatar').textContent = user.first_name[0].toUpperCase();

    // Check if profile exists
    try {
      vendorProfile = await api.get('/vendor/profile');
      document.getElementById('app').classList.remove('hidden');
      loadOverview();
      _startNewOrderPolling();
    } catch {
      document.getElementById('profile-setup').classList.remove('hidden');
    }
  } catch {
    authStore.clear();
    location.reload();
  }
}

async function handleProfileSetup(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  setLoading(btn, true);
  try {
    await api.post('/auth/vendor/profile', {
      business_name: document.getElementById('bizName').value.trim(),
      business_address: document.getElementById('bizAddress').value.trim(),
      business_type: document.getElementById('bizType').value.trim(),
      bank_account_number: document.getElementById('bankAcc').value.trim() || null,
      bank_code: document.getElementById('bankCode').value.trim() || null,
      bank_name: document.getElementById('bankName').value.trim() || null,
    });
    document.getElementById('profile-setup').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    loadOverview();
  } catch (err) {
    showAlert('#setup-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

// ── Overview ──────────────────────────────────────────────────────────────────
async function loadOverview() {
  try {
    if (!vendorProfile) vendorProfile = await api.get('/vendor/profile');
    if (!vendorProfile.is_approved) {
      document.getElementById('approval-alert').innerHTML = `
        <div class="alert alert-warning">
          ⏳ Your vendor account is <strong>pending admin approval</strong>. You can set up products, but orders won't be routed until approved.
        </div>`;
    }
    // Stats
    const wallet = await api.get('/vendor/wallet').catch(() => ({ balance: 0 }));
    const orders = await api.get('/vendor/orders?per_page=5').catch(() => ({ items: [], total: 0 }));

    document.getElementById('stat-total-orders').textContent = vendorProfile.total_orders;
    document.getElementById('stat-balance').textContent = formatNGN(wallet.balance);

    let active = 0, delivered = 0;
    (orders.items || []).forEach(o => {
      if (o.status === 'delivered') delivered++;
      else if (!['cancelled','refunded','pending'].includes(o.status)) active++;
    });
    document.getElementById('stat-delivered').textContent = delivered;
    document.getElementById('stat-pending').textContent = active;

    // Recent orders
    const recentEl = document.getElementById('recent-orders-list');
    if (orders.items.length) {
      recentEl.innerHTML = orders.items.map(o => renderOrderRow(o, true)).join('');
    } else {
      recentEl.innerHTML = '<div class="empty-state"><div class="icon">📦</div><h3>No orders yet</h3></div>';
    }

    // Store toggle button
    const toggleBtn = document.getElementById('storeToggleBtn');
    if (vendorProfile.is_open) {
      toggleBtn.textContent = '⏸ Close Store';
      toggleBtn.className = 'btn btn-ghost btn-sm';
    } else {
      toggleBtn.textContent = '▶ Open Store';
      toggleBtn.className = 'btn btn-success btn-sm';
    }
  } catch (err) {
    console.error('Overview load error:', err);
  }
}

async function toggleStore() {
  try {
    vendorProfile = await api.patch('/vendor/profile', { is_open: !vendorProfile.is_open });
    loadOverview();
    showToast(vendorProfile.is_open ? 'Store is now open!' : 'Store is closed.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Orders ────────────────────────────────────────────────────────────────────
async function loadOrders() {
  const list = document.getElementById('orders-list');
  list.innerHTML = '<div class="spinner"></div>';
  const statusFilter = document.getElementById('order-status-filter')?.value || '';
  try {
    const url = `/vendor/orders?per_page=30${statusFilter ? '&status=' + statusFilter : ''}`;
    const data = await api.get(url);
    const orders = data.items || [];
    if (!orders.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">📦</div><h3>No orders found</h3></div>';
      return;
    }
    list.innerHTML = orders.map(o => renderOrderRow(o)).join('');
  } catch (err) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function renderOrderRow(order, compact = false) {
  const actions = [];
  const isNew = order.status === 'paid';

  if (isNew) {
    actions.push(`<button class="btn btn-success btn-sm" onclick="confirmOrder('${order.id}')">✓ Accept</button>`);
    actions.push(`<button class="btn btn-danger btn-sm" onclick="rejectOrder('${order.id}')">✕ Reject</button>`);
  }
  if (order.status === 'vendor_confirmed') {
    actions.push(`<button class="btn btn-primary btn-sm" onclick="markPreparing('${order.id}')">Start Preparing</button>`);
  }
  if (order.status === 'preparing') {
    actions.push(`<button class="btn btn-primary btn-sm" onclick="markReady('${order.id}')">Mark Ready for Pickup</button>`);
  }

  return `
    <div class="order-row${isNew ? ' order-row-new' : ''}">
      <div class="flex justify-between" style="flex-wrap:wrap;gap:8px">
        <div>
          ${isNew ? '<span class="badge badge-paid" style="font-size:10px;margin-right:4px">NEW</span>' : ''}
          <span class="order-reference" style="font-family:var(--font-mono);font-size:var(--text-sm);font-weight:700;background:var(--color-bg);padding:4px 10px;border-radius:var(--radius-md)">${escapeHtml(order.reference)}</span>
          ${statusBadge(order.status)}
        </div>
        <div style="text-align:right">
          <div class="font-bold" style="color:var(--color-primary)">${formatNGN(order.total_amount)}</div>
          <div class="text-sm text-muted">${formatDate(order.created_at)}</div>
        </div>
      </div>
      ${compact ? '' : `
        <div class="text-sm text-muted mt-md">${escapeHtml(order.delivery_address)}</div>
        <div class="order-actions">${actions.join('')}</div>
      `}
    </div>`;
}

async function confirmOrder(id) {
  try {
    await api.post(`/vendor/orders/${id}/confirm`);
    showToast('Order accepted! Admin will assign a rider.', 'success');
    loadOrders();
  } catch (err) { showToast(err.message, 'error'); }
}

async function rejectOrder(id) {
  const reason = prompt('Reason for rejecting this order (required):');
  if (reason === null) return; // cancelled prompt
  if (!reason.trim() || reason.trim().length < 5) {
    showToast('Please enter a reason (at least 5 characters).', 'error');
    return;
  }
  if (!confirm(`Reject this order? The customer will be refunded.\n\nReason: "${reason}"`)) return;
  try {
    await api.post(`/vendor/orders/${id}/reject`, { reason: reason.trim() });
    showToast('Order rejected. Customer will be refunded.', 'warning');
    loadOrders();
  } catch (err) { showToast(err.message, 'error'); }
}

async function markPreparing(id) {
  try {
    await api.post(`/vendor/orders/${id}/prepare`);
    showToast('Order marked as preparing.', 'success');
    loadOrders();
  } catch (err) { showToast(err.message, 'error'); }
}

async function markReady(id) {
  try {
    await api.post(`/vendor/orders/${id}/ready`);
    showToast('Order ready for pickup!', 'success');
    loadOrders();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── New-order polling (checks every 30s for incoming PAID orders) ─────────────
function _startNewOrderPolling() {
  if (_newOrderPollId) return; // already running
  _newOrderPollId = setInterval(_checkNewOrders, 30000);
}

async function _checkNewOrders() {
  try {
    const data = await api.get('/vendor/orders?status=paid&per_page=50');
    const count = (data.items || []).length;
    const badge = document.getElementById('new-order-badge');
    if (badge) {
      if (count > 0) {
        badge.textContent = count;
        badge.classList.remove('hidden');
        if (_lastKnownPaidCount >= 0 && count > _lastKnownPaidCount) {
          showToast(`🔔 ${count - _lastKnownPaidCount} new order(s) waiting for your response!`, 'info');
        }
      } else {
        badge.classList.add('hidden');
      }
    }
    _lastKnownPaidCount = count;
  } catch {}
}

// ── Products ──────────────────────────────────────────────────────────────────
async function loadProducts() {
  const list = document.getElementById('products-list');
  list.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/vendor/products');
    const products = data.items || [];
    if (!products.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">🏪</div><h3>No products yet</h3><p>Add your first product to get started</p></div>';
      return;
    }
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = products.map(p => `
      <div class="product-row">
        <div class="product-row-img">
          ${p.image_url ? `<img src="${escapeHtml(p.image_url)}" alt="" />` : '📦'}
        </div>
        <div style="flex:1">
          <div class="product-row-name">${escapeHtml(p.name)}</div>
          <div class="product-row-category">${p.category}</div>
          <div class="product-row-price">${formatNGN(p.price)}</div>
        </div>
        <div>
          <span class="badge ${p.is_available && p.stock_quantity > 0 ? 'badge-paid' : 'badge-cancelled'}">
            ${p.is_available && p.stock_quantity > 0 ? 'Available' : 'Unavailable'}
          </span>
          <div class="text-sm text-muted">${p.stock_quantity} in stock</div>
        </div>
        <div class="product-row-actions">
          <button class="btn btn-ghost btn-sm" onclick="openProductModal('${p.id}', ${p.image_url ? `'${escapeHtml(p.image_url)}'` : 'null'})">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteProduct('${p.id}')">Delete</button>
        </div>
      </div>`).join('');
    list.innerHTML = '';
    list.appendChild(card);
  } catch (err) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function _setImagePreview(url) {
  const wrap = document.getElementById('prod-image-preview-wrap');
  const img  = document.getElementById('prod-image-preview');
  if (url) {
    // Prepend backend base for /uploads/... paths
    const backendBase = window.API_BASE_URL
      ? window.API_BASE_URL.replace('/api', '')
      : (location.hostname === 'localhost' || location.hostname === '127.0.0.1'
          ? 'http://127.0.0.1:8000'
          : 'https://avdan-system.onrender.com');
    img.src = url.startsWith('http') ? url : `${backendBase}${url}`;
    wrap.style.display = 'block';
  } else {
    img.src = '';
    wrap.style.display = 'none';
  }
}

function handleImagePick(e) {
  const file = e.target.files[0];
  if (!file) return;
  // Show local preview instantly (before upload)
  const reader = new FileReader();
  reader.onload = ev => _setImagePreview(ev.target.result);
  reader.readAsDataURL(file);
  // Clear previous saved URL — will be replaced on save
  _productImageUrl = null;
}

function openProductModal(productId = null, existingImageUrl = null) {
  editingProductId = productId;
  _productImageUrl = existingImageUrl || null;
  document.getElementById('product-modal-title').textContent = productId ? 'Edit Product' : 'Add Product';
  document.getElementById('product-modal').classList.add('open');
  if (!productId) {
    document.getElementById('productForm').reset();
    _productImageUrl = null;
    _setImagePreview(null);
  } else {
    // Show the existing image for edits
    document.getElementById('prodImageFile').value = '';
    _setImagePreview(existingImageUrl);
  }
}

function closeProductModal() {
  editingProductId = null;
  _productImageUrl = null;
  document.getElementById('product-modal').classList.remove('open');
}

async function handleProductSave(e) {
  e.preventDefault();
  const btn = document.getElementById('productSubmitBtn');
  setLoading(btn, true);
  try {
    // Upload new image file if one was selected
    const fileInput = document.getElementById('prodImageFile');
    if (fileInput.files[0]) {
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      const result = await api.uploadFile('/upload/image', formData);
      _productImageUrl = result.url;
    }

    const payload = {
      name:           document.getElementById('prodName').value.trim(),
      description:    document.getElementById('prodDesc').value.trim() || null,
      category:       document.getElementById('prodCategory').value,
      price:          parseFloat(document.getElementById('prodPrice').value),
      stock_quantity: parseInt(document.getElementById('prodStock').value),
      image_url:      _productImageUrl || null,
    };

    if (editingProductId) {
      await api.patch(`/vendor/products/${editingProductId}`, payload);
      showToast('Product updated!', 'success');
    } else {
      await api.post('/vendor/products', payload);
      showToast('Product added!', 'success');
    }
    closeProductModal();
    loadProducts();
  } catch (err) {
    showAlert('#product-modal-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

async function deleteProduct(id) {
  if (!confirm('Delete this product?')) return;
  try {
    await api.delete(`/vendor/products/${id}`);
    showToast('Product deleted.', 'warning');
    loadProducts();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Profile ───────────────────────────────────────────────────────────────────
async function loadProfile() {
  const el = document.getElementById('profile-details');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const p = await api.get('/vendor/profile');
    vendorProfile = p;
    el.innerHTML = `
      <div class="card">
        <div class="card-header"><span class="card-title">Business Information</span></div>
        <form id="updateProfileForm">
          <div class="form-group"><label class="form-label">Business Name</label><input type="text" id="upBizName" class="form-control" value="${escapeHtml(p.business_name)}" required /></div>
          <div class="form-group"><label class="form-label">Business Address</label><textarea id="upBizAddr" class="form-control" rows="2">${escapeHtml(p.business_address)}</textarea></div>
          <div class="form-group"><label class="form-label">Description</label><textarea id="upBizDesc" class="form-control" rows="2">${escapeHtml(p.description || '')}</textarea></div>
          <div class="flex gap-sm">
            <div class="form-group" style="flex:1"><label class="form-label">Bank Account</label><input type="text" id="upBank" class="form-control" value="${escapeHtml(p.bank_account_number || '')}" /></div>
            <div class="form-group" style="flex:1"><label class="form-label">Bank Code</label><input type="text" id="upBankCode" class="form-control" value="${escapeHtml(p.bank_code || '')}" /></div>
          </div>
          <div class="form-group"><label class="form-label">Bank Name</label><input type="text" id="upBankName" class="form-control" value="${escapeHtml(p.bank_name || '')}" /></div>
          <button type="submit" class="btn btn-primary">Save Changes</button>
        </form>
      </div>`;
    document.getElementById('updateProfileForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await api.patch('/vendor/profile', {
          business_name: document.getElementById('upBizName').value.trim(),
          business_address: document.getElementById('upBizAddr').value.trim(),
          description: document.getElementById('upBizDesc').value.trim(),
          bank_account_number: document.getElementById('upBank').value.trim() || null,
          bank_code: document.getElementById('upBankCode').value.trim() || null,
          bank_name: document.getElementById('upBankName').value.trim() || null,
        });
        showToast('Profile updated!', 'success');
      } catch (err) { showToast(err.message, 'error'); }
    });
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Wallet ────────────────────────────────────────────────────────────────────
async function loadWallet() {
  const el = document.getElementById('wallet-details');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const wallet = await api.get('/vendor/wallet');
    const txData = await api.get('/vendor/wallet/transactions');
    el.innerHTML = `
      <div style="background:linear-gradient(135deg,var(--color-primary),var(--color-primary-dk));color:#fff;border-radius:var(--radius-xl);padding:var(--space-xl);margin-bottom:var(--space-xl)">
        <div style="font-size:var(--text-sm);opacity:.85">Available Balance</div>
        <div style="font-size:40px;font-weight:900">₦${Number(wallet.balance).toLocaleString('en-NG',{minimumFractionDigits:2})}</div>
      </div>
      <div class="card mb-md">
        <h3 class="card-title mb-md">Request Payout</h3>
        <div class="flex gap-sm">
          <input type="number" id="payoutAmount" class="form-control" placeholder="Amount in ₦" min="100" style="flex:1" />
          <button class="btn btn-success" onclick="requestPayout()">Withdraw</button>
        </div>
        <p class="form-hint">Funds will be transferred to your registered bank account.</p>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Transaction History</span></div>
        ${(txData.transactions || []).length ? `
          <div class="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Description</th><th>Type</th><th>Amount</th></tr></thead>
              <tbody>
                ${(txData.transactions || []).map(t => `<tr>
                  <td>${formatDate(t.created_at)}</td>
                  <td>${escapeHtml(t.description || '—')}</td>
                  <td><span class="badge ${t.transaction_type === 'credit' ? 'badge-paid' : 'badge-cancelled'}">${t.transaction_type}</span></td>
                  <td style="font-weight:600;color:${t.transaction_type === 'credit' ? 'var(--color-success)' : 'var(--color-danger)'}">
                    ${t.transaction_type === 'credit' ? '+' : '-'}${formatNGN(t.amount)}
                  </td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>` : '<div class="empty-state"><div class="icon">💳</div><h3>No transactions</h3></div>'}
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function requestPayout() {
  const amount = parseFloat(document.getElementById('payoutAmount').value);
  if (!amount || amount < 100) {
    showToast('Minimum payout is ₦100.', 'error');
    return;
  }
  try {
    await api.post('/vendor/payout', { amount, reason: 'Vendor earnings withdrawal' });
    showToast('Payout initiated! Check your bank within 24 hours.', 'success');
    loadWallet();
  } catch (err) { showToast(err.message, 'error'); }
}

// ── Navigation ─────────────────────────────────────────────────────────────────
const _origNavigate = navigate;
window.navigate = function(pageId) {
  _origNavigate(pageId);
  const map = {
    'page-overview': 'Overview',
    'page-orders': 'Orders',
    'page-products': 'My Products',
    'page-profile': 'Store Settings',
    'page-wallet': 'Wallet & Payouts',
  };
  document.getElementById('topbar-title').textContent = map[pageId] || 'ADVAN Vendor';
};
