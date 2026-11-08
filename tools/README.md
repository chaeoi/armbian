# 工具分类

`./compile.sh help` 是主机构建入口。构建不访问盒子，不运行下面的设备测试和刷写程序。

完整系统通过官方框架与 `extensions/ec6108v9-usb.sh` 构建。
USB 导出、首次启动和稀疏格式工具位于 `packages/bsp/ec6108v9/`。
原独立内核流程的入口改为 `compile.sh kernel-local`。

| 类别 | 文件 | 运行位置与作用 |
| --- | --- | --- |
| 官方框架 | `armbian-build.py` | 主机；获取固定框架并安装板级扩展，`compile.sh build/kernel` 使用此入口 |
| USB 校验 | `verify-usb.py` | 主机；检查 `.img.xz` 的分区、FAT32、环境变量、摘要和稀疏镜像，不访问设备 |
| 构建 | `fetch-kernel.py`, `build-kernel.py`, `package-kernel.py`, `package-modules.py` | 主机；只处理源码和构建目录 |
| 检查与导出 | `check-repo.py`, `export-port.py`, `port.py`, `uimage.py` | 主机；源码检查及公开适配包 |
| 用户空间来源 | `fetch-rootfs.py`, `build-bsp.py`, `prepare-wifi-firmware.py` | 主机；保留原固定 rootfs/BSP 来源和固件准备方法，非完整整机镜像流程 |
| 私有包 | `build-direct-release.py` | 主机；显式 `--private` 组装已有私有 rootfs，包含设备身份 |
| 网络安装 | `flash-direct.py` | 复制为私有包中的 `flash.py`；默认只读检查，`--flash` 写 eMMC |
| RAM 安装 | `prepare-direct-install.py`, `ec6108-ram-init.sh`, `install-direct-in-ram.py` | 由安装器在目标盒子上运行；修改引导或文件系统 |
| 系统校验 | `verify-direct-system.py` | 目标盒子；只读校验固化状态 |
| Wi-Fi 运行时 | `wifi-clean-shutdown.sh`, `wifi-refresh-networkd.py`, `fix-system-config.py` | 目标盒子或指定 rootfs；安装和执行兼容性配置 |
| SD 挂载 | `configure-sd-automount.py` | 目标盒子；按显式 UUID 配置现有 exFAT，不格式化 |
| 私有连接 | `box.py`, `copy-active-wifi.py` | 主机；读取忽略目录中的连接信息，后者读取并复制当前主机的无线配置 |
| 设备诊断 | `audit-*`, `collect-box-info.sh`, `check-storage.py` | 盒子，部分由主机 SSH 调用；可能改变接口或控制器状态 |
| 存储测试 | `benchmark-sd.py`, `probe-sd-*.py`, `test-sd-*.py`, `test-usb-read.py` | 盒子；部分写测试文件或原始扇区，不应批量执行 |

诊断和硬件测试脚本保存了当时样机的路径、地址或介质约束，不是适用于所有用户的自动测试套件。
运行前逐个阅读其参数与目标；CI 只运行 `tests/` 中的主机单元测试。
旧 RAM 入口在当前三分区直接根上的本次试验未恢复网络，安装器已在写入启动区前拒绝此路径。
该保护不影响新的官方框架 USB 安装盘。
早期双系统和试启动脚本已从活跃工具集移出，在原开发机 `work/legacy-tools-20261108/` 留存，
相关历史方案见 `docs/history/`。
