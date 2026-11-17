# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/image.mk


# Keep image builds compatible with dtc versions without this legacy check.
DTC_FLAGS := $(filter-out -Wno-graph_child_address,$(DTC_FLAGS))

KERNEL_LOADADDR := 0x80200000
KERNEL_ENTRY := 0x80200000

define Device/Default
  PROFILES := Default
  KERNEL_NAME := Image
  KERNEL = kernel-bin | lzma | fit lzma $$(KDIR)/image-$$(firstword $$(DEVICE_DTS)).dtb
  KERNEL_INITRAMFS = kernel-bin | gzip | fit gzip $$(KDIR)/image-$$(firstword $$(DEVICE_DTS)).dtb
  KERNEL_SUFFIX := .itb
  KERNEL_INITRAMFS_SUFFIX := .itb
  DEVICE_DTS_DIR := $(DTS_DIR)/zte
  IMAGES :=
endef

define Device/zte_zxslc-sr7420
  DEVICE_VENDOR := ZTE
  DEVICE_MODEL := ZXSLC SR7420
  DEVICE_VARIANT := USB development, unverified
  DEVICE_DTS := zx279133-sr7420-warmram
  DEVICE_DTS_DIR := $(TOPDIR)/target/linux/zte/dts
  SUPPORTED_DEVICES := zte,zx279133-sr7420
  DEVICE_PACKAGES := \
		kmod-gpio-button-hotplug kmod-zte-npu kmod-zte-rtl8372n \
		kmod-inet-diag kmod-netlink-diag kmod-nft-socket kmod-nf-conntrack-netlink kmod-nft-tproxy kmod-tun librt \
		ethtool ip-full firewall4 nftables-json kmod-nft-offload \
		luci-base luci-mod-admin-full luci-theme-bootstrap \
		luci-proto-ipv6 luci-proto-ppp ppp ppp-mod-pppoe \
		odhcp6c odhcpd-ipv6only uhttpd uhttpd-mod-ubus
  # Enable CONFIG_TARGET_ROOTFS_INITRAMFS for the first kernel boot test.
  # Wired warm-RAM prototype is verified separately; this DTS keeps NPPT off.
  # Cold reset, CPU1, board data and flash-root integration remain open.
  IMAGES :=
endef
TARGET_DEVICES += zte_zxslc-sr7420

$(eval $(call BuildImage))
