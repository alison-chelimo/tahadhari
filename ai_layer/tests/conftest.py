from datetime import datetime, timezone

import pytest

from ai_layer.schemas import Alert, Profile, ActionTemplate, Message


@pytest.fixture
def sample_alert_ward() -> Alert:
    return Alert(
        id=1, hazard_type="heavy_rainfall", severity="high",
        geography_type="ward", geography_ref="Kisumu_Central",
        rainfall_mm=65.0, created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_profile_farmer() -> Profile:
    return Profile(
        id=1, phone_number="+254712345001", channel="whatsapp",
        language="en", user_type="rural", occupation="farmer",
        ward="Kisumu_Central", key_asset="maize_farm",
    )


@pytest.fixture
def sample_profile_farmer_sw() -> Profile:
    return Profile(
        id=3, phone_number="+254712345003", channel="whatsapp",
        language="sw", user_type="rural", occupation="farmer",
        ward="Kisumu_Central", key_asset="maize_farm",
    )


@pytest.fixture
def sample_template() -> ActionTemplate:
    return ActionTemplate(
        id=1, hazard_type="heavy_rainfall", occupation="farmer",
        severity="high", language="en",
        template_text=(
            "Heavy rainfall expected in {ward} within 24 hours. "
            "Delay planting by 48 hours."
        ),
    )


@pytest.fixture
def sample_message() -> Message:
    return Message(
        id=10, profile_id=1, alert_id=1, template_id=1, flood_prediction_id=None,
        final_text="Heavy rainfall expected in Kisumu_Central within 24 hours. Delay planting by 48 hours.",
        channel="whatsapp", delivery_status="pending", sent_at=datetime.now(timezone.utc),
    )
