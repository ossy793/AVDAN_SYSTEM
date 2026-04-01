/**
 * ADVAN Customer Portal — Application Logic
 */

// ── Fee constants (must match backend config) ─────────────────────────────────
const FEES = {
  DELIVERY_BASE: 500,       // NGN flat delivery fee
  HUB_FEE: 100,             // NGN per-order hub processing fee
  PLATFORM_PCT: 0.05,       // 5% of subtotal
};

// ── State ─────────────────────────────────────────────────────────────────────
const cart = {
  items: JSON.parse(localStorage.getItem('advan_cart') || '[]'),

  save() { localStorage.setItem('advan_cart', JSON.stringify(this.items)); },

  add(product, qty = 1) {
    const existing = this.items.find(i => i.product_id === product.id);
    if (existing) {
      existing.quantity += qty;
    } else {
      this.items.push({
        product_id: product.id,
        name: product.name,
        price: product.price,
        quantity: qty,
      });
    }
    this.save();
    updateCartUI();
  },

  remove(productId) {
    this.items = this.items.filter(i => i.product_id !== productId);
    this.save();
    updateCartUI();
    renderCart();
  },

  updateQty(productId, delta) {
    const item = this.items.find(i => i.product_id === productId);
    if (!item) return;
    item.quantity = Math.max(1, item.quantity + delta);
    this.save();
    renderCart();
  },

  clear() {
    this.items = [];
    this.save();
    updateCartUI();
    renderCart();
  },

  subtotal() {
    return this.items.reduce((s, i) => s + i.price * i.quantity, 0);
  },

  total() {
    const sub = this.subtotal();
    return sub + FEES.DELIVERY_BASE + FEES.HUB_FEE + sub * FEES.PLATFORM_PCT;
  },

  toApiItems() {
    return this.items.map(i => ({ product_id: i.product_id, quantity: i.quantity }));
  },
};

let allProducts   = [];
let trackingMap   = null;
let riderMarker   = null;
let _trackPollId  = null;   // setInterval handle for tracking page auto-refresh
let _trackingOrderId = null; // currently tracked order

