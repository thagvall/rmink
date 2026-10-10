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

**Limits on the hosted version:**
- Vercel caps each request and response at 4.5 MB. The browser shrinks
  large photos (to at most 3200 px, as JPEG) before uploading, which is
  plenty for the tablet's resolution.
- Large PDFs have to be split, or converted locally with
  `uvx --from 'rmink[web]' rmink web`.
- Uploaded files only live in the function's temporary storage while the
  request runs.

## Docker (any server)

```bash
docker build -t rmink .
docker run -p 8765:8765 -e RMINK_SUPPORT_URL=... rmink
```

Limits are set with the `RMINK_*` environment variables; see
`src/rmink/web/__init__.py`.
