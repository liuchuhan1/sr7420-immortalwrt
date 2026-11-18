#!/bin/sh
# Online bootstrap for the immutable USB44 r2 release. Requires a stock root shell.
# Initial script delivery must use authenticated HTTPS; see online_install_command.py.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
BASE=https://github.com/liuchuhan1/sr7420-immortalwrt/releases/download/usb44-r2-20261118
LAUNCHER_SHA=4a5d5bcadd39282d393f4231409265e329043372fa5bff4bd359c131e80c3bb5
INSTALLER_SHA=f8db7ecfc4f5ceb5f6b8369a7e009b3abb652529bb00971c36db5d7d60a32054
SHA_TOOL_SHA=8ff4bde2872b94cb1a451f12440478d83179b87ecd5a9345082747975e942bbd
log() { printf '%s\n' "SR7420-ONLINE: $*"; }
die() { log "ERROR: $*" >&2; exit 1; }
CMD=${1:-detect}
[ $# -eq 0 ] || shift
AUTO=0
case "$CMD" in
 detect|verify|boot|install) :;;
 *) die 'usage: sh sr7420-install-online.sh detect|install|verify|boot [--erase-single-usb] [installer options]';;
esac
# This explicit option authorizes erasure only when exactly one eligible USB exists.
# Multiple disks, serial-less disks, mounted disks and a running USB root are rejected.
case " ${*} " in *' --erase-single-usb '*)
 [ "${1:-}" = --erase-single-usb ] || die '--erase-single-usb must be the first option'
 [ "$CMD" = install ] || die '--erase-single-usb is only valid for install'
 AUTO=1; shift
 for option in "$@"; do
  case "$option" in --boot) :;; *) die "single-USB mode accepts only --boot; use explicit installer options otherwise";; esac
 done;; esac