// ── Delivery location state ───────────────────────────────────────────────────
let deliveryMap      = null;
let deliveryMarker   = null;
const deliveryState  = { lat: null, lng: null, address: '' };
let _searchTimer     = null;
let _geoWatchId      = null;
let _accuracyCircle  = null;

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
    if (!(data.roles || [data.role]).includes('customer')) {
      showAlert('#auth-alert', 'This portal is for customers only. Please use the correct dashboard.', 'error');
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
      role: 'customer',
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

function logout() {
  authStore.clear();
  location.reload();
}

async function showApp() {
  document.getElementById('auth-gate').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');

  // Load user info
  try {
    const user = await api.get('/auth/me');
    document.getElementById('user-name').textContent = `${user.first_name} ${user.last_name}`;
    document.getElementById('user-email').textContent = user.email;
    document.getElementById('user-avatar').textContent = user.first_name[0].toUpperCase();
  } catch {}

  updateCartUI();
  loadProducts();
}

// ── Products ──────────────────────────────────────────────────────────────────
async function loadProducts() {
  const grid = document.getElementById('products-grid');
  grid.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/customer/products?per_page=50');
    allProducts = data.items || [];
    renderProducts(allProducts);
  } catch (err) {
    grid.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

function renderProducts(products) {
  const grid = document.getElementById('products-grid');
  if (!products.length) {
    grid.innerHTML = '<div class="empty-state"><div class="icon">🛍️</div><h3>No products found</h3></div>';
    return;
  }
  grid.innerHTML = products.map(p => `
    <div class="product-card">
      <div class="product-image">
        ${p.image_url
          ? `<img src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}" />`
          : '📦'}
      </div>
      <div class="product-body">
        <div class="product-name" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</div>
        <div class="product-category">${p.category}</div>
        <div class="product-price">${formatNGN(p.price)}</div>
        <div class="product-stock">${p.stock_quantity} in stock</div>
      </div>
      <div class="product-footer">
        <div class="qty-control">
          <button class="qty-btn" onclick="adjustQty('${p.id}', -1)">−</button>
          <span class="qty-display" id="qty-${p.id}">1</span>
          <button class="qty-btn" onclick="adjustQty('${p.id}', 1)">+</button>
        </div>
        <button class="btn btn-primary btn-sm" style="flex:1" onclick="addToCart('${p.id}')">
          Add to Cart
        </button>
      </div>
    </div>
  `).join('');
}

function filterProducts() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const category = document.getElementById('categoryFilter').value;
  const filtered = allProducts.filter(p => {
    const matchSearch = !search || p.name.toLowerCase().includes(search);
    const matchCat = !category || p.category === category;
    return matchSearch && matchCat;
  });
  renderProducts(filtered);
}

const qtyState = {};
function adjustQty(productId, delta) {
  qtyState[productId] = Math.max(1, (qtyState[productId] || 1) + delta);
  const el = document.getElementById(`qty-${productId}`);
  if (el) el.textContent = qtyState[productId];
}

function addToCart(productId) {
  const product = allProducts.find(p => p.id === productId);
  if (!product) return;
  const qty = qtyState[productId] || 1;
  cart.add(product, qty);
  showToast(`${product.name} added to cart!`, 'success');
}

// ── Cart ──────────────────────────────────────────────────────────────────────
function updateCartUI() {
  const count = cart.items.reduce((s, i) => s + i.quantity, 0);
  document.getElementById('cart-count').textContent = count;
  const badge = document.getElementById('cart-count-badge');
  badge.textContent = count || '';
  badge.style.display = count ? 'inline-flex' : 'none';
}

function renderCart() {
  const list = document.getElementById('cart-items-list');
  if (!cart.items.length) {
    list.innerHTML = '<div class="empty-state"><div class="icon">🛒</div><h3>Your cart is empty</h3></div>';
    document.getElementById('summary-subtotal').textContent = '₦0.00';
    document.getElementById('summary-platform').textContent = '₦0.00';
    document.getElementById('summary-total').textContent = '₦0.00';
    return;
  }

  list.innerHTML = cart.items.map(item => `
    <div class="cart-item">
      <div class="cart-item-icon">📦</div>
      <div style="flex:1">
        <div class="cart-item-name">${escapeHtml(item.name)}</div>
        <div class="cart-item-price">${formatNGN(item.price)} each</div>
        <div class="qty-control" style="margin-top:8px">
          <button class="qty-btn" onclick="cart.updateQty('${item.product_id}', -1)">−</button>
          <span class="qty-display">${item.quantity}</span>
          <button class="qty-btn" onclick="cart.updateQty('${item.product_id}', 1)">+</button>
        </div>
      </div>
      <div style="text-align:right">
        <div class="cart-item-subtotal">${formatNGN(item.price * item.quantity)}</div>
        <button class="cart-remove" onclick="cart.remove('${item.product_id}')">✕</button>
      </div>
    </div>
  `).join('');

  const sub = cart.subtotal();
  document.getElementById('summary-subtotal').textContent = formatNGN(sub);
  document.getElementById('summary-platform').textContent = formatNGN(sub * FEES.PLATFORM_PCT);
  document.getElementById('summary-total').textContent = formatNGN(cart.total());
}

function clearCart() {
  if (confirm('Clear entire cart?')) cart.clear();
}

// ── Delivery Map & Geocoding ──────────────────────────────────────────────────
function initDeliveryMap() {
  if (deliveryMap) {
    // Re-trigger size calculation if container was hidden before
    setTimeout(() => deliveryMap.invalidateSize(), 10);
    return;
  }

  deliveryMap = L.map('delivery-map', { zoomControl: true })
    .setView([6.5244, 3.3792], 12);   // default: Lagos

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(deliveryMap);

  // Click anywhere on map to place/move marker (also cancels any active watchPosition)
  deliveryMap.on('click', (e) => {
    if (_geoWatchId !== null) {
      navigator.geolocation.clearWatch(_geoWatchId);
      _geoWatchId = null;
      const btn = document.getElementById('useLocationBtn');
      btn.textContent = '📍 Use My Current Location';
      btn.disabled = false;
    }
    placeDeliveryMarker(e.latlng.lat, e.latlng.lng);
    reverseGeocode(e.latlng.lat, e.latlng.lng);
  });
}

function placeDeliveryMarker(lat, lng, address) {
  // Clear any accuracy circle from watchPosition
  if (_accuracyCircle) { _accuracyCircle.remove(); _accuracyCircle = null; }

  deliveryState.lat = lat;
  deliveryState.lng = lng;
  if (address !== undefined) deliveryState.address = address;

  // Sync hidden inputs (backend payload)
  document.getElementById('deliveryLat').value = lat;
  document.getElementById('deliveryLng').value = lng;
  if (address !== undefined) document.getElementById('deliveryAddress').value = address;

  const icon = L.divIcon({
    html: '<div style="font-size:28px;line-height:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,.4))">📍</div>',
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 28],
  });

  if (deliveryMarker) {
    deliveryMarker.setLatLng([lat, lng]);
  } else {
    deliveryMarker = L.marker([lat, lng], { icon, draggable: true }).addTo(deliveryMap);

    // Dragging the marker refines the location
    deliveryMarker.on('dragend', (e) => {
      const { lat: dLat, lng: dLng } = e.target.getLatLng();
      placeDeliveryMarker(dLat, dLng);
      reverseGeocode(dLat, dLng);
    });
  }

  deliveryMap.setView([lat, lng], 16);
  _setLocationError('');
}

function _updateConfirmedDisplay(address, lat, lng) {
  const el = document.getElementById('location-confirmed');
  document.getElementById('location-confirmed-text').textContent = address;
  document.getElementById('location-coords').textContent =
    `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
  el.classList.remove('hidden');
}

function _setLocationError(msg) {
  const el = document.getElementById('location-error');
  el.textContent = msg;
  el.classList.toggle('hidden', !msg);
}

async function reverseGeocode(lat, lng) {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`,
      { headers: { 'Accept-Language': 'en' } }
    );
    if (!res.ok) throw new Error();
    const data = await res.json();
    const addr = data.display_name || `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    deliveryState.address = addr;
    document.getElementById('deliveryAddress').value = addr;
    document.getElementById('locationSearch').value = addr;
    _updateConfirmedDisplay(addr, lat, lng);
  } catch {
    // Coordinates are already stored — address display degrades gracefully
    const fallback = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    deliveryState.address = fallback;
    document.getElementById('deliveryAddress').value = fallback;
    _updateConfirmedDisplay(fallback, lat, lng);
  }
}

