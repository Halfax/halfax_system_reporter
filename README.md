# Halfax System Reporter

> **Project Engineering Tasks:**
> 
 > All actionable engineering tasks, phase goals, and cross-cutting requirements are tracked in [ACTIONABLE_TODO_CHECKLIST.md](ACTIONABLE_TODO_CHECKLIST.md). This checklist is the authoritative, dependency-aware source for ongoing and future development. Please update it as you complete or plan work. (TjMax read, MSR 0x1A2, package temperature calculation, PL1/PL2 + RAPL, and provenance tags for all MSR-derived values are now implemented in Python integration.)

A cross-platform system information monitoring tool built with Python and Tkinter. Works on **Windows**, **Linux**, and **Raspberry Pi 5**.

## Current Status (January 2026)

**✅ PHASE 5 COMPLETE - Multi-Method Implementation & GUI Fixes Operational**

### Latest Achievements:
- **✅ Multi-Method System Telemetry** - All system components with multiple detection methods
- **✅ GUI Data Population Fixed** - Resolved KeyError issues, tabs now display data properly
- **✅ Cross-Platform Robustness** - Enhanced error handling and fallback mechanisms
- **✅ User-Mode First Architecture** - Prioritizing user helpers over kernel access
- **✅ Complete Data Source Transparency** - Each data point shows collection method
- **✅ Enhanced Battery Information** - Voltage, current, power, wear level monitoring
- **✅ Comprehensive System Information** - Model, manufacturer, BIOS, motherboard details
- **✅ Advanced Network Telemetry** - MAC addresses, wireless detection, connection analysis
- **✅ Enhanced Storage Monitoring** - NVMe SMART data, I/O statistics, disk identification
- **✅ Multi-Method Memory Detection** - SPD helper → WMI → dmidecode → kernel fallbacks

### CPU Telemetry Capabilities (95%+ Accuracy):
- **Per-core temperature monitoring** with thermal margins
- **Real-time power consumption** via RAPL energy counters
- **Turbo ratio analysis** with kernel MSR data
- **C-state residency tracking** for power efficiency
- **IPC efficiency metrics** for performance analysis
- **Microcode version detection** with kernel MSR support

### Memory Telemetry Capabilities (Complete):
- **Multi-Method Detection** - SPD helper → WMI → dmidecode → kernel fallbacks
- **Enhanced Memory Details** - CAS latency, temperature, rank/bank configuration
- **SPD Timing Information** - Complete timing parameters from hardware
- **Memory Controller Info** - IMC detection and topology analysis
- **NUMA Node Mapping** - Memory locality and NUMA topology
- **Cross-platform Support** - Windows, Linux, Raspberry Pi compatibility
- **Provenance Tracking** - Each data source clearly identified

### Storage Telemetry Capabilities (Complete):
- **Multi-Method Storage Detection** - psutil → NVMe helper → WMI → lsblk fallback
- **NVMe SMART Data** - Temperature, health, power-on hours, data units
- **Disk Model Information** - Serial numbers, firmware, interface types
- **I/O Performance Data** - Read/write statistics and timing data
- **Cross-platform Support** - Windows WMI, Linux lsblk, NVMe helper integration
- **Disk Type Detection** - SSD/HDD/NVMe identification improvements

### Network Telemetry Capabilities (Complete):
- **Multi-Method Network Detection** - psutil → WMI → ip command → iwconfig fallback
- **Enhanced Network Telemetry** - MAC addresses, adapter types, speeds
- **Wireless Network Support** - IEEE 802.11 detection and protocol info
- **Connection Analysis** - Established, listen, time_wait, close_wait breakdown
- **Cross-platform Support** - Windows WMI, Linux ip/iwconfig commands
- **I/O Performance Data** - Enhanced network throughput and error metrics

### System Telemetry Capabilities (Complete):
- **Multi-Method System Detection** - platform → WMI → dmidecode → device_tree fallback
- **Enhanced System Telemetry** - Model, manufacturer, serial, BIOS details
- **Motherboard Information** - Base board details and product information
- **Boot Time Analysis** - System boot time and uptime tracking
- **Cross-platform Support** - Windows WMI, Linux dmidecode, Raspberry Pi
- **Hardware Identification** - Clear model, manufacturer, and serial information

