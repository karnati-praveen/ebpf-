#!/usr/bin/env bash
# Verify the installer layout and file modes before distributing it.
set -euo pipefail
package=${1:?Usage: packaging/verify-deb.sh dist/shardwise_VERSION_amd64.deb}
listing=$(dpkg-deb --contents "$package")
for name in controller nodeagent uv; do
  line=$(printf '%s\n' "$listing" | awk -v path="./opt/shardwise/bin/$name" '$NF==path {print $1}')
  [[ "$line" == '-rwxr-xr-x' ]] || { echo "Unsafe/missing binary mode: $name ($line)" >&2; exit 1; }
done
if printf '%s\n' "$listing" | awk '{print $NF}' | rg '/(mock_api\.py|__pycache__|test[^/]*)(/|$)' >/dev/null; then
  echo 'Package unexpectedly includes development mocks/tests/bytecode' >&2; exit 1
fi
printf '%s\n' "$listing" | awk '$6=="./usr/bin/shardwise" && $7=="->" && $8=="/opt/shardwise/app/demo/keinfer-demo" {found=1} END {exit !found}'
[[ $(dpkg-deb --field "$package" Package) == shardwise ]]
echo 'PASS: Shardwise package identity, launcher, executable binary modes, and exclusion of mocks/tests.'
