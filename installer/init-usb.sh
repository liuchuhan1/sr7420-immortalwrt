#!/bin/sh
export PATH=/bin:/sbin
# The initramfs contains the exact musl interpreter and busybox dependencies.
B=/bin/busybox
$B mount -t proc proc /proc
$B mount -t sysfs sysfs /sys
$B mount -t devtmpfs devtmpfs /dev
log() { echo "<0>SR7420_STD: USB44 $*" >/dev/kmsg; }
fail() { log "FAILED $*"; $B sync; $B reboot -f; echo b >/proc/sysrq-trigger; while :; do $B sleep 1; done; }
($B sleep 150; log EARLY_DEADLINE; $B reboot -f; $B sleep 5; echo b >/proc/sysrq-trigger) &
EARLY_GUARD=$!
SERIAL=
for arg in $($B cat /proc/cmdline); do case "$arg" in sr7420_usb_serial=*) SERIAL=${arg#*=};; esac; done
# CONFIG_CMDLINE_FORCE on this board can discard kexec --append.
# If no serial is supplied, match physical USB serial to the installed marker.
[ -f /load-usb.sh ] || fail missing-usb-module-loader
. /load-usb.sh || fail usb-module-load
$B mkdir -p /new_root
log "WAIT_USB serial=$SERIAL"
root=
tries=0
while [ "$tries" -lt 45 ] && [ -z "$root" ]; do
 for node in /sys/class/block/sd*; do
  [ -e "$node" ] || continue
  [ ! -e "$node/partition" ] || continue
  d=${node##*/}
  p=$($B readlink -f "$node/device")
  case "$p" in */usb[0-9]*/*) :;; *) continue;; esac
  sn=
  while [ "$p" != / ] && [ -n "$p" ]; do
   if [ -r "$p/serial" ]; then sn=$($B cat "$p/serial"); break; fi
   p=${p%/*}; [ -n "$p" ] || p=/
  done
  [ -n "$sn" ] || continue
  [ -z "$SERIAL" ] || [ "$sn" = "$SERIAL" ] || continue
  [ -r "/sys/class/block/${d}2/dev" ] || continue
  mm=$($B cat "/sys/class/block/${d}2/dev")
  [ -b "/dev/${d}2" ] || $B mknod "/dev/${d}2" b "${mm%:*}" "${mm#*:}"
  if $B mount -t ext4 -o ro,noload "/dev/${d}2" /new_root; then
   if [ "$($B cat /new_root/etc/sr7420-usb-release 2>/dev/null)" = sr7420-usb44 ] && [ "$($B cat /new_root/etc/sr7420-usb-serial 2>/dev/null)" = "$sn" ] && [ -x /new_root/usr/sbin/sr7420-ram-init ]; then root=/dev/${d}2; SERIAL=$sn; break; fi
   $B umount /new_root
  fi
 done
 [ -n "$root" ] || $B sleep 1
 tries=$((tries+1))
done
[ -n "$root" ] || fail usb-root-not-found
$B umount /new_root || fail unmount-probe
$B mount -t ext4 -o rw "$root" /new_root || fail mount-root-rw
$B mkdir -p /new_root/boot /new_root/proc /new_root/sys /new_root/dev
$B mkdir -p /new_root/boot-state
printf '%s\n' "$d" >/new_root/etc/sr7420-usb-disk
printf 'ROOT_READY tries=%s\n' "$tries" >>/new_root/boot-state/stages.log
log "ROOT_READY device=$root tries=$tries"
# Skip fstools flash-root discovery; the real writable root is already USB ext4.
export INITRAMFS=1
kill "$EARLY_GUARD" 2>/dev/null || true
exec $B switch_root /new_root /usr/sbin/sr7420-ram-init
fail switch-root
