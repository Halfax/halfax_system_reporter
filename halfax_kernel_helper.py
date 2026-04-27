"""
Halfax Kernel Helper - Python Integration Module

Provides clean Python interface to the kernel broker for privileged
hardware access (MSRs, PCI, SMBus).

This is a first-class data source for Halfax System Reporter with:
- Standardized audit trail (source identity, capabilities, whitelist version)
- Semantic APIs that hide MSR complexity (read_core_temperatures, read_package_power)
- Three-state presence model: absent, present_but_limited, present_full

Usage:
    from halfax_kernel_helper import KernelHelper
    
    helper = KernelHelper()
    if helper.available:
        print(f"Kernel helper v{helper.version}")
        temps = helper.read_core_temperatures()  # Returns {core: temp_c}
"""

import subprocess
import json
import os
from typing import Optional, Dict, Any, Callable, Literal
from enum import Enum


class KernelHelperError(Exception):
    """Base exception for kernel helper errors."""
    pass


class KernelHelperNotAvailable(KernelHelperError):
    """Kernel helper driver is not present or not loaded."""
    pass


class KernelHelperAccessDenied(KernelHelperError):
    """Access denied - need admin or MSR not whitelisted."""
    pass


class KernelHelperNotImplemented(KernelHelperError):
    """Feature not implemented in driver."""
    pass


class HelperPresence(Enum):
    """Three-state presence model for kernel helper."""
    ABSENT = "absent"  # Broker not found or driver not loaded
    PRESENT_LIMITED = "present_but_limited"  # MSR only, no PCI/SMBus
    PRESENT_FULL = "present_full"  # All capabilities available


# MSR Mapping and Decoders
# This centralizes MSR knowledge so System Reporter doesn't need raw MSR numbers

class MSRScope(Enum):
    """MSR scope - whether it's per-core or package-wide."""
    CORE = "core"  # Different value per CPU core
    PACKAGE = "package"  # Single value for entire CPU package
    UNCORE = "uncore"  # Uncore/system agent


class MSRDefinition:
    """Definition of an MSR with decoding logic."""
    def __init__(
        self,
        name: str,
        msr: int,
        scope: MSRScope,
        decoder: Optional[Callable[[int], Any]] = None,
        description: str = ""
    ):
        self.name = name
        self.msr = msr
        self.scope = scope
        self.decoder = decoder or (lambda x: x)  # Default: return raw value
        self.description = description


# MSR Decoder Functions
def decode_therm_status(raw: int) -> Dict[str, Any]:
    """Decode IA32_THERM_STATUS (0x19C)."""
    digital_readout = (raw >> 16) & 0x7F
    resolution_deg = (raw >> 27) & 0xF
    valid = (raw >> 31) & 0x1
    
    return {
        "digital_readout": digital_readout,
        "resolution_deg": resolution_deg,
        "valid": bool(valid),
        "raw": raw
    }


def decode_temperature_target(raw: int) -> Dict[str, Any]:
    """Decode IA32_TEMPERATURE_TARGET (0x1A2) - Tj Max."""
    tj_max = (raw >> 16) & 0xFF
    
    return {
        "tj_max_celsius": tj_max,
        "raw": raw
    }


def decode_turbo_ratio_limit(raw: int) -> Dict[str, int]:
    """Decode MSR_TURBO_RATIO_LIMIT (0x1AD)."""
    return {
        "1_core_active": (raw >> 0) & 0xFF,
        "2_cores_active": (raw >> 8) & 0xFF,
        "3_cores_active": (raw >> 16) & 0xFF,
        "4_cores_active": (raw >> 24) & 0xFF,
        "5_cores_active": (raw >> 32) & 0xFF,
        "6_cores_active": (raw >> 40) & 0xFF,
        "7_cores_active": (raw >> 48) & 0xFF,
        "8_cores_active": (raw >> 56) & 0xFF,
    }


def decode_rapl_power_unit(raw: int) -> Dict[str, float]:
    """Decode MSR_RAPL_POWER_UNIT (0x606)."""
    power_units = (raw >> 0) & 0xF
    energy_units = (raw >> 8) & 0x1F
    time_units = (raw >> 16) & 0xF
    
    return {
        "power_watts_per_unit": 1.0 / (2 ** power_units),
        "energy_joules_per_unit": 1.0 / (2 ** energy_units),
        "time_seconds_per_unit": 1.0 / (2 ** time_units),
        "raw": raw
    }


def decode_pkg_power_info(raw: int) -> Dict[str, Any]:
    """Decode MSR_PKG_POWER_INFO (0x614) - TDP and power info."""
    # Bits 14:0 = Thermal Design Power (TDP)
    tdp = (raw >> 0) & 0x7FFF
    # Bits 30:16 = Minimum Power
    min_power = (raw >> 16) & 0x7FFF
    # Bits 46:32 = Maximum Power
    max_power = (raw >> 32) & 0x7FFF
    # Bit 47 = Thermal Design Power Time Window
    tdp_time_window = (raw >> 47) & 0x1
    
    return {
        "tdp_watts": tdp,
        "min_power_watts": min_power,
        "max_power_watts": max_power,
        "tdp_time_window": tdp_time_window
    }


