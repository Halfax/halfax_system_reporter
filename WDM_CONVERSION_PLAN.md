# WDM Driver Conversion Plan

## Status: ✅ COMPLETED & OPERATIONAL (Jan 24, 2026 7:15 PM)

The KMDF to WDM conversion has been successfully completed and the driver is fully operational.

---

## Conversion Summary

**Reason for Conversion:**
- KMDF driver failed to load with "Incorrect function" (ERROR 1)
- 4+ hours of troubleshooting (signatures, catalogs, KMDF versions, exports)
- Root cause: KMDF framework binding incompatibility on this system
- Decision: Convert to WDM for reliability and simpler architecture

**Key Changes Completed:**
1. ✅ vcxproj: DriverType KMDF → WDM
2. ✅ Headers: Removed `<wdf.h>`, using only `<ntddk.h>` and `<ntstrsafe.h>`
3. ✅ DriverEntry: IoCreateDevice + IoCreateSymbolicLink (no WdfDriverCreate)
4. ✅ Dispatch routines: HalfaxDispatchCreate, Close, DeviceControl, Unload
5. ✅ IOCTL handler: Converted from WDFREQUEST to IRP/SystemBuffer
6. ✅ Device extension: Replaced WDF device context with DEVICE_EXTENSION struct
7. ✅ Buffer access: METHOD_BUFFERED with direct systemBuffer casts
8. ✅ Completion: IoCompleteRequest instead of WdfRequestCompleteWithInformation

**Build Output:**
- Driver: `x64\Release\halfax_telemetry_driver.sys` (signed)
- Catalog: `x64\Release\halfax_telemetry_driver\halfaxtelemetry.cat` (signed)
- Both files deployed to System32

**Final Configuration:**
- Device name: `HalfaxTelemetry2` (workaround for stuck symbolic link)
- Service: halfax_telemetry (RUNNING)
- Broker: Updated with symbolic link fallback
- Status: Fully operational, all tests passing

**Test Results:**
- ✅ Driver loads successfully (STATE: 4 RUNNING)
- ✅ Broker communication working
- ✅ All IOCTLs functional (version, capabilities, MSR reads)
- ✅ Python integration operational (temps, power, energy, turbo)
- ✅ 24 cores detected and monitored

---

## Original Conversion Plan (For Reference)

## Phase 1: Project Configuration Changes

### 1.1 Update vcxproj
**File:** `halfax_telemetry_driver.vcxproj`

**Changes:**
```xml
<!-- Change DriverType from KMDF to WDM -->
<DriverType>WDM</DriverType>

<!-- Remove KMDF version settings -->
<!-- DELETE these lines: -->
<!-- <KmdfVersionMajor>1</KmdfVersionMajor> -->
<!-- <KmdfVersionMinor>35</KmdfVersionMinor> -->
```

**Impact:** Build will no longer link WDF libraries

---

## Phase 2: Header File Changes

### 2.1 Update Includes
**File:** `halfax_telemetry_driver.c`

**Remove KMDF headers:**
```c
// REMOVE:
#include <wdf.h>
```

**Add WDM headers:**
```c
// ADD:
#include <ntddk.h>      // Already present
#include <ntstrsafe.h>  // Already present  
// No additional headers needed
```

### 2.2 Remove WDF-Specific Declarations
**Remove:**
```c
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL HalfaxEvtIoDeviceControl;
WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(DEVICE_CONTEXT, DeviceGetContext)
```

**Add WDM equivalents:**
```c
// Forward declarations
DRIVER_INITIALIZE DriverEntry;
DRIVER_UNLOAD HalfaxUnload;
DRIVER_DISPATCH HalfaxDispatchDeviceControl;
DRIVER_DISPATCH HalfaxDispatchCreate;
DRIVER_DISPATCH HalfaxDispatchClose;

// Device extension (replaces WDF context)
typedef struct _DEVICE_EXTENSION {
    PDEVICE_OBJECT DeviceObject;
    UNICODE_STRING DeviceName;
    UNICODE_STRING SymbolicLinkName;
} DEVICE_EXTENSION, *PDEVICE_EXTENSION;
```

---

## Phase 3: DriverEntry Conversion

### 3.1 Function Signature
**Current (KMDF):**
```c
NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
```

