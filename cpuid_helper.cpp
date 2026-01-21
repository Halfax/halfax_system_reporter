#include <windows.h>
#include <stdio.h>
#include <intrin.h>
#include <string.h>
#include <stdlib.h>
#include <wbemidl.h>
#include <comdef.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "wbemuuid.lib")

// Structure to hold CPUID results
typedef struct {
    int eax, ebx, ecx, edx;
} CPUIDResult;

// Forward declaration
void read_cpuid(int leaf, int subleaf, CPUIDResult* result);

// Cache info structure
typedef struct {
    int size_kb;
    int assoc;
    int line_size;
    int partitions;
    int sets;
    int cores_sharing;     // Number of cores sharing this cache
    int is_inclusive;      // 1=inclusive, 0=exclusive, -1=unknown
} CacheInfo;

// Per-core APIC topology structure
typedef struct {
    int apic_id;           // APIC ID of this core
    int core_type;         // 0=reserved, 1=performance, 2=efficiency, 3+=reserved
    int core_index;        // Index within core type
    int logical_index;     // Logical processor number
    int package_id;        // Package/socket ID
    int tile_id;           // Tile ID (Meteor Lake)
    int die_id;            // Die ID
    int module_id;         // Module ID (cluster of cores)
} PerCoreTopology;

// Simple vendor detection
enum CpuVendor { VENDOR_UNKNOWN, VENDOR_INTEL, VENDOR_AMD };

CpuVendor get_cpu_vendor() {
    CPUIDResult r;
    read_cpuid(0, 0, &r);
    char vendor[13] = {0};
    memcpy(vendor + 0, &r.ebx, 4);
    memcpy(vendor + 4, &r.edx, 4);
    memcpy(vendor + 8, &r.ecx, 4);
    if (strncmp(vendor, "GenuineIntel", 12) == 0) return VENDOR_INTEL;
    if (strncmp(vendor, "AuthenticAMD", 12) == 0) return VENDOR_AMD;
    return VENDOR_UNKNOWN;
}

// Read CPUID leaf and return results
void read_cpuid(int leaf, int subleaf, CPUIDResult* result) {
    int cpuInfo[4] = {0};
    __cpuidex(cpuInfo, leaf, subleaf);
    
    result->eax = cpuInfo[0];
    result->ebx = cpuInfo[1];
    result->ecx = cpuInfo[2];
    result->edx = cpuInfo[3];
}

// Get max CPUID support
int get_max_cpuid_leaf() {
    CPUIDResult result;
    read_cpuid(0, 0, &result);
    return result.eax;
}

// Get turbo ratio limits via CPUID 0x16 (Intel Turbo Ratio Info Leaf)
// Returns base_freq, max_turbo_1c, max_turbo_ac (in MHz)
int get_turbo_ratios(int* base_freq, int* max_turbo_1c, int* max_turbo_ac) {
    CPUIDResult result;
    int max_leaf = get_max_cpuid_leaf();
    
    // CPUID 0x16 is available if max_leaf >= 0x16
    if (max_leaf < 0x16) {
        return 0;  // Not available
    }
    
    read_cpuid(0x16, 0, &result);
    
    // EAX[15:0] = Base frequency (in MHz)
    *base_freq = result.eax & 0xFFFF;
    
    // EBX[15:0] = Max frequency, single-core (in MHz)
    *max_turbo_1c = result.ebx & 0xFFFF;
    
    // ECX[15:0] = Max frequency, multi-core (in MHz)
    *max_turbo_ac = result.ecx & 0xFFFF;
    
    return 1;  // Success
}

