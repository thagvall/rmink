"""Send notebooks to the reMarkable Cloud with rmapi (github.com/ddvk/rmapi).

The web server keeps no accounts. Connecting turns the one-time code from
my.remarkable.com into a device token that goes back to the browser, which
sends it along with each upload. Every rmapi run gets its own temp config and
cache, so tokens never mix between users or end up on disk after a request.

The owner's own token (``RMINK_CLOUD_TOKEN`` on the server, or the saved one for
the CLI and MCP server) keeps rmapi's document-tree cache between runs instead.
Without it every run downloads the metadata of every notebook, and a few
rounds in a row get the account rate limited (HTTP 429).

The CLI and MCP server run on the user's own machine and keep their token in
``~/.config/rmink/cloud.toml`` instead (see :func:`save_token`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from rmink import blob_cache

log = logging.getLogger(__name__)

CONNECT_URL = "https://my.remarkable.com/device/browser/connect"
_CODE = re.compile(r"^[a-z0-9]{8}$")
_TOKEN = re.compile(r"^[\w.\-]+$")
_TIMEOUT_S = 90
# Filling an empty tree cache reads every notebook's metadata (~2,900 requests
# on a 1,000-notebook account): give it longer, under Vercel's 300 s limit, and
# more parallel requests, once.
_COLD_TIMEOUT_S = 270
_COLD_CONCURRENT = "6"


class CloudError(Exception):
    """rmapi failed; the message is safe to show to the user."""


class CloudAuthError(CloudError):
    """The device token is missing, revoked or expired."""


class CloudExistsError(CloudError):
    """A document with the same name is already in the target folder."""


class CloudNotFoundError(CloudError):
    """The path does not exist in the user's cloud."""


def token_path() -> Path:
    from rmink.devices import config_dir

    return config_dir() / "cloud.toml"


def load_token() -> str | None:
    """The device token saved by ``rmink cloud connect`` (or $RMINK_CLOUD_TOKEN)."""
    if token := os.environ.get("RMINK_CLOUD_TOKEN"):
        return token
    path = token_path()
    if not path.is_file():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8")).get("devicetoken")


def save_token(token: str) -> Path:
    """Keep the token for the CLI and MCP server; only the user can read it."""
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(f'devicetoken = "{token}"\n', encoding="utf-8")
    return path


def find_rmapi() -> str | None:
    return os.environ.get("RMINK_RMAPI") or shutil.which("rmapi")


def _env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    # rmapi reads its config from RMAPI_CONFIG and caches the document tree in
    # the user cache dir; point everything at the per-request temp dir, and
    # the cache at the lasting one when the session links it (see _session).
    env["RMAPI_CONFIG"] = str(home / "rmapi.conf")
    cache = home / "cache" if (home / "cache").exists() else home
    for key in ("HOME", "XDG_CONFIG_HOME", "APPDATA"):
        env[key] = str(home)
    for key in ("XDG_CACHE_HOME", "LOCALAPPDATA"):
        env[key] = str(cache)
    # rmapi fetches every notebook's metadata into an empty cache, 20 at a time
    # by default; a large account then gets HTTP 429. Two at a time is gentler.
    env.setdefault("RMAPI_CONCURRENT", _COLD_CONCURRENT if _cold(home) else "2")
    return env


def _cold(home: Path) -> bool:
    """The owner's session has no tree cache yet (see _session)."""
    return (home / "cache").exists() and not (home / "cache" / "rmapi" / "tree.cache").exists()


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
            timeout=_COLD_TIMEOUT_S if _cold(home) else _TIMEOUT_S,
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
    if re.search(r"status 429|too many requests", proc.stdout + proc.stderr, re.I):
        return "reMarkable Cloud is limiting requests right now; wait a few minutes and try again"
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


@contextmanager
def _session(device_token: str) -> Iterator[Path]:
    """A temp rmapi home holding only this token. For the owner's token the
    cache dir links to a lasting one, used by one rmapi run at a time."""
    if not _TOKEN.match(device_token or ""):
        raise CloudAuthError("Not connected to reMarkable")
    with tempfile.TemporaryDirectory(prefix="rmink-cloud-") as tmp:
        home = Path(tmp)
        (home / "rmapi.conf").write_text(f"devicetoken: {device_token}\n", encoding="utf-8")
        if device_token != load_token() or os.name == "nt":
            yield home
            return
        digest = hashlib.sha256(device_token.encode()).hexdigest()[:16]
        cache = Path(tempfile.gettempdir()) / f"rmink-rmapi-cache-{digest}"
        cache.mkdir(mode=0o700, exist_ok=True)
        with _locked(cache):
            # rmapi keeps the user token it gets for the device token in its config;
            # keeping that too saves a call to the strictly limited token endpoint.
            conf = cache / "rmapi.conf"
            if not conf.exists() or f"devicetoken: {device_token}\n" not in conf.read_text("utf-8"):
                conf.write_text(f"devicetoken: {device_token}\n", encoding="utf-8")
            conf.chmod(0o600)
            (home / "rmapi.conf").unlink()
            (home / "rmapi.conf").symlink_to(conf)
            # Linux finds it through XDG_CACHE_HOME (_env), macOS under $HOME. Not on
            # Windows, where links need extra rights.
            (home / "cache").symlink_to(cache, target_is_directory=True)
            (home / "Library").mkdir()
            (home / "Library" / "Caches").symlink_to(cache, target_is_directory=True)
            # A new server instance starts without it: fetch it from Vercel Blob.
            tree = cache / "rmapi" / "tree.cache"
            before = blob_cache.restore(tree, digest)
            try:
                yield home
            finally:
                blob_cache.save(tree, digest, before)


