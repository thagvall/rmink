"""The public pages in deploy/vercel: links that are already out in posts must
keep working, and every link on a generated page must lead somewhere."""

import json
import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).parent.parent / "deploy" / "vercel"
PUBLIC = DEPLOY / "public"
CONFIG = json.loads((DEPLOY / "vercel.json").read_text())
REWRITES = {r["source"]: r["destination"] for r in CONFIG["rewrites"]}
PAGES = ["home.html", "home-sv.html", "skola.html", "bygg.html"]
# Served by FastAPI rather than public/.
APP_ROUTES = {"/app", "/rounds", "/thanks"}


def _resolves(url: str) -> bool:
    path = url.split("#")[0].split("?")[0] or "/"
    if path in APP_ROUTES or path in REWRITES:
        return path not in REWRITES or (PUBLIC / REWRITES[path].lstrip("/")).is_file()
    return (PUBLIC / path.lstrip("/")).is_file()


def test_rewrites_point_at_files():
    for source, destination in REWRITES.items():
        assert (PUBLIC / destination.lstrip("/")).is_file(), source


@pytest.mark.parametrize(
    "url",
    ["/", "/sv", "/skola", "/bygg", "/video", "/video/sv", "/sketch", "/sketch/sv", "/skiss",
     "/sketch/video", "/sketch/video/sv"],
)  # fmt: skip
def test_public_urls_exist(url):
    assert url in REWRITES


def test_the_home_page_does_not_shadow_the_app():
    # Without public/index.html, / is decided by the rewrite and `rmink web` is untouched.
    assert not (PUBLIC / "index.html").exists()


def test_video_share_pages_open_the_video():
    assert 'location.replace("/?demo=en")' in (PUBLIC / "video.html").read_text(encoding="utf-8")
    swedish = (PUBLIC / "video-sv.html").read_text(encoding="utf-8")
    assert 'location.replace("/sv?demo=sv")' in swedish


@pytest.mark.parametrize("name", PAGES + ["sketch.html", "sketch-sv.html"])
def test_page_links_resolve(name):
    text = (PUBLIC / name).read_text(encoding="utf-8")
    links = re.findall(r'(?:href|src|data-video|data-poster)="(/[^"/][^"]*|/)"', text)
    missing = sorted({link for link in links if not _resolves(link)})
    assert links and not missing


@pytest.mark.parametrize("name", PAGES)
def test_page_is_ready_to_share(name):
    text = (PUBLIC / name).read_text(encoding="utf-8")
    assert 'rel="canonical"' in text and 'property="og:title"' in text
    image = re.search(r'og:image" content="https://rmink\.vercel\.app(/[^"]+)"', text)
    assert image and (PUBLIC / image[1].lstrip("/")).is_file()
    # A video to open with ?demo, and the source link AGPL-3.0 section 13 asks for.
    assert 'data-video="/promo/' in text and "github.com/thagvall/rmink" in text


def test_owner_pages_are_not_linked():
    for name in PAGES:
        assert "/rounds" not in (PUBLIC / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["home.html", "home-sv.html"])
def test_home_pages_name_each_other(name):
    text = (PUBLIC / name).read_text(encoding="utf-8")
    assert 'hreflang="en"' in text and 'hreflang="sv"' in text
