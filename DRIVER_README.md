# Halfax Telemetry Driver - Build and Deployment Guide

## Overview

This is a minimal WDM driver that exposes privileged hardware primitives (MSR, PCI, SMBus) via a secure IOCTL interface. Only administrators can access it.

**Design Philosophy**: The kernel driver is the **last resort** for hardware telemetry. It exists only for operations that require ring-0 privileges (MSR, PCI config, SMBus). All user-accessible hardware information should be collected via user-mode helpers (`cpuid_helper.exe`, `spd_helper.exe`, `nvme_helper.exe`, `edid_helper.exe`) to minimize kernel complexity and attack surface.

**Extension Rule**: When adding new telemetry capabilities:
- ✅ If the data is accessible via user-mode APIs (WMI, registry, file I/O, CPUID instruction) → extend user-mode helpers
- ✅ If the data requires kernel privileges (MSRs, raw PCI config, SMBus, MMIO) → extend this driver
- ❌ Never implement user-accessible operations in the kernel

## Architecture

```
┌─────────────────────────────┐
│  Halfax System Reporter     │ (Python - main.py)
│       (main.py)              │
└──────────┬──────────────────┘
           │
           v
┌─────────────────────────────┐
│  halfax_kernel_broker.exe   │ (User-mode broker)
│  - CLI interface             │
│  - Wraps IOCTLs              │
└──────────┬──────────────────┘
           │ IOCTL
           v
┌─────────────────────────────┐
│ halfax_telemetry_driver.sys │ (Kernel driver)
│  - MSR read/write            │
│  - PCI config space          │
│  - SMBus access              │
└─────────────────────────────┘
```

## Files

- `halfax_telemetry.h` - Shared IOCTL contract (kernel + user-mode)
- `halfax_telemetry_driver.c` - WDM driver source
- `halfax_kernel_broker.cpp` - User-mode broker/helper
- `halfax_guid.cpp` - GUID definitions for device interface
- `halfax_telemetry.inf` - Driver installation manifest
- `deploy_driver.py` - Automated build and deployment script

## Building & Deployment

### Prerequisites

You need:
- Visual Studio 2022 (Community edition or higher)
- Windows Driver Kit (WDK) 10.0.26100.0 or later
- Windows SDK
- Python 3.x

### Automated Build & Deployment (Recommended)

Use the Python deployment script:

```powershell
python deploy_driver.py
```

The script automatically:
1. Detects Visual Studio installation
2. Configures build environment
3. Builds driver and broker
4. Deploys to System32\drivers
5. Creates and starts service
6. Verifies operation

**Output location:** 
- Driver: `C:\Windows\System32\drivers\halfax_telemetry_driver.sys`
- Broker: `halfax_kernel_broker.exe`

### Manual Build (Advanced)

If you need to build manually, open VS Developer Command Prompt:

**Build driver:**
```cmd
msbuild halfax_telemetry_driver.vcxproj /p:Configuration=Release /p:Platform=x64
```

**Build broker:**
```cmd
cl /EHsc /W4 /Ox halfax_kernel_broker.cpp halfax_guid.cpp setupapi.lib /Fe:halfax_kernel_broker.exe
```

## Installation & Testing

### Prerequisite: Disable Secure Boot (One-Time Setup)

Test signing requires Secure Boot to be disabled. This is a one-time setup for driver development.

**Steps to disable Secure Boot:**

