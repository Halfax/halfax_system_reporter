/*
 * SPD Helper - Reads memory SPD (Serial Presence Detect) data
 * Outputs timing information as JSON
 */

#include <windows.h>
#include <stdio.h>
#include <stdint.h>

// SPD EEPROM addresses (standard I2C addresses for DIMMs)
#define SPD_BASE_ADDR 0x50
#define MAX_DIMMS 8

// DDR4 SPD byte offsets
#define SPD_DDR4_DEVICE_TYPE 2
#define SPD_DDR4_MODULE_TYPE 3
#define SPD_DDR4_DENSITY 4
#define SPD_DDR4_SDRAM_WIDTH 12
#define SPD_DDR4_MODULE_ORG 12
#define SPD_DDR4_BUS_WIDTH 13
#define SPD_DDR4_TIMEBASE 17
#define SPD_DDR4_TCK_MIN 18
#define SPD_DDR4_CAS_1ST 20
#define SPD_DDR4_CAS_2ND 21
#define SPD_DDR4_CAS_3RD 22
#define SPD_DDR4_CAS_4TH 23
#define SPD_DDR4_TAA_MIN 24
#define SPD_DDR4_TRCD_MIN 25
#define SPD_DDR4_TRP_MIN 26
#define SPD_DDR4_TRAS_TRC 27
#define SPD_DDR4_TRC_MIN 28
#define SPD_DDR4_MANUFACTURER_ID_LSB 320
#define SPD_DDR4_MANUFACTURER_ID_MSB 321
#define SPD_DDR4_PART_NUMBER 329

typedef struct {
    int slot;
    int present;
    int size_mb;
    int speed_mhz;
    int configured_speed_mhz;
    int max_speed_mhz;
    char ddr_generation[16];
    char module_type[32];
    char form_factor[32];
    char jedec_profile[32];
    int rank;
    int ecc;
    int data_width;
    int total_width;
    int voltage_mv;
    char manufacturer[64];
    char part_number[32];
    char serial_number[32];
    char channel[8];
    int timings_available;
    int cl;
    int trcd;
    int trp;
    int tras;
    int trc;
    // Memory error information (SMBIOS Type 18)
    int error_type;
    int error_granularity;
    int error_operation;
    uint32_t error_count;
} SPDInfo;

// Trim leading and trailing whitespace from string
void trim_string(char *str) {
    if (!str) return;
    
    // Trim trailing whitespace
    int len = strlen(str);
    while (len > 0 && (str[len - 1] == ' ' || str[len - 1] == '\t' || str[len - 1] == '\n' || str[len - 1] == '\r')) {
        str[--len] = '\0';
    }
    
    // Trim leading whitespace
    int start = 0;
    while (str[start] && (str[start] == ' ' || str[start] == '\t' || str[start] == '\n' || str[start] == '\r')) {
        start++;
    }
    
    if (start > 0) {
        memmove(str, str + start, len - start + 1);
    }
}

