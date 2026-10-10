"""Optional links shown by the web UI and `rmink web`.

rmink is free. People who want to can support it through a Stripe Payment
Link; hosted deployments must also link to the source (AGPL-3.0 section 13).
Set either to an empty string to hide it.
"""

from __future__ import annotations

import os

# Filled in once the Stripe Payment Link and public repository exist.
DEFAULT_SUPPORT_URL = ""
DEFAULT_SOURCE_URL = ""


def support_url() -> str:
    return os.environ.get("RMINK_SUPPORT_URL", DEFAULT_SUPPORT_URL).strip()


def source_url() -> str:
    return os.environ.get("RMINK_SOURCE_URL", DEFAULT_SOURCE_URL).strip()
