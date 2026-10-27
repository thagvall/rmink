# Hosting the web UI

## Vercel

The `deploy/vercel/` folder is a ready-made Vercel project. It runs the
released rmink version pinned in `requirements.txt` as a Python function
(about 300 MB; the limit is 500 MB), in the Stockholm region (`arn1`).

1. Vercel dashboard: **Add New… → Project → Import** `thagvall/rmink`.
2. Set **Root Directory** to `deploy/vercel`. Leave the framework preset as
   detected (FastAPI/Python) and click **Deploy**.
3. Optional, under *Settings → Environment Variables*:
   - `RMINK_SUPPORT_URL`: the Stripe Payment Link; shows the support button
   - `RMINK_SOURCE_URL`: defaults to the GitHub repo
   - `RMINK_DEMO_URL`: the demo video behind "Watch the demo" (`{lang}` is
     `en` or `sv`); defaults to the video on rmink.vercel.app, `""` hides it
4. Optional: add your own domain under *Settings → Domains*.

The Hobby plan is enough to start with. It includes about 4 hours of active
CPU a month, and one conversion takes 1–6 s. Asking for donations is allowed
on Hobby; selling is not.

**Updating the site:** release a new version to PyPI, bump the version in
`deploy/vercel/requirements.txt` and push. Vercel redeploys automatically.
The project sets `VERCEL_FORCE_NO_BUILD_CACHE=1`. Without it, Vercel restores
uv's cached copy of the PyPI index from the previous build, and a newly
released version is reported as missing ("no version of rmink[web]==X"). If
a build ever fails that way, check that the variable is still set and
redeploy.

**Demo video links:** `deploy/vercel/public/` is served as static files.
`/video` and `/video/sv` (rewrites in `vercel.json`) carry link-preview tags
for LinkedIn and other sites, and send visitors on to the app with the video
open (`/?demo`, `/?demo=sv`). Regenerate them with
`python promo/make_share.py` (see `promo/README.md`).

**Sketch to drawing entry:** a separate, static entry for the other direction
(hand sketch to clean drawing), next to the app. The app's start page is not
affected.
- `/sketch` (English) and `/sketch/sv` or `/skiss` (Swedish) show the
  interactive demo, with "Watch the video" opening the 4:5 video in a dialog.
- `/sketch?demo` and `/sketch/sv?demo=sv` open the page with the video
  playing.
- `/sketch/video` and `/sketch/video/sv` are share links with link-preview
  tags for LinkedIn and other sites. They send visitors on to the page with
  the video open.
- The videos are at `/promo/sketch/rmink-sketch-{sv,en}-{4x5,16x9}.mp4`.

Rebuild with `python promo/sketch-video/make_site.py` (see
`promo/sketch-video/README.md`).

**Revision rounds (owner-only, experimental):** `/rounds` runs one round of
the sketch-to-drawing loop with Claude. The page lists your drawings, each
with a "Kör nästa varv" (next round) button, and the new sketches in the
`rmink` folder of your reMarkable Cloud. Each revision goes to
`rmink/<drawing>/` and the one before it moves to `rmink/<drawing>/Tidigare/`.
It is off
unless these are set under *Settings → Environment Variables*:
- `RMINK_ROUNDS_SECRET`: a long random passphrase; the page asks for it once
- `ANTHROPIC_API_KEY`: your Claude API key (each round costs roughly
  0.3–0.6 USD; the page shows the cost after every round)
- `RMINK_CLOUD_TOKEN`: the device token from `rmink cloud connect CODE`
  (it is printed into `~/.config/rmink/cloud.toml`)
- `RMINK_ROUND_EFFORT` (optional): `low`, `medium` (default) or `high`

Drawings are kept between rounds in the browser you run them from (the page
sends them with each round and stores what comes back), so no database is
needed; a different phone or a cleared browser starts the drawing over from
its latest revision. Optionally, the **Upstash for Redis** integration
(`KV_REST_API_URL`, `KV_REST_API_TOKEN`) keeps them on the server instead. The rounds need `rmink[rounds]`
in `requirements.txt`. Locally, `rmink round Altan` (a drawing name) or
`rmink round /rmink/Garage` (a new sketch) runs the same round with drawings in
`~/.config/rmink/drawings`.

**Limits on the hosted version:**
- Vercel caps each request and response at 4.5 MB. The browser shrinks
  large photos (to at most 3200 px, as JPEG) before uploading, which is
  plenty for the tablet's resolution.
- Large PDFs have to be split, or converted locally with
  `uvx --from 'rmink[web]' rmink web`.
- Uploaded files only live in the function's temporary storage while the
  request runs.

**Send to reMarkable:** the Linux build of
[rmapi](https://github.com/ddvk/rmapi) is committed as
`deploy/vercel/bin/rmapi` (run `deploy/vercel/fetch-rmapi.sh` to change the
pinned version) and bundled through `includeFiles` in `vercel.json`. The
server keeps no accounts: connecting turns the user's one-time code into a
device token that is stored only in their browser and sent along with each
upload, where rmapi uses it from a per-request temp config.

## Docker (any server)

```bash
docker build -t rmink .
docker run -p 8765:8765 -e RMINK_SUPPORT_URL=... rmink
```

Limits are set with the `RMINK_*` environment variables; see
`src/rmink/web/__init__.py`.
