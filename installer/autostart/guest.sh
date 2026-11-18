#!/bin/sh
# Native container: use the existing Telnet login on the shared loopback only.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
export PATH LC_ALL
umask 077

fail() { printf '%s\n' "SR7420-AUTOSTART: $*" >&2; exit 1; }
case "${1:-boot}" in
 boot)
  exec >/var/run/sr7420-usb-autostart.log 2>&1
  # Allow stock services and hardware initialization to finish before logging in.
  sleep 35
  request='exec /bin/sh /Plugin/sr7420-usb-autostart/host.sh'
  answer=SR7420_AUTOSTART_QUEUED
  ;;
 probe)
  request='[ "$(id -u)" = 0 ] && [ "$(uname -r)" = 5.4.196 ] && awk '\''$2=="/" && $3=="jffs2" {ok=1} END{exit !ok}'\'' /proc/mounts && printf "\n%s%s\n" SR7420_AUTOSTART_ HOST_OK'
  answer=SR7420_AUTOSTART_HOST_OK
  ;;
 *) fail 'invalid guest action';;
esac
dir=${0%/*}
[ -d "$dir" ] && [ ! -L "$dir" ] || fail 'invalid guest directory'
[ -f "$dir/login" ] && [ ! -L "$dir/login" ] || fail 'login is not provisioned'
[ "$(stat -c '%a:%u:%g' "$dir/login")" = 600:0:0 ] || fail 'login must be private to root'
{
 IFS= read -r user && IFS= read -r password && ! IFS= read -r extra
} <"$dir/login" || fail 'invalid login file'
[ -n "$user" ] && [ -n "$password" ] || fail 'incomplete login'

work=$(mktemp -d /var/run/sr7420-usb-telnet.XXXXXX) || fail 'cannot allocate a private session directory'
client=
cleanup() {
 exec 3>&- 4<&-
 if [ -n "$client" ]; then
  kill "$client" 2>/dev/null || :
  wait "$client" 2>/dev/null || :
 fi
 rm -f "$work/in" "$work/out"
 rmdir "$work"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
mkfifo "$work/in" "$work/out"
timeout 35 telnet 127.0.0.1 23 <"$work/in" >"$work/out" 2>&1 &
client=$!
exec 3>"$work/in" 4<"$work/out"

expect_suffix() {
 needle=$1
 line=
 count=0
 while [ "$count" -lt 4096 ] && IFS= read -r -n 1 -t 8 ch <&4; do
  count=$((count+1))
  if [ -n "$ch" ]; then line=$line$ch; else line=; fi
  case "$line" in *"$needle") return 0;; esac
 done
 return 1
}

expect_suffix 'ogin:' || fail 'host login prompt unavailable'
# BusyBox telnet converts a single LF into the wire protocol's CR LF.
printf '%s\n' "$user" >&3
expect_suffix 'assword:' || fail 'host password prompt unavailable'
printf '%s\n' "$password" >&3
unset password
expect_suffix '/ #' || fail 'host authentication was not accepted'
printf '%s\n' "$request" >&3
expect_suffix "$answer" || fail 'host did not acknowledge the request'
printf '%s\n' "$answer"