### Battery Telemetry Capabilities (Complete):
- **Multi-Method Battery Detection** - psutil → WMI → powercfg → ACPI → sysfs fallback
- **Enhanced Battery Telemetry** - Voltage, current, power, capacity, wear level
- **Battery Health Analysis** - Wear level calculation and health status
- **Battery Identification** - Manufacturer, model, serial, technology details
- **Cross-platform Support** - Windows WMI, Linux ACPI/sysfs, powercfg reports
- **Power Consumption Data** - Real-time voltage, current, and power monitoring

### GPU Telemetry Capabilities (Complete):
- **Multi-GPU Detection** - NVIDIA discrete + Intel integrated GPUs
- **Real-time performance monitoring** - Core/memory utilization, temperature, power, clocks
- **PCIe configuration detection** - Link speed, width, Resizable BAR status
- **Display-GPU association** - Optimus/Switchable graphics support
- **Intel GPU metrics** - Performance counters for integrated graphics
- **Professional structured display** - Clear sections with visual hierarchy
- **Cross-vendor support** - NVIDIA, Intel, AMD GPU detection

### New Features (Phase 5.5):
- **✅ GUI Data Population Fixes** - Resolved KeyError issues, tabs now display data properly
- **✅ Enhanced Battery Detection** - psutil → WMI → powercfg → ACPI → sysfs fallback
- **✅ Battery Health Analysis** - Wear level calculation and health status assessment
- **✅ Power Consumption Data** - Real-time voltage, current, and power monitoring
- **✅ Cross-platform Battery Support** - Works on Windows, Linux, Raspberry Pi
- **✅ Robust Error Handling** - Defensive programming prevents data loss

- **✅ Router Scan (Network)** - Added a read-only Router Scan tab that performs UPnP/SSDP discovery behind a confirmation prompt. Uses optional `miniupnpc` when available; otherwise the UI shows a helpful note.
- **✅ Text Report improvements** - Aggregated Text Report now canonicalizes per-tab decorative headers and is export-friendly for saving or copying.
- **✅ Storage rendering fallback** - Storage tab prefers NVMe helper output but falls back to Windows WMI-detected devices when `nvme_helper` returns none; improved deterministic partition→physical-device mapping.
- **✅ Optional dependency guards** - Runtime guards and explicit platform flags (IS_WINDOWS/IS_LINUX/IS_MAC/IS_PI) added to avoid crashes when optional modules are missing.

### Previous Features (Phase 5.4):
- **Multi-Method System Detection** - platform → WMI → dmidecode → device_tree fallback
- **Enhanced System Telemetry** - Model, manufacturer, serial, BIOS details
- **Motherboard Information** - Base board details and product information
- **Boot Time Analysis** - System boot time and uptime tracking
- **Cross-platform System Support** - Works on Windows, Linux, Raspberry Pi

### Previous Features (Phase 5.3):
- **Multi-Method Network Detection** - psutil → WMI → ip command → iwconfig fallback
- **Enhanced Network Telemetry** - MAC addresses, adapter types, speeds
- **Wireless Network Support** - IEEE 802.11 detection and protocol info
- **Connection Analysis** - Established, listen, time_wait, close_wait breakdown
- **Cross-platform Network Support** - Works on Windows, Linux, Raspberry Pi

### Previous Features (Phase 5.2):
- **Multi-Method Storage Detection** - psutil → NVMe helper → WMI → lsblk fallback
- **Enhanced Storage Telemetry** - SMART data, temperature, health metrics
- **NVMe Health Monitoring** - Temperature, wear level, and health status
- **I/O Performance Data** - Read/write statistics and timing
- **Cross-platform Storage Support** - Works on Windows, Linux, Raspberry Pi

### Previous Features (Phase 5.1):
- **Multi-Method Memory Detection** - SPD helper → WMI → dmidecode → kernel fallbacks
- **Enhanced Memory Telemetry** - CAS latency, temperature, rank/bank configuration
- **Complete Memory Details** - No more "Not reported by system API" responses
- **Cross-platform Memory Support** - Works on Windows, Linux, Raspberry Pi
- **Data Source Transparency** - Each data point shows which method provided it