def decode_pkg_power_limit(raw: int) -> Dict[str, Any]:
    """Decode MSR_PKG_POWER_LIMIT (0x610)."""
    pl1_power = (raw >> 0) & 0x7FFF
    pl1_enabled = (raw >> 15) & 0x1
    pl1_clamp = (raw >> 16) & 0x1
    pl1_time = (raw >> 17) & 0x7F
    
    pl2_power = (raw >> 32) & 0x7FFF
    pl2_enabled = (raw >> 47) & 0x1
    pl2_clamp = (raw >> 48) & 0x1
    pl2_time = (raw >> 49) & 0x7F
    
    return {
        "pl1": {
            "power_units": pl1_power,
            "enabled": bool(pl1_enabled),
            "clamp": bool(pl1_clamp),
            "time_window": pl1_time
        },
        "pl2": {
            "power_units": pl2_power,
            "enabled": bool(pl2_enabled),
            "clamp": bool(pl2_clamp),
            "time_window": pl2_time
        },
        "raw": raw
    }


# Central MSR Registry
MSR_REGISTRY: Dict[str, MSRDefinition] = {
    "therm_status": MSRDefinition(
        "therm_status", 0x19C, MSRScope.CORE, decode_therm_status,
        "Thermal status - digital temperature sensor"
    ),
    "temperature_target": MSRDefinition(
        "temperature_target", 0x1A2, MSRScope.PACKAGE, decode_temperature_target,
        "Temperature target (Tj Max)"
    ),
    "turbo_ratio_limit": MSRDefinition(
        "turbo_ratio_limit", 0x1AD, MSRScope.PACKAGE, decode_turbo_ratio_limit,
        "Turbo boost ratio limits"
    ),
    "platform_info": MSRDefinition(
        "platform_info", 0x00CE, MSRScope.PACKAGE, None,
        "Platform information (max non-turbo ratio, etc.)"
    ),
    "rapl_power_unit": MSRDefinition(
        "rapl_power_unit", 0x0606, MSRScope.PACKAGE, decode_rapl_power_unit,
        "RAPL power unit (conversion factors)"
    ),
    "pkg_power_limit": MSRDefinition(
        "pkg_power_limit", 0x0610, MSRScope.PACKAGE, decode_pkg_power_limit,
        "Package power limit (PL1/PL2)"
    ),
    "pkg_energy_status": MSRDefinition(
        "pkg_energy_status", 0x0611, MSRScope.PACKAGE, None,
        "Package energy status counter"
    ),
    "pkg_power_info": MSRDefinition(
        "pkg_power_info", 0x0614, MSRScope.PACKAGE, decode_pkg_power_info,
        "Package power info (TDP, min/max power)"
    ),
    "dram_energy_status": MSRDefinition(
        "dram_energy_status", 0x0619, MSRScope.PACKAGE, None,
        "DRAM energy status counter"
    ),
    "pp0_energy_status": MSRDefinition(
        "pp0_energy_status", 0x0639, MSRScope.PACKAGE, None,
        "PP0 (cores) energy status counter"
    ),
    "pp1_energy_status": MSRDefinition(
        "pp1_energy_status", 0x0641, MSRScope.PACKAGE, None,
        "PP1 (uncore/GPU) energy status counter"
    ),
}

# Whitelist version for tracking changes
MSR_WHITELIST_VERSION = "1.1-intel"


