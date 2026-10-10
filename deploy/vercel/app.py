"""Vercel entrypoint for the hosted rmink web UI.

Vercel Functions accept at most 4.5 MB per request and per response, so the
hosted instance uses tighter limits than a local `rmink web`. Override any of
them with environment variables in the Vercel project settings.
"""

import os

for key, value in {
    "RMINK_MAX_UPLOAD_MB": "4.4",
    "RMINK_MAX_PAGES": "15",
    "RMINK_TIMEOUT_S": "250",
    "RMINK_CONCURRENCY": "2",
}.items():
    os.environ.setdefault(key, value)

from rmink.web import create_app  # noqa: E402

app = create_app()
