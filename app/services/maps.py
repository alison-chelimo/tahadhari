import os
from urllib.parse import urlencode


def build_segment_map_url(
    *,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    width: int = 700,
    height: int = 380,
) -> str:
    provider = os.getenv("MAP_PROVIDER", "osm").lower()

    if provider == "mapbox":
        token = os.getenv("MAPBOX_ACCESS_TOKEN")
        if token:
            midpoint_lat = (start_lat + end_lat) / 2
            midpoint_lon = (start_lon + end_lon) / 2
            return (
                "https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/"
                f"pin-s-a+f44({start_lon},{start_lat}),pin-s-b+3b82f6({end_lon},{end_lat})/"
                f"{midpoint_lon},{midpoint_lat},14/{width}x{height}?access_token={token}"
            )

    query = urlencode(
        {
            "size": f"{width}x{height}",
            "markers": (
                f"{start_lat},{start_lon},red-pushpin|"
                f"{end_lat},{end_lon},blue-pushpin"
            ),
        }
    )
    return f"https://staticmap.openstreetmap.de/staticmap.php?{query}"
