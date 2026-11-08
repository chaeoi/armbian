# EC6108V9 单 Armbian 固化记录 · 2026-11-07 至 08

> 历史实测记录。以下工作目录路径相对于当时的项目根目录；原始日志、镜像和设备配置未纳入公开仓库。当前入口见 [测试索引](../VALIDATION.md)。

**单系统安装、精简、系统盘和 USB 持久化、无线恢复及两次普通重启复核已完成。** 当前唯一运行系统为 Armbian 26.8.3 / Ubuntu 22.04.5 CLI，内核 7.3.0-rc7-ec6108v9-r6，直接使用 eMMC 根分区。设备上的海 NAS、原内核、旧恢复和备份分区、循环根镜像及系统回退逻辑已移除。

早期复核第二次启动时，RTL8188EU 在固件加载阶段从 USB 总线上掉线，端口及主控重置均未恢复。11 月 8 日完全断电后，芯片重新出现并自动连接。源码确认此驱动没有 USB shutdown 回调，关机不会自动执行其 disconnect 中的芯片关断流程；新增关机前驱动卸载，复用该驱动原有的关断和复位逻辑。

实际调用清理脚本后，模块在 0.817 秒内卸载，USB 设备保留，重新加载及联网共约 6.7 秒。随后连续两次普通重启均恢复 Wi-Fi，约 12.7 秒完成关联，未再出现本次的 USB 消失现象；最终有线与无线各 4 MiB 双向 SHA-256 校验通过。该结果覆盖这些具体用例，未据此宣称长期故障率为零。

## 最终布局

| 分区 | 起始位置 | 大小 | 内容 |
| --- | --- | --- | --- |
| mmcblk0p1 | 0 | 14 MiB | 合并的引导及板级参数区 |
| mmcblk0p2 | 14 MiB | 20 MiB | 唯一 r6 内核，剩余区域清零 |
| mmcblk0p3 | 34 MiB | 3,923,771,392 字节，约 3.65 GiB | 唯一 ext4 Armbian 根系统 |

分区由启动参数定义。合并逻辑分区没有移动 U-Boot、环境变量和板级参数在 eMMC 中的固定位置；内核仍从固定扇区读取。boot0/boot1 为 eMMC 硬件启动区域，并非另一套操作系统。

根 UUID：7c8c1bbb-09c7-4a6b-b5a5-a787694a3897。实际系统盘约使用 **282 MiB**、可用约 **3.3 GiB**；空闲观测内存约使用 **49 MiB**。

## 固化与清理

- 原 1.5 GiB 循环根镜像以及承载它的海 NAS 文件系统已被新的单一根分区替代，取消嵌套存储结构。
- 只保留 r6 的 41 个模块，删除 r2、r3、r4、r5 模块目录。
- 清理约 81 MiB apt 缓存、91 MiB 软件索引、测试记录、旧日志及备份。旧系统区中的早期安装包、试启动文件和预安装备份随重新安装移除。
- 卸载 cron、rsyslog、man-db、groff-base，以及 libestr0、libfastjson4、libpipeline1、libuchardet0。保留 SSH、Python、网络、自动校时、文件系统及日常管理工具。
- 关闭自动软件更新、新闻、旧维护定时任务；固定自定义 BSP，阻止其他主板内核包替换本机内核。用户仍可主动使用 apt。
- 使用内存日志，上限 8 MiB；删除重复的全局无线守护进程，保留实际管理 wlan0 的服务及无线恢复处理。
- 默认永久启动 Armbian，开机校验服务仅检查、不写启动选择；不再保留原系统回退入口。
- 加入仅在关机、重启时执行的无线清理脚本，无常驻进程；已同步加入安装包 overlay，后续一键重装会保留此修正。

系统保持可写，可正常安装软件和保存配置。“固化”对应固定已验证内核、启动方式和自动更新策略。

## 安装与一键程序

先将精简用户空间、当前内核和新启动配置打为校验包；在 RAM 中执行 ARM 程序与 SSH 配置预检。随后切换到完整的 RAM Armbian，确认 SSH、有线及 Wi-Fi 正常，卸载原系统，重建合并后的根分区并复制系统。离线 e2fsck 五项检查全部通过，最后才提交固定启动环境并重启。

首次 RAM 准备实际约四分钟，超过了最初三分钟等待上限；安装器现已调整为十分钟，并支持继续监控 RAM 中的现有安装状态。正式系统启动无需解包，实测本轮内核日志在约 9.8 秒有线链路就绪、约 12.5 秒无线关联完成。

私有安装包为 output/ec6108v9-armbian-r6-single（本地记录：`output/ec6108v9-armbian-r6-single/README.md`），约 105 MiB，其中根系统压缩包约 99 MiB。入口：

    output/ec6108v9-armbian-r6-single/flash.sh

只做校验：

    python3 output/ec6108v9-armbian-r6-single/flash.py

该安装器已经实际用于本次单系统安装；最终三分区状态下的只读硬件、分区和连接检查也通过。它需要盒子仍可通过 root SSH 连接，不能代替空白或无法启动设备所需的底层烧录工具。刷写会重建内置系统区；SD 和 USB 不作为写入目标。