// Get JEDEC profile string from DDR generation and speed
void get_jedec_profile(const char *ddr_gen, int speed_mhz, char *profile, int max_len) {
    if (!profile || max_len <= 0) return;
    
    // JEDEC profiles for common DDR speeds
    if (strstr(ddr_gen, "DDR4")) {
        switch (speed_mhz) {
            case 1200: snprintf(profile, max_len, "JEDEC (1200 MHz)"); break;
            case 1333: snprintf(profile, max_len, "JEDEC (1333 MHz)"); break;
            case 1466: snprintf(profile, max_len, "JEDEC (1466 MHz)"); break;
            case 1600: snprintf(profile, max_len, "JEDEC (1600 MHz)"); break;
            case 1866: snprintf(profile, max_len, "JEDEC (1866 MHz)"); break;
            case 2133: snprintf(profile, max_len, "JEDEC (2133 MHz)"); break;
            case 2400: snprintf(profile, max_len, "JEDEC (2400 MHz)"); break;
            case 2666: snprintf(profile, max_len, "XMP/DOCP"); break;
            case 2933: snprintf(profile, max_len, "XMP/DOCP"); break;
            case 3200: snprintf(profile, max_len, "JEDEC (3200 MHz)"); break;
            default: 
                if (speed_mhz < 1200) snprintf(profile, max_len, "Sub-JEDEC");
                else if (speed_mhz <= 3200) snprintf(profile, max_len, "JEDEC");
                else snprintf(profile, max_len, "XMP/DOCP");
                break;
        }
    } else if (strstr(ddr_gen, "DDR5")) {
        switch (speed_mhz) {
            case 3200: snprintf(profile, max_len, "JEDEC (3200 MHz)"); break;
            case 3600: snprintf(profile, max_len, "JEDEC (3600 MHz)"); break;
            case 4000: snprintf(profile, max_len, "JEDEC (4000 MHz)"); break;
            case 4400: snprintf(profile, max_len, "JEDEC (4400 MHz)"); break;
            case 4800: snprintf(profile, max_len, "JEDEC (4800 MHz)"); break;
            case 5600: snprintf(profile, max_len, "JEDEC (5600 MHz)"); break;
            case 6400: snprintf(profile, max_len, "JEDEC (6400 MHz)"); break;
            case 7200: snprintf(profile, max_len, "JEDEC (7200 MHz)"); break;
            default:
                if (speed_mhz <= 6400) snprintf(profile, max_len, "JEDEC");
                else snprintf(profile, max_len, "XMP/EXPO");
                break;
        }
    } else {
        snprintf(profile, max_len, "Unknown");
    }
}

// Normalize voltage based on DDR generation and speed (SMBIOS voltages can be wrong)
int normalize_voltage(const char *ddr_gen, int speed_mhz, int smbios_voltage) {
    // If SMBIOS voltage is clearly wrong or missing, use JEDEC spec
    // Otherwise prefer SMBIOS value as it's the actual reading
    
    if (smbios_voltage <= 0 || smbios_voltage > 2000) {
        // Use JEDEC spec defaults
        if (strstr(ddr_gen, "DDR5")) {
            // DDR5 standard is 1.1V (1100mV), but can vary with speed
            return 1100;
        } else if (strstr(ddr_gen, "DDR4")) {
            return 1200;
        } else if (strstr(ddr_gen, "DDR3")) {
            return (strstr(ddr_gen, "DDR3L") ? 1350 : 1500);
        }
        return 1200;  // Safe default
    }
    
    // For DDR5, if SMBIOS reports voltage but it's in an odd range,
    // normalize to standard JEDEC voltage (1.1V = 1100mV for DDR5)
    if (strstr(ddr_gen, "DDR5")) {
        // Valid DDR5 voltages: 1.1V (1100mV) is standard
        // Some SMBIOS implementations report wrong values
        if (smbios_voltage > 1150 && smbios_voltage < 2000) {
            // Likely a scaling error - normalize to 1100mV
            return 1100;
        }
    }
    
    return smbios_voltage;
}

// Try to read SPD via SMBIOS tables (Windows WMI)
int read_spd_from_smbios(SPDInfo spd_data[], int max_slots) {
    // This would use GetSystemFirmwareTable with 'RSMB' signature
    // For now, return 0 to indicate we need SMBus access
    return 0;
}

// Attempt to read SPD via direct SMBus access
// Note: This requires administrator privileges and may not work on all systems
int read_spd_direct(int dimm_index, uint8_t *buffer, int size) {
    // On Windows, direct SMBus access typically requires:
    // 1. A kernel driver (like WinRing0, InpOut32, etc.)
    // 2. Or going through the Intel/AMD chipset SMBus controller
    
    // For safety and portability, we'll indicate this needs privileges
    return 0;  // Not implemented without kernel driver
}

