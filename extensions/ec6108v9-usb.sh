# SPDX-License-Identifier: GPL-2.0-only

function add_host_dependencies__ec6108v9_usb() {
	EXTRA_BUILD_DEPS+=("mtools" "dosfstools")
}

function extension_prepare_config__ec6108v9_usb() {
	[[ "${BOARD}" == "ec6108v9" ]] || exit_with_error "Unsupported USB installer board" "${BOARD}"
	add_packages_to_image python3 openssh-server iw wpasupplicant exfatprogs dosfstools e2fsprogs
}

# Apply masks after the framework finishes enabling its default services.
function post_customize_image__900_ec6108v9_runtime() {
	local bsp="${SRC}/packages/bsp/ec6108v9"
	mkdir -p "${SDCARD}/etc/default" "${SDCARD}/etc/systemd/network"
	ARMBIAN_ROOT="${SDCARD}" python3 "${bsp}/fix-system-config.py"
	install -Dm755 "${bsp}/wifi-clean-shutdown.sh" "${SDCARD}/usr/lib/systemd/system-shutdown/ec6108-wifi-reset"
	install -Dm755 "${bsp}/firstboot.sh" "${SDCARD}/usr/local/sbin/ec6108v9-firstboot"
	install -Dm755 "${bsp}/verify-direct-system.py" "${SDCARD}/usr/local/sbin/ec6108-verify-system"
	cat > "${SDCARD}/etc/systemd/system/ec6108v9-firstboot.service" <<-'UNIT'
		[Unit]
		Description=Initialize EC6108V9 storage and device identity
		DefaultDependencies=no
		After=local-fs.target systemd-udev-settle.service
		Before=sysinit.target network-pre.target systemd-networkd.service ssh.service
		ConditionPathExists=!/var/lib/ec6108v9/initialized
		[Service]
		Type=oneshot
		ExecStart=/usr/local/sbin/ec6108v9-firstboot
		RemainAfterExit=yes
		TimeoutStartSec=180
		[Install]
		WantedBy=sysinit.target
	UNIT
	systemctl --root="${SDCARD}" enable ec6108v9-firstboot.service
	systemctl --root="${SDCARD}" mask armbian-resize-filesystem.service armbian-hardware-optimize.service \
		armbian-hardware-monitor.service armbian-zram-config.service armbian-ramlog.service \
		armbian-led-state.service systemd-networkd-wait-online.service
	# The early board service creates keys before ssh starts.
	printf 'OPENSSHD_REGENERATE_HOST_KEYS=false\n' > "${SDCARD}/etc/default/armbian-firstrun"
	systemctl --root="${SDCARD}" mask apt-daily.service apt-daily.timer apt-daily-upgrade.service apt-daily-upgrade.timer
	cat > "${SDCARD}/etc/systemd/system/ec6108-system-check.service" <<-'UNIT'
		[Unit]
		Description=Check EC6108V9 installed system
		After=ec6108v9-firstboot.service ssh.service
		Requires=ssh.service
		ConditionPathExists=/etc/ec6108-system.json
		[Service]
		Type=oneshot
		ExecStart=/usr/local/sbin/ec6108-verify-system
		RemainAfterExit=yes
		[Install]
		WantedBy=multi-user.target
	UNIT
	systemctl --root="${SDCARD}" enable ec6108-system-check.service
	cat > "${SDCARD}/etc/systemd/network/10-ethernet.network" <<-'NETWORK'
		[Match]
		Name=eth0
		[Network]
		DHCP=yes
		LinkLocalAddressing=yes
		IPv6AcceptRA=yes
		[DHCPv4]
		UseHostname=no
	NETWORK
	cat > "${SDCARD}/etc/systemd/network/20-wifi.network" <<-'NETWORK'
		[Match]
		Name=wlan0
		[Network]
		DHCP=yes
		LinkLocalAddressing=yes
		IPv6AcceptRA=yes
		[DHCPv4]
		UseHostname=no
	NETWORK
	printf '[Unit]\nConditionPathExists=/etc/wpa_supplicant/wpa_supplicant-wlan0.conf\n' >> "${SDCARD}/etc/systemd/system/wpa_supplicant@wlan0.service.d/10-ec6108-device.conf"
	mkdir -p "${SDCARD}/etc/systemd/journald.conf.d"
	printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=8M\n' > "${SDCARD}/etc/systemd/journald.conf.d/10-ec6108v9.conf"
	python3 - "${SRC}" "${SDCARD}" <<-'PY'
		import hashlib,json,shutil,sys
		from pathlib import Path
		source,root=map(Path,sys.argv[1:])
		manifest=json.loads((source/'config/sources/ec6108v9-firmware.json').read_text())
		for name,item in manifest['files'].items():
		    original=source/item['path']
		    assert hashlib.sha256(original.read_bytes()).hexdigest()==item['sha256']
		    target=root/('usr/share/doc/ec6108v9-firmware/'+name if name.startswith(('LICENCE','COPYING')) else 'usr/lib/firmware/'+name)
		    target.parent.mkdir(parents=True,exist_ok=True)
		    shutil.copy2(original,target)
	PY
	return 0
}

function pre_umount_final_image__ec6108v9_usb_payload() {
	local staging="${WORKDIR}/ec6108v9-usb"
	mkdir -p "${staging}"
	python3 "${SRC}/packages/bsp/ec6108v9/prepare-image.py" \
		--root "${MOUNT}" --staging "${staging}" --source-root "${SRC}" --version "${version}"
}

function post_build_image__900_ec6108v9_usb() {
	python3 "${SRC}/packages/bsp/ec6108v9/build-usb.py" \
		--image "${FINAL_IMAGE_FILE}" --staging "${WORKDIR}/ec6108v9-usb" \
		--source-root "${SRC}" --output "${DESTIMG}" --version "${version}"
	# The exporter atomically replaces the rootfs container with a FAT32 installer disk.
}
