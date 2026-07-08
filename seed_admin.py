"""Bootstraps the single admin account from ADMIN_USERNAME/ADMIN_PASSWORD env vars.

Caveat (same as seed_segments.py/seed_profiles.py): run once against a fresh DB. Running
it again against a DB that already has an admin_users row with that username will fail
on the unique constraint rather than update the existing account.
"""

import os

from app.auth import hash_password
from app.database import SessionLocal
from app.models import AdminUser

username = os.environ["ADMIN_USERNAME"]
password = os.environ["ADMIN_PASSWORD"]

db = SessionLocal()
db.add(AdminUser(username=username, hashed_password=hash_password(password)))
db.commit()
print(f"Seeded admin user {username!r}.")
