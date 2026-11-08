#!/bin/sh
set -eu
wait_wifi() {
    for attempt in $(seq 1 45); do
        if wpa_cli -i wlan0 status 2>/dev/null | grep -q '^wpa_state=COMPLETED$'; then
            if ip -4 -o address show dev wlan0 | grep -q 'inet '; then
                ping -I wlan0 -c 5 -W 2 192.168.10.1 && return 0
            fi
        fi
        sleep 1
    done
    return 1
}
for cycle in 1 2; do
    printf '\nWi-Fi reconnect cycle %s\n' "$cycle"
    wpa_cli -i wlan0 disconnect
    sleep 2
    wpa_cli -i wlan0 reconnect
    wait_wifi
done
printf '\nWi-Fi driver unload/reload and udev service recovery\n'
modprobe -r rtl8xxxu
sleep 2
modprobe rtl8xxxu
wait_wifi
systemctl is-active wpa_supplicant@wlan0.service ec6108-wifi-power-save-off.service
iw dev wlan0 get power_save | grep 'Power save: off'
iw dev wlan0 link
printf '\nWi-Fi reconnect and reload tests passed\n'
