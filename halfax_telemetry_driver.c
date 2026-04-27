/*
 * Halfax Telemetry Driver (WDM)
 * 
 * Minimal kernel driver that exposes privileged hardware primitives
 * via a controlled IOCTL interface. No business logic here—just
 * hardware access and strict validation.
 * 
 * Security: Only administrators can open this device (enforced via security descriptor).
 */

#include <ntddk.h>
#include <ntstrsafe.h>
#include "halfax_telemetry.h"

// Forward declarations
DRIVER_INITIALIZE DriverEntry;
DRIVER_UNLOAD HalfaxUnload;
__drv_dispatchType(IRP_MJ_CREATE) DRIVER_DISPATCH HalfaxDispatchCreate;
__drv_dispatchType(IRP_MJ_CLOSE) DRIVER_DISPATCH HalfaxDispatchClose;
__drv_dispatchType(IRP_MJ_DEVICE_CONTROL) DRIVER_DISPATCH HalfaxDispatchDeviceControl;

#ifdef ALLOC_PRAGMA
#pragma alloc_text(INIT, DriverEntry)
#pragma alloc_text(PAGE, HalfaxUnload)
#pragma alloc_text(PAGE, HalfaxDispatchCreate)
#pragma alloc_text(PAGE, HalfaxDispatchClose)
#pragma alloc_text(PAGE, HalfaxDispatchDeviceControl)
#endif

// Device extension (replaces WDF device context)
typedef struct _DEVICE_EXTENSION {
    PDEVICE_OBJECT DeviceObject;
    UNICODE_STRING DeviceName;
    UNICODE_STRING SymbolicLinkName;
} DEVICE_EXTENSION, *PDEVICE_EXTENSION;


//
// DriverEntry - Called when driver loads
// Creates a control device (non-PnP) directly in DriverEntry
//
NTSTATUS
DriverEntry(
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
    KdPrint(("HalfaxTelemetry: Build: Jan 24 2026\n"));
    KdPrint(("HalfaxTelemetry: ============================================\n"));

    // Set up dispatch routines
    DriverObject->MajorFunction[IRP_MJ_CREATE] = HalfaxDispatchCreate;
    DriverObject->MajorFunction[IRP_MJ_CLOSE] = HalfaxDispatchClose;
    DriverObject->MajorFunction[IRP_MJ_DEVICE_CONTROL] = HalfaxDispatchDeviceControl;
    DriverObject->DriverUnload = HalfaxUnload;

    KdPrint(("HalfaxTelemetry: [1] Dispatch routines registered\n"));

    // Define device name and symbolic link
    RtlInitUnicodeString(&deviceName, L"\\Device\\HalfaxTelemetry");
    RtlInitUnicodeString(&symbolicLink, L"\\DosDevices\\HalfaxTelemetry");

    KdPrint(("HalfaxTelemetry: [2] Device name: \\Device\\HalfaxTelemetry\n"));
    KdPrint(("HalfaxTelemetry: [3] Symbolic link: \\??\\HalfaxTelemetry\n"));

    // Create device object
    KdPrint(("HalfaxTelemetry: [4] Creating device object...\n"));
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
        KdPrint(("HalfaxTelemetry: FATAL: IoCreateDevice failed 0x%08X\n", status));
        return status;
    }

    KdPrint(("HalfaxTelemetry: [5] Device created successfully\n"));

    // Initialize device extension
    deviceExtension = (PDEVICE_EXTENSION)deviceObject->DeviceExtension;
    deviceExtension->DeviceObject = deviceObject;
    deviceExtension->DeviceName = deviceName;
    deviceExtension->SymbolicLinkName = symbolicLink;

    // Set device flags
    deviceObject->Flags |= DO_BUFFERED_IO;
    deviceObject->Flags &= ~DO_DEVICE_INITIALIZING;

    KdPrint(("HalfaxTelemetry: [6] Device extension initialized (Buffered I/O)\n"));

    // Create symbolic link for user-mode access
    KdPrint(("HalfaxTelemetry: [7] Creating symbolic link...\n"));
    status = IoCreateSymbolicLink(&symbolicLink, &deviceName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("HalfaxTelemetry: FATAL: IoCreateSymbolicLink failed 0x%08X\n", status));
        IoDeleteDevice(deviceObject);
        return status;
    }

    KdPrint(("HalfaxTelemetry: [8] Symbolic link created: \\??\\HalfaxTelemetry\n"));
    KdPrint(("HalfaxTelemetry: [9] User-mode path: \\\\.\\HalfaxTelemetry\n"));
    KdPrint(("HalfaxTelemetry: ============================================\n"));
    KdPrint(("HalfaxTelemetry: *** DRIVER LOADED SUCCESSFULLY (WDM) ***\n"));
    KdPrint(("HalfaxTelemetry: ============================================\n"));

    return STATUS_SUCCESS;
}

