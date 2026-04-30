/*
 * Halfax Kernel Broker - User-mode helper
 * 
 * This is the single user-mode interface to the kernel driver.
 * Wraps IOCTLs in clean functions and exposes CLI/IPC interface
 * for the rest of your helpers to use.
 * 
 * Compile: cl halfax_kernel_broker.cpp /EHsc
 */

#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <vector>
#include <string>
#include <iostream>
#include <sstream>
#include <nlohmann/json.hpp>
#include "halfax_telemetry.h"

#pragma comment(lib, "setupapi.lib")

class HalfaxKernelBroker {
private:
    HANDLE hDevice;
    bool initialized;

    // Helper to find the device interface
    bool OpenDriverInterface() {
        HDEVINFO deviceInfoSet;
        SP_DEVICE_INTERFACE_DATA deviceInterfaceData;
        PSP_DEVICE_INTERFACE_DETAIL_DATA deviceInterfaceDetailData = NULL;
        DWORD requiredSize = 0;
        bool result = false;

        // Get device interface set
        deviceInfoSet = SetupDiGetClassDevs(
            &GUID_DEVINTERFACE_HALFAX_TELEMETRY,
            NULL,
            NULL,
            DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        );

        if (deviceInfoSet == INVALID_HANDLE_VALUE) {
            // Try fallback: open by symbolic link directly
            hDevice = CreateFileA(
                "\\\\.\\HalfaxTelemetry",
                GENERIC_READ | GENERIC_WRITE,
                0,
                NULL,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                NULL
            );

            if (hDevice != INVALID_HANDLE_VALUE) {
                return true;
            }

            fprintf(stderr, "Failed to get device info set. Error: %lu\n", GetLastError());
            return false;
        }

        // Enumerate first device interface
        deviceInterfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);
        if (!SetupDiEnumDeviceInterfaces(
                deviceInfoSet,
                NULL,
                &GUID_DEVINTERFACE_HALFAX_TELEMETRY,
                0,
                &deviceInterfaceData)) {
            // No device interface found - try direct symbolic link (WDM control device)
            SetupDiDestroyDeviceInfoList(deviceInfoSet);
            
            hDevice = CreateFileA(
                "\\\\.\\HalfaxTelemetry",
                GENERIC_READ | GENERIC_WRITE,
                0,
                NULL,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                NULL
            );

            if (hDevice != INVALID_HANDLE_VALUE) {
                return true;
            }

            fprintf(stderr, "No device interface found. Is the driver loaded?\n");
            return false;
        }

        // Get device interface detail (path)
        SetupDiGetDeviceInterfaceDetail(
            deviceInfoSet,
            &deviceInterfaceData,
            NULL,
            0,
            &requiredSize,
            NULL
        );

        deviceInterfaceDetailData = (PSP_DEVICE_INTERFACE_DETAIL_DATA)malloc(requiredSize);
        if (!deviceInterfaceDetailData) {
            SetupDiDestroyDeviceInfoList(deviceInfoSet);
            return false;
        }

        deviceInterfaceDetailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

        if (!SetupDiGetDeviceInterfaceDetail(
                deviceInfoSet,
                &deviceInterfaceData,
                deviceInterfaceDetailData,
                requiredSize,
                NULL,
                NULL)) {
            fprintf(stderr, "Failed to get device path. Error: %lu\n", GetLastError());
            free(deviceInterfaceDetailData);
            SetupDiDestroyDeviceInfoList(deviceInfoSet);
            return false;
        }

        // Open device
        hDevice = CreateFile(
            deviceInterfaceDetailData->DevicePath,
            GENERIC_READ | GENERIC_WRITE,
            0,
            NULL,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            NULL
        );

        if (hDevice == INVALID_HANDLE_VALUE) {
            fprintf(stderr, "Failed to open device. Error: %lu\n", GetLastError());
            fprintf(stderr, "Path: %s\n", deviceInterfaceDetailData->DevicePath);
            fprintf(stderr, "Make sure you're running as Administrator.\n");
        } else {
            result = true;
        }

        free(deviceInterfaceDetailData);
        SetupDiDestroyDeviceInfoList(deviceInfoSet);

        return result;
    }

