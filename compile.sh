#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PYTHONDONTWRITEBYTECODE=1
case "${1:-help}" in
    build|BOARD=*|kernel|config-dump-json|artifact-config-dump-json)
        exec python3 tools/armbian-build.py "$@"
        ;;
    prepare-framework) exec python3 tools/armbian-build.py --prepare-only ;;
    check)
        python3 tools/check-repo.py
        python3 -m unittest discover -s tests -v
        ;;
    fetch) python3 tools/fetch-kernel.py ;;
    prepare) python3 tools/build-kernel.py prepare ;;
    configure) python3 tools/build-kernel.py configure ;;
    kernel-local)
        python3 tools/fetch-kernel.py
        python3 tools/build-kernel.py configure
        python3 tools/build-kernel.py build
        python3 tools/build-kernel.py modules-install
        python3 tools/package-kernel.py
        python3 tools/package-modules.py
        ;;
    source) python3 tools/export-port.py ;;
    help|--help|-h)
        cat <<'HELP'
EC6108V9 Armbian community adaptation

  ./compile.sh build BOARD=ec6108v9 BRANCH=edge RELEASE=jammy BUILD_MINIMAL=yes
                          Build the USB installer .img.xz with the official framework
  ./compile.sh prepare-framework
                          Fetch the pinned framework and install the board overlay
  ./compile.sh check       Check sources, documentation and host-tool tests (offline)
  ./compile.sh fetch       Fetch the checksum-pinned Linux source
  ./compile.sh prepare     Apply and verify patches and the board DTS
  ./compile.sh configure   Prepare the kernel configuration
  ./compile.sh kernel      Build native Armbian kernel packages
  ./compile.sh kernel-local
                          Build the original standalone r6 kernel and modules
  ./compile.sh source      Export public adaptation sources from the Git index

Host: Linux, Python >= 3.12; kernel dependencies: see docs/BUILD.md.
Overrides: CROSS_COMPILE, HOSTCC, JOBS, EC6108_{SOURCE,BUILD,OUTPUT}_DIR.
These commands build on the host. They do not connect to or flash the box.
HELP
        ;;
    *) printf 'Unknown command: %s\nUse ./compile.sh help\n' "$1" >&2; exit 2 ;;
esac
