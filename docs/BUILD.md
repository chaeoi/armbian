# 构建 EC6108V9 内核

本仓库是独立的社区适配层，目录参考 Armbian 的板级配置和内核补丁组织方式。
`compile.sh` 是本项目入口，不是上游 Armbian Build Framework 的同名脚本。
目前可从干净源码构建内核、DTB 和模块；尚不提供从零生成通用整机 `.img` 的流程。

## 构建环境

建议在 Ubuntu 24.04 的 x86_64 Linux 主机上构建，Python 3.12 或更新版本。
下载、编译和打包均不需要 root；只有安装主机依赖需要 sudo：

```sh
sudo apt-get update
sudo apt-get install -y python3 git make gcc gcc-arm-linux-gnueabihf \
    binutils-arm-linux-gnueabihf bison flex bc libssl-dev libelf-dev patch
./compile.sh check
./compile.sh kernel
```

默认使用 `arm-linux-gnueabihf-gcc`。可用 `CROSS_COMPILE` 指定其他兼容工具链，
`HOSTCC` 指定主机编译器，`JOBS=8 ./compile.sh kernel` 调整并行任务数。

## 固定输入

- 源码地址、提交、原始归档 SHA-256：`config/sources/linux-hi3798mv100.json`。
- 设备与启动布局：`config/boards/ec6108v9.json`。
- `hisi_defconfig` 加 `config/kernel/linux-hi3798mv100.config` 配置片段。
- `patch/kernel/hi3798mv100/series.json` 决定补丁顺序，并校验修改前后的源码摘要。
- `dts/hi3798mv100-ec6108v9.dts` 覆盖上游同名板级设备树。

构建按固定提交下载，不跟随分支最新版本。源码原始导入分支名是 `mv100`；
以后该分支改名或删除，也不会自动切换到别的内核。
已有归档会先校验 SHA-256，网络不可用时可使用校验通过的缓存。
已有源码目录只有在来源记录相符时才会复用，补丁既可首次应用，也可重复验证。

分步操作：

```sh
./compile.sh fetch
./compile.sh prepare
./compile.sh configure
python3 tools/build-kernel.py build
python3 tools/build-kernel.py modules-install
python3 tools/package-kernel.py
python3 tools/package-modules.py
```

## 工作目录与产物

默认源码在 `work/histb-linux-source/`，编译目录在 `work/kernel-build/`，产物在 `output/`。
这些目录均不纳入 Git。可在构建前设置下列变量隔离新构建：

```sh
export EC6108_SOURCE_DIR=work/new-source
export EC6108_BUILD_DIR=work/new-build
export EC6108_OUTPUT_DIR=output/new-kernel
./compile.sh kernel
```

不要让新构建覆盖唯一的已验证固件。旧开发环境中手动解压、没有来源记录的源码树不会被自动接管或删除；选择新的源码目录即可。
原开发机还可显式设置 `EC6108_USE_BUNDLED_TOOLS=1` 使用本地解包工具链；干净检出不依赖它。

输出包含：

| 文件 | 用途 |
| --- | --- |
| `uImage-ec6108v9` | legacy uImage 头 + ARM zImage + 追加 DTB |
| `hi3798mv100-ec6108v9.dtb` | 单独设备树，便于检查 |
| `kernel.config` | Kconfig 解析后的完整配置 |
| `kernel-modules.tar` | 当前版本模块，归档为 root 所有者 |
| `kernel-manifest.json` | 源码提交、补丁、配置摘要、编译器及镜像摘要 |
| `kernel-modules-manifest.json` | 模块文件摘要 |
| `kernel-SHA256SUMS` | 以上产物的完整性校验 |

引导程序目前只读取 8 MiB 内核数据，即使内核分区有 20 MiB，也不能构建超过 8 MiB 的 uImage。
打包器会检查长度、uImage CRC、DTB 长度和 eMMC/SD 编号，避免生成明显不可启动的包。

固定时间戳和归档元数据可减少无关差异；更换编译器或构建环境仍可能改变二进制摘要。
每次新构建都标记 `tested_boot=false`，编译通过不等于已在盒子上验证。

## 导出适配源码

完成修改后先用 `git add` 暂存要导出的公开文件，再运行 `./compile.sh source`。
导出器从 Git 索引读取内容，不会读取未暂存的私人配置；输出为
`output/ec6108v9-armbian-port-source.tar.gz` 及其 SHA-256。
包内是本仓库适配源码，完整 Linux 源码由其中的固定提交清单另行获取。
源码包解压后无需 `.git` 也可运行 `./compile.sh check` 和内核构建；再次导出才需要 Git 索引。

## 与上游 Armbian 的关系

现有用户空间使用官方 Armbian armhf Jammy 最小 rootfs 和经裁剪的 CLI BSP。
`tools/fetch-rootfs.py` 保留了原 rootfs 的固定 OCI 清单；`tools/build-bsp.py` 保留了 BSP 调整方法。
最终用户空间还经历过设备上的配置、包裁剪和导出，当前不能仅靠上述两步重建整机镜像。

本仓库尚未接入上游 `./compile.sh BOARD=ec6108v9` 的整机镜像流程，也没有声称通过其构建测试。
未来接入需要实现本机专用引导安装、分区处理和用户空间初始化，不能直接复用其他主板的刷写脚本。
目录命名参考 [Armbian 用户配置与补丁说明](https://docs.armbian.com/build-framework/user-configurations/)。
