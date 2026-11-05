"""The one gate every download / clip / post goes through."""
from __future__ import annotations

from . import licenses
from .models import Video


class RightsError(PermissionError):
    pass


def assert_reusable(v: Video) -> None:
    if not licenses.is_allowed(v.license_code):
        raise RightsError(
            f"{v.id} has license {v.license_code!r}: not free-reuse. It may only be shown on the site via its "
            f"official embed (embed-approve). Clip/repost needs one of {sorted(licenses.ALLOWED)}; "
            f"{licenses.BLOCKED_HINT}.")
    if licenses.ALLOWED[v.license_code.upper()][1] and not (v.creator or "").strip():
        raise RightsError(f"{v.id} is {v.license_code} but has no creator recorded; attribution is required.")
