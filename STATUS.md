# Halfax Telemetry - Current Status

> **Engineering Roadmap:**
> 
> All actionable engineering tasks, phase goals, and cross-cutting requirements are tracked in [ACTIONABLE_TODO_CHECKLIST.md](ACTIONABLE_TODO_CHECKLIST.md). This file is for operational and deployment status only.

**Last Updated:** January 24, 2026

## ✅ System Status: OPERATIONAL

All components are built, deployed, and running successfully.

## Configuration

| Component | Value |
|-----------|-------|
| **Driver Architecture** | WDM Control Device |
| **Service Name** | HalfaxTelemetry |
| **Service Status** | RUNNING |
| **Device Path** | `\\.\HalfaxTelemetry` |
| **Driver Location** | `C:\Windows\System32\drivers\halfax_telemetry_driver.sys` |
| **Broker** | `halfax_kernel_broker.exe` (in project directory) |
| **Deployment Method** | `python deploy_driver.py` |

## Quick Commands

### Check Service Status
```powershell
sc.exe query HalfaxTelemetry
```

### Test Driver Communication
```powershell
.\halfax_kernel_broker.exe --version
.\halfax_kernel_broker.exe --capabilities
```

### Read MSR (example)
```powershell
.\halfax_kernel_broker.exe --read-msr 0 0xCE
```

### Run Python Integration
```powershell
python main_integration_example.py
```

### Rebuild and Redeploy
```powershell
python deploy_driver.py
```

## Architecture Summary

```
┌──────────────────────────────────────┐
│   main.py (GUI)                      │
│   cli_reporter.py (Headless CLI)     │ Python components
└──────────────────────┬───────────────┘
                       │
      ┌────────────────┼────────────────┐
      │                │                │
      v                v                v
   Helpers      Privileged Ops      System APIs
  (x86/arm)     (sudo -n / sudo -S)  (WMI, sysfs)
      │                │                │
      ├─→ cpuid_helper.exe            │
      ├─→ spd_helper.exe              │
      ├─→ nvme_helper.exe             │
      ├─→ edid_helper.exe             │
      │                │                │
      │         ┌──────v────────┐      │
      │         │ sudo -n (non- │      │
      │         │ interactive)  │      │
      │         └───────┬───────┘      │
      │                 │              │
      │         ┌───────v────────┐    │
      │         │ dmidecode,     │    │
      │         │ other root     │    │
      │         │ commands       │    │
      │         └────────────────┘    │
      │                               │
      └───────────────┬───────────────┘
                      │
                      └─→ Kernel Driver (optional, Windows only)
                          halfax_kernel_broker.exe → IOCTL
```

### CLI Modes (April 2026 Update)

- **Non-Interactive (Default)**: Uses `sudo -n` for automated/CI/headless environments. Gracefully degrades with notifications if sudo unavailable.
- **Interactive (`--interactive` flag)**: Prompts for sudo password if non-interactive fails. Suitable for manual system analysis.
- **Failure Notifications**: Both modes report uncollected items with clear reasons in text and JSON output.


## Recent Changes (Jan 24, 2026)

1. **Driver converted from KMDF to WDM** - Control device architecture eliminates PnP dependencies
2. **Service renamed** - From `halfax_telemetry` back to original `HalfaxTelemetry`
3. **Device name restored** - From temporary `HalfaxTelemetry2` back to `HalfaxTelemetry`
4. **Automated deployment** - Created `deploy_driver.py` for full build/deploy/test workflow
5. **Documentation updated** - All references to old BAT files replaced with Python script
6. **BAT files removed** - Old build scripts deleted, Python-based deployment only

### Session Update (2026-02-03)

- **Router Scan tab added**: A read-only Router Scan feature was added to the Network area to perform UPnP/SSDP discovery with user confirmation. Discovery uses the optional `miniupnpc` library when present; otherwise the UI notes the missing dependency.
- **Text Report canonicalization**: The Text Report aggregation was corrected to remove duplicated decorative headers and produce a single exportable report.
- **Storage rendering fix**: Storage tab now shows WMI-detected devices as a fallback when `nvme_helper` returns no devices; partition→physical-device mapping heuristics were improved.
- **Runtime guards**: Added platform flags and import guards for optional features (WMI, miniupnpc) to prevent startup crashes.

## Next Steps

- [ ] Extend driver with real PCI config space access (currently stubbed)
- [ ] Implement SMBus access for sensors (currently stubbed)
- [ ] Add MSR write whitelist for safe write operations
- [ ] Test on different hardware configurations
- [ ] Consider WHQL signing for production deployment

## Troubleshooting

### Service won't start
Check Event Viewer:
```powershell
Get-WinEvent -LogName System -MaxEvents 20 | Where-Object { $_.Message -like '*halfax*' } | Format-List
```

### Broker can't connect
Verify service is running:
```powershell
sc.exe query HalfaxTelemetry
```

### Rebuild after code changes
```powershell
python deploy_driver.py
```

The script handles stopping the old service, rebuilding, deploying, and restarting automatically.

## Security Notes

- Driver requires Administrator privileges
- SDDL restricts device access to Administrators only
- Test signing enabled (bcdedit /set testsigning on)
- Driver is signed with WDKTestCert
- Not suitable for production without proper code signing certificate

## Support

For driver development documentation, see:
- [DRIVER_README.md](DRIVER_README.md) - Complete driver documentation
- [REBUILD_DRIVER.md](REBUILD_DRIVER.md) - Build and deployment instructions
- [ENHANCEMENTS.md](ENHANCEMENTS.md) - Planned features and enhancements
- [WDM_CONVERSION_PLAN.md](WDM_CONVERSION_PLAN.md) - Technical details of KMDF→WDM conversion