**WDM (Same - no change needed):**
```c
NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
```

### 3.2 Replace WDF Initialization
**Remove all WDF calls:**
- `WDF_DRIVER_CONFIG_INIT`
- `WdfDriverCreate`
- `WdfControlDeviceInitAllocate`
- `WdfDeviceInitSetDeviceType`
- `WdfDeviceInitSetIoType`
- `WdfDeviceCreate`
- `WdfIoQueueCreate`
- `WdfDeviceCreateDeviceInterface`
- `WdfControlFinishInitializing`

**Replace with WDM device creation:**
```c
NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    NTSTATUS status;
    PDEVICE_OBJECT deviceObject = NULL;
    PDEVICE_EXTENSION deviceExtension;
    UNICODE_STRING deviceName;
    UNICODE_STRING symbolicLink;

    UNREFERENCED_PARAMETER(RegistryPath);

    KdPrint(("HalfaxTelemetry: ============================================\n"));
    KdPrint(("HalfaxTelemetry: DriverEntry START - WDM Version\n"));
    KdPrint(("HalfaxTelemetry: ============================================\n"));

    // Set up dispatch routines
    DriverObject->MajorFunction[IRP_MJ_CREATE] = HalfaxDispatchCreate;
    DriverObject->MajorFunction[IRP_MJ_CLOSE] = HalfaxDispatchClose;
    DriverObject->MajorFunction[IRP_MJ_DEVICE_CONTROL] = HalfaxDispatchDeviceControl;
    DriverObject->DriverUnload = HalfaxUnload;

    // Define device name and symbolic link
    RtlInitUnicodeString(&deviceName, L"\\Device\\HalfaxTelemetry");
    RtlInitUnicodeString(&symbolicLink, L"\\DosDevices\\HalfaxTelemetry");

    // Create device object
    status = IoCreateDevice(
        DriverObject,
        sizeof(DEVICE_EXTENSION),
        &deviceName,
        FILE_DEVICE_HALFAX,
        FILE_DEVICE_SECURE_OPEN,
        FALSE,
        &deviceObject
    );

    if (!NT_SUCCESS(status)) {
        KdPrint(("HalfaxTelemetry: IoCreateDevice failed: 0x%08X\n", status));
        return status;
    }

    KdPrint(("HalfaxTelemetry: Device created successfully\n"));

    // Initialize device extension
    deviceExtension = (PDEVICE_EXTENSION)deviceObject->DeviceExtension;
    deviceExtension->DeviceObject = deviceObject;
    deviceExtension->DeviceName = deviceName;
    deviceExtension->SymbolicLinkName = symbolicLink;

    // Set device flags
    deviceObject->Flags |= DO_BUFFERED_IO;
    deviceObject->Flags &= ~DO_DEVICE_INITIALIZING;

    // Create symbolic link for user-mode access
    status = IoCreateSymbolicLink(&symbolicLink, &deviceName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("HalfaxTelemetry: IoCreateSymbolicLink failed: 0x%08X\n", status));
        IoDeleteDevice(deviceObject);
        return status;
    }

    KdPrint(("HalfaxTelemetry: Symbolic link created: \\??\\HalfaxTelemetry\n"));
    KdPrint(("HalfaxTelemetry: *** DRIVER LOADED SUCCESSFULLY (WDM) ***\n"));

    return STATUS_SUCCESS;
}
```

---

## Phase 4: Dispatch Routine Conversions

### 4.1 Create/Close Handlers (New)
**Add:**
```c
NTSTATUS HalfaxDispatchCreate(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
)
{
    UNREFERENCED_PARAMETER(DeviceObject);
    
    KdPrint(("HalfaxTelemetry: IRP_MJ_CREATE\n"));
    
    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    
    return STATUS_SUCCESS;
}

NTSTATUS HalfaxDispatchClose(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
)
{
    UNREFERENCED_PARAMETER(DeviceObject);
    
    KdPrint(("HalfaxTelemetry: IRP_MJ_CLOSE\n"));
    
    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    
    return STATUS_SUCCESS;
}
```

### 4.2 DeviceIoControl Handler (Major Refactor)
**Current (KMDF):**
```c
VOID HalfaxEvtIoDeviceControl(
    _In_ WDFQUEUE Queue,
    _In_ WDFREQUEST Request,
    ...
)
```

