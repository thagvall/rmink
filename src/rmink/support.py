"""Optional links shown by the web UI and `rmink web`.

rmink is free. People who want to can support it through a Stripe Payment
Link; hosted deployments must also link to the source (AGPL-3.0 section 13).
The demo video is hosted with the public site. Set any of them to an empty
string to hide it.
"""

from __future__ import annotations

import os

DEFAULT_SUPPORT_URL = "https://buy.stripe.com/7sY4gy4b1aQo0iI0SB1sQ00"
DEFAULT_SOURCE_URL = "https://github.com/thagvall/rmink"
# {lang} is "en" or "sv".
DEFAULT_DEMO_URL = "https://rmink.vercel.app/promo/rmink-promo-{lang}.mp4"


def support_url() -> str:
    return os.environ.get("RMINK_SUPPORT_URL", DEFAULT_SUPPORT_URL).strip()


def source_url() -> str:
    return os.environ.get("RMINK_SOURCE_URL", DEFAULT_SOURCE_URL).strip()


def demo_url() -> str:
    """URL template of the demo video; "{lang}" is replaced by en or sv."""
    return os.environ.get("RMINK_DEMO_URL", DEFAULT_DEMO_URL).strip()