public:
    HalfaxKernelBroker() : hDevice(INVALID_HANDLE_VALUE), initialized(false) {}

    ~HalfaxKernelBroker() {
        if (hDevice != INVALID_HANDLE_VALUE) {
            CloseHandle(hDevice);
        }
    }

    bool Initialize() {
        if (!OpenDriverInterface()) {
            return false;
        }

        initialized = true;
        return true;
    }

    bool GetVersion(ULONG* major, ULONG* minor, ULONG* build) {
        if (!initialized) return false;

        HALFAX_VERSION_RESPONSE response;
        DWORD bytesReturned;

        if (!DeviceIoControl(
                hDevice,
                IOCTL_HALFAX_GET_VERSION,
                NULL, 0,
                &response, sizeof(response),
                &bytesReturned,
                NULL)) {
            return false;
        }

        *major = response.MajorVersion;
        *minor = response.MinorVersion;
        *build = response.BuildNumber;
        return true;
    }

    bool GetCapabilities(ULONG* capFlags, ULONG* procCount) {
        if (!initialized) return false;

        HALFAX_CAPABILITIES_RESPONSE response;
        DWORD bytesReturned;

        if (!DeviceIoControl(
                hDevice,
                IOCTL_HALFAX_GET_CAPABILITIES,
                NULL, 0,
                &response, sizeof(response),
                &bytesReturned,
                NULL)) {
            return false;
        }

        *capFlags = response.CapabilityFlags;
        *procCount = response.ProcessorCount;
        return true;
    }

    bool ReadMSR(ULONG processorNumber, ULONG msr, uint64_t* value, NTSTATUS* status) {
        if (!initialized) return false;

        HALFAX_MSR_REQUEST request;
        HALFAX_MSR_RESPONSE response;
        DWORD bytesReturned;

        request.Version = HALFAX_PROTOCOL_VERSION;
        request.ProcessorNumber = processorNumber;
        request.Msr = msr;
        request.Reserved = 0;

        if (!DeviceIoControl(
                hDevice,
                IOCTL_HALFAX_READ_MSR,
                &request, sizeof(request),
                &response, sizeof(response),
                &bytesReturned,
                NULL)) {
            return false;
        }

        *value = response.Value;
        if (status) *status = response.Status;
        return true;
    }

    bool WriteMSR(ULONG processorNumber, ULONG msr, uint64_t value, NTSTATUS* status) {
        if (!initialized) return false;

        HALFAX_MSR_WRITE_REQUEST request;
        HALFAX_MSR_RESPONSE response;
        DWORD bytesReturned;

        request.Version = HALFAX_PROTOCOL_VERSION;
        request.ProcessorNumber = processorNumber;
        request.Msr = msr;
        request.Reserved = 0;
        request.Value = value;

        if (!DeviceIoControl(
                hDevice,
                IOCTL_HALFAX_WRITE_MSR,
                &request, sizeof(request),
                &response, sizeof(response),
                &bytesReturned,
                NULL)) {
            return false;
        }

        if (status) *status = response.Status;
        return true;
    }

    bool ReadMSRBatch(HALFAX_MSR_BATCH_ENTRY* entries, ULONG count, 
                      ULONG* successCount, ULONG* failureCount, NTSTATUS* overallStatus) {
        if (!initialized) return false;
        if (count == 0 || count > HALFAX_MAX_BATCH_MSRS) return false;

        HALFAX_MSR_BATCH_REQUEST request;
        HALFAX_MSR_BATCH_RESPONSE response;
        DWORD bytesReturned;

        request.Version = HALFAX_PROTOCOL_VERSION;
        request.Count = count;

        // Copy input entries
        for (ULONG i = 0; i < count; i++) {
            request.Entries[i] = entries[i];
        }

        if (!DeviceIoControl(
                hDevice,
                IOCTL_HALFAX_READ_MSR_BATCH,
                &request, sizeof(request),
                &response, sizeof(response),
                &bytesReturned,
                NULL)) {
            return false;
        }

        // Copy results back
        for (ULONG i = 0; i < count; i++) {
            entries[i] = response.Results[i];
        }

        if (successCount) *successCount = response.SuccessCount;
        if (failureCount) *failureCount = response.FailureCount;
        if (overallStatus) *overallStatus = response.OverallStatus;

        return true;
    }

    bool ReadPCI(ULONG bus, ULONG device, ULONG function, ULONG offset, 
                 ULONG length, ULONG* value, NTSTATUS* status) {
        if (!initialized) return false;

        HALFAX_PCI_REQUEST request;
        HALFAX_PCI_RESPONSE response;
        DWORD bytesReturned;

        request.Version = HALFAX_PROTOCOL_VERSION;
        request.Bus = bus;
        request.Device = device;
        request.Function = function;
        request.Offset = offset;
        request.Length = length;

        if (!DeviceIoControl(
                hDevice,
                IOCTL_HALFAX_READ_PCI,
                &request, sizeof(request),
                &response, sizeof(response),
                &bytesReturned,
                NULL)) {
            return false;
        }

        *value = response.Value;
        if (status) *status = response.Status;
        return true;
    }
};