// ── Location search (Nominatim) ───────────────────────────────────────────────
function onLocationInput() {
  const q = document.getElementById('locationSearch').value.trim();
  clearTimeout(_searchTimer);

  const box = document.getElementById('search-suggestions');
  if (q.length < 3) {
    box.classList.add('hidden');
    return;
  }

  _searchTimer = setTimeout(async () => {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=6&countrycodes=ng&addressdetails=1`,
        { headers: { 'Accept-Language': 'en' } }
      );
      const results = await res.json();
      _renderSuggestions(results);
    } catch {
      box.classList.add('hidden');
    }
  }, 350);
}

function _renderSuggestions(results) {
  const box = document.getElementById('search-suggestions');
  if (!results.length) {
    box.innerHTML = '<div class="suggestion-item" style="color:var(--color-muted);cursor:default">No results found</div>';
    box.classList.remove('hidden');
    return;
  }
  box._results = results;
  box.innerHTML = results.map((r, i) =>
    `<div class="suggestion-item" onclick="selectSuggestion(${i})">${escapeHtml(r.display_name)}</div>`
  ).join('');
  box.classList.remove('hidden');
}

function selectSuggestion(index) {
  const box = document.getElementById('search-suggestions');
  const r   = box._results[index];
  const lat = parseFloat(r.lat);
  const lng = parseFloat(r.lon);
  document.getElementById('locationSearch').value = r.display_name;
  box.classList.add('hidden');
  placeDeliveryMarker(lat, lng, r.display_name);
  _updateConfirmedDisplay(r.display_name, lat, lng);
}

// Dismiss suggestions when clicking outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('.location-search-wrap')) {
    const box = document.getElementById('search-suggestions');
    if (box) box.classList.add('hidden');
  }
});

// ── Use current location (watchPosition for better accuracy) ──────────────────
function useCurrentLocation() {
  const btn = document.getElementById('useLocationBtn');
  _setLocationError('');

  if (!navigator.geolocation) {
    _setLocationError('Geolocation is not supported by your browser. Please search manually.');
    return;
  }

  // Cancel any previous watch
  if (_geoWatchId !== null) {
    navigator.geolocation.clearWatch(_geoWatchId);
    _geoWatchId = null;
  }

  const GOOD_ACCURACY = 150;    // metres — stop early if we reach this
  const MAX_WAIT_MS   = 12000;  // hard timeout: commit best fix after 12 seconds
  let   bestPos       = null;
  let   committed     = false;

  btn.disabled = true;
  btn.textContent = '⏳ Detecting location…';

  // ── Commit whatever best fix we have (called on timeout OR good accuracy) ──
  function _commitFix() {
    if (committed) return;
    committed = true;
    if (_geoWatchId !== null) {
      navigator.geolocation.clearWatch(_geoWatchId);
      _geoWatchId = null;
    }
    if (!bestPos) {
      // Timed out with zero fixes — give up
      btn.textContent = '📍 Use My Current Location';
      btn.disabled = false;
      _setLocationError('Could not detect location. Please search your address or click the map.');
      return;
    }

    const finalLat = bestPos.coords.latitude;
    const finalLng = bestPos.coords.longitude;
    const finalAcc = Math.round(bestPos.coords.accuracy);

    placeDeliveryMarker(finalLat, finalLng);
    reverseGeocode(finalLat, finalLng);

    if (finalAcc > 5000) {
      // IP-based fix — very rough, warn strongly
      _setLocationError(
        `Very low accuracy (±${(finalAcc / 1000).toFixed(0)}km) — this is an IP-based estimate. ` +
        `Please drag the map pin to your exact address or use the search bar.`
      );
      btn.textContent = '⚠️ Approximate location set';
    } else if (finalAcc > 500) {
      _setLocationError(
        `Low accuracy (±${finalAcc}m) — drag the pin or search your address for a more precise location.`
      );
      btn.textContent = '⚠️ Low accuracy — location set';
    } else {
      btn.textContent = `✅ Location set (±${finalAcc}m)`;
    }

    setTimeout(() => {
      btn.textContent = '📍 Use My Current Location';
      btn.disabled = false;
    }, 3500);
  }

  // Hard timeout — never leave the button spinning
  const _timeoutId = setTimeout(_commitFix, MAX_WAIT_MS);

  _geoWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      const { latitude, longitude, accuracy } = pos.coords;

      // Keep the most accurate fix seen so far
      if (!bestPos || accuracy < bestPos.coords.accuracy) {
        bestPos = pos;
      }

      // Update button with live accuracy feedback
      btn.textContent = `⏳ Refining… (±${Math.round(accuracy)}m)`;

      // Draw / update accuracy circle on map
      if (_accuracyCircle) {
        _accuracyCircle.setLatLng([latitude, longitude]).setRadius(accuracy);
      } else if (deliveryMap) {
        _accuracyCircle = L.circle([latitude, longitude], {
          radius: accuracy,
          color: '#3b82f6',
          fillColor: '#3b82f6',
          fillOpacity: 0.10,
          weight: 1.5,
        }).addTo(deliveryMap);
      }

      // Preview marker position while refining
      if (deliveryMarker) {
        deliveryMarker.setLatLng([latitude, longitude]);
        deliveryMap.setView([latitude, longitude], 15);
      } else {
        placeDeliveryMarker(latitude, longitude);
        deliveryMap.setView([latitude, longitude], 15);
      }

      // Stop early if accuracy is good enough
      if (accuracy <= GOOD_ACCURACY) {
        clearTimeout(_timeoutId);
        _commitFix();
      }
    },
    (err) => {
      clearTimeout(_timeoutId);
      // If we already have a best fix, commit it
      if (bestPos) { _commitFix(); return; }
      committed = true;
      if (_geoWatchId !== null) {
        navigator.geolocation.clearWatch(_geoWatchId);
        _geoWatchId = null;
      }
      btn.textContent = '📍 Use My Current Location';
      btn.disabled = false;
      const msgs = {
        1: 'Location permission denied. Please allow access or search your address manually.',
        2: 'Location unavailable. Try searching your address instead.',
        3: 'Location request timed out. Please search your address manually.',
      };
      _setLocationError(msgs[err.code] || 'Could not detect location. Please search manually.');
    },
    { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 }
  );
}

// ── Place Order & Pay ─────────────────────────────────────────────────────────
async function placeOrder() {
  if (!cart.items.length) {
    showAlert('#cart-alert', 'Your cart is empty.', 'error');
    return;
  }

  if (!deliveryState.lat || !deliveryState.lng) {
    showAlert('#cart-alert', 'Please select your delivery location on the map.', 'error');
    // Scroll the map into view
    document.getElementById('delivery-map').scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }

  const btn = document.getElementById('placeOrderBtn');
  setLoading(btn, true);
  try {
    const payload = {
      items: cart.toApiItems(),
      delivery_address: deliveryState.address,
      delivery_latitude: deliveryState.lat,
      delivery_longitude: deliveryState.lng,
    };
    const data = await api.post('/customer/orders', payload);
    cart.clear();
    // Reset delivery state for next order
    deliveryState.lat = null; deliveryState.lng = null; deliveryState.address = '';
    if (deliveryMarker) { deliveryMap.removeLayer(deliveryMarker); deliveryMarker = null; }
    document.getElementById('locationSearch').value = '';
    document.getElementById('location-confirmed').classList.add('hidden');

    showToast('Order created! Redirecting to payment…', 'success');
    setTimeout(() => {
      window.open(data.checkout_url, '_blank');
      navigate('page-orders');
      loadOrders();
    }, 1500);
  } catch (err) {
    showAlert('#cart-alert', err.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

// ── Orders ────────────────────────────────────────────────────────────────────
async function loadOrders() {
  const list = document.getElementById('orders-list');
  list.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await api.get('/customer/orders');
    const orders = data.items || [];
    if (!orders.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">📦</div><h3>No orders yet</h3><p>Browse products and place your first order!</p></div>';
      return;
    }
    list.innerHTML = orders.map(o => `
      <div class="order-card">
        <div class="order-card-header">
          <span class="order-reference">${escapeHtml(o.reference)}</span>
          ${statusBadge(o.status)}
        </div>
        <div class="flex justify-between">
          <div>
            <div class="text-sm text-muted">Total</div>
            <div class="font-bold" style="font-size:var(--text-lg)">${formatNGN(o.total_amount)}</div>
          </div>
          <div>
            <div class="text-sm text-muted">Delivery to</div>
            <div class="text-sm" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(o.delivery_address)}</div>
          </div>
          <div>
            <div class="text-sm text-muted">Placed</div>
            <div class="text-sm">${formatDate(o.created_at)}</div>
          </div>
        </div>
        <div class="flex gap-sm mt-md">
          <button class="btn btn-ghost btn-sm" onclick="loadOrderDetail('${o.id}')">View Details</button>
          ${o.status === 'pending' || o.status === 'paid' ? `
            <button class="btn btn-danger btn-sm" onclick="cancelOrder('${o.id}')">Cancel</button>` : ''}
          ${!['pending','cancelled','refunded'].includes(o.status) ? `
            <button class="btn btn-ghost btn-sm" onclick="trackOrderById('${o.id}')">📍 Track</button>` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function loadOrderDetail(orderId) {
  navigate('page-track');
  await trackOrderById(orderId);
}

async function cancelOrder(orderId) {
  const reason = prompt('Reason for cancellation:');
  if (!reason) return;
  try {
    await api.post(`/customer/orders/${orderId}/cancel`, { reason });
    showToast('Order cancelled.', 'warning');
    loadOrders();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── Track Order ───────────────────────────────────────────────────────────────

// The 6 customer-visible stages with their status-set and timestamp field
const TRACK_STAGES = [
  {
    label:     'Order Placed',
    icon:      '🛍️',
    statuses:  ['pending','paid'],
    tsField:   'created_at',
  },
  {
    label:     'Vendor Accepted',
    icon:      '✅',
    statuses:  ['vendor_confirmed','preparing','ready_for_pickup'],
    tsField:   'vendor_accepted_at',
  },
  {
    label:     'Rider Assigned',
    icon:      '🚴',
    statuses:  ['rider_assigned','picked_up'],
    tsField:   'rider_assigned_at',
  },
  {
    label:     'Checked by Agent',
    icon:      '🏠',
    statuses:  ['at_hub','hub_verified'],
    tsField:   'hub_verified_at',
  },
  {
    label:     'Rider On The Way',
    icon:      '📦',
    statuses:  ['in_transit'],
    tsField:   'in_transit_at',
  },
  {
    label:     'Delivered',
    icon:      '🎉',
    statuses:  ['delivered'],
    tsField:   'delivered_at',
  },
];

// Terminal statuses where polling should stop
const TERMINAL_STATUSES = new Set(['delivered','cancelled','refunded','disputed','vendor_rejected']);

function _stageIndex(status) {
  for (let i = 0; i < TRACK_STAGES.length; i++) {
    if (TRACK_STAGES[i].statuses.includes(status)) return i;
  }
  return -1;
}

function _renderTrackTimeline(order) {
  const currentIdx = _stageIndex(order.status);
  const isRejected = order.status === 'vendor_rejected';
  const isCancelled = ['cancelled','refunded'].includes(order.status);

  // Rejection banner
  let banner = '';
  if (isRejected) {
    banner = `<div class="alert alert-error" style="margin-bottom:var(--space-md)">
      <strong>Order Rejected by Vendor</strong>
      ${order.cancellation_reason ? ` — ${escapeHtml(order.cancellation_reason)}` : ''}
      <div style="font-size:var(--text-xs);margin-top:4px;opacity:.8">A refund has been initiated to your wallet.</div>
    </div>`;
  } else if (isCancelled) {
    banner = `<div class="alert alert-warning" style="margin-bottom:var(--space-md)">
      <strong>Order ${order.status === 'refunded' ? 'Refunded' : 'Cancelled'}</strong>
      ${order.cancellation_reason ? ` — ${escapeHtml(order.cancellation_reason)}` : ''}
    </div>`;
  }

  const stepsHtml = TRACK_STAGES.map((stage, i) => {
    const ts = order[stage.tsField];
    let state, dot, labelColor, timeHtml;

    if (isRejected && i === 1) {
      // "Vendor Accepted" slot shows rejection instead
      state = 'rejected';
      dot = `<div class="tl-dot" style="background:#ef4444;border-color:#fef2f2">✕</div>`;
      labelColor = '#ef4444';
      timeHtml = order.vendor_rejected_at
        ? `<span class="tl-time">${formatDate(order.vendor_rejected_at)}</span>`
        : '';
      return `
        <div class="tl-step">
          <div class="tl-connector ${i > 0 ? '' : 'tl-connector-hidden'}"></div>
          ${dot}
          <div class="tl-body">
            <span class="tl-label" style="color:${labelColor}">Vendor Rejected</span>
            ${timeHtml}
          </div>
        </div>`;
    }

    if (currentIdx === -1 || i > currentIdx) {
      // Pending step
      state = 'pending';
      dot = `<div class="tl-dot tl-dot-pending"></div>`;
      labelColor = 'var(--color-muted)';
      timeHtml = '<span class="tl-time">—</span>';
    } else if (i < currentIdx) {
      // Completed step
      state = 'done';
      dot = `<div class="tl-dot tl-dot-done">✓</div>`;
      labelColor = 'var(--color-success)';
      timeHtml = ts ? `<span class="tl-time">${formatDate(ts)}</span>` : '';
    } else {
      // Active step
      state = 'active';
      dot = `<div class="tl-dot tl-dot-active"></div>`;
      labelColor = 'var(--color-primary)';
      timeHtml = ts ? `<span class="tl-time">${formatDate(ts)}</span>` : '<span class="tl-time tl-time-active">In progress…</span>';
    }

    return `
      <div class="tl-step">
        <div class="tl-connector ${i > 0 ? (state === 'pending' ? '' : 'tl-connector-done') : 'tl-connector-hidden'}"></div>
        ${dot}
        <div class="tl-body">
          <span class="tl-icon">${stage.icon}</span>
          <span class="tl-label" style="color:${labelColor}">${stage.label}</span>
          ${timeHtml}
        </div>
      </div>`;
  }).join('');

  return `
    ${banner}
    <div class="card">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:var(--space-md)">
        <div>
          <div style="font-family:var(--font-mono);font-size:var(--text-sm);font-weight:700;background:var(--color-bg);padding:4px 10px;border-radius:var(--radius-md);display:inline-block">${escapeHtml(order.reference)}</div>
          <div class="text-sm text-muted" style="margin-top:6px">${escapeHtml(order.delivery_address || '')}</div>
        </div>
        ${statusBadge(order.status)}
      </div>
      <div class="tl-track">
        ${stepsHtml}
      </div>
    </div>`;
}

async function trackOrder() {
  const ref = document.getElementById('trackInput').value.trim();
  if (!ref) return;

  const result = document.getElementById('track-result');
  result.innerHTML = '<div class="spinner"></div>';
  _stopTrackPoll();
  try {
    const data = await api.get('/customer/orders?per_page=100');
    const order = (data.items || []).find(o => o.reference === ref);
    if (!order) {
      result.innerHTML = '<div class="alert alert-error">Order not found. Check the reference and make sure you\'re signed in as the customer who placed it.</div>';
      return;
    }
    await _renderAndPollOrder(order.id);
  } catch (err) {
    result.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function trackOrderById(orderId) {
  navigate('page-track');
  _stopTrackPoll();
  await _renderAndPollOrder(orderId);
}

async function _renderAndPollOrder(orderId) {
  _trackingOrderId = orderId;
  const result = document.getElementById('track-result');
  result.innerHTML = '<div class="spinner"></div>';

  const refresh = async () => {
    try {
      const order = await api.get(`/customer/orders/${orderId}/track`);
      result.innerHTML = _renderTrackTimeline(order);

      // Show delivery map for active delivery stages
      const mapEl = document.getElementById('map');
      if (['at_hub','hub_verified','in_transit'].includes(order.status)) {
        mapEl.classList.remove('hidden');
        setTimeout(() => initTrackingMap(order), 60);
      } else {
        mapEl.classList.add('hidden');
      }

      // Stop polling once order reaches a terminal state
      if (TERMINAL_STATUSES.has(order.status)) {
        _stopTrackPoll();
      }
    } catch (err) {
      result.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
      _stopTrackPoll();
    }
  };

  await refresh();

  // Poll every 8 seconds for live updates
  _trackPollId = setInterval(refresh, 8000);
}

function _stopTrackPoll() {
  if (_trackPollId !== null) {
    clearInterval(_trackPollId);
    _trackPollId = null;
  }
  _trackingOrderId = null;
}

function initTrackingMap(order) {
  const mapContainer = document.getElementById('map');
  mapContainer.style.height = '280px';
  mapContainer.style.borderRadius = 'var(--radius-lg)';
  mapContainer.style.overflow = 'hidden';
  mapContainer.style.marginTop = 'var(--space-md)';

  if (!trackingMap) {
    trackingMap = L.map('map').setView([6.5244, 3.3792], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(trackingMap);
  } else {
    setTimeout(() => trackingMap.invalidateSize(), 10);
  }
  if (order.delivery_latitude && order.delivery_longitude) {
    const icon = L.divIcon({ html: '📍', className: '', iconSize: [30, 30] });
    if (riderMarker) {
      riderMarker.setLatLng([order.delivery_latitude, order.delivery_longitude]);
    } else {
      riderMarker = L.marker([order.delivery_latitude, order.delivery_longitude], { icon })
        .bindPopup('Delivery Location').addTo(trackingMap);
    }
    trackingMap.setView([order.delivery_latitude, order.delivery_longitude], 14);
  }
}

// ── Wallet ────────────────────────────────────────────────────────────────────
async function loadWallet() {
  const el = document.getElementById('wallet-details');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const wallet = await api.get('/customer/wallet');
    const txData = await api.get('/customer/wallet/transactions');
    const txs = txData.transactions || [];
    el.innerHTML = `
      <div class="wallet-balance-card">
        <div class="wallet-balance-label">Available Balance</div>
        <div class="wallet-balance-amount">
          <span class="wallet-currency">₦</span>${Number(wallet.balance).toLocaleString('en-NG', {minimumFractionDigits:2})}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Transaction History</span></div>
        ${txs.length ? `
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Date</th><th>Description</th><th>Type</th><th>Amount</th>
              </tr></thead>
              <tbody>
                ${txs.map(t => `<tr>
                  <td>${formatDate(t.created_at)}</td>
                  <td>${escapeHtml(t.description || '—')}</td>
                  <td><span class="badge ${t.transaction_type === 'credit' ? 'badge-paid' : 'badge-cancelled'}">${t.transaction_type}</span></td>
                  <td style="font-weight:600;color:${t.transaction_type === 'credit' ? 'var(--color-success)' : 'var(--color-danger)'}">
                    ${t.transaction_type === 'credit' ? '+' : '-'}${formatNGN(t.amount)}
                  </td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>` : '<div class="empty-state"><div class="icon">💳</div><h3>No transactions yet</h3></div>'}
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ── Notifications ─────────────────────────────────────────────────────────────
async function loadNotifications() {
  const list = document.getElementById('notifications-list');
  list.innerHTML = '<div class="spinner"></div>';
  try {
    const notifs = await api.get('/customer/notifications');
    if (!notifs.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">🔔</div><h3>All caught up!</h3><p>No new notifications</p></div>';
      return;
    }
    list.innerHTML = notifs.map(n => `
      <div class="card mb-md" style="${n.is_read ? 'opacity:.7' : ''}">
        <div class="flex justify-between mb-md">
          <strong>${escapeHtml(n.title)}</strong>
          <span class="text-sm text-muted">${formatDate(n.created_at)}</span>
        </div>
        <p>${escapeHtml(n.message)}</p>
      </div>`).join('');
  } catch (err) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

async function markAllRead() {
  try {
    await api.post('/customer/notifications/read-all');
    loadNotifications();
  } catch {}
}

// ── Navigation hook ───────────────────────────────────────────────────────────
const _origNavigate = navigate;
window.navigate = function(pageId) {
  _origNavigate(pageId);
  const titleMap = {
    'page-shop': 'Browse Products',
    'page-cart': 'Your Cart',
    'page-orders': 'My Orders',
    'page-track': 'Track Order',
    'page-wallet': 'My Wallet',
    'page-notifications': 'Notifications',
  };
  document.getElementById('topbar-title').textContent = titleMap[pageId] || 'ADVAN';
  if (pageId === 'page-cart') {
    renderCart();
    // Leaflet requires the container to be visible before initializing
    setTimeout(initDeliveryMap, 60);
  }
  // Stop tracking poll when user leaves the track page
  if (pageId !== 'page-track') {
    _stopTrackPoll();
  }
};

// Initial cart render when navigating to cart
document.querySelectorAll('[data-page="page-cart"]').forEach(el => {
  el.addEventListener('click', renderCart);
});
