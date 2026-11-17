#!/bin/sh
# Called only by a separately verified vendor startup hook. This file installs none.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
STATE=${1:?usage: sr7420-usb-autostart.sh /verified/persistent/state}
case "$STATE" in /*) :;; *) exit 1;; esac
[ -d "$STATE" ] && [ "$(cat "$STATE/enabled" 2>/dev/null)" = sr7420-usb44 ] || exit 0
[ -f "$STATE/usb-serial" ] && [ -f "$STATE/sr7420-usb.sh" ] || exit 0
SERIAL=$(cat "$STATE/usb-serial")
case "$SERIAL" in ''|*[!A-Za-z0-9_.:-]*) exit 1;; esac
# A failed or absent USB launch returns normally and lets the vendor boot continue.
# A boot-pending marker is honored by the launcher; no automatic --retry is used.
if [ -f "$STATE/allow-format" ]; then
 sh "$STATE/sr7420-usb.sh" install --serial "$SERIAL" --erase || exit 0
 mv "$STATE/allow-format" "$STATE/format-used"
 sh "$STATE/sr7420-usb.sh" boot --serial "$SERIAL" || exit 0
else
 sh "$STATE/sr7420-usb.sh" boot --serial "$SERIAL" || exit 0
fi