// Parse DDR4 SPD data
void parse_ddr4_spd(uint8_t *spd, SPDInfo *info) {
    if (spd[SPD_DDR4_DEVICE_TYPE] != 0x0C) {  // 0x0C = DDR4
        info->present = 0;
        return;
    }
    
    info->present = 1;
    
    // Calculate memory size
    int sdram_capacity = spd[SPD_DDR4_DENSITY] & 0x0F;
    int bus_width = 8 << (spd[SPD_DDR4_BUS_WIDTH] & 0x07);
    int sdram_width = 4 << (spd[SPD_DDR4_SDRAM_WIDTH] & 0x07);
    int ranks = 1 + ((spd[SPD_DDR4_MODULE_ORG] >> 3) & 0x07);
    
    int capacity_mb = (256 << sdram_capacity) * bus_width / sdram_width * ranks / 8;
    info->size_mb = capacity_mb;
    
    // Calculate speed and timings
    int mtb_dividend = spd[SPD_DDR4_TIMEBASE] & 0xFF;
    int mtb_divisor = spd[SPD_DDR4_TIMEBASE + 1] & 0xFF;
    if (mtb_dividend == 0) mtb_dividend = 125;  // Default MTB = 125ps
    if (mtb_divisor == 0) mtb_divisor = 1000;
    
    int tck_min = spd[SPD_DDR4_TCK_MIN];
    double tck_ns = (double)tck_min * mtb_dividend / mtb_divisor;
    info->speed_mhz = (int)(2000.0 / tck_ns);
    
    // Timings (in MTB units)
    int taa_min = spd[SPD_DDR4_TAA_MIN];
    int trcd_min = spd[SPD_DDR4_TRCD_MIN];
    int trp_min = spd[SPD_DDR4_TRP_MIN];
    int tras_min = ((spd[SPD_DDR4_TRAS_TRC] & 0x0F) << 8) | spd[SPD_DDR4_TRAS_TRC + 1];
    int trc_min = ((spd[SPD_DDR4_TRAS_TRC] & 0xF0) << 4) | spd[SPD_DDR4_TRC_MIN];
    
    // Convert to clock cycles
    info->cl = (int)((double)taa_min * mtb_dividend / mtb_divisor / tck_ns + 0.5);
    info->trcd = (int)((double)trcd_min * mtb_dividend / mtb_divisor / tck_ns + 0.5);
    info->trp = (int)((double)trp_min * mtb_dividend / mtb_divisor / tck_ns + 0.5);
    info->tras = (int)((double)tras_min * mtb_dividend / mtb_divisor / tck_ns + 0.5);
    info->trc = (int)((double)trc_min * mtb_dividend / mtb_divisor / tck_ns + 0.5);
    
    // Voltage (DDR4 typically 1.2V)
    info->voltage_mv = 1200;
    
    // Manufacturer (JEDEC ID)
    int mfg_id = (spd[SPD_DDR4_MANUFACTURER_ID_MSB] << 8) | spd[SPD_DDR4_MANUFACTURER_ID_LSB];
    const char *mfg_name = "Unknown";
    switch (mfg_id & 0x7F7F) {
        case 0x2C80: mfg_name = "Micron"; break;
        case 0xAD80: mfg_name = "SK Hynix"; break;
        case 0xCE80: mfg_name = "Samsung"; break;
        case 0x4304: mfg_name = "Corsair"; break;
        case 0x4F01: mfg_name = "Transcend"; break;
        case 0x9801: mfg_name = "Kingston"; break;
        case 0xCB04: mfg_name = "A-DATA"; break;
    }
    strncpy(info->manufacturer, mfg_name, sizeof(info->manufacturer) - 1);
    
    // Part number
    for (int i = 0; i < 18 && i < sizeof(info->part_number) - 1; i++) {
        char c = spd[SPD_DDR4_PART_NUMBER + i];
        info->part_number[i] = (c >= 32 && c < 127) ? c : ' ';
    }
    info->part_number[18] = '\0';
}

// Get string from SMBIOS string table
const char* get_smbios_string(uint8_t *struct_start, uint8_t length, uint8_t string_num) {
    if (string_num == 0) return "";
    
    uint8_t *str_ptr = struct_start + length;
    int current_str = 1;
    
    while (*str_ptr != 0 || *(str_ptr + 1) != 0) {
        if (current_str == string_num) {
            return (const char*)str_ptr;
        }
        while (*str_ptr != 0) str_ptr++;
        str_ptr++;
        current_str++;
    }
    return "";
}

