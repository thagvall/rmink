#!/bin/sh
# Download the pinned rmapi (github.com/ddvk/rmapi) for Vercel's Linux runtime
# into bin/rmapi. The binary is committed; rerun this to change version.
set -eu
VERSION=v0.0.35
SHA256=117616151d11937446ead6972b0934f97155443087f8406141db38fd1ac8fb25
cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/rmapi.tar.gz" \
  "https://github.com/ddvk/rmapi/releases/download/$VERSION/rmapi-linux-amd64.tar.gz"
echo "$SHA256  $tmp/rmapi.tar.gz" | shasum -a 256 -c -
tar -xzf "$tmp/rmapi.tar.gz" -C "$tmp"
mkdir -p bin
install -m 755 "$tmp/rmapi" bin/rmapi
echo "bin/rmapi: rmapi $VERSION (linux-amd64)"
