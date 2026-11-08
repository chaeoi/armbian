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
- Realtek Wi-Fi 固件：`packages/blobs/hi3798mv100/firmware/` 收录实机验证的版本、监管数据库和许可文本。
  摘要与 Ubuntu 软件包来源见 `config/sources/ec6108v9-firmware.json`。
  Ubuntu 包装层的 copyright 不代表每个固件均为 GPL 源码。
- USB 引导与板级参数：来自公开海纳思 mdmo1d USB 包，文件未修改。
  摘要、来源和 REG 名称见 `config/sources/usb-bootstrap.json`，资产目录附 `NOTICE.md`。
  原包没有单独许可文件；这些第三方二进制不由本仓库的 GPL 声明重新许可。
  不包含海纳思 Linux 内核、恢复系统或根文件系统，亦不包含原设备个人备份。

这是社区适配项目，与 Huawei 或 Armbian 官方的支持和认证无关。