// WMI fallback for MaxClockSpeed (in MHz)
int get_max_clock_wmi() {
    HRESULT hr;
    IWbemLocator* pLoc = NULL;
    IWbemServices* pSvc = NULL;
    IEnumWbemClassObject* pEnumerator = NULL;
    IWbemClassObject* pclsObj = NULL;
    VARIANT vtProp;
    ULONG uReturn = 0;
    int max_mhz = 0;

    hr = CoInitializeEx(0, COINIT_MULTITHREADED);
    if (FAILED(hr)) return 0;

    hr = CoInitializeSecurity(NULL, -1, NULL, NULL,
                              RPC_C_AUTHN_LEVEL_DEFAULT,
                              RPC_C_IMP_LEVEL_IMPERSONATE,
                              NULL, EOAC_NONE, NULL);
    // Even if security init fails because already initialized, keep going

    hr = CoCreateInstance(CLSID_WbemLocator, 0, CLSCTX_INPROC_SERVER,
                          IID_IWbemLocator, (LPVOID*)&pLoc);
    if (FAILED(hr) || !pLoc) {
        CoUninitialize();
        return 0;
    }

    hr = pLoc->ConnectServer(_bstr_t(L"ROOT\\CIMV2"), NULL, NULL, 0, 0, 0, 0, &pSvc);
    if (FAILED(hr) || !pSvc) {
        pLoc->Release();
        CoUninitialize();
        return 0;
    }

    hr = CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, NULL,
                           RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE,
                           NULL, EOAC_NONE);

    hr = pSvc->ExecQuery(_bstr_t(L"WQL"),
                         _bstr_t(L"SELECT MaxClockSpeed FROM Win32_Processor"),
                         WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY,
                         NULL, &pEnumerator);
    if (FAILED(hr) || !pEnumerator) {
        pSvc->Release();
        pLoc->Release();
        CoUninitialize();
        return 0;
    }

    if (pEnumerator->Next(WBEM_INFINITE, 1, &pclsObj, &uReturn) == S_OK) {
        VariantInit(&vtProp);
        if (SUCCEEDED(pclsObj->Get(L"MaxClockSpeed", 0, &vtProp, 0, 0))) {
            if ((vtProp.vt == VT_I4 || vtProp.vt == VT_UI4) && vtProp.lVal > 0) {
                max_mhz = (int)vtProp.lVal;
            }
        }
        VariantClear(&vtProp);
        pclsObj->Release();
    }

    if (pEnumerator) pEnumerator->Release();
    if (pSvc) pSvc->Release();
    if (pLoc) pLoc->Release();
    CoUninitialize();
    return max_mhz;
}

// Gather the 48-byte processor brand string from CPUID leaves 0x80000002-4
void get_brand_string(char* buffer, size_t buffer_size) {
    if (!buffer || buffer_size < 49) {
        return;
    }

    int max_ext = 0;
    CPUIDResult result;
    read_cpuid(0x80000000, 0, &result);
    max_ext = result.eax;

    if (max_ext < 0x80000004) {
        buffer[0] = '\0';
        return;
    }

    int* buf_int = reinterpret_cast<int*>(buffer);
    for (int i = 0; i < 3; ++i) {
        read_cpuid(0x80000002 + i, 0, &result);
        buf_int[i * 4 + 0] = result.eax;
        buf_int[i * 4 + 1] = result.ebx;
        buf_int[i * 4 + 2] = result.ecx;
        buf_int[i * 4 + 3] = result.edx;
    }
    buffer[48] = '\0';
}