包内附本机连接所需的 SSH 登录密钥和服务器身份校验信息，配置采用相对路径，移动目录仍可使用；另一电脑可能需要调整接口或目标地址。包中还含本机 Wi-Fi 和登录配置，应作为私有备份保存。客户端登录私钥未嵌入系统镜像。

## 实际验证

| 项目 | 结果 |
| --- | --- |
| 安装前预检 | 根包、内核及安装文件摘要一致；uImage 头和数据 CRC 正确；eMMC 身份及偏移符合目标布局；启动环境编码、CRC 和尾部保持检查通过 |
| 新文件系统 | 安装阶段卸载后执行 e2fsck -fn，五项检查通过，退出码 0 |
| 单系统启动 | 首次安装后启动、随后普通重启均进入直接 eMMC 根分区，开机校验通过，无失败服务 |
| 永久启动配置 | 两次启动间的环境摘要保持一致，证明开机未再改写启动选择 |
| 系统盘持久化 | 16 MiB 随机文件同步、清缓存读取及普通重启后 SHA-256 一致，已删除 |
| USB 持久化 | 当前 UUID 19EB-E04D 的 U 盘 4 MiB 文件跨挂载、清缓存和普通重启校验通过，已删除；fsck.fat -n 通过 |
| 网络 | 冷启动恢复后，实际清理脚本卸载/重载、连续两次普通重启均恢复 Wi-Fi；最后有线和无线各 4 MiB 下载、上传 SHA-256 一致，省电关闭 |
| 模块 | 当前 41 个 r6 模块与编译清单 SHA-256 全部一致 |
| 存储错误 | 最终 eMMC CRC、超时等错误计数全部为零 |
| 精简状态 | 仅有三个逻辑分区、仅一套模块，无循环系统盘、原系统挂载或安装暂存目录；测试文件已清除 |

第一次直接启动 ID：8515ae5c-7d73-4555-b8d9-d296bb6aeef6。最终两次普通重启 ID：fab70968-55e3-447e-82f1-831fd82fe754、3462e75d-587e-4f8a-a2fa-fc8d0ee0bf4c。

最终安装配置版本：ec6108v9-armbian-26.8.3-r6-single-20261108。

启动环境 SHA-256：38ec2d0dc5b07193439cfedddce4d2ff212a2faf3c2920efe9651c393804044c。

内核 SHA-256：1f9598b747b20d0fb9483c63ec497fe80b1b6bb7fcb29da210f5e66720eaf4ee。

本轮迁移时 SD 已被物理拔出，因此没有新增插卡测试。保留 /mnt/sdcard 的 UUID 自动挂载配置和已验证的驱动；此前同一 r6 内核下该卡的连续读写、清缓存及跨重启记录见 [SD 修复](SD-INVESTIGATION-20261106.md) 和 [换卡对照](SD-OLD-CARD-20261107.md)。HDMI 等原先暂缓功能仍未启用，社区 RC 内核尚未做长期老化。

## 证据

- 安装包清单（本地记录：`artifacts/finalize-system-20261107/release-manifest.json`）、首次安装过程（本地记录：`artifacts/finalize-system-20261107/install.log`）、RAM 续接及安装成功（本地记录：`artifacts/finalize-system-20261107/install-resume.log`）
- 第一次直接启动（本地记录：`artifacts/finalize-system-20261107/direct-first-boot.txt`）、最终状态（本地记录：`artifacts/finalize-system-20261107/final-state.json`）
- 系统盘与 U 盘跨重启（本地记录：`artifacts/finalize-system-20261107/persistence-after.json`）、模块一致性（本地记录：`artifacts/finalize-system-20261107/module-integrity.json`）
- 有线及无线传输（本地记录：`artifacts/system-audit-20261106/network-single-direct.json`）、可移动私有包只读检查（本地记录：`artifacts/finalize-system-20261107/portable-package-check.log`）
- 第二次启动无线掉线（本地记录：`artifacts/finalize-system-20261107/wifi-second-boot-check.txt`）、端口开关对照（本地记录：`artifacts/finalize-system-20261107/wifi-port-power-cycle.json`）、控制器对照（本地记录：`artifacts/finalize-system-20261107/wifi-phy-reprobe.json`）
- 完全断电后的恢复（本地记录：`artifacts/finalize-system-20261107/wifi-after-cold-power.txt`）、实际清理脚本测试（本地记录：`artifacts/finalize-system-20261107/wifi-shutdown-hook-test.json`）
- 第一次普通重启（本地记录：`artifacts/finalize-system-20261107/wifi-clean-warm-reboot-1-state.txt`）、第二次普通重启（本地记录：`artifacts/finalize-system-20261107/wifi-clean-warm-reboot-2-state.txt`）、最终双向传输（本地记录：`artifacts/system-audit-20261106/network-single-final-20261108.json`）

安装器和构建源码保存在 tools/，本地私有安装包附 SHA256SUMS 和 BUNDLE-SHA256SUMS。当前设备无需这些构建或安装文件即可启动和使用。
