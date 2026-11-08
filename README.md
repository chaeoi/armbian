# Armbian for Huawei EC6108V9

[![Build USB image](https://github.com/chaeoi/armbian/actions/workflows/build.yml/badge.svg)](https://github.com/chaeoi/armbian/actions/workflows/build.yml)

Huawei EC6108V9 / Hi3798MV100 的 Armbian 社区适配。目标为 **mdmo1d、1 GiB RAM、4 GB eMMC** 样机。
仓库通过固定版本的官方 Armbian Build Framework 构建内核、BSP 和 Jammy 最小系统，再导出 **U 盘刷机 ZIP**。
下载完成后解压到 FAT32 U 盘，从主板 USB 启动入口安装，无需原系统或 SSH。

**状态：社区 TV box / 实验性。** 原 r6 系统已有实机记录；新增官方框架与 USB 导出流程已通过本地主机验证。
首次 GitHub Actions 全量构建、U 盘启动与完整烧写尚待验证，新包不会自动标记为已上机测试。

## 下载和刷机

打开 [Build EC6108V9 USB image](https://github.com/chaeoi/armbian/actions/workflows/build.yml)，点击 **Run workflow**。
成功后从该次运行的 Artifacts 下载产物。勾选 `publish` 可同时创建预发布版本。
镜像按官方规则命名，例如：

```text
Armbian-unofficial_26.11.0-trunk_Ec6108v9_jammy_edge_<kernel>_minimal.usb.zip
```

1. 校验 ZIP 的 SHA-256，解压到 FAT32 USB 2.0 U 盘根目录。
2. 断电，插入 U 盘、接网线，按实际主板短接点进入 USB 启动模式。
3. USB 启动后放开短接，保持供电，等待写入和自动重启。
4. 首次启动通过有线 DHCP 获取地址。SSH 初始账号为 `root`，密码为 `1234`，首次登录修改。

安装会删除内置系统及数据，最终只有一个 Armbian。SD 和其他 USB 存储不在烧写目标内。
短接点尚未经本项目实测，不能只凭外壳型号套用其他 V9/V9C 教程。
完整步骤、包内文件和验证范围见 [安装指南](docs/INSTALL.md) 与 [USB 构建记录](docs/validation/USB-PIPELINE-20261108.md)。

## 构建

```sh
./compile.sh check
./compile.sh build BOARD=ec6108v9 BRANCH=edge RELEASE=jammy BUILD_MINIMAL=yes BUILD_DESKTOP=no
```

入口自动获取固定的官方构建框架并安装本仓库板级扩展。完整构建需要框架要求的 Linux 主机和 root 权限，
GitHub Actions 已配置所需环境。本机无需维护私人 rootfs、设备密钥或 Wi-Fi 配置即可重建。
详见 [构建指南](docs/BUILD.md)。

## 目录

```text
config/boards/ec6108v9.tvb               官方格式的 TV box 配置
config/sources/families/hi3798mv100.conf 芯片家族配置
config/kernel/linux-hi3798mv100-edge.config
patch/kernel/archive/hi3798mv100-7.3/    官方构建使用的板级补丁
extensions/ec6108v9-usb.sh              系统配置与镜像导出扩展
packages/bsp/ec6108v9/                  首次启动、稀疏镜像与 USB 打包
packages/blobs/hi3798mv100/              固定摘要的引导参数和已验证无线固件
.github/workflows/build.yml             全量构建、校验、产物及可选发布
```

四组原 r6 修复保存在 `patch/kernel/hi3798mv100/`，准备框架时合并到官方补丁目录。
`config/boards/ec6108v9.json` 记录本机容量和固定扇区布局，辅助工具与官方配置共同使用。
`downloads/`、`work/`、`output/`、`artifacts/` 和 `local/` 为本地忽略目录。

## 硬件和基线

| 项目 | 当前范围 |
| --- | --- |
| CPU / 存储 | 四核 ARMv7、1 GiB RAM、eMMC；直接 ext4 根分区 |
| USB / SD | 两个 USB 口；SD 4-bit / 25 MHz，r6 下有正常卡读写及重启记录 |
| 网络 | Ethernet；RTL8188ETV / rtl8xxxu，保留已验证的无线固件和关机复位 |
| 安装布局 | 14 MiB 引导、20 MiB 内核、其余空间单一根分区 |
| 首次启动 | 扩展 ext4、独立 SSH 主机密钥、按 eMMC 身份生成本地 MAC，SD 按固定卡槽自动挂载 |
| 未启用 | HDMI、音频、GPU、视频解码；温度与动态调频接口尚未提供 |

现有实机仍为 Armbian 26.8.3 / Ubuntu 22.04.5，内核 `7.3.0-rc7-ec6108v9-r6`。
新官方框架构建的包拥有独立版本和测试状态，不继承旧镜像的上机认证。
RC 内核未完成长期老化；同名外壳下的其他 PCB、DDR 或闪存配置不在当前兼容范围内。
见 [硬件说明](docs/HARDWARE.md)、[测试索引](docs/VALIDATION.md) 与 [救砖说明](docs/RECOVERY.md)。

本项目适配代码采用 [GPL-2.0-only](LICENSE)。第三方引导与固件保留原有来源和许可，见 [NOTICE](NOTICE.md)。
维护约定见 [CONTRIBUTING](CONTRIBUTING.md)，变更见 [CHANGELOG](CHANGELOG.md)。