// Parse frequency (MHz) from brand string; returns 1 if parsed
int parse_frequency_from_brand(const char* brand, int* freq_mhz_out) {
    if (!brand || !freq_mhz_out) return 0;

    // Uppercase copy for easier matching
    char upper[128] = {0};
    size_t len = strlen(brand);
    if (len > sizeof(upper) - 1) len = sizeof(upper) - 1;
    for (size_t i = 0; i < len; ++i) {
        char c = brand[i];
        if (c >= 'a' && c <= 'z') c = (char)(c - 32);
        upper[i] = c;
    }
    upper[len] = '\0';

    // Look for "GHZ" or "MHZ"
    const char* ghz = strstr(upper, "GHZ");
    const char* mhz = strstr(upper, "MHZ");

    const char* target = ghz ? ghz : mhz;
    if (!target) return 0;

    // Walk backward to find the number start
    const char* p = target - 1;
    while (p >= upper && ((*p >= '0' && *p <= '9') || *p == '.' || *p == ' ')) {
        p--;
    }
    p++; // move to first digit/space

    char number[32] = {0};
    size_t nlen = 0;
    while (p < target && nlen < sizeof(number) - 1) {
        if ((*p >= '0' && *p <= '9') || *p == '.') {
            number[nlen++] = *p;
        }
        p++;
    }
    number[nlen] = '\0';

    if (nlen == 0) return 0;

    double val = atof(number);
    if (val <= 0.0) return 0;

    int mhz_val = 0;
    if (ghz && ghz == target) {
        mhz_val = (int)(val * 1000.0 + 0.5);
    } else {
        mhz_val = (int)(val + 0.5);
    }

    *freq_mhz_out = mhz_val;
    return 1;
}

// Intel cache detection using CPUID leaf 0x4 (iterating subleafs)
void detect_intel_caches(CacheInfo* l1d, CacheInfo* l1i, CacheInfo* l2, CacheInfo* l3) {
    if (!l1d || !l1i || !l2 || !l3) return;
    for (int ecx = 0; ecx < 32; ++ecx) {
        CPUIDResult r;
        read_cpuid(4, ecx, &r);
        int cache_type = r.eax & 0x1F; // 0=invalid
        if (cache_type == 0) break;
        int level = (r.eax >> 5) & 0x7;
        int line_size = (r.ebx & 0xFFF) + 1;           // bits 11:0
        int partitions = ((r.ebx >> 12) & 0x3FF) + 1;  // bits 21:12
        int ways = ((r.ebx >> 22) & 0x3FF) + 1;        // bits 31:22
        int sets = r.ecx + 1;

        long long size_bytes = (long long)ways * partitions * line_size * sets;
        int size_kb = (int)(size_bytes / 1024);

        // Debug: extract APIC field for inspection
        unsigned int apic_bits = (r.eax >> 14) & 0xFFF;
        CacheInfo* target = NULL;
        if (cache_type == 1) { // Data cache
            if (level == 1) target = l1d;
        } else if (cache_type == 2) { // Instruction cache
            if (level == 1) target = l1i;
        } else if (cache_type == 3) { // Unified
            if (level == 1) target = l1d;
            else if (level == 2) target = l2;
            else if (level == 3) target = l3;
        }

        if (target && target->size_kb == 0) { // Only fill once
            target->size_kb = size_kb;
            target->assoc = ways;
            target->line_size = line_size;
            target->partitions = partitions;
            target->sets = sets;
            // EAX bits 25:14: Contains (num_cores_sharing - 1) encoded in APIC ID space
            // Many tools just use: ((EAX >> 26) & 0x3F) + 1
            // But safer is: ((EAX >> 14) & 0xFFF) for raw APIC ID mask, then count set bits
            unsigned int apic_mask = (r.eax >> 14) & 0xFFF;  // 12-bit field
            // Count consecutive set bits from LSB (this gives log2 of core count)
            int bit_count = 0;
            for (int i = 0; i < 12 && ((apic_mask >> i) & 1); i++) {
                bit_count++;
            }
            target->cores_sharing = (bit_count > 0) ? (1 << bit_count) : 1;
            // Cache is inclusive: bit 9
            target->is_inclusive = (r.eax >> 9) & 1;
        }
    }
}