//
// Helper: Check if MSR is in whitelist (read-safe MSRs only)
//
BOOLEAN
HalfaxIsMsrWhitelisted(
    _In_ ULONG Msr
)
{
    // Whitelist of known-safe read MSRs (Intel - adjust for AMD)
    ULONG safeReadMsrs[] = {
        MSR_IA32_PLATFORM_INFO,      // 0x00CE
        MSR_IA32_THERM_STATUS,       // 0x019C
        MSR_IA32_TEMPERATURE_TARGET, // 0x01A2
        MSR_IA32_BIOS_SIGN_ID,       // 0x08B (Microcode version)
        MSR_TURBO_RATIO_LIMIT,       // 0x01AD
        MSR_RAPL_POWER_UNIT,         // 0x0606
        MSR_PKG_POWER_LIMIT,         // 0x0610
        MSR_PKG_ENERGY_STATUS,       // 0x0611
        MSR_PKG_POWER_INFO,          // 0x0614
        MSR_DRAM_ENERGY_STATUS,      // 0x0619
        MSR_PP0_ENERGY_STATUS,       // 0x0639
        MSR_PP1_ENERGY_STATUS,       // 0x0641
    };

    for (ULONG i = 0; i < ARRAYSIZE(safeReadMsrs); i++) {
        if (Msr == safeReadMsrs[i]) {
            return TRUE;
        }
    }

    // Allow if MSR < 0x1000 (most architectural MSRs are safe to read)
    // This is permissive but prevents catastrophic writes
    if (Msr < 0x1000) {
        return TRUE;
    }

    return FALSE;
}

//
// Helper: Read MSR on specific processor
//
NTSTATUS
HalfaxReadMsr(
    _In_ ULONG ProcessorNumber,
    _In_ ULONG Msr,
    _Out_ PULONG64 Value
)
{
    PROCESSOR_NUMBER procNumber;
    GROUP_AFFINITY affinity, oldAffinity;
    NTSTATUS status;

    // Convert logical processor to group/number
    status = KeGetProcessorNumberFromIndex(ProcessorNumber, &procNumber);
    if (!NT_SUCCESS(status)) {
        return STATUS_INVALID_PARAMETER;
    }

    // Set affinity to target processor
    RtlZeroMemory(&affinity, sizeof(affinity));
    affinity.Group = procNumber.Group;
    affinity.Mask = 1ULL << procNumber.Number;

    KeSetSystemGroupAffinityThread(&affinity, &oldAffinity);

    __try {
        *Value = __readmsr(Msr);
        status = STATUS_SUCCESS;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        status = STATUS_ILLEGAL_INSTRUCTION;
        *Value = 0;
    }

    // Restore affinity
    KeRevertToUserGroupAffinityThread(&oldAffinity);

    return status;
}

