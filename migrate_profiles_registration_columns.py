"""One-time migration for any database that already had a `profiles` table before
`registration_source`/`registered_by` were added to `app.models.Profile`.

This project has no Alembic (or other migration framework) -- `app/main.py` only calls
`Base.metadata.create_all`, which creates missing tables but never ALTERs an existing
one. Run this once against any database provisioned before that change; it is a no-op
(skips already-present columns, and does nothing at all if `profiles` doesn't exist yet)
if run again or against a fresh database that `create_all` will set up correctly on its
own.
"""

from sqlalchemy import inspect, text

from app.database import engine

inspector = inspect(engine)

if not inspector.has_table("profiles"):
    print("profiles table does not exist yet -- nothing to migrate; "
          "Base.metadata.create_all will create it with the current schema.")
else:
    existing_columns = {col["name"] for col in inspector.get_columns("profiles")}

    with engine.begin() as conn:
        if "registration_source" not in existing_columns:
            conn.execute(text(
                "ALTER TABLE profiles ADD COLUMN registration_source VARCHAR NOT NULL "
                "DEFAULT 'partner_assisted'"
            ))
            print("Added profiles.registration_source")
        else:
            print("profiles.registration_source already present, skipping")

        if "registered_by" not in existing_columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN registered_by VARCHAR"))
            print("Added profiles.registered_by")
        else:
            print("profiles.registered_by already present, skipping")

        if "resolved_lat" not in existing_columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN resolved_lat DOUBLE PRECISION"))
            print("Added profiles.resolved_lat")
        else:
            print("profiles.resolved_lat already present, skipping")

        if "resolved_lon" not in existing_columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN resolved_lon DOUBLE PRECISION"))
            print("Added profiles.resolved_lon")
        else:
            print("profiles.resolved_lon already present, skipping")

        if "resolved_place_name" not in existing_columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN resolved_place_name VARCHAR"))
            print("Added profiles.resolved_place_name")
        else:
            print("profiles.resolved_place_name already present, skipping")
