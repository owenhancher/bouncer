# Bouncer Video Scout: guide for Mark

*Only real deals get in.* Video Scout finds hotel and travel videos that are going viral. It shows the best ones on the Bouncer site through their official embeds. It turns **free-reuse-licensed** videos into vertical Bouncer-branded clips and posts those to Bouncer's Instagram, Facebook Page and X, either by hand or automatically.

There are three parts:

| Part | What it is | Where it runs |
|---|---|---|
| `video_scout/` + CLI | Discovery, ranking, licensing gate, clipper, posting, autopost. Every command prints JSON. | Any box with Python, ffmpeg and node |
| `admin_app.py` | Password-protected admin console: Discover → Library → Clip → Post / Autopost | Locally or privately, port 8502. **Not** the public site |
| "Hotels going viral" section in `app.py` | Official embeds of approved videos | The public site. Off unless `BOUNCER_SHOW_VIDEOS=1` |

---

## 1. Rights rules (read first)

These rules are enforced in code (`video_scout/rights.py`) and not merely by convention.

1. **Clip, download and repost only videos that are already licensed for free reuse.** We never ask creators for permission, and there is no "permission obtained" checkbox.
   - Allowed codes:
     - `CC0` and `PD` (public domain)
     - `CC-BY` and `CC-BY-SA` (YouTube's Creative Commons filter, Wikimedia Commons, Internet Archive)
     - `PEXELS` and `PIXABAY` (free commercial licenses)
     - `OWN` (Bouncer's own footage)
   - **Refused:**
     - anything NonCommercial (**NC**) or NoDerivatives (**ND**)
     - standard YouTube or all-rights-reserved videos
     - TikTok, Instagram and X posts
     - an unspecified "Creative Commons" with no version or terms
     - unknown licenses
2. Every video stores **license, source URL and creator**.
3. **Attribution is automatic.** It is burned into the clip, e.g. `Video: rewinside / CC BY 3.0, edited`, and appended to every caption with the source link.
   - "edited" is there because CC licenses require us to indicate that we changed the work.
   - CC BY-SA clips also say "(clip CC BY-SA)", because derivatives must keep the same license.
4. `clip`, `download`, `post` and `autopost` **refuse** anything without an allowed license (CLI exit code 2, `"refused": "license"`).
5. **Non-licensed viral videos** can appear on our site **only through the platform's official embed**. The video plays from the creator's post and carries a credit plus a "Watch original ↗" link. They are never downloaded, clipped or reposted.
6. Pexels and Pixabay ask for (but do not require) credit. We credit anyway.
   - Don't use clips that show identifiable people or brands in a way that suggests they endorse Bouncer.
   - The autopost safety filter skips obvious problem titles (crime, disasters, adult content and so on), but **review what goes out**.

---

## 2. Setup

```bash
cd bouncer
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-video.txt        # requirements.txt + yt-dlp[default]
# system tools: ffmpeg + ffprobe (apt install ffmpeg), Node.js >= 20 (yt-dlp uses it for YouTube downloads)
python -m pytest tests -q                    # all tests should pass, no network needed
```

The data lives in `data/video_scout/`, which is git-ignored:

- `scout.db` (SQLite: videos, clips, posted-log)
- `downloads/`
- `exports/`, which holds the clips and `exports/packages/` (ready-to-post bundles)

Start the admin console:

```bash
BOUNCER_ADMIN_PASSWORD='pick-a-long-one' streamlit run admin_app.py --server.port 8502
```

The console refuses to start without `BOUNCER_ADMIN_PASSWORD`.
- It is a separate Streamlit app (not a `pages/` file), so it never shows up in the public site's sidebar.
- **Don't deploy it publicly.** If you must host it, use a separate private Railway service with the password set.

### Environment variables

Put these in `.env` (never commit it) or in your Railway variables.

| Variable | Default | Purpose |
|---|---|---|
| `BOUNCER_SHOW_VIDEOS` | off | `1` shows "Hotels going viral" on the public site |
| `BOUNCER_ADMIN_PASSWORD` | unset (admin disabled) | Password for `admin_app.py` |
| `VIDEO_SCOUT_DATA_DIR` | `data/video_scout` | Where the DB, downloads and exports live |
| `VIDEO_SCOUT_DB` | `<data>/scout.db` | SQLite path override |
| `VIDEO_SCOUT_EXPORTS_DIR` | `<data>/exports` | Clip output folder |
| `VIDEO_SCOUT_PROVIDERS` | all available | e.g. `youtube,commons,archive,pexels,pixabay` |
| `VIDEO_SCOUT_DAILY_CAP` | `3` | Max live posts **per platform per day** (manual + auto) |
| `VIDEO_SCOUT_AUTOPOST_PLATFORMS` | `ig,fb,x` | Platforms autopost targets |
| `VIDEO_SCOUT_AUTOPOST_SECONDS` | `20` | Autopost clip length |
| `YOUTUBE_API_KEY` | – | Optional: YouTube Data API provider (yt-dlp search needs no key) |
| `PEXELS_API_KEY` | – | Enables the Pexels provider |
| `PIXABAY_API_KEY` | – | Enables the Pixabay provider |
| `X_USER_ACCESS_TOKEN` | – | X OAuth 2.0 user token (**or** the 4 OAuth 1.0a keys below) |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | – | X OAuth 1.0a user context |
| `META_PAGE_ACCESS_TOKEN` | – | Long-lived **Page** access token (covers both IG and FB) |
| `IG_USER_ID` | – | Instagram professional account id linked to the Page |
| `FB_PAGE_ID` | – | Bouncer Facebook Page id |
| `META_GRAPH_VERSION` | `v21.0` | Graph API version |
| `VIDEO_SCOUT_ENABLE_RAPIDAPI`, `VIDEO_SCOUT_RAPIDAPI_HOST`, `VIDEO_SCOUT_RAPIDAPI_PATH` | off | Optional RapidAPI social video search (uses `RAPIDAPI_KEY`). Results are **embed-only**. Off by default; the flight/hotel RapidAPI quota is separate and nearly used up |

---

## 3. Mark's workflow inside the admin tool (discover → pick → clip vertical → post)

You never leave `admin_app.py`.

1. **Log in** with the admin password.
2. **1 · Discover**
   - Type a search (e.g. `hotel room tour`, `overwater villa`, `capsule hotel`) and leave **Licensed only (clippable)** on.
   - Click **Discover**. Results are ranked by virality and saved to the library.
     - The score is `0.6·log10(views) + 0.4·log10(views/day)`, plus a like-rate bonus.
     - Turn *Licensed only* off to find big viral videos for the **site embed** section. Those can't be clipped.
   - You can also paste a TikTok, Instagram, X or YouTube URL under "Add a known post URL" for site embedding.
3. **2 · Library / pick**
   - Each card shows the thumbnail, views, views/day, date, a hotel/location guess and a license tag.
     - A **green "clippable"** tag means it is free-reuse licensed.
     - A **grey "embed only"** tag means it can only be shown on the site through its embed.
   - **Approve**, **Reject** or **Show on site (embed)** as you like.
   - On a clippable video, click **Clip this →**.
4. **3 · Clip**
   - The video you picked is preselected, and the embed player is shown so you can find the moment.
   - Set **Start/End** (seconds or `mm:ss`, max 180 s) and an optional on-video caption (e.g. `€40,000/night suite`).
   - Keep **9:16 vertical crop** and **Bouncer watermark** ticked.
   - The attribution line is burned in automatically.
   - Click **Make clip**. The source downloads (720p max) and ffmpeg renders a 1080×1920 H.264/AAC MP4.
5. **4 · Post**
   - The clip you just made is preselected and plays inline.
   - Edit the caption. The attribution, "Only real deals get in. Follow @bouncertravel" and the hashtags are added automatically, and *Preview captions* shows exactly what each platform gets.
   - Pick platforms (Instagram Reel, Facebook Page, X) and click **Post now**.
     - **Platforms with credentials** post live, and you see the post URLs.
     - **Platforms without credentials** get a **ready-to-post package** in `data/video_scout/exports/packages/<time>_<id>/`, containing the clip, `caption_ig.txt`, `caption_fb.txt`, `caption_x.txt` and `post.json`. You also get an **Open X composer** button (an X intent link with the caption prefilled). Attach the MP4 yourself.
   - De-dupe and daily cap: the same video is never posted twice to the same platform, and each platform stops at `VIDEO_SCOUT_DAILY_CAP` live posts a day.
6. **Autopost** tab: **Run autopost now** runs the whole chain with no further clicks (see §6). Tick *Dry run* to see what it would pick without posting.
7. **Log & credentials** tab: shows which keys are present (never their values), the posted-log and all clips.

---

## 4. Site display ("Hotels going viral")

1. In the admin Library click **Show on site (embed)**, or run `python -m video_scout embed-approve <id>`.
2. This writes `video_scout/site_videos.json`. **Commit and push that file.** The live site reads it, not the local DB.
3. Set `BOUNCER_SHOW_VIDEOS=1` in Railway. Without it the section doesn't render. It is wrapped in try/except, so a bad embed can't break the page.

Each embed uses the platform's official player and shows a credit footer: "Video by <creator> on <platform> · <license> · Watch original ↗".

| Platform | How it is embedded |
|---|---|
| YouTube | `youtube-nocookie.com` iframe |
| TikTok | `tiktok.com/player/v1` iframe |
| Instagram | Blockquote + `embed.js` (oEmbed needs a Meta token, so not used) |
| X | Blockquote + `widgets.js` |
| Commons/Archive/Pexels/Pixabay | Plain `<video>` tag (these files are licensed) |

---

## 5. Posting credentials (per platform)

None of these are configured yet. Until they are, every post produces a package plus an X intent link.

### X (Twitter): API v2

- **Get keys**
  1. Go to developer.x.com and create a Project and App.
  2. Set *User authentication settings* to **Read and write**, with a callback URL.
  3. Either:
     - OAuth 2.0 (PKCE): authorize the @bouncertravel account with scopes `tweet.read tweet.write users.read media.write offline.access` and set `X_USER_ACCESS_TOKEN`. User tokens expire after 2 h unless you refresh them with `offline.access`, so for unattended autopost **OAuth 1.0a is simpler**.
     - OAuth 1.0a: set `X_API_KEY`/`X_API_SECRET` (consumer keys) and `X_ACCESS_TOKEN`/`X_ACCESS_TOKEN_SECRET`, generated for the Bouncer account with Read+Write.
- **Calls**
  1. `POST /2/media/upload/initialize`, then `/{id}/append` (4 MB chunks), then `/{id}/finalize`.
  2. Poll `GET /2/media/upload?command=STATUS`.
  3. `POST /2/tweets` with `media.media_ids`.
  - The v1.1 upload endpoint was retired in 2025.
- **Cost and limits**
  - X API access is **pay-per-use**: about **$0.015 per post**, or about **$0.20 per post that contains a URL**. Our captions include the source URL for attribution.
  - Video max 512 MB and 140 s for normal accounts (our clips are 20 s).
  - The `media_id` must be used within 24 h.
  - Per-endpoint rate limits are listed on the developer portal. Our daily cap (3/day) is far below them.

### Instagram Reels: Instagram Graph API (Content Publishing)

- **Requirements**
  - The Bouncer Instagram account must be a **Business or Creator** account **linked to the Bouncer Facebook Page**.
  - A Meta developer app (developers.facebook.com, app type *Business*) with **Instagram Graph API** / *Instagram API with Facebook Login*.
  - Permissions: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` (and `business_management` if the Page is in Business Manager).
  - For your own accounts in Development mode no App Review is needed; you are an app admin.
- **Token**
  1. In Graph API Explorer get a user token with those scopes.
  2. Exchange it for a long-lived token.
  3. Call `GET /me/accounts`, which returns a **long-lived Page token**. Set it as `META_PAGE_ACCESS_TOKEN`.
  4. `GET /{page-id}?fields=instagram_business_account` gives `IG_USER_ID`.
- **Calls**
  1. `POST /{ig-user-id}/media` with `media_type=REELS, upload_type=resumable`.
  2. Upload the file to `rupload.facebook.com/ig-api-upload/<ver>/{container}`.
  3. Poll `status_code` until `FINISHED`.
  4. `POST /{ig-user-id}/media_publish`.
  5. Read the `permalink`.
- **Limits**
  - **100 API-published posts per rolling 24 h** per IG account.
  - Reels 3 s to 15 min, MP4/H.264/AAC, 9:16 recommended. We output exactly that.

### Facebook Page video: Graph API

- **Same app and token as IG.** The Page token also needs `pages_manage_posts` (and `publish_video` if your app version requires it). Set `FB_PAGE_ID`.
- **Call:** `POST graph-video.facebook.com/<ver>/{page-id}/videos` with `source=@clip.mp4` and `description`. The result is `facebook.com/{page}/videos/{id}`.
- **Limits:** standard Graph API Page rate limiting (based on Page engagement; you'll never hit it at 3/day). Video up to 10 GB / 240 min.

### Discovery keys (optional, all free)

| Source | Key | How to get it | Limits |
|---|---|---|---|
| YouTube via yt-dlp | none | – | Be polite. We enrich only the top results (about 1 s each) |
| YouTube Data API | `YOUTUBE_API_KEY` | console.cloud.google.com, enable "YouTube Data API v3", create an API key | 10,000 units/day; a search costs 100 units, so about 100 searches/day |
| Wikimedia Commons | none | – | Send a User-Agent (we do) |
| Internet Archive | none | – | Be polite |
| Pexels | `PEXELS_API_KEY` | pexels.com/api, create an account, "Your API key" (instant, free) | 200 requests/hour, 20,000/month |
| Pixabay | `PIXABAY_API_KEY` | pixabay.com/api/docs, sign up, key shown on the docs page | 100 requests / 60 s. Cache results 24 h. Don't hotlink permanently (we download) |

---

## 6. Autopost (no human click)

Owen has authorized automatic posting to Bouncer's own IG, FB Page and X.

```bash
python -m video_scout autopost                       # discover licensed -> pick -> clip 9:16 -> post to ig,fb,x
python -m video_scout autopost --dry-run             # everything except the actual post
python -m video_scout autopost --no-discover --platforms x --seconds 15
```

The steps it runs:

1. Skip entirely if every platform has hit today's cap.
2. Run licensed discovery for a few hotel queries.
3. **Pick** the top candidate. An **approved** video comes first if there is one. Otherwise it takes the top-scored candidate that:
   - is licensed
   - has hotel keywords in the title
   - passes the safety filter
   - is at least 6 s long
   - hasn't been posted yet on at least one target platform
4. Clip `VIDEO_SCOUT_AUTOPOST_SECONDS` (20 s), starting 15% in for videos longer than 2 minutes to skip intros. The clip is vertical, watermarked, and has the attribution burned in.
5. Post to every platform that has credentials and is under the cap. Results go to the posted-log, so a video is never posted twice to the same platform.
   - Without credentials autopost still makes the clip and package. It will pick the same video again next run, because only *live* posts count as "posted".

Cron example (3 runs a day = the default cap):

```cron
0 9,13,18 * * * cd /home/box/bouncer && .venv/bin/python -m video_scout autopost >> data/video_scout/autopost.log 2>&1
```

To steer what goes out, **approve** videos in the Library, since approved videos are picked first. **Reject** anything you never want posted.

---

## 7. Chat bot commands

The Grok Bot teammate in Owen's group chat drives the tool through the shell. Every command:

- is non-interactive
- prints **one JSON object** to stdout
- exits **0** on success, **1** on error (`{"error": ...}`) and **2** when the rights gate refuses (`{"error": ..., "refused": "license"}`)

Run from the repo root with the venv's Python.

```bash
# discover (ranked + saved). --licensed = only clippable; --any-topic = skip hotel keyword filter
python -m video_scout discover --query "hotel room tour" --limit 25
python -m video_scout discover --query "luxury hotel suite" --limit 15 --licensed --providers youtube,commons

# list ranked results with ids
python -m video_scout list --limit 10
python -m video_scout list --licensed --status approved
python -m video_scout show youtube:PgceOhAh2cw

# curate
python -m video_scout approve youtube:PgceOhAh2cw
python -m video_scout reject youtube:XXXXXXXXXXX
python -m video_scout embed-approve youtube:iogcY_4xGjo           # show on site via official embed (any license)
python -m video_scout embed-approve youtube:iogcY_4xGjo --remove
python -m video_scout add-url "https://www.tiktok.com/@user/video/123..."   # embed-only

# clip (licensed only). Exit 2 if not allowed
python -m video_scout clip --id youtube:PgceOhAh2cw --start 1:00 --end 1:20 --vertical --watermark --caption "€40,000/night suite"
python -m video_scout clip --file ./our_footage.mp4 --license OWN --start 0 --end 15 --vertical --watermark
python -m video_scout clip --file ./pexels.mp4 --license PEXELS --creator "Jane Doe" --source-url https://www.pexels.com/video/... --start 0 --end 12 --vertical

# preview -> {"path": ".../clip.mp4", "thumbnail": ".../clip.jpg", "probe": {...}}
python -m video_scout preview 5
python -m video_scout clips

# post (live where creds exist, else package + X intent link). Platforms: ig (alias ix/instagram), fb, x
python -m video_scout post 5 --platforms ig,fb,x --caption "Europe's priciest hotel room: €40k a night."
python -m video_scout post 5 --platforms x --dry-run

# autopost, log, creds
python -m video_scout autopost --dry-run
python -m video_scout posts            # posted-log + today's count vs cap
python -m video_scout creds            # which keys are present (never values)
```

Typical bot flow:

1. `discover --licensed`
2. `list --licensed -n 5`, then show the top 5 in chat
3. `clip --id <id> ... --vertical --watermark`
4. `preview <clip_id>`, then send the thumbnail
5. `post <clip_id> --platforms ig,fb,x`, then reply with the post URLs, or with the package path and X intent link

`python -m video_scout.discover --query "hotel room tour" --limit 25` also works, as an alias of `discover`.

---

## 8. Adding a provider

1. In `video_scout/providers.py`, subclass `VideoProvider`:
   - Set `name`.
   - Set `needs` (the env vars it requires; `available()` checks them).
   - Set `licensed_only = True` if every result is free-reuse.
   - Implement `search(query, limit, licensed) -> List[Video]`.
2. For each `Video`:
   - Fill `id` (`"<provider>:<native id>"`), `platform`, `url`, `title`, `creator`, `views`/`likes`/`published` where known, and `thumbnail`.
   - Fill `license_code`/`license_name`/`license_url` via `licenses.classify(text, url)`. Never guess a license. Leave it `UNKNOWN` and the item becomes embed-only.
   - For clippable sources, fill `download_url`.
   - Return `self._finish(v)`, which adds the hotel/location guess and the score.
3. Register it in `PROVIDERS`, and in `DEFAULT_ORDER` if it should run by default.
4. Add a test using a fake response (see `tests/test_video_scout.py`). Tests must not hit the network.

## 9. Known limitations

- **Posting is untested against the live APIs.** No X or Meta credentials exist yet. The code follows the current docs and is covered by fake-session tests, but the first real post may need small fixes. Try `post <id> --platforms x` once and check the result.
- The hotel/location guess is keyword-based and sometimes wrong.
- View-sorted YouTube search drifts off-topic, so a hotel keyword filter is on by default (`--any-topic` turns it off). The licensed pool is much smaller than the viral pool.
- yt-dlp depends on YouTube's current site. If downloads break, `pip install -U "yt-dlp[default]"`.
- The RapidAPI social provider is a stub behind a flag. It has not been run.
- X oEmbed returned nothing in testing, so X embeds use the blockquote + `widgets.js` method.