1. **Shut down your PC completely** (don't restart)

2. **Power on and enter BIOS/UEFI Setup** during startup:
   - **Dell**: Press `F2` or `Del`
   - **HP/Lenovo/ASUS**: Press `F2`, `F10`, or `Del` (varies by model)
   - **Acer**: Press `Del` or `F2`
   - **MSI/Gigabyte**: Press `Del` or `F2`
   - **Surface**: Press and hold volume-up button
   - Check your PC manual or manufacturer website if unsure

3. **Navigate to Security settings**:
   - Look for menu: `Security`, `Boot`, or `Startup`
   - Find option labeled `Secure Boot`, `Secure Boot Control`, or similar
   - It may be under `Security → Boot Options` or `Startup → Security`

4. **Disable Secure Boot**:
   - Select the Secure Boot option
   - Change from `Enabled` to `Disabled`
   - Look for `Secure Boot Mode` and set to `Standard` or `Disabled`

5. **Save and Exit**:
   - Press `Ctrl+S` or `F10` (varies by BIOS)
   - Select `Save Changes and Exit` or `Yes`
   - System will reboot

6. **After reboot**, continue with Test Signing steps below

---

### Test-Sign the Driver (Development)

**After disabling Secure Boot and rebooting**, run these steps from an **Administrator Command Prompt**:

1. Enable test signing:
```cmd
bcdedit /set testsigning on
```

2. **Reboot** after enabling test signing (required):
```cmd
shutdown /r /t 0
```

3. **After reboot**, open **Administrator PowerShell** and create test certificate:
```cmd
& "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makecert.exe" -r -pe -ss PrivateCertStore -n "CN=HalfaxTestCert" HalfaxTest.cer
```

4. **Create driver package and sign everything:**
```cmd
REM Create clean driver package directory
mkdir driver_package
Copy-Item x64\Release\halfax_telemetry_driver.sys driver_package\
Copy-Item halfax_telemetry.inf driver_package\

REM Navigate to package directory
cd driver_package

REM Create catalog file from INF
& "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x86\Inf2Cat.exe" /driver:. /os:10_X64

REM Sign the catalog file (REQUIRED for pnputil)
& "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe" sign /fd SHA256 /s PrivateCertStore /n HalfaxTestCert /t http://timestamp.digicert.com halfaxtelemetry.cat
```

5. **Install certificate to Trusted Root store** (run as Administrator):
```cmd
REM Export certificate from PrivateCertStore
$cert = Get-ChildItem -Path Cert:\CurrentUser\PrivateCertStore\ | Where-Object { $_.Subject -like '*HalfaxTestCert*' }
Export-Certificate -Cert $cert -FilePath HalfaxTest.cer

REM Import to Trusted Root (required for driver installation)
Import-Certificate -FilePath HalfaxTest.cer -CertStoreLocation Cert:\LocalMachine\Root
```

**Note:** The commands above use PowerShell syntax with the `&` call operator and full paths to the Windows SDK tools. If you have a different SDK version:
- Check installed versions: `Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin"`
- Update the version number (10.0.26100.0) in the paths above
- Or download latest SDK from: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/

### Install the Driver (SCM Service Method - CURRENT APPROACH)

**This is the CPU-Z/HWiNFO deployment model. Your system is already configured.**

**Current Status:**
- ✅ Driver compiled: `x64\Release\halfax_telemetry_driver.sys`
- ✅ Driver deployed: `C:\Windows\System32\drivers\halfax_telemetry_driver.sys`
- ✅ Service created: `HalfaxTelemetry` (type=kernel, start=demand)
- ✅ Driver signed: WDKTestCert (lacks kernel-mode EKU)
- ✅ Workaround enabled: `bcdedit /set nointegritychecks on`
- ⏳ **REBOOT REQUIRED** for nointegritychecks to take effect

**After Reboot - Starting the Driver:**

```powershell
# Start the service (as Administrator)
sc start HalfaxTelemetry

# Check status
sc query HalfaxTelemetry
```

**Expected output after successful start:**
```
SERVICE_NAME: HalfaxTelemetry
        TYPE               : 1  KERNEL_DRIVER
        STATE              : 4  RUNNING
        WIN32_EXIT_CODE    : 0  (0x0)
        SERVICE_EXIT_CODE  : 0  (0x0)
```

**If you need to reinstall from scratch:**

```powershell
# 1. Copy driver to System32
Copy-Item x64\Release\halfax_telemetry_driver.sys C:\Windows\System32\drivers\ -Force

# 2. Create SCM service
sc create HalfaxTelemetry type= kernel start= demand binPath= "C:\Windows\System32\drivers\halfax_telemetry_driver.sys"

# 3. Start service
sc start HalfaxTelemetry
```

**Note:** Spaces after `type=` and `start=` are required by sc.exe syntax.

---

### Alternative: Install via INF/Catalog (Not Currently Used)

**Prerequisites:**
- Catalog file created and signed (see Test-Sign section above)
- Certificate installed to Trusted Root store
- Driver package in `driver_package\` directory with:
  - `halfax_telemetry_driver.sys`
  - `halfax_telemetry.inf`
  - `halfaxtelemetry.cat` (signed catalog)
- Run all commands as **Administrator**

**Installation (from driver_package directory):**
```cmd
REM Navigate to driver package
cd driver_package

REM Install using pnputil
pnputil /add-driver halfax_telemetry.inf /install

REM Verify it loaded
sc query HalfaxTelemetry
```

**Alternative options:**

**Option A: Using devcon** (requires WDK):
```cmd
devcon install halfax_telemetry.inf Root\HalfaxTelemetry
```

**Option B: Using sc.exe (SCM service - CURRENT METHOD)**:
```cmd
# Copy driver to System32\drivers first
Copy-Item halfax_telemetry_driver.sys C:\Windows\System32\drivers\

# Create and start service
sc create HalfaxTelemetry type= kernel start= demand binPath= C:\Windows\System32\drivers\halfax_telemetry_driver.sys
sc start HalfaxTelemetry
```

**Option C: Using pnputil** (INF-based):
```cmd
pnputil /add-driver halfax_telemetry.inf /install
```

---

### Verify Installation

```cmd
sc query HalfaxTelemetry
```

Expected output:
```
SERVICE_NAME: HalfaxTelemetry
    TYPE               : 1  KERNEL_DRIVER
    STATE              : 4  RUNNING
    WIN32_EXIT_CODE    : 0  (0x0)
    SERVICE_EXIT_CODE  : 0  (0x0)
    CHECKPOINT         : 0x0
    WAIT_HINT          : 0x0
```

If STATE is not `4 RUNNING`, check troubleshooting section below.

### Test the Broker

Run as Administrator:
```cmd
halfax_kernel_broker.exe --version
```

Expected output:
```
Driver version: 1.0.1
```

### Read MSR Examples

```cmd
REM Read IA32_THERM_STATUS (temperature) on CPU 0
halfax_kernel_broker.exe --read-msr 0 0x19C

REM Read turbo ratio limits on CPU 0
halfax_kernel_broker.exe --read-msr 0 0x1AD

REM Read package power limit (PL1) on CPU 0
halfax_kernel_broker.exe --read-msr 0 0x610
```

## Integration with main.py

Add a Python wrapper to call the broker:

```python
import subprocess
import json

def read_msr(cpu, msr):
    """Read MSR via kernel broker."""
    try:
        result = subprocess.run(
            ['halfax_kernel_broker.exe', '--read-msr', str(cpu), hex(msr)],
            capture_output=True,
            text=True,
            check=True
        )
        return int(result.stdout.strip(), 16)
    except subprocess.CalledProcessError as e:
        print(f"MSR read failed: {e.stderr}")
        return None

# Example usage
if __name__ == "__main__":
    # Read CPU temperature
    temp_msr = read_msr(0, 0x19C)
    if temp_msr:
        print(f"Temp MSR: 0x{temp_msr:X}")
```

## Security Notes

- **SDDL restricts access to Admins only** (`D:P(A;;GA;;;BA)(A;;GA;;;SY)`)
- No arbitrary code execution - only structured IOCTLs
- Input validation in kernel driver
- Buffer size checks on all IOCTLs

## Production Deployment

For production (no test-signing):
1. Get an EV code signing certificate (~$300-500/year)
2. Sign driver with EV cert
3. Submit to Microsoft for attestation signing (or WHQL)
4. Distribute signed driver

Alternative: Use Microsoft's documented APIs and avoid kernel driver entirely.

## Troubleshooting

### Secure Boot Issues

**Error: "The value is protected by Secure Boot policy"**
- Secure Boot is still enabled
- Go back to BIOS and disable it (see Disable Secure Boot section)
- Reboot and try again

---

### Test Signing Issues

**Error: "An error has occurred setting the element data"**
- You're not running as Administrator
- Right-click Command Prompt, select "Run as Administrator"
- Or use `Win + X` → "Windows PowerShell (Admin)"

**Error: "makecert" or "signtool" not found**
- Install Windows SDK from: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/
- Or add to PATH: `C:\Program Files (x86)\Windows Kits\10\bin\10.0.xxxxx.0\x64\`

**Error: "The third-party INF does not contain digital signature information"**
- The catalog file (.cat) was not created or not signed
- Follow step 4 in Test-Sign section to create and sign catalog file using `Inf2Cat.exe`
- Ensure `halfaxtelemetry.cat` exists in same directory as INF and .sys files

**Error: "Certificate chain terminated in a root certificate which is not trusted"**
- Test certificate not installed to Trusted Root store
- Follow step 5 in Test-Sign section to export and import certificate
- Run `Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -like '*HalfaxTestCert*' }` to verify
- Certificate must be in LocalMachine\Root, not just CurrentUser\PrivateCertStore

**Error 577: "Windows cannot verify the digital signature" (CRITICAL)**
- **Root cause:** Certificate lacks "Kernel Mode Code Signing" EKU (1.3.6.1.4.1.311.61.1.1)
- WDKTestCert (auto-created by WDK) has only "Code Signing" EKU - insufficient for kernel drivers
- **Quick fix for development:** Enable nointegritychecks (bypasses all signature checks)
  ```cmd
  bcdedit /set nointegritychecks on
  ```
  Then reboot and start service with `sc start HalfaxTelemetry`
- **Production fix:** Create certificate with kernel-mode EKU:
  ```cmd
  makecert -r -pe -ss PrivateCertStore -n "CN=MyKernelCert" -eku 1.3.6.1.4.1.311.61.1.1 MyKernel.cer
  ```
  Then install to Root + TrustedPublisher and re-sign driver
- Check certificate EKU: 
  ```powershell
  $cert = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -like '*YourCert*' }
  $cert.EnhancedKeyUsageList
  ```
- See Event Viewer → Microsoft-Windows-CodeIntegrity/Operational for detailed error

---

### Driver Installation Issues

**"Failed to open kernel driver"**
- Driver is not loaded: `sc query HalfaxTelemetry` (should show STATE: 4)
- Not running as Administrator (right-click → Run as admin)
- Driver file not found: check path in INF matches .sys location
- Check Event Viewer for kernel errors: Windows Logs → System

**"MSR read failed with NTSTATUS 0xC000001C"**
- STATUS_ILLEGAL_INSTRUCTION - MSR not available on this CPU
- Try a different MSR address (see MSR Reference below)
- Check Intel Datasheet for valid MSRs

**Driver won't load / BSOD on load**
- Check Event Viewer → Windows Logs → System for error code
- Ensure driver is test-signed: `signtool verify /pa halfax_telemetry_driver.sys`
- Verify INF file has correct paths and device class
- Check KMDF version matches WDK version

**"devcon: command not found"**
- `devcon` comes with WDK
- Use `pnputil` instead (modern alternative)
- Or add WDK bin to PATH

## MSR Reference (Intel)

Common MSRs for telemetry:
- `0x19C` - IA32_THERM_STATUS (CPU temperature)
- `0x1AD` - MSR_TURBO_RATIO_LIMIT
- `0x606` - MSR_RAPL_POWER_UNIT
- `0x610` - MSR_PKG_POWER_LIMIT
- `0x611` - MSR_PKG_ENERGY_STATUS
- `0x639` - MSR_PP0_ENERGY_STATUS (cores)
- `0xCE`  - MSR_PLATFORM_INFO

See Intel SDM Volume 4 for complete list.

## License

See LICENSE file.
