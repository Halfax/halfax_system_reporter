#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "cfgmgr32.lib")

// EDID Structure (simplified - first 128 bytes)
typedef struct {
    BYTE header[8];                    // Fixed 00 FF FF FF FF FF FF 00
    WORD manufacturer_id;              // Big-endian
    WORD product_code;                 // Little-endian
    DWORD serial_number;               // Little-endian
    BYTE week;                         // Manufacturing week
    BYTE year;                         // Year (offset from 1990)
    BYTE edid_version;                 // Major version
    BYTE edid_revision;                // Minor revision
    BYTE input_type;                   // Digital (bit 7) or Analog
    BYTE max_h_size;                   // cm
    BYTE max_v_size;                   // cm
    BYTE gamma;                        // (gamma + 100) / 100
    BYTE features;                     // Features bitmap
    BYTE chromaticity[10];             // CIE 1931 chromaticity coordinates
    BYTE timing[3];                    // Supported timing
    BYTE descriptors[72];              // 4x 18-byte descriptors
} EDID_128;

// Manufacturer ID to name (common mappings)
typedef struct {
    WORD id;
    const char* name;
} MFG_ID;

static MFG_ID mfg_ids[] = {
    {0x0610, "AOC"},
    {0x0AAA, "ASUS"},
    {0x3142, "Dell"},
    {0x1050, "LG"},
    {0x0304, "HP"},
    {0x003E, "Samsung"},
    {0x002B, "BenQ"},
    {0x0B59, "ACER"},
    {0x0F32, "Viewsonic"},
    {0x0000, NULL}
};

// Decode 3-letter manufacturer ID from 16-bit value
void decode_manufacturer_id(WORD id, char* mfg_name) {
    // IDs are 3 10-bit values: CCCCBBBBBAAAAA (where A=char1, B=char2, C=char3)
    char c1 = 'A' + ((id >> 10) & 0x1F) - 1;
    char c2 = 'A' + ((id >> 5) & 0x1F) - 1;
    char c3 = 'A' + (id & 0x1F) - 1;
    
    sprintf(mfg_name, "%c%c%c", c1, c2, c3);
}

// Get friendly manufacturer name
const char* get_manufacturer_name(WORD id) {
    for (int i = 0; mfg_ids[i].name; i++) {
        if (mfg_ids[i].id == id) {
            return mfg_ids[i].name;
        }
    }
    return "Unknown";
}

// Extract monitor name from EDID descriptors
void extract_monitor_name(BYTE* descriptors, char* name) {
    strcpy(name, "Unknown");
    
    // Descriptors are at offset 54 in EDID, 4 blocks of 18 bytes each
    for (int i = 0; i < 4; i++) {
        BYTE* desc = descriptors + (i * 18);
        // Type 0xFC is Monitor Name
        if (desc[3] == 0xFC) {
            // Name is in bytes 5-17 (13 bytes max)
            char temp[14];
            strncpy(temp, (char*)&desc[5], 13);
            temp[13] = '\0';
            
            // Remove trailing spaces
            for (int j = strlen(temp) - 1; j >= 0; j--) {
                if (temp[j] == ' ' || temp[j] == '\0' || temp[j] == 0x0A) {
                    temp[j] = '\0';
                } else {
                    break;
                }
            }
            
            if (strlen(temp) > 0 && isprint(temp[0])) {
                strcpy(name, temp);
                break;
            }
        }
    }
}

// Extract serial number from EDID descriptors
void extract_serial_number(BYTE* descriptors, char* serial) {
    strcpy(serial, "Unknown");
    
    for (int i = 0; i < 4; i++) {
        BYTE* desc = descriptors + (i * 18);
        // Type 0xFF is Serial Number
        if (desc[3] == 0xFF) {
            char temp[14];
            strncpy(temp, (char*)&desc[5], 13);
            temp[13] = '\0';
            
            // Remove trailing spaces and newlines
            for (int j = strlen(temp) - 1; j >= 0; j--) {
                if (temp[j] == ' ' || temp[j] == 0x0A || temp[j] == '\0') {
                    temp[j] = '\0';
                } else {
                    break;
                }
            }
            
            if (strlen(temp) > 0) {
                strcpy(serial, temp);
                break;
            }
        }
    }
}

