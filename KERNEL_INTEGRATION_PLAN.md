# Kernel Helper Integration Plan - Code Review & Strategy

> **For all actionable engineering tasks and phase checklists, see [ACTIONABLE_TODO_CHECKLIST.md](ACTIONABLE_TODO_CHECKLIST.md). This file is for architecture and planning only.**

**Date:** January 24, 2026  
**Status:** REVIEW ONLY - NO CODE CHANGES  
**Purpose:** Analyze main.py architecture and plan kernel helper integration

---

## 1. Current Architecture Analysis

### 1.1 Mission & Design Philosophy (from README.md)

**Goal:** Provide **fact-based, comprehensive hardware and configuration telemetry** with accurate, low-level system information across platforms.

**Architectural Philosophy:** Layered approach with privilege escalation only when necessary:
1. **User-mode helpers first** - Standalone C/C++ helpers for accessible hardware
2. **Kernel driver as fallback** - Only for privileged operations (MSR, PCI, SMBus)
3. **Design Rule:** Augment user-mode helpers if accessible without kernel privileges; extend kernel driver only when ring-0 access is mandatory

**Critical Principle:** Never use kernel for what user-mode can do - minimize kernel complexity and attack surface.

### 1.2 Data Collection Model

**main.py** uses a **layered fallback architecture** with multiple data sources:

```
┌─────────────────────────────────────────────────────────────┐
│                     MAIN.PY COLLECTION                       │
├─────────────────────────────────────────────────────────────┤
│ Level 1: Python Libraries (psutil, cpuinfo, platform)       │
│   ├─ Cross-platform, always available                       │
│   ├─ Basic metrics: CPU count, memory, disk, network        │
│   └─ Limited hardware details                               │
├─────────────────────────────────────────────────────────────┤
│ Level 2: OS-Specific APIs                                   │
│   ├─ Windows: WMI (wmi module)                              │
│   ├─ Linux: /proc, /sys, dmidecode, lscpu, numactl          │
│   └─ Raspberry Pi: Special device tree parsing              │
├─────────────────────────────────────────────────────────────┤
│ Level 3: Helper Executables (subprocess calls)              │
│   ├─ cpuid_helper.exe - CPU frequencies, cache, APIC        │
│   ├─ spd_helper.exe - Memory SPD/SMBIOS data                │
│   ├─ nvme_helper.exe - NVMe SMART telemetry                 │
│   └─ edid_helper.exe - Display EDID information             │
├─────────────────────────────────────────────────────────────┤
│ Level 3.5: Privileged Helper (PLANNED - INTEGRATION TARGET) │
│   └─ kernel_helper - MSR, PCI, SMBus via kernel driver      │
│       ├─ Same subprocess + JSON pattern as Level 3          │
│       ├─ Optional - graceful degradation when unavailable   │
│       └─ Augments (not replaces) existing data sources      │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Helper Pattern Analysis

All existing helpers follow this consistent pattern:

#### **Pattern: External Helper Subprocess**
```python
def get_[feature]_helper_info():
    """Get [feature] from [helper].exe"""
    info = {
        'data': [],
        'available': False,
        'error': None
    }
    
    if not IS_WINDOWS:
        return info
    
    try:
        helper_path = os.path.join(os.path.dirname(__file__), '[helper].exe')
        if not os.path.exists(helper_path):
            return info
        
        result = subprocess.run([helper_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            info['data'] = data.get('[key]', [])
            info['available'] = True
            info['method'] = data.get('method', 'Unknown')
    except json.JSONDecodeError:
        info['error'] = "JSON parse error"
    exceCurrent Tab Status Assessment

**Tabs with Good Data:**
- ✅ Overview Tab - System identification, storage summary
- ✅ CPU Tab - Good basic info, but MSR data missing
- ✅ Memory Tab - Good with spd_helper integration
- ✅ Network Tab - Complete with psutil

**Tabs with Weak/Missing Data:**
- ⚠️ GPU Tab - WMI only, distorted by RDP, no VRAM/temp/power
- ⚠️ Storage Tab - NVMe helper exists but not fully integrated
- ⚠️ Display Tab - EDID helper exists but not integrated
- ❌ System Architecture Tab - Currently blank, needs topology

### 1.4 pt FileNotFoundError:
        info['error'] = "[helper].exe not found"
    except Exception as e:
        info['error'] = str(e)
    
    return info
```

**Examples:**
- `get_spd_helper_info()` → Line 543 → Returns DIMM details
- `get_nvme_helper_info()` → Line 1418 → Returns NVMe SMART data
- `get_edid_helper_info()` → Line 1450 → Returns display EDID
- `read_cpuid_frequencies()` → Line 640 → Returns CPU frequency data

### 1.3 Integration Points

Helpers are called from collection functions which feed into tab refresh:

```
refresh_all_tabs() (Line 2500)
  ├─ Calls: get_memory_extended_info()
  │   └─ Calls: get_spd_helper_info()  [Line 543]
  │       └─ Subprocess: spd_helper.exe
  │
  ├─ Calls: get_cpu_extended_info()
  │   └critical Issues from ingestion.txt

### 2.1 Batching MSR Reads (CRITICAL)

**Issue:** Unbatched MSR reads can cause performance problems.

**Current Risk:**
- Per-core temperature: 8-32 IOCTLs
- Power reads: 4-6 IOCTLs
- Turbo ratios: 1-2 IOCTLs
- Total: 50+ IOCTLs per refresh

**Impact:**
- SMI spikes
- Thermal jitter
- System responsiveness degradation

**Solution:** Driver should support "read N MSRs in one IOCTL" batch operation.

**Priority:** Move batching from Phase 4 to **Phase 2** (required for stability).

### 2.2 Capability Bitmask (REQUIRED)

**Issue:** UI must know what driver capabilities are available.

**Required Addition to JSON Schema:**
```json
{
  "kernel_helper": {
    "capabilities": {
      "msr_read": true,
      "pci_read": false,
      "smbus_read": false,
      "rapl": true,
      "turbo": true,
      "imc_temp": false,
      "c_states": true,
      "per_core_freq": true
    }
  }
}
```
4. GPU Tab Integration (MISSING FROM ORIGINAL PLAN)

### 4.1 Current GPU Tab Issues

**Current Data Sources:**
- WMI (Win32_VideoController) - weak, incomplete
- EnumDisplayDevices / EnumDisplaySettings - basic only
- ❌ No DXGI, no ADL, no NVML, no KMD queries

**Problems:**
1. **RDP Distortion:** Shows "Microsoft Basic Display Adapter" instead of real GPU
2. **No Real VRAM:** WMI AdapterRAM is rounded, doesn't reflect BAR1/resizable BAR
3. **No Telemetry:** No temp, power, clocks, utilization, fan speed
4. **No PCIe Info:** No link width/speed, no topology
5. **Hybrid GPU Confusion:** dGPU not marked as display owner

### 4.2 Required GPU Data (Missing)

**Hardware:**
- Real VRAM (dedicated + shared)
- PCIe link width/speed
- Resizable BAR status
- BAR1 aperture
- LUID mapping
- Multi-GPU topology

**Telemetry:**
- GPU temperature
- Hotspot temperature
- Memory temperature
- Power draw & limits
- GPU clock (current + max)
- Memory clock
- GPU utilization
- Memory utilization
- Fan speed
- Voltage

**Display Routing:**
- Which GPU owns display
- MUX status
- Dynamic switching state
- iGPU vs dGPU routing

### 4.3 Required Integration

**New Module:** `gpu_integration.py`

**Features:**
- DXGI adapter enumeration (for VRAM, PCIe, topology)
- NVIDIA NVML integration (for temperature, power, clocks)
- AMD ADL integration (for AMD systems)
- Intel iGPU telemetry (for GT frequency, temperature, EU utilization)
- RDP detection and handling
- Fallback to WMI when proprietary APIs unavailable

**Status:** ❌ Not in current plan - must be added.

---

## 5. Storage Tab Integration (MISSING FROM ORIGINAL PLAN)

### 5.1 Current Storage Tab Issues

**Current Status:** Minimal - uses nvme_helper.exe but not fully integrated into UI.

**Missing Data:**
- NVMe kernel-level telemetry
- PCIe link width/speed for drives
- PCIe throttling reasons
- NVMe power states (L0/L1/L1.1/L1.2)
- NVMe endurance (write amplification, wear leveling)
- SMART extended attributes
- SATA/AHCI telemetry
- RAID detection
- USB storage detection
- eMMC/UFS detection
- Storage topology (controller → device mapping)
- Drive health scoring
- Drive lifetime estimation

### 5.2 Required Integration

**New Module:** `storage_integration.py`

**Features:**
- NVMe SMART (kernel + helper combined)
- PCIe link telemetry via kernel helper
- Temperature monitoring
- Power state tracking
- Endurance metrics
- SATA/AHCI support
- USB storage enumeration
- RAID detection
- Drive health scoring algorithm

**Kernel Helper Role:**
- Read NVMe registers via MMIO (if BAR mapped)
- Monitor PCIe link state
- Track controller temperature
- Report power state changes

**Status:** ❌ Not in current plan - must be added.

---

## 6. Display Tab Integration (MISSING FROM ORIGINAL PLAN)

### 6.1 Current Display Tab Issues

**Current Status:** EDID helper exists but not integrated into Display tab.

**Missing Data:**
- Real EDID parsing (currently using WMI partial EDID)
- HDR capability
- Color space (sRGB, DCI-P3, Adobe RGB)
- Bit depth
- Panel brightness range
- Adaptive sync (VRR/G-Sync/FreeSync)
- Accurate refresh rate
- Display routing (iGPU/dGPU/MUX)
- Multi-monitor topology
- Internal vs external panel detection
- USB-C/Thunderbolt display detection
- Display bandwidth (DP link rate)
- DSC compression status

### 6.2 Required Integration

**New Module:** `display_integration.py`

**Features:**
- EDID helper integration (parse full EDID block)
- HDR metadata extraction
- Color space detection
- Bit depth reporting
- VRR capability detection
- Display routing logic (via DXGI or kernel)
- Multi-monitor topology
- DP/HDMI link rate monitoring
- DSC detection

**Kernel Helper Role:**
- PCIe display routing (iGPU vs dGPU)
- MUX state reading
- Display engine residency
- GPU ownership mapping

**Status:** ❌ Not in current plan - must be added.

---

## 7. System Architecture Tab (MISSING FROM ORIGINAL PLAN)

### 7.1 Current System Architecture Tab Issues

**Current Status:** ❌ Completely blank - no data collection exists.

**Missing Data:**
- CPUID 0xB / 0x1F topology decoding
- APIC ID → core → cluster → tile mapping
- P-core vs E-core classification
- NUMA domains
- Cache hierarchy visualization
- Memory controller mapping
- PCIe topology tree
- GPU/CPU/Memory interconnects
- Tile layout (Meteor Lake)
- Fabric bandwidth
- Power domains
- Thermal domains

### 7.2 Required Integration

**New Module:** `topology_integration.py`

**Features:**
- CPUID 0xB / 0x1F parser
- APIC ID decoder
- P-core/E-core classifier (via CPUID 0x1A)
- Cluster mapping
- Tile mapping (Meteor Lake specific)
- NUMA domain detection
- Cache hierarchy builder
- PCIe topology enumeration
- Interconnect bandwidth estimation

**Kernel Helper Role:**
- PCIe configuration space reads
- Memory controller topology
- Fabric link status
- Power domain mapping

**Existing Helper Extensions:**
- cpuid_helper.exe already has APIC topology - integrate it!

**Status:** ❌ Not in current plan - must be added.

---

## 8. BIOS/Firmware Tab Integration (CRITICAL MISSING PIECE)

### 8.1 Current Status - No BIOS Tab Exists

**Critical Omission:** The current plan has NO BIOS/Firmware tab, despite it being foundational for:
- System identity
- Firmware compliance
- Security posture
- CPU feature correctness
- Memory training correctness
- PCIe link training
- Thermal policy
- Power limits
- Microcode behavior
- Virtualization support
- Kernel helper compatibility

**Current Blindness:** The tool cannot report:
- BIOS version/date/vendor
- UEFI vs Legacy mode
- Secure Boot status
- TPM status
- Boot order
- ACPI tables
- Firmware capabilities
- ME/AMT firmware
- EC firmware
- Fan tables
- Thermal policy (BIOS defaults)
- Power limits (BIOS defaults)
- Microcode version
- Firmware-level CPU features
- BIOS settings
- BIOS update status

### 8.2 What a Proper BIOS Tab Should Contain

#### **1. Firmware Identity**
- BIOS vendor (Dell, HP, Lenovo, etc.)
- BIOS version (e.g., 1.12.0)
- BIOS release date
- EC (Embedded Controller) firmware version
- ME/AMT (Intel Management Engine) firmware version
- UEFI version
- SMBIOS version

#### **2. Boot Configuration**
- Boot mode (UEFI / Legacy)
- Secure Boot (Enabled/Disabled)
- TPM status (Enabled/Disabled/Not Present)
- TPM version (1.2 / 2.0)
- Boot order
- Fast Boot status

#### **3. CPU Microcode**
- Microcode version (hex)
- Microcode update source (BIOS vs OS)
- Microcode date (if available)

#### **4. Firmware Capabilities**
- VT-x (Intel Virtualization)
- VT-d (Intel IOMMU)
- AMD-V / SVM
- SGX (Software Guard Extensions)
- TXT (Trusted Execution Technology)
- SMM (System Management Mode) protection
- BIOS Guard
- Firmware TPM (fTPM)
- Memory encryption support (TME, MKTME)

#### **5. Thermal & Power Policy (BIOS Defaults)**
- PL1 (Sustained Power Limit) - BIOS default
- PL2 (Burst Power Limit) - BIOS default
- Tau (Time window)
- Fan curves (if exposed via ACPI/EC)
- Thermal trip points
- EC thermal policy

#### **6. ACPI Tables (Optional Advanced)**
- DSDT (Differentiated System Description Table)
- SSDT (Secondary System Description Table)
- FACP (Fixed ACPI Description Table)
- Thermal zones
- Power domains
- CPU topology (firmware view)

#### **7. Firmware Events**
- Last BIOS update date
- Last CMOS reset
- Last boot reason
- Firmware error logs (if accessible)

### 8.3 Existing Building Blocks (Not Yet Integrated)

**A. WMI APIs (Already Available):**
- `Win32_BIOS` - Version, date, vendor
- `Win32_ComputerSystem` - UEFI mode, Secure Boot
- `Win32_OperatingSystem` - Boot configuration
- `Win32_TPM` - TPM status

**B. Kernel Helper (Can Be Extended):**
- Microcode version (via CPUID leaf 0x01)
- PL1/PL2 defaults (MSR 0x614 - PKG_POWER_INFO)
- Thermal trip points (MSR access)
- ACPI table access (via kernel mapping)

**C. Existing Helpers (Partial Data):**
- `cpuid_helper.exe` - Already reads microcode version
- `spd_helper.exe` - SMBIOS version
- `nvme_helper.exe` - Firmware version for drives

### 8.4 Required Integration

**New Module:** `bios_integration.py`

**Features:**
- Query WMI for BIOS identity
- Query kernel helper for microcode
- Query ACPI tables (optional)
- Query Secure Boot status (via WMI or registry)
- Query TPM status (via WMI)
- Query UEFI mode (WMI)
- Query firmware capabilities (CPUID + MSR)
- Normalize all data
- Provide provenance (WMI vs kernel vs CPUID)

**Fallback Model:**
- **ABSENT:** WMI only (basic BIOS info)
- **PRESENT_LIMITED:** WMI + CPUID (adds microcode)
- **PRESENT_FULL:** WMI + CPUID + kernel helper (adds MSR thermal/power defaults)

### 8.5 UI Layout for BIOS Tab

```
╔══════════════════════════════════════════════════════════════╗
║                  BIOS / FIRMWARE INFORMATION                 ║
╚══════════════════════════════════════════════════════════════╝

FIRMWARE IDENTITY:
Vendor:            Dell Inc.
Version:           1.12.0
Release Date:      2024-09-14
SMBIOS Version:    3.5
UEFI Version:      2.7

BOOT CONFIGURATION:
Boot Mode:         UEFI
Secure Boot:       Disabled
TPM Status:        Enabled (v2.0)
Fast Boot:         Enabled

CPU MICROCODE:
Microcode Version: 0x2F (Latest)
Update Source:     BIOS
Platform ID:       0x06

FIRMWARE CAPABILITIES:
Virtualization:    VT-x: Enabled, VT-d: Enabled
Security:          SGX: Supported, TXT: Enabled
Memory:            TME: Supported

THERMAL & POWER (BIOS Defaults):
PL1 (Sustained):   28W
PL2 (Burst):       64W
Tau:               8 seconds
Thermal Trip:      100°C

FIRMWARE STATUS:
Last BIOS Update:  2024-09-14
CMOS Battery:      Good
Boot Count:        1,247
```

### 8.6 Integration into Overview Tab

Add to Overview tab:
```
FIRMWARE:
BIOS:              Dell Inc. 1.12.0 (2024-09-14)
Boot Mode:         UEFI
Secure Boot:       Disabled
TPM:               Enabled (v2.0)
Microcode:         0x2F
```

### 8.7 Data Sources Summary

| Data Point | Source | Fallback |
|------------|--------|----------|
| BIOS Vendor/Version/Date | WMI Win32_BIOS | SMBIOS Type 0 |
| UEFI Mode | WMI Win32_ComputerSystem | Registry |
| Secure Boot | WMI or Registry | PowerShell |
| TPM Status | WMI Win32_TPM | PowerShell |
| Microcode | CPUID 0x01 (cpuid_helper) | None |
| PL1/PL2 Defaults | MSR 0x614 (kernel_helper) | None |
| VT-x/VT-d | CPUID + BIOS settings | CPUID only |
| Boot Count | WMI or Event Log | None |

**Status:** ❌ Not in current plan - must be added as **Phase 8** (renumber Power & Thermal to Phase 9).

---

## 9. Integration Strategy (REVISED)
This prevents UI from guessing what's available and enables graceful feature degradation.

### 2.3 Versioned JSON Schema (STABILITY)

**Issue:** Need stable contract between driver and UI.

**Required:** Define versioned schema for kernel helper output with:
- Protocol version number
- Required vs optional fields
- Backward compatibility rules
- Version mismatch warnings

### 2.4 Timeout and Error Semantics

**Required Error Handling:**
- Timeout behavior (default: 5 seconds)
- Retry behavior (default: no retries)
- Error codes (aligned with broker exit codes)
- Fallback paths (to user-mode data)

### 2.5 C-State Residency (MISSING DEFINITION)

**Current Status:** Values in CPU tab are synthetic (user-mode cannot read MSRs).

**Required MSRs for Real C-State Data:**
- MSR 0x3FC - C3 residency
- MSR 0x3FD - C6 residency
- MSR 0x3FE - C7 residency
- MSR 0xE7 - APERF (active frequency)
- MSR 0xE8 - MPERF (maximum frequency)

**Integration Requirements:**
- Batch read all C-state MSRs per core
- Normalize residency percentages
- Calculate idle vs active time
- Show per-core C-state breakdown

**Current Plan Status:** Mentioned in Phase 4 but not fully defined - needs expansion.

### 2.6 SMT Status Reporting (MISLEADING)

**Issue:** Current "SMT Status: No" is technically correct but semantically misleading.

**Problem:** Meteor Lake / Ultra 9 architecture:
- P-cores: SMT disabled
- E-cores: No SMT by design

**Required for Accurate Reporting:**
- CPUID leaf 0xB (legacy topology)
- CPUID leaf 0x1F (extended topology - Meteor Lake)
- APIC ID decoding
- Per-core SMT status (not system-wide)

**Solution:** Report SMT per core type:
```
SMT Status: P-cores: Disabled, E-cores: N/A (by design)
```

**Current Plan Status:** Not addressed - needs addition.

---

## 3. C─ Calls: read_cpuid_frequencies()  [Line 640]
  │       └─ Subprocess: cpuid_helper.exe
  │
  ├─ Updates CPU tab [Line 2640]
  │   └─ Shows: MSR Access field [Line 2678]
  │       └─ Currently shows: "Not available (user-mode)"
  │
  └─ Updates Storage/Display tabs [Lines 3194, 3256]
      ├─ get_nvme_helper_info()
      └─ get_edid_helper_info()
```

---

## 2. Current MSR Handling

### 2.1 MSR Status Display

**Location:** CPU tab, Line 2678
```python
MSR Access:           {cpu_extended.get('msr_access', 'Unavailable')}
```

**Current Source:** `cpuid_helper.exe`
- Returns: `"Not available (user-mode execution)"`
- Reason: User-mode process cannot access MSRs directly

**Key Insight:** The UI already has a placeholder for MSR data!

### 2.2 MSR-Related Data Currently Missing

From `cpuid_helper.cpp` (lines 693-705):
```cpp
// MSR status returned as string message
printf("\"msr_access\": \"Not available (user-mode execution)\", ");
```

From `main.py` CPU tab (lines 2670-2678):
```python
TURBO RATIO INFORMATION (CPUID 0x16):
Max Turbo (1-core):   {cpu_extended.get('max_turbo_1c', 'Unavailable')} MHz
Max Turbo (all-core): {cpu_extended.get('max_turbo_ac', 'Unavailable')} MHz
MSR Access:           {cpu_extended.get('msr_access', 'Unavailable')}
```

**What's Missing (that kernel driver can provide):**
1. **Core Temperatures** - Per-core via MSR 0x19C (IA32_THERM_STATUS)
2. **Package Power Limits** - PL1/PL2 via MSR 0x610
3. **Energy Counters** - RAPL via MSRs 0x611, 0x619
4. **Turbo Ratios** - Actual turbo limits via MSR 0x1AD
5. **Platform Info** - Base clock via MSR 0xCE
6. **C-State Residency** - Power states (requires per-core MSR reads)
7. **Voltage/Frequency** - Real-time P-state data

---

## 3. Integration Strategy

### 3.1 Placement in Data Hierarchy

**Recommended: Level 3.5 - Between Helpers and Kernel**

The kernel helper should be treated as a **privileged helper** that:
1. Follows the same subprocess + JSON pattern as other helpers
2. Has fallback behavior when driver not loaded
3. Augments (not replaces) existing data collection
4. Is optional - system works without it (graceful degradation)

### 3.2 Integration Points by Tab

#### **CPU Tab (Primary Integration)**

Current functions that should call kernel helper:
- `get_cpu_extended_info()` (Line 1095)
  - Add: Core temperatures from MSR 0x19C
  - Add: Real turbo ratios from MSR 0x1AD
  - Add: Platform info from MSR 0xCE
  - Update: `msr_access` field with actual status

**Proposed Addition:**
```python
def get_cpu_extended_info():
    # ... existing code ...
    
    # Try to get kernel helper data
    kernel_data = get_kernel_helper_cpu_data()  # NEW FUNCTION
    if kernel_data.get('available'):
        cpu_details['msr_access'] = 'Available (kernel driver)'
        cpu_details['core_temperatures'] = kernel_data.get('temperatures', {})
        cpu_details['package_power'] = kernel_data.get('power_limits', {})
        cpu_details['turbo_ratios_msr'] = kernel_data.get('turbo_ratios', {})
    else:
        cpu_details['msr_access'] = kernel_data.get('error', 'Unavailable')
```

#### **Memory Tab (Secondary Integration)**

Current function: `get_memory_extended_info()` (Line 572)
- Add: Memory controller temperature (if available via MSRs)
- Add: IMC frequency/power (advanced, optional)

#### **System Overview Tab (Summary Integration)**

Current function: `refresh_all_tabs()` → Overview section (Line 2559)
- Add: Kernel Helper status indicator
- Add: Overall CPU package temperature
- Add: Current power consumption (RAPL)

#### **New "Power & Thermal" Tab (Future)**

Could be added as 11th tab:
- CPU: Per-core temperatures, package temp, Tj Max
- GPU: Temperature (if accessible)
- Package: Power limits (PL1/PL2), current consumption
- Energy: RAPL counters for package/cores/DRAM/uncore
- Real-time graphs: Temperature and power over time

---

## 4. Fallback Strategy

### 4.1 Three-State Presence Model

Already implemented in `halfax_kernel_helper.py`:

```python
class HelperPresence(Enum):
    ABSENT = "absent"                    # Driver not loaded
    PRESENT_LIMITED = "present_but_limited"  # MSR only
    PRESENT_FULL = "present_full"        # All features
```

**Usage in main.py:**
```python
def get_kernel_helper_cpu_data():
    """Get CPU data from kernel helper with fallback."""
    from halfax_kernel_helper import KernelHelper, HelperPresence
    
    helper = KernelHelper()
    presence = helper.get_presence_state()
    
    if presence == HelperPresence.ABSENT:
        return {
            'available': False,
            'error': 'Drive (REVISED)

### Phase 1: Kernel Helper Foundation (Week 1)
**CPU Tab - Basic Integration**
- [ ] Create `kernel_integration.py` module
- [ ] Implement capability bitmask detection
- [ ] Add versioned JSON schema
- [ ] Add `get_kernel_helper_status()` function
- [ ] Add timeout and error handling (5 sec default)
- [ ] Add kernel status to CPU tab (read-only display)
- [ ] Test with driver loaded/unloaded
- [ ] Test driver version mismatch detection

### Phase 2: CPU Telemetry + Batching (Week 1-2)
**CPU Tab - Temperature & Power**
- [ ] **Implement MSR batch read support in driver** (CRITICAL)
- [ ] Implement `get_kernel_cpu_temperatures()` with batch reads
- [ ] Display per-core temps in CPU tab
- [ ] Add Tj Max and margin display
- [ ] Add package temp to Overview tab
- [ ] Implement `get_kernel_power_data()` with batch reads
- [ ] Display PL1/PL2 limits in CPU tab
- [ ] Add RAPL energy counters
- [ ] Calculate real-time power consumption
- [ ] Test batch vs individual read performance

### Phase 3: CPU Advanced Telemetry (Week 2-3)
**CPU Tab - Turbo, C-States, Frequencies**
- [ ] Implement `get_kernel_turbo_ratios()`
- [ ] Display real turbo limits from MSR 0x1AD
- [ ] Implement C-state residency collection:
  - [ ] MSR 0x3FC (C3), 0x3FD (C6), 0x3FE (C7)
  - [ ] MSR 0xE7 (APERF), 0xE8 (MPERF)
  - [ ] Normalize residency percentages
  - [ ] Show per-core C-state breakdown
- [ ] Add per-core frequency monitoring
- [ ] Fix SMT status reporting:
  - [ ] Add CPUID 0xB / 0x1F integration
  - [ ] Report per-core-type SMT status
  - [ ] Handle hybrid architectures correctly

### Phase 4: GPU Integration (Week 3-4)
**GPU Tab - Complete Overhaul**
- [ ] Create `gpu_integration.py` module
- [ ] Implement DXGI adapter enumeration
- [ ] Add NVIDIA NVML integration (if available)
- [ ] Add AMD ADL integration (if available)
- [ ] Add Intel iGPU telemetry
- [ ] Implement RDP detection and handling
- [ ] Add GPU temperature display
- [ ] Add GPU power draw and limits
- [ ] Add GPU clocks (current + max)
- [ ] Add GPU utilization
- [ ] Add VRAM usage (dedicated + shared)
- [ ] Add PCIe link width/speed
- [ ] Add resizable BAR detection
- [ ] Add multi-GPU topology
- [ ] Add display routing info (MUX status)
- [ ] Update GPU tab UI with all new data

### Phase 5: Storage Integration (Week 4-5)
**Storage Tab - NVMe + PCIe Telemetry**
- [ ] Create `storage_integration.py` module
- [ ] Integrate nvme_helper.e (COMPLETE LIST)

### New Integration Modules:
1. **`kernel_integration.py`** - CPU/Memory kernel helper integration
   - Status detection
   - MSR batch reads
   - Temperature collection
   - Power data collection
   - Turbo ratio collection
   - C-state collection
   - Capability detection

2. **`bios_integration.py`** - BIOS/Firmware integration
   - WMI BIOS queries
   - Microcode version
   - Secure Boot detection
   - TPM detection
   - UEFI mode detection
   - Firmware capabilities
   - Boot configuration
   - Power defaults (MSR 0x614)

3. **`gpu_integration.py`** - GPU telemetry integration
   - DXGI enumeration
   - NVML integration (NVIDIA)
   - ADL integration (AMD)
   - Intel iGPU telemetry
   - RDP detection
   - Display routing
   - Multi-GPU topology

4. **`storage_integration.py`** - Storage telemetry integration
   - NVMe helper integration
   - PCIe link monitoring
   - Temperature monitoring
   - Power state tracking
   - SATA/AHCI support
   - RAID detection
   - Health scoring

5. **`display_integration.py`** - Display telemetry integration
   - EDID helper integration
   - HDR detection
   - Color space parsing
   - VRR detection
   - Display routing
   - Link rate monitoring

6. **`topology_integration.py`** - System topology integration
   - CPUID 0xB / 0x1F parser
   - APIC ID decoder
   - P-core/E-core classifier
   - Cluster mapping
   - Tile mapping (Meteor Lake)
   - NUMA mapping
   - Cache hierarchy
   - PCIe topology
   - Memory controller mapping

### Files to Modify:
1. **`main.py`**:
   - `get_cpu_extended_info()` (Line 1095) - Add kernel_integration calls
   - `refresh_all_tabs()` CPU section (Line 2640) - Add MSR display
   - `get_gpu_info()` (Line 1649) - Add gpu_integration calls
   - `get_disk_info()` (Line 2268) - Add storage_integration calls
   - `gArchitectural Observations from ingestion.txt

### 14.1 Strengths Validated

**✅ Level 3.5 Placement is Correct**
- Treating kernel helper as privileged helper (subprocess + JSON)
- Keeps architecture predictable, testable, auditable
- Consistent with existing patterns
- Avoids kernel helper becoming "special case"

**✅ kernel_integration.py is Right Abstraction**
- Prevents main.py from becoming monolith
- Driver quirks don't leak into UI code
- Future driver changes don't require UI rewrites
- Clean place for normalization, provenance, batching, exceptions

**✅ Three-State Fallback Model is Robust**
- Handles: not installed, installed but not started, missing privileges, partial failures
- Avoids binary thinking
- Room to evolve

**✅ Provenance Tracking is Major Win**
- Makes debugging trivial
- Prevents "mystery values"
- Aligns with audit-first architecture

**✅ Risk Analysis is Realistic**
- Correctly identifies MSR read frequency as biggest risk
- Snapshot-only until Phase 8 avoids SMI/thermal issues

### 14.2 Critical Additions Made

**🔴 MSR Batching Elevated to Phase 2**
- Was Phase 4, now Phase 2
- Performance and stability requirement, not "advanced feature"

**🔴 Capability Bitmask Added**
- Prevents UI from guessing what's available
- Enables graceful feature degradation

**🔴 Versioned JSON Schema Required**
- Prevents silent failures on driver updates
- Backward compatibility enforcement

**🔴 C-State Residency Fully Defined**
- Was "mentioned", now has specific MSRs
- Includes normalization and batch read requirements

**🔴 SMT Status Reporting Fixed**
- Now handles hybrid architectures correctly
- Per-core-type reporting instead of misleading system-wide

**🔴 GPU/Storage/Display/Architecture Tabs Added**
- Original plan only covered CPU/Memory
- Now comprehensive across all tabs

## 15. Success Criteria (REVISED)

### Minimum Viable Integration (Phase 1-2):
- [ ] Kernel helper status shows in CPU tab
- [ ] Capability bitmask reported
- [ ] No crashes when driver not loaded
- [ ] No crashes when driver is loaded
- [ ] MSR batch reads working
- [ ] Per-core temperatures displayed
- [ ] Power limits and consumption sh8):
- [ ] GPU tab accurate (DXGI/NVML/ADL)
- [ ] Storage tab complete (NVMe + PCIe telemetry)
- [ ] Display tab complete (EDID + routing)
- [ ] System Architecture tab populated (topology)
- [ ] BIOS/Firmware tab complete (WMI + CPUID + MSR)
- [ ] All tabs use appropriate integration modules
- [ ] No WMI/user-mode fallback where kernel data available

### Final Polish (Phase 9):
- [ ] Power & Thermal tab operational
- [ ] All telemetry consolidated (including BIOS defaults)se 4-7):
- [ ] GPU tab accurate (DXGI/NVML/ADL)
- [ ] Storage tab complete (NVMe + PCIe telemetry)
- [ ] Display tab complete (EDID + routing)
- [ ] System Architecture tab populated (topology)
- [ ] All tabs use appropriate integration modules
- [ ] No WMI/user-mode fallback where Now includes BIOS tab (critical gap filled)
2. **Prioritize Phase 1** - Foundation must be solid (batching + capabilities)
3. **Create stub modules**:
   - `kernel_integration.py`
   - `bios_integration.py` ← NEW
   - `gpu_integration.py`
   - `storage_integration.py`
   - `display_integration.py`
   - `topology_integration.py`
4. **Enhance driver for batching** - Critical for Phase 2
5. **Add MSR 0x614 support to kernel helper** - For BIOS power defaults
6. **Test integration pattern** with one module before scaling to all tabs
7
1. **Review this updated document** - Validate against ingestion.txt requirements
2. **Prioritize Phase 1** - Foundation must be solid (batching + capabilities)
3. **Create stub modules**:
   - `kCritical Gap Addressed: BIOS/Firmware Tab

**Why This Was Missing:**
The original plan focused on runtime telemetry (CPU, GPU, Memory) but overlooked **firmware identity and configuration**, which is foundational for:
- System identification
- Security compliance (Secure Boot, TPM)
- Firmware feature validation
- Microcode tracking
- Power/thermal policy baseline

**What ingestion.txt Pointed Out:**
"A BIOS tab is not 'nice to have.' It's foundational for system identity, firmware compliance, security posture, CPU feature correctness, memory training, PCIe link training, thermal policy, power limits, microcode behavior, virtualization support, and kernel helper compatibility."

**How It's Now Addressed:**
- Section 8: Complete BIOS/Firmware tab design
- Phase 8: Implementation roadmap
- `bios_integration.py`: New integration module
- UI layout defined
- Data sources identified (WMI + CPUID + kernel helper)
- Fallback model established
- Integration with Overview tab

**Building Blocks Already Available:**
- WMI APIs: Win32_BIOS, Win32_ComputerSystem, Win32_TPM
- cpuid_helper.exe: Already reads microcode
- Kernel helper: Can expose MSR 0x614 (BIOS power defaults)

This is now **Phase 8** with Power & Thermal moved to Phase 9.

---

## 18. ernel_integration.py`
   - `gpu_integration.py`
   - `storage_integration.py`
   - `display_integration.py`
   - `topology_integration.py`
4. **Enhance driver for batching** - Critical for Phase 2
5. **Test integration pattern** with one module before scaling to all tabs
6. **Iterate based on test results**

---

## 17. Alignment with Mission (README.md)

This plan now fully aligns with the project's core philosophy:

**✅ User-mode helpers first:**
- GPU: DXGI/NVML/ADL before kernel
- Storage: NVMe helper before kernel MMIO
- Display: EDID helper before kernel routing
- Topology: cpuid_helper before kernel PCIe

**✅ Kernel driver as fallback:**
- MSR: Only kernel can do this
- PCIe config space: User-mode insufficient
- SMBus: Requires ring-0
- Temperature via MMIO: Needs kernel mapping

**✅ Augment, don't replace:**
- Kernel data augments cpuid_helper (doesn't replace)
- Kernel PCIe data augments DXGI (doesn't replace)
- Always show data source (provenance)

**✅ Minimize kernel complexity:**
- Batch reads reduce IOCTL count
- Whitelist prevents arbitrary MSR access
- Read-only operations (write limited)
- Simple, auditable kernel surface

---

**END OF COMPREHENSIVE INTEGRATION PLAN