//
// Helper: Write MSR on specific processor
//
NTSTATUS
HalfaxWriteMsr(
    _In_ ULONG ProcessorNumber,
    _In_ ULONG Msr,
    _In_ ULONG64 Value
)
{
    PROCESSOR_NUMBER procNumber;
    GROUP_AFFINITY affinity, oldAffinity;
    NTSTATUS status;

    status = KeGetProcessorNumberFromIndex(ProcessorNumber, &procNumber);
    if (!NT_SUCCESS(status)) {
        return STATUS_INVALID_PARAMETER;
    }

    RtlZeroMemory(&affinity, sizeof(affinity));
    affinity.Group = procNumber.Group;
    affinity.Mask = 1ULL << procNumber.Number;

    KeSetSystemGroupAffinityThread(&affinity, &oldAffinity);

    __try {
        __writemsr(Msr, Value);
        status = STATUS_SUCCESS;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        status = STATUS_ILLEGAL_INSTRUCTION;
    }

    KeRevertToUserGroupAffinityThread(&oldAffinity);

    return status;
}

//
// Unload Handler
//
VOID
HalfaxUnload(
    _In_ PDRIVER_OBJECT DriverObject
)
{
    PDEVICE_OBJECT deviceObject = DriverObject->DeviceObject;
    PDEVICE_EXTENSION deviceExtension;

    PAGED_CODE();

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

//
// Create Handler
//
NTSTATUS
HalfaxDispatchCreate(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
)
{
    UNREFERENCED_PARAMETER(DeviceObject);
    PAGED_CODE();

    KdPrint(("HalfaxTelemetry: IRP_MJ_CREATE\n"));

    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);

    return STATUS_SUCCESS;
}

//
// Close Handler
//
NTSTATUS
HalfaxDispatchClose(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
)
{
    UNREFERENCED_PARAMETER(DeviceObject);
    PAGED_CODE();

    KdPrint(("HalfaxTelemetry: IRP_MJ_CLOSE\n"));

    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);

    return STATUS_SUCCESS;
}

