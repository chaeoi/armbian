#!/bin/sh
# rtl8xxxu has no USB shutdown callback: unload it while USB control I/O works.
# A clean disconnect runs the chip's existing power-off/reset sequence.
case "${1:-}" in
    reboot|poweroff|halt|kexec)
        /usr/bin/timeout 10 /sbin/modprobe -r rtl8xxxu 2>/dev/null || true
        ;;
esac
