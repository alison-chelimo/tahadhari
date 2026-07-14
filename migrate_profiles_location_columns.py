"""One-time migration for any database that already had `profiles`/`registration_requests`
tables before the location-conversation columns were added to `app.models.Profile` and
`app.models.RegistrationRequest`.

This project has no Alembic (or other migration framework) -- `app/main.py` only calls
`Base.metadata.create_all`, which creates missing tables but never ALTERs an existing
one. Run this once against any database provisioned before that change; it is a no-op
(skips already-present columns, and does nothing at all if a table doesn't exist yet)
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
        for column_name, ddl in (
            ("resolved_lat", "ALTER TABLE profiles ADD COLUMN resolved_lat FLOAT"),
            ("resolved_lon", "ALTER TABLE profiles ADD COLUMN resolved_lon FLOAT"),
            ("resolved_place_name", "ALTER TABLE profiles ADD COLUMN resolved_place_name VARCHAR"),
        ):
            if column_name not in existing_columns:
                conn.execute(text(ddl))
                print(f"Added profiles.{column_name}")
            else:
                print(f"profiles.{column_name} already present, skipping")

if not inspector.has_table("registration_requests"):
    print("registration_requests table does not exist yet -- nothing to migrate; "
          "Base.metadata.create_all will create it with the current schema.")
else:
    existing_columns = {col["name"] for col in inspector.get_columns("registration_requests")}

    with engine.begin() as conn:
        for column_name, ddl in (
            ("state", "ALTER TABLE registration_requests ADD COLUMN state VARCHAR"),
            ("raw_location_text", "ALTER TABLE registration_requests ADD COLUMN raw_location_text VARCHAR"),
        ):
            if column_name not in existing_columns:
                conn.execute(text(ddl))
                print(f"Added registration_requests.{column_name}")
            else:
                print(f"registration_requests.{column_name} already present, skipping")
