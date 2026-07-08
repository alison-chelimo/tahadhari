from abc import ABC, abstractmethod

from ..schemas import Profile


class ProfileNotFoundError(Exception):
    def __init__(self, profile_id: int):
        super().__init__(f"profile {profile_id} not found")
        self.profile_id = profile_id


class ProfilesRepo(ABC):
    """Abstract contract. A future ApiProfilesRepo (once Person One wires up
    app/routers/profiles.py) should implement this same interface, calling
    GET /profiles/{id} and GET /profiles instead of reading in-memory data --
    callers (template_selector, personalizer, main.py) must not need to change."""

    @abstractmethod
    async def get_profile(self, profile_id: int) -> Profile: ...

    @abstractmethod
    async def list_profiles(self) -> list[Profile]: ...


DEFAULT_MOCK_PROFILES: list[Profile] = [
    # rural/ward track, all pinned to ward="Kisumu_Central" to match seeded test alert id 1 (65mm, high)
    Profile(id=1, phone_number="+254712345001", channel="whatsapp", language="en",
            user_type="rural", occupation="farmer", ward="Kisumu_Central", key_asset="maize_farm"),
    Profile(id=2, phone_number="+254712345002", channel="sms", language="en",
            user_type="rural", occupation="fisherman", ward="Kisumu_Central", key_asset="fishing_boat"),
    Profile(id=3, phone_number="+254712345003", channel="whatsapp", language="sw",
            user_type="rural", occupation="farmer", ward="Kisumu_Central", key_asset="maize_farm"),
    # urban/corridor track, route_id values matching 3 of the 7 seeded Ngong_Road segments,
    # to match seeded test alert id 2 (Ngong_Road, 40mm, medium)
    Profile(id=4, phone_number="+254712345004", channel="whatsapp", language="en",
            user_type="urban", occupation="driver", route_id="Adams_Arcade", key_asset="matatu_route_46"),
    Profile(id=5, phone_number="+254712345005", channel="sms", language="en",
            user_type="urban", occupation="driver", route_id="Dagoretti_Corner", key_asset="motorbike"),
    Profile(id=6, phone_number="+254712345006", channel="whatsapp", language="sw",
            user_type="urban", occupation="driver", route_id="Kilimani_Junction", key_asset="delivery_van"),
]


class MockProfilesRepo(ProfilesRepo):
    def __init__(self, profiles: list[Profile] | None = None):
        self._profiles = {p.id: p for p in (profiles or DEFAULT_MOCK_PROFILES)}

    async def get_profile(self, profile_id: int) -> Profile:
        try:
            return self._profiles[profile_id]
        except KeyError:
            raise ProfileNotFoundError(profile_id)

    async def list_profiles(self) -> list[Profile]:
        return list(self._profiles.values())
