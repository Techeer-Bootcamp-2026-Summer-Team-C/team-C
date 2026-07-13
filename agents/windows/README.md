# Windows C++20 Agent

Windows x64 foreground CLI and Service entrypoint. The Service is designed for the LocalSystem portfolio profile. It does not install itself.

```powershell
cmake -S . -B build -A x64 -DNPCAP_SDK_DIR=C:\NpcapSDK
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
build\Release\edr-windows-agent.exe --config C:\ProgramData\EDR-C-Agent\config.json --once
```

`NPCAP_SDK_DIR` is optional. Without it the packet/L7 sensor reports `DEGRADED`; Toolhelp32, TCP table, ReadDirectoryChangesW, and DNS Client ETW remain enabled. The repository contains no Npcap installer, driver, SDK, or DLL.

Import the provisioned `agent.p12` into the LocalMachine certificate context or leave it at the ACL-protected configured path for the WinHTTP runtime importer. Install the development CA certificate in the trusted root store. Never place either private-key artifact in source control or logs.
