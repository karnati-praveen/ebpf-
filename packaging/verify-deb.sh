#!/usr/bin/env bash
# Verify the installer layout and file modes before distributing it.
set -euo pipefail
package=${1:?Usage: packaging/verify-deb.sh dist/shardwise_VERSION_amd64.deb}
listing=$(dpkg-deb --contents "$package")
for name in controller nodeagent uv; do
  line=$(printf '%s\n' "$listing" | awk -v path="./opt/shardwise/bin/$name" '$NF==path {print $1}')
  [[ "$line" == '-rwxr-xr-x' ]] || { echo "Unsafe/missing binary mode: $name ($line)" >&2; exit 1; }
done
if printf '%s\n' "$listing" | awk '$NF ~ /\/(mock_api\.py|__pycache__|test[^/]*)(\/|$)/ {found=1} END {exit !found}'; then
  echo 'Package unexpectedly includes development mocks/tests/bytecode' >&2; exit 1
fi
printf '%s\n' "$listing" | awk '$6=="./usr/bin/shardwise" && $7=="->" && $8=="/opt/shardwise/app/demo/shardwise" {found=1} END {exit !found}'
[[ $(dpkg-deb --field "$package" Package) == shardwise ]]
checksum="$package.sha256"
[[ -f "$checksum" ]] || { echo 'Missing distributable checksum' >&2; exit 1; }
expected_name=$(basename -- "$package")
checksum_name=$(awk 'NR==1 {print $2}' "$checksum")
[[ "$checksum_name" == "$expected_name" ]] || { echo 'Checksum must contain the portable package basename' >&2; exit 1; }
(cd -- "$(dirname -- "$package")" && sha256sum --check --status "$expected_name.sha256")
echo 'PASS: Shardwise identity, launcher, safe binary modes, development exclusions, and portable checksum.' 