// AMD cache detection using extended leaves 0x80000005/0x80000006
void detect_amd_caches(CacheInfo* l1d, CacheInfo* l1i, CacheInfo* l2, CacheInfo* l3) {
    if (!l1d || !l1i || !l2 || !l3) return;
    CPUIDResult r5, r6;
    read_cpuid(0x80000005, 0, &r5);
    read_cpuid(0x80000006, 0, &r6);

    // AMD doesn't expose associativity/line size in extended leaves; use sizes only
    int l1d_val = (r5.ecx >> 24) & 0xFF; // KB
    int l1i_val = (r5.edx >> 24) & 0xFF; // KB
    int l2_val  = (r6.ecx >> 16) & 0xFFFF; // KB
    int l3_chunks = (r6.edx >> 18) & 0x3FFF; // units of 512KB
    int l3_val = l3_chunks * 512; // KB

    if (l1d_val > 0) {
        l1d->size_kb = l1d_val;
        l1d->cores_sharing = -1; // AMD doesn't expose this
        l1d->is_inclusive = -1;
    }
    if (l1i_val > 0) {
        l1i->size_kb = l1i_val;
        l1i->cores_sharing = -1;
        l1i->is_inclusive = -1;
    }
    if (l2_val > 0) {
        l2->size_kb = l2_val;
        l2->cores_sharing = -1;
        l2->is_inclusive = -1;
    }
    if (l3_val > 0) {
        l3->size_kb = l3_val;
        l3->cores_sharing = -1;
        l3->is_inclusive = -1;
    }
}

// Detect per-core APIC ID topology using CPUID 0xB (Intel) or 0x1F (Meteor Lake)
// CRITICAL: Must set thread affinity to each logical processor to get unique APIC IDs
void detect_apic_topology(PerCoreTopology* topo_array, int* num_cores) {
    if (!topo_array || !num_cores) return;
    *num_cores = 0;
    
    CPUIDResult r0;
    read_cpuid(0, 0, &r0);
    int max_leaf = r0.eax;
    
    // Try CPUID 0x1F first (Meteor Lake+ with tile info), fall back to 0xB
    int topo_leaf = (max_leaf >= 0x1F) ? 0x1F : 0xB;
    
    if (max_leaf < 0xB) return; // CPUID 0xB/0x1F not supported
    
    // Step 1: Use GetLogicalProcessorInformationEx to enumerate all logical processors
    DWORD buffer_size = 0;
    GetLogicalProcessorInformationEx(RelationProcessorCore, NULL, &buffer_size);
    if (buffer_size == 0) return;
    
    BYTE* buffer = (BYTE*)malloc(buffer_size);
    if (!buffer) return;
    
    if (!GetLogicalProcessorInformationEx(RelationProcessorCore, 
        (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)buffer, &buffer_size)) {
        free(buffer);
        return;
    }
    
    // Parse the returned structures to count logical processors
    DWORD offset = 0;
    int total_logical_processors = 0;
    
    while (offset < buffer_size) {
        PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX info = 
            (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)(buffer + offset);
        
        if (info->Relationship == RelationProcessorCore) {
            // Count how many bits are set in the GroupMask (each bit = 1 logical processor)
            for (WORD group = 0; group < info->Processor.GroupCount; group++) {
                KAFFINITY mask = info->Processor.GroupMask[group].Mask;
                while (mask) {
                    if (mask & 1) total_logical_processors++;
                    mask >>= 1;
                }
            }
        }
        
        offset += info->Size;
    }
    
    // Step 2: For each logical processor, set thread affinity and read CPUID
    HANDLE current_thread = GetCurrentThread();
    DWORD_PTR original_affinity = SetThreadAffinityMask(current_thread, 1);
    
    for (int lp = 0; lp < total_logical_processors && *num_cores < 256; lp++) {
        // Set thread affinity to logical processor 'lp'
        DWORD_PTR affinity_mask = (DWORD_PTR)1 << lp;
        
        if (SetThreadAffinityMask(current_thread, affinity_mask) == 0) {
            // Failed to set affinity - skip this LP
            continue;
        }
        
        // Small delay to ensure thread migration completes
        Sleep(1);
        
        // Step 3: Execute CPUID 0xB/0x1F on THIS specific logical processor
        CPUIDResult r;
        read_cpuid(topo_leaf, 0, &r);  // Subleaf 0 for SMT level
        
        // EDX contains the x2APIC ID for this logical processor
        int apic_id = r.edx;
        
        // Decode topology levels by iterating subleaves
        int smt_bits = 0, core_bits = 0, tile_bits = 0;
        
        for (int subleaf = 0; subleaf < 8; subleaf++) {
            CPUIDResult r_sub;
            read_cpuid(topo_leaf, subleaf, &r_sub);
            
            int level_type = (r_sub.ecx >> 8) & 0xFF;  // ECX bits 15:8 = level type
            int shift_bits = r_sub.eax & 0x1F;          // EAX bits 4:0 = bits to shift
            
            if (level_type == 0) break;  // End of topology levels
            
            if (level_type == 1) {       // SMT (thread) level
                smt_bits = shift_bits;
            } else if (level_type == 2) { // Core level
                core_bits = shift_bits;
            } else if (level_type == 5) { // Tile/die level (0x1F only)
                tile_bits = shift_bits;
            }
        }
        
        // Decode APIC ID fields
        int smt_mask = (1 << smt_bits) - 1;
        int core_mask = ((1 << core_bits) - 1) & ~smt_mask;
        
        topo_array[*num_cores].apic_id = apic_id;
        topo_array[*num_cores].logical_index = lp;
        topo_array[*num_cores].package_id = apic_id >> core_bits;
        topo_array[*num_cores].core_index = (apic_id & core_mask) >> smt_bits;
        topo_array[*num_cores].tile_id = (tile_bits > 0) ? (apic_id >> tile_bits) : 0;
        topo_array[*num_cores].die_id = 0;     // Could extract from higher levels
        topo_array[*num_cores].module_id = 0;  // Could extract from CPUID 0x1F level 3
        
        // Extract core type from CPUID 0x1A if available (P-core vs E-core, Intel hybrid)
        if (max_leaf >= 0x1A) {
            CPUIDResult r1a;
            read_cpuid(0x1A, 0, &r1a);
            // Bits 31:24 = core type (0x20=performance/Atom, 0x40=efficiency/Core)
            topo_array[*num_cores].core_type = (r1a.eax >> 24) & 0xFF;
        } else {
            topo_array[*num_cores].core_type = 0;  // Unknown
        }
        
        (*num_cores)++;
    }
    
    // Restore original thread affinity
    if (original_affinity != 0) {
        SetThreadAffinityMask(current_thread, original_affinity);
    }
    
    free(buffer);
}

