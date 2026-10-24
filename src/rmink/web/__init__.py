"""Web UI: drop files, tune options with a live preview, download a .rmdoc.

Run locally with ``rmink web``. For hosting, the limits below can be tightened
with environment variables:

- ``RMINK_MAX_UPLOAD_MB`` (default 25): total upload size per request
- ``RMINK_MAX_FILES`` (default 20): files per request
- ``RMINK_MAX_PAGES`` (default 40): pages per request after page selection
- ``RMINK_TIMEOUT_S`` (default 120): conversion time limit per request
- ``RMINK_CONCURRENCY`` (default 2): conversions running at the same time
- ``RMINK_RMAPI``: path to rmapi (github.com/ddvk/rmapi) for the
  "Send to reMarkable" button; by default ``rmapi`` on the PATH. Without it
  the button is hidden.
"""

from rmink.web.app import create_app

__all__ = ["create_app"]
