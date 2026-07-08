import pytest

from ai_layer.services.personalizer import (
    build_placeholder_values,
    fill_placeholders,
    MissingPlaceholderValueError,
    LeftoverPlaceholderError,
)


def test_fill_placeholders_happy_path(sample_alert_ward, sample_profile_farmer, sample_template):
    values = build_placeholder_values(sample_alert_ward, sample_profile_farmer)
    assert values["ward"] == "Kisumu_Central"
    assert values["occupation"] == "farmer"
    assert values["key_asset"] == "maize_farm"

    filled = fill_placeholders(sample_template.template_text, values)

    assert "{" not in filled and "}" not in filled
    assert "Kisumu_Central" in filled


def test_fill_placeholders_missing_value_raises():
    with pytest.raises(MissingPlaceholderValueError) as exc_info:
        fill_placeholders("Contact {key_asset} owner", {})
    assert exc_info.value.placeholder_name == "key_asset"


def test_fill_placeholders_leftover_token_raises():
    with pytest.raises(LeftoverPlaceholderError) as exc_info:
        fill_placeholders("Rainfall {rainfall_mm} expected {when?}", {"rainfall_mm": "40"})
    assert exc_info.value.leftover_text == "{when?}"