// Derive cache sharing groups from APIC IDs and cache topology
// For each cache level (L1D, L2, L3), we group cores that share the same cache instance
void derive_cache_sharing_groups(PerCoreTopology* topo_array, int num_cores,
                                 CacheInfo l1d, CacheInfo l2, CacheInfo l3,
                                 int** l1d_groups, int** l2_groups, int** l3_groups) {
    if (!topo_array || num_cores == 0) return;
    if (!l1d_groups || !l2_groups || !l3_groups) return;
    
    // Allocate group ID arrays
    *l1d_groups = (int*)malloc(num_cores * sizeof(int));
    *l2_groups = (int*)malloc(num_cores * sizeof(int));
    *l3_groups = (int*)malloc(num_cores * sizeof(int));
    
    if (!*l1d_groups || !*l2_groups || !*l3_groups) return;
    
    // Initialize all to -1 (no group assigned)
    for (int i = 0; i < num_cores; i++) {
        (*l1d_groups)[i] = -1;
        (*l2_groups)[i] = -1;
        (*l3_groups)[i] = -1;
    }
    
    // Derive bit masks for each cache level
    // L1D: typically per-core (shared by SMT threads only)
    // L2: shared by cluster of cores (e.g., 2-8 cores)
    // L3: shared by entire die/tile (many cores)
    
    // Calculate shift amounts based on cores_sharing
    // If L1D shared by 2 cores → 1 bit shift (group = APIC >> 1)
    // If L2 shared by 8 cores → 3 bit shift (group = APIC >> 3)
    // If L3 shared by 128 cores → 7 bit shift (group = APIC >> 7)
    
    auto calc_shift = [](int cores_sharing) -> int {
        if (cores_sharing <= 1) return 0;
        int shift = 0;
        int val = cores_sharing;
        while (val > 1) {
            shift++;
            val >>= 1;
        }
        return shift;
    };
    
    int l1d_shift = calc_shift(l1d.cores_sharing);
    int l2_shift = calc_shift(l2.cores_sharing);
    int l3_shift = calc_shift(l3.cores_sharing);
    
    // Assign group IDs based on shifted APIC IDs
    for (int i = 0; i < num_cores; i++) {
        int apic = topo_array[i].apic_id;
        
        // L1D group: shift by SMT bits (typically 1 bit for 2-way SMT)
        (*l1d_groups)[i] = apic >> l1d_shift;
        
        // L2 group: shift by cluster bits
        (*l2_groups)[i] = apic >> l2_shift;
        
        // L3 group: shift by tile/die bits
        (*l3_groups)[i] = apic >> l3_shift;
    }
}

