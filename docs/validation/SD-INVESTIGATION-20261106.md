# EC6108V9 SD 卡修复与实测 · 2026-11-06

> 历史实测记录。以下工作目录路径相对于当时的项目根目录；原始日志、镜像和设备配置未纳入公开仓库。当前入口见 [测试索引](../VALIDATION.md)。

当前使用 ACLCE 64 GB（59.5 GiB）、exFAT，UUID `6802-7F21`。本轮直接连接盒子修改、启动内核并测试，未格式化卡；读写测试仅操作新建的临时文件。

## 修复内容

1. **恢复 SD 的 4-bit / 25 MHz 总线。** 之前为排查旧 NCard 写入丢失而保留了 1-bit 配置，这明显限制当前卡的性能。现在使用 4-bit、25 MHz、3.3 V、legacy timing，保持原时钟频率。
2. **修正 DesignWare MMC 的软件读超时计算。** 原定时器只按数据访问等待时间设置期限，未计入整笔数据经过总线的时间。1 MiB 数据在 1-bit / 50 MHz 总线上理论上就需要约 168 毫秒，原软件期限可能先到，导致正在传输的 eMMC 请求被判超时并退回单块重试。现在根据块数、块长、实际总线宽度和时钟分频补足传输时间；硬件超时、CRC 检查与错误恢复逻辑保留。
3. **补齐真实错误统计与恢复日志。** 此驱动以前没有更新通用 `err_stats`，所以过去“计数为零”不足以排除重试。现在统计命令/数据的 CRC 与超时，并记录进入块层恢复的请求。诊断版 r5 捕获到 eMMC 的错误超时；修正后的 r6 启动及额外 64 MiB 直接读取均为零错误、无恢复日志。
4. **配置日常访问路径。** 当前卡按 UUID 自动挂载到 `/mnt/sdcard`。卡缺席不会阻止系统启动；访问路径才触发挂载。原 `/etc/fstab` 已备份到 `/var/lib/ec6108-backups/fstab-before-sd-automount`。更换不同 UUID 的卡需要相应调整这一项。

改动见 `targets/hi3798mv100-ec6108v9.dts`、`patches/0004-mmc-report-recovered-errors.patch` 和 `tools/configure-sd-automount.py`。eMMC 继续使用原来的 1-bit / 50 MHz 配置。

## 写入、同步和清缓存读回

数据先在 RAM 中生成，计时包含文件写入及 `fdatasync`；每轮都卸载、清空块缓存、只读重挂并校验 SHA-256。以下速度不是单纯写入页缓存的速度。

| 配置与用例 | 写入加同步 | 清缓存读取 | 校验 |
| --- | --- | --- | --- |
| 原 r4，1-bit / 25 MHz，3 × 16 MiB | 6.327、7.093、28.336 秒；0.565～2.529 MiB/s | 每 16 MiB 约 15.1～16.3 秒 | 通过，但有明显停顿与单块请求 |
| r5，4-bit / 25 MHz，8 × 64 MiB | 每轮 6.066～7.613 秒；8.406～10.551 MiB/s | 每 64 MiB 约 5.60 秒；约 11.4 MiB/s | 全部通过，SD CRC/超时计数为零 |
| 最终 r6，4 × 64 MiB | 每轮 6.113～6.682 秒；9.578～10.469 MiB/s | 每 64 MiB 约 5.60 秒 | 全部通过，SD CRC/超时计数为零 |
| 最终 r6，128 次随机 4 KiB 更新，每次同步 | 中位 1.826 ms，95 分位 1.941 ms，最慢 9.112 ms | 整个 1 MiB 文件卸载、清缓存读回 | SHA-256 一致 |

仅上述两轮长测试就累计写入 768 MiB、清缓存读回 768 MiB；另有前后对照、随机写和跨重启验证。没有再现修复前数十秒至数分钟的同步停顿。这是当前卡及已测负载的结果，未进行全容量覆盖或长期老化。

## 启动与持久化

- r5 留下的 16 MiB、64 MiB 文件，在启动 r6 后均校验一致，随后删除。
- 最终 r6 连续两次正常启动并自动确认；64 MiB 连续写文件和 1 MiB 随机更新文件在第二次启动后 SHA-256 均一致，随后删除。最终启动 ID 为 `34b8b0ec-690e-43d6-a2e6-46daeed1b209`。
- 开机自动挂载、中文长文件名、重命名通过。清洁卸载后只重新绑定 SD 控制器，再次触发自动挂载，2 MiB 文件冷读 SHA-256 一致；eMMC 管理连接保持正常。这验证了软件重新识别流程，未进行物理拔卡或强制断电测试。
- 有线及 Wi-Fi 各完成 4 MiB 下载到 SD、同步、清除文件缓存、读回上传；电脑与盒子双方 SHA-256 一致。
- 最终所有测试文件与目录均删除，`fsck.exfat -n` 显示干净，原有 4 个目录、912 个文件保留；当前可在 `/mnt/sdcard` 读写。无失败服务，启动校验通过，41 个模块与构建摘要一致。
- 原海 NAS 内核与回退逻辑保留。旧 NCard 的 CID 专用只读规则继续保留，不影响当前卡。

最终内核 `7.3.0-rc7-ec6108v9-r6`，镜像 5,787,087 字节，SHA-256：

`1f9598b747b20d0fb9483c63ec497fe80b1b6bb7fcb29da210f5e66720eaf4ee`

## 证据与复测工具

- 原配置对照（本地记录：`artifacts/sd-investigation-20261106/baseline-1bit.json`）、4-bit 长测试（本地记录：`artifacts/sd-investigation-20261106/4bit-long.json`）
- r6 连续读写（本地记录：`artifacts/sd-investigation-20261106/r6-bulk.json`）、r6 小块同步写入（本地记录：`artifacts/sd-investigation-20261106/r6-small.json`）
- r6 首次启动（本地记录：`artifacts/sd-investigation-20261106/r6-first-boot.txt`）、eMMC 超时修复复测（本地记录：`artifacts/sd-investigation-20261106/r6-timeout-regression.txt`）
- 16 MiB 跨重启（本地记录：`artifacts/sd-investigation-20261106/r5-16m-reboot-verify.log`）、64 MiB 跨重启（本地记录：`artifacts/sd-investigation-20261106/r5-64m-reboot-verify.log`）
- 最终 r6 大文件跨重启（本地记录：`artifacts/sd-investigation-20261106/r6-bulk-reboot-verify.log`）、随机更新跨重启（本地记录：`artifacts/sd-investigation-20261106/r6-small-reboot-verify.log`）
- 自动挂载与重新识别（本地记录：`artifacts/sd-investigation-20261106/r6-automount-reprobe.json`）、有线/无线实际传输（本地记录：`artifacts/system-audit-20261106/network-r6-sd.json`）、最终状态及文件系统检查（本地记录：`artifacts/sd-investigation-20261106/r6-final-state.json`）

已验证镜像、配置、模块及摘要另存于 `output/verified-working-20261106-r6/`。原 r4 的全面审计构建与回退文件保留。

`tools/benchmark-sd.py` 分别记录写入、同步和清缓存读取；`tools/test-sd-small-io.py` 测随机更新逐笔同步。保留文件的记录包含卡 CID、UUID、SHA-256 与启动 ID；验证阶段要求实际经历重启，成功后才删除对应临时文件。
