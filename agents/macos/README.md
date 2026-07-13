# macOS Swift Agent

Foreground Swift CLI for the contracted Process, Network, File, DNS, and L7 metadata flow. Packet input is `/usr/sbin/tcpdump -w -`; packet bytes are parsed in memory and never written to disk or included in telemetry.

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift build
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
.build/debug/edr-macos-agent --config ./config.example.json --once --collect-seconds 5
```

Copy `config.example.json` outside the repository and set local certificate/key paths. The private key itself must remain under an ignored local secret directory.