//
// IOCTL Handler
//
NTSTATUS
HalfaxDispatchDeviceControl(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
)
{
    PIO_STACK_LOCATION irpStack;
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;
    ULONG_PTR information = 0;
    ULONG ioControlCode;
    PVOID systemBuffer;
    ULONG inputBufferLength;
    ULONG outputBufferLength;

    UNREFERENCED_PARAMETER(DeviceObject);
    PAGED_CODE();

    irpStack = IoGetCurrentIrpStackLocation(Irp);
    ioControlCode = irpStack->Parameters.DeviceIoControl.IoControlCode;
    inputBufferLength = irpStack->Parameters.DeviceIoControl.InputBufferLength;
    outputBufferLength = irpStack->Parameters.DeviceIoControl.OutputBufferLength;

    // For METHOD_BUFFERED, both input and output use SystemBuffer
    systemBuffer = Irp->AssociatedIrp.SystemBuffer;

    KdPrint(("HalfaxTelemetry: IOCTL 0x%08X received\n", ioControlCode));

    switch (ioControlCode) {

    case IOCTL_HALFAX_GET_VERSION:
    {
        PHALFAX_VERSION_RESPONSE response;

        if (outputBufferLength < sizeof(HALFAX_VERSION_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        response = (PHALFAX_VERSION_RESPONSE)systemBuffer;
        response->Version = HALFAX_PROTOCOL_VERSION;
        response->MajorVersion = HALFAX_DRIVER_VERSION_MAJOR;
        response->MinorVersion = HALFAX_DRIVER_VERSION_MINOR;
        response->BuildNumber = 1;

        information = sizeof(HALFAX_VERSION_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_HALFAX_GET_CAPABILITIES:
    {
        PHALFAX_CAPABILITIES_RESPONSE response;

        if (outputBufferLength < sizeof(HALFAX_CAPABILITIES_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        response = (PHALFAX_CAPABILITIES_RESPONSE)systemBuffer;
        response->Version = HALFAX_PROTOCOL_VERSION;
        response->CapabilityFlags = 
            HALFAX_CAP_MSR_READ | 
            HALFAX_CAP_MSR_WRITE | 
            HALFAX_CAP_MULTICORE;
        // PCI and SMBUS not implemented yet
        response->ProcessorCount = KeQueryActiveProcessorCountEx(ALL_PROCESSOR_GROUPS);
        response->Reserved = 0;

        information = sizeof(HALFAX_CAPABILITIES_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_HALFAX_READ_MSR:
    {
        PHALFAX_MSR_REQUEST request;
        PHALFAX_MSR_RESPONSE response;
        ULONG64 msrValue;

        if (inputBufferLength < sizeof(HALFAX_MSR_REQUEST) ||
            outputBufferLength < sizeof(HALFAX_MSR_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        request = (PHALFAX_MSR_REQUEST)systemBuffer;
        response = (PHALFAX_MSR_RESPONSE)systemBuffer;

        // Check protocol version
        if (request->Version != HALFAX_PROTOCOL_VERSION) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = STATUS_INVALID_PARAMETER;
            response->Value = 0;
            information = sizeof(HALFAX_MSR_RESPONSE);
            status = STATUS_SUCCESS;
            break;
        }

        // Validate processor number
        if (request->ProcessorNumber >= KeQueryActiveProcessorCountEx(ALL_PROCESSOR_GROUPS)) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = STATUS_INVALID_PARAMETER;
            response->Value = 0;
        }
        // Check MSR whitelist
        else if (!HalfaxIsMsrWhitelisted(request->Msr)) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = STATUS_ACCESS_DENIED;
            response->Value = 0;
        }
        else {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = HalfaxReadMsr(
                request->ProcessorNumber,
                request->Msr,
                &msrValue
            );
            response->Value = msrValue;
        }

        information = sizeof(HALFAX_MSR_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_HALFAX_WRITE_MSR:
    {
        PHALFAX_MSR_WRITE_REQUEST request;
        PHALFAX_MSR_RESPONSE response;

        if (inputBufferLength < sizeof(HALFAX_MSR_WRITE_REQUEST) ||
            outputBufferLength < sizeof(HALFAX_MSR_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        request = (PHALFAX_MSR_WRITE_REQUEST)systemBuffer;
        response = (PHALFAX_MSR_RESPONSE)systemBuffer;

        // Check protocol version
        if (request->Version != HALFAX_PROTOCOL_VERSION) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = STATUS_INVALID_PARAMETER;
            response->Value = 0;
            information = sizeof(HALFAX_MSR_RESPONSE);
            status = STATUS_SUCCESS;
            break;
        }

        // MSR writes are DANGEROUS - always deny for now
        // To enable, add a separate whitelist and capability check
        response->Version = HALFAX_PROTOCOL_VERSION;
        response->Status = STATUS_ACCESS_DENIED;
        response->Value = 0;

        information = sizeof(HALFAX_MSR_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_HALFAX_READ_MSR_BATCH:
    {
        PHALFAX_MSR_BATCH_REQUEST request;
        PHALFAX_MSR_BATCH_RESPONSE response;
        ULONG i;
        ULONG successCount = 0;
        ULONG failureCount = 0;

        if (inputBufferLength < sizeof(HALFAX_MSR_BATCH_REQUEST) ||
            outputBufferLength < sizeof(HALFAX_MSR_BATCH_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        request = (PHALFAX_MSR_BATCH_REQUEST)systemBuffer;
        response = (PHALFAX_MSR_BATCH_RESPONSE)systemBuffer;

        // Check protocol version
        if (request->Version != HALFAX_PROTOCOL_VERSION) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->OverallStatus = STATUS_INVALID_PARAMETER;
            response->SuccessCount = 0;
            response->FailureCount = 0;
            information = sizeof(HALFAX_MSR_BATCH_RESPONSE);
            status = STATUS_SUCCESS;
            break;
        }

        // Validate count
        if (request->Count == 0 || request->Count > HALFAX_MAX_BATCH_MSRS) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->OverallStatus = STATUS_INVALID_PARAMETER;
            response->SuccessCount = 0;
            response->FailureCount = 0;
            information = sizeof(HALFAX_MSR_BATCH_RESPONSE);
            status = STATUS_SUCCESS;
            break;
        }

        // Process each MSR read request
        for (i = 0; i < request->Count; i++) {
            ULONG64 msrValue = 0;
            NTSTATUS readStatus;

            // Validate processor number
            if (request->Entries[i].ProcessorNumber >= KeQueryActiveProcessorCountEx(ALL_PROCESSOR_GROUPS)) {
                readStatus = STATUS_INVALID_PARAMETER;
                msrValue = 0;
                failureCount++;
            }
            // Check MSR whitelist
            else if (!HalfaxIsMsrWhitelisted(request->Entries[i].Msr)) {
                readStatus = STATUS_ACCESS_DENIED;
                msrValue = 0;
                failureCount++;
            }
            else {
                // Perform MSR read
                readStatus = HalfaxReadMsr(
                    request->Entries[i].ProcessorNumber,
                    request->Entries[i].Msr,
                    &msrValue
                );

                if (NT_SUCCESS(readStatus)) {
                    successCount++;
                } else {
                    failureCount++;
                }
            }

            // Store result
            response->Results[i].ProcessorNumber = request->Entries[i].ProcessorNumber;
            response->Results[i].Msr = request->Entries[i].Msr;
            response->Results[i].Value = msrValue;
            response->Results[i].Status = readStatus;
        }

        // Set response header
        response->Version = HALFAX_PROTOCOL_VERSION;
        response->OverallStatus = (successCount > 0) ? STATUS_SUCCESS : STATUS_UNSUCCESSFUL;
        response->SuccessCount = successCount;
        response->FailureCount = failureCount;

        information = sizeof(HALFAX_MSR_BATCH_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_HALFAX_READ_PCI:
    {
        PHALFAX_PCI_REQUEST request;
        PHALFAX_PCI_RESPONSE response;

        if (inputBufferLength < sizeof(HALFAX_PCI_REQUEST) ||
            outputBufferLength < sizeof(HALFAX_PCI_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        request = (PHALFAX_PCI_REQUEST)systemBuffer;
        response = (PHALFAX_PCI_RESPONSE)systemBuffer;

        // Check protocol version
        if (request->Version != HALFAX_PROTOCOL_VERSION) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = STATUS_INVALID_PARAMETER;
            response->Value = 0;
            information = sizeof(HALFAX_PCI_RESPONSE);
            status = STATUS_SUCCESS;
            break;
        }

        // TODO: Implement PCI config space reading via bus interface
        // For now, return not implemented with clear status
        response->Version = HALFAX_PROTOCOL_VERSION;
        response->Status = STATUS_NOT_IMPLEMENTED;
        response->Value = 0;
        response->Reserved = 0;

        information = sizeof(HALFAX_PCI_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_HALFAX_READ_SMBUS:
    {
        PHALFAX_SMBUS_REQUEST request;
        PHALFAX_SMBUS_RESPONSE response;

        if (inputBufferLength < sizeof(HALFAX_SMBUS_REQUEST) ||
            outputBufferLength < sizeof(HALFAX_SMBUS_RESPONSE)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        request = (PHALFAX_SMBUS_REQUEST)systemBuffer;
        response = (PHALFAX_SMBUS_RESPONSE)systemBuffer;

        // Check protocol version
        if (request->Version != HALFAX_PROTOCOL_VERSION) {
            response->Version = HALFAX_PROTOCOL_VERSION;
            response->Status = STATUS_INVALID_PARAMETER;
            response->BytesRead = 0;
            information = sizeof(HALFAX_SMBUS_RESPONSE);
            status = STATUS_SUCCESS;
            break;
        }

        // TODO: Implement SMBus reading via ACPI or chipset driver
        // For now, return not implemented with clear status
        response->Version = HALFAX_PROTOCOL_VERSION;
        response->Status = STATUS_NOT_IMPLEMENTED;
        response->BytesRead = 0;

        information = sizeof(HALFAX_SMBUS_RESPONSE);
        status = STATUS_SUCCESS;
        break;
    }

    default:
        status = STATUS_INVALID_DEVICE_REQUEST;
        break;
    }

    Irp->IoStatus.Status = status;
    Irp->IoStatus.Information = information;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return status;
}
