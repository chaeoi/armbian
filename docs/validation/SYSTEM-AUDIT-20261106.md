# EC6108V9 Armbian 实机系统审计 · 2026-11-06

> 历史实测记录。以下工作目录路径相对于当时的项目根目录；原始日志、镜像和设备配置未纳入公开仓库。当前入口见 [测试索引](../VALIDATION.md)。

**本轮可执行的实机复测已完成，发现的问题已修复；已测范围内没有失败服务、数据校验错误或启动失败。** 当前仅枚举到一块 USB 存储，第二 USB 口未完成本轮插盘读写测试；HDMI 按要求暂缓。已知功能限制列在下方，不能据此宣称整个系统绝无 bug。

本报告的全面审计基线为 Armbian 26.8.3 / Ubuntu 22.04.5 最小用户空间、内核 `7.3.0-rc7-ec6108v9-r4`。r4 连续两次正常启动，最后启动 ID 为 `5d6f5f9f-8850-4a05-815f-0cb8d7423eac`。本轮通过网线直连 SSH 实际执行测试，无需用户拔插或手动重启。

**后续 SD 专项已将当前运行内核更新为 r6。** 恢复 SD 的 4-bit / 25 MHz，修复 MMC 大块读取的软件超时计算，并补齐原驱动未实现的错误统计。最终 r6 的写入加同步约 9.58～10.47 MiB/s，清缓存读取约 11.4 MiB/s；随机逐笔同步、跨重启持久化、自动挂载、中文文件名、控制器重新识别及有线/无线到 SD 的实际传输均通过。当前路径为 `/mnt/sdcard`，无失败服务、MMC CRC/超时计数为零。详细证据及 r6 复测范围见 [SD 专项报告](SD-INVESTIGATION-20261106.md)；下表中的 r4 用例保持为当时的实测记录。

## 发现并修复的问题

1. **四核定时器精度错误。** 原配置用共享 SP804 时钟事件，四核退回 dummy timer，1 毫秒休眠中位数约 9.97 毫秒。依据 MV100 SDK 的寄存器及中断映射实现四核独立定时器，现在四核中位数均约 **1.08 毫秒**；CPU 1、2、3 逐个下线、上线后仍正常。
2. **无线启动和故障恢复。** 修正 `rtl8xxxun` 模块名；将过早执行的省电命令改为设备就绪后执行；用 `BindsTo` 在旧接口消失时停止旧 supplicant。完整无线核心重载还会改变 `nl80211` 编号，旧版 networkd 缓存失效；现仅在编号变化时刷新网络服务，并恢复失败的链路配置。两轮重连、完整模块卸载/加载、自动获取 IP、重载后再次重连均通过。
3. **防火墙和 NAT 实际未编入。** 虽然原目标配置要求 NAT，但缺少连接跟踪和协议族依赖，被 Kconfig 静默取消；实机创建 IPv4 防火墙表返回“不支持”。已补齐依赖、nftables 与旧版 iptables 模块，并增加构建前配置检查。隔离网络中的真实桥接、连接跟踪和 NAT 流量已通过验证。
4. **硬件随机数误报。** 正数短读已经返回有效数据，却仍打印错误。现接受合法短读，保留零字节超时的限速错误提示，未改变熵源及后处理强度。实际读取 `/dev/hwrng` 1024 字节，基本校验通过，内核熵池 256。
5. **开机配置兼容问题。** DHCP 不再覆盖固定主机名；日志套接字适配当前内核支持的选项；修复日志目录遗留软链接及启动确认服务权限。
6. **U 盘卷标元数据不一致。** 启动扇区为 `DISK_IMG`，根目录缺少对应标签。先备份覆盖相关扇区的 4 MiB 元数据，再统一为原卷标；读写、跨重启校验和最终 `fsck.fat -n` 均通过。

