# U 盘安装 Armbian

仅针对已确认的 EC6108V9 / Hi3798MV100 / mdmo1d / 1 GiB RAM / 4 GB eMMC。
当前 USB 流程通过本地格式与烧写逻辑检查，首次 GitHub Actions 构建及硬件 USB 刷入尚待验证。

## 获取产物

在 [GitHub Actions](https://github.com/chaeoi/armbian/actions/workflows/build.yml) 手动运行 USB 工作流。
成功后下载 Artifact；其中 `.usb.zip` 才是最终刷机包，适配源码 `.tar.gz` 不用于刷机。
可选的 `publish` 输入会将成功构建发布为预发布版本。

```sh
sha256sum -c Armbian-unofficial_*.usb.zip.sha256
unzip Armbian-unofficial_*.usb.zip -d /你的U盘挂载点
```

U 盘使用 FAT32，建议普通 USB 2.0 闪存盘。不要用写卡工具把这个 ZIP 当作整盘镜像烧进 U 盘。
根目录应直接看到 `fastboot.bin`、`bootargs.bin` 和 `mv100/`，不能多套一层解压目录。

## 启动与刷入

1. 关闭盒子电源，插入 U 盘，接网线到路由器 LAN。
2. 按实际 PCB 的 USB 启动短接点进入芯片 USB 启动模式，再上电。
3. USB 启动开始后放开短接。保持供电，等待写入和自动重启。
4. 正常启动后在路由器查找 DHCP 地址，用 SSH 登录。

本项目尚未实测这块主板的短接位置，不能将外壳 V9/V9C 型号当作点位证据。
原始参考见 [海纳思 USB 启动教程](https://www.ecoo.top/docs/tutorial-basics/usb-flash/)。
无需盒子原系统能启动，也无需预先 SSH 登录。不使用电脑双公 USB 线。
刷写本身不需要网络；网线用于安装完成后的首次登录。
刷写会清除内置系统数据，安装一个 Armbian；SD 和其他 USB 盘不是目标。
实际写入时间取决于 U 盘和 eMMC，不能按固定秒数断电。

首次 SSH：`root` / `1234`，按官方首次登录流程修改密码。
系统首次启动会扩展 ext4，并生成独立 SSH 主机密钥和本地 MAC。
SD 按已固定的第二个 MMC 卡槽自动挂载到 `/mnt/sdcard`，不按开发者的卡 UUID 固定。
不包含任何人的 Wi-Fi 配置；先通过有线网络进入系统，再配置无线。

## 包内布局

| 文件 | 用途 |
| --- | --- |
| 根目录 `fastboot.bin` | mdmo1d 芯片 USB 启动引导 |
| 根目录 `bootargs.bin` | 校验及烧写指令 |
| `mv100/fastboot.bin` | 写入 eMMC 的引导程序 |
| `mv100/bootargs.bin` | 安装完成后的唯一 Armbian 启动参数 |
| `mv100/kernel.bin` | uImage 与内核分区填充 |
| `mv100/rootfs.ext4` | Android sparse 格式的完整根文件系统 |
| 其余参数文件 | 匹配引导使用的板级显示参数 |
| `manifest.json` / `SHA256SUMS` | 来源、测试状态及文件校验 |

不是把旧私有 rootfs 改名分发。内核、BSP 和用户空间来自官方构建流程，SSH 身份在目标首次启动时生成。
Linux 内核与根系统只有一份，底层引导文件不构成第二套海纳思系统。

## 旧私有网络重装包

原开发机 `output/ec6108v9-armbian-r6-single/` 仍是已验证样机的私有备份，不在公开仓库内。
它包含该设备的身份与无线配置，只支持 root SSH 登录后重装；不作为新的 USB 包输入。
其入口为 `flash.sh`，仅检查使用 `python3 flash.py`。
维护工具 `tools/build-direct-release.py --private` 也仅服务于这个历史私有包。
