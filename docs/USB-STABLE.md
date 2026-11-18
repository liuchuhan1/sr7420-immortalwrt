# r2 U 盘稳定模式（实验）

`--stable` 让同一套 U 盘系统在第一次通过外部确认后，后续启动可以由路由器自己检查并确认。它不负责启动 ImmortalWrt，也不改变原厂开机流程。增强启动器目前只做过离线模拟和归档验证，尚未完成真机两次启动及回退验收。

## 给已有 r2 启用稳定模式

核对增强启动器的 SHA256，在**原厂 root shell** 中进入已解开的增强启动器目录。目标应是未挂载的 U 盘，且已有完整、可验证的 r2。仅连接这一块 U 盘，然后执行：

```sh
sh ./sr7420-usb.sh install --stable
```

这条命令不带 `--erase`。如果缺少完整的 r2 或校验失败，它会停止，不会下载重装或格式化。正常完成后仍停在原厂，内核、用户配置和软件源不变。原 r2 发布包和一键在线入口不含此参数，请不要把 `--stable` 追加到旧的一键命令。

## 首次确认和后续启动

1. 在原厂执行 `sh ./sr7420-usb.sh boot`，按[安装说明](INSTALLER.md#3-在-120-秒内完成本次启动确认)检查 DHCP 和 LuCI。在 120 秒内从电脑 SSH 登录 ImmortalWrt，执行 `sr7420-usb-confirm`。
2. 在同一 SSH 会话运行 `sr7420-usb-policy status`。只有出现 `stable=confirmed` 才表示首次确认已写入 U 盘；若显示 `stable=pending-first-external-confirmation`，稍等片刻后再查。
3. 之后仍从原厂手动执行 `boot`。同一 U 盘和同一套策略校验通过，且本机 LAN、管理进程和可写 USB 根分区就绪时，不需要再手动确认。原有回退守护仍会独立复查。若未就绪又没有外部确认，仍尝试回退原厂，并保留 `boot-pending`。

本机检查不能代替电脑端的 DHCP、登录或连通性测试。更换 U 盘或改变所绑定的校验清单和策略后，旧确认不再生效。上次启动失败时按[失败处理](INSTALLER.md#4-失败处理和返回原厂)排查，`--stable` 不会代替手动 `--retry`。

要恢复每次启动手动确认，在已启动的 ImmortalWrt 中运行：

```sh
sr7420-usb-policy disable
sr7420-usb-policy status
```

`--autostart` 不受支持：当前没有已验证的原厂启动入口。本增强版只在 U 盘内安装策略和保存启动状态，不修改原厂启动配置、U-Boot 或固件槽，也不是能上传到原厂升级页的安装包。

## 构建和检查

在电脑上用已发布的 r2 **启动器**归档生成一个新文件；原 `sr7420-usb44-offline.tar.gz` 系统包不用重打：

```sh
python3 tools/extend_r2_launcher.py \
  --r2-launcher /path/to/r2/sr7420-usb44-launcher.tar.gz \
  --output /path/to/sr7420-usb44-r2-stable-launcher.tar.gz

python3 tests/test_usb_stable.py
python3 tests/test_usb_stable_install.py
SR7420_R2_LAUNCHER=/path/to/r2/sr7420-usb44-launcher.tar.gz python3 tests/test_usb_stable_launcher.py
```

这些测试覆盖首次外部确认、后续就绪与失败回退、禁用、已有 r2 的无格式化复用，以及归档完整性。测试用临时文件模拟 U 盘和启动状态，不操作路由器或块设备。
