"""Download (licensed only) and clip with ffmpeg: trim, optional 9:16 crop, brand watermark, caption, attribution."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from . import config, licenses
from .models import Video
from .providers import UA, InternetArchive, ytdlp_base_args
from .rights import assert_reusable

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MAX_DOWNLOAD_BYTES = 600 * 1024 * 1024


def ffmpeg_bin(name: str = "ffmpeg") -> str:
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"{name} not found. Install it: sudo apt-get install -y ffmpeg (Railway: add ffmpeg to nixpkgs/apt)")
    return p


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80]


def download(v: Video, dest_dir: Optional[Path] = None) -> Path:
    """Download the source file for a LICENSED video. Refuses anything else (RightsError)."""
    assert_reusable(v)
    dest_dir = Path(dest_dir or config.downloads_dir())
    base = dest_dir / _safe(v.id)
    existing = sorted(dest_dir.glob(base.name + ".*"))
    existing = [p for p in existing if p.suffix in {".mp4", ".webm", ".mkv", ".mov", ".ogv"}]
    if existing:
        return existing[0]
    if v.platform == "youtube":
        out = subprocess.run(ytdlp_base_args() + [
            "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b",
            "--merge-output-format", "mp4", "--max-filesize", str(MAX_DOWNLOAD_BYTES), "-o", f"{base}.%(ext)s", v.url],
            capture_output=True, text=True, timeout=900)
        got = sorted(dest_dir.glob(base.name + ".*"))
        got = [p for p in got if not p.name.endswith(".part")]
        if not got:
            raise RuntimeError(f"yt-dlp download failed: {out.stderr.strip()[-400:]}")
        return got[0]
    url = v.download_url
    if v.platform == "archive" and not url:
        url = InternetArchive.resolve_download(v.id.split(":", 1)[1])
    if not url:
        raise RuntimeError(f"no download URL recorded for {v.id}")
    ext = Path(url.split("?")[0]).suffix or ".mp4"
    path = base.with_suffix(ext)
    with requests.get(url, stream=True, timeout=60, headers={"User-Agent": UA}) as r:
        r.raise_for_status()
        n = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                n += len(chunk)
                if n > MAX_DOWNLOAD_BYTES:
                    f.close(); path.unlink(missing_ok=True)
                    raise RuntimeError("download larger than 600 MB; pick a shorter source")
                f.write(chunk)
    return path


def probe(path: Path) -> Dict[str, Any]:
    out = subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                          str(path)], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()[-300:]}")
    d = json.loads(out.stdout)
    vs = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    au = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {"duration": round(float(d.get("format", {}).get("duration", 0) or 0), 3),
            "width": vs.get("width"), "height": vs.get("height"), "video_codec": vs.get("codec_name"),
            "audio_codec": au.get("codec_name"), "size_bytes": int(d.get("format", {}).get("size", 0) or 0)}


def _parse_time(t) -> float:
    if t is None or t == "":
        return 0.0
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(x) for x in str(t).split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def clip(src: Path, start, end, out: Optional[Path] = None, vertical: bool = False, watermark: bool = False,
         caption: str = "", attribution: str = "", logo: Optional[Path] = None) -> Dict[str, Any]:
    """Trim [start, end) from src. Returns {'path', 'thumbnail', 'probe'}. Re-encodes to H.264/AAC MP4 (+faststart)."""
    src = Path(src)
    s, e = _parse_time(start), _parse_time(end)
    if e <= s:
        raise ValueError("end must be after start")
    if e - s > 180:
        raise ValueError("clips are capped at 180 s (Reels/X friendly); pick a shorter range")
    out = Path(out or (config.exports_dir() / f"{_safe(src.stem)}_{int(s)}-{int(e)}{'_v' if vertical else ''}.mp4"))
    out.parent.mkdir(parents=True, exist_ok=True)
    logo = Path(logo or config.DEFAULT_LOGO)
    tmp = Path(tempfile.mkdtemp(prefix="vs_"))
    vf = []
    W = 1080 if vertical else None
    if vertical:
        vf.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1")
    else:
        vf.append("scale='min(1920,iw)':-2,setsar=1")
    font_px = "h/28" if vertical else "h/18"
    if caption:
        (tmp / "cap.txt").write_text(caption.strip()[:120])
        vf.append(f"drawtext=fontfile={FONT_BOLD}:textfile={tmp / 'cap.txt'}:fontcolor=0xF5F1E8:fontsize={font_px}:"
                  "box=1:boxcolor=0xB3243A@0.92:boxborderw=18:x=(w-text_w)/2:y=h*0.12")
    if attribution:
        (tmp / "attr.txt").write_text(attribution.strip()[:110])
        vf.append(f"drawtext=fontfile={FONT}:textfile={tmp / 'attr.txt'}:fontcolor=white:fontsize=h/60:"
                  "box=1:boxcolor=0x14161B@0.6:boxborderw=8:x=(w-text_w)/2:y=h-text_h-h*0.16")
    chain = ",".join(vf)
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", str(src)]
    if watermark and logo.exists():
        cmd += ["-i", str(logo)]
        fc = (f"[0:v]{chain}[base];[1:v]format=rgba,scale={170 if vertical else 120}:-1,colorchannelmixer=aa=0.85[wm];"
              "[base][wm]overlay=W-w-32:32[v]")
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]
    else:
        cmd += ["-vf", chain, "-map", "0:v:0", "-map", "0:a?"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[-500:]}")
    return {"path": str(out), "thumbnail": str(thumbnail(out)), "probe": probe(out)}


def thumbnail(path: Path, at: Optional[float] = None) -> Path:
    path = Path(path)
    jpg = path.with_suffix(".jpg")
    if at is None:
        try:
            at = probe(path)["duration"] / 2
        except Exception:
            at = 0.5
    subprocess.run([ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(path),
                    "-frames:v", "1", "-q:v", "3", str(jpg)], capture_output=True, timeout=60)
    return jpg


def clip_video(v: Video, start, end, **kw) -> Dict[str, Any]:
    """Licensed video -> download -> clip with automatic attribution burned in."""
    assert_reusable(v)
    src = download(v)
    attr = licenses.attribution(v.creator, v.license_code, None, v.license_name)
    return clip(src, start, end, attribution=kw.pop("attribution", None) or attr, **kw)
