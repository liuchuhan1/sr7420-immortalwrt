# 构建与模块

构建需要普通 Linux 用户和足够磁盘空间。不要在路由器上执行构建，也不要使用 `make allmodconfig` 替代 OpenWrt 的软件包依赖求解。

1. 克隆 `upstream.json` 指定的上游，检出 `commit`。
2. 从同一上游获取 `generic_commit`，将该提交的 `target/linux/generic` 检出到这个新建的工作树。保留所有修改记录，勿在有其他工作的树中覆盖目录。
3. 运行本仓库的 `tools/configure.py --topdir /path/to/immortalwrt --backup /path/outside/buildroot/backup`。它只检查固定修订版，覆盖本仓库列出的移植文件，为当前构建产生独立 APK 签名密钥，运行 defconfig，并请求全部 kmod。
4. 运行 `tools/build_runtime.py --topdir /path/to/immortalwrt`，再运行 `tools/build.sh /path/to/immortalwrt 4`。

本次实际全量构建中发现 SCTP 新选择项导致 syncconfig 请求交互。维护者正在将最终配置差异固化到构建入口；完整干净重建尚未验收，不能把上述步骤视为已通过的 CI 配方。

## 模块的含义

`CONFIG_PACKAGE_kmod-xxx=y` 表示把模块软件包安装进默认根文件系统；Linux 对应的 `CONFIG_xxx=m` 才表示编译成 `.ko`。其余可用 kmod 请求为 `m`，只生成可安装包，不全部安装/加载到路由器。

编译完成后运行：

```sh
python3 tools/all_kmods.py report --topdir /path/to/immortalwrt --output build/kmod-built.json
```

报告必须同时包含软件包选择、Linux `=m`、`=y`、`modules.builtin`、实际 `.ko` 和 APK 清单。架构限制、依赖缺失或互斥造成未选中的包必须保留在报告中。Kconfig 的布尔功能依赖内建，不能编译成模块；也不会通过强行改为 `y` 来启用其他 SoC 的功能。

## 同 ABI 软件源

使用 `tools/publish_kmods.py` 从同一次成功构建收集 APK，检查唯一 kernel 依赖，使用该构建的项目密钥签名并生成 `packages.adb`。对应镜像必须安装同一个公钥。不同内核配置/构建的 kmod 不能混用。

私钥只存构建机和私有备份；公钥、软件包索引、SHA256 与 ABI 清单可公开。全量模块构建完成之前不创建假索引、不复用历史少量模块充数。

## 空间整理

`tools/cleanup_build.py` 默认检查，不执行清理。本次历史资料先归档下载，再逐文件验证 1,414 个文件和链接，验证源目录未变后才移除远端副本。工具链、下载缓存和正在构建的目录没有作为垃圾删除。
