"""Stable boundary around the legacy finalized rule package interpreter."""

from app.services.finalized_route_generator import generate_steps_from_finalized_rule_package


def generate_v1_route(*args, **kwargs):
    return generate_steps_from_finalized_rule_package(*args, **kwargs)
