from app.schemas import ROUTE_ID_PATTERN as app_route_id_pattern
from ai_layer.schemas import ROUTE_ID_PATTERN as ai_layer_route_id_pattern


def test_route_id_pattern_matches_between_packages():
    """app/schemas.py and ai_layer/schemas.py intentionally duplicate ROUTE_ID_PATTERN
    by hand (the two packages are independently deployable with no cross-import). This
    test is the drift guard: if one copy is edited without the other, CI catches it here
    instead of the mismatch surfacing silently at runtime as inconsistent validation."""
    assert app_route_id_pattern.pattern == ai_layer_route_id_pattern.pattern