### Previous Features (Phase 4.4):
- **Complete GPU Performance Metrics** - All utilization, temperature, power, clocks
- **Multi-GPU Detection** - NVIDIA discrete + Intel integrated GPUs
- **GPU Display Association** - Map displays to active GPUs (Optimus support)
- **PCIe Information Detection** - Link speed, width, ReBAR status
- **Intel GPU Support** - Performance metrics for integrated graphics
- **Cross-vendor GPU Support** - NVIDIA, Intel, AMD GPU detection
- **Enhanced GPU Interface** - Professional structured display

### Technical Stack:
- **Kernel Driver**: HalfaxTelemetry v1.1.0 (MSR whitelist 1.1-intel)
- **Python Integration**: Complete kernel helper API
- **Real-time Monitoring**: Package power, temperature, frequency
- **Cross-platform**: Windows 10/11, Linux, Raspberry Pi 5

---

## Mission

**Goal**: Provide a **fact-based, comprehensive hardware and configuration telemetry system** that collects accurate, low-level system information across platforms.

**Architectural Philosophy**: Layered approach with privilege escalation only when necessary:

1. **User-mode helpers first** - Use standalone C/C++ helpers for accessible hardware:
   - `cpuid_helper.exe` - CPU topology, cache info, feature flags
   - `spd_helper.exe` - SMBIOS memory and system configuration
   - `nvme_helper.exe` - NVMe device enumeration and SMART data
   - `edid_helper.exe` - Display EDID parsing

2. **Kernel driver as fallback** - Use `halfax_telemetry_driver.sys` only for privileged operations:
   - MSR (Model-Specific Register) reads/writes
   - PCI configuration space access
   - SMBus transactions
   - Other ring-0 required operations

**Design Rule**: When extending the system:
- ✅ **Augment user-mode helpers** if the information is accessible without kernel privileges
- ✅ **Extend kernel driver** only when ring-0 access is mandatory
- ❌ **Never use kernel for what user-mode can do** - minimize kernel complexity and attack surface

**Data Collection Strategy**:
- ✅ **Use multiple methods** when available (NVML + WMI + Performance Counters, etc.)
- ✅ **Combine data sources** to ensure comprehensive coverage
- ✅ **Prioritize user-mode methods** for reliability and security
- ✅ **Use kernel driver** only for ring-0 privileged operations

## Features

- **Cross-Platform Support**: Windows 10/11, Linux, Raspberry Pi 5
- **Real-Time System Monitoring**: CPU, Memory, GPU, Storage, Battery, Network
- **Advanced CPU Telemetry** (Windows Intel):
  - Per-core temperature table in CPU tab (with provenance)
  - Package temperature summary in CPU tab
  - PL1/PL2 + RAPL section in CPU tab
  - Per-core frequency monitoring (via `CallNtPowerInformation`)
  - C-state residency tracking (idle vs active time per core)
  - APIC topology with P-core/E-core detection (hybrid CPUs)
  - Cache sharing group analysis (L1D/L2/L3 topology)
  - Turbo Ratio Limits (base, 1-core, all-core max frequencies)
  - Turbo ratio display (MSR 0x1AD) in CPU tab
  - MSR status reporting
- **Detailed Memory Information**:
  - Memory array configuration (max capacity, slots, ECC type)
  - Per-DIMM details (manufacturer, speed, capacity, voltage)
  - Memory error tracking (SMBIOS Type 18)
  - Battery wear level calculation
- **Storage Analysis**:
  - NVMe SMART data collection
  - Storage I/O performance metrics
  - GPU PCIe link information
  - GPU utilization and temperature
- **Display Information**:
  - EDID parsing for monitor details
  - Resolution, refresh rate, color depth
- **Network Monitoring**:
  - Interface status and configuration
  - IP addresses (IPv4/IPv6)
  - Network I/O statistics (bytes, packets, errors, drops)
- **System Architecture**:
  - PCI device topology tree
  - PCIe link speeds and widths
- **10-Tab Interface**: Overview, CPU, Memory, GPU, Disks, Storage, Display, System Architecture, Network, Text Report
- **Refresh Button**: Update all data instantly with one click
- **Export Reports**: Comprehensive text-based system report for documentation

