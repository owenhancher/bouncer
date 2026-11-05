"""Virality score: mostly raw reach, boosted by velocity (views/day) and engagement (likes/views)."""
from __future__ import annotations

import math
from typing import Iterable, List

from .models import Video


def score(v: Video) -> float:
    views = v.views or 0
    s = 0.6 * math.log10(views + 1)
    vpd = v.views_per_day
    if vpd is not None:
        s += 0.4 * math.log10(vpd + 1)
    else:
        s += 0.4 * 0.5 * math.log10(views + 1)  # unknown age: assume middling velocity
    if v.likes and views:
        s += min(1.0, 10 * v.likes / views) * 0.5  # up to +0.5 for a 10%+ like rate
    return round(s, 3)


def rank(videos: Iterable[Video]) -> List[Video]:
    out = list(videos)
    for v in out:
        v.score = score(v)
    return sorted(out, key=lambda v: v.score, reverse=True)