// Try to read SPD via WMI MSSmBios_RawSMBiosTables
int read_spd_via_firmware_table(SPDInfo spd_data[], int max_slots) {
    DWORD size = GetSystemFirmwareTable('RSMB', 0, NULL, 0);
    if (size == 0) {
        return 0;
    }
    
    uint8_t *firmware_table = (uint8_t*)malloc(size);
    if (!firmware_table) {
        return 0;
    }
    
    DWORD result = GetSystemFirmwareTable('RSMB', 0, firmware_table, size);
    if (result == 0) {
        free(firmware_table);
        return 0;
    }
    
    // Parse SMBIOS structures looking for Type 17 (Memory Device)
    int found_dimms = 0;
    uint8_t *ptr = firmware_table + 8;  // Skip header
    uint8_t *end = firmware_table + size;
    
    while (ptr < end && found_dimms < max_slots) {
        if (ptr + 4 > end) break;
        
        uint8_t type = ptr[0];
        uint8_t length = ptr[1];
        uint8_t *struct_start = ptr;
        
        if (type == 17 && length >= 0x15) {  // Type 17 = Memory Device
            SPDInfo *info = &spd_data[found_dimms];
            memset(info, 0, sizeof(SPDInfo));
            
            info->slot = found_dimms;
            
            // Size
            uint16_t size_mb = *(uint16_t*)(ptr + 0x0C);
            if (size_mb == 0 || size_mb == 0xFFFF) {
                // Empty slot
                info->present = 0;
                found_dimms++;
                goto next_struct;
            }
            
            info->present = 1;
            info->size_mb = (size_mb == 0x7FFF) ? *(uint32_t*)(ptr + 0x1C) : size_mb;
            
            // Form Factor (offset 0x0E)
            uint8_t form_factor = ptr[0x0E];
            const char *form_str = "Unknown";
            switch (form_factor) {
                case 0x09: form_str = "DIMM"; break;
                case 0x0D: form_str = "SODIMM"; break;
                case 0x0C: form_str = "SO-DIMM"; break;
                case 0x0F: form_str = "FB-DIMM"; break;
                case 0x22: form_str = "LRDIMM"; break;
            }
            strncpy(info->form_factor, form_str, sizeof(info->form_factor) - 1);
            
            // Memory Type (offset 0x12)
            uint8_t mem_type = ptr[0x12];
            const char *ddr_gen = "Unknown";
            int default_voltage = 1200;
            switch (mem_type) {
                case 0x14: ddr_gen = "DDR"; default_voltage = 2500; break;
                case 0x15: ddr_gen = "DDR2"; default_voltage = 1800; break;
                case 0x18: ddr_gen = "DDR3"; default_voltage = 1500; break;
                case 0x1C: ddr_gen = "DDR3"; default_voltage = 1350; break;
                case 0x1A: ddr_gen = "DDR4"; default_voltage = 1200; break;
                case 0x22: ddr_gen = "DDR5"; default_voltage = 1100; break;
            }
            strncpy(info->ddr_generation, ddr_gen, sizeof(info->ddr_generation) - 1);
            
            // Data Width (offset 0x08) and Total Width (offset 0x06)
            info->data_width = *(uint16_t*)(ptr + 0x08);
            info->total_width = *(uint16_t*)(ptr + 0x06);
            
            // ECC detection: if total_width > data_width, it's ECC
            info->ecc = (info->total_width > info->data_width && info->total_width != 0xFFFF);
            
            // Type Detail (offset 0x13) - can show rank info
            uint16_t type_detail = *(uint16_t*)(ptr + 0x13);
            if (type_detail & (1 << 3)) {  // Bit 3 = Single rank
                info->rank = 1;
            } else if (type_detail & (1 << 4)) {  // Bit 4 = Dual rank
                info->rank = 2;
            } else if (type_detail & (1 << 5)) {  // Bit 5 = Quad rank
                info->rank = 4;
            } else {
                info->rank = 0;  // Unknown
            }
            
            // Speed (offset 0x15)
            if (length >= 0x15) {
                info->speed_mhz = *(uint16_t*)(ptr + 0x15);
            }
            
            // Configured Speed (offset 0x20 in SMBIOS 2.7+)
            if (length >= 0x22) {
                info->configured_speed_mhz = *(uint16_t*)(ptr + 0x20);
            } else {
                info->configured_speed_mhz = info->speed_mhz;
            }
            
            // Maximum Speed (offset 0x14 in newer versions)
            if (length >= 0x17) {
                info->max_speed_mhz = *(uint16_t*)(ptr + 0x14);
            } else {
                info->max_speed_mhz = info->speed_mhz;
            }
            
            // Voltage (offset 0x16 in older, or detected from type)
            if (length >= 0x17) {
                uint16_t min_voltage = *(uint16_t*)(ptr + 0x16);
                if (min_voltage != 0 && min_voltage != 0xFFFF) {
                    info->voltage_mv = min_voltage;
                } else {
                    info->voltage_mv = default_voltage;
                }
            } else {
                info->voltage_mv = default_voltage;
            }
            
            // Normalize voltage based on DDR generation
            info->voltage_mv = normalize_voltage(info->ddr_generation, info->configured_speed_mhz, info->voltage_mv);
            
            // Get JEDEC profile
            get_jedec_profile(info->ddr_generation, info->configured_speed_mhz, info->jedec_profile, sizeof(info->jedec_profile));
            
            // Manufacturer (string offset 0x17)
            const char *mfg = get_smbios_string(struct_start, length, ptr[0x17]);
            if (mfg && strlen(mfg) > 0) {
                strncpy(info->manufacturer, mfg, sizeof(info->manufacturer) - 1);
            } else {
                strcpy(info->manufacturer, "Unknown");
            }
            
            // Serial Number (string offset 0x18)
            const char *serial = get_smbios_string(struct_start, length, ptr[0x18]);
            if (serial && strlen(serial) > 0) {
                strncpy(info->serial_number, serial, sizeof(info->serial_number) - 1);
            } else {
                strcpy(info->serial_number, "N/A");
            }
            
            // Part Number (string offset 0x1A)
            const char *part = get_smbios_string(struct_start, length, ptr[0x1A]);
            if (part && strlen(part) > 0) {
                strncpy(info->part_number, part, sizeof(info->part_number) - 1);
                trim_string(info->part_number);
            } else {
                strcpy(info->part_number, "N/A");
            }
            
            // Determine channel (simple heuristic: even slots = A, odd = B)
            sprintf(info->channel, "%c", 'A' + (found_dimms % 2));
            
            // Module type derived from form factor and size
            if (strcmp(form_str, "SODIMM") == 0 || strcmp(form_str, "SO-DIMM") == 0) {
                strcpy(info->module_type, "Laptop/Small Form Factor");
            } else if (strcmp(form_str, "DIMM") == 0) {
                strcpy(info->module_type, "Desktop/Server");
            } else {
                strcpy(info->module_type, form_str);
            }
            
            // SMBIOS doesn't give us detailed timings, just basic info
            info->timings_available = 0;
            info->cl = 0;
            info->trcd = 0;
            info->trp = 0;
            info->tras = 0;
            info->trc = 0;
            
            found_dimms++;
        }
        
next_struct:
        // Move to next structure
        ptr += length;
        while (ptr + 1 < end && !(ptr[0] == 0 && ptr[1] == 0)) {
            ptr++;
        }
        ptr += 2;  // Skip double null terminator
    }
    
    free(firmware_table);
    return found_dimms;
}

