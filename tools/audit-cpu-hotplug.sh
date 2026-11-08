#!/bin/sh
set -eu
restore() {
    for cpu in 1 2 3; do
        test "$(cat /sys/devices/system/cpu/cpu$cpu/online)" = 1 || printf '1\n' > /sys/devices/system/cpu/cpu$cpu/online
    done
}
trap restore EXIT
for cpu in 1 2 3; do
    control=/sys/devices/system/cpu/cpu$cpu/online
    test "$(cat "$control")" = 1
    printf '0\n' > "$control"
    test "$(cat "$control")" = 0
    printf '1\n' > "$control"
    test "$(cat "$control")" = 1
    printf 'CPU %s offline/online passed\n' "$cpu"
done
cat /sys/devices/system/cpu/online
cat /proc/interrupts | grep mv100-tick
