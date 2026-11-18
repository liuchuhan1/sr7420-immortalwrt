# ZTE SR7420 ImmortalWrt 开发移植

这是 SR7420 的开发移植、补丁和 USB 系统切换工具源码。目前不提供可直接交给原厂升级页的刷机包。

[下载 USB44 r2 实验预发布](https://github.com/liuchuhan1/sr7420-immortalwrt/releases/tag/usb44-r2-20261118) · [下载 stable/autostart 增强版](https://github.com/liuchuhan1/sr7420-immortalwrt/releases/tag/usb44-r2-stable-autostart-20261119) · [一行安装命令](docs/INSTALL-R2-ONE-LINE.sh) · [完整安装说明](docs/INSTALLER.md) · [r2 模块软件源](docs/REPOSITORIES.md)

## 快速开始：从原厂启动 U 盘系统

当前方案是在原厂完成硬件初始化后，通过 kexec 启动 U 盘中的 ImmortalWrt，使用可写 ext4 根分区；这不是在 LXC 容器里运行 ImmortalWrt。需要已获授权的原厂 root shell，仅验证过原厂 Linux `5.4.196`。网页上传安装仍未完成。

1. 备份 U 盘数据，只接入一块准备安装的 U 盘。在 [一行安装命令](docs/INSTALL-R2-ONE-LINE.sh) 中复制最后一整行，在原厂 root shell 执行。命令会从 GitHub 下载固定 r2 发行包并校验，**需要安装时会清空唯一符合条件的 U 盘**；已有完整、校验通过的同版系统会复用。
2. 安装结束仍停留在原厂系统。准备好承受网络中断后，复制 [一行启动命令](docs/BOOT-R2-ONE-LINE.sh) 的最后一整行，在原厂 root shell 执行，切换到已安装的 U 盘系统。
3. 电脑网口使用 DHCP 获取 `192.168.77.x` 地址。打开 LuCI `http://192.168.77.1`，用 `root` / `password` 登录，并检查网络配置页面能正常访问。
4. 在 **120 秒回退窗口内**，从电脑 SSH 登录本次启动的新系统，确认根分区可写后执行确认命令：

   ```sh
   ssh root@192.168.77.1
   # 登录后执行；SSH 密码为 password
   test -w / && mount | grep ' on / '
   sr7420-usb-confirm
   ```

原版 r2 每次 U 盘启动都需要新的外部确认。只打开 LuCI、只等本机服务就绪，均不会取消回退倒计时。完整操作、离线安装、失败处理和返回原厂的方法见 [安装说明](docs/INSTALLER.md)。

开发分支提供独立的 [增强启动器](docs/USB-STABLE.md)。`--stable` 在首次 SSH 确认后启用后续自动确认；[`--autostart`](docs/USB-STABLE.md#单机自启) 负责从原厂开机后发起切换。原版一键入口不含这两个选项。

## 当前状态（2026-11-19）

| 项目 | 状态 |
| --- | --- |
| 原厂 kexec 进入新内核 | r2 USB 系统已实机验证 |
| USB 识别、挂载 ext4 根分区 | r2 已验证，可写 USB 根分区 |
| USB 根系统启动后网口获取地址/管理访问 | r2 DHCP、SSH、LuCI 登录与配置权限已验证 |
| 双无线、hostapd/netifd/LuCI 控制 | r2 两个 radio 启动；客户端连接/吞吐仍待专门测试 |
| 全量 kmod | 1109 个目标可选包全部构建；403 个未选中项另行列出 |
| USB44 r2 在线安装与启动器 | 原厂一行命令在线下载安装、重复复用及新发布归档启动均已实机验证 |
| `--stable` | 首次 SSH 确认、后续自动确认及故障回退已在一台设备上验证 |
| 双核、交换机独立冷启动 | 未完成 |
| 原厂配置恢复/升级页一次上传安装 | 未验证，不生成伪装的原厂升级包 |
| `--autostart` | 单台 SR7420 已验证软件重启后自行切换到 r2；断电上电未实测 |

源码固定 Linux **6.18.60**、无线 backports **6.18.26**。保留已经验证的 warm handover 与双无线 vendor ABI 适配。`nosmp` 仍是启动条件，不宣称双核支持。

## 公开版默认设置

- 用户名 `root`，密码 `password`。
- 主机名 `ImmortalWrt`；LAN 管理地址 `192.168.77.1`，LAN1–3 为 LAN，LAN4 为 WAN。
- 两个无线网络默认开启，SSID 都是 `immortalwrt`，不设密码。
- 默认使用已测试过的 2.4 GHz HE20、5 GHz HE80 设置。
- SSH 管理服务限 LAN；软件包签名校验保留。

这些是公开、统一的默认值。设备自己的 MAC、校准和板级数据由安装器在本机读取，不能随公共镜像分发。

## 内容

- `overlay/`：针对固定上游版本的目标、内核、无线及 firewall4 源文件/补丁。
- `files/`：脱敏后的根文件系统默认配置和正常启动服务。
- `source/ath12k/`：vendor ABI bridge 的最终源文件，用于核对补丁结果。
- `config/`：发行配置、内核片段、需要移除的旧板级文件。
- `installer/`：USB 安装/切换源码模板和辅助 C 程序。
- `tools/`：配置、模块选择/报告、隐私检查、签名软件源和空间整理工具。
- `tests/`：用合成数据测试 SHA、TLV、校准映射、DTB MAC 替换和脚本语法。

参考 [构建说明](docs/BUILD.md)、[安装器状态与设计](docs/INSTALLER.md)、[隐私处理](docs/PRIVACY.md)、[兼容性说明](docs/PORT.md)。

同次内核构建的软件包发布在独立的 `sr7420-kmods-r2` 仓库：1109 个 kmod APK、1 个 kernel APK 和签名 `packages.adb`。精确内核 ABI 为 `6.18.60~2b497291254683b6ce56b38338fafb7e-r1`。原 `sr7420-kmods` r1 仓库及其软件包保留。`r2` 是系统/仓库代际，不改变 APK 版本尾部的 `-r1`。模块说明见 [模块报告](docs/KMODS.md)，软件源与验证结果见 [仓库说明](docs/REPOSITORIES.md)。

## r2 在线安装实测

2026-11-18 在真机上完成了 GitHub 在线安装、重复执行复用、独立校验，以及随后启动新安装系统的测试：

- 首次下载安装约 61.78 秒；重复复用约 14.66 秒，不再下载系统包或格式化。每次调用仍会下载并校验小型 launcher。
- 下载 404、系统包 SHA256 不符、目标分区已挂载，均在擦盘前停止，三项测试前后启动分区 SHA256 不变。
- 新系统通过可写 ext4 根分区、外部 DHCP、SSH、LuCI 登录及配置写权限、两个 radio 启动和默认无线设置检查。
- `apk update` 成功，实测可见 11468 个不同软件包；此前缺少的六个 kmod 已可用。不是所有模块都适用于本机硬件。

安装、复用、校验和启动是分次验收的；组合 `install ... --boot` 没有另做一次完整重装测试。详细记录见 [在线安装测试报告](reports/r2/online-install-test-r2.json)。双核、交换机独立冷启动、无线客户端吞吐和硬件加速不属于已完成结论。
