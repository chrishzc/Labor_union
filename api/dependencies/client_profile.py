"""Composition root for administrative Client profile maintenance."""

from functools import lru_cache

from subsystems.client_profile.application import ClientProfileApplication
from subsystems.client_profile.mysql_unit_of_work import open_client_profile_unit_of_work


@lru_cache(maxsize=1)
def get_client_profile_application() -> ClientProfileApplication:
    return ClientProfileApplication(
        open_client_profile_unit_of_work,
    )
