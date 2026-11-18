# ZTE SR7420 ImmortalWrt 开发移植

这是 SR7420 的开发移植、补丁和 USB 系统切换工具源码。目前不提供可直接交给原厂升级页的刷机包。

## 当前状态（2026-11-18）

| 项目 | 状态 |
| --- | --- |
| 原厂 kexec 进入新内核 | r2 USB 系统已实机验证 |
| USB 识别、挂载 ext4 根分区 | r2 已验证，可写 USB 根分区 |
| USB 根系统启动后网口获取地址/管理访问 | r2 DHCP、SSH、LuCI 登录与配置权限已验证 |
| 双无线、hostapd/netifd/LuCI 控制 | r2 两个 radio 启动；客户端连接/吞吐仍待专门测试 |
| 全量 kmod | 1109 个目标可选包全部构建；403 个未选中项另行列出 |
| USB44 r2 在线安装与启动器 | 原厂一行命令在线下载安装、重复复用及新发布归档启动均已实机验证 |
| 双核、交换机独立冷启动 | 未完成 |
| 原厂配置恢复/升级页一次上传安装 | 未验证，不生成伪装的原厂升级包 |
| 原厂持久自启入口 | 尚未验证，自动化部署未完成 |

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

USB44 r2 以实验预发布提供在线安装入口、离线包和启动器。[原厂一行安装命令](docs/INSTALL-R2-ONE-LINE.sh)已经实测：从 GitHub 下载 r2，安装到 U 盘，再启动这份发布归档，通过 DHCP、SSH、LuCI、双 radio 和 r2 软件源检查。命令会清空唯一符合条件的 U 盘；安装后默认留在原厂系统。切换及外部确认方法见 [安装器文档](docs/INSTALLER.md)，验收结果见 [在线安装测试记录](reports/r2/online-install-test-r2.json)。原厂网页一次上传和持久自启仍未完成。
