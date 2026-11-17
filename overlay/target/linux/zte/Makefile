# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

BOARD:=zte
BOARDNAME:=ZTE SoCs
SUBTARGETS:=zx279133
FEATURES:=dt gpio ramdisk cpiogz squashfs usb
KERNEL_PATCHVER:=6.18

DEVICE_TYPE:=basic

include $(INCLUDE_DIR)/target.mk
include $(TOPDIR)/target/linux/zte/firmware.mk

ifneq ($(DUMP),1)
  ifneq ($(call qstrip,$(CONFIG_EXTERNAL_KERNEL_TREE))$(call qstrip,$(CONFIG_KERNEL_GIT_CLONE_URI)),)
    $(error The ZTE target uses its Linux 6.18 patch series. Clear CONFIG_EXTERNAL_KERNEL_TREE and CONFIG_KERNEL_GIT_CLONE_URI)
  endif
endif

KERNEL_FILE_DEPENDS += $(ZTE_FIRMWARE_DIR)/zx279133-npu.bin

define Kernel/Prepare
	$(call Kernel/Prepare/Default)
	$(INSTALL_DIR) $(LINUX_DIR)/firmware/zte/zx279133
	$(CP) $(ZTE_FIRMWARE_DIR)/zx279133-npu.bin \
		$(LINUX_DIR)/firmware/zte/zx279133/mcode_intel.bin
endef

# Resolve defaults for newly enabled choices before the compile-time syncconfig.
define Kernel/Configure
	$(call Kernel/Configure/Default)
	$(KERNEL_MAKE) olddefconfig
endef

define Target/Description
	Build images for the ZTE ZX279133 SoC family.
endef

$(eval $(call BuildTarget))
