> 历史移植与试启动记录。当前设备已改为三分区单 Armbian；下面的旧布局和回退命令不对应当前安装。

> 历史实测记录。以下工作目录路径相对于当时的项目根目录；原始日志、镜像和设备配置未纳入公开仓库。当前入口见 [测试索引](../VALIDATION.md)。

# Huawei EC6108V9 Armbian 移植

本目录是针对网线直连实机进行的移植。目标是 **Armbian 用户空间 + Hi3798MV100 社区新内核**。这不是 Armbian 官方支持的主板镜像，不能直接使用其他主板的刷机工具。

## 2026-11-07 换回旧卡后的对照

用户换回的旧卡在海 NAS 和 Armbian r6 下都无法完成初始化，四档低速及 SD 控制器重置后仍失败，没有生成可格式化的块设备。随后换回 ACLCE 64 GB，同一内核和卡槽立即正常识别，3 × 32 MiB 写入、同步、清缓存读回，以及普通重启后的 32 MiB 校验全部通过；最终文件系统干净，`/mnt/sdcard` 可读写、错误计数为零。对照结果更指向旧卡本身或触点问题；本轮没有格式化任何卡。详见 [换卡对照报告](../validation/SD-OLD-CARD-20261107.md)。

## 2026-11-06 SD 修复与当前版本

当前运行 `7.3.0-rc7-ec6108v9-r6`。针对 SD 的后续调查已恢复 **4-bit / 25 MHz**，修正 MMC 大块读取的软件超时计算，并补齐原驱动缺失的真实 CRC/超时统计。当前 ACLCE 64 GB exFAT 卡按 UUID 自动挂载到 **`/mnt/sdcard`**。

- 4-bit 长测试累计 768 MiB 写入及 768 MiB 清缓存读回，全部 SHA-256 一致；最终 r6 的 4 × 64 MiB 写入加同步为 9.58～10.47 MiB/s，读取约 11.4 MiB/s。
- 128 次随机 4 KiB 更新，每次同步，中位 1.83 毫秒，最慢 9.11 毫秒；卸载、清缓存读回一致。
- r5 的 16/64 MiB 与最终 r6 的 64/1 MiB 测试文件均通过普通重启后的校验，随后删除。
- SD 未再出现之前的长停顿，新增真实错误计数为零；eMMC 原有大块读取误超时也已消除。卡未格式化。

修复说明、前后对照及日志见 [SD 专项报告](../validation/SD-INVESTIGATION-20261106.md)。当前镜像 SHA-256 为 `1f9598b747b20d0fb9483c63ec497fe80b1b6bb7fcb29da210f5e66720eaf4ee`，已验证构建保存在 `output/verified-working-20261106-r6/`。r4 的全面系统审计及范围见 [系统审计报告](../validation/SYSTEM-AUDIT-20261106.md)，r6 在其基础上增加 MMC 修复及专项复测；不能将 r4 的所有测试记为 r6 重新执行。

## 2026-11-06 系统基础审计

已修复四核定时器、Wi-Fi 启动及完整重载恢复、NAT 内核配置依赖、随机数误报与开机配置兼容问题，并修复 U 盘卷标元数据。r4 两次正常启动，有线/无线实际收发、桥接/连接跟踪/NAT、系统盘/U 盘/SD 卡跨重启数据校验通过。临时测试包已清理。

本轮只枚举到一块 USB 存储，第二口未完成本轮插盘实测。温度/调频接口尚未提供，HDMI 等显示功能仍暂缓；社区 RC 内核也未经过长期老化验证。r4 的历史构建保存在 `output/verified-working-20261106/`，其 SHA-256 为 `767ef42bd8d8427a499e7916f0a837d9b223b7f452d12cdac63b13ca301fa6eb`。

