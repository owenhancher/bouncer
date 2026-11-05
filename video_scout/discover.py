"""Discovery orchestration + `python -m video_scout.discover` shortcut."""
from __future__ import annotations

import sys
from typing import Dict, List, Optional

from . import providers as P
from .models import Video
from .guess import is_hotel_related
from .ranking import rank
from .store import Store

DEFAULT_QUERIES = ["hotel room tour", "luxury hotel tour", "viral hotel", "hotel review shorts", "resort tour"]


def discover(query: str, limit: int = 25, licensed: bool = False, provider_names: Optional[List[str]] = None,
             store: Optional[Store] = None, hotel_only: bool = True) -> Dict:
    store = store or Store()
    found: List[Video] = []
    errors: Dict[str, str] = {}
    used = []
    for p in P.build(provider_names):
        try:
            res = p.search(query, limit=limit, licensed=licensed)
            used.append(p.name)
            found.extend(res)
        except Exception as e:  # one provider failing never sinks the run
            errors[p.name] = str(e)[:300]
    if hotel_only:  # view-sorted search drifts off-topic (e.g. "$1 vs $100M House"); keep hotel-ish titles
        found = [v for v in found if is_hotel_related(v.title, v.hotel_guess)]
    ranked = rank({v.id: v for v in found}.values())
    for v in ranked:
        store.upsert(v)
    return {"query": query, "licensed_only": licensed, "providers": used, "errors": errors,
            "count": len(ranked), "videos": [summary(v) for v in ranked[:limit]]}


def summary(v: Video) -> Dict:
    return {"id": v.id, "platform": v.platform, "title": v.title, "creator": v.creator, "url": v.url,
            "views": v.views, "likes": v.likes, "published": v.published, "views_per_day": v.views_per_day,
            "score": v.score, "hotel_guess": v.hotel_guess, "location_guess": v.location_guess,
            "license": v.license_code, "reusable": v.reusable, "status": v.status, "on_site": v.show_on_site,
            "thumbnail": v.thumbnail}


if __name__ == "__main__":
    from .cli import main
    sys.exit(main(["discover", *sys.argv[1:]]))
