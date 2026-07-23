# macOS Swift Agent

Foreground Swift CLI for the contracted Process, Network, File, DNS, and L7 metadata flow. Packet input is `/usr/sbin/tcpdump -w -`; packet bytes are parsed in memory and never written to disk or included in telemetry.

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift build
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
.build/debug/edr-macos-agent --config ./config.example.json --once --collect-seconds 5
```

Copy `config.example.json` outside the repository and set local certificate/key paths. The private key itself must remain under an ignored local secret directory.

The packaged service is a system `LaunchDaemon`, not a per-user `LaunchAgent`. It currently runs as root because the
prototype starts `tcpdump` for every collection cycle. When running as root, startup rejects a configuration file,
private key, certificate, CA certificate, or state directory that is not root-owned or has unsafe permissions. The
plist also applies umask `077`.

Install production-style files under `/Library/Application Support/EDR-C-Agent` with directory mode `700`,
configuration/private-key mode `600`, and certificate mode `644`. A separate privileged packet-capture helper and an
unprivileged main process are not implemented in this prototype; do not describe the current service as privilege
separated.
