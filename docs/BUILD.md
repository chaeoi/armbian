# 使用官方 Armbian 框架构建

本仓库是设备适配层。入口获取固定版本的官方框架，复制标准板级、家族、配置、补丁和扩展后运行其原生构建命令。
官方框架提交固定在 `config/sources/armbian-build.json`，不是手写替代的 rootfs 构建器。

## GitHub Actions

工作流为 `.github/workflows/build.yml`。支持手动运行，以及 `main` 上构建相关文件的更新。
它完成主机测试、官方内核与用户空间构建、USB 安装盘导出、压缩镜像校验和适配源码归档。
产物上传到 Artifacts。手动勾选 `publish` 时额外创建预发布版本；普通构建只需仓库读取权限。
构建失败时保留框架日志。

此流程从公开源码、官方 rootfs 流程和固定引导/固件资产构建，不读取开发机私人目录或设备备份。
当前首次云端全量构建尚待执行，不能把已提交工作流当作已构建成功。

## 本地入口

建议使用 Ubuntu 24.04 x86_64。完整构建由官方框架准备依赖，需要 root 或可用 sudo。

```sh
./compile.sh check
./compile.sh build BOARD=ec6108v9 BRANCH=edge RELEASE=jammy BUILD_MINIMAL=yes BUILD_DESKTOP=no
```

默认框架位于 `work/armbian-build/`，可用 `ARMBIAN_BUILD_DIR` 指定其他目录。
已经存在但提交不符的目录会被拒绝，不会自动重置或覆盖其历史。

```sh
./compile.sh prepare-framework
CONFIG_DEFS_ONLY=yes ./compile.sh config-dump-json BOARD=ec6108v9 BRANCH=edge RELEASE=jammy
./compile.sh kernel BOARD=ec6108v9 BRANCH=edge
```

`kernel` 使用官方框架生成内核 Debian 包。完整 USB 镜像使用 `build` 命令。
目前只维护 `edge` 的固定 HiSTB 7.3-rc7 源码及 Jammy 最小系统，没有暗示其他发行版或分支已验证。

## 官方布局与固定输入

- `config/boards/ec6108v9.tvb`：主板、维护者、设备树和家族。
- `config/sources/families/hi3798mv100.conf`：armhf、内核提交、镜像大小和网络。
- `config/kernel/linux-hi3798mv100-edge.config`：基于原实机完整配置。
- `patch/kernel/hi3798mv100/`：USB 时钟、四核定时器、RNG、MMC 的原修复。
- `patch/kernel/archive/hi3798mv100-7.3/`：注册本机 DTS。准备框架时并入前述四组修复。
- `extensions/ec6108v9-usb.sh`：用户空间配置、独立设备身份、USB 导出。
- `packages/blobs/hi3798mv100/`：摘要受保护的 mdmo1d 引导与参数、原实机验证的无线固件。

不再编译其他无线驱动，也不安装全量固件集合。系统只保留当前目标的 RTL8188EU 固件和监管数据库。
原设备引导备份不参与公开构建；USB 引导取自有固定摘要的公开 mdmo1d 底包，不包含海纳思内核或根系统。

目录和扩展接口参考 [官方添加板卡说明](https://docs.armbian.com/build-framework/adding-a-board/)。

新配置不携带旧 `-ec6108v9-r6` 后缀；版本后缀由官方框架统一生成，保持内核、模块与 Debian 包命名一致。
`check` 的磁盘集成用例需要 `device-tree-compiler`、`e2fsprogs`、`dosfstools` 和 `mtools`。
缺少时明确显示跳过；Actions 会安装全部依赖，板级扩展也声明了构建主机的 FAT 工具依赖。

## 镜像导出

框架先生成标准的中间 ext4 磁盘容器，根分区从 34 MiB 开始。
扩展验证已安装内核和存储别名，生成追加 DTB 的 legacy uImage，并导出 Android sparse 根文件系统。
该容器只用于读取已构建的根系统。扩展随后将它替换成真正的 512 MiB USB 安装盘：
MBR 分区表、从 1 MiB 开始的单一 FAT32 分区，根目录包含 USB 引导和 `mv100/` 烧写文件。
分区内的所有文件写入后进行只读 FAT 检查。
这张盘用于安装到 eMMC；盒子的正常 Armbian 根系统安装在 eMMC 中。

根文件系统中的零块编码为 FILL，避免烧写时保留零块位置的旧内容。
官方 `cleanup-space-final-image` 扩展在卸载 ext4 后清零空闲块，清除已删除构建文件的残留并缩小稀疏文件。
U-Boot 先校验全部文件，再依次写根系统、内核、参数和引导，正式启动环境最后写入。
内核分区有 20 MiB，但 U-Boot 只读取前 8 MiB；uImage 超过上限会拒绝打包。
稀疏文件超过 384 MiB RAM 缓冲限制时同样拒绝。

最终压缩、整盘 SHA-256 和文件整理使用官方框架原有流程，默认 `COMPRESS_OUTPUTIMAGE=sha,xz`。
`output/images/` 包含 `.img.xz`、`.img.xz.sha`、`.img.txt` 以及 `.manifest.json` 和对应 `.sha`。
盘内还保留每个烧写文件的 SHA-256，启动脚本包含 CRC 校验。
来源清单保持 `tested_boot=false`，直到有对应镜像的实机证据。

```sh
python3 tools/verify-usb.py output/images/*.img.xz
```

校验工具以只读方式解压镜像，检查 MBR、FAT32、全部文件、启动环境、内核和稀疏根系统。
它拒绝额外文件、错误写入范围及不一致的来源清单，不访问盒子或主机物理磁盘。

## 旧 r6 独立工具

早期本机内核流程保留用于追溯和维护已验证镜像：

```sh
./compile.sh fetch
./compile.sh prepare
./compile.sh configure
./compile.sh kernel-local
```

这些命令只生成旧格式的独立内核、DTB 和模块，不负责新的完整 USB 镜像。
旧本机可显式使用 `EC6108_USE_BUNDLED_TOOLS=1`，工作目录覆盖仍支持 `EC6108_SOURCE_DIR`、`EC6108_BUILD_DIR`、`EC6108_OUTPUT_DIR`。

## 适配源码包

先用 `git add` 暂存公开源码，再运行 `./compile.sh source`。
导出器从 Git 索引生成 `output/ec6108v9-armbian-port-source.tar.gz`，不读取私人工作目录。
它包含配置、补丁、扩展及登记过的引导/固件资产；完整 Linux 与官方框架按固定提交获取。
源码包解压后不依赖 `.git` 即可检查和构建，再次导出才需要 Git 索引。