更换 ACLCE 卡后的最初读写和重启校验已经通过，但 1-bit 阶段曾有 16 MiB 同步约 278 秒的停顿。该历史记录见 早期 SD 复测（本地记录：`artifacts/sd-final-report-20261106.json`）、早期重启校验（本地记录：`artifacts/sd-reboot-readback-20261106.json`）；当前设置和性能以顶部 r6 专项结果为准。旧 NCard 的只读保护仅匹配其 CID，不影响当前卡。

## 2026-11-02 实测更新

已在实机启动 Armbian 26.8.3 CLI / Ubuntu 22.04.5 最小用户空间，社区内核 `7.3.0-rc7-ec6108v9-r2`。这是社区开发内核，当前测试不能代替长期稳定性验证。

- 修正 eMMC/SD 异步探测编号，固定 eMMC 为 `mmc0`、外置 SD 为 `mmc1`，避免启用 SD 后 `root=/dev/mmcblk0p9` 指向错误设备。
- 移植 MV100 的 USB3 PHY/主机初始化；两个 USB 口各有一块约 7.1 GiB U 盘，均通过头/中/尾重复直接读取校验。有 FAT 的盘通过临时文件写入、卸载重挂读回和删除；另一个盘为空 MBR 分区表，未格式化，未测试写入。
- RTL8188ETV 使用 `rtl8xxxu` 和 `rtl8188eufw.bin`，可自动连接已配置 Wi-Fi，已通过两轮重新连接、路由器 ping 和 4 MiB 双向文件传输 SHA-256 校验。首次快速重关联曾短暂丢包，后续等待连接稳定的完整测试通过。
- 当时 SD 为 NCard 1.86 GiB，可重复读取。临时文件写入返回成功，但卸载重挂后丢失；4-bit 的 25 MHz、4 MHz、400 kHz，以及 1-bit 的 25 MHz 都出现相同现象；1-bit 测试还在重挂前清除了块缓存。**此卡写入没有通过验证。** 当时保留 1-bit/25 MHz 并针对其 CID 设置只读保护。后续换卡验证已通过，并恢复 4-bit；11 月 6 日发现原驱动未更新错误计数，所以历史“CRC/超时为零”不能用来排除恢复重试。
- 已补齐 NTP 自动校时，改用 DHCP 提供的 DNS，清除构建阶段遗留的服务启动阻止策略。HDMI、GPU、解码、音频按当前阶段要求保持关闭。
- 增加 `ec6108-accept-boot.service`：U-Boot 每次启动候选前先保存海NAS回退配置；Armbian 根系统和 SSH 启动正常、两份内核与环境校验通过后，再设置下一次启动 Armbian。早期失败后的下一次复位会回到海NAS。

源码补丁在 `patches/`，构建器按 SHA-256 检查并应用，且每次增量构建都同步 `targets/` 的 DTS。打包时核对编译出来的 eMMC/SD 别名，避免再次漏带板级修改。

具体测试日志在 `artifacts/*20261102*`。正常重启验证结果以 `artifacts/normal-reboot-20261102.txt` 和后续复查记录为准。

## 实机与验证状态

- SoC：Hi3798MV100，四核 Cortex-A7，armhf，启动参数配置 1 GiB RAM。
- 存储：约 4 GB eMMC；原系统根分区 `/dev/mmcblk0p9`。
- 原系统：海 NAS / Ubuntu 20.04.6，内核 `4.4.35_ecoo_81032968`。
- 连接：电脑 `enp4s0` 与盒子网口直连，SSH 使用 IPv6 链路本地地址。普通双公 USB 线没有枚举出可用数据接口。
- 已备份 p1～p7、eMMC boot0/boot1，并逐一核对实机与本机 SHA-256。未完整备份 p8/p9，原根分区保留。
- 已在盒子上创建独立的 1536 MiB ext4 根文件系统镜像，安装依赖并通过 `dpkg --audit`、ARM 二进制执行、SSH 实际登录、离线文件系统检查。
- 已在隔离的挂载/PID/网络命名空间内，以 PID 1 实测 `pivot_root` 切换到 Armbian 镜像成功。

