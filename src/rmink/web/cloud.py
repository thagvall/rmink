"""Send notebooks to the reMarkable Cloud with rmapi (github.com/ddvk/rmapi).

The server keeps no accounts. Connecting turns the one-time code from
my.remarkable.com into a device token that goes back to the browser, which
sends it along with each upload. Every rmapi run gets its own temp config and
cache, so tokens never mix between users or end up on disk after a request.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

CONNECT_URL = "https://my.remarkable.com/device/browser/connect"
_CODE = re.compile(r"^[a-z0-9]{8}$")
_TOKEN = re.compile(r"^[\w.\-]+$")
_TIMEOUT_S = 90


class CloudError(Exception):
    """rmapi failed; the message is safe to show to the user."""


class CloudAuthError(CloudError):
    """The device token is missing, revoked or expired."""


class CloudExistsError(CloudError):
    """A document with the same name is already in the target folder."""


def find_rmapi() -> str | None:
    return os.environ.get("RMINK_RMAPI") or shutil.which("rmapi")


def _env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    # rmapi reads its config from RMAPI_CONFIG and caches the document tree in
    # the user cache dir; point everything at the per-request temp dir.
    env["RMAPI_CONFIG"] = str(home / "rmapi.conf")
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
        env[key] = str(home)
    return env


def _run(args: list[str], home: Path, stdin: str | None = None) -> subprocess.CompletedProcess:
    exe = find_rmapi()
    if not exe:
        raise CloudError("rmapi is not installed on this server")
    try:
        return subprocess.run(
            [exe, *args],
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            env=_env(home),
            cwd=home,
            timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise CloudError("reMarkable Cloud did not answer in time; try again") from e


def _message(proc: subprocess.CompletedProcess) -> str:
    out = re.sub(r"(Bearer |token:? ?)\S+|eyJ[\w.\-]+", r"\1<redacted>", proc.stdout + proc.stderr)
    log.warning("rmapi failed (%s):\n%s", proc.returncode, out)
    # The error is on stderr; stdout only has progress like "uploading: [...]...".
    lines = [ln.strip() for ln in (proc.stderr or proc.stdout).splitlines() if ln.strip()]
    if not lines:
        return f"rmapi exited with code {proc.returncode}"
    # Drop the timestamp rmapi's logger prefixes and our temp paths.
    msg = re.sub(r"^\w+: \d{4}/\d\d/\d\d \d\d:\d\d:\d\d(\.\d+)? ", "", lines[-1])
    return re.sub(r"\[?/\S*/([^/\s\]]+)\]?", r"\1", msg)[:300]


def connect(code: str) -> str:
    """Register this app with the user's account; returns the device token."""
    code = code.strip().lower()
    if not _CODE.match(code):
        raise ValueError("The one-time code has 8 characters; get one at " + CONNECT_URL)
    with tempfile.TemporaryDirectory(prefix="rmink-cloud-") as tmp:
        home = Path(tmp)
        proc = _run(["ls", "/"], home, stdin=code + "\n")
        conf = home / "rmapi.conf"
        token = _read_token(conf) if conf.exists() else None
        if proc.returncode != 0 or not token:
            raise CloudAuthError("reMarkable did not accept the code; get a new one and try again")
        return token


def put(path: Path, device_token: str, attempts: int = 20) -> str:
    """Upload a .rmdoc to the root of the user's cloud; returns the name used.

    rmapi names the document after the file, so a taken name is retried as
    "name_2", "name_3" and so on.
    """
    if not _TOKEN.match(device_token or ""):
        raise CloudAuthError("Not connected to reMarkable")
    with tempfile.TemporaryDirectory(prefix="rmink-cloud-") as tmp:
        home = Path(tmp)
        (home / "rmapi.conf").write_text(f"devicetoken: {device_token}\n", encoding="utf-8")
        (home / "upload").mkdir()
        upload = home / "upload" / path.name
        _without_thumbnails(path, upload)
        for n in range(2, attempts + 2):
            try:
                _put_once(upload, home)
                return upload.stem
            except CloudExistsError:
                upload = upload.rename(upload.with_name(f"{path.stem}_{n}{path.suffix}"))
    raise CloudExistsError(f'Too many notebooks named "{path.stem}"; pick another name')


def _without_thumbnails(src: Path, dst: Path) -> None:
    """Copy a .rmdoc without its thumbnails: the cloud rejects their
    "<id>.thumbnails/<page>.png" names from rmapi, and the tablet draws its own."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if ".thumbnails/" not in info.filename:
                zout.writestr(info, zin.read(info))


def _put_once(path: Path, home: Path) -> None:
    # -ni: with a bad token rmapi would otherwise wait for a code on stdin.
    proc = _run(["-ni", "put", str(path), "/"], home)
    output = proc.stdout + proc.stderr
    if "missing token" in output or "Unauthorized" in output:
        raise CloudAuthError("The reMarkable connection has expired; connect again")
    if "already exists" in output:
        raise CloudExistsError(path.stem)
    # rmapi reports some command errors on stderr but still exits 0.
    if proc.returncode != 0 or "OK" not in proc.stdout:
        raise CloudError("Upload failed: " + _message(proc))


def _read_token(conf: Path) -> str | None:
    for line in conf.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "devicetoken":
            value = value.strip().strip("'\"")
            return value if _TOKEN.match(value) else None
    return None
