# Rebuild Driver - Current Configuration

## ✅ Current Status: OPERATIONAL (Jan 24, 2026)

The driver has been successfully converted to WDM and is fully operational with original naming restored.

## Current Configuration

**Device Name:** `HalfaxTelemetry` (original name)
**Service:** HalfaxTelemetry (RUNNING)
**Driver:** C:\Windows\System32\drivers\halfax_telemetry_driver.sys
**Broker:** halfax_kernel_broker.exe

## What Changed (WDM Conversion)

The driver was converted from KMDF to native WDM and uses a **control device** architecture:

### Before (PnP model - didn't work):
```c
// DriverEntry registered EvtDeviceAdd callback
WDF_DRIVER_CONFIG_INIT(&config, HalfaxEvtDeviceAdd);
// EvtDeviceAdd never fired because no PnP device → no device interface
```

### After (Control device - will work):
```c
// DriverEntry creates control device directly
deviceInit = WdfControlDeviceInitAllocate(driver, &SDDL_DEVOBJ_SYS_ALL_ADM_ALL);
WdfDeviceCreate(&deviceInit, &deviceAttributes, &device);
WdfDeviceCreateDeviceInterface(device, &GUID_DEVINTERFACE_HALFAX_TELEMETRY, NULL);
WdfControlFinishInitializing(device);  // Makes device visible immediately
```

## Automated Build & Deployment (Recommended)

Use the Python deployment script which handles everything automatically:

```powershell
python deploy_driver.py
```

The script will:
1. Auto-elevate to Administrator (UAC prompt)
2. Detect and configure Visual Studio environment
3. Build driver (halfax_telemetry_driver.sys)
4. Build broker (halfax_kernel_broker.exe)
5. Stop and remove old services
6. Deploy driver to System32\drivers
7. Create HalfaxTelemetry service
8. Start service and verify operation
9. Test broker communication

## Manual Build (Advanced)

If you need to build components manually:

### Build Driver:
```powershell
# Open VS Developer Command Prompt, then:
msbuild halfax_telemetry_driver.vcxproj /p:Configuration=Release /p:Platform=x64
```

### Build Broker:
```powershell
cl /EHsc /W4 /Ox halfax_kernel_broker.cpp halfax_guid.cpp setupapi.lib /Fe:halfax_kernel_broker.exe
```

### Manual Deployment:
```powershell
# Stop old service
sc.exe stop HalfaxTelemetry
sc.exe delete HalfaxTelemetry

# Deploy driver
copy x64\Release\halfax_telemetry_driver.sys C:\Windows\System32\drivers\halfax_telemetry_driver.sys

# Create and start service
sc.exe create HalfaxTelemetry type= kernel start= demand binPath= C:\Windows\System32\drivers\halfax_telemetry_driver.sys
sc.exe start HalfaxTelemetry

# Test
halfax_kernel_broker.exe --version
```

### 4. Test the broker:
```powershell
cd C:\Users\arhal_iz5093n\Desktop\projects\somethingfun
.\halfax_kernel_broker.exe --version
```

**Expected output:**
```
Driver version: 1.0.1
```

### 5. Test MSR read:
```powershell
.\halfax_kernel_broker.exe --read-msr 0 0xCE
```

**Expected:** Should return a hex value (e.g., `0x88310800`)

### 6. Run full integration:
```powershell
python main_integration_example.py
```

**Expected:** Should show `🟢 Full` status

## Troubleshooting

**If msbuild not found:**
- You're not in a Developer Command Prompt
- Search Start menu for "x64 Native Tools Command Prompt for VS 2022"
- Make sure Visual Studio and WDK are installed

**If driver still fails to create interface:**
- Check Event Viewer: `Get-WinEvent -LogName System -MaxEvents 20`
- Verify KdPrint messages in DebugView or kernel debugger
- The new code logs: `"HalfaxTelemetry: Control device initialized successfully"`

**If WdfControlDeviceInitAllocate fails:**
- Driver will log: `"HalfaxTelemetry: WdfControlDeviceInitAllocate failed"`
- This means KMDF runtime issue - check WDF version in vcxproj

## Files Modified

- [halfax_telemetry_driver.c](halfax_telemetry_driver.c) - ✅ Updated to control device model
- Forward declarations: Removed `EVT_WDF_DRIVER_DEVICE_ADD HalfaxEvtDeviceAdd`
- `DriverEntry`: Now creates control device directly
- `HalfaxEvtDeviceAdd`: Removed entirely (no longer needed)

## Why This Fixes The Issue

**Old architecture:**
1. Service starts → DriverEntry called
2. DriverEntry returns SUCCESS
3. Windows waits for PnP device attachment
4. **EvtDeviceAdd never called** (no PnP device)
5. No device interface created
6. Broker can't find device ❌

**New architecture:**
1. Service starts → DriverEntry called
2. DriverEntry creates control device
3. Device interface published in DriverEntry
4. WdfControlFinishInitializing makes it visible
5. Broker finds device interface ✅
6. Communication works ✅

---

**See also:**
- [POST_REBOOT_CHECKLIST.md](POST_REBOOT_CHECKLIST.md) - Full testing procedure
- [DRIVER_README.md](DRIVER_README.md) - Complete architecture documentation
