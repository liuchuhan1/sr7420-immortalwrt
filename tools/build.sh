#!/bin/sh
# Run as an ordinary build user after tools/configure.py.
set -eu
TOPDIR=${1:?usage: build.sh /path/to/immortalwrt [jobs]}
JOBS=${2:-8}
cd "$TOPDIR"
[ "$(id -u)" != 0 ] || { echo "Build as an ordinary user" >&2; exit 1; }
make -j"$JOBS" V=s