// Exit codes for machine-readable error handling
#define EXIT_SUCCESS 0
#define EXIT_DRIVER_NOT_PRESENT 1
#define EXIT_ACCESS_DENIED 2
#define EXIT_NOT_IMPLEMENTED 3
#define EXIT_INVALID_PARAMETER 4
#define EXIT_OPERATION_FAILED 5

// CLI interface
void PrintUsage(const char* progName) {
    printf("Halfax Kernel Broker - Privileged Hardware Access\n\n");
    printf("Usage:\n");
    printf("  %s [--json] --version                 Get driver version\n", progName);
    printf("  %s [--json] --capabilities            Get driver capabilities\n", progName);
    printf("  %s [--json] --read-msr <cpu> <msr>    Read MSR\n", progName);
    printf("  %s [--json] --read-msr-batch <count>  Read multiple MSRs (stdin JSON)\n", progName);
    printf("  %s [--json] --write-msr <cpu> <msr> <value>  Write MSR\n", progName);
    printf("  %s [--json] --read-pci <b:d:f> <offset> <len>  Read PCI config\n", progName);
    printf("\n");
    printf("Options:\n");
    printf("  --json    Output machine-readable JSON (one line per result)\n");
    printf("\n");
    printf("Examples:\n");
    printf("  %s --read-msr 0 0x1AD                 Read turbo ratio limit on CPU 0\n", progName);
    printf("  %s --json --read-msr 0 0x19C          Read temperature (JSON output)\n", progName);
    printf("  %s --json --read-msr-batch < batch.json  Batch MSR reads from file\n", progName);
    printf("\n");
    printf("Exit codes:\n");
    printf("  0 = Success\n");
    printf("  1 = Driver not present/not loaded\n");
    printf("  2 = Access denied (need admin or MSR not whitelisted)\n");
    printf("  3 = Feature not implemented\n");
    printf("  4 = Invalid parameter\n");
    printf("  5 = Operation failed\n");
    printf("\n");
}

