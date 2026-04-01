"""
Database migration: order lifecycle tracking enhancements.

Run ONCE from the backend/ directory before (re)starting the server:

    python migrate.py

What this does:
  1. Adds stage-timestamp columns to the 'orders' table
     (vendor_accepted_at, vendor_rejected_at, rider_assigned_at,
      picked_up_at, hub_verified_at, in_transit_at)
  2. Adds 'vendor_rejected' value to the orderstatus enum
     (safe no-op if already present — PostgreSQL DO/EXCEPTION block)

All statements use IF NOT EXISTS / DO…EXCEPTION so the script is
safe to run multiple times.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("✗ DATABASE_URL not set in .env")
    sys.exit(1)

MIGRATIONS = [
    # ── 1. Order stage-timestamp columns ─────────────────────────────────
    """
    ALTER TABLE orders
      ADD COLUMN IF NOT EXISTS vendor_accepted_at TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS vendor_rejected_at TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS rider_assigned_at  TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS picked_up_at       TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS hub_verified_at    TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS in_transit_at      TIMESTAMPTZ;
    """,
    # ── 2. New order status enum value ───────────────────────────────────
    """
    DO $$ BEGIN
      ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'vendor_rejected';
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
    # ── 3. Multi-role support: extra_roles column on users ───────────────
    """
    ALTER TABLE users
      ADD COLUMN IF NOT EXISTS extra_roles TEXT[] NOT NULL DEFAULT '{}';
    """,
    # ── 4. Vendor location coordinates ───────────────────────────────────
    """
    ALTER TABLE vendor_profiles
      ADD COLUMN IF NOT EXISTS latitude  NUMERIC(10,7),
      ADD COLUMN IF NOT EXISTS longitude NUMERIC(10,7);
    """,
]


async def run_migrations() -> None:
    print("\n" + "=" * 52)
    print("  ADVAN — Database Migration")
    print("=" * 52 + "\n")

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for i, sql in enumerate(MIGRATIONS, 1):
            print(f"  Running migration {i}/{len(MIGRATIONS)}…")
            await conn.execute(text(sql))
            print(f"  ✓ Done")

    await engine.dispose()
    print("\n✓ All migrations applied successfully.\n")


if __name__ == "__main__":
    asyncio.run(run_migrations())
