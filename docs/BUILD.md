# 构建与模块

构建需要普通 Linux 用户和足够磁盘空间。不要在路由器上执行构建，也不要使用 `make allmodconfig` 替代 OpenWrt 的软件包依赖求解。

1. 克隆 `upstream.json` 指定的上游，检出 `commit`。
2. 从同一上游获取 `generic_commit`，将该提交的 `target/linux/generic` 检出到这个新建的工作树。保留所有修改记录，勿在有其他工作的树中覆盖目录。
3. 运行本仓库的 `tools/configure.py --topdir /path/to/immortalwrt --backup /path/outside/buildroot/backup`。它只检查固定修订版，覆盖本仓库列出的移植文件，为当前构建产生独立 APK 签名密钥，运行 defconfig，并请求全部 kmod。
4. 运行 `tools/build_runtime.py --topdir /path/to/immortalwrt`，再运行 `tools/build.sh /path/to/immortalwrt 8`。

已在现有构建树完成一次完整构建，并修复新内核的配置选择、符号表收集和外置模块接口差异。最终将目标配置中的 69 项固定内建偏好改为优先 `m`，经 Kconfig 求解后完成 1109 个已选中 kmod 的构建及实际 APK 检查。现有树的成功构建不等于从空目录开始的干净重建已通过；发布状态以 `status.json` 和对应构建报告为准。

## 模块的含义

`CONFIG_PACKAGE_kmod-xxx=y` 表示把模块软件包安装进默认根文件系统；Linux 对应的 `CONFIG_xxx=m` 才表示编译成 `.ko`。其余可用 kmod 请求为 `m`，只生成可安装包，不全部安装/加载到路由器。

编译完成后运行：

```sh
python3 tools/all_kmods.py report --topdir /path/to/immortalwrt --output build/kmod-built.json
```

报告必须同时包含软件包选择、Linux `=m`、`=y`、`modules.builtin`、实际 `.ko` 和 APK 清单。架构限制、依赖缺失或互斥造成未选中的包必须保留在报告中。Kconfig 的布尔功能依赖内建，不能编译成模块；也不会通过强行改为 `y` 来启用其他 SoC 的功能。

## 内建和模块化

`config/module-preferences.json` 记录本次从目标配置中移除的固定内建偏好，以及启动所需的内建例外。Kconfig 如果因其他内建驱动的依赖把某项恢复为 `y`，报告会保留求解结果；不会将它宣称为可单独加载的模块。

USB 最小 initramfs 必须包含 USB 控制器、平台驱动、存储和 ext4 的依赖闭包。新增 DWC3 平台模块时，安装器和根文件系统的模块选择也必须一并修改。

全量 APK 生成后运行：

```sh
python3 tools/audit_modules.py --topdir /path/to/immortalwrt \
  --selection-report build/kmod-built.json --output build/module-audit.json
```

该检查解包实际 APK，核对 `.ko` 的 AArch64 架构、vermagic 和全局模块依赖。它会列出没有 `.ko` 的元包或内建功能包；不能替代实机测试，也不证明每种软件包组合均可安装。

## 同 ABI 软件源

使用 `tools/publish_kmods.py` 从同一次成功构建收集 APK，检查唯一 kernel 依赖，使用该构建的项目密钥签名并生成 `packages.adb`。对应镜像必须安装同一个公钥。不同内核配置/构建的 kmod 不能混用。

私钥只存构建机和私有备份；公钥、软件包索引、SHA256 与 ABI 清单可公开。全量模块构建完成之前不创建假索引、不复用历史少量模块充数。

## 空间整理

`tools/cleanup_build.py` 默认检查，不执行清理。本次历史资料先归档下载，再逐文件验证 1,414 个文件和链接，验证源目录未变后才移除远端副本。工具链、下载缓存和正在构建的目录没有作为垃圾删除。


## 静态 kexec 与 USB 开发包

先从独立、未注入设备数据的 kexec-tools 2.0.28 源码构建静态工具：

```sh
python3 tools/build_kexec.py --source /path/to/kexec-tools-2.0.28 \
  --topdir /path/to/immortalwrt --output /path/to/new-kexec-output --jobs 8
```

输出包含静态 AArch64 `kexec`、对应源码、源码中的构建配方、GPL 许可证及 SHA256 报告。编译和静态链接检查通过不代表已在原厂内核上测试。

`tools/build_usb_bundle.py` 接收同次构建的干净 rootfs，以及该 kexec 输出的二进制、对应源码、许可证、已核对的 SHA256 和 HTTPS 下载地址。它生成：

- `sr7420-usb44-offline.tar.gz`：根系统、内核、设备树模板及磁盘工具；不含个人校准。
- `sr7420-usb44-launcher.tar.gz`：启动脚本、静态 SHA 工具、curl 运行库及 CA；用于离线安装前置环境或首次在线下载。
- `kexec-tools-corresponding-source.tar.gz` 和 `COPYING.kexec`：与发布二进制配套保存。
- `bundle-report.json`：实际大小、哈希、内核 ABI 与验证状态。

两个 USB 包需要配套使用；离线包应放在启动脚本旁边。增强启动器的 `--autostart` 只支持明确核对过配置的原厂 `nativeC` 环境，详见 [单机自启](USB-STABLE.md#单机自启)。不要把这些 tar 包上传到原厂升级页。

## 发布前检查

运行 `privacy_scan.py` 检查源码、展开的 rootfs、bootstrap CPIO 和发布包。扫描 APK 时必须指定构建机的可信 host `apk`，例如 `--apk-tool /path/to/immortalwrt/staging_dir/host/bin/apk`；未解包的 APK 会直接判定不通过。签名验证、模块 ABI 核对与隐私检查均须分别通过。

实际产物的二次验收使用：

```sh
python3 tools/verify_usb_bundle.py /path/to/usb-output \
  --module-audit reports/module-audit-final44.json \
  --repository-key /path/to/feed/keys/public-key.pem \
  --report /path/to/usb-verification.json
```

它核对归档内容和各层 manifest、默认密码、公钥、实际 Image 内嵌 CPIO、USB 模块顺序及静态 AArch64 kexec。它不重启路由器。
