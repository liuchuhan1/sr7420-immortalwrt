#!/bin/sh
# Run through lxc-attach as the stock administrator. Only edit the nativeC init table.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
table=/etc/inittab
dir=/etc/sr7420-usb-autostart
sysinit='::sysinit:/etc/rc'
entry='::once:/bin/sh /etc/sr7420-usb-autostart/guest.sh boot'
managed=sr7420-usb-autostart-v1

die() { printf '%s\n' "SR7420-AUTOSTART: $*" >&2; exit 1; }
contains() { awk -v entry="$1" '$0==entry {found=1} END {exit !found}' "$table"; }
[ -f "$table" ] && [ ! -L "$table" ] || die 'unexpected nativeC inittab'
awk '$5=="/" && $(NF-2)=="overlay" && $NF ~ /(^|,)upperdir=\/apps\/apps(,|$)/ {ok=1} END {exit !ok}' /proc/self/mountinfo || die 'unexpected nativeC overlay'
is_managed() {
 [ -d "$dir" ] && [ ! -L "$dir" ] && [ -f "$dir/managed" ] && [ ! -L "$dir/managed" ] &&
  [ "$(cat "$dir/managed")" = "$managed" ]
}
check_sysinit() {
 [ "$(awk -v entry="$sysinit" '$0==entry {n++} END {print n+0}' "$table")" = 1 ] || die 'unexpected nativeC startup entries'
}

replace_table() (
 temp=$(mktemp /etc/.sr7420-usb-inittab.XXXXXX)
 trap 'rm -f "$temp"' EXIT
 cp -p "$table" "$temp"
 awk -v sysinit="$sysinit" -v entry="$entry" -v action="$1" '
  $0==entry {next}
  {print}
  $0==sysinit && action=="add" {print entry}
 ' "$table" >"$temp"
 mv -f "$temp" "$table"
)

case "${1:-}" in
 check)
  [ ! -e "$dir" ] && [ ! -L "$dir" ] || die 'nativeC already has autostart files'
  check_sysinit
  if contains "$entry"; then die 'nativeC already has an autostart entry'; fi
  for applet in mktemp mkfifo stat timeout telnet; do
   command -v "$applet" >/dev/null 2>&1 || die "nativeC is missing $applet"
  done
  ;;
 add)
  is_managed || die 'unknown nativeC autostart files'
  check_sysinit
  if ! contains "$entry"; then replace_table add; fi
  contains "$entry" || die 'nativeC startup entry was not written'
  ;;
 status)
  is_managed && contains "$entry" || die 'nativeC autostart entry is incomplete'
  ;;
 remove)
  if [ -e "$dir" ] || [ -L "$dir" ]; then
   is_managed || die 'unknown nativeC autostart files'
  fi
  if contains "$entry"; then replace_table remove; fi
  if [ -d "$dir" ]; then
   rm -f "$dir/login" "$dir/guest.sh" "$dir/managed"
   rmdir "$dir"
  fi
  [ ! -e "$dir" ] && [ ! -L "$dir" ] || die 'nativeC autostart files remain'
  if contains "$entry"; then die 'nativeC autostart entry remains'; fi
  ;;
 *) die 'invalid nativeC configuration action';;
esac
printf 'SR7420_GUEST_CONFIG:%s\n' "$1"
