#!/bin/sh
# Disable this launcher's state without changing flash partitions or USB data.
set -eu
STATE=${1:?usage: sr7420-usb-disable.sh /verified/persistent/state}
case "$STATE" in /*) :;; *) exit 1;; esac
[ -d "$STATE" ] || exit 1
[ "$(cat "$STATE/enabled" 2>/dev/null)" = sr7420-usb44 ] || exit 0
mv "$STATE/enabled" "$STATE/disabled"
sync
printf '%s\n' 'USB automatic launching disabled; vendor boot path retained.'