[ "$(id -u)" = 0 ] || die 'run from an authorized stock root shell'
[ "$(uname -r)" = 5.4.196 ] || die 'return to the validated stock 5.4.196 system first; no disk changed'
MODEL=$(tr -d '\000\r\n' </proc/device-tree/model)
[ "$MODEL" = 'ZTE 133' ] || die 'unexpected board; no disk changed'
awk '$2=="/var" && $3=="tmpfs" {ok=1} END {exit !ok}' /proc/mounts || die '/var must be RAM-backed'
command -v curl >/dev/null 2>&1 || die 'stock HTTPS curl is required'
MEM=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[ -n "$MEM" ] && [ "$MEM" -ge 286720 ] || die 'at least 280 MiB available RAM is required'
WORK=/var/sr7420-online.$$
mkdir -m 700 "$WORK" || die 'cannot create private RAM directory'
MOUNTED=0
cleanup() {
 set +e
 if [ "$MOUNTED" = 1 ]; then umount "$WORK" || return; fi
 rmdir "$WORK" 2>/dev/null
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
mount -t tmpfs -o size=24576k,mode=700 tmpfs "$WORK" || die 'cannot allocate bounded launcher workspace'
MOUNTED=1
# Public roots: USERTrust ECC Certification Authority and ISRG Root X1.
# Copied from certificate chains validated by the development host trust store.
cat >"$WORK/ca.pem" <<'SR7420_PUBLIC_ROOTS'
-----BEGIN CERTIFICATE-----
MIICjzCCAhWgAwIBAgIQXIuZxVqUxdJxVt7NiYDMJjAKBggqhkjOPQQDAzCBiDEL
MAkGA1UEBhMCVVMxEzARBgNVBAgTCk5ldyBKZXJzZXkxFDASBgNVBAcTC0plcnNl
eSBDaXR5MR4wHAYDVQQKExVUaGUgVVNFUlRSVVNUIE5ldHdvcmsxLjAsBgNVBAMT
JVVTRVJUcnVzdCBFQ0MgQ2VydGlmaWNhdGlvbiBBdXRob3JpdHkwHhcNMTAwMjAx
MDAwMDAwWhcNMzgwMTE4MjM1OTU5WjCBiDELMAkGA1UEBhMCVVMxEzARBgNVBAgT
Ck5ldyBKZXJzZXkxFDASBgNVBAcTC0plcnNleSBDaXR5MR4wHAYDVQQKExVUaGUg
VVNFUlRSVVNUIE5ldHdvcmsxLjAsBgNVBAMTJVVTRVJUcnVzdCBFQ0MgQ2VydGlm
aWNhdGlvbiBBdXRob3JpdHkwdjAQBgcqhkjOPQIBBgUrgQQAIgNiAAQarFRaqflo
I+d61SRvU8Za2EurxtW20eZzca7dnNYMYf3boIkDuAUU7FfO7l0/4iGzzvfUinng
o4N+LZfQYcTxmdwlkWOrfzCjtHDix6EznPO/LlxTsV+zfTJ/ijTjeXmjQjBAMB0G
A1UdDgQWBBQ64QmG1M8ZwpZ2dEl23OA1xmNjmjAOBgNVHQ8BAf8EBAMCAQYwDwYD
VR0TAQH/BAUwAwEB/zAKBggqhkjOPQQDAwNoADBlAjA2Z6EWCNzklwBBHU6+4WMB
zzuqQhFkoJ2UOQIReVx7Hfpkue4WQrO/isIJxOzksU0CMQDpKmFHjFJKS04YcPbW
RNZu9YO6bVi9JNlWSOrvxKJGgYhqOkbRqZtNyWHa0V1Xahg=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
SR7420_PUBLIC_ROOTS
log 'downloading pinned r2 launcher from GitHub over authenticated HTTPS'
curl --fail --location --proto '=https' --proto-redir '=https' --cacert "$WORK/ca.pem" \
 --retry 2 --connect-timeout 10 --max-time 300 --max-filesize 8388608 \
 -o "$WORK/launcher.tar.gz.part" "$BASE/sr7420-usb44-launcher.tar.gz"
mv "$WORK/launcher.tar.gz.part" "$WORK/launcher.tar.gz"
# Stock has no SHA tool. The helper is first authenticated by HTTPS, then pinned.
# Extract only that fixed entry before verifying the whole launcher archive.
mkdir "$WORK/launcher"
tar xzf "$WORK/launcher.tar.gz" -C "$WORK/launcher" sha256
HASH=$WORK/launcher/sha256
[ -f "$HASH" ] && [ ! -L "$HASH" ] || die 'invalid hash helper'
chmod 700 "$HASH"
hash_file() { "$HASH" "$1" | awk '{print $1}'; }
[ "$(hash_file "$HASH")" = "$SHA_TOOL_SHA" ] || die 'hash helper checksum mismatch; USB unchanged'
[ "$(hash_file "$WORK/launcher.tar.gz")" = "$LAUNCHER_SHA" ] || die 'launcher checksum mismatch; USB unchanged'
log 'launcher SHA256 verified'
tar tzf "$WORK/launcher.tar.gz" >"$WORK/names"
awk '/^\// || /(^|\/)\.\.(\/|$)/ {bad=1} END {exit bad}' "$WORK/names" || die 'unsafe launcher path'
tar xzf "$WORK/launcher.tar.gz" -C "$WORK/launcher"
SCRIPT=$WORK/launcher/sr7420-usb.sh
[ "$(hash_file "$SCRIPT")" = "$INSTALLER_SHA" ] || die 'installer checksum mismatch; USB unchanged'
while read digest name extra; do
 [ -z "${extra:-}" ] && [ "${#digest}" = 64 ] || die 'invalid launcher manifest'
 case "$digest" in *[!0-9a-f]*) die 'invalid launcher digest';; esac
 case "$name" in /*|*..*|'') die 'unsafe launcher manifest';; esac
 [ "$(hash_file "$WORK/launcher/$name")" = "$digest" ] || die "launcher member checksum mismatch: $name"
done <"$WORK/launcher/launcher.sha256"
log 'all launcher tools verified; no offline system bundle is present'
if [ "$AUTO" = 1 ]; then
 sh "$SCRIPT" detect >"$WORK/detect.log" || { cat "$WORK/detect.log"; die 'USB detection failed'; }
 cat "$WORK/detect.log"
 COUNT=$(grep -c '^SR7420-USB: USB device=' "$WORK/detect.log")
 [ "$COUNT" = 1 ] || die 'exactly one removable USB is required; use explicit device/serial options instead'
 DEV=$(awk '/^SR7420-USB: USB device=/ {sub(/^device=/,"",$3);print $3}' "$WORK/detect.log")
 SERIAL=$(awk '/^SR7420-USB: USB device=/ {sub(/^serial=/,"",$4);print $4}' "$WORK/detect.log")
 case "$DEV" in /dev/sd[a-z]) :;; *) die 'unexpected disk name';; esac
 case "$SERIAL" in ''|*[!A-Za-z0-9_.:-]*) die 'missing/unsafe serial; use explicit options';; esac
 log "explicit single-USB erase mode selected for $DEV; installer will recheck identity and mounts"
 set -- --device "$DEV" --serial "$SERIAL" --erase "$@"
fi
sh "$SCRIPT" "$CMD" "$@"
