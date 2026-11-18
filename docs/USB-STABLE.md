# r2 U 盘稳定模式（实验）

`--stable` 让同一套 U 盘系统在第一次通过外部确认后，后续启动可以由路由器自己检查并确认。它不负责启动 ImmortalWrt，也不改变原厂开机流程。在一台 SR7420（原厂 Linux `5.4.196`）上已实测首次确认、后续自动确认和 LuCI 未就绪时的回退。

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

`--autostart` 仍不受支持：当前没有已验证、可由原厂主系统调用的启动入口。增强版只在 U 盘内安装策略和保存启动状态，不修改原厂启动配置、U-Boot 或固件槽，也不是能上传到原厂升级页的安装包。自动确认和原厂开机自动切换是两项不同的功能。

### 真机结果

| 场景 | 结果 |
| --- | --- |
| 在原厂给已有 r2 安装策略 | 复用原系统，未重装或格式化 |
| 第一次启动 | 电脑 DHCP、SSH、LuCI 登录正常；守护接受外部确认后才写入 `stable=confirmed` |
| 第二次启动 | 未发送 SSH 确认命令；本机就绪检查和守护复查均通过 |
| 暂停 LuCI 启动后再启动 | DHCP 和 SSH 可用，但没有自动确认；守护超时回到原厂，未确认状态保留，启动器拒绝普通 `boot`；测试后恢复了 LuCI 启动项 |
| 用修订版 `boot --retry` 恢复 | 自动确认通过；同一次启动在 195 秒时仍在线，两路无线均已启动 |

首次交接尝试未进入 r2，原厂侧回退命令依赖的接口在本机不存在，需用原厂重启命令恢复。修订版改用独立的 `sync` 和原厂 `/sbin/reboot`，并在交接前预检所需工具。修订版正常交接已实测，但没有在真机上触发新版原厂守护的超时分支；上表中的故障回退发生在 r2 已启动之后。软件回退不保证能处理内核或总线完全卡死。详见[真机验收记录](../reports/r2/usb-stable-hardware-test.json)。

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
