#!/bin/sh
# Invoked only from the authenticated stock administrator's launcher.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
export PATH LC_ALL
umask 077
state=/Plugin/sr7420-usb-autostart
guest_dir=/etc/sr7420-usb-autostart
managed=sr7420-usb-autostart-v1
action=${1:?autostart action required}
self=${0%/*}
run=/var/sr7420-usb-autostart.setup
guest_created=0
host_created=0
committed=0

log() { printf '%s\n' "SR7420-AUTOSTART: $*"; }
die() { log "ERROR: $*" >&2; exit 1; }
in_guest() {
 attached=0
 # Keep lxc-attach noninteractive even when the caller uses a Telnet terminal.
 lxc-attach -n nativeC -- "$@" >"$run/attach.log" 2>&1 || attached=$?
 cat "$run/attach.log" || return 1
 return "$attached"
}
configure_guest() {
 # Pass the complete script as one argument; no shell commands depend on lxc stdin delivery.
 script=$(cat "$self/guest-config.sh") || return 1
 if ! result=$(in_guest /bin/sh -c "$script" sh "$1" </dev/null); then
  printf '%s\n' "$result" >&2
  return 1
 fi
 [ "$result" = "SR7420_GUEST_CONFIG:$1" ] || return 1
}
is_managed() {
 [ -d "$state" ] && [ ! -L "$state" ] && [ -f "$state/managed" ] && [ ! -L "$state/managed" ] &&
  [ "$(cat "$state/managed")" = "$managed" ]
}
remove_state() {
 rm -f "$state/enabled" "$state/enable.new" "$state/host.sh" "$state/sha256" "$state/sr7420-usb.sh" \
       "$state/usb-serial" "$state/usb-pin" "$state/guest-config.sh" "$state/manage.sh" "$state/managed"
 rmdir "$state"
 sync
}
cleanup() {
 status=$?
 set +e
 if [ "$status" != 0 ] && [ "$host_created" = 1 ] && [ "$committed" = 0 ]; then
  rm -f "$state/enabled"
  if [ "$guest_created" = 1 ] && ! configure_guest remove && ! in_guest /bin/rmdir "$guest_dir" </dev/null; then
   log 'setup was disarmed; run disable-autostart to finish cleanup' >&2
  else
   remove_state
  fi
 fi
 rm -f "$run/guest.sh" "$run/login" "$run/managed" "$run/guest.tar" "$run/attach.log"
 rmdir "$run"
}

[ "$(id -u)" = 0 ] && [ "$(uname -r)" = 5.4.196 ] || die 'use the stock host root shell'
[ "$(tr -d '\000\r\n' </proc/device-tree/model)" = 'ZTE 133' ] || die 'unexpected stock board'
awk '$2=="/" && $3=="jffs2" {root=1} $2=="/var" && $3=="tmpfs" {ram=1}
     $2=="/Plugin" && $3=="jffs2" && $4 ~ /^rw(,|$)/ {plugin=1}
     END {exit !(root && ram && plugin)}' /proc/mounts || die 'unexpected stock mounts'
[ "$(readlink -f /apps)" = /Plugin ] || die 'unexpected nativeC backing storage'
[ -f "$self/guest-config.sh" ] || die 'incomplete autostart payload'
mkdir -m 700 "$run" || die 'another autostart configuration is running'
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

case "$action" in
 install)
  [ "$#" = 4 ] || die 'invalid autostart installer arguments'
  launcher=$2
  serial=$3
  pin=$4
  case "$serial" in ''|*[!A-Za-z0-9_.:-]*) die 'unsupported USB serial';; esac
  case "$pin" in ''|*[!0-9a-f:]*) die 'invalid USB manifest pin';; esac
  [ "${#pin}" = 259 ] || die 'invalid USB manifest pin length'
  if [ -e "$state" ] || [ -L "$state" ]; then
   is_managed || die 'unknown stock autostart directory'
   if [ "$(cat "$state/enabled" 2>/dev/null)" = sr7420-usb44 ] &&
      [ "$(cat "$state/usb-serial" 2>/dev/null)" = "$serial" ] &&
      [ "$(cat "$state/usb-pin" 2>/dev/null)" = "$pin" ]; then
    configure_guest status || die 'disable existing autostart before reconfiguring it'
    log 'autostart is already enabled for this USB disk'
    exit 0
   fi
   die 'disable existing autostart before reconfiguring it'
  fi
  [ ! -t 0 ] || die 'supply the authorized stock Telnet username and password as two lines on stdin'
  IFS= read -r user && IFS= read -r password || die 'missing Telnet credentials on stdin'
  case "$user" in ''|*[!A-Za-z0-9_.-]*) die 'invalid Telnet username';; esac
  case "$password" in ''|*[![:print:]]*) die 'Telnet password must be printable ASCII';; esac
  [ "${#user}" -le 64 ] && [ "${#password}" -le 128 ] || die 'Telnet credentials are too long'
  printf '%s\n' "$user" "$password" >"$run/login"
  unset password
  configure_guest check || die 'nativeC startup check failed'
  for file in "$self/guest.sh" "$self/host.sh" "$launcher/sr7420-usb.sh" "$launcher/sha256"; do
   [ -f "$file" ] && [ ! -L "$file" ] || die 'incomplete autostart payload'
  done
  [ -x "$launcher/sha256" ] || die 'launcher sha256 tool is not executable'
  busybox --list | grep -q '^setsid$' || die 'stock cannot detach the launcher'

  mkdir -m 700 "$state"
  host_created=1
  printf '%s\n' "$managed" >"$state/managed"
  printf '%s\n' "$serial" >"$state/usb-serial"
  printf '%s\n' "$pin" >"$state/usb-pin"
  cp "$self/host.sh" "$self/manage.sh" "$self/guest-config.sh" "$launcher/sr7420-usb.sh" "$launcher/sha256" "$state/"
  chmod 700 "$state/sha256"

  cp "$self/guest.sh" "$run/guest.sh"
  printf '%s\n' "$managed" >"$run/managed"
  (cd "$run"; tar cf guest.tar managed guest.sh login)
  in_guest /bin/mkdir -m 700 "$guest_dir" </dev/null
  guest_created=1
  in_guest /bin/tar xf - -C "$guest_dir" <"$run/guest.tar"
  rm -f "$run/login" "$run/guest.tar"
  if ! probe=$(in_guest /bin/sh "$guest_dir/guest.sh" probe </dev/null); then
   printf '%s\n' "$probe" | grep '^SR7420-AUTOSTART: ' >&2 || :
   die 'nativeC could not log in to stock Telnet over loopback'
  fi
  [ "$probe" = SR7420_AUTOSTART_HOST_OK ] || die 'unverified stock Telnet session'
  configure_guest add || die 'nativeC startup configuration failed'
  sync
  printf '%s\n' sr7420-usb44 >"$state/enable.new"
  mv "$state/enable.new" "$state/enabled"
  sync
  committed=1
  log 'autostart enabled for the next stock boot'
  ;;
 disable)
  [ "$#" = 1 ] || die 'invalid autostart disable arguments'
  if [ ! -e "$state" ] && [ ! -L "$state" ]; then
   configure_guest remove || die 'autostart is disarmed; nativeC cleanup still required'
   sync
   log 'autostart disabled and saved Telnet login removed'
   exit 0
  fi
  is_managed || die 'unknown stock autostart directory'
  rm -f "$state/enabled"
  sync
  configure_guest remove || die 'autostart is disarmed; nativeC cleanup still required'
  remove_state
  log 'autostart disabled and saved Telnet login removed'
  ;;
 *) die 'invalid autostart configuration action';;
esac
