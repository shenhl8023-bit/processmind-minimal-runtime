from __future__ import annotations

from dataclasses import dataclass


ROUTE_RULES_PROFILE = "route_rules.document_rules"


@dataclass(frozen=True)
class ProfileDefinition:
    key: str
    mode: str
    label: str
    short_label: str
    description: str
    engine_type: str


PROFILE_REGISTRY: tuple[ProfileDefinition, ...] = (
    ProfileDefinition(
        key=ROUTE_RULES_PROFILE,
        mode="route_rules",
        label="工艺规程规则",
        short_label="规程提炼",
        description="上传典型工艺规程，提炼母路线、工序与影响因素，再生成固定工艺路线。",
        engine_type="llm_route_rules",
    ),
)


def list_profiles(mode: str | None = None) -> list[ProfileDefinition]:
    if not mode:
        return list(PROFILE_REGISTRY)
    return [profile for profile in PROFILE_REGISTRY if profile.mode == mode]


def get_profile(profile_key: str | None) -> ProfileDefinition | None:
    if not profile_key:
        return None
    for profile in PROFILE_REGISTRY:
        if profile.key == profile_key:
            return profile
    return None


def default_profile_for_mode(mode: str) -> str:
    return ROUTE_RULES_PROFILE


def normalize_profile(mode: str, profile_key: str | None) -> str:
    profile = get_profile(profile_key)
    if profile and profile.mode == mode:
        return profile.key
    return default_profile_for_mode(mode)