无线缓存处理依据：[systemd v249 的实现](https://github.com/systemd/systemd/blob/v249/src/libsystemd/sd-netlink/generic-netlink.c)。实测编号 `29 → 30` 时自动刷新成功；完整无线核心重载会使有线 DHCP 短暂重新获取地址，IPv6 管理连接实测保持正常。

## 实际测试结果

| 项目 | 结果与范围 |
| --- | --- |
| 启动与管理 | r4 连续两次正常启动；SSH、原内核/候选内核摘要、启动环境 CRC、自动确认及下次启动配置通过 |
| CPU 与定时器 | 四核在线、各自收到定时器中断；CPU 1/2/3 下线再上线通过；1 毫秒休眠中位数约 1.08 毫秒 |
| 内存 | `memtester` 64 MiB、完整一轮全部通过 |
| 压力 | 4 个 CPU worker + 1 个 128 MiB VM worker，开启校验，持续 120 秒通过 |
| 系统根文件系统 | 暂停写入期间复制一致的元数据快照，在独立 RAM 文件上执行 `e2fsck -fn`，五项检查通过，退出码 0 |
| eMMC 上的系统盘 | r4 写入并同步 32 MiB 随机文件，清缓存读回及普通重启后 SHA-256 一致，测试文件已删除 |
| 当前 U 盘 | 头/中/尾各 4 MiB 重复直接读取一致；r4 的 8 MiB 临时文件跨挂载及跨重启校验通过；最终 FAT 检查通过 |
| 新 SD 卡 | ACLCE 64 GB / 59.5 GiB、exFAT；头/中/尾重复直接读取一致；r4 的 4 MiB 临时文件跨挂载及跨重启校验通过。此前另有 16 MiB 跨重启验证通过；最终检查干净，原 4 个目录、912 个文件保留 |
| 有线网络 | r4 的 4 MiB 双向传输 SHA-256 一致；网关 ping 无丢包 |
| Wi-Fi | 自动连接、普通重连、完整无线模块重载及后续再次重连通过；r4 的 4 MiB 双向传输 SHA-256 一致；省电保持关闭 |
| 网络基础 | IPv6 回环、IPv6 链路本地 SSH、DNS、外网 HTTPS、NTP 通过；最终重启后从 wlan0 经公网 IPv6 访问 HTTPS 返回 200 |
| 桥接/连接跟踪/NAT | 三个隔离网络命名空间构成真实桥接和路由；无 NAT 时连接失败，启用后双向各 4 MiB 校验通过，服务端确认源地址已转换。连接跟踪规则累计处理约 8.4 MB；临时命名空间已删除，主系统防火墙未改变 |
| 通用内核功能 | veth、bridge、网络/PID/挂载命名空间、overlay 写时复制、cgroup 限额配置与子进程运行通过；r4 的 nftables、iptables、NAT 等所选模块全部加载通过 |
| 模块完整性 | 安装后的 41 个 `.ko` 文件与构建清单 SHA-256 全部一致 |
| 服务与精简状态 | 无失败服务；SSH 配置、软件包依赖、日志写入检查通过；8 个临时测试包及新增依赖已全部清理，无测试服务器或网络命名空间残留 |

内存和压力测试在修复定时器后的 r3 完成；r4 的改动为网络过滤依赖，另完成了 r4 的基础功能、模块、真实收发、NAT、存储及两次启动复测。测试范围是上述具体用例，未做长时间老化或整盘全容量写入。

最后一轮 r4 写入与同步实测：系统盘 32 MiB 约 7.69 秒，SD 卡 4 MiB 约 19.99 秒，U 盘 8 MiB 约 1.27 秒。SD 当时同步耗时有明显波动，数据持久化校验均通过；此项性能问题已继续调查并修复，当前 r6 结果见顶部专项报告。

清理后的空闲观测约使用 58 MiB 内存。根镜像可用约 985 MiB，承载镜像的原分区普通可用约 731 MiB；写入空间需同时考虑两层文件系统的剩余空间。

## 仍有的限制

- 内核基线为 Hi3798MV100 社区 `7.3.0-rc7`，属于社区移植，非 Armbian 官方支持或 LTS 内核。当前测试不能代替长期稳定性验证。
- eMMC 仍使用 1-bit / 50 MHz，性能受限；SD 已恢复 4-bit / 25 MHz，专项测试未再现此前长停顿。未做全容量写入或长期老化。
- 本轮部分启动出现单次 RX IQK 校准告警，驱动重试后的连接、重连、收发校验通过；保留告警，未将校准问题声称为彻底解决。
- 温度监测和 CPU 动态调频接口尚未提供；仍有设备树 CPU 频率属性缺失提示。硬件 RTC 不可用，启动早期日志可能显示镜像时期的日期，NTP 后时间正常。
- 第二 USB 口本轮没有检测到存储设备，无法确认其当前插入状态，不能记作本轮插盘测试通过。11 月 2 日两个口均有读取验证记录。本轮读取了各根集线器端口状态，当前只检测到已枚举 U 盘及内置 Wi-Fi 的连接。
- HDMI、GPU、视频解码、音频当前未启用；HDMI 按用户要求暂缓。
- 升级模拟显示 70 个用户空间包可更新。本次测试对应以上固定版本。

## 证据与构建

- r4 最终状态（本地记录：`artifacts/system-audit-20261106/final-state.json`）、最终重启检查（本地记录：`artifacts/system-audit-20261106/post-reboot-final-checks.txt`）、r4 基础功能（本地记录：`artifacts/system-audit-20261106/functional-r4.log`）
- 定时器修复前（本地记录：`artifacts/system-audit-20261106/timer-before.json`）、修复及 CPU 上线后（本地记录：`artifacts/system-audit-20261106/timer-final.json`）、CPU 上下线（本地记录：`artifacts/system-audit-20261106/cpu-hotplug.log`）
- 内存（本地记录：`artifacts/system-audit-20261106/memtester-clean.log`）、压力（本地记录：`artifacts/system-audit-20261106/stress.log`）、根文件系统快照检查（本地记录：`artifacts/system-audit-20261106/rootfs-metadata.json`）
- r4 存储跨重启结果（本地记录：`artifacts/system-audit-20261106/storage-r4-reboot.json`）、最终 FAT/exFAT 检查（本地记录：`artifacts/system-audit-20261106/media-final-filesystem-check.txt`）、USB 端口状态（本地记录：`artifacts/system-audit-20261106/usb-port-status.json`）
- 无线完整重载（本地记录：`artifacts/system-audit-20261106/wifi-recovery-final.log`）、重载后再次重连（本地记录：`artifacts/system-audit-20261106/wifi-post-reload-reconnect.log`）、编号刷新证据（本地记录：`artifacts/system-audit-20261106/wifi-family-refresh-proof.txt`）、r4 有线/无线收发（本地记录：`artifacts/system-audit-20261106/network-r4.json`）
- 旧内核防火墙不支持的实测（本地记录：`artifacts/system-audit-20261106/nat-before-unsupported.txt`）、r4 真实桥接/NAT 验证（本地记录：`artifacts/system-audit-20261106/nat-r4.json`）、41 个模块完整性（本地记录：`artifacts/system-audit-20261106/modules-r4-integrity.json`）

r4 历史镜像：5,786,863 字节，SHA-256 `767ef42bd8d8427a499e7916f0a837d9b223b7f452d12cdac63b13ca301fa6eb`，保存在 `output/verified-working-20261106/`。

当前 r6 镜像 `output/uImage-ec6108v9`：5,787,087 字节，SHA-256 `1f9598b747b20d0fb9483c63ec497fe80b1b6bb7fcb29da210f5e66720eaf4ee`，已验证构建保存在 `output/verified-working-20261106-r6/`。

源码补丁在 `patches/`，配置在 `targets/`；兼容性修复由 `tools/fix-system-config.py` 与同目录的 `wifi-refresh-networkd.py` 提供，SD 自动挂载由 `tools/configure-sd-automount.py` 配置。原海 NAS 内核、根系统和各轮回退文件保留。