int main(void) {
    int base_mhz = 0, max_mhz = 0, bus_mhz = 0;
    int turbo_supported = 0;
    int success = 0;
    char brand[64] = {0};
    get_brand_string(brand, sizeof(brand));
    
    // Detect vendor for cache handling
    CpuVendor vendor = get_cpu_vendor();

    // Check if CPUID leaf 0x16 is supported
    int max_leaf = get_max_cpuid_leaf();
    
    if (max_leaf >= 0x16) {
        // CPUID leaf 0x16: Processor Frequency Information
        // Returns:
        // EAX[15:0] = Base frequency (in MHz)
        // EBX[15:0] = Max frequency (in MHz)  
        // ECX[15:0] = Bus reference frequency (in MHz)
        
        CPUIDResult result;
        read_cpuid(0x16, 0, &result);
        
        base_mhz = result.eax & 0xFFFF;
        max_mhz  = result.ebx & 0xFFFF;
        bus_mhz  = result.ecx & 0xFFFF;
        
        if (base_mhz > 0 && max_mhz > 0) {
            success = 1;
        }
    }
    
    // Optional CPUID 0x15: core crystal clock and ratios (not universal)
    if (max_leaf >= 0x15) {
        CPUIDResult r15;
        read_cpuid(0x15, 0, &r15);
        if (r15.eax > 0 && r15.ebx > 0 && r15.ecx > 0) {
            double crystal_mhz = r15.ecx / 1e6;          // ECX: crystal clock Hz
            double ratio = (double)r15.ebx / (double)r15.eax; // EBX/EAX
            double derived_base = crystal_mhz * ratio;

            // Use bus clock from crystal if we don't already have one
            if (bus_mhz == 0) {
                bus_mhz = (int)(crystal_mhz + 0.5);
            }

            // If base still missing, use derived value
            if (base_mhz == 0 && derived_base > 0.0) {
                base_mhz = (int)(derived_base + 0.5);
                if (max_mhz == 0) {
                    max_mhz = base_mhz; // conservative
                }
                success = 1;
            }
        }
    }

    // Try CPUID 0x06 for turbo and features
    if (max_leaf >= 0x06) {
        CPUIDResult result;
        read_cpuid(0x06, 0, &result);
        turbo_supported = (result.eax & 0x02) ? 1 : 0;
    }

    // Fallback: parse brand string for base frequency (works on most Intel/AMD)
    if (!success || base_mhz == 0 || max_mhz == 0) {
        int parsed_mhz = 0;
        if (parse_frequency_from_brand(brand, &parsed_mhz) && parsed_mhz > 0) {
            if (base_mhz == 0) base_mhz = parsed_mhz;
            if (max_mhz == 0) max_mhz = parsed_mhz;
            success = 1; // treat as successful because brand gives nominal/base
        }
    }

    // Final fallback: WMI MaxClockSpeed if still missing
    if (max_mhz == 0) {
        int wmi_max = get_max_clock_wmi();
        if (wmi_max > 0) {
            max_mhz = wmi_max;
            if (base_mhz == 0) base_mhz = wmi_max; // conservative use same as nominal
            success = 1;
        }
    }
    
    // If CPUID 0x16 didn't work, try to get base from turbo boost capability
    // Fallback: read from processor brand string or other sources
    if (!success && max_leaf >= 0x80000002) {
        // For now, just report that detection failed gracefully
        // Python code will handle WMI fallback
        success = 0;
    }
    
    // Cache detection (vendor-specific)
    CacheInfo l1d = {0}, l1i = {0}, l2 = {0}, l3 = {0};
    if (vendor == VENDOR_INTEL) {
        detect_intel_caches(&l1d, &l1i, &l2, &l3);
    } else if (vendor == VENDOR_AMD) {
        detect_amd_caches(&l1d, &l1i, &l2, &l3);
    }
    
    // APIC topology detection
    PerCoreTopology topo_array[256] = {0};
    int num_logical_cores = 0;
    detect_apic_topology(topo_array, &num_logical_cores);
    
    // Derive cache sharing groups
    int* l1d_groups = NULL;
    int* l2_groups = NULL;
    int* l3_groups = NULL;
    derive_cache_sharing_groups(topo_array, num_logical_cores, l1d, l2, l3,
                                &l1d_groups, &l2_groups, &l3_groups);

    // Get turbo ratio limits (CPUID 0x16)
    int turbo_base = 0, turbo_1c = 0, turbo_ac = 0;
    int turbo_ratios_available = get_turbo_ratios(&turbo_base, &turbo_1c, &turbo_ac);
    
    // Output JSON format
    printf("{");
    printf("\"base_mhz\": %d, ", base_mhz);
    printf("\"max_mhz\": %d, ", max_mhz);
    printf("\"bus_mhz\": %d, ", bus_mhz);
    printf("\"turbo_supported\": %d, ", turbo_supported);
    
    // Add CPUID 0x16 turbo information if available
    if (turbo_ratios_available) {
        printf("\"cpuid_base_freq_mhz\": %d, ", turbo_base);
        printf("\"cpuid_max_turbo_1c_mhz\": %d, ", turbo_1c);
        printf("\"cpuid_max_turbo_ac_mhz\": %d, ", turbo_ac);
    }
    
    // MSR status (user-mode process cannot access MSRs)
    printf("\"msr_access\": \"Not available (user-mode execution)\", ");
    
    printf("\"brand\": \"%s\", ", brand);
    
    // L1D cache details
    printf("\"l1d_kb\": %d, ", l1d.size_kb);
    if (l1d.size_kb > 0) {
        printf("\"l1d_assoc\": %d, ", l1d.assoc);
        printf("\"l1d_line\": %d, ", l1d.line_size);
        printf("\"l1d_partitions\": %d, ", l1d.partitions);
        printf("\"l1d_sets\": %d, ", l1d.sets);
        printf("\"l1d_cores_sharing\": %d, ", l1d.cores_sharing);
        printf("\"l1d_inclusive\": %d, ", l1d.is_inclusive);
    }
    
    // L1I cache details
    printf("\"l1i_kb\": %d, ", l1i.size_kb);
    if (l1i.size_kb > 0) {
        printf("\"l1i_assoc\": %d, ", l1i.assoc);
        printf("\"l1i_line\": %d, ", l1i.line_size);
        printf("\"l1i_partitions\": %d, ", l1i.partitions);
        printf("\"l1i_sets\": %d, ", l1i.sets);
        printf("\"l1i_cores_sharing\": %d, ", l1i.cores_sharing);
        printf("\"l1i_inclusive\": %d, ", l1i.is_inclusive);
    }
    
    // L2 cache details
    printf("\"l2_kb\": %d, ", l2.size_kb);
    if (l2.size_kb > 0) {
        printf("\"l2_assoc\": %d, ", l2.assoc);
        printf("\"l2_line\": %d, ", l2.line_size);
        printf("\"l2_partitions\": %d, ", l2.partitions);
        printf("\"l2_sets\": %d, ", l2.sets);
        printf("\"l2_cores_sharing\": %d, ", l2.cores_sharing);
        printf("\"l2_inclusive\": %d, ", l2.is_inclusive);
    }
    
    // L3 cache details
    printf("\"l3_kb\": %d, ", l3.size_kb);
    if (l3.size_kb > 0) {
        printf("\"l3_assoc\": %d, ", l3.assoc);
        printf("\"l3_line\": %d, ", l3.line_size);
        printf("\"l3_partitions\": %d, ", l3.partitions);
        printf("\"l3_sets\": %d, ", l3.sets);
        printf("\"l3_cores_sharing\": %d, ", l3.cores_sharing);
        printf("\"l3_inclusive\": %d, ", l3.is_inclusive);
    }
    printf("\"max_cpuid_leaf\": %d, ", max_leaf);
    printf("\"num_logical_cores\": %d, ", num_logical_cores);
    
    // Output APIC ID array with cache sharing groups
    printf("\"apic_ids\": [");
    for (int i = 0; i < num_logical_cores; i++) {
        if (i > 0) printf(", ");
        printf("{\"index\": %d, \"apic\": %d, \"core_type\": %d, \"l1d_group\": %d, \"l2_group\": %d, \"l3_group\": %d}", 
               topo_array[i].logical_index, 
               topo_array[i].apic_id, 
               topo_array[i].core_type,
               l1d_groups ? l1d_groups[i] : -1,
               l2_groups ? l2_groups[i] : -1,
               l3_groups ? l3_groups[i] : -1);
    }
    printf("], ");
    
    // Output cache sharing group summary
    // Count unique groups for each cache level
    int l1d_unique = 0, l2_unique = 0, l3_unique = 0;
    if (l1d_groups && l2_groups && l3_groups) {
        // Count unique L1D groups
        int seen_l1d[256] = {0};
        for (int i = 0; i < num_logical_cores; i++) {
            if (l1d_groups[i] >= 0 && l1d_groups[i] < 256 && !seen_l1d[l1d_groups[i]]) {
                seen_l1d[l1d_groups[i]] = 1;
                l1d_unique++;
            }
        }
        
        // Count unique L2 groups
        int seen_l2[256] = {0};
        for (int i = 0; i < num_logical_cores; i++) {
            if (l2_groups[i] >= 0 && l2_groups[i] < 256 && !seen_l2[l2_groups[i]]) {
                seen_l2[l2_groups[i]] = 1;
                l2_unique++;
            }
        }
        
        // Count unique L3 groups
        int seen_l3[256] = {0};
        for (int i = 0; i < num_logical_cores; i++) {
            if (l3_groups[i] >= 0 && l3_groups[i] < 256 && !seen_l3[l3_groups[i]]) {
                seen_l3[l3_groups[i]] = 1;
                l3_unique++;
            }
        }
    }
    
    printf("\"cache_sharing\": {");
    printf("\"l1d_instances\": %d, ", l1d_unique);
    printf("\"l2_instances\": %d, ", l2_unique);
    printf("\"l3_instances\": %d", l3_unique);
    printf("}, ");
    
    printf("\"success\": %d", success);
    printf("}\n");
    
    // Cleanup
    if (l1d_groups) free(l1d_groups);
    if (l2_groups) free(l2_groups);
    if (l3_groups) free(l3_groups);
    
    return 0;
}
