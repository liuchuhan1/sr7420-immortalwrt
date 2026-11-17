# 移植注意事项

- 仍依赖原厂初始化后的 warm handover，不是独立冷启动支持；U-Boot 不修改。
- PCIe1 的无线为 2.4 GHz，PCIe0 为 5 GHz；两个设备的 BDF/cal 和 variant 必须分开。
- WSI 配对会使 netifd 的两个 radio 使用同一 wiphy 路径，靠 `radio` 与 `band` 区分。不要仅因为 UCI path 一样就强行改成两个 PCI 路径。
- 原厂 vendor ABI 适配位于 ath12k 下行命令/上行事件与上层之间；控制面仍使用 mac80211/nl80211、hostapd、netifd 和 LuCI。
- 64 位 survey 需要资源位、请求/事件编解码和 survey 更新一起工作，不能只打开一位能力标记。
- 启动服务保留已测试的资源/WSI/INI/内存模式参数，但默认关闭原始 payload 十六进制调试转储。
- 新默认配置不包含 SR1010 灯控服务、旧软件源豁免和错误机型展示。共享内核代码中的 SR1010 兼容字符串、Kconfig 名与历史补丁名属于现有 ABI/共享来源标识，保留以避免无关破坏。
- 全量 kmod 的可编译性不能证明 SR7420 有对应硬件，也不代表所有硬件加速路径已实测。

最近一次 USB43 的证据仅能确认：新内核进入、USB 探测、ext4 根分区挂载和后续软件 guard 重启。网口未恢复，所以不会把“挂载根分区”标成“USB 系统完整启动成功”。
