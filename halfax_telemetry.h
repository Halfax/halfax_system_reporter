#pragma once
/*
 * Halfax Telemetry Driver - Shared IOCTL Interface
 * 
 * This header is shared between the kernel driver and user-mode broker.
 * Defines the contract for privileged hardware access primitives.
 */

#ifdef _KERNEL_MODE
#include <ntddk.h>
#else
#include <windows.h>
#include <winioctl.h>
#endif

// Device interface GUID - generate your own with guidgen.exe
// {8E6F1D3A-47B2-4E9C-8D7A-9F2B4C5E6A7D}
DEFINE_GUID(GUID_DEVINTERFACE_HALFAX_TELEMETRY,
    0x8e6f1d3a, 0x47b2, 0x4e9c, 0x8d, 0x7a, 0x9f, 0x2b, 0x4c, 0x5e, 0x6a, 0x7d);

// Custom device type
#define FILE_DEVICE_HALFAX  0x8000

// IOCTL definitions
#define IOCTL_HALFAX_READ_MSR \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x801, METHOD_BUFFERED, FILE_READ_DATA)

#define IOCTL_HALFAX_WRITE_MSR \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x802, METHOD_BUFFERED, FILE_READ_DATA | FILE_WRITE_DATA)

#define IOCTL_HALFAX_READ_PCI \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x803, METHOD_BUFFERED, FILE_READ_DATA)

#define IOCTL_HALFAX_READ_SMBUS \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x804, METHOD_BUFFERED, FILE_READ_DATA)

#define IOCTL_HALFAX_GET_VERSION \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x800, METHOD_BUFFERED, FILE_READ_DATA)

#define IOCTL_HALFAX_GET_CAPABILITIES \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x805, METHOD_BUFFERED, FILE_READ_DATA)

#define IOCTL_HALFAX_READ_MSR_BATCH \
    CTL_CODE(FILE_DEVICE_HALFAX, 0x806, METHOD_BUFFERED, FILE_READ_DATA)

// Protocol version - increment when ABI changes
#define HALFAX_PROTOCOL_VERSION 1

// Version info
#define HALFAX_DRIVER_VERSION_MAJOR 1
#define HALFAX_DRIVER_VERSION_MINOR 1
#define HALFAX_DRIVER_VERSION_STRING "1.1.0"

// Capability flags
typedef enum _HALFAX_CAPABILITY_FLAGS {
    HALFAX_CAP_MSR_READ     = 0x00000001,  // MSR read support
    HALFAX_CAP_MSR_WRITE    = 0x00000002,  // MSR write support (dangerous)
    HALFAX_CAP_PCI_READ     = 0x00000004,  // PCI config space read
    HALFAX_CAP_SMBUS_READ   = 0x00000008,  // SMBus/I2C read (SPD)
    HALFAX_CAP_MULTICORE    = 0x00000010,  // Per-core MSR affinity
} HALFAX_CAPABILITY_FLAGS;

//
// MSR Access Structures
//

typedef struct _HALFAX_MSR_REQUEST {
    ULONG  Version;          // Protocol version (set to HALFAX_PROTOCOL_VERSION)
    ULONG  ProcessorNumber;  // Logical processor index (0-based)
    ULONG  Msr;              // MSR register number
    ULONG  Reserved;         // For future use
} HALFAX_MSR_REQUEST, *PHALFAX_MSR_REQUEST;

typedef struct _HALFAX_MSR_RESPONSE {
    ULONG    Version;        // Protocol version
    NTSTATUS Status;         // Operation status
    ULONG64  Value;          // MSR value read
} HALFAX_MSR_RESPONSE, *PHALFAX_MSR_RESPONSE;

typedef struct _HALFAX_MSR_WRITE_REQUEST {
    ULONG    Version;        // Protocol version
    ULONG    ProcessorNumber;
    ULONG    Msr;
    ULONG    Reserved;
    ULONG64  Value;
} HALFAX_MSR_WRITE_REQUEST, *PHALFAX_MSR_WRITE_REQUEST;

//
// Batch MSR Read - Phase 2 Critical Performance Feature
//

#define HALFAX_MAX_BATCH_MSRS 64  // Maximum MSRs in one batch request

typedef struct _HALFAX_MSR_BATCH_ENTRY {
    ULONG  ProcessorNumber;  // Logical processor index
    ULONG  Msr;              // MSR register number
    ULONG64 Value;           // Output: MSR value (0 on error)
    NTSTATUS Status;         // Output: Per-MSR status
} HALFAX_MSR_BATCH_ENTRY, *PHALFAX_MSR_BATCH_ENTRY;