// Get SMBIOS memory array information (Type 16)
int get_memory_array_info(char* method, int* max_capacity_mb, int* num_slots, char* ecc_type, int max_len) {
    DWORD table_size = 0;
    BYTE* firmware_table = NULL;
    BYTE* ptr = NULL;
    BYTE* end = NULL;
    int found = 0;
    
    if (!method || !max_capacity_mb || !num_slots || !ecc_type) return 0;
    
    strcpy(method, "SMBIOS");
    strcpy(ecc_type, "None");
    *max_capacity_mb = 0;
    *num_slots = 0;
    
    // Get SMBIOS tables
    firmware_table = (BYTE*)malloc(65536);
    if (!firmware_table) return 0;
    
    table_size = GetSystemFirmwareTable('RSMB', 0, firmware_table, 65536);
    if (table_size == 0 || table_size > 65536) {
        free(firmware_table);
        return 0;
    }
    
    ptr = firmware_table + 8;  // Skip SMBIOS header (8 bytes)
    end = firmware_table + table_size;
    
    while (ptr + 4 < end) {
        BYTE struct_type = ptr[0];
        BYTE length = ptr[1];
        
        if (struct_type == 0x7F) break;  // End-of-table marker
        if (length < 4 || ptr + length > end) break;
        
        // SMBIOS Type 16 = Memory Array
        if (struct_type == 16 && length >= 15) {
            // Byte 4-7: Max capacity in KB
            DWORD max_cap_kb = *(DWORD*)(ptr + 4);
            if (max_cap_kb > 0) {
                *max_capacity_mb = max_cap_kb / 1024;
            }
            
            // Byte 10: Number of memory devices
            BYTE num_devices = ptr[10];
            if (num_devices > 0) {
                *num_slots = num_devices;
            }
            
            // Byte 12: Memory error correction type
            BYTE ecc_byte = ptr[12];
            switch (ecc_byte) {
                case 1: strcpy(ecc_type, "Other"); break;
                case 2: strcpy(ecc_type, "Unknown"); break;
                case 3: strcpy(ecc_type, "None"); break;
                case 4: strcpy(ecc_type, "Parity"); break;
                case 5: strcpy(ecc_type, "Single-bit CRC"); break;
                case 6: strcpy(ecc_type, "Multi-bit ECC"); break;
                case 7: strcpy(ecc_type, "CRC"); break;
                default: strcpy(ecc_type, "Unknown"); break;
            }
            
            found = 1;
            break;
        }
        
        // Move to next structure
        ptr += length;
        while (ptr + 1 < end && !(ptr[0] == 0 && ptr[1] == 0)) {
            ptr++;
        }
        ptr += 2;  // Skip double null terminator
    }
    
    free(firmware_table);
    return found;
}

