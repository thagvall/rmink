"""Keep rmapi's document-tree cache in Vercel Blob between cold starts.

reMarkable Cloud has no way to list one folder: rmapi reads the metadata of
every notebook on the account into its tree cache, about 2,900 requests for
1,000 notebooks, and a warm cache needs one. On Vercel the local cache dies
with the instance, so the owner's cache is also kept, gzipped, in a private
Blob store and fetched when an instance starts without one.

It is on when the deployment has a Blob store (``BLOB_STORE_ID`` with
Vercel's OIDC token, or ``BLOB_READ_WRITE_TOKEN``) and ``vercel-blob`` is
installed (the ``rounds`` extra). Any Blob error only costs the cache: rmapi
then syncs from the cloud as before.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def enabled() -> bool:
    if not (os.environ.get("BLOB_STORE_ID") or os.environ.get("BLOB_READ_WRITE_TOKEN")):
        return False
    try:
        import vercel.blob.sync  # noqa: F401
    except ImportError:
        return False
    return True


def _pathname(key: str) -> str:
    return f"rmink/rmapi-tree-{key}.json.gz"


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def restore(tree: Path, key: str) -> str | None:
    """Fetch the tree cache into ``tree`` unless it is there already; return
    the digest of what ``tree`` now holds, for :func:`save`."""
    if not tree.is_file() and enabled():
        from vercel.blob import sync as blob

        try:
            data = gzip.decompress(blob.get_blob(_pathname(key), access="private").body)
        except blob.BlobNotFoundError:
            data = None
        except Exception as e:  # noqa: BLE001 - a missing cache is never fatal
            log.warning("Could not fetch the rmapi cache from Blob: %s", e)
            data = None
        if data:
            tree.parent.mkdir(parents=True, exist_ok=True)
            tree.write_bytes(data)
    return _digest(tree)


def save(tree: Path, key: str, before: str | None) -> None:
    """Upload ``tree`` if rmapi changed it since :func:`restore`."""
    after = _digest(tree)
    if after is None or after == before or not enabled():
        return
    from vercel.blob import sync as blob

    try:
        blob.put_blob(
            _pathname(key),
            gzip.compress(tree.read_bytes(), compresslevel=6),
            access="private",
            content_type="application/gzip",
            allow_overwrite=True,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Could not save the rmapi cache to Blob: %s", e)