typedef struct _HALFAX_MSR_BATCH_REQUEST {
    ULONG  Version;          // Protocol version
    ULONG  Count;            // Number of entries (1 to HALFAX_MAX_BATCH_MSRS)
    HALFAX_MSR_BATCH_ENTRY Entries[HALFAX_MAX_BATCH_MSRS];
} HALFAX_MSR_BATCH_REQUEST, *PHALFAX_MSR_BATCH_REQUEST;

typedef struct _HALFAX_MSR_BATCH_RESPONSE {
    ULONG    Version;        // Protocol version
    NTSTATUS OverallStatus;  // Overall operation status
    ULONG    SuccessCount;   // Number of successful reads
    ULONG    FailureCount;   // Number of failed reads
    HALFAX_MSR_BATCH_ENTRY Results[HALFAX_MAX_BATCH_MSRS];
} HALFAX_MSR_BATCH_RESPONSE, *PHALFAX_MSR_BATCH_RESPONSE;

//
// PCI Config Space Access
//

typedef struct _HALFAX_PCI_REQUEST {
    ULONG Version;   // Protocol version
    ULONG Bus;
    ULONG Device;
    ULONG Function;
    ULONG Offset;
    ULONG Length;    // 1, 2, or 4 bytes
} HALFAX_PCI_REQUEST, *PHALFAX_PCI_REQUEST;

typedef struct _HALFAX_PCI_RESPONSE {
    ULONG    Version;  // Protocol version
    NTSTATUS Status;
    ULONG    Value;
    ULONG    Reserved;
} HALFAX_PCI_RESPONSE, *PHALFAX_PCI_RESPONSE;

//
// SMBus Access (for SPD reading)
//

typedef struct _HALFAX_SMBUS_REQUEST {
    ULONG Version;       // Protocol version
    UCHAR SlaveAddress;  // I2C slave address (0x50-0x57 for SPD)
    UCHAR Command;       // Register/offset
    UCHAR Length;        // Bytes to read (max 32)
    UCHAR Reserved;
} HALFAX_SMBUS_REQUEST, *PHALFAX_SMBUS_REQUEST;

typedef struct _HALFAX_SMBUS_RESPONSE {
    ULONG    Version;    // Protocol version
    NTSTATUS Status;
    UCHAR    BytesRead;
    UCHAR    Reserved[3];
    UCHAR    Data[32];
} HALFAX_SMBUS_RESPONSE, *PHALFAX_SMBUS_RESPONSE;

//
// Version Query
//

typedef struct _HALFAX_VERSION_RESPONSE {
    ULONG Version;       // Protocol version
    ULONG MajorVersion;
    ULONG MinorVersion;
    ULONG BuildNumber;
} HALFAX_VERSION_RESPONSE, *PHALFAX_VERSION_RESPONSE;

//
// Capabilities Query
//

typedef struct _HALFAX_CAPABILITIES_RESPONSE {
    ULONG Version;           // Protocol version
    ULONG CapabilityFlags;   // Bitmask of HALFAX_CAPABILITY_FLAGS
    ULONG ProcessorCount;    // Number of logical processors
    ULONG Reserved;
} HALFAX_CAPABILITIES_RESPONSE, *PHALFAX_CAPABILITIES_RESPONSE;

//
// MSR Safety - Common Intel MSRs safe for reading
// (Not exhaustive - consult Intel SDM Volume 4)
//

#define MSR_IA32_PLATFORM_INFO      0x00CE   // Platform info
#define MSR_IA32_THERM_STATUS       0x019C   // Thermal status
#define MSR_IA32_TEMPERATURE_TARGET 0x01A2   // Tj Max
#define MSR_IA32_BIOS_SIGN_ID       0x08B    // Microcode version
#define MSR_TURBO_RATIO_LIMIT       0x01AD   // Turbo ratios
#define MSR_RAPL_POWER_UNIT         0x0606   // RAPL unit
#define MSR_PKG_POWER_LIMIT         0x0610   // Package power limit
#define MSR_PKG_ENERGY_STATUS       0x0611   // Package energy
#define MSR_PKG_POWER_INFO          0x0614   // Package power info
#define MSR_PP0_ENERGY_STATUS       0x0639   // Core energy
#define MSR_PP1_ENERGY_STATUS       0x0641   // Uncore energy
#define MSR_DRAM_ENERGY_STATUS      0x0619   // DRAM energy
