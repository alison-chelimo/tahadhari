import pytest

from ai_layer.clients.profiles_repo import (
    DEFAULT_MOCK_PROFILES,
    MockProfilesRepo,
    ProfileNotFoundError,
)


@pytest.mark.asyncio
async def test_get_profile_returns_matching_profile():
    repo = MockProfilesRepo()
    profile = await repo.get_profile(1)
    assert profile.id == 1
    assert profile.occupation == "farmer"


@pytest.mark.asyncio
async def test_get_profile_raises_for_unknown_id():
    repo = MockProfilesRepo()
    with pytest.raises(ProfileNotFoundError) as exc_info:
        await repo.get_profile(999)
    assert exc_info.value.profile_id == 999


@pytest.mark.asyncio
async def test_list_profiles_returns_all_default_profiles():
    repo = MockProfilesRepo()
    profiles = await repo.list_profiles()
    assert len(profiles) == len(DEFAULT_MOCK_PROFILES)
    assert {p.id for p in profiles} == {p.id for p in DEFAULT_MOCK_PROFILES}


@pytest.mark.asyncio
async def test_repo_accepts_custom_profile_list(sample_profile_farmer):
    repo = MockProfilesRepo(profiles=[sample_profile_farmer])
    profiles = await repo.list_profiles()
    assert profiles == [sample_profile_farmer]

    fetched = await repo.get_profile(sample_profile_farmer.id)
    assert fetched == sample_profile_farmer

    with pytest.raises(ProfileNotFoundError):
        await repo.get_profile(sample_profile_farmer.id + 1000)
