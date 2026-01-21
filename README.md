# Halfax System Reporter

A cross-platform system information monitoring tool built with Python and Tkinter. Works on **Windows**, **Linux**, and **Raspberry Pi 5**.

## Features

- **Cross-Platform Support**: Windows 10/11, Linux, Raspberry Pi 5
- **Real-Time System Monitoring**: CPU, Memory, GPU, Storage, Battery, Network
- **Advanced CPU Telemetry** (Windows Intel):
  - Per-core frequency monitoring (via `CallNtPowerInformation`)
  - C-state residency tracking (idle vs active time per core)
  - APIC topology with P-core/E-core detection (hybrid CPUs)
  - Cache sharing group analysis (L1D/L2/L3 topology)
  - Turbo Ratio Limits (base, 1-core, all-core max frequencies)
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

The precompiled `.exe` files are included, but you can rebuild them if needed:

### Windows (requires Visual Studio Build Tools or MSVC)

```batch
# Build all helpers
.\build_cpuid_helper.bat
.\build_spd_helper.bat
.\build_nvme_helper.bat
.\build_edid_helper.bat
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
- **Build Scripts**: `build_*.bat` files for compiling C/C++ helpers
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
