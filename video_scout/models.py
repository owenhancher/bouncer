from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from . import licenses


@dataclass
class Video:
    id: str                      # stable id, e.g. "youtube:abc123", "commons:File:X.webm"
    platform: str                # youtube | tiktok | instagram | x | commons | archive | pexels | pixabay | upload
    url: str                     # canonical public page (link-back target)
    title: str = ""
    creator: str = ""
    creator_url: str = ""
    views: Optional[int] = None
    likes: Optional[int] = None
    published: Optional[str] = None   # YYYY-MM-DD
    duration: Optional[float] = None
    thumbnail: str = ""
    hotel_guess: str = ""
    location_guess: str = ""
    license_code: str = "UNKNOWN"     # see licenses.ALLOWED
    license_name: str = ""
    license_url: str = ""
    download_url: str = ""            # direct media URL when the source offers one (stock/commons/archive)
    source: str = ""                  # provider name
    query: str = ""
    score: float = 0.0
    status: str = "new"               # new | approved | rejected
    show_on_site: bool = False
    embed_html: str = ""              # oEmbed html when known
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def reusable(self) -> bool:
        return licenses.is_allowed(self.license_code)

    @property
    def age_days(self) -> Optional[int]:
        if not self.published:
            return None
        try:
            d = date.fromisoformat(self.published[:10])
        except ValueError:
            return None
        return max(1, (date.today() - d).days)

    @property
    def views_per_day(self) -> Optional[float]:
        if self.views is None or self.age_days is None:
            return None
        return round(self.views / self.age_days, 1)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reusable"] = self.reusable
        d["views_per_day"] = self.views_per_day
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Video":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: d[k] for k in keys if k in d})