新内核真实启动结果以 `output/kernel-manifest.json` 的 `tested_boot` 和 `artifacts/` 下实测记录为准；编译成功不等于硬件验证成功。

## 固定的来源

根文件系统来自 Armbian 官方 GHCR `armbian/os/rootfs-armhf-jammy-minimal`，标签 `202605-2069cd1b0d77-H6eccde-Bd966a5`，底层 Ubuntu 22.04.5 / systemd 249。`tools/fetch-rootfs.py` 校验 OCI 清单及内容摘要。

CLI 组件来自 Armbian 官方 BSP 26.8.3，改包脚本 `tools/build-bsp.py` 移除了其他主板专用的启动脚本、刷机工具及内核安装钩子，暂时屏蔽自动调整分区或硬件的服务。

内核来自 [histb-mainline/linux 的 mv100 分支](https://github.com/histb-mainline/linux/tree/mv100)，固定提交 `e92ca2afc9bcb365616ff780af29c9dcaf5f2d38`，版本 `7.3.0-rc7`。它是适配该芯片的社区开发内核。来源与压缩包摘要记录在 `artifacts/kernel-source.json`。板级 DTS 基于同仓库 EC6108V9C，配置在 `targets/`。

初次验证聚焦 CPU、eMMC、网口与 USB，关闭 HDMI、GPU、视频解码和音频。硬件是否可用必须在实机启动后逐项确认。

## 工作文件

| 路径 | 用途 |
| --- | --- |
| `tools/box.py` | 优先使用本机专用 SSH 密钥，兼容已建立的多路复用连接，执行命令及传文件 |
| `tools/collect-box-info.sh` | 只读采集原系统硬件、分区及驱动信息 |
| `tools/build-kernel.py` | 使用 `work/build-tools` 的本地工具链配置、编译、安装模块 |
| `tools/package-kernel.py` | 将 zImage 和板级 DTB 打包为与原引导兼容的 uImage |
| `tools/prepare-kernel-trial.py` | 在电脑上生成一次性试启动环境和校验计划 |
| `tools/apply-kernel-trial.py` | 在盒子上核对备份与 CRC，再写入候选内核和启动环境；支持 `--check-only` |
| `tools/armbian-init.sh` | 早期 PID 1，切换到独立镜像，旧根保留在 `/.hinas` |
| `tools/with-rootfs.sh` | 在私有挂载命名空间中操作镜像 |
| `tools/test-rootfs-ssh.sh` | 在私有网络命名空间中实测镜像内 SSH 登录 |
| `tools/early-trial-watchdog.py` | 早期 600 秒确认超时及持久化内核日志 |
| `tools/accept-boot.py` | 校验运行系统、原内核、候选内核与环境后，设置下一次启动 Armbian |
| `tools/check-storage.py` | 存储直接读取与临时文件跨挂载校验；失败不算通过 |
| `tools/fix-system-config.py` | 修复实机审计发现的模块、Wi-Fi 启动、DHCP 和日志兼容设置；支持 `ARMBIAN_ROOT` |
| `tools/wifi-refresh-networkd.py` | 无线核心重新加载导致 nl80211 编号改变时，刷新旧版 networkd 的缓存 |
| `tools/audit-nat.py` | 三个隔离网络命名空间中实测桥接、连接跟踪、NAT 及校验数据，完成后清理 |
| `tools/audit-functional.sh` | 功能和服务的实机检查 |
| `tools/audit-storage.py` | 自动识别当前介质，直接读取及跨重启临时文件校验 |
| `tools/benchmark-sd.py` | SD 写入/同步计时、逐轮清缓存校验及跨重启复核 |
| `tools/test-sd-small-io.py` | 随机 4 KiB 更新，每次强制同步并清缓存校验 |
| `tools/configure-sd-automount.py` | 按已验证卡的 UUID 配置 `/mnt/sdcard`，保留原 fstab |
| `tools/test-sd-automount.py` | 中文文件名、重命名、SD 控制器重新识别及自动挂载复测 |
| `patches/` | USB3、定时器、随机数、MMC 源码补丁及构建前后 SHA-256 |
| `artifacts/backup-20261101/` | 原引导分区备份、摘要与 uImage 校验记录 |

`downloads/`、`work/`、`output/`、`artifacts/` 均已忽略。含有本机 SSH 身份或密码摘要的根文件系统备份不可公开。

## 一次性内核验证

原 p6 内核有效 uImage 约 10.4 MiB，p6 总共 20 MiB。已从完整备份确认 p6 偏移 12 MiB 后的 8 MiB 全为零。候选 uImage 限制在 8 MiB 内，放入该区域，保留原 uImage 头和所有有效数据。

原启动命令从 eMMC 块 `0x7000` 读 20 MiB；候选从块 `0xD000` 读 8 MiB。U-Boot 环境位于 p2，CRC32 覆盖的环境大小为 65536 字节。生成器保留环境区外数据。

试启动先恢复旧内核的默认启动命令并执行 `saveenv`，成功后才加载候选。候选失败后的下一次复位应选择旧内核。旧系统还安装确认超时定时器，用于新内核进入用户空间但未确认的情况。**早期内核彻底卡死时，软件定时器无法生效，仍可能需要断电复位。**

首次验证新内核与原海 NAS 用户空间；成功后再验证 Armbian 用户空间。启动写入脚本不适用于未经核实的其他盒子、分区布局或环境格式，也不会自动重启。

## 参考

- [海 NAS 内核说明](https://dl.ecoo.top/docs/nas-skill/kernel/)
- [海 NAS 作者公开的旧版 HiSTB 内核](https://github.com/teasiu/HiSTBLinuxKernel)
- [Hi3798MV100 社区内核](https://github.com/histb-mainline/linux)
- [EC6108V9C 其他社区内核项目](https://github.com/loonpn/ec6108v9c-linux-kernel)

## 日常连接与回退

在本机项目目录使用 `python3 tools/box.py run uname -r` 可直接连接，无需重新输入密码或恢复过期的 SSH 控制套接字。专用私钥在忽略的 `artifacts/` 下，权限 0600，不应公开或复制到其他机器。

Armbian 内执行 `/usr/local/sbin/ec6108-accept-boot` 只做启动校验；`--apply` 确认下次启动 Armbian；`--fallback` 选择保存的海NAS内核和根系统，下次普通重启生效。两者都会验证分区布局对应的内核摘要和环境 CRC，不会覆盖旧内核。

USB 盘符会随枚举顺序改变，挂载持久配置应使用 UUID。当前 FAT U 盘 UUID 为 `19EB-E04D`；另一块盘只有空分区表，保持未格式化。新 ACLCE SD 卡已通过跨挂载和重启持久化测试；旧 NCard 的失败记录及只读规则按 CID 保留。

2026-11-02 历史构建 SHA-256：`0c84cb180acea9617feedaf4948c77602eafbb6f11968412d81cefb64c5fe9cd`。两轮普通重启已自动回到 Armbian，最后一轮启动 ID 为 `4770989a-57e3-44e6-9246-4b4b20fa100c`。这是 2026-11-02 的历史验证记录；2026-11-06 更换 SD 卡后的持久化验证已通过，当前完整审计记录见后续报告。

重新配置根镜像前，应将 `tools/fix-system-config.py` 和 `tools/wifi-refresh-networkd.py` 上传到原系统 `/var/lib/armbian-port/` 同一目录；`configure-rootfs.sh` 和 `configure-wifi-rootfs.sh` 会在配置完成时调用它。对当前运行系统，将这两个文件放在同一目录后，以 root 执行 `fix-system-config.py`。