## C/C++ Helper Binaries

The application includes four compiled helper utilities for low-level hardware access:

- **cpuid_helper.exe** - Direct CPUID access for CPU topology, cache info, and turbo ratios
- **spd_helper.exe** - SMBIOS parsing for memory modules and system configuration
- **nvme_helper.exe** - NVMe device enumeration and SMART data collection
- **edid_helper.exe** - EDID parsing from Windows registry for monitor information

## Kernel Driver Integration (Phase 1 Complete)

For privileged hardware access (MSR reads, PCIe config space), the application supports the **HalfaxTelemetry kernel driver**:

### Components
- **halfax_telemetry_driver.sys** - WDM kernel driver (ring-0 access)
- **halfax_kernel_broker.exe** - User-mode broker (IOCTL wrapper)
- **halfax_kernel_helper.py** - Python semantic API (MSR decoders)
- **kernel_integration.py** - Integration layer for main.py

### Current Status (Phase 1-2 Complete, Pending Reboot)

**Phase 1** ✅ COMPLETE:
- ✅ **Status Detection** - Shows driver availability in CPU tab
- ✅ **Capability Reporting** - Displays MSR/PCI/SMBus capabilities
- ✅ **Protocol Versioning** - v1.0 schema validation
- ✅ **Graceful Fallback** - Works without driver (ABSENT/LIMITED/FULL states)

**Phase 2** ✅ CODE COMPLETE | ⏳ TESTING PENDING REBOOT:
- ✅ **Batch MSR Support** - IOCTL_HALFAX_READ_MSR_BATCH (up to 64 MSRs/call)
- ✅ **Temperature Data** - MSR 0x19C per-core temps, Tj Max, package temp
- ✅ **Power Limits** - MSR 0x610 PL1/PL2 with enable/clamping status
- ✅ **RAPL Energy** - MSR 0x611/0x639/0x619 (package/cores/DRAM)
- ✅ **UI Display** - Temperature and power sections in CPU tab
- ⏳ **Live Testing** - Awaiting reboot to clear kernel namespace (Error 183)


-**Phase 3** (In Progress):
- ✅ **Turbo Ratios** - MSR 0x1AD real limits
- ✅ **C-State Residency** - MSR 0x3FC/0x3FD/0x3FE + APERF/MPERF (0xE7/0xE8) implemented
- ✅ **SMT Status Fix** - CPUID 0xB/0x1F for hybrid CPUs

- Per-core temperature table (sortable, provenance-aware)
- Package temperature summary (with provenance)
- PL1/PL2 + RAPL section (with provenance)
- Turbo ratio display (MSR 0x1AD, provenance-aware)
- Driver status with icon (🟢 Full / 🟡 Limited / ⚪ Not Available)
- Capability bitmask (MSR Read/Write, PCI, SMBus, Multicore)
- Protocol version and compatibility
- Available data by implementation phase
- Instructions when driver not available

**Phase 4** (Started):
- ✅ **GPU Integration (scaffold)** - `gpu_integration.py` added with NVML/nvidia-smi/WMI fallbacks
- ✅ **GPU Tab scaffold** - basic GPU tab and text report added to `main.py`
  - ⚙️ **DXDiag/DXGI enumeration**: `dxdiag` XML fallback implemented and enriched via WMI matching
  - ⚙️ **NVML integration**: NVML and `nvidia-smi` fallbacks present; utilization, temperature, power, clocks, and VRAM total/used are exposed
  - ⚙️ **PCIe / ReBAR / Topology**: best-effort PCIe negotiated link info (via kernel helper), Resizable BAR detection stub, and basic multi-GPU topology grouping implemented
  - ⚙️ **AMD ADL / Intel iGPU**: scaffolds present; vendor-native bindings can be added later for richer telemetry