// Parse SMBIOS Type 18 (Memory Error Information) and update SPD data
void parse_memory_errors(SPDInfo spd_data[], int dimm_count) {
    DWORD table_size = GetSystemFirmwareTable('RSMB', 0, NULL, 0);
    if (table_size == 0) return;
    
    BYTE* firmware_table = (BYTE*)malloc(table_size);
    if (!firmware_table) return;
    
    DWORD result = GetSystemFirmwareTable('RSMB', 0, firmware_table, table_size);
    if (result == 0) {
        free(firmware_table);
        return;
    }
    
    // Initialize error fields
    for (int i = 0; i < dimm_count; i++) {
        spd_data[i].error_type = 0;
        spd_data[i].error_granularity = 0;
        spd_data[i].error_operation = 0;
        spd_data[i].error_count = 0;
    }
    
    // Parse Type 18 structures
    BYTE* ptr = firmware_table + 8;
    BYTE* end = firmware_table + table_size;
    
    while (ptr + 4 < end) {
        BYTE struct_type = ptr[0];
        BYTE length = ptr[1];
        
        if (struct_type == 0x7F) break;  // End-of-table
        if (length < 4 || ptr + length > end) break;
        
        // Type 18 = Memory Error Information
        if (struct_type == 18 && length >= 21) {
            // Byte 4: Error type
            BYTE error_type = ptr[4];
            
            // Byte 5: Error granularity
            BYTE error_granularity = ptr[5];
            
            // Byte 6: Error operation
            BYTE error_operation = ptr[6];
            
            // Bytes 7-10: Error count
            DWORD error_count = *(DWORD*)(ptr + 7);
            
            // Assign to first available DIMM (ideally we'd match via device handle, but Type 18 design is complex)
            if (dimm_count > 0) {
                spd_data[0].error_type = error_type;
                spd_data[0].error_granularity = error_granularity;
                spd_data[0].error_operation = error_operation;
                spd_data[0].error_count = error_count;
            }
        }
        
        // Move to next structure
        ptr += length;
        while (ptr + 1 < end && !(ptr[0] == 0 && ptr[1] == 0)) {
            ptr++;
        }
        ptr += 2;
    }
    
    free(firmware_table);
}

