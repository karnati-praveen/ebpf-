#!/usr/bin/env bash
set -euo pipefail
umask 022
version=${1:-0.1.0}
[[ "$version" =~ ^[0-9][a-zA-Z0-9.+~-]*$ ]] || { echo 'Invalid package version' >&2; exit 2; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $(uname -m) == x86_64 ]] || { echo 'Build on Linux x86_64' >&2; exit 1; }
for tool in go curl sha256sum tar dpkg-deb; do command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }; done
# Fail before producing an incomplete package while backend work is in progress.
for file in demo/shardwise demo/app.py demo/hwdetect.py demo/helper.py demo/app.html demo/runtime-setup.sh; do [[ -f "$root/$file" ]] || { echo "Missing $file; integrate backend branch before packaging." >&2; exit 1; }; done
stage=$(mktemp -d);trap 'rm -rf "$stage"' EXIT
pkg="$stage/package";dest="$pkg/opt/shardwise"
mkdir -p "$dest/bin" "$dest/app" "$pkg/DEBIAN" "$pkg/usr/bin" "$pkg/usr/share/applications" "$pkg/usr/share/icons/hicolor/scalable/apps" "$root/dist"
cd "$root"
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o "$dest/bin/controller" ./cmd/controller
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o "$dest/bin/nodeagent" ./cmd/nodeagent
uv_version=0.10.8
uv_sha=f0c566b55683395a62fefb9261a060fa09824914b5682c3b9629fa154762ae2f
curl --fail --location --retry 3 --proto '=https' -o "$stage/uv.tar.gz" "https://github.com/astral-sh/uv/releases/download/$uv_version/uv-x86_64-unknown-linux-gnu.tar.gz"
printf '%s  %s\n' "$uv_sha" "$stage/uv.tar.gz" | sha256sum --check --status
tar -xzf "$stage/uv.tar.gz" -C "$stage" uv-x86_64-unknown-linux-gnu/uv
install -m755 "$stage/uv-x86_64-unknown-linux-gnu/uv" "$dest/bin/uv"
# Go may restore cached executable modes; enforce non-writable executable binaries.
chmod 755 "$dest/bin/controller" "$dest/bin/nodeagent" "$dest/bin/uv"
# Archive filters avoid test, mock, bytecode, and developer artifact leakage.
tar -cf - --exclude='__pycache__' --exclude='*.pyc' --exclude='mock_api.py' --exclude='test*' --exclude='*.log' demo worker deploy/standalone bench/profile_qwen3.py | tar -xf - -C "$dest/app"
find "$dest/app" -type f -perm /111 -exec chmod 755 {} +
find "$dest/app" -type f ! -perm /111 -exec chmod 644 {} +
chmod 755 "$dest/app/demo/shardwise" "$dest/app/demo/runtime-setup.sh"
ln -s /opt/shardwise/app/demo/shardwise "$pkg/usr/bin/shardwise"
ln -s shardwise "$pkg/usr/bin/keinfer-demo"
install -m644 packaging/shardwise.desktop "$pkg/usr/share/applications/shardwise.desktop"
install -m644 packaging/shardwise.svg "$pkg/usr/share/icons/hicolor/scalable/apps/shardwise.svg"
cat > "$pkg/DEBIAN/control" <<EOF
Package: shardwise
Version: $version
Section: science
Priority: optional
Architecture: amd64
Maintainer: Shardwise contributors <shardwise@localhost>
Depends: iproute2, curl, ca-certificates, xdg-utils
Recommends: stress-ng
Installed-Size: $(du -sk "$dest" | cut -f1)
Description: Local CPU and NVIDIA distributed inference demonstration
 Runs a small language model split across one or more trusted laptops.
 Downloads a managed Python runtime and model on first launch.
EOF
cat > "$pkg/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
printf '%s\n' 'Run shardwise to finish setup (downloads ~1–3 GB once; CUDA may require more).'
EOF
cat > "$pkg/DEBIAN/prerm" <<'EOF'
#!/bin/sh
# Package scripts run as root; never target another user's state.
/opt/shardwise/app/demo/shardwise stop || true
EOF
chmod 755 "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/prerm"
find "$pkg" -type d -exec chmod 755 {} +
dpkg-deb --build --root-owner-group "$pkg" "$root/dist/shardwise_${version}_amd64.deb"
(cd "$root/dist" && sha256sum "shardwise_${version}_amd64.deb" > "shardwise_${version}_amd64.deb.sha256")
du -h "$root/dist/shardwise_${version}_amd64.deb"
