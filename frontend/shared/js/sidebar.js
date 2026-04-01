/**
 * ADVAN — Sidebar Controller
 *
 * Single behaviour for both desktop and mobile:
 *   - .app-shell.sidebar-hidden  → sidebar is translateX(-100%), fully off-screen
 *   - no class                   → sidebar is visible at translateX(0)
 *
 * Desktop: main-content margin shifts with the sidebar (CSS handles this).
 * Mobile:  sidebar overlays content, backdrop dims the page.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'advan_sidebar_hidden';
  var MOBILE_BP   = 768;

  var shell    = document.querySelector('.app-shell');
  var sidebar  = document.querySelector('.sidebar');
  var backdrop = document.getElementById('sidebar-backdrop');

  if (!shell || !sidebar) return;  // not a portal page (e.g. auth page)

  /* ── Helpers ─────────────────────────────────────────────── */
  function isMobile() {
    return window.innerWidth <= MOBILE_BP;
  }

  function isHidden() {
    return shell.classList.contains('sidebar-hidden');
  }

  function showBackdrop() {
    if (!backdrop) return;
    backdrop.classList.add('visible');
  }

  function hideBackdrop() {
    if (!backdrop) return;
    backdrop.classList.remove('visible');
  }

  /* ── Open sidebar ─────────────────────────────────────────── */
  function openSidebar() {
    shell.classList.remove('sidebar-hidden');
    if (isMobile()) {
      showBackdrop();
      document.body.style.overflow = 'hidden';  // prevent page scroll behind overlay
    }
    if (!isMobile()) {
      localStorage.setItem(STORAGE_KEY, '0');
    }
  }

  /* ── Close sidebar ────────────────────────────────────────── */
  function closeSidebar() {
    shell.classList.add('sidebar-hidden');
    hideBackdrop();
    document.body.style.overflow = '';
    if (!isMobile()) {
      localStorage.setItem(STORAGE_KEY, '1');
    }
  }

  /* ── Public toggle (called by hamburger button) ───────────── */
  window.toggleSidebar = function () {
    if (isHidden()) {
      openSidebar();
    } else {
      closeSidebar();
    }
  };

  /* ── Initialise state ─────────────────────────────────────── */
  if (isMobile()) {
    // Mobile: always start with sidebar hidden
    shell.classList.add('sidebar-hidden');
  } else {
    // Desktop: restore last state (default = visible)
    if (localStorage.getItem(STORAGE_KEY) === '1') {
      shell.classList.add('sidebar-hidden');
    }
    // else: no class = sidebar visible (default)
  }

  /* ── Backdrop click → close ──────────────────────────────── */
  if (backdrop) {
    backdrop.addEventListener('click', closeSidebar);
  }

  /* ── Nav item click on mobile → close overlay ────────────── */
  sidebar.addEventListener('click', function (e) {
    if (isMobile() && e.target.closest('.nav-item')) {
      closeSidebar();
    }
  });

  /* ── Escape key → close ──────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !isHidden()) {
      closeSidebar();
    }
  });

  /* ── Handle viewport resize ───────────────────────────────── */
  var _resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(function () {
      if (isMobile()) {
        // Switched to mobile: ensure sidebar is hidden and backdrop cleared
        if (!isHidden()) {
          shell.classList.add('sidebar-hidden');
          hideBackdrop();
          document.body.style.overflow = '';
        }
      } else {
        // Switched to desktop: restore saved preference, clear mobile state
        hideBackdrop();
        document.body.style.overflow = '';
        var saved = localStorage.getItem(STORAGE_KEY);
        if (saved === '1') {
          shell.classList.add('sidebar-hidden');
        } else {
          shell.classList.remove('sidebar-hidden');
        }
      }
    }, 100);
  });

}());
