#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu"
cd "$(dirname "$0")/traces"
for t in 603.bwaves_s-3699B 605.mcf_s-665B 625.x264_s-18B 654.roms_s-842B 657.xz_s-3167B 600.perlbench_s-210B 602.gcc_s-734B 607.cactuBSSN_s-2421B 621.wrf_s-575B 631.deepsjeng_s-928B; do
  f="${t}.champsimtrace.xz"; [ -f "$f" ] && echo "Exists: $f" || { echo "Downloading $f..."; curl -sSL -o "$f" "${BASE_URL}/${f}" || wget -q -O "$f" "${BASE_URL}/${f}"; }
done
sha256sum -c ../checksums.txt 2>/dev/null && echo "Checksums OK" || echo "Checksums not verified"
