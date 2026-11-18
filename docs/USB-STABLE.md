# r2 U 盘稳定模式与自启（实验）

`--stable` 让同一套 U 盘系统在第一次通过外部确认后，后续启动可以由路由器自己检查并确认。单独使用它不会改变原厂开机流程。要让路由器自动发起切换，另启用 [`--autostart`](#单机自启)。在一台 SR7420（原厂 Linux `5.4.196`）上已实测稳定模式的首次确认、后续自动确认和 LuCI 未就绪时的回退。

## 给已有 r2 启用稳定模式

核对增强启动器的 SHA256，在**原厂 root shell** 中进入已解开的增强启动器目录。目标应是未挂载的 U 盘，且已有完整、可验证的 r2。仅连接这一块 U 盘，然后执行：

```sh
sh ./sr7420-usb.sh install --stable
```

这条命令不带 `--erase`。如果缺少完整的 r2 或校验失败，它会停止，不会下载重装或格式化。正常完成后仍停在原厂，内核、用户配置和软件源不变。原 r2 发布包和一键在线入口不含此参数，请不要把 `--stable` 追加到旧的一键命令。

## 首次确认和后续启动

1. 在原厂执行 `sh ./sr7420-usb.sh boot`；已启用自启时，由原厂开机流程发起这一步。按[安装说明](INSTALLER.md#3-在-120-秒内完成本次启动确认)检查 DHCP 和 LuCI。在 120 秒内从电脑 SSH 登录 ImmortalWrt，执行 `sr7420-usb-confirm`。
2. 在同一 SSH 会话运行 `sr7420-usb-policy status`。只有出现 `stable=confirmed` 才表示首次确认已写入 U 盘；若显示 `stable=pending-first-external-confirmation`，稍等片刻后再查。
3. 之后无论手动还是自动发起 `boot`，同一 U 盘和同一套策略校验通过，且本机 LAN、管理进程和可写 USB 根分区就绪时，不需要再手动确认。原有回退守护仍会独立复查。若未就绪又没有外部确认，仍尝试回退原厂，并保留 `boot-pending`。

本机检查不能代替电脑端的 DHCP、登录或连通性测试。更换 U 盘或改变所绑定的校验清单和策略后，旧确认不再生效。上次启动失败时按[失败处理](INSTALLER.md#4-失败处理和返回原厂)排查，`--stable` 不会代替手动 `--retry`。

要恢复每次启动手动确认，在已启动的 ImmortalWrt 中运行：

```sh
sr7420-usb-policy disable
sr7420-usb-policy status
```

## 单机自启

此选项针对带有 `nativeC` 容器、共享宿主回环网络且已配置授权 root Telnet 维护登录的 SR7420 原厂固件。它给容器自己的 BusyBox 启动表添加一条开机任务。容器登录宿主 `127.0.0.1:23`，由宿主调用现有 USB 启动器。无需电脑常驻，也不新开端口或修改容器网络。持久配置写入原厂 `/Plugin` 文件系统，不改写宿主只读根、U-Boot 或固件槽。

在原厂 root shell 中，从核对过 SHA256 并解压的增强启动器目录执行：

```sh
sh ./sr7420-usb.sh install --autostart --stable < /path/to/private-telnet-login
```

标准输入依次为现有**原厂 Telnet**用户名、密码，每行一项；不是 ImmortalWrt 的密码。也可以使用参数方式：

```sh
sh ./sr7420-usb.sh install --autostart --stable \
  --tnu root --tnp '原厂Telnet密码'
```

`--tnu` 与 `--tnp` 必须同时提供，并且只用于 `install --autostart`。两种方式最终使用同一个自启安装、凭据校验和回环登录探测流程。参数方式不会读取标准输入；不要把两种方式混用。安装仅复用已验证的 r2 U 盘，不格式化或下载系统包，也不立即切换。原厂下一次启动时自动尝试一次。如果已有同一 U 盘和策略的 `stable=confirmed`，不会要求重新确认；未确认时仍按上节做一次 SSH 确认。未加 `--stable` 且此前也未启用它时，每次切换仍需外部确认。

自启绑定安装时的 U 盘序列号与校验清单。宿主最多等待约 150 秒，直到绑定的 U 盘和两个分区出现；出现后只验证并尝试切换一次。U 盘缺失、接错盘、接入多块可移除 U 盘、清单变更或上次留下 `boot-pending` 时，留在原厂，不自动 `--retry`。排查修复后由管理员手动决定是否重试。

**凭据风险：** 原厂密码以明文保存在容器的 root 私有文件（`0600`）。获得容器 root 的人可以读取该密码；回环连接不等于加密，也不改变原厂 Telnet 的 LAN/WAN 暴露范围。标准输入文件方式不会把密码放进 shell 参数；`--tnp` 参数方式会让密码出现在 shell history、进程参数或终端审计记录中，只适合临时维护，不要用于公开脚本。无论哪种方式，都不要把凭据放入日志或发布包。若不用自启，请在原厂执行 `sh ./sr7420-usb.sh disable-autostart`；也可用设备上已保存的 `sh /Plugin/sr7420-usb-autostart/manage.sh disable`。这会撤销容器启动项并删除保存的登录文件，不改变 U 盘的稳定确认。要在自启启用时进入原厂维护，可先正常关机，再拔 U 盘后启动；不要热拔运行中的 USB 根分区。

## 稳定模式真机结果

| 场景 | 结果 |
| --- | --- |
| 在原厂给已有 r2 安装策略 | 复用原系统，未重装或格式化 |
| 第一次启动 | 电脑 DHCP、SSH、LuCI 登录正常；守护接受外部确认后才写入 `stable=confirmed` |
| 第二次启动 | 未发送 SSH 确认命令；本机就绪检查和守护复查均通过 |
| 暂停 LuCI 启动后再启动 | DHCP 和 SSH 可用，但没有自动确认；守护超时回到原厂，未确认状态保留，启动器拒绝普通 `boot`；测试后恢复了 LuCI 启动项 |
| 用修订版 `boot --retry` 恢复 | 自动确认通过；同一次启动在 195 秒时仍在线，两路无线均已启动 |

首次交接尝试未进入 r2，原厂侧回退命令依赖的接口在本机不存在，需用原厂重启命令恢复。修订版改用独立的 `sync` 和原厂 `/sbin/reboot`，并在交接前预检所需工具。修订版正常交接已实测，但没有在真机上触发新版原厂守护的超时分支；上表中的故障回退发生在 r2 已启动之后。软件回退不保证能处理内核或总线完全卡死。详见[真机验收记录](../reports/r2/usb-stable-hardware-test.json)。

## 单机自启真机结果

在同一台 SR7420 上，复用已经通过首次 SSH 确认的 r2 U 盘，验证了 `--autostart --stable`：

| 场景 | 结果 |
| --- | --- |
| 原厂正常重启 | 路由器自行切换到 r2；约 209 秒后电脑取得 DHCP 租约，SSH、LuCI 和可写 ext4 根分区正常。电脑未发送 `boot` 或确认命令；新的 boot ID 有 `STABLE_LOCAL_READY` 和守护接受回执，没有 `EXTERNAL_CONFIRM`。同一次启动在 234 秒时仍在线。 |
| LuCI 启动链接暂移 | 路由器仍自行切换到 r2，但无法确认就绪；守护超时后回到原厂，留下 `boot-pending`。下一次自启拒绝切换，没有加载 r2 内核。测试后恢复了 LuCI 启动链接。 |
| `disable-autostart` | 原厂 `nativeC` 容器的启动表恢复原样，容器保存的登录文件和宿主上的自启配置被删除；U 盘的稳定确认和启动标记未改变。 |
| 重新启用后手动 `boot --retry` | 启用时保留了 `boot-pending`；修复后显式重试，r2 再次自动确认并清除该标记。启动后 207 秒复查，DHCP、SSH、LuCI 和两个 radio 均正常。 |

早期版本因在 U 盘枚举前只检查一次而留在原厂，没有写入待回退标记；修订版加入了限时等待。归档 SHA256 和详细结果见[自启验收报告](../reports/r2/usb-autostart-hardware-test.json)。

这里验证的是软件重启后的自启，**没有断电再上电的实测记录**。切换一直由原厂先完成硬件初始化，再通过 kexec 进入 r2，并不是跳过原厂的独立冷启动。

## 构建和检查

在电脑上用已发布的 r2 **启动器**归档生成一个新文件；原 `sr7420-usb44-offline.tar.gz` 系统包不用重打：

```sh
python3 tools/extend_r2_launcher.py \
  --r2-launcher /path/to/r2/sr7420-usb44-launcher.tar.gz \
  --output /path/to/sr7420-usb44-r2-stable-launcher.tar.gz

SR7420_R2_LAUNCHER=/path/to/r2/sr7420-usb44-launcher.tar.gz \
  python3 -m unittest discover -s tests -p 'test_usb_stable*.py' -v
```

这些测试覆盖首次外部确认、后续自动确认和失败回退、已有 r2 的无格式化复用、自启的介质校验和限时等待、撤销与登录文件清理，以及归档完整性。测试用临时文件模拟 U 盘和启动状态，不操作路由器或块设备。
