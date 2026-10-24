"""Vercel entrypoint for the hosted rmink web UI.

Vercel Functions accept at most 4.5 MB per request and per response, so the
hosted instance uses tighter limits than a local `rmink web`. Override any of
them with environment variables in the Vercel project settings.
"""

import os
import shutil
import stat
from pathlib import Path

for key, value in {
    "RMINK_MAX_UPLOAD_MB": "4.4",
    "RMINK_MAX_PAGES": "15",
    "RMINK_TIMEOUT_S": "250",
    "RMINK_CONCURRENCY": "2",
}.items():
    os.environ.setdefault(key, value)

# rmapi for "Send to reMarkable" (see fetch-rmapi.sh). The deployment may drop
# the executable bit, so run a copy from /tmp if needed.
_rmapi = Path(__file__).parent / "bin" / "rmapi"
if _rmapi.exists() and "RMINK_RMAPI" not in os.environ:
    if not os.access(_rmapi, os.X_OK):
        _rmapi = Path(shutil.copy(_rmapi, "/tmp/rmapi"))
        _rmapi.chmod(_rmapi.stat().st_mode | stat.S_IXUSR)
    os.environ["RMINK_RMAPI"] = str(_rmapi)

from rmink.web import create_app  # noqa: E402

app = create_app()
