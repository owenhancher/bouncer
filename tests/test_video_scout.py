"""Video Scout tests: mock providers, fake HTTP sessions, no network. ffmpeg test is skipped if ffmpeg is missing."""
import json
import shutil
import subprocess
import urllib.parse

import pytest

from video_scout import autopost, cli, embeds, licenses, posting, ranking
from video_scout.guess import guess, is_hotel_related, is_safe_for_autopost
from video_scout.models import Video
from video_scout.rights import RightsError, assert_reusable
from video_scout.store import Store

CRED_VARS = ["X_USER_ACCESS_TOKEN", "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
             "META_PAGE_ACCESS_TOKEN", "IG_USER_ID", "FB_PAGE_ID"]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_SCOUT_DATA_DIR", str(tmp_path / "vs"))
    monkeypatch.delenv("VIDEO_SCOUT_DB", raising=False)
    monkeypatch.delenv("VIDEO_SCOUT_DAILY_CAP", raising=False)
    monkeypatch.delenv("VIDEO_SCOUT_PROVIDERS", raising=False)
    for n in CRED_VARS:
        monkeypatch.delenv(n, raising=False)
    # never touch the committed site JSON from tests
    monkeypatch.setattr("video_scout.config.SITE_VIDEOS_JSON", tmp_path / "site_videos.json")
    yield


def vid(**kw):
    base = dict(id="youtube:abc", platform="youtube", url="https://www.youtube.com/watch?v=abcdefghijk", title="Hotel room tour",
                creator="Jane", views=1000, published="2025-01-01", duration=60.0, license_code="CC-BY",
                license_name="CC BY 4.0", download_url="https://example.com/a.mp4")
    base.update(kw)
    return Video(**base)


def fake_clip(v, start, end, **kw):
    assert_reusable(v)
    return {"path": "/tmp/fake_clip.mp4", "thumbnail": "/tmp/fake_clip.jpg", "probe": {"duration": end - start}}


# ------------------------------------------------------------------ licenses / rights
@pytest.mark.parametrize("text,code,ok", [
    ("Creative Commons Attribution license (reuse allowed)", "CC-BY", True),
    ("https://creativecommons.org/licenses/by-sa/4.0/", "CC-BY-SA", True),
    ("CC0 1.0 Universal", "CC0", True),
    ("Public domain", "PD", True),
    ("https://creativecommons.org/licenses/by-nc/4.0/", "NC-OR-ND", False),
    ("CC BY-ND 4.0", "NC-OR-ND", False),
    ("CC BY-NC-SA 3.0", "NC-OR-ND", False),
    ("", "UNKNOWN", False),
])
def test_license_classify(text, code, ok):
    c, allowed = licenses.classify(text, text if text.startswith("http") else "")
    assert c == code and allowed is ok


def test_attribution_text():
    assert licenses.attribution("Jane", "CC-BY", None, "CC BY 4.0").startswith("Video: Jane / CC BY 4.0")
    assert "edited" in licenses.attribution("Jane", "CC-BY", None, "CC BY 4.0")
    assert licenses.attribution("", "OWN") == "Video: Bouncer Travel"


def test_rights_gate_refuses_unlicensed():
    for code in ("YOUTUBE-STANDARD", "NC-OR-ND", "UNKNOWN", "CC-UNSPECIFIED"):
        with pytest.raises(RightsError):
            assert_reusable(vid(license_code=code))
    with pytest.raises(RightsError):  # attribution licenses need a creator
        assert_reusable(vid(creator=""))
    assert_reusable(vid())


def test_clipper_refuses_before_download(monkeypatch):
    from video_scout import clipper
    monkeypatch.setattr(clipper.subprocess, "run", lambda *a, **k: pytest.fail("must not download"))
    with pytest.raises(RightsError):
        clipper.clip_video(vid(license_code="YOUTUBE-STANDARD"), 0, 5)
    with pytest.raises(RightsError):
        clipper.download(vid(license_code="NC-OR-ND"))


# ------------------------------------------------------------------ ranking / guess / store
def test_ranking_prefers_viral():
    a = vid(id="a", views=10_000_000, published="2025-06-01", likes=400_000)
    b = vid(id="b", views=50_000, published="2025-06-01")
    c = vid(id="c", views=10_000_000, published="2015-06-01")
    order = [v.id for v in ranking.rank([b, c, a])]
    assert order[0] == "a" and order[-1] == "b"


