"""
DEPRECATED — this file is kept for reference only.

Demo accounts are no longer seeded automatically. All user roles now
self-register through the respective portal UIs:

  • Customer  → /frontend/customer/index.html
  • Vendor    → /frontend/vendor/index.html
  • Rider     → /frontend/rider/index.html
  • Agent     → /frontend/agent/index.html

Admin accounts must be created via the dedicated script:

  python create_admin.py

"""
raise SystemExit(
    "seed_demo.py is deprecated.\n"
    "Run 'python create_admin.py' to create an admin account.\n"
    "All other roles register via the portal UIs."
)
