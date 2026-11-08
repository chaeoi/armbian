# 来源与许可证

本仓库原创适配脚本、配置和文档采用 GPL-2.0-only，许可证全文见 `LICENSE`。
没有单独声明的代码按该许可提供；上游文件及补丁涉及的原有代码保留原版权及许可证。

- Linux：来自 [histb-mainline/linux](https://github.com/histb-mainline/linux)，固定提交见源码清单。
  Linux 内核采用 GPLv2 及其 syscall exception，各文件可能有兼容的独立声明。
- 设备树：继承该社区内核的 EC6108V9C DTS，板级修改见 `dts/`。
- Armbian CLI BSP 调整：基于 [armbian/build](https://github.com/armbian/build) 的 26.8.3 组件，
  原包摘要与构建来源见 `tools/build-bsp.py`，上游框架为 GPLv2。
- 官方 Armbian rootfs：原始 OCI 清单和摘要固定在 `tools/fetch-rootfs.py`；
  用户空间软件包分别遵循其自身许可证。
- Realtek Wi-Fi 固件：运行时需要 `rtl8188eufw.bin`。本仓库不包含该二进制，
  分发时须另行携带对应固件许可；Ubuntu 包装层的 copyright 不代表其中每个固件均为 GPL 源码。
- 原设备 U-Boot、DDR/REG 配置与参数备份不包含在本仓库，亦不由本仓库重新许可。

这是社区适配项目，与 Huawei 或 Armbian 官方的支持和认证无关。