**New (WDM):**
```c
NTSTATUS HalfaxDispatchDeviceControl(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
)
{
    PIO_STACK_LOCATION irpStack;
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;
    ULONG_PTR information = 0;
    ULONG ioControlCode;
    PVOID inputBuffer;
    PVOID outputBuffer;
    ULONG inputBufferLength;
    ULONG outputBufferLength;

    UNREFERENCED_PARAMETER(DeviceObject);

    irpStack = IoGetCurrentIrpStackLocation(Irp);
    ioControlCode = irpStack->Parameters.DeviceIoControl.IoControlCode;
    inputBufferLength = irpStack->Parameters.DeviceIoControl.InputBufferLength;
    outputBufferLength = irpStack->Parameters.DeviceIoControl.OutputBufferLength;

    // For METHOD_BUFFERED, both input and output use SystemBuffer
    inputBuffer = Irp->AssociatedIrp.SystemBuffer;
    outputBuffer = Irp->AssociatedIrp.SystemBuffer;

    KdPrint(("HalfaxTelemetry: IOCTL 0x%08X received\n", ioControlCode));

    switch (ioControlCode) {
        case IOCTL_HALFAX_GET_VERSION:
            // Handle version request
            // ... existing logic ...
            break;

        case IOCTL_HALFAX_READ_MSR:
            // Handle MSR read
            // ... existing logic ...
            break;

        // ... other IOCTLs ...

        default:
            status = STATUS_INVALID_DEVICE_REQUEST;
            break;
    }

    Irp->IoStatus.Status = status;
    Irp->IoStatus.Information = information;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);

    return status;
}
```

**Key Changes:**
- Replace `WDFREQUEST` → `PIRP`
- Replace `WdfRequestRetrieveInputBuffer` → Direct `SystemBuffer` access
- Replace `WdfRequestRetrieveOutputBuffer` → Direct `SystemBuffer` access
- Replace `WdfRequestCompleteWithInformation` → `IoCompleteRequest`
- Use `IoGetCurrentIrpStackLocation` for IOCTL code

### 4.3 Unload Handler (New)
**Add:**
```c
VOID HalfaxUnload(
    _In_ PDRIVER_OBJECT DriverObject
)
{
    PDEVICE_OBJECT deviceObject = DriverObject->DeviceObject;
    PDEVICE_EXTENSION deviceExtension;
    
    KdPrint(("HalfaxTelemetry: Driver unloading...\n"));

    if (deviceObject != NULL) {
        deviceExtension = (PDEVICE_EXTENSION)deviceObject->DeviceExtension;
        
        // Delete symbolic link
        IoDeleteSymbolicLink(&deviceExtension->SymbolicLinkName);
        KdPrint(("HalfaxTelemetry: Symbolic link deleted\n"));
        
        // Delete device
        IoDeleteDevice(deviceObject);
        KdPrint(("HalfaxTelemetry: Device deleted\n"));
    }

    KdPrint(("HalfaxTelemetry: Driver unloaded successfully\n"));
}
```

---

## Phase 5: IOCTL Handler Details (Per-IOCTL Conversion)

### 5.1 IOCTL_HALFAX_GET_VERSION
**Buffer Access Changes:**
```c
// OLD (KMDF):
status = WdfRequestRetrieveOutputBuffer(Request, sizeof(...), &buffer, NULL);

// NEW (WDM):
if (outputBufferLength < sizeof(HALFAX_VERSION_RESPONSE)) {
    status = STATUS_BUFFER_TOO_SMALL;
    break;
}
PHALFAX_VERSION_RESPONSE response = (PHALFAX_VERSION_RESPONSE)outputBuffer;
```

### 5.2 IOCTL_HALFAX_READ_MSR
**Similar pattern - validate buffer sizes, use SystemBuffer directly**

### 5.3 All Other IOCTLs
**Follow same conversion pattern:**
1. Validate buffer sizes against `inputBufferLength`/`outputBufferLength`
2. Cast `SystemBuffer` to appropriate structure pointer
3. Perform operation
4. Set `Irp->IoStatus.Information` to bytes written
5. Return status

---

## Phase 6: INF File Updates

### 6.1 Remove WDF References
**File:** `halfax_telemetry.inf`