class KernelHelper:
    def read_c_state_residency(self) -> dict:
        """
        Read C-state residency and APERF/MPERF for each core.
        Returns a dict: {core: {C3, C6, C7, APERF, MPERF, normalized_percentages...}}
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        results = {}
        try:
            # MSR addresses
            MSR_C3 = 0x3FC
            MSR_C6 = 0x3FD
            MSR_C7 = 0x3FE
            MSR_APERF = 0xE7
            MSR_MPERF = 0xE8
            num_cores = self.processor_count
            # Batch read all MSRs for all cores
            batch = []
            for cpu in range(num_cores):
                for msr in [MSR_C3, MSR_C6, MSR_C7, MSR_APERF, MSR_MPERF]:
                    batch.append({"cpu": cpu, "msr": msr})
            batch_results = self.read_msr_batch(batch)
            # Organize results per core
            per_core = {cpu: {} for cpu in range(num_cores)}
            for entry in batch_results:
                cpu = entry["cpu"]
                msr = entry["msr"]
                value = entry.get("value", 0)
                if msr == MSR_C3:
                    per_core[cpu]["C3"] = value
                elif msr == MSR_C6:
                    per_core[cpu]["C6"] = value
                elif msr == MSR_C7:
                    per_core[cpu]["C7"] = value
                elif msr == MSR_APERF:
                    per_core[cpu]["APERF"] = value
                elif msr == MSR_MPERF:
                    per_core[cpu]["MPERF"] = value
            # Normalize residency percentages and APERF/MPERF ratio
            for cpu, data in per_core.items():
                c3 = data.get("C3", 0)
                c6 = data.get("C6", 0)
                c7 = data.get("C7", 0)
                aperf = data.get("APERF", 0)
                mperf = data.get("MPERF", 0)
                total_c = c3 + c6 + c7
                norm = {}
                if total_c > 0:
                    norm["C3_%"] = round(100 * c3 / total_c, 2)
                    norm["C6_%"] = round(100 * c6 / total_c, 2)
                    norm["C7_%"] = round(100 * c7 / total_c, 2)
                else:
                    norm["C3_%"] = norm["C6_%"] = norm["C7_%"] = 0.0
                norm["APERF"] = aperf
                norm["MPERF"] = mperf
                norm["APERF/MPERF"] = round(aperf / mperf, 4) if mperf else 0.0
                results[cpu] = norm
            return results
        except Exception as e:
            return {"error": str(e)}


    def read_package_temperature(self) -> dict:
        """
        Read package temperature (summary, not per-core).
        Returns a dict: {"celsius": float, "tj_max": int, "digital_readout": int, ...}
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        try:
            tj_data = self.read_msr(0, MSR_REGISTRY["temperature_target"].msr)
            if tj_data:
                tj_decoded = decode_temperature_target(tj_data)
                tj_max = tj_decoded["tj_max_celsius"]
            else:
                tj_max = 100
            raw = self.read_msr(0, MSR_REGISTRY["therm_status"].msr)
            if raw is not None:
                decoded = decode_therm_status(raw)
                if decoded["valid"]:
                    celsius = tj_max - decoded["digital_readout"]
                    return {
                        "celsius": celsius,
                        "tj_max": tj_max,
                        "digital_readout": decoded["digital_readout"],
                        "source": "kernel_helper",
                        "msr": "package_temperature"
                    }
            return {"error": "unavailable"}
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            return {"error": str(type(e).__name__), "reason": str(e)}

    def __init__(self, broker_path: Optional[str] = None):
        """
        Initialize kernel helper.
        
        Args:
            broker_path: Path to halfax_kernel_broker.exe. If None, searches current dir.
        """
        self.broker_path = broker_path or self._find_broker()
        self.available = False
        self.version = None
        self.capabilities = {}
        self.processor_count = 0
        
        # Try to detect and initialize
        self._detect()
    
    def _find_broker(self) -> str:
        """Find broker executable in common locations."""
        # Check current directory
        local_broker = os.path.join(os.path.dirname(__file__), "halfax_kernel_broker.exe")
        if os.path.exists(local_broker):
            return local_broker
        
        # Check same directory as this module
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_broker = os.path.join(script_dir, "halfax_kernel_broker.exe")
        if os.path.exists(script_broker):
            return script_broker
        
        # Default name (will fail gracefully later)
        return "halfax_kernel_broker.exe"
    
    def _run_broker(self, args: list, json_mode: bool = True) -> Dict[str, Any]:
        """
        Run broker command and parse output.
        
        Args:
            args: Command arguments (without broker path)
            json_mode: Use JSON output mode
            
        Returns:
            Parsed JSON response or error dict
            
        Raises:
            KernelHelperNotAvailable: Driver not present
            KernelHelperAccessDenied: Access denied
            KernelHelperNotImplemented: Feature not implemented
            KernelHelperError: Other errors
        """
        cmd = [self.broker_path]
        if json_mode:
            cmd.append("--json")
        cmd.extend(args)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False  # Don't raise on non-zero exit
            )
            
            # Parse JSON output
            if json_mode:
                try:
                    data = json.loads(result.stdout.strip())
                except json.JSONDecodeError:
                    return {
                        "error": "parse_error",
                        "message": f"Failed to parse JSON: {result.stdout}",
                        "stderr": result.stderr
                    }
            else:
                data = {"output": result.stdout, "stderr": result.stderr}
            
            # Map exit codes to exceptions
            if result.returncode == 1:  # EXIT_DRIVER_NOT_PRESENT
                raise KernelHelperNotAvailable(
                    data.get("message", "Kernel driver not present or not loaded")
                )
            elif result.returncode == 2:  # EXIT_ACCESS_DENIED
                raise KernelHelperAccessDenied(
                    data.get("message", "Access denied")
                )
            elif result.returncode == 3:  # EXIT_NOT_IMPLEMENTED
                raise KernelHelperNotImplemented(
                    data.get("message", "Feature not implemented")
                )
            elif result.returncode == 4:  # EXIT_INVALID_PARAMETER
                raise KernelHelperError(
                    f"Invalid parameter: {data.get('message', 'Unknown error')}"
                )
            elif result.returncode == 5:  # EXIT_OPERATION_FAILED
                raise KernelHelperError(
                    f"Operation failed: {data.get('message', 'Unknown error')}"
                )
            elif result.returncode != 0:
                raise KernelHelperError(
                    f"Broker returned exit code {result.returncode}: {data}"
                )
            
            return data
            
        except FileNotFoundError:
            raise KernelHelperNotAvailable(
                f"Kernel broker not found at: {self.broker_path}"
            )
        except subprocess.SubprocessError as e:
            raise KernelHelperError(f"Failed to execute broker: {e}")
    
    def _detect(self):
        """Detect if kernel helper is available and get capabilities."""
        try:
            # Get version
            ver_data = self._run_broker(["--version"])
            if ver_data.get("status") == "success":
                self.version = ver_data.get("version")
            
            # Get capabilities
            cap_data = self._run_broker(["--capabilities"])
            if cap_data.get("status") == "success":
                self.capabilities = {
                    "msr_read": cap_data.get("msr_read", False),
                    "msr_write": cap_data.get("msr_write", False),
                    "pci_read": cap_data.get("pci_read", False),
                    "smbus_read": cap_data.get("smbus_read", False),
                    "multicore": cap_data.get("multicore", False),
                }
                self.processor_count = cap_data.get("processor_count", 0)
                self.available = True
        except KernelHelperNotAvailable:
            # Expected if driver not loaded
            self.available = False
        except Exception as e:
            # Unexpected error, but don't fail initialization
            self.available = False
            import warnings
            warnings.warn(f"Failed to detect kernel helper: {e}")
    
    def read_msr(self, cpu: int, msr: int) -> Optional[int]:
        """
        Read MSR (Model-Specific Register) on given CPU core.
        
        Args:
            cpu: Logical CPU number (0-based)
            msr: MSR register number (e.g., 0x19C for temp)
            
        Returns:
            64-bit MSR value, or None if unavailable
            
        Raises:
            KernelHelperAccessDenied: MSR not whitelisted
            KernelHelperError: Other errors
            
        Example:
            >>> helper.read_msr(0, 0x19C)  # Read temperature MSR
            0x88340000
        """
        if not self.available:
            return None
        
        data = self._run_broker(["--read-msr", str(cpu), hex(msr)])
        
        if data.get("status") == "success":
            value_str = data.get("value", "0x0")
            return int(value_str, 16)
        
        return None
    
    def read_msr_all_cores(self, msr: int) -> Dict[int, Optional[int]]:
        """
        Read MSR on all CPU cores.
        
        Args:
            msr: MSR register number
            
        Returns:
            Dictionary mapping CPU number to MSR value
            
        Example:
            >>> temps = helper.read_msr_all_cores(0x19C)
            >>> for cpu, val in temps.items():
            ...     print(f"CPU {cpu}: {val:#x}")
        """
        results = {}
        for cpu in range(self.processor_count):
            try:
                results[cpu] = self.read_msr(cpu, msr)
            except (KernelHelperError, KernelHelperAccessDenied):
                results[cpu] = None
        return results
    
    def read_pci(self, bus: int, device: int, function: int, 
                 offset: int, length: int = 4) -> Optional[int]:
        """
        Read PCI configuration space.
        
        Args:
            bus: PCI bus number
            device: PCI device number
            function: PCI function number
            offset: Config space offset
            length: Bytes to read (1, 2, or 4)
            
        Returns:
            PCI config value, or None if unavailable
            
        Raises:
            KernelHelperNotImplemented: PCI reading not implemented
        """
        if not self.available:
            return None
        
        data = self._run_broker([
            "--read-pci",
            f"{bus}:{device}:{function}",
            hex(offset),
            str(length)
        ])
        
        if data.get("status") == "success":
            value_str = data.get("value", "0x0")
            return int(value_str, 16)
        
        return None

    def _get_pci_capability_offset(self, bus: int, device: int, function: int, cap_id: int) -> Optional[int]:
        """
        Walk the standard PCI capability list and return the offset of a capability by ID.

        Returns None if not present or on error.
        """
        try:
            # Capability pointer stored at config offset 0x34 (byte)
            ptr = self.read_pci(bus, device, function, 0x34, 1)
            if not ptr:
                return None
            ptr = ptr & 0xFF
            # Basic validation
            visited = set()
            while ptr and ptr not in visited and 0x40 <= ptr <= 0xF8:
                visited.add(ptr)
                # Read capability ID at ptr (1 byte)
                cid = self.read_pci(bus, device, function, ptr, 1)
                if cid is None:
                    return None
                cid = cid & 0xFF
                if cid == cap_id:
                    return ptr
                # Next pointer is at ptr + 1 (1 byte)
                next_ptr = self.read_pci(bus, device, function, ptr + 1, 1)
                if not next_ptr:
                    break
                ptr = next_ptr & 0xFF
        except Exception:
            return None
        return None

    def get_pcie_link_info(self, bus: int, device: int, function: int) -> Optional[Dict[str, Any]]:
        """
        Read PCIe Link Status from the PCI Express Capability (if present).

        Returns a dict with `link_width`, `link_speed_gt_s`, `bandwidth_gb_s`,
        and raw register values, or None if unavailable.
        """
        if not self.available:
            return None

        try:
            cap_ptr = self._get_pci_capability_offset(bus, device, function, 0x10)
            if not cap_ptr:
                return None

            # Link Status register is at cap_ptr + 0x12 (2 bytes)
            raw = self.read_pci(bus, device, function, cap_ptr + 0x12, 2)
            if raw is None:
                return None

            link_status = raw & 0xFFFF
            speed_code = link_status & 0xF
            width = (link_status >> 4) & 0x3F

            # Map negotiated speed code to GT/s (common mapping)
            speed_map = {
                1: 2.5,
                2: 5.0,
                3: 8.0,
                4: 16.0,
                5: 32.0
            }
            gt_s = speed_map.get(speed_code, None)

            # Approximate per-lane GB/s for common generations
            per_lane_gb = {
                1: 0.25,
                2: 0.5,
                3: 0.985,
                4: 1.969,
                5: 3.938
            }
            gb_per_lane = per_lane_gb.get(speed_code, None)
            bandwidth = (gb_per_lane * width) if (gb_per_lane is not None and width) else None

            return {
                "link_width": int(width),
                "link_speed_gt_s": gt_s,
                "bandwidth_gb_s": float(bandwidth) if bandwidth is not None else None,
                "raw_link_status": link_status,
                "source": "kernel_helper"
            }
        except Exception:
            return None

    def get_resizable_bar_state(self, bus: int, device: int, function: int) -> Optional[Dict[str, Any]]:
        """
        Best-effort Resizable BAR detection stub.

        Returns a dict with keys:
          - supported: True/False/None
          - enabled: True/False/None
          - source: 'kernel_helper'
          - note: explanatory text

        NOTE: Accurate ReBAR detection often requires platform-specific support
        or ACPI/BIOS interfaces. This implementation is conservative and
        returns 'None' for unknown when it cannot determine state.
        """
        if not self.available:
            return None

        try:
            # Placeholder implementation: we don't yet have a reliable,
            # cross-vendor config-space method implemented here. Return a
            # best-effort stub to be enriched later.
            return {
                "supported": None,
                "enabled": None,
                "source": "kernel_helper",
                "note": "best-effort stub; requires extended-capability parsing or vendor API"
            }
        except Exception:
            return None
    
    def get_presence_state(self) -> HelperPresence:
        """
        Get three-state presence model.
        
        Returns:
            ABSENT: Driver not loaded or broker not found
            PRESENT_LIMITED: MSR only, PCI/SMBus not implemented
            PRESENT_FULL: All capabilities available
        """
        if not self.available:
            return HelperPresence.ABSENT
        
        # Check if PCI and SMBus are implemented
        has_pci = self.capabilities.get("pci_read", False)
        has_smbus = self.capabilities.get("smbus_read", False)
        
        if has_pci and has_smbus:
            return HelperPresence.PRESENT_FULL
        else:
            return HelperPresence.PRESENT_LIMITED
    
    def get_info_dict(self) -> Dict[str, Any]:
        """
        Get kernel helper status for reporting (first-class data source).
        
        This is the standardized audit anchor for System Reporter.
        Includes source identity, capabilities, and provenance info.
        
        Returns:
            Dictionary with helper status, version, capabilities, and whitelist version.
            Suitable for inclusion in Halfax System Reporter output.
            
        Example:
            >>> info = helper.get_info_dict()
            >>> print(json.dumps(info, indent=2))
            {
              "source": "kernel_helper",
              "presence": "present_but_limited",
              "available": true,
              "driver_version": "1.0.1",
              "protocol_version": 1,
              "msr_whitelist_version": "1.0-intel",
              ...
            }
        """
        presence = self.get_presence_state()
        
        info = {
            "source": "kernel_helper",
            "presence": presence.value,
            "available": self.available,
            "driver_version": self.version,
            "protocol_version": 1,  # HALFAX_PROTOCOL_VERSION from header
            "msr_whitelist_version": MSR_WHITELIST_VERSION,
            "broker_path": self.broker_path,
            "processor_count": self.processor_count,
        }
        
        if self.available:
            info["capabilities"] = {
                "raw_flags": self.capabilities,
                "decoded": {
                    "msr_read": self.capabilities.get("msr_read", False),
                    "msr_write": self.capabilities.get("msr_write", False),
                    "pci_read": self.capabilities.get("pci_read", False),
                    "smbus_read": self.capabilities.get("smbus_read", False),
                    "multicore": self.capabilities.get("multicore", False),
                }
            }
            info["available_msrs"] = list(MSR_REGISTRY.keys())
        else:
            info["reason"] = "Driver not loaded or broker not found"
        
        return info
    
    # High-level Semantic APIs
    # These hide MSR complexity and return human-readable values
    
    def read_core_temperatures(self) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Read temperature on all CPU cores (semantic API).
        
        Returns:
            Dictionary mapping CPU core to temperature data:
            {
                0: {"celsius": 45.0, "tj_max": 100, "margin": 55, "source": "kernel_helper"},
                1: {"celsius": 47.0, "tj_max": 100, "margin": 53, "source": "kernel_helper"},
                ...
            }
            
            Returns None for cores where reading failed.
            
        Raises:
            KernelHelperNotAvailable: If helper not present
            
        Example:
            >>> temps = helper.read_core_temperatures()
            >>> for core, data in temps.items():
            ...     if data and 'celsius' in data:
            ...         print(f"Core {core}: {data['celsius']}°C")
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        results = {}
        
        # Get Tj Max (package-wide)
        tj_max = 100  # Default fallback
        try:
            tj_data = self.read_msr(0, MSR_REGISTRY["temperature_target"].msr)
            if tj_data:
                decoded = decode_temperature_target(tj_data)
                tj_max = decoded["tj_max_celsius"]
        except (KernelHelperError, KernelHelperAccessDenied):
            pass  # Use default
        
        # Read temperature on each core
        for cpu in range(self.processor_count):
            try:
                raw = self.read_msr(cpu, MSR_REGISTRY["therm_status"].msr)
                if raw is not None:
                    decoded = decode_therm_status(raw)
                    if decoded["valid"]:
                        celsius = tj_max - decoded["digital_readout"]
                        results[cpu] = {
                            "celsius": celsius,
                            "tj_max": tj_max,
                            "margin": decoded["digital_readout"],
                            "source": "kernel_helper",
                            "msr": "IA32_THERM_STATUS",
                            "provenance": {
                                "method": "read_core_temperatures",
                                "msr": "0x19C",
                                "description": "per-core digital temperature sensor"
                            }
                        }
                    else:
                        results[cpu] = None
                else:
                    results[cpu] = None
            except Exception:
                results[cpu] = None
        return results
    
    def read_microcode_version(self) -> Optional[Dict[str, Any]]:
        """
        Read microcode version from MSR_IA32_BIOS_SIGN_ID (0x8B).
        
        Returns:
            Dictionary with microcode information:
            {
                "microcode_version": "0x1A",
                "update_signature": 0x1A,
                "source": "kernel_helper",
                "msr": "MSR_IA32_BIOS_SIGN_ID"
            }
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        try:
            raw = self.read_msr(0, 0x8B)  # MSR_IA32_BIOS_SIGN_ID
            if raw is not None:
                microcode_version = (raw >> 32) & 0xFFFFFFFF
                return {
                    "microcode_version": f"0x{microcode_version:X}",
                    "update_signature": microcode_version,
                    "source": "kernel_helper",
                    "msr": "MSR_IA32_BIOS_SIGN_ID"
                }
            return None
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            return {"error": str(type(e).__name__), "reason": str(e)}
    
    def read_package_energy(self) -> Optional[Dict[str, Any]]:
        """
        Read package energy status and calculate real-time power (NEW - High Priority).
        
        Returns:
            Dictionary with package energy and power data:
            {
                "energy_joules": 12345.67,
                "watts": 45.2,
                "source": "kernel_helper",
                "msr": "MSR_PKG_ENERGY_STATUS"
            }
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        try:
            # Get energy units first
            power_unit_raw = self.read_msr(0, MSR_REGISTRY["rapl_power_unit"].msr)
            if power_unit_raw:
                power_unit = decode_rapl_power_unit(power_unit_raw)
                joules_per_unit = power_unit["energy_joules_per_unit"]
            else:
                joules_per_unit = 0.000061  # Default for Intel
            
            # Read package energy status
            package_energy_raw = self.read_msr(0, MSR_REGISTRY["pkg_energy_status"].msr)
            if package_energy_raw is not None:
                energy_joules = (package_energy_raw & 0xFFFFFFFF) * joules_per_unit
                
                # For power calculation, we need time delta - this is a simplified version
                # Real implementation would store previous reading and calculate delta/time
                # For now, return energy and estimated power based on typical usage
                estimated_watts = energy_joules * 1000  # Rough estimate
                
                return {
                    "energy_joules": energy_joules,
                    "watts": estimated_watts,
                    "source": "kernel_helper",
                    "msr": "MSR_PKG_ENERGY_STATUS"
                }
            else:
                return None
                
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            return {"error": str(type(e).__name__), "reason": str(e)}
    
    def read_tdp_info(self) -> Optional[Dict[str, Any]]:
        """
        Read TDP information from MSR_PKG_POWER_INFO.
        
        Returns:
            Dictionary with TDP information:
            {
                "tdp_watts": 45,
                "min_power_watts": 30,
                "max_power_watts": 60,
                "tdp_time_window": 1,
                "source": "kernel_helper",
                "msr": "MSR_PKG_POWER_INFO"
            }
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        try:
            raw = self.read_msr(0, MSR_REGISTRY["pkg_power_info"].msr)
            if raw is not None:
                decoded = decode_pkg_power_info(raw)
                decoded["source"] = "kernel_helper"
                decoded["msr"] = "MSR_PKG_POWER_INFO"
                return decoded
            return None
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            raise KernelHelperError(f"Failed to read TDP info: {e}")
    
    def read_package_power(self) -> Optional[Dict[str, Any]]:
        """
        Read package power limits and settings (semantic API).
        
        Returns:
            Dictionary with power limit data:
            {
                "pl1": {"watts": 65.0, "enabled": true, "clamp": true},
                "pl2": {"watts": 90.0, "enabled": true, "clamp": false},
                "source": "kernel_helper"
            }
            
            Returns None if unavailable.
            
        Raises:
            KernelHelperNotAvailable: If helper not present
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        try:
            # Get power units
            power_unit_raw = self.read_msr(0, MSR_REGISTRY["rapl_power_unit"].msr)
            if power_unit_raw:
                power_unit = decode_rapl_power_unit(power_unit_raw)
                watts_per_unit = power_unit["power_watts_per_unit"]
            else:
                watts_per_unit = 0.125  # Default for Intel

            # Get power limits
            power_limit_raw = self.read_msr(0, MSR_REGISTRY["pkg_power_limit"].msr)
            if not power_limit_raw:
                return None

            power_limit = decode_pkg_power_limit(power_limit_raw)

            return {
                "pl1": {
                    "watts": power_limit["pl1"]["power_units"] * watts_per_unit,
                    "enabled": power_limit["pl1"]["enabled"],
                    "clamp": power_limit["pl1"]["clamp"],
                    "time_window": power_limit["pl1"]["time_window"]
                },
                "pl2": {
                    "watts": power_limit["pl2"]["power_units"] * watts_per_unit,
                    "enabled": power_limit["pl2"]["enabled"],
                    "clamp": power_limit["pl2"]["clamp"],
                    "time_window": power_limit["pl2"]["time_window"]
                },
                "source": "kernel_helper",
                "msr": "MSR_PKG_POWER_LIMIT"
            }
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            return {
                "error": str(type(e).__name__),
                "reason": str(e)
            }
    
    def read_energy_counters(self) -> Dict[str, Any]:
        """
        Read RAPL energy counters (semantic API).
        
        Returns:
            Dictionary with energy counter data (raw counters, needs delta for power):
            {
                "package": {"counter": 12345678, "joules_per_unit": 0.000061},
                "cores": {"counter": 6789012, "joules_per_unit": 0.000061},
                "dram": {"counter": 3456789, "joules_per_unit": 0.000061},
                "source": "kernel_helper"
            }
            
            Note: Take deltas over time and divide by time to get watts.
            
        Raises:
            KernelHelperNotAvailable: If helper not present
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        results = {"source": "kernel_helper"}
        
        try:
            # Get energy units
            power_unit_raw = self.read_msr(0, MSR_REGISTRY["rapl_power_unit"].msr)
            if power_unit_raw:
                power_unit = decode_rapl_power_unit(power_unit_raw)
                joules_per_unit = power_unit["energy_joules_per_unit"]
            else:
                joules_per_unit = 0.000061  # Default for Intel
            
            # Read counters (package-wide MSRs, so CPU 0 is canonical)
            for name, msr_name in [
                ("package", "pkg_energy_status"),
                ("cores", "pp0_energy_status"),
                ("uncore", "pp1_energy_status"),
                ("dram", "dram_energy_status")
            ]:
                try:
                    if msr_name in MSR_REGISTRY:
                        raw = self.read_msr(0, MSR_REGISTRY[msr_name].msr)
                        if raw is not None:
                            results[name] = {
                                "counter": raw & 0xFFFFFFFF,  # 32-bit counter
                                "joules_per_unit": joules_per_unit,
                                "msr": msr_name
                            }
                except (KernelHelperError, KernelHelperAccessDenied):
                    results[name] = {"error": "unavailable"}
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            results["error"] = str(e)
        
        return results
    
    def read_turbo_ratios(self) -> Optional[Dict[str, Any]]:
        """
        Read turbo boost ratio limits (semantic API).
        
        Returns:
            Dictionary with turbo ratios for different core counts:
            {
                "1_core_active": 48,  # 4.8 GHz
                "2_cores_active": 46,
                ...
                "source": "kernel_helper"
            }
            
        Raises:
            KernelHelperNotAvailable: If helper not present
        """
        if not self.available:
            raise KernelHelperNotAvailable("Kernel helper not available")
        
        try:
            raw = self.read_msr(0, MSR_REGISTRY["turbo_ratio_limit"].msr)
            if raw is not None:
                decoded = decode_turbo_ratio_limit(raw)
                # Add provenance/source metadata consistent with other APIs
                decoded["source"] = "kernel_helper"
                decoded["msr"] = "MSR_TURBO_RATIO_LIMIT"
                return decoded
            return None
        except (KernelHelperError, KernelHelperAccessDenied) as e:
            return {"error": str(type(e).__name__), "reason": str(e)}
        except Exception as e:
                return {"error": "Exception", "reason": str(e)}
    
    def read_msr_batch(self, requests: list) -> list:
        """
        Batch read MSRs using the kernel broker. Each request is a dict: {"cpu": int, "msr": int}
        Returns a list of dicts: {"cpu": int, "msr": int, "value": int, "status": int}
        """
        import json
        if not self.available:
            return []
        # Prepare JSON array for broker
        batch_json = json.dumps(requests)
        try:
            import subprocess
            proc = subprocess.Popen(
                [self.broker_path, "--json", "--read-msr-batch", str(len(requests))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            out, err = proc.communicate(batch_json, timeout=10)
            if proc.returncode == 0:
                data = json.loads(out)
                if data.get("status") == "success":
                    return data["results"]
            return []
        except Exception as e:
            return []

        # ...existing code...
            status = "✓" if enabled else "✗"
            print(f"    {status} {cap}")
        
        print(f"\n  Available MSRs: {len(info['available_msrs'])}")
        
        # Test semantic APIs
        print("\n" + "="*60)
        print("Testing Semantic APIs...")
        print("="*60)
        
        # Core temperatures
        print("\n1. Core Temperatures:")
        try:
            temps = helper.read_core_temperatures()
            for core, data in sorted(temps.items())[:4]:  # Show first 4 cores
                if data and 'celsius' in data:
                    print(f"   Core {core}: {data['celsius']:.1f}°C (margin: {data['margin']}°C)")
                elif data and 'error' in data:
                    print(f"   Core {core}: {data['reason']}")
                else:
                    print(f"   Core {core}: unavailable")
            if len(temps) > 4:
                print(f"   ... and {len(temps) - 4} more cores")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Package power
        print("\n2. Package Power Limits:")
        try:
            power = helper.read_package_power()
            if power and 'pl1' in power:
                print(f"   PL1: {power['pl1']['watts']:.1f}W (enabled: {power['pl1']['enabled']})")
                print(f"   PL2: {power['pl2']['watts']:.1f}W (enabled: {power['pl2']['enabled']})")
            elif power and 'error' in power:
                print(f"   Error: {power['reason']}")
            else:
                print(f"   Not available")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Energy counters
        print("\n3. RAPL Energy Counters:")
        try:
            energy = helper.read_energy_counters()
            for domain in ['package', 'cores', 'dram', 'uncore']:
                if domain in energy and 'counter' in energy[domain]:
                    counter = energy[domain]['counter']
                    print(f"   {domain.capitalize()}: counter={counter} (0x{counter:08X})")
                elif domain in energy and 'error' in energy[domain]:
                    print(f"   {domain.capitalize()}: {energy[domain]['error']}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Turbo ratios
        print("\n4. Turbo Boost Ratios:")
        try:
            ratios = helper.read_turbo_ratios()
            if ratios and '1_core_active' in ratios:
                for key in ['1_core_active', '2_cores_active', '4_cores_active']:
                    if key in ratios:
                        ratio = ratios[key]
                        ghz = ratio / 10.0
                        print(f"   {key}: {ratio} ({ghz:.1f} GHz)")
            elif ratios and 'error' in ratios:
                print(f"   Error: {ratios['reason']}")
            else:
                print(f"   Not available")
        except Exception as e:
            print(f"   Error: {e}")
        
        print("\n" + "="*60)
        print("Integration Example for main.py:")
        print("="*60)
        print("""
from halfax_kernel_helper import KernelHelper

helper = KernelHelper()
report = {
    "kernel_helper": helper.get_info_dict(),
}

if helper.available:
    report["temperatures"] = helper.read_core_temperatures()
    report["power_limits"] = helper.read_package_power()
    report["energy_counters"] = helper.read_energy_counters()
""")
        print(f"\n  Reason: {info.get('reason', 'Unknown')}")
        print("\nKernel helper not available. Ensure:")
        print("  1. Driver is loaded (sc query HalfaxTelemetry)")
        print("  2. Running as Administrator")
        print("  3. Broker executable present in same directory")
        print("  4. Test signing enabled (bcdedit | findstr testsigning)")