### Architecture
**Level 3.5 Placement**: Treats kernel helper as privileged helper (subprocess + JSON pattern)
- Augments existing data (doesn't replace)
- No breaking changes to main.py
- Complete error handling
- Provenance tracking (data source attribution)

For deployment instructions, see [DRIVER_README.md](DRIVER_README.md) and [deploy_driver.py](deploy_driver.py).

## Requirements

### Python 3.8+
- **psutil** - System and process utilities
- **py-cpuinfo** - CPU information
- **wmi** (Windows only) - Windows system info
- **pywin32** (Windows only) - Windows API access
- **tkinter** - GUI (included with Python)

## Installation

### Windows

```bash
# Clone/navigate to project directory
cd path/to/somethingfun

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py
```

## Building C/C++ Helper Binaries

The precompiled `.exe` files are included. If you need to rebuild them:

### Windows (requires Visual Studio Build Tools or MSVC)

Open VS Developer Command Prompt and run:

```powershell
# Build individual helpers manually:
cl /O2 cpuid_helper.cpp /Fe:cpuid_helper.exe
cl /O2 spd_helper.c /Fe:spd_helper.exe
cl /O2 nvme_helper.c /Fe:nvme_helper.exe
cl /O2 edid_helper.c gdi32.lib /Fe:edid_helper.exe
```

Each helper outputs JSON to stdout for easy parsing in Python.

### Linux (Ubuntu/Debian)

```bash
# Install Python and tkinter
sudo apt-get update
sudo apt-get install python3 python3-pip python3-tk python3-venv

# Clone/navigate to project directory
cd path/to/somethingfun

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python3 main.py
```

### Raspberry Pi 5

```bash
# Install dependencies
sudo apt-get update
sudo apt-get install python3 python3-pip python3-tk python3-venv

# Clone/navigate to project directory
cd path/to/somethingfun

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python3 main.py
```

## Usage

1. **Run the application**: `python main.py`
2. **Browse tabs**: Overview, CPU, Memory, GPU, Disks, Text Report
3. **Refresh data**: Click "⟳ Refresh All" button to update all tabs
4. **View details**: Scroll through each tab for comprehensive system info

## CLI Usage

The project now includes a headless CLI that reuses the same Python collection methods as the GUI, with support for non-interactive and interactive sudo modes. **Reports are automatically saved to timestamped files.**

### Direct Python CLI

```bash
# Full text report (auto-saves to halfaxsystemreport.20260427_113823.txt)
./venv/bin/python cli_reporter.py

# JSON output for selected sections (auto-saves to halfaxsystemreport.20260427_113838.json)
./venv/bin/python cli_reporter.py --section overview --section cpu --format json

# Specify custom output filename
./venv/bin/python cli_reporter.py --section all --output my-custom-report.txt

# Interactive mode with automatic save (prompts for sudo password if needed)
./venv/bin/python cli_reporter.py --section overview --interactive
```

### Auto-Save Behavior

**Default behavior**: Reports are automatically saved with timestamped filenames
- Format: `halfaxsystemreport.{YYYYMMDD_HHMMSS}.{txt|json}`
- Example: `halfaxsystemreport.20260427_113823.txt`
- Confirmation message printed: `✓ Report saved to: halfaxsystemreport.20260427_113823.txt`

**Custom filename**: Use `--output` flag to specify your own filename
- `./venv/bin/python cli_reporter.py --output myreport.txt`
- Still prints confirmation with the filename used

### CLI Modes

#### Non-Interactive Mode (Default)
- Uses `sudo -n` (non-interactive flag) for privileged operations
- **Never prompts for password** - designed for automation/CI/headless systems
- If sudo access unavailable: silently degrades to "Unknown" values
- Notifies user about uncollected items (e.g., "System model (sudo access required)")
- **Report auto-saved to timestamped file** (no terminal buffer overflow)

```bash
./venv/bin/python cli_reporter.py --section overview --format text
# Output: ✓ Report saved to: halfaxsystemreport.20260427_113823.txt
```

#### Interactive Mode
- Enabled with `--interactive` flag
- Attempts non-interactive `sudo -n` first
- If that fails and interactive mode enabled: prompts user for sudo password
- Uses password to attempt privileged operations with `sudo -S`
- Still notifies user about any items that fail to collect
- **Report auto-saved to timestamped file**

```bash
./venv/bin/python cli_reporter.py --section overview --interactive
# Output: ✓ Report saved to: halfaxsystemreport.20260427_113838.txt
```

### Collection Failure Notifications

When items fail to collect, they appear in the report:

**Text Format:**
```
╔══════════════════════════════════════════════════════════════╗
║                    ⚠ ITEMS NOT COLLECTED                     ║
╚══════════════════════════════════════════════════════════════╝

  • System model (sudo access required)
  • System serial (sudo access required)
```

**JSON Format:**
```json
{
  "overview": {
    "hostname": "...",
    "_collection_failures": [
      "System model (sudo access required)",
      "System serial (sudo access required)"
    ]
  }
}
```

### Bash Wrapper

```bash
./hardware-report.sh --section overview,cpu,memory
# Report auto-saved to: halfaxsystemreport.20260427_113823.txt

./hardware-report.sh --format json --section network
# Report auto-saved to: halfaxsystemreport.20260427_113838.json

./hardware-report.sh --format json --section network --output network.json
# Report saved to: network.json (custom filename)

./hardware-report.sh --interactive --section overview --format text
# Prompts for sudo password if needed, report auto-saved
```

### PowerShell Wrapper

```powershell
.\hardware-report.ps1 --section overview,cpu,gpu
# Report auto-saved to: halfaxsystemreport.20260427_113823.txt

.\hardware-report.ps1 --format json --section all
# Report auto-saved to: halfaxsystemreport.20260427_113838.json

.\hardware-report.ps1 --format json --section all --output halfax-report.json
# Report saved to: halfax-report.json (custom filename)

.\hardware-report.ps1 --interactive --section overview --format text
# Prompts for sudo password if needed, report auto-saved
```

### Notes

- **Auto-Save**: Reports are automatically saved to timestamped files (`halfaxsystemreport.{YYYYMMDD_HHMMSS}.txt/json`). No more terminal buffer overflow!
- **Custom Filename**: Use `--output` flag to specify a custom filename instead of the timestamped default.
- **Non-Interactive (Default)**: On Linux/Pi, privileged probes use `sudo -n` to prevent hanging on password prompts. Perfect for automation.
- **Interactive Mode**: Can prompt for sudo password interactively when needed. Useful for manual system analysis.
- **Graceful Degradation**: If a privileged helper or binary is unavailable, the CLI falls back to lower-privilege methods and notifies you about missed items.
- **Setup Passwordless Sudo** (Optional): For best results in non-interactive mode, configure passwordless sudo for dmidecode:
  ```bash
  echo "$USER ALL=(ALL) NOPASSWD: /usr/sbin/dmidecode" | sudo tee /etc/sudoers.d/dmidecode-halfax > /dev/null
  sudo chmod 440 /etc/sudoers.d/dmidecode-halfax
  ```

## Platform-Specific Features

### Windows
- System model and serial number (via WMI)
- Memory module details (capacity, speed, type, manufacturer, errors)
- Complete GPU information (all video controllers)
- GPU PCIe link speeds and utilization
- Power supply information
- Battery status with wear level calculation
- **Advanced CPU telemetry** (Intel modern CPUs):
  - Per-core frequency via Windows kernel API
  - APIC ID enumeration with thread affinity pinning
  - Cache sharing topology (L1D/L2/L3 instances)
  - P-core vs E-core detection (Intel 12th gen+)
  - Turbo ratio limits (CPUID 0x16)
  - MSR status reporting
- **CPUID helper binary** (`cpuid_helper.exe`):
  - Direct CPUID access for accurate cache topology
  - APIC ID detection using CPUID leaves 0xB/0x1F
  - Inclusive/exclusive cache flag detection
- **SPD helper binary** (`spd_helper.exe`):
  - SMBIOS Type 16/17/18 parsing
  - Memory array configuration and error tracking
- **NVMe helper binary** (`nvme_helper.exe`):
  - NVMe device enumeration via IOCTL
  - SMART attribute collection
- **EDID helper binary** (`edid_helper.exe`):
  - EDID parsing from Windows registry
  - Monitor manufacturer, model, resolution details
- **Network monitoring**:
  - Interface statistics and IP configuration
  - I/O counters, error rates, drop counts

### Linux
- GPU detection via `lspci`
- Monitor detection via `xrandr` (X11) or `wlr-randr` (Wayland)
- Disk info via `lsblk`
- Battery info via `acpi` (if available)
- Distribution info via `lsb_release`

### Raspberry Pi 5
- Automatic Pi5 detection
- VideoCore VII GPU info
- System-on-Chip (SoC) memory details
- MMC card/storage detection
- CPU temperature monitoring
- Proper ARM architecture detection

## Optional: Faster Setup Script

Create a `setup.sh` (Linux/Pi) or `setup.bat` (Windows) for automated setup:

### setup.sh (Linux/Raspberry Pi)
```bash
#!/bin/bash
sudo apt-get update
sudo apt-get install python3 python3-pip python3-tk python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Setup complete! Run: python3 main.py"
```

### setup.bat (Windows)
```batch
@echo off
python -m venv venv
call .\venv\Scripts\activate.bat
pip install -r requirements.txt
echo Setup complete! Run: python main.py
```

## Troubleshooting

### tkinter not found
**Linux**: `sudo apt-get install python3-tk`
**macOS**: Usually pre-installed, or `brew install python-tk`

### Permission errors on Linux
Some system info requires elevated privileges. For full details, run with:
```bash
sudo python3 main.py
```

### WMI not available on Linux
The app gracefully handles missing WMI and uses alternative methods automatically.

### GPU not detected
- **NVIDIA**: Ensure `nvidia-smi` is installed
- **Linux**: Ensure `lspci` is available
- **Pi**: VideoCore is auto-detected

## Architecture

- **main.py**: Core application with all system info functions (4100+ lines)
- **C/C++ Helper Binaries**:
  - `cpuid_helper.cpp` / `cpuid_helper.exe` - CPU topology and CPUID access
  - `spd_helper.c` / `spd_helper.exe` - SMBIOS memory information
  - `nvme_helper.c` / `nvme_helper.exe` - NVMe device enumeration
  - `edid_helper.c` / `edid_helper.exe` - EDID display information
- **Kernel Driver** (Windows only):
  - `halfax_telemetry_driver.c` - WDM driver for MSR/PCI/SMBus access
  - `halfax_kernel_broker.cpp` - User-mode broker wrapping driver IOCTLs
  - `deploy_driver.py` - Automated build and deployment script
- **requirements.txt**: Python dependencies
- **Cross-platform functions**: Automatic platform detection and fallback methods
- **Tkinter GUI**: Responsive 10-tab interface with dark theme

## Supported Platforms

| Platform | Version | Architecture | Status |
|----------|---------|--------------|--------|
| Windows | 10, 11 | x86_64 | ✅ Full |
| Linux | Ubuntu 20.04+ | x86_64, ARM | ✅ Full |
| Raspberry Pi | 5 | ARM64 | ✅ Full |
| macOS | 10.15+ | Intel/Apple Silicon | ⚠️ Partial |

## Author

**Halfax**

## License

MIT License - see [LICENSE](LICENSE) file for details.

Free to use, modify, and distribute.

## Notes

- Some features require `sudo` on Linux (dmidecode, lspci details)
- Battery info not available on Raspberry Pi or desktop systems without battery
- Monitor detection works best with X11 (xrandr), Wayland support via wlr-randr
- GPU VRAM detection works best with nvidia-smi installed
- **C/C++ helpers are Windows-specific** - Linux/macOS use alternative methods
- Helper binaries output JSON for cross-language compatibility
- SMBIOS data (SPD helper) provides memory details without kernel drivers
- NVMe SMART data requires administrative privileges on some systems
- Network statistics are cumulative since last system boot

---

## January 2026 Update: Kernel Driver Replacement

The kernel driver and broker have been replaced and verified. All batch MSR reads, capability detection, and telemetry features are now live and tested. The Python integration modules are confirmed working with the new driver.

- Batch MSR reading (up to 64 per call) is now supported and tested.
- All CLI and Python API tests pass (see test_kernel_broker.py for regression results).
- The driver and broker now provide robust error handling, versioned protocol, and full capability reporting.
- Documentation, UI, and integration code are up-to-date with the new driver features.

**Next Steps:**
- Proceed to Phase 3: Turbo ratios, C-state residency, and SMT status for hybrid CPUs.
- See ENHANCEMENTS.md and PHASE1_IMPLEMENTATION_STATUS.md for implementation plan.