@contextmanager
def _locked(cache: Path) -> Iterator[None]:
    """Keep two rmapi runs from writing the same tree cache at once."""
    try:
        import fcntl
    except ImportError:  # Windows: the CLI runs one command at a time anyway
        yield
        return
    with open(cache / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _check_auth(proc: subprocess.CompletedProcess) -> None:
    output = proc.stdout + proc.stderr
    if "missing token" in output or "Unauthorized" in output:
        raise CloudAuthError("The reMarkable connection has expired; connect again")


def _failed(proc: subprocess.CompletedProcess) -> bool:
    # rmapi reports some command errors on stderr but still exits 0.
    return proc.returncode != 0 or bool(re.search(r"error", proc.stderr, re.I))


def _missing(proc: subprocess.CompletedProcess) -> bool:
    output = proc.stdout + proc.stderr
    # rmapi says "directory doesn't exist", or "entry 'X' doesnt exist" for a
    # missing folder on the way.
    return "no matches for" in output or re.search(r"doesn'?t exist", output) is not None


@dataclass(frozen=True)
class Entry:
    name: str
    folder: bool


def ls(device_token: str, path: str = "/") -> list[Entry]:
    """Documents and folders in ``path`` of the user's cloud."""
    with _session(device_token) as home:
        proc = _run(["-ni", "ls", path], home)
    _check_auth(proc)
    if proc.returncode != 0:
        if _missing(proc):
            raise CloudNotFoundError(f'"{path}" does not exist')
        raise CloudError("Listing failed: " + _message(proc))
    entries = []
    for line in proc.stdout.splitlines():
        # rmapi prints "[d]\tname" for folders and "[f]\tname" for documents.
        m = re.match(r"^\[([df])\]\s+(.*\S)\s*$", line)
        if m:
            entries.append(Entry(m.group(2), m.group(1) == "d"))
    return entries


def get(device_token: str, path: str) -> bytes:
    """Download the document at ``path`` (e.g. "/Altan") as .rmdoc bytes."""
    with _session(device_token) as home:
        proc = _run(["-ni", "get", path], home)
        _check_auth(proc)
        # Newer rmapi writes "<name>.rmdoc", older versions "<name>.zip"; both
        # are the same archive layout.
        files = [f for f in home.iterdir() if f.suffix in (".rmdoc", ".zip")]
        if proc.returncode != 0 or not files:
            raise CloudError(f'Could not download "{path}": ' + _message(proc))
        return max(files, key=lambda f: f.stat().st_mtime).read_bytes()


def put(
    path: Path, device_token: str, attempts: int = 20, folder: str = "/", name: str | None = None
) -> str:
    """Upload a .rmdoc to ``folder`` (which must exist) in the user's cloud,
    named ``name`` (default: the file name); returns the name used.

    rmapi names the document after the file, so a taken name is retried as
    "name_2", "name_3" and so on.
    """
    stem = name or path.stem
    with _session(device_token) as home:
        (home / "upload").mkdir()
        upload = home / "upload" / f"{stem}{path.suffix}"
        _without_thumbnails(path, upload)
        for n in range(2, attempts + 2):
            try:
                _put_once(upload, home, folder)
                return upload.stem
            except CloudExistsError:
                upload = upload.rename(upload.with_name(f"{stem}_{n}{path.suffix}"))
    raise CloudExistsError(f'Too many notebooks named "{stem}"; pick another name')


def _without_thumbnails(src: Path, dst: Path) -> None:
    """Copy a .rmdoc without its thumbnails: the cloud rejects their
    "<id>.thumbnails/<page>.png" names from rmapi, and the tablet draws its own."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if ".thumbnails/" not in info.filename:
                zout.writestr(info, zin.read(info))


def _put_once(path: Path, home: Path, folder: str = "/") -> None:
    # -ni: with a bad token rmapi would otherwise wait for a code on stdin.
    proc = _run(["-ni", "put", str(path), folder], home)
    _check_auth(proc)
    if "already exists" in proc.stdout + proc.stderr:
        raise CloudExistsError(path.stem)
    if _missing(proc):
        raise CloudNotFoundError(f'The folder "{folder}" does not exist')
    # rmapi reports some command errors on stderr but still exits 0.
    if proc.returncode != 0 or "OK" not in proc.stdout:
        raise CloudError("Upload failed: " + _message(proc))


def mkdir(device_token: str, path: str) -> None:
    """Create the folder ``path``; its parent must exist. A folder that is
    already there counts as created."""
    with _session(device_token) as home:
        proc = _run(["-ni", "mkdir", path], home)
    _check_auth(proc)
    if "already exists" in proc.stdout + proc.stderr:
        return
    if _failed(proc):
        raise CloudError(f'Could not create "{path}": ' + _message(proc))


def mv(device_token: str, src: str, dst: str) -> None:
    """Move ``src`` to the full path ``dst`` (folder and new name). With the
    name given, a missing folder is an error instead of a rename to it."""
    with _session(device_token) as home:
        proc = _run(["-ni", "mv", src, dst], home)
    _check_auth(proc)
    if "already exists" in proc.stdout + proc.stderr:
        raise CloudExistsError(dst)
    if _failed(proc):
        raise CloudError(f'Could not move "{src}": ' + _message(proc))


def _read_token(conf: Path) -> str | None:
    for line in conf.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "devicetoken":
            value = value.strip().strip("'\"")
            return value if _TOKEN.match(value) else None
    return None
