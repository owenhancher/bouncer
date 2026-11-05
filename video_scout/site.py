"""Public site section "Hotels going viral" (official embeds only). OFF unless BOUNCER_SHOW_VIDEOS=1.
Reads the committed video_scout/site_videos.json (written by `embed-approve`), so it works on Railway
without the local SQLite store. Any failure renders nothing rather than breaking the page."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from . import config
from .embeds import embed_html
from .models import Video


def enabled() -> bool:
    return config.flag("BOUNCER_SHOW_VIDEOS")


def load_site_videos(path: Optional[Path] = None) -> List[Video]:
    p = Path(path or config.SITE_VIDEOS_JSON)
    if not p.exists():
        return []
    data = json.loads(p.read_text() or "{}")
    return [Video.from_dict(d) for d in data.get("videos", [])]


def show_html(st, markup: str, height: int) -> None:
    """Render trusted, escaped embed markup (built by embeds.embed_html) in an iframe."""
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:  # older Streamlit
        st_html(markup, height=height, scrolling=False)


def render(st, max_items: int = 6, columns: int = 3) -> None:
    if not enabled():
        return
    try:
        vids = load_site_videos()[:max_items]
        if not vids:
            return
        st.markdown("### Hotels going viral")
        st.caption("Hand-picked hotel videos from around the web. Each plays from its original creator's post.")
        cols = st.columns(min(columns, len(vids)))
        for i, v in enumerate(vids):
            with cols[i % len(cols)]:
                markup, h = embed_html(v, width=520)
                show_html(st, markup, h)
    except Exception:  # never take the live site down for a widget
        return
