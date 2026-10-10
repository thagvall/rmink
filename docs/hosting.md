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
4. Optional: add your own domain under *Settings → Domains*.

The Hobby plan is enough to start with. It includes about 4 hours of active
CPU a month, and one conversion takes 1–6 s. Asking for donations is allowed
on Hobby; selling is not.

**Updating the site:** release a new version to PyPI, bump the version in
`deploy/vercel/requirements.txt` and push. Vercel redeploys automatically.
Wait a few minutes after the PyPI release before pushing the bump. PyPI's
CDN can take a little while to list a new version, and a Vercel build that
starts too early fails. The previous deployment stays live; push again (an
empty commit is enough) or click *Redeploy* in Vercel.

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