def test_guess_and_filters():
    h, p = guess("Inside the Burj Al Arab Dubai royal suite")
    assert "Burj Al Arab" in h and p == "Dubai"
    assert is_hotel_related("Overwater villa tour") and not is_hotel_related("Cooking pasta")
    assert not is_safe_for_autopost("Vegas Shooter's Hotel Room Tour")
    assert is_safe_for_autopost("Plaza Hotel suite tour")


def test_store_roundtrip_and_curation(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert(vid())
    s.set_on_site("youtube:abc", True)
    s.upsert(vid(views=99))  # re-discovery keeps curation, refreshes metrics
    v = s.get("youtube:abc")
    assert v.show_on_site and v.status == "approved" and v.views == 99
    s.set_status("youtube:abc", "rejected")
    assert not s.get("youtube:abc").show_on_site
    assert [x.id for x in s.list(reusable=True)] == ["youtube:abc"]
    out = s.export_site_json(tmp_path / "site.json")
    assert json.loads(out.read_text())["videos"] == []


# ------------------------------------------------------------------ embeds
@pytest.mark.parametrize("url,plat,nid", [
    ("https://www.youtube.com/watch?v=iogcY_4xGjo", "youtube", "iogcY_4xGjo"),
    ("https://youtu.be/iogcY_4xGjo", "youtube", "iogcY_4xGjo"),
    ("https://www.youtube.com/shorts/abcDEF12345", "youtube", "abcDEF12345"),
    ("https://www.tiktok.com/@user/video/7234567890123456789", "tiktok", "7234567890123456789"),
    ("https://www.instagram.com/reel/C1a2b3c4/", "instagram", "C1a2b3c4"),
    ("https://x.com/someone/status/1234567890", "x", "1234567890"),
])
def test_detect(url, plat, nid):
    assert embeds.detect(url) == (plat, nid)


def test_embed_html_credit_and_escaping():
    v = vid(license_code="YOUTUBE-STANDARD", title='<script>alert(1)</script>', creator="MrBeast")
    html, h = embeds.embed_html(v)
    assert "youtube-nocookie.com/embed/abcdefghijk" in html and "MrBeast" in html and "Watch original" in html
    assert "<script>alert" not in html and h > 200
    for url, needle in [("https://www.tiktok.com/@u/video/123", "tiktok.com/player/v1/123"),
                        ("https://www.instagram.com/reel/XYZ/", "instagram-media"),
                        ("https://x.com/u/status/42", "twitter-tweet")]:
        assert needle in embeds.embed_html(vid(url=url, license_code="UNKNOWN"))[0]
    commons = vid(id="commons:1", platform="commons", url="https://commons.wikimedia.org/wiki/File:A.webm",
                  license_code="CC-BY-SA", license_name="CC BY-SA 4.0")
    assert "<video" in embeds.embed_html(commons)[0]


def test_site_section_reads_json(tmp_path, monkeypatch):
    from video_scout import config, site
    s = Store(tmp_path / "t.db")
    s.upsert(vid(license_code="YOUTUBE-STANDARD"))
    s.set_on_site("youtube:abc", True)
    s.export_site_json()
    assert [v.id for v in site.load_site_videos(config.SITE_VIDEOS_JSON)] == ["youtube:abc"]
    monkeypatch.delenv("BOUNCER_SHOW_VIDEOS", raising=False)
    assert not site.enabled()
    monkeypatch.setenv("BOUNCER_SHOW_VIDEOS", "1")
    assert site.enabled()


# ------------------------------------------------------------------ captions / posting
def test_caption_attribution_and_x_limit():
    v = vid(title="x" * 400)
    x = posting.build_caption(v, "y" * 400, platform="x")
    weighted = len(x) - len(v.url) + 23  # X counts every URL as 23 chars
    assert weighted <= 280 and "Video: Jane / CC BY 4.0" in x and x.endswith("#hotels #travel")
    ig = posting.build_caption(v, "Nice suite", platform="ig")
    assert "Video: Jane / CC BY 4.0" in ig and "Only real deals get in." in ig


def _store_with_clip(tmp_path, **kw):
    s = Store(tmp_path / "p.db")
    v = s.upsert(vid(**kw))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00" * 2048)
    cid = s.add_clip(video_id=v.id, path=str(clip), thumb="", start=0, end=5, vertical=1, watermark=1,
                     caption="", attribution="auto", probe={})
    return s, cid


def test_publish_without_creds_makes_package(tmp_path):
    s, cid = _store_with_clip(tmp_path)
    res = posting.publish(s, cid, ["ix", "fb", "x"], caption="€40k suite")
    assert {r["platform"]: r["status"] for r in res["results"]} == {"ig": "package", "fb": "package", "x": "package"}
    assert res["x_intent"].startswith("https://x.com/intent/post?text=")
    assert "Video%3A%20Jane" in res["x_intent"]
    pkg = res["package_dir"]
    files = {p.name for p in __import__("pathlib").Path(pkg).iterdir()}
    assert {"post.json", "caption_x.txt", "caption_ig.txt"} <= files


def test_publish_refuses_unlicensed(tmp_path):
    s, cid = _store_with_clip(tmp_path, license_code="YOUTUBE-STANDARD")
    with pytest.raises(RightsError):
        posting.publish(s, cid, ["x"])


class Resp:
    def __init__(self, data):
        self._d = data
        self.status_code = 200

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


class FakeSession:
    """Answers the X v2 / Graph API calls posting.py makes."""
    def __init__(self):
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        if url.endswith("/initialize"):
            return Resp({"data": {"id": "m1"}})
        if url.endswith("/append"):
            return Resp({})
        if url.endswith("/finalize"):
            return Resp({"data": {"id": "m1", "processing_info": {"state": "succeeded"}}})
        if url.endswith("/2/tweets"):
            assert kw["json"]["media"]["media_ids"] == ["m1"]
            return Resp({"data": {"id": "t9"}})
        if url.endswith("/media") and "graph.facebook.com" in url:
            return Resp({"id": "c1"})
        if "rupload.facebook.com" in url:
            return Resp({"success": True})
        if url.endswith("/media_publish"):
            return Resp({"id": "ig5"})
        if url.endswith("/videos"):
            return Resp({"id": "fb7"})
        raise AssertionError(url)

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        if url.endswith("/c1"):
            return Resp({"status_code": "FINISHED"})
        if url.endswith("/ig5"):
            return Resp({"permalink": "https://www.instagram.com/reel/abc/"})
        raise AssertionError(url)


def _all_creds(monkeypatch):
    for n, val in [("X_USER_ACCESS_TOKEN", "tok-x"), ("META_PAGE_ACCESS_TOKEN", "tok-meta"),
                   ("IG_USER_ID", "1789"), ("FB_PAGE_ID", "555")]:
        monkeypatch.setenv(n, val)


def test_publish_live_dedupe_and_cap(tmp_path, monkeypatch):
    _all_creds(monkeypatch)
    monkeypatch.setenv("VIDEO_SCOUT_DAILY_CAP", "1")
    s, cid = _store_with_clip(tmp_path)
    fs = FakeSession()
    res = posting.publish(s, cid, ["ig", "fb", "x"], session=fs)
    urls = {r["platform"]: r["url"] for r in res["results"]}
    assert urls == {"ig": "https://www.instagram.com/reel/abc/", "fb": "https://www.facebook.com/555/videos/fb7",
                    "x": "https://x.com/i/status/t9"}
    assert res["package_dir"] is None
    # same video again -> de-duped from the posted-log
    again = posting.publish(s, cid, ["x"], session=fs)
    assert again["results"][0]["status"] == "skipped" and "already" in again["results"][0]["detail"]
    # different video, cap of 1/day already used -> capped
    v2 = s.upsert(vid(id="youtube:def", url="https://www.youtube.com/watch?v=def"))
    cid2 = s.add_clip(video_id=v2.id, path=s.get_clip(cid)["path"], thumb="", start=0, end=5, vertical=1,
                      watermark=1, caption="", attribution="auto", probe={})
    capped = posting.publish(s, cid2, ["x"], session=fs)
    assert capped["results"][0]["status"] == "skipped" and "daily cap" in capped["results"][0]["detail"]
    assert s.posted_today("x") == 1


def test_publish_redacts_secrets_in_errors(tmp_path, monkeypatch):
    _all_creds(monkeypatch)
    s, cid = _store_with_clip(tmp_path)

    class Boom(FakeSession):
        def post(self, url, **kw):
            raise RuntimeError("401 for token tok-x")
    res = posting.publish(s, cid, ["x"], session=Boom())
    r = res["results"][0]
    assert r["status"] == "failed" and "tok-x" not in r["detail"] and res["package_dir"]


# ------------------------------------------------------------------ autopost
def test_autopost_mock_end_to_end(tmp_path, monkeypatch):
    _all_creds(monkeypatch)
    monkeypatch.setenv("VIDEO_SCOUT_DAILY_CAP", "3")
    s = Store(tmp_path / "a.db")
    clip_file = tmp_path / "c.mp4"
    clip_file.write_bytes(b"\x00" * 1024)

    def clip_fn(v, start, end, **kw):
        assert kw["vertical"] and kw["watermark"]
        assert_reusable(v)
        return {"path": str(clip_file), "thumbnail": "", "probe": {}}

    fs = FakeSession()
    out = autopost.run(platforms=["x", "fb"], queries=["hotel"], provider_names=["mock"], store=s, clip_fn=clip_fn,
                       session=fs)
    assert out["status"] == "ok" and out["picked"]["license"] in licenses.ALLOWED
    assert {r["status"] for r in out["post"]["results"]} == {"posted"}
    first = out["picked"]["id"]
    out2 = autopost.run(platforms=["x", "fb"], discover_first=False, store=s, clip_fn=clip_fn, session=fs)
    assert out2["status"] == "ok" and out2["picked"]["id"] != first  # never reposts the same video
    for p in ("x", "fb"):
        s.log_post(None, "manual:1", p, "posted")
    assert autopost.run(platforms=["x", "fb"], discover_first=False, store=s, clip_fn=clip_fn)["status"] == "capped"


def test_autopost_never_picks_unlicensed(tmp_path):
    s = Store(tmp_path / "b.db")
    s.upsert(vid(id="youtube:std", license_code="YOUTUBE-STANDARD", status="approved"))
    s.upsert(vid(id="youtube:nc", license_code="NC-OR-ND", status="approved"))
    assert autopost.pick(s, ["x"]) is None


# ------------------------------------------------------------------ CLI (JSON, exit codes)
def run_cli(capsys, *args):
    code = cli.main(list(args))
    return code, json.loads(capsys.readouterr().out)


def test_cli_discover_list_and_refusal(capsys, tmp_path):
    code, d = run_cli(capsys, "discover", "--query", "hotel room tour", "--limit", "10", "--providers", "mock")
    assert code == 0 and d["count"] >= 4 and d["providers"] == ["mock"]
    code, d = run_cli(capsys, "list", "--licensed")
    assert code == 0 and all(v["reusable"] for v in d["videos"])
    code, d = run_cli(capsys, "clip", "--id", "youtube:mock2", "--start", "0", "--end", "5", "--vertical")
    assert code == 2 and d["refused"] == "license"
    code, d = run_cli(capsys, "embed-approve", "youtube:mock2")  # embed-only video can still go on the site
    assert code == 0 and d["video"]["on_site"] is True
    code, d = run_cli(capsys, "creds")
    assert code == 0 and set(d["posting"]) >= {"ig", "fb", "x"}
    f = tmp_path / "x.mp4"
    f.write_bytes(b"0")
    code, d = run_cli(capsys, "clip", "--file", str(f), "--start", "0", "--end", "3")
    assert code == 2  # local file without a declared allowed license is refused
    code, d = run_cli(capsys, "clip", "--file", str(f), "--start", "0", "--end", "3", "--license", "CC BY-NC 4.0",
                      "--creator", "Jane")
    assert code == 2


# ------------------------------------------------------------------ real ffmpeg
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_ffmpeg_vertical_clip(tmp_path):
    from video_scout import clipper
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-c:a", "aac",
                    "-shortest", str(src)], check=True)
    out = clipper.clip(src, "00:01", 4, out=tmp_path / "out.mp4", vertical=True, watermark=True,
                       caption="€40,000/night suite", attribution="Video: Jane / CC BY 4.0, edited")
    p = out["probe"]
    v = next(s for s in p["streams"] if s["codec_type"] == "video") if "streams" in p else p
    assert (int(v["width"]), int(v["height"])) == (1080, 1920)
    dur = float(p["format"]["duration"]) if "format" in p else float(p["duration"])
    assert 2.8 < dur < 3.3
    assert (tmp_path / "out.jpg").exists() or out["thumbnail"]