int main(int argc, char *argv[]) {
    SPDInfo spd_data[MAX_DIMMS] = {0};
    int dimm_count = 0;
    
    // Try reading via firmware tables (most portable)
    dimm_count = read_spd_via_firmware_table(spd_data, MAX_DIMMS);
    
    // Parse memory error information (SMBIOS Type 18)
    parse_memory_errors(spd_data, dimm_count);
    
    // Get memory array information
    char array_method[32] = {0};
    int max_capacity_mb = 0;
    int num_slots = 0;
    char ecc_type[32] = {0};
    int array_found = get_memory_array_info(array_method, &max_capacity_mb, &num_slots, ecc_type, sizeof(ecc_type));
    
    // Output JSON
    printf("{\n");
    printf("  \"method\": \"SMBIOS\",\n");
    printf("  \"note\": \"SPD EEPROM timing data is not exposed through SMBIOS. Access requires SMBus/I2C controller access, which is restricted on most systems.\",\n");
    
    // Add memory array information if available
    if (array_found) {
        printf("  \"memory_array\": {\n");
        printf("    \"max_capacity_mb\": %d,\n", max_capacity_mb);
        printf("    \"num_slots\": %d,\n", num_slots);
        printf("    \"system_ecc_type\": \"%s\"\n", ecc_type);
        printf("  },\n");
    }
    
    printf("  \"dimms\": [\n");
    
    for (int i = 0; i < dimm_count; i++) {
        SPDInfo *info = &spd_data[i];
        
        printf("    {\n");
        printf("      \"slot\": %d,\n", info->slot);
        printf("      \"present\": %s,\n", info->present ? "true" : "false");
        
        if (info->present) {
            printf("      \"size_mb\": %d,\n", info->size_mb);
            printf("      \"speed_mhz\": %d,\n", info->speed_mhz);
            
            if (info->configured_speed_mhz > 0) {
                printf("      \"configured_speed_mhz\": %d,\n", info->configured_speed_mhz);
            }
            if (info->max_speed_mhz > 0 && info->max_speed_mhz != info->speed_mhz) {
                printf("      \"max_speed_mhz\": %d,\n", info->max_speed_mhz);
            }
            
            printf("      \"ddr_generation\": \"%s\",\n", info->ddr_generation);
            printf("      \"jedec_profile\": \"%s\",\n", info->jedec_profile);
            printf("      \"form_factor\": \"%s\",\n", info->form_factor);
            printf("      \"module_type\": \"%s\",\n", info->module_type);
            printf("      \"channel\": \"%s\",\n", info->channel);
            
            if (info->rank > 0) {
                printf("      \"rank\": %d,\n", info->rank);
            } else {
                printf("      \"rank\": \"Unknown\",\n");
            }
            
            printf("      \"ecc\": %s,\n", info->ecc ? "true" : "false");
            
            if (info->data_width > 0 && info->data_width != 0xFFFF) {
                printf("      \"data_width\": %d,\n", info->data_width);
            }
            if (info->total_width > 0 && info->total_width != 0xFFFF) {
                printf("      \"total_width\": %d,\n", info->total_width);
            }
            
            printf("      \"voltage_mv\": %d,\n", info->voltage_mv);
            printf("      \"manufacturer\": \"%s\",\n", info->manufacturer);
            printf("      \"part_number\": \"%s\",\n", info->part_number);
            
            if (strlen(info->serial_number) > 0 && strcmp(info->serial_number, "N/A") != 0) {
                printf("      \"serial_number\": \"%s\",\n", info->serial_number);
            }
            
            printf("      \"timings_available\": false,\n");
            printf("      \"timings\": null,\n");
            
            // Memory error information (if available)
            if (info->error_count > 0 || info->error_type > 0) {
                printf("      \"memory_errors\": {\n");
                printf("        \"error_type\": %d,\n", info->error_type);
                printf("        \"error_granularity\": %d,\n", info->error_granularity);
                printf("        \"error_operation\": %d,\n", info->error_operation);
                printf("        \"error_count\": %u\n", info->error_count);
                printf("      },\n");
            }
            
            printf("      \"data_source\": \"SMBIOS\"\n");
        }
        
        printf("    }%s\n", (i < dimm_count - 1) ? "," : "");
    }
    
    printf("  ]\n");
    printf("}\n");
    
    return 0;
}
