# mdmo1d boot assets

These unmodified board boot assets come from the HiNAS USB installer:
https://node4.histb.com:9088/update/system/mv100-mdmo1d-usb-flash.zip

Archive and file digests are recorded in `config/sources/usb-bootstrap.json`.
The source ZIP contains no separate license file. These third-party binaries are not relicensed under this repository's GPL notice.
The underlying HiSilicon SDK and U-Boot sources are available at https://github.com/JasonFreeLab/HiSTBLinuxV100R005C00SPC060.
This repository does not claim to rebuild the modified HiNAS bootloader from that SDK.

Only the board loader and display parameters are retained. No HiNAS Linux kernel or root filesystem is included.