**No changes needed** - INF is already WDM-compatible. The `[HalfaxTelemetry_Device.NT.Interfaces]` section will be ignored for control devices (as it should be).

---

## Phase 7: Build Configuration

### 7.1 Linker Changes
With `<DriverType>WDM</DriverType>`:
- Entry point automatically becomes `DriverEntry` (not `FxDriverEntry`)
- No WDF libraries linked
- Standard WDM kernel libraries (`ntoskrnl.lib`, `hal.lib`) used

### 7.2 No .def File Needed
WDM drivers export `DriverEntry` automatically via standard conventions.

---

## Phase 8: Testing Plan

### 8.1 Build
```powershell
msbuild halfax_telemetry_driver.vcxproj /p:Configuration=Release /p:Platform=x64 /t:Rebuild
```

### 8.2 Sign
```powershell
signtool.exe sign /ph /fd SHA256 /sha1 "5972C1283156B4C2717091F6B5F81C2A90E229DE" "x64\Release\halfax_telemetry_driver.sys"
```

### 8.3 Create Catalog
```powershell
Copy-Item "x64\Release\halfax_telemetry_driver.sys" "x64\Release\halfax_telemetry_driver\" -Force
inf2cat.exe /driver:x64\Release\halfax_telemetry_driver\ /os:10_X64
signtool.exe sign /ph /fd SHA256 /sha1 "..." "x64\Release\halfax_telemetry_driver\halfaxtelemetry.cat"
```

### 8.4 Install
```powershell
# Option A: pnputil (proper)
pnputil /add-driver "x64\Release\halfax_telemetry_driver\halfax_telemetry.inf" /install /force

# Option B: Manual (testing)
Copy-Item "x64\Release\halfax_telemetry_driver.sys" "C:\Windows\System32\drivers\" -Force
sc.exe create HalfaxTelemetry type= kernel start= demand binPath= "C:\Windows\System32\drivers\halfax_telemetry_driver.sys"
```

### 8.5 Start & Test
```powershell
# Start with DebugView running!
sc.exe start HalfaxTelemetry

# Test broker
.\halfax_kernel_broker.exe --version
```

**Expected Output in DebugView:**
```
HalfaxTelemetry: ============================================
HalfaxTelemetry: DriverEntry START - WDM Version
HalfaxTelemetry: ============================================
HalfaxTelemetry: Device created successfully
HalfaxTelemetry: Symbolic link created: \??\HalfaxTelemetry
HalfaxTelemetry: *** DRIVER LOADED SUCCESSFULLY (WDM) ***
```

**Expected broker output:**
```
Driver version: 1.0.1
```

---

## Phase 9: Validation Checklist

- [ ] Driver builds without WDF dependencies
- [ ] DriverEntry logs appear in DebugView
- [ ] Device `/Device/HalfaxTelemetry` created
- [ ] Symbolic link `\\.\HalfaxTelemetry` accessible
- [ ] Broker can open device handle
- [ ] VERSION IOCTL returns correct data
- [ ] All IOCTLs functional
- [ ] Driver unloads cleanly

---

## Estimated Time: 30-45 minutes

**Breakdown:**
- Phase 1-2 (Config/Headers): 5 min
- Phase 3 (DriverEntry): 10 min
- Phase 4 (Dispatch routines): 15 min
- Phase 5 (IOCTL details): 10 min
- Phase 8-9 (Build/Test): 10 min

---

## Files to Modify
1. ✏️ `halfax_telemetry_driver.vcxproj` - Change DriverType to WDM
2. ✏️ `halfax_telemetry_driver.c` - All WDF → WDM conversions
3. ✅ `halfax_telemetry.h` - No changes needed
4. ✅ `halfax_guid.cpp` - No changes needed
5. ✅ `halfax_telemetry.inf` - No changes needed

## Files to Create
- None (all existing files reused)

## Files to Delete
- ✅ Already deleted: `halfax_telemetry_driver.def`

---

## Risk Assessment: **LOW**

**Why WDM is safer:**
- No framework dependencies
- Direct kernel APIs - universally compatible
- Simpler code path - easier debugging
- Control device pattern well-established in WDM
- No loader complexity

**Only risk:** Manual IRP handling requires careful buffer validation (already doing this).

---

## Ready to Implement

All phases documented. Waiting for approval to proceed with conversion.
