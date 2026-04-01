"""
Admin account creation script.
Run once from the backend/ directory to create the first admin account:

    python create_admin.py

All other user roles (customer, vendor, rider, agent) self-register through
the respective portal UIs. Admin accounts are NOT available for public
registration and must be created via this script.
"""
import asyncio
import os
import sys

import bcrypt
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
DATABASE_URL = os.environ["DATABASE_URL"]


async def create_admin() -> None:
    print("\n" + "=" * 52)
    print("  ADVAN — Create Admin Account")
    print("=" * 52 + "\n")

    email      = input("Admin email:        ").strip().lower()
    first_name = input("First name:         ").strip()
    last_name  = input("Last name:          ").strip()
    phone      = input("Phone (+234...):    ").strip()
    password   = input("Password (hidden):  ").strip()

    if not email or not password or len(password) < 8:
        print("\n✗ Email and password (min 8 chars) are required.")
        sys.exit(1)

    engine  = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import uuid
    from datetime import datetime, timezone

    async with Session() as db:
        # Check for duplicate email
        row = (await db.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": email}
        )).fetchone()
        if row:
            print(f"\n✗ An account with email '{email}' already exists.")
            await engine.dispose()
            sys.exit(1)

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user_id = uuid.uuid4()
        now     = datetime.now(tz=timezone.utc)

        await db.execute(
            text("""
                INSERT INTO users
                    (id, email, phone, first_name, last_name,
                     password_hash, role, extra_roles, is_active, is_verified,
                     created_at, updated_at)
                VALUES
                    (:id, :email, :phone, :first_name, :last_name,
                     :pw, 'admin', '{}', true, true, :now, :now)
            """),
            {
                "id": str(user_id), "email": email, "phone": phone,
                "first_name": first_name, "last_name": last_name,
                "pw": pw_hash, "now": now,
            },
        )

        # Every user gets a wallet
        await db.execute(
            text("""
                INSERT INTO wallets (id, user_id, balance, ledger_balance, currency, updated_at)
                VALUES (:id, :uid, 0, 0, 'NGN', :now)
            """),
            {"id": str(uuid.uuid4()), "uid": str(user_id), "now": now},
        )

        await db.commit()

    await engine.dispose()

    print(f"\n✓ Admin account created.")
    print(f"  Email:  {email}")
    print(f"  Login at: /frontend/admin/index.html\n")


if __name__ == "__main__":
    asyncio.run(create_admin())
