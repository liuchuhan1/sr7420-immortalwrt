#!/bin/sh
# Stock host: the authenticated container may request one ordinary boot.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
state=/Plugin/sr7420-usb-autostart
once=/var/sr7420-usb-autostart.once

[ "$(id -u)" = 0 ] && [ "$(uname -r)" = 5.4.196 ] || exit 1
[ "$(tr -d '\000\r\n' </proc/device-tree/model)" = 'ZTE 133' ] || exit 1
awk '$2=="/" && $3=="jffs2" {ok=1} END{exit !ok}' /proc/mounts || exit 1
awk '$2=="/var" && $3=="tmpfs" {ok=1} END{exit !ok}' /proc/mounts || exit 1
[ -d "$state" ] && [ ! -L "$state" ] || exit 1
for file in enabled usb-serial usb-pin host.sh sha256 sr7420-usb.sh; do
 [ -f "$state/$file" ] && [ ! -L "$state/$file" ] || exit 1
done
[ "$(cat "$state/enabled")" = sr7420-usb44 ] && [ -x "$state/sha256" ] || exit 1
serial=$(cat "$state/usb-serial")
case "$serial" in ''|*[!A-Za-z0-9_.:-]*) exit 1;; esac
pin=$(cat "$state/usb-pin")
case "$pin" in ''|*[!0-9a-f:]*) exit 1;; esac
[ "${#pin}" = 259 ] || exit 1

case "$#:${1:-}" in
 0:)
  busybox --list | grep -q '^setsid$' || exit 1
  mkdir -m 700 "$once" || exit 1
  (
   trap '' HUP
   exec busybox setsid /bin/sh "$state/host.sh" boot
  ) </dev/null >"$once/launch.log" 2>&1 &
  worker=$!
  for delay in 1 2 3; do
   [ ! -d "$once/worker" ] || break
   kill -0 "$worker" 2>/dev/null || break
   sleep 1
  done
  [ -d "$once/worker" ] || exit 1
  printf '%s\n' SR7420_AUTOSTART_QUEUED
  ;;
 1:boot)
  [ -d "$once" ] && [ ! -L "$once" ] || exit 1
  mkdir -m 700 "$once/worker" || exit 1
  cd /
  # A single launch after startup. The launcher verifies the USB and honors boot-pending.
  exec /bin/sh "$state/sr7420-usb.sh" boot --serial "$serial" --autostart-pin "$pin"
  ;;
 *) exit 1;;
esac
