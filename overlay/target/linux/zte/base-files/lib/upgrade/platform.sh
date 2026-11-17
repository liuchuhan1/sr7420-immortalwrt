# SPDX-License-Identifier: GPL-2.0-only
platform_check_image() {
 echo 'SR7420 USB development images cannot be installed into factory flash.' >&2
 return 1
}
platform_do_upgrade() { return 1; }
