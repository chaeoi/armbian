# Armbian for Huawei EC6108V9

Huawei EC6108V9 / Hi3798MV100 的 Armbian 社区适配仓库，面向精简命令行和存储服务用途。
当前实机基线为 **Armbian 26.8.3 / Ubuntu 22.04.5 Jammy armhf**，
内核 **7.3.0-rc7-ec6108v9-r6**，直接使用 eMMC 上唯一的 ext4 根系统。

**适配状态：实验性社区移植。** 当前内核为 RC 版本，尚未完成长期老化；本项目不属于 Armbian 官方支持的主板。
仓库包含板级设备树、固定源码清单、补丁、内核构建和专用网络安装工具。
目前可独立构建内核、DTB 和模块，通用整机镜像与离线救砖包尚未完成。

## 设备支持

| 项目 | 已验证配置 |
| --- | --- |
| 型号 / SoC | Huawei EC6108V9 / Hi3798MV100，四核 ARMv7 |
| 内存 / eMMC | 1 GiB / 4 GB，eMMC 实际 3,959,422,976 字节 |
| 引导配置 | mdmo1d；同名外壳的其他主板须另行核实 |
| 可用接口 | eMMC、SD、两个 USB 口、有线网络、RTL8188ETV Wi-Fi，测试轮次见记录 |
| 尚未启用 | HDMI、音频、GPU、视频解码；温度及动态调频尚未提供 |

SD 已修复大块读取超时，并通过正常 64 GB 卡的读写和重启校验。
Wi-Fi 配置关机驱动清理后，两次普通重启自动连接及双向传输通过。
各接口测试范围、未验证项目及已知限制见 [硬件说明](docs/HARDWARE.md) 和 [测试记录](docs/VALIDATION.md)。

## 快速开始

Linux 主机、Python 3.12+，安装依赖后：

```sh
./compile.sh check      # 离线检查源码、配置、文档及主机测试
./compile.sh kernel     # 校验下载、应用补丁、构建并打包内核和模块
```

产物位于 `output/`，附源码提交、完整配置、编译信息及 SHA-256。
构建不连接盒子、不写入设备；新构建默认标记为尚未上机测试。
详细依赖、工作目录和分步构建见 [构建指南](docs/BUILD.md)。

## 安装与救砖

已有私有网络重装包支持经过硬件和分区检查的本机，要求设备仍能 root SSH 登录。
它从 RAM 完成安装，最终为 **14 MiB 引导区 + 20 MiB 内核区 + 剩余空间根分区**，不保留 HiNAS 或旧系统回退。
当前实机根系统约用 282 MiB，可用约 3.3 GiB；这些是该次精简安装的观测值。

私有包包含设备身份和无线配置，不在公开仓库或 CI 产物中。
本项目的内核包不是可直接写卡的整盘 `.img`，网络重装包也不能给无法启动的设备直接救砖。
参见 [安装说明](docs/INSTALL.md) 和 [救砖范围](docs/RECOVERY.md)。

## 仓库结构

```text
config/
  boards/       设备参数和启动布局
  kernel/       最小服务器内核配置片段
  sources/      固定源码提交、下载地址和摘要
dts/            EC6108V9 板级设备树
patch/kernel/   有顺序和源码摘要保护的内核补丁
tools/          构建、安装、运行时兼容和诊断工具
tests/          不访问设备的主机测试
docs/           构建、安装、硬件、救砖与实测记录
.github/        自动检查及手动内核构建工作流
compile.sh      本项目构建入口
```

`downloads/`、`work/`、`output/`、`artifacts/` 和 `local/` 为忽略的本地目录。
旧双系统及试启动方案已退出活跃工具集，记录留在 `docs/history/`。
工具中哪些会修改目标设备，见 [工具分类](tools/README.md)。

## 源码与维护

内核基于 [histb-mainline/linux](https://github.com/histb-mainline/linux) 的固定提交
`e92ca2afc9bcb365616ff780af29c9dcaf5f2d38`，增加 USB 初始化、四核定时器、RNG 短读和 MMC 超时及统计修复。
上游源码按固定摘要获取，不随分支自动升级。

本项目适配代码采用 [GPL-2.0-only](LICENSE)，第三方部分保留原许可，见 [来源说明](NOTICE.md)。
参与维护见 [CONTRIBUTING](CONTRIBUTING.md)，变更见 [CHANGELOG](CHANGELOG.md)。
Wi-Fi 运行仍需要单独的 Realtek 二进制固件；原设备引导和 DDR 参数不包含在仓库中。