// Parse EDID structure and output JSON
void parse_edid_to_json(BYTE* edid_data, size_t edid_size, const char* device_path) {
    if (edid_size < 128) {
        printf("    {\"device\": \"%s\", \"error\": \"EDID too small\"}", device_path);
        return;
    }
    
    EDID_128* edid = (EDID_128*)edid_data;
    
    // Verify EDID header
    if (edid->header[0] != 0x00 || edid->header[1] != 0xFF || 
        edid->header[2] != 0xFF || edid->header[3] != 0xFF) {
        printf("    {\"device\": \"%s\", \"error\": \"Invalid EDID header\"}", device_path);
        return;
    }
    
    // Extract info
    char mfg_name[4];
    decode_manufacturer_id(edid->manufacturer_id, mfg_name);
    
    char monitor_name[64];
    extract_monitor_name(edid->descriptors, monitor_name);
    
    char serial_number[64];
    extract_serial_number(edid->descriptors, serial_number);
    
    int manufacturing_year = edid->year + 1990;
    int product_id = edid->product_code;
    
    printf("    {\n");
    printf("      \"device\": \"%s\",\n", device_path);
    printf("      \"monitor_name\": \"%s\",\n", monitor_name);
    printf("      \"manufacturer\": \"%s\",\n", mfg_name);
    printf("      \"manufacturer_id\": %d,\n", edid->manufacturer_id);
    printf("      \"product_code\": %d,\n", product_id);
    printf("      \"serial_number\": \"%s\",\n", serial_number);
    printf("      \"manufacturing_year\": %d,\n", manufacturing_year);
    printf("      \"manufacturing_week\": %d,\n", edid->week);
    printf("      \"edid_version\": \"%d.%d\",\n", edid->edid_version, edid->edid_revision);
    printf("      \"input_type\": \"%s\",\n", (edid->input_type & 0x80) ? "Digital" : "Analog");
    printf("      \"physical_height_cm\": %d,\n", edid->max_v_size);
    printf("      \"physical_width_cm\": %d,\n", edid->max_h_size);
    printf("      \"gamma\": %.2f\n", (edid->gamma + 100) / 100.0);
    printf("    }");
}

// Registry-based EDID retrieval for connected displays
void enumerate_edid_from_registry() {
    HKEY hkeyDevEnum = NULL;
    LONG ret = RegOpenKeyExA(HKEY_LOCAL_MACHINE, 
        "SYSTEM\\CurrentControlSet\\Enum\\DISPLAY", 
        0, KEY_READ, &hkeyDevEnum);
    
    if (ret != ERROR_SUCCESS) {
        return;
    }
    
    DWORD index = 0;
    CHAR display_id[256];
    DWORD display_id_size;
    int first = 1;
    
    while (1) {
        display_id_size = sizeof(display_id);
        ret = RegEnumKeyExA(hkeyDevEnum, index, display_id, &display_id_size, 
                            NULL, NULL, NULL, NULL);
        
        if (ret != ERROR_SUCCESS) break;
        
        // Open device registry key
        HKEY hkeyDevice = NULL;
        CHAR device_path[512];
        sprintf(device_path, "SYSTEM\\CurrentControlSet\\Enum\\DISPLAY\\%s", display_id);
        
        ret = RegOpenKeyExA(HKEY_LOCAL_MACHINE, device_path, 0, KEY_READ, &hkeyDevice);
        if (ret == ERROR_SUCCESS) {
            // Enumerate sub-keys (connected monitors)
            DWORD monitor_index = 0;
            CHAR monitor_id[256];
            DWORD monitor_id_size;
            
            while (1) {
                monitor_id_size = sizeof(monitor_id);
                ret = RegEnumKeyExA(hkeyDevice, monitor_index, monitor_id, &monitor_id_size,
                                   NULL, NULL, NULL, NULL);
                
                if (ret != ERROR_SUCCESS) break;
                
                // Read EDID value
                HKEY hkeyMonitor = NULL;
                CHAR monitor_path[512];
                sprintf(monitor_path, "SYSTEM\\CurrentControlSet\\Enum\\DISPLAY\\%s\\%s", 
                        display_id, monitor_id);
                
                ret = RegOpenKeyExA(HKEY_LOCAL_MACHINE, monitor_path, 0, KEY_READ, &hkeyMonitor);
                if (ret == ERROR_SUCCESS) {
                    BYTE edid_data[256];
                    DWORD edid_size = sizeof(edid_data);
                    
                    ret = RegQueryValueExA(hkeyMonitor, "EDID", NULL, NULL, 
                                          edid_data, &edid_size);
                    
                    if (ret == ERROR_SUCCESS && edid_size > 0) {
                        if (!first) printf(",\n");
                        parse_edid_to_json(edid_data, edid_size, display_id);
                        first = 0;
                    }
                    
                    RegCloseKey(hkeyMonitor);
                }
                
                monitor_index++;
            }
            
            RegCloseKey(hkeyDevice);
        }
        
        index++;
    }
    
    RegCloseKey(hkeyDevEnum);
}

int main() {
    printf("{\n");
    printf("  \"edid_devices\": [\n");
    
    enumerate_edid_from_registry();
    
    printf("\n  ]\n");
    printf("}\n");
    
    return 0;
}
