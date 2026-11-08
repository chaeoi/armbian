# 2026-11-08 官方框架与 USB 镜像流程

## 已完成

- 获取官方 `armbian/build`，固定提交 `8ddeef322b4706b5be19d0fb7869f107c117666d`。
- 官方 `config-dump-json` 成功解析本机配置：`ARCH=armhf`、`BOARD_TYPE=tvb`、家族 `hi3798mv100`。
- 内核固定为原实机使用的 HiSTB 提交，关闭额外无线驱动和全量固件集合。
- 配置进入官方 kernel、base-files、BSP 和 rootfs 构建流程，不编译不匹配的上游 U-Boot。
- USB 启动资产取自公开 mdmo1d 包，REG 字符串与样机相符，逐文件记录摘要。
- RTL8188EU 固件及监管数据库按摘要确认与原实机验证文件完全一致。
- 检查引导程序的稀疏写入实现，确认 RAW、FILL、DONT_CARE 分支存在；导出器使用 RAW/FILL。
- 16 项主机测试通过，包含真实 ext4 容器的准备、导出、ZIP 校验和身份清理测试。
- 新 DTS 补丁已在固定源码归档上实际应用，并核对与本仓库设备树一致。
- 固定内核提交已通过远端 Git 浅获取验证，不依赖旧分支名继续存在。
- 官方框架原有压缩与产物整理函数已接受 `.usb.zip` 及其清单输出，未重复压缩 ZIP。

测试使用 Ubuntu `device-tree-compiler` 和 `e2fsprogs`。
其中 ext4 集成用例使用明确标记的合成内核与小文件系统，只验证格式和流程，不代表可启动系统。
临时文件不进入正式镜像输出目录，也不随 Git 或源码包发布。

## 烧写逻辑验证

全部烧写文件在第一次写 eMMC 前完成加载和 CRC 校验。
测试逐一模拟文件缺失、校验错误和写入失败，确认不在失败后提交正式启动环境或执行重启。
成功路径最后写入唯一 Armbian 的启动参数。
这验证脚本逻辑，不能代替实际 U-Boot 和闪存写入测试。

根文件系统稀疏转换后重新展开计算 SHA-256，与输入 ext4 容器一致。
零块使用显式 FILL，避免写入器跳过零块而保留先前内容。
内核头和数据 CRC、8 MiB 读取上限、DTB 存储别名、文件集合及写入边界均有检查。

## 尚待完成

- GitHub Actions 首次完整内核、BSP 和 rootfs 构建。
- 在实际 PCB 上确认短接点并验证芯片 USB 启动。
- 完整 USB 写入、首次启动、扩容、独立身份，以及 USB/SD/网络回归。

本机 `git push --dry-run origin main` 返回 HTTPS 未认证，且未发现可用 GitHub CLI/token 配置。
因此尚未推送新流程或触发远端工作流，不把本地配置与测试通过写成云端构建已通过。
新 USB 清单保持 `tested_boot=false`、`usb_boot_hardware_tested=false`。

原实机 r6 与私有网络重装包不参与新公开包的构建，尚未向盒子刷入新镜像。
