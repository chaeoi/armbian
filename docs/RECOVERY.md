# USB 恢复入口

新增的 USB 构建流程使用芯片 USB 启动模式，可在原系统或 eMMC 引导不可用时进入烧写。
它写入匹配 mdmo1d 的引导、内核和完整 Armbian 根系统，不要求先恢复海纳思。
当前只完成本地格式、校验和烧写逻辑验证；实际 USB 启动与完整恢复还需上机确认。

| 当前状态 | 可用入口 |
| --- | --- |
| 原系统正常 | 使用同一个 USB 包，或原开发机的私有 SSH 重装包 |
| Linux 不启动 / SSH 不可用 | 主板 USB 启动短接，使用 USB 包 |
| eMMC 引导损坏 | 芯片 USB 启动入口，或 TTL + HiTool |

板级配置为 `Hi3798MV100 / mdmo1d`。同名外壳可能装入其他 PCB，不可混用其他 REG/DDR 包。
本项目没有实测当前 PCB 的短接点，不给未经确认的 J15/J16 指令。
普通双公 USB 线不能替代 FAT32 U 盘或 TTL 模块。

操作见 [安装指南](INSTALL.md)。参考 [原项目 USB 教程](https://www.ecoo.top/docs/tutorial-basics/usb-flash/)
与 [TTL 方式说明](https://ecoo.top/flashstyle.html)。

根目录的 `fastboot.bin` 是专门的芯片启动引导，不是任意分区备份改名。
`rootfs.ext4` 是对应 U-Boot 写入器支持的 Android sparse 文件，不是 gzip 归档。
不要将原网络重装包的 `rootfs.tar.gz` 直接当作 USB 根文件系统。
