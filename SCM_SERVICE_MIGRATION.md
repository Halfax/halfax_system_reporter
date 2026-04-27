# SCM Service Migration Guide

## Overview

This guide converts your driver from PnP/INF-based installation to **Service Control Manager (SCM)** installation - the standard approach used by all hardware telemetry tools like CPU-Z, HWiNFO, ThrottleStop, etc.

## Why SCM Instead of PnP?

Your driver provides **system-wide hardware access (MSR/PCI/SMBus)**, not device-specific functionality. It should be a kernel service, not a PnP device driver.

**Industry Standard:**
- ✅ CPU-Z - SCM service
- ✅ HWiNFO - SCM service  
- ✅ ThrottleStop - SCM service
- ✅ OpenHardwareMonitor - SCM service
- ✅ AMD Ryzen Master - SCM service
- ✅ Intel XTU - SCM service

**Your current approach (PnP/INF)** is designed for hardware that gets plugged in, not system services.

---

## PHASE 1: Clean Up Current Environment

### 1. Remove PnP/INF-based installs

```powershell
# List installed driver packages
pnputil /enum-drivers

# Find your driver (look for "halfax" or "oem249.inf" from earlier install)
# Remove it:
pnputil /delete-driver oem249.inf /uninstall /force
```

### 2. Delete leftover services (if any)

```powershell
sc delete HalfaxTelemetry
```

If it says "service does not exist", that's expected and fine.

---

## PHASE 2: Verify Driver Code

### 3. Ensure driver creates device object

Your `DriverEntry` in [halfax_telemetry_driver.c](halfax_telemetry_driver.c) should create:

```c
// Device name: \Device\HalfaxTelemetry
IoCreateDevice(
    DriverObject,
    0,
    &deviceName,
    FILE_DEVICE_UNKNOWN,
    0,
    FALSE,
    &deviceObject
);

// Symbolic link: \DosDevices\HalfaxTelemetry or \\.\HalfaxTelemetry
IoCreateSymbolicLink(&dosDeviceName, &deviceName);
```

This exposes the IOCTL interface for your broker to communicate.

### 4. Confirm driver is signed

You already have:
- ✅ `halfax_telemetry_driver.sys` (signed)
- ✅ Test certificate in Trusted Root
- ✅ Test-signing enabled

---

## PHASE 3: Deploy as SCM Service (The CPUID/HWiNFO Way)

### 5. Copy driver to System32\drivers

**Run as Administrator:**

```powershell
Copy-Item "C:\Users\arhal_iz5093n\Desktop\projects\somethingfun\driver_package\halfax_telemetry_driver.sys" `
          "C:\Windows\System32\drivers\"
```

### 6. Create the SCM kernel service

**This is the key step - how all telemetry tools install:**

```powershell
sc create HalfaxTelemetry type= kernel start= demand binPath= "C:\Windows\System32\drivers\halfax_telemetry_driver.sys"
```

**Important:** Note the spaces after `type=` and `start=` - this is required by sc.exe syntax.

**Parameters explained:**
- `type= kernel` - Kernel-mode driver
- `start= demand` - Loads on-demand when broker opens handle (like CPU-Z)
- `binPath=` - Full path to .sys file in drivers folder

### 7. Start the driver

```powershell
sc start HalfaxTelemetry
```

**Expected output:**
```
SERVICE_NAME: HalfaxTelemetry
        TYPE               : 1  KERNEL_DRIVER
        STATE              : 4  RUNNING
```

**If it fails**, you'll get an error code. Common ones:
- `1275` - Driver blocked by policy (need to check test-signing)
- `577` - Signature invalid (cert issue)
- `2` - File not found (wrong path)

---

## PHASE 4: Verify Driver Works

### 8. Check device object exists

The broker should be able to open:

```
\\.\HalfaxTelemetry
```

If `CreateFile()` succeeds, the driver is alive and reachable.

### 9. Test with broker

```powershell
# Check driver responds
halfax_kernel_broker.exe --version

# Try reading an MSR
halfax_kernel_broker.exe --read-msr 0 0x19C
```

---

## PHASE 5: Update Documentation

### 10. Update DRIVER_README.md

Replace the INF-based installation section with SCM installation:

**New Installation Section:**
```markdown
### Install the Driver (SCM Service Method)

1. Copy driver to System32:
   ```powershell
   Copy-Item driver_package\halfax_telemetry_driver.sys C:\Windows\System32\drivers\
   ```

2. Create kernel service:
   ```powershell
   sc create HalfaxTelemetry type= kernel start= demand binPath= "C:\Windows\System32\drivers\halfax_telemetry_driver.sys"
   ```

3. Start service:
   ```powershell
   sc start HalfaxTelemetry
   ```

4. Verify:
   ```powershell
   sc query HalfaxTelemetry
   ```
```

---

## PHASE 6: Optional - Remove INF

Since you're using SCM, the INF is no longer needed for installation.

**You can:**
- Delete `halfax_telemetry.inf` entirely
- Or keep it only for reference/catalog generation during signing

Most hardware telemetry tools ship **no INF at all**.

---

## Comparison: PnP vs SCM

| Aspect | PnP/INF (Old) | SCM Service (New) |
|--------|---------------|-------------------|
| Installation | `pnputil /add-driver` | `sc create` |
| Device enumeration | Waits for Root device | No enumeration needed |
| Loading | On device plug | On-demand or boot |
| Uninstall | `pnputil /delete-driver` | `sc delete` |
| Used by | Device drivers | System services |
| Examples | USB drivers, GPU drivers | CPU-Z, HWiNFO, telemetry tools |

---

## Next Steps

1. ✅ Clean up PnP install (Phase 1)
2. ✅ Verify driver code has IoCreateDevice (Phase 2)
3. ✅ Deploy via SCM (Phase 3)
4. ✅ Test with broker (Phase 4)
5. ✅ Update docs (Phase 5)

This gets you to the same architecture as **every professional hardware telemetry tool**.

---

## Troubleshooting

**Service won't start:**
- Check `sc query HalfaxTelemetry` for error code
- Check Event Viewer → Windows Logs → System for driver errors
- Verify test-signing enabled: `bcdedit /enum | findstr testsigning`

**Broker can't open device:**
- Verify service is running: `sc query HalfaxTelemetry`
- Check device name in driver matches broker: `\\.\HalfaxTelemetry`
- Ensure broker runs as Administrator

**"Driver blocked" error:**
- Verify Secure Boot disabled
- Verify certificate in Trusted Root
- Check driver signature: `signtool verify /pa C:\Windows\System32\drivers\halfax_telemetry_driver.sys`
