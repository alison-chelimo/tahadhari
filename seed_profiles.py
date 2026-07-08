"""Seeds the real `profiles` table with the same 6 profiles ai_layer.clients.profiles_repo
uses in-memory as DEFAULT_MOCK_PROFILES, so POST /messages/'s profile_id foreign-key
check succeeds when running `python -m ai_layer.main` against a real database.

Caveat (same as seed_segments.py): Postgres auto-assigns primary keys, so ids only line
up with the hardcoded 1-6 that ai_layer.main and DEFAULT_MOCK_PROFILES expect if this is
run once against a fresh, empty `profiles` table.
"""

from app.database import SessionLocal
from app.models import Profile
from ai_layer.clients.profiles_repo import DEFAULT_MOCK_PROFILES

db = SessionLocal()

for p in DEFAULT_MOCK_PROFILES:
    db.add(Profile(
        phone_number=p.phone_number,
        channel=p.channel,
        language=p.language,
        user_type=p.user_type,
        occupation=p.occupation,
        ward=p.ward,
        route_id=p.route_id,
        key_asset=p.key_asset,
    ))

db.commit()
print(f"Seeded {len(DEFAULT_MOCK_PROFILES)} profiles.")