int main(int argc, char* argv[]) {
    HalfaxKernelBroker broker;
    bool jsonMode = false;
    int argOffset = 1;

    if (argc < 2) {
        PrintUsage(argv[0]);
        return EXIT_INVALID_PARAMETER;
    }

    // Check for --json flag
    if (strcmp(argv[1], "--json") == 0) {
        jsonMode = true;
        argOffset = 2;
        if (argc < 3) {
            fprintf(stderr, "{\"error\":\"missing command after --json\"}\n");
            return EXIT_INVALID_PARAMETER;
        }
    }

    // Initialize
    if (!broker.Initialize()) {
        if (jsonMode) {
            printf("{\"error\":\"driver_not_present\",\"message\":\"Failed to open kernel driver. Check: 1) Driver loaded 2) Running as Administrator 3) Test signing enabled\"}\n");
        } else {
            fprintf(stderr, "ERROR: Failed to open kernel driver.\n");
            fprintf(stderr, "Make sure:\n");
            fprintf(stderr, "  1. Driver is loaded (sc query HalfaxTelemetry)\n");
            fprintf(stderr, "  2. You're running as Administrator\n");
            fprintf(stderr, "  3. Test signing is enabled (bcdedit /set testsigning on)\n");
        }
        return EXIT_DRIVER_NOT_PRESENT;
    }

    // Parse commands
    if (strcmp(argv[argOffset], "--version") == 0) {
        ULONG major, minor, build;
        if (broker.GetVersion(&major, &minor, &build)) {
            if (jsonMode) {
                printf("{\"status\":\"success\",\"version\":\"%lu.%lu.%lu\",\"major\":%lu,\"minor\":%lu,\"build\":%lu}\n",
                       major, minor, build, major, minor, build);
            } else {
                printf("Driver version: %lu.%lu.%lu\n", major, minor, build);
            }
            return EXIT_SUCCESS;
        } else {
            if (jsonMode) {
                printf("{\"error\":\"ioctl_failed\",\"message\":\"Failed to get version\"}\n");
            } else {
                fprintf(stderr, "Failed to get version\n");
            }
            return EXIT_OPERATION_FAILED;
        }
    }
    else if (strcmp(argv[argOffset], "--capabilities") == 0) {
        ULONG capFlags, procCount;
        if (broker.GetCapabilities(&capFlags, &procCount)) {
            if (jsonMode) {
                printf("{\"status\":\"success\",\"capability_flags\":%lu,\"processor_count\":%lu,"
                       "\"msr_read\":%s,\"msr_write\":%s,\"pci_read\":%s,\"smbus_read\":%s,\"multicore\":%s}\n",
                       capFlags, procCount,
                       (capFlags & HALFAX_CAP_MSR_READ) ? "true" : "false",
                       (capFlags & HALFAX_CAP_MSR_WRITE) ? "true" : "false",
                       (capFlags & HALFAX_CAP_PCI_READ) ? "true" : "false",
                       (capFlags & HALFAX_CAP_SMBUS_READ) ? "true" : "false",
                       (capFlags & HALFAX_CAP_MULTICORE) ? "true" : "false");
            } else {
                printf("Capabilities: 0x%08lX\n", capFlags);
                printf("  MSR Read:    %s\n", (capFlags & HALFAX_CAP_MSR_READ) ? "Yes" : "No");
                printf("  MSR Write:   %s\n", (capFlags & HALFAX_CAP_MSR_WRITE) ? "Yes" : "No");
                printf("  PCI Read:    %s\n", (capFlags & HALFAX_CAP_PCI_READ) ? "Yes" : "No");
                printf("  SMBus Read:  %s\n", (capFlags & HALFAX_CAP_SMBUS_READ) ? "Yes" : "No");
                printf("  Multicore:   %s\n", (capFlags & HALFAX_CAP_MULTICORE) ? "Yes" : "No");
                printf("Processor Count: %lu\n", procCount);
            }
            return EXIT_SUCCESS;
        } else {
            if (jsonMode) {
                printf("{\"error\":\"ioctl_failed\",\"message\":\"Failed to get capabilities\"}\n");
            } else {
                fprintf(stderr, "Failed to get capabilities\n");
            }
            return EXIT_OPERATION_FAILED;
        }
    }
    else if (strcmp(argv[argOffset], "--read-msr") == 0) {
        if (argc < argOffset + 3) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_arguments\",\"message\":\"Usage: --read-msr <cpu> <msr>\"}\n");
            } else {
                fprintf(stderr, "Usage: %s --read-msr <cpu> <msr>\n", argv[0]);
            }
            return EXIT_INVALID_PARAMETER;
        }

        ULONG cpu = strtoul(argv[argOffset + 1], NULL, 0);
        ULONG msr = strtoul(argv[argOffset + 2], NULL, 0);
        uint64_t value;
        NTSTATUS status;

        if (broker.ReadMSR(cpu, msr, &value, &status)) {
            if (status == 0) {  // STATUS_SUCCESS
                if (jsonMode) {
                    printf("{\"status\":\"success\",\"cpu\":%lu,\"msr\":\"0x%lX\",\"value\":\"0x%llX\",\"value_dec\":%llu}\n",
                           cpu, msr, value, value);
                } else {
                    printf("0x%llX\n", value);
                }
                return EXIT_SUCCESS;
            } else if (status == 0xC0000022) {  // STATUS_ACCESS_DENIED
                if (jsonMode) {
                    printf("{\"error\":\"access_denied\",\"message\":\"MSR not whitelisted or write-only\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "Access denied: MSR 0x%lX not whitelisted (NTSTATUS 0x%08lX)\n", msr, status);
                }
                return EXIT_ACCESS_DENIED;
            } else if (status == 0xC000001C) {  // STATUS_ILLEGAL_INSTRUCTION
                if (jsonMode) {
                    printf("{\"error\":\"invalid_msr\",\"message\":\"Invalid MSR for this CPU\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "Invalid MSR 0x%lX for this CPU (NTSTATUS 0x%08lX)\n", msr, status);
                }
                return EXIT_INVALID_PARAMETER;
            } else {
                if (jsonMode) {
                    printf("{\"error\":\"msr_read_failed\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "MSR read failed with NTSTATUS 0x%08lX\n", status);
                }
                return EXIT_OPERATION_FAILED;
            }
        } else {
            if (jsonMode) {
                printf("{\"error\":\"ioctl_failed\",\"message\":\"DeviceIoControl failed\"}\n");
            } else {
                fprintf(stderr, "DeviceIoControl failed\n");
            }
            return EXIT_OPERATION_FAILED;
        }
    }
    else if (strcmp(argv[argOffset], "--read-msr-batch") == 0) {
        // Usage: --read-msr-batch <count> (reads JSON array of {cpu, msr} from stdin)
        if (argc < argOffset + 2) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_arguments\",\"message\":\"Usage: --read-msr-batch <count> (JSON array from stdin)\"}\n");
            } else {
                fprintf(stderr, "Usage: %s --read-msr-batch <count> (JSON array from stdin)\n", argv[0]);
            }
            return EXIT_INVALID_PARAMETER;
        }
        ULONG count = strtoul(argv[argOffset + 1], NULL, 0);
        if (count == 0 || count > HALFAX_MAX_BATCH_MSRS) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_count\",\"message\":\"Count must be 1-%d\"}\n", HALFAX_MAX_BATCH_MSRS);
            } else {
                fprintf(stderr, "Count must be 1-%d\n", HALFAX_MAX_BATCH_MSRS);
            }
            return EXIT_INVALID_PARAMETER;
        }
        // Read JSON array from stdin
        std::vector<HALFAX_MSR_BATCH_ENTRY> entries(count);
        bool parseOk = false;
        {
            std::string input;
            std::getline(std::cin, input);
            try {
                auto arr = nlohmann::json::parse(input);
                if (arr.is_array() && arr.size() == count) {
                    for (size_t i = 0; i < count; ++i) {
                        entries[i].ProcessorNumber = arr[i]["cpu"].get<ULONG>();
                        entries[i].Msr = arr[i]["msr"].get<ULONG>();
                    }
                    parseOk = true;
                }
            } catch (...) {}
        }
        if (!parseOk) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_json\",\"message\":\"Failed to parse JSON array from stdin\"}\n");
            } else {
                fprintf(stderr, "Failed to parse JSON array from stdin\n");
            }
            return EXIT_INVALID_PARAMETER;
        }
        ULONG successCount = 0, failureCount = 0;
        NTSTATUS overallStatus = 0;
        if (broker.ReadMSRBatch(entries.data(), count, &successCount, &failureCount, &overallStatus)) {
            if (jsonMode) {
                nlohmann::json outArr = nlohmann::json::array();
                for (ULONG i = 0; i < count; ++i) {
                    outArr.push_back({
                        {"cpu", entries[i].ProcessorNumber},
                        {"msr", entries[i].Msr},
                        {"value", entries[i].Value},
                        {"status", entries[i].Status}
                    });
                }
                nlohmann::json result = {
                    {"status", "success"},
                    {"overall_status", overallStatus},
                    {"success_count", successCount},
                    {"failure_count", failureCount},
                    {"results", outArr}
                };
                printf("%s\n", result.dump().c_str());
            } else {
                printf("Batch MSR read: %lu success, %lu failure\n", successCount, failureCount);
                for (ULONG i = 0; i < count; ++i) {
                    printf("CPU %lu MSR 0x%lX = 0x%llX (status 0x%08lX)\n",
                        entries[i].ProcessorNumber, entries[i].Msr, entries[i].Value, entries[i].Status);
                }
            }
            return (failureCount == 0) ? EXIT_SUCCESS : EXIT_OPERATION_FAILED;
        } else {
            if (jsonMode) {
                printf("{\"error\":\"ioctl_failed\",\"message\":\"DeviceIoControl failed\"}\n");
            } else {
                fprintf(stderr, "DeviceIoControl failed\n");
            }
            return EXIT_OPERATION_FAILED;
        }
    }
    else if (strcmp(argv[argOffset], "--write-msr") == 0) {
        if (argc < argOffset + 4) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_arguments\",\"message\":\"Usage: --write-msr <cpu> <msr> <value>\"}\n");
            } else {
                fprintf(stderr, "Usage: %s --write-msr <cpu> <msr> <value>\n", argv[0]);
            }
            return EXIT_INVALID_PARAMETER;
        }

        ULONG cpu = strtoul(argv[argOffset + 1], NULL, 0);
        ULONG msr = strtoul(argv[argOffset + 2], NULL, 0);
        uint64_t value = strtoull(argv[argOffset + 3], NULL, 0);
        NTSTATUS status;

        if (broker.WriteMSR(cpu, msr, value, &status)) {
            if (status == 0) {
                if (jsonMode) {
                    printf("{\"status\":\"success\",\"cpu\":%lu,\"msr\":\"0x%lX\",\"value\":\"0x%llX\"}\n", cpu, msr, value);
                } else {
                    printf("MSR 0x%lX on CPU %lu set to 0x%llX\n", msr, cpu, value);
                }
                return EXIT_SUCCESS;
            } else if (status == 0xC0000022) {  // STATUS_ACCESS_DENIED
                if (jsonMode) {
                    printf("{\"error\":\"access_denied\",\"message\":\"MSR writes disabled for safety\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "MSR writes disabled for safety (NTSTATUS 0x%08lX)\n", status);
                }
                return EXIT_ACCESS_DENIED;
            } else {
                if (jsonMode) {
                    printf("{\"error\":\"msr_write_failed\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "MSR write failed with NTSTATUS 0x%08lX\n", status);
                }
                return EXIT_OPERATION_FAILED;
            }
        } else {
            if (jsonMode) {
                printf("{\"error\":\"ioctl_failed\",\"message\":\"DeviceIoControl failed\"}\n");
            } else {
                fprintf(stderr, "DeviceIoControl failed\n");
            }
            return EXIT_OPERATION_FAILED;
        }
    }
    else if (strcmp(argv[argOffset], "--read-pci") == 0) {
        if (argc < argOffset + 4) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_arguments\",\"message\":\"Usage: --read-pci <b:d:f> <offset> <length>\"}\n");
            } else {
                fprintf(stderr, "Usage: %s --read-pci <b:d:f> <offset> <length>\n", argv[0]);
            }
            return EXIT_INVALID_PARAMETER;
        }

        ULONG bus, dev, func, offset, length;
        if (sscanf(argv[argOffset + 1], "%lu:%lu:%lu", &bus, &dev, &func) != 3) {
            if (jsonMode) {
                printf("{\"error\":\"invalid_bdf\",\"message\":\"Invalid BDF format. Use: bus:device:function\"}\n");
            } else {
                fprintf(stderr, "Invalid BDF format. Use: bus:device:function\n");
            }
            return EXIT_INVALID_PARAMETER;
        }

        offset = strtoul(argv[argOffset + 2], NULL, 0);
        length = strtoul(argv[argOffset + 3], NULL, 0);

        ULONG value;
        NTSTATUS status;

        if (broker.ReadPCI(bus, dev, func, offset, length, &value, &status)) {
            if (status == 0) {
                if (jsonMode) {
                    printf("{\"status\":\"success\",\"bus\":%lu,\"device\":%lu,\"function\":%lu,\"offset\":%lu,\"value\":\"0x%08lX\"}\n",
                           bus, dev, func, offset, value);
                } else {
                    printf("0x%08lX\n", value);
                }
                return EXIT_SUCCESS;
            } else if (status == 0xC0000002) {  // STATUS_NOT_IMPLEMENTED
                if (jsonMode) {
                    printf("{\"error\":\"not_implemented\",\"message\":\"PCI config space reading not implemented in driver\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "PCI config space reading not implemented (NTSTATUS 0x%08lX)\n", status);
                }
                return EXIT_NOT_IMPLEMENTED;
            } else {
                if (jsonMode) {
                    printf("{\"error\":\"pci_read_failed\",\"ntstatus\":\"0x%08lX\"}\n", status);
                } else {
                    fprintf(stderr, "PCI read failed with NTSTATUS 0x%08lX\n", status);
                }
                return EXIT_OPERATION_FAILED;
            }
        } else {
            if (jsonMode) {
                printf("{\"error\":\"ioctl_failed\",\"message\":\"DeviceIoControl failed\"}\n");
            } else {
                fprintf(stderr, "DeviceIoControl failed\n");
            }
            return EXIT_OPERATION_FAILED;
        }
    }
    else {
        if (jsonMode) {
            printf("{\"error\":\"unknown_command\",\"message\":\"Unknown command: %s\"}\n", argv[argOffset]);
        } else {
            fprintf(stderr, "Unknown command: %s\n", argv[argOffset]);
            PrintUsage(argv[0]);
        }
        return EXIT_INVALID_PARAMETER;
    }

    return EXIT_SUCCESS;
}
