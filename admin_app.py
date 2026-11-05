"""Bouncer Video Scout — admin / curation console. NOT part of the public site.

Run locally:  BOUNCER_ADMIN_PASSWORD=... streamlit run admin_app.py --server.port 8502
Refuses to start without BOUNCER_ADMIN_PASSWORD. Flow: Discover -> Library (pick) -> Clip -> Post (or Autopost).
"""
import hmac
import os
from pathlib import Path

import streamlit as st

from video_scout import clipper, config, licenses, posting
from video_scout.discover import DEFAULT_QUERIES, discover
from video_scout.embeds import embed_html, from_url
from video_scout.site import show_html
from video_scout.rights import RightsError, assert_reusable
from video_scout.store import Store

st.set_page_config(page_title="Bouncer Video Scout · Admin", page_icon="assets/bouncer-favicon.png", layout="wide")
INK, VELVET, PAPER = "#14161B", "#B3243A", "#F5F1E8"
st.markdown(f"""<style>.stButton>button[kind="primary"]{{background:{VELVET};border-color:{VELVET}}}
h1,h2,h3{{color:{INK}}} .vs-tag{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.78rem;font-weight:700}}
.vs-ok{{background:#1F6B3A;color:#fff}} .vs-no{{background:#DDD5C5;color:{INK}}}</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- password gate
PW = os.environ.get("BOUNCER_ADMIN_PASSWORD", "")
if not PW:
    st.error("Admin is disabled: set BOUNCER_ADMIN_PASSWORD in the environment to enable it.")
    st.stop()
if not st.session_state.get("vs_authed"):
    st.title("Bouncer Video Scout · Admin")
    pw = st.text_input("Admin password", type="password")
    if st.button("Enter", type="primary"):
        if hmac.compare_digest(pw.encode(), PW.encode()):
            st.session_state.vs_authed = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()


@st.cache_resource
def _store():
    return Store()


store = _store()
st.title("Bouncer Video Scout")
st.caption("Discover → pick → clip to 9:16 → post. Only free-reuse licensed videos can be clipped or posted; "
           "everything else can only be shown on the site through its official embed.")


def lic_tag(v):
    cls = "vs-ok" if v.reusable else "vs-no"
    txt = f"{v.license_code} · clippable" if v.reusable else f"{v.license_code} · embed only"
    return f'<span class="vs-tag {cls}">{txt}</span>'


t_disc, t_lib, t_clip, t_post, t_auto, t_log = st.tabs(
    ["1 · Discover", "2 · Library / pick", "3 · Clip", "4 · Post", "Autopost", "Log & credentials"])

# ---------------------------------------------------------------- 1. Discover
with t_disc:
    c1, c2, c3 = st.columns([3, 1, 1])
    q = c1.text_input("Search", value=DEFAULT_QUERIES[0], help="e.g. hotel room tour, overwater villa, capsule hotel")
    n = c2.number_input("Limit", 5, 50, 20)
    licensed = c3.toggle("Licensed only (clippable)", value=True)
    provs = st.multiselect("Providers (blank = all available)",
                           ["youtube", "youtube_api", "commons", "archive", "pexels", "pixabay", "rapidapi"])
    if st.button("Discover", type="primary"):
        with st.spinner("Searching… (YouTube license checks take ~1 s per video)"):
            res = discover(q, limit=int(n), licensed=licensed, provider_names=provs or None, store=store)
        st.success(f"{res['count']} videos from {', '.join(res['providers'])}. Saved to the library.")
        if res["errors"]:
            st.warning(f"Provider errors: {res['errors']}")
    st.divider()
    url = st.text_input("Or add a known post URL (TikTok / Instagram / X / YouTube) — embed-only")
    if st.button("Add URL") and url:
        try:
            v = store.upsert(from_url(url))
            st.success(f"Added {v.id}: {v.title or v.url}")
        except Exception as e:
            st.error(str(e))

# ---------------------------------------------------------------- 2. Library
with t_lib:
    f1, f2, f3 = st.columns(3)
    only_lic = f1.toggle("Clippable only", value=False)
    status = f2.selectbox("Status", ["any", "new", "approved", "rejected"])
    lim = f3.number_input("Show", 10, 200, 40)
    vids = store.list(limit=int(lim), status=None if status == "any" else status, reusable=True if only_lic else None)
    st.caption(f"{len(vids)} videos, ranked by virality score (views + views/day + like rate).")
    for v in vids:
        with st.container(border=True):
            a, b = st.columns([1, 3])
            if v.thumbnail:
                a.image(v.thumbnail, width="stretch")
            b.markdown(f"**{v.title[:110]}**  \n{v.creator} · {v.platform} · "
                       f"{(v.views or 0):,} views · {v.views_per_day or '–'}/day · {v.published or '–'} · "
                       f"score {v.score}  \n{lic_tag(v)} &nbsp; status: `{v.status}`"
                       f"{' · **on site**' if v.show_on_site else ''}  \n"
                       f"Hotel: {v.hotel_guess or '–'} · Place: {v.location_guess or '–'} · [open ↗]({v.url}) · `{v.id}`",
                       unsafe_allow_html=True)
            k1, k2, k3, k4 = b.columns(4)
            if k1.button("Approve", key=f"ap{v.id}"):
                store.set_status(v.id, "approved"); st.rerun()
            if k2.button("Reject", key=f"rj{v.id}"):
                store.set_status(v.id, "rejected"); st.rerun()
            if k3.button("Remove from site" if v.show_on_site else "Show on site (embed)", key=f"os{v.id}"):
                store.set_on_site(v.id, not v.show_on_site); store.export_site_json(); st.rerun()
            if v.reusable and k4.button("Clip this →", key=f"cl{v.id}", type="primary"):
                st.session_state.clip_vid = v.id
                st.info("Selected. Open the **3 · Clip** tab.")
    st.caption("“Show on site” writes video_scout/site_videos.json. Commit it and set BOUNCER_SHOW_VIDEOS=1 to go live.")

# ---------------------------------------------------------------- 3. Clip
with t_clip:
    clippable = store.list(limit=300, reusable=True)
    if not clippable:
        st.info("No licensed videos yet. Discover with “Licensed only” on.")
    else:
        ids = [v.id for v in clippable]
        default = ids.index(st.session_state.clip_vid) if st.session_state.get("clip_vid") in ids else 0
        vid = st.selectbox("Licensed video", ids, index=default,
                           format_func=lambda i: f"{store.get(i).title[:70]} · {store.get(i).license_code} · {i}")
        v = store.get(vid)
        st.markdown(f"[{v.title}]({v.url}) by **{v.creator}** · {v.license_name} · duration {v.duration or '?'} s")
        markup, h = embed_html(v, width=420)
        show_html(st, markup, min(h, 700))
        c1, c2, c3 = st.columns(3)
        start = c1.text_input("Start (s or mm:ss)", "0")
        end = c2.text_input("End (s or mm:ss)", "20")
        cap = c3.text_input("On-video caption (optional)", (v.hotel_guess or "")[:40])
        o1, o2 = st.columns(2)
        vertical = o1.checkbox("9:16 vertical crop (Reels/Shorts)", value=True)
        wm = o2.checkbox("Bouncer watermark", value=True)
        st.caption(f"Attribution burned in automatically: “{licenses.attribution(v.creator, v.license_code, None, v.license_name)}”")
        if st.button("Make clip", type="primary"):
            try:
                with st.spinner("Downloading source + rendering with ffmpeg…"):
                    out = clipper.clip_video(v, start, end, vertical=vertical, watermark=wm, caption=cap)
                cid = store.add_clip(video_id=v.id, path=out["path"], thumb=out["thumbnail"],
                                     start=clipper._parse_time(start), end=clipper._parse_time(end), vertical=int(vertical),
                                     watermark=int(wm), caption=cap, attribution="auto", probe=out["probe"])
                st.session_state.post_clip = cid
                st.success(f"Clip #{cid} ready · {out['probe']}. Open **4 · Post**.")
            except RightsError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Clip failed: {e}")
    st.divider()
    st.markdown("**Clip a local file** (Bouncer's own footage or a file you have under a free-reuse license)")
    up = st.file_uploader("Video file", type=["mp4", "mov", "webm", "mkv"])
    l1, l2, l3 = st.columns(3)
    up_lic = l1.selectbox("License", list(licenses.ALLOWED))
    up_creator = l2.text_input("Creator (required unless OWN)")
    up_src = l3.text_input("Source URL")
    u1, u2 = st.columns(2)
    up_start, up_end = u1.text_input("Start", "0", key="us"), u2.text_input("End", "15", key="ue")
    if up and st.button("Clip uploaded file"):
        from video_scout.models import Video
        p = config.downloads_dir() / f"upload_{Path(up.name).name}"
        p.write_bytes(up.getbuffer())
        uv = Video(id=f"upload:{p.stem}", platform="upload", url=up_src, title=up.name,
                   creator=up_creator or ("Bouncer Travel" if up_lic == "OWN" else ""), license_code=up_lic,
                   license_name=licenses.label(up_lic), source="upload")
        try:
            assert_reusable(uv)
            store.upsert(uv)
            attr = "" if up_lic == "OWN" else licenses.attribution(uv.creator, up_lic, None, uv.license_name)
            out = clipper.clip(p, up_start, up_end, vertical=True, watermark=True, attribution=attr)
            cid = store.add_clip(video_id=uv.id, path=out["path"], thumb=out["thumbnail"], start=clipper._parse_time(up_start),
                                 end=clipper._parse_time(up_end), vertical=1, watermark=1, caption="", attribution=attr,
                                 probe=out["probe"])
            st.session_state.post_clip = cid
            st.success(f"Clip #{cid} ready. Open **4 · Post**.")
        except Exception as e:
            st.error(str(e))

# ---------------------------------------------------------------- 4. Post
with t_post:
    clips = store.clips(50)
    if not clips:
        st.info("No clips yet. Make one in **3 · Clip**.")
    else:
        cids = [c["id"] for c in clips]
        d = cids.index(st.session_state.post_clip) if st.session_state.get("post_clip") in cids else 0
        cid = st.selectbox("Clip", cids, index=d, format_func=lambda i: f"#{i} · {store.get_clip(i)['video_id']}")
        c = store.get_clip(cid)
        v = store.get(c["video_id"])
        a, b = st.columns([1, 2])
        if Path(c["path"]).exists():
            a.video(c["path"])
        caption = b.text_area("Caption (attribution + hashtags are added automatically)", v.title if v else "", height=110)
        tags = b.text_input("Hashtags", posting.DEFAULT_TAGS)
        plats = b.multiselect("Platforms", ["ig", "fb", "x"], default=["ig", "fb", "x"],
                              format_func=lambda p: {"ig": "Instagram Reel", "fb": "Facebook Page", "x": "X"}[p])
        cs = posting.creds_status()
        b.caption(" · ".join(f"{p}: {'live' if cs[p]['ready'] else 'package only (no creds)'}" for p in ["ig", "fb", "x"]))
        if v:
            with b.expander("Preview captions"):
                for p in plats:
                    st.text_area(p, posting.build_caption(v, caption, tags, p), height=120, key=f"pv{p}{cid}")
        if b.button("Post now", type="primary"):
            try:
                res = posting.publish(store, cid, plats, caption=caption, hashtags=tags, mode="manual")
                for r in res["results"]:
                    (st.success if r["status"] == "posted" else st.warning)(f"{r['platform']}: {r['status']} {r['url']} {r['detail']}")
                if res["package_dir"]:
                    st.info(f"Ready-to-post package: `{res['package_dir']}`")
                if res.get("x_intent"):
                    st.link_button("Open X composer (attach the clip yourself)", res["x_intent"])
            except RightsError as e:
                st.error(str(e))

# ---------------------------------------------------------------- Autopost
with t_auto:
    st.markdown(f"Finds licensed hotel videos, picks the top unposted one (approved first), clips 20 s at 9:16 with "
                f"watermark + attribution, and posts to every platform with credentials. Cap: **{config.daily_cap()}** "
                f"posts/platform/day (`VIDEO_SCOUT_DAILY_CAP`). Never posts the same video twice to one platform.")
    ap_plats = st.multiselect("Platforms", ["ig", "fb", "x"], default=["ig", "fb", "x"], key="apl")
    nodisc = st.checkbox("Use library only (skip discovery)")
    dry = st.checkbox("Dry run (clip but don't post)")
    if st.button("Run autopost now", type="primary"):
        from video_scout import autopost
        with st.spinner("Running…"):
            try:
                st.json(autopost.run(platforms=ap_plats, discover_first=not nodisc, dry_run=dry, store=store))
            except Exception as e:
                st.error(str(e))

# ---------------------------------------------------------------- Log
with t_log:
    st.subheader("Credentials (presence only)")
    st.json({p: {"ready": s["ready"], "needs": s["needs"]} for p, s in posting.creds_status().items()})
    st.subheader("Posted log")
    st.dataframe(store.posts(100), width="stretch")
    st.subheader("Clips")
    st.dataframe(store.clips(100), width="stretch")
