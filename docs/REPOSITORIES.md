# r1 / r2 软件源

r1 保留在 `sr7420-kmods`；当前 r2 使用独立的 `sr7420-kmods-r2`。旧包及签名索引没有删除、替换或重签，只修正了旧文档的 ABI 拼写。

| 系统代际 | 完整 kernel ABI | 仓库 |
| --- | --- | --- |
| r1 | `6.18.60~b608e4c72ecf314fc3955d48ca497c9f-r1` | `sr7420-kmods` |
| r2 | `6.18.60~2b497291254683b6ce56b38338fafb7e-r1` | `sr7420-kmods-r2` |

代际 r2 与 APK 版本修订后缀 `-r1` 无关，不应手工修改内核依赖。两个仓库各有 1109 个 kmod 和 1 个 kernel APK，并使用与相应系统匹配的签名公钥。

## 默认配置与复现

r2 源的完整地址保存在 `config/sr7420-r2.list`，安装包中的配置路径为 `/etc/apk/repositories.d/sr7420.list`。重新打包时给 `tools/build_usb_bundle.py` 传入 `--kmod-index-url "$(cat config/sr7420-r2.list)"`。自定义内核或公钥后必须发布自己的配套仓库，不能继续套用这里的固定 ABI。

apk 3.0.5 实测请求的索引是 `packages.adb`，无需创建 `package.db`。配置文件使用 LF 换行，避免 CR 字符被当作 URL 的一部分。公钥放在 `/etc/apk/keys/`，保持签名校验开启。

## 本次验证

- 匿名下载两版索引、公钥和样本 APK，字节/哈希与本地产物一致。
- 在真实路由器上验证两版索引签名。
- r1 使用隔离 APK 根目录更新，成功读取 1110 个包。
- 当前 r2 系统运行 `apk update` 返回 0，共可见 11468 个去重软件包。
- 下载并验证 `kmod-inet-diag`、`kmod-netlink-diag`、`kmod-nf-conntrack-netlink`、`kmod-nft-tproxy`、`kmod-nft-socket`、`kmod-tun`，同时通过依赖安装模拟；没有升级运行系统。

证据见 `reports/r2/router-repository-test-r2.json` 和两个模块仓库的 `reports/index-verification.json`。这些检查不代表所有模块的硬件功能都已经测试。
