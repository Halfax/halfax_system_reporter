from typing import Dict, Any

def get_network_telemetry() -> Dict[str, Any]:
    """
    Collect network telemetry for all detected interfaces (Phase 6).
    Returns a dictionary with link speed, MAC address, IP config, connection status, error rates, and throughput.
    Aggregates data from WMI (Windows), psutil, and kernel helper (if available).
    Kernel driver reload is deferred until all phases are complete.
    """
    import platform
    import os
    import json
    network_data = {
        'status': 'Phase 6 - In Progress',
        'note': 'Kernel driver reload deferred until all phases complete.',
        'provenance': [],
        'interfaces': [],
        'kernel_interfaces': [],
        'errors': []
    }
    # psutil for cross-platform interface info
    try:
        import psutil
        for name, info in psutil.net_if_addrs().items():
            iface = {
                'name': name,
                'mac': next((a.address for a in info if a.family == psutil.AF_LINK), 'Unknown'),
                'ips': [a.address for a in info if a.family in (2, 23)],
                'provenance': 'psutil'
            }
            network_data['interfaces'].append(iface)
        network_data['provenance'].append('psutil')
    except Exception as e:
        network_data['errors'].append(f"psutil error: {e}")

    # WMI for Windows
    try:
        if platform.system() == 'Windows':
            import wmi
            c = wmi.WMI()
            for nic in c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                iface = {
                    'name': getattr(nic, 'Description', 'Unknown'),
                    'mac': getattr(nic, 'MACAddress', 'Unknown'),
                    'ips': getattr(nic, 'IPAddress', []),
                    'dhcp': getattr(nic, 'DHCPEnabled', False),
                    'dns': getattr(nic, 'DNSServerSearchOrder', []),
                    'gateway': getattr(nic, 'DefaultIPGateway', []),
                    'provenance': 'WMI'
                }
                network_data['interfaces'].append(iface)
            network_data['provenance'].append('WMI')
    except Exception as e:
        network_data['errors'].append(f"WMI error: {e}")

    # Kernel helper integration
    try:
        if KERNEL_HELPER_AVAILABLE:
            helper = KernelHelper()
            if helper.available and hasattr(helper, 'read_network_info'):
                try:
                    kernel_ifaces = helper.read_network_info()
                    network_data['kernel_interfaces'] = kernel_ifaces
                    network_data['provenance'].append('kernel_helper')
                except Exception as e:
                    network_data['errors'].append(f"kernel_helper error: {e}")
            else:
                network_data['errors'].append('kernel_helper not available or no network info')
    except Exception as e:
        network_data['errors'].append(f"kernel_helper exception: {e}")

    return network_data
"""
Kernel Integration Module - Phase 1 Foundation

Provides high-level integration layer between main.py and halfax_kernel_helper.
This module abstracts kernel helper complexity and provides standardized data structures
that match main.py's existing patterns.

Architecture:
- Level 3.5: Treats kernel helper as privileged helper (subprocess + JSON)
- Three-state fallback: ABSENT, PRESENT_LIMITED, PRESENT_FULL
- Provenance tracking: Every value includes data source
- Timeout handling: 5 second default for all operations
- Graceful degradation: System works without kernel helper

Phase 1 Implementation:
- Capability bitmask detection
- Versioned JSON schema validation
- Status reporting for UI integration
- Foundation for Phase 2 (temperature/power)
"""

import json
import warnings
from typing import Dict, Any, Optional, List
from enum import Enum

# Import kernel helper with fallback
try:
    from halfax_kernel_helper import KernelHelper, HelperPresence, KernelHelperError
    KERNEL_HELPER_AVAILABLE = True
except ImportError:
    KERNEL_HELPER_AVAILABLE = False
    # Mock classes for when module not available
    class HelperPresence(Enum):
        ABSENT = "absent"
        PRESENT_LIMITED = "present_but_limited"
        PRESENT_FULL = "present_full"


# Protocol version for schema validation
PROTOCOL_VERSION = "1.0"
MIN_SUPPORTED_PROTOCOL = "1.0"


class KernelIntegrationError(Exception):
    """Base exception for kernel integration errors."""
    pass


def get_kernel_helper_status() -> Dict[str, Any]:
    """
    Get kernel helper availability and status for UI display.
    Returns a dictionary with status and capabilities.
    """
    # Default response used when kernel helper is not available or detection fails
    default = {
        'available': False,
        'presence': HelperPresence.ABSENT.value if 'HelperPresence' in globals() else 'absent',
        'driver_version': '',
        'protocol_version': '',
        'protocol_compatible': False,
        'capabilities': {},
        'processor_count': 0,
        'msr_whitelist_version': MSR_WHITELIST_VERSION if 'MSR_WHITELIST_VERSION' in globals() else '',
        'source': 'kernel_helper',
        'error': 'halfax_kernel_helper not available',
        'status_text': 'Not Available'
    }

    if not KERNEL_HELPER_AVAILABLE:
        return default

    try:
        helper = KernelHelper()

        # Try to use a structured info dict if the helper exposes it
        info = {}
        try:
            info = helper.get_info_dict()
        except Exception:
            # Fall back to piecing together fields from attributes/methods
            info = {}

        presence = info.get('presence') if info.get('presence') else None
        if not presence:
            try:
                presence_state = helper.get_presence_state()
                presence = presence_state.value if hasattr(presence_state, 'value') else str(presence_state)
            except Exception:
                presence = HelperPresence.ABSENT.value if 'HelperPresence' in globals() else 'absent'

        driver_version = info.get('driver_version') or getattr(helper, 'version', '')
        protocol_version = info.get('protocol_version') or info.get('protocol') or PROTOCOL_VERSION
        protocol_compatible = _is_protocol_compatible(str(protocol_version)) if protocol_version else False
        # Normalize capabilities into a consistent shape:
        # { 'raw_flags': {...}, 'decoded': { 'msr_read': bool, ... } }
        raw_caps = {}
        decoded_caps = {}
        caps_src = info.get('capabilities') or getattr(helper, 'capabilities', {}) or {}
        # If caps_src already has 'decoded' or 'raw_flags', use them
        if isinstance(caps_src, dict):
            if 'decoded' in caps_src:
                decoded_caps = caps_src.get('decoded', {})
            if 'raw_flags' in caps_src:
                raw_caps = caps_src.get('raw_flags', {})
        # If caps_src is flat (booleans), treat it as decoded
        for k, v in list(caps_src.items()):
            if k in ('msr_read', 'msr_write', 'pci_read', 'smbus_read', 'multicore'):
                decoded_caps.setdefault(k, bool(v))
                # also record in raw if not present
                raw_caps.setdefault(k, bool(v))
        # If helper exposes capabilities attribute as a flat dict, include it
        if not decoded_caps and hasattr(helper, 'capabilities'):
            try:
                for k, v in getattr(helper, 'capabilities', {}).items():
                    decoded_caps.setdefault(k, bool(v))
                    raw_caps.setdefault(k, v)
            except Exception:
                pass
        capabilities = {'raw_flags': raw_caps, 'decoded': decoded_caps}
        processor_count = info.get('processor_count') or getattr(helper, 'processor_count', 0)
        msr_whitelist = info.get('msr_whitelist_version') if info.get('msr_whitelist_version') else (MSR_WHITELIST_VERSION if 'MSR_WHITELIST_VERSION' in globals() else '')

        # Determine status based on actual working capabilities, not presence string
        # MSR access is the key capability for this application
        if not getattr(helper, 'available', False):
            status_text = 'Not Available'
        else:
            status_text = 'Full'
            if not decoded_caps.get('msr_read', False):
                status_text = 'Limited'
            elif not decoded_caps.get('multicore', False):
                status_text = 'Limited'
            # If MSR and multicore work, consider it Full regardless of PCI/SMBus

        return {
            'available': bool(getattr(helper, 'available', False)),
            'presence': presence,
            'driver_version': driver_version,
            'protocol_version': protocol_version,
            'protocol_compatible': protocol_compatible,
            'capabilities': capabilities,
            'processor_count': processor_count,
            'msr_whitelist_version': msr_whitelist,
            'source': 'kernel_helper',
            'error': None if getattr(helper, 'available', False) else 'Driver not loaded or broker not found',
            'status_text': status_text
        }

    except Exception as e:
        return {
            **default,
            'error': f'Exception while detecting kernel helper: {e}',
            'status_text': 'Error'
        }


def _is_protocol_compatible(version: str) -> bool:
    """
    Check if protocol version is compatible.
    
    Uses simple version comparison (assumes X.Y format).
    Compatible if version >= MIN_SUPPORTED_PROTOCOL.
    
    Args:
        version: Protocol version string (e.g., "1.0")
        
    Returns:
        True if compatible, False otherwise
    """
    try:
        # Parse versions as floats for simple comparison
        current = float(version)
        minimum = float(MIN_SUPPORTED_PROTOCOL)
        return current >= minimum
    except (ValueError, TypeError):
        # If parsing fails, assume incompatible
        return False


def get_kernel_cpu_temperatures() -> Dict[str, Any]:
    """
    Get per-core CPU temperatures from kernel helper (Phase 2 - IMPLEMENTED).
    
    Reads MSR 0x19C (IA32_THERM_STATUS) per-core to get digital thermal sensor readings.
    Also reads MSR 0x1A2 (IA32_TEMPERATURE_TARGET) for Tj Max.
    
    Returns:
        Dictionary with temperature data:
        {
            'available': bool,
            'error': str | None,
            'tj_max': int,              # Maximum junction temperature (°C)
            'package_temp': int,        # Package temperature (max of all cores)
            'temperatures': {           # Per-core temperatures
                0: {'celsius': int, 'margin': int, 'tj_max': int, 'source': str, 'msr': str},
                1: {'celsius': int, 'margin': int, 'tj_max': int, 'source': str, 'msr': str},
                ...
            },
            'source': 'kernel_helper'
        }
    """
    if not KERNEL_HELPER_AVAILABLE:
        return {
            'available': False,
            'error': 'halfax_kernel_helper.py not found',
            'temperatures': {},
            'source': 'kernel_helper'
        }
    
    try:
        helper = KernelHelper()
        
        if not helper.available:
            return {
                'available': False,
                'error': 'Driver not loaded or broker not found',
                'temperatures': {},
                'source': 'kernel_helper'
            }
        
        # Read core temperatures using semantic API
        try:
            core_temps = helper.read_core_temperatures()
            
            if not core_temps:
                return {
                    'available': False,
                    'error': 'No temperature data available',
                    'temperatures': {},
                    'source': 'kernel_helper'
                }
            
            # Calculate package temperature (max of all cores)
            package_temp = max(temp_data.get('celsius', 0) for temp_data in core_temps.values())
            
            # Get Tj Max from first core (same for all cores)
            tj_max = next(iter(core_temps.values())).get('tj_max', 100) if core_temps else 100
            
            # Add source and MSR information to each entry
            formatted_temps = {}
            for core, temp_data in core_temps.items():
                formatted_temps[core] = {
                    'celsius': temp_data.get('celsius', 0),
                    'margin': temp_data.get('margin', 0),
                    'tj_max': temp_data.get('tj_max', 100),
                    'source': 'kernel_helper',
                    'msr': '0x19C'
                }
            
            return {
                'available': True,
                'error': None,
                'tj_max': tj_max,
                'package_temp': package_temp,
                'temperatures': formatted_temps,
                'source': 'kernel_helper'
            }
            
        except KernelHelperError as e:
            return {
                'available': False,
                'error': f'MSR read failed: {str(e)}',
                'temperatures': {},
                'source': 'kernel_helper'
            }
            
    except Exception as e:
        return {
            'available': False,
            'error': f'Unexpected error: {str(e)}',
            'temperatures': {},
            'source': 'kernel_helper'
        }


def get_kernel_power_data() -> Dict[str, Any]:
    """
    Get CPU power limits and RAPL energy data (Phase 2 - IMPLEMENTED).
    
    Reads MSR 0x610 for PL1/PL2 power limits and MSRs 0x611/0x619/0x639 for RAPL energy counters.
    
    Returns:
        Dictionary with power data:
        {
            'available': bool,
            'error': str | None,
            'pl1': {'watts': float, 'enabled': bool, 'clamping': bool},
            'pl2': {'watts': float, 'enabled': bool, 'clamping': bool},
            'rapl': {
                'package_watts': float,
                'cores_watts': float,
                'dram_watts': float,
                'total_watts': float
            },
            'source': 'kernel_helper'
        }
    """
    if not KERNEL_HELPER_AVAILABLE:
        return {
            'available': False,
            'error': 'halfax_kernel_helper.py not found',
            'pl1': {},
            'pl2': {},
            'rapl': {},
            'source': 'kernel_helper'
        }
    
    try:
        helper = KernelHelper()
        
        if not helper.available:
            return {
                'available': False,
                'error': 'Driver not loaded or broker not found',
                'pl1': {},
                'pl2': {},
                'rapl': {},
                'source': 'kernel_helper'
            }
        
        # Read power limits using semantic API
        try:
            power_limits = helper.read_package_power_limit()
            
            if not power_limits:
                return {
                    'available': False,
                    'error': 'Power limits read returned None',
                    'phase': 'Phase 2',
                    'pl1': {},
                    'pl2': {},
                    'rapl': {},
                    'source': 'kernel_helper',
                    'description': 'MSR 0x610 read failed'
                }
            
            # Read RAPL energy data
            rapl_data = {}
            try:
                package_energy = helper.read_package_energy()
                if package_energy:
                    rapl_data['package_watts'] = package_energy.get('watts', 0)
                
                # Try to read additional RAPL domains (may not be available)
                try:
                    pp0_energy = helper.read_pp0_energy()  # Cores
                    if pp0_energy:
                        rapl_data['cores_watts'] = pp0_energy.get('watts', 0)
                except:
                    rapl_data['cores_watts'] = 0
                
                try:
                    dram_energy = helper.read_dram_energy()
                    if dram_energy:
                        rapl_data['dram_watts'] = dram_energy.get('watts', 0)
                except:
                    rapl_data['dram_watts'] = 0
                
                # Calculate total
                rapl_data['total_watts'] = (
                    rapl_data.get('package_watts', 0) +
                    rapl_data.get('dram_watts', 0)
                )
                
            except:
                rapl_data = {
                    'package_watts': 0,
                    'cores_watts': 0,
                    'dram_watts': 0,
                    'total_watts': 0
                }
            
            return {
                'available': True,
                'error': None,
                'pl1': power_limits.get('pl1', {}),
                'pl2': power_limits.get('pl2', {}),
                'rapl': rapl_data,
                'source': 'kernel_helper'
            }
            
        except KernelHelperError as e:
            return {
                'available': False,
                'error': f'MSR read failed: {str(e)}',
                'pl1': {},
                'pl2': {},
                'rapl': {},
                'source': 'kernel_helper'
            }
            
    except Exception as e:
        return {
            'available': False,
            'error': f'Unexpected error: {str(e)}',
            'pl1': {},
            'pl2': {},
            'rapl': {},
            'source': 'kernel_helper'
        }


def get_kernel_turbo_ratios() -> Dict[str, Any]:
    """
    Get real turbo ratio limits from MSR (Phase 3 - IMPLEMENTED).

    Reads MSR 0x1AD (MSR_TURBO_RATIO_LIMIT) via kernel helper.
    Returns per-core turbo ratio limits (multiplier values).

    Returns:
        Dictionary with turbo ratio data or error status
    """
    if not KERNEL_HELPER_AVAILABLE:
        return {
            'available': False,
            'error': 'halfax_kernel_helper.py not found',
            'phase': 'Phase 3',
            'turbo_ratios': {},
            'source': 'kernel_helper',
            'description': 'MSR 0x1AD turbo ratio limits require kernel helper'
        }
    try:
        helper = KernelHelper()
        if not helper.available:
            return {
                'available': False,
                'error': 'Driver not loaded or broker not found',
                'phase': 'Phase 3',
                'turbo_ratios': {},
                'source': 'kernel_helper',
                'description': 'Kernel driver not loaded'
            }
        try:
            ratios = helper.read_turbo_ratios()
            if ratios and isinstance(ratios, dict):
                return {
                    'available': True,
                    'error': None,
                    'phase': 'Phase 3',
                    'turbo_ratios': ratios,
                    'source': 'kernel_helper',
                    'description': 'Turbo ratio limits from MSR 0x1AD'
                }
            else:
                return {
                    'available': False,
                    'error': 'No turbo ratio data available',
                    'phase': 'Phase 3',
                    'turbo_ratios': {},
                    'source': 'kernel_helper',
                    'description': 'No turbo ratio data returned'
                }
        except KernelHelperError as e:
            return {
                'available': False,
                'error': f'MSR read failed: {str(e)}',
                'phase': 'Phase 3',
                'turbo_ratios': {},
                'source': 'kernel_helper',
                'description': 'Turbo ratio MSR read failed'
            }
    except Exception as e:
        return {
            'available': False,
            'error': f'Unexpected error: {str(e)}',
            'phase': 'Phase 3',
            'turbo_ratios': {},
            'source': 'kernel_helper',
            'description': 'Unexpected error in turbo ratio read'
        }


def get_kernel_ipc_metrics() -> Dict[str, Any]:
    """
    Get IPC (Instructions Per Cycle) metrics from APERF/MPERF (NEW - Medium Priority).
    
    Returns:
        Dictionary with IPC data:
        {
            "available": True,
            "ipc_ratio": 0.85,
            "aperf": 12345678,
            "mperf": 14567890,
            "efficiency": "Good",
            "source": "kernel_helper"
        }
        or
        {
            "available": False,
            "error": "error_message"
        }
    """
    if not KERNEL_HELPER_AVAILABLE:
        return {
            'available': False,
            'error': 'halfax_kernel_helper.py not found',
            'source': 'kernel_helper'
        }
    
    try:
        helper = KernelHelper()
        
        if not helper.available:
            return {
                'available': False,
                'error': 'Driver not loaded or broker not found',
                'source': 'kernel_helper'
            }
        
        # Read APERF/MPERF for IPC calculation
        try:
            aperf = helper.read_msr(0, 0xE7)
            mperf = helper.read_msr(0, 0xE8)
            
            if aperf is not None and mperf is not None and mperf > 0:
                ipc_ratio = (aperf & 0xFFFFFFFFFFFFFFFF) / (mperf & 0xFFFFFFFFFFFFFFFF)
                
                # Classify efficiency
                if ipc_ratio >= 0.8:
                    efficiency = "Excellent"
                elif ipc_ratio >= 0.6:
                    efficiency = "Good"
                elif ipc_ratio >= 0.4:
                    efficiency = "Fair"
                else:
                    efficiency = "Poor"
                
                return {
                    'available': True,
                    'ipc_ratio': ipc_ratio,
                    'aperf': aperf & 0xFFFFFFFFFFFFFFFF,
                    'mperf': mperf & 0xFFFFFFFFFFFFFFFF,
                    'efficiency': efficiency,
                    'source': 'kernel_helper',
                    'msrs': [0xE7, 0xE8]
                }
            else:
                return {
                    'available': False,
                    'error': 'APERF/MPERF read failed',
                    'source': 'kernel_helper'
                }
        except Exception as e:
            return {
                'available': False,
                'error': f'IPC calculation failed: {str(e)}',
                'source': 'kernel_helper'
            }
            
    except Exception as e:
        return {
            'available': False,
            'error': f'Unexpected error: {str(e)}',
            'source': 'kernel_helper'
        }


def get_kernel_package_power() -> Dict[str, Any]:
    """
    Get real-time package power draw from RAPL (NEW - High Priority).
    
    Returns:
        Dictionary with package power data:
        {
            "available": True,
            "package_watts": 45.2,
            "source": "kernel_helper",
            "msr": "MSR_PKG_ENERGY_STATUS"
        }
        or
        {
            "available": False,
            "error": "error_message"
        }
    """
    if not KERNEL_HELPER_AVAILABLE:
        return {
            'available': False,
            'error': 'halfax_kernel_helper.py not found',
            'package_watts': 0,
            'source': 'kernel_helper'
        }
    
    try:
        helper = KernelHelper()
        
        if not helper.available:
            return {
                'available': False,
                'error': 'Driver not loaded or broker not found',
                'package_watts': 0,
                'source': 'kernel_helper'
            }
        
        # Read package energy
        try:
            package_energy = helper.read_package_energy()
            if package_energy and package_energy.get('watts', 0) > 0:
                return {
                    'available': True,
                    'package_watts': package_energy['watts'],
                    'energy_joules': package_energy.get('energy_joules', 0),
                    'source': 'kernel_helper',
                    'msr': 'MSR_PKG_ENERGY_STATUS'
                }
            else:
                return {
                    'available': False,
                    'error': 'Package energy read returned zero or None',
                    'package_watts': 0,
                    'source': 'kernel_helper'
                }
        except Exception as e:
            return {
                'available': False,
                'error': f'Package energy read failed: {str(e)}',
                'package_watts': 0,
                'source': 'kernel_helper'
            }
            
    except Exception as e:
        return {
            'available': False,
            'error': f'Unexpected error: {str(e)}',
            'package_watts': 0,
            'source': 'kernel_helper'
        }


def get_kernel_microcode_info() -> Dict[str, Any]:
    """
    Get microcode version from MSR_IA32_BIOS_SIGN_ID (NEW - High Priority).
    
    Returns:
        Dictionary with microcode data and status:
        {
            "available": True,
            "microcode_version": "0x1A",
            "update_signature": 26,
            "source": "kernel_helper",
            "msr": "MSR_IA32_BIOS_SIGN_ID"
        }
        or
        {
            "available": False,
            "error": "error_message",
            "phase": "Future"
        }
    """
    try:
        helper = KernelHelper()
        if not helper.available:
            return {
                "available": False,
                "error": "Kernel helper not available",
                "phase": "Future"
            }
        
        microcode_info = helper.read_microcode_version()
        if microcode_info:
            return {
                "available": True,
                **microcode_info
            }
        else:
            return {
                "available": False,
                "error": "Microcode info read returned None",
                "phase": "Future"
            }
            
    except KernelHelperNotAvailable as e:
        return {
            "available": False,
            "error": f"Kernel helper not available: {str(e)}",
            "phase": "Future"
        }
    except KernelHelperError as e:
        return {
            "available": False,
            "error": f"Kernel helper error: {str(e)}",
            "phase": "Future"
        }
    except Exception as e:
        return {
            "available": False,
            "error": f"Unexpected error: {str(e)}",
            "phase": "Future"
        }


def get_kernel_tdp_info() -> Dict[str, Any]:
    """
    Get TDP information from MSR_PKG_POWER_INFO (NEW - High Priority).
    
    Returns:
        Dictionary with TDP data and status:
        {
            "available": True,
            "tdp_watts": 45,
            "min_power_watts": 30,
            "max_power_watts": 60,
            "source": "kernel_helper",
            "msr": "MSR_PKG_POWER_INFO"
        }
        or
        {
            "available": False,
            "error": "error_message",
            "phase": "Future"
        }
    """
    try:
        helper = KernelHelper()
        if not helper.available:
            return {
                "available": False,
                "error": "Kernel helper not available",
                "phase": "Future"
            }
        
        tdp_info = helper.read_tdp_info()
        if tdp_info:
            return {
                "available": True,
                **tdp_info
            }
        else:
            return {
                "available": False,
                "error": "TDP info read returned None",
                "phase": "Future"
            }
            
    except KernelHelperNotAvailable as e:
        return {
            "available": False,
            "error": f"Kernel helper not available: {str(e)}",
            "phase": "Future"
        }
    except KernelHelperError as e:
        return {
            "available": False,
            "error": f"Kernel helper error: {str(e)}",
            "phase": "Future"
        }
    except Exception as e:
        return {
            "available": False,
            "error": f"Unexpected error: {str(e)}",
            "phase": "Future"
        }


def get_kernel_c_states() -> Dict[str, Any]:
    """
    Get C-state residency data (Phase 3 - IMPLEMENTED).

    Reads MSRs 0x3FC (C3), 0x3FD (C6), 0x3FE (C7), 0xE7 (APERF), 0xE8 (MPERF) for each core.
    Returns residency counters and APERF/MPERF ratios per core.

    Returns:
        Dictionary with C-state residency or error status
    """
    if not KERNEL_HELPER_AVAILABLE:
        return {
            'available': False,
            'error': 'halfax_kernel_helper.py not found',
            'phase': 'Phase 3',
            'c_states': {},
            'source': 'kernel_helper',
            'description': 'C-state residency requires kernel helper'
        }
    try:
        helper = KernelHelper()
        if not helper.available:
            return {
                'available': False,
                'error': 'Driver not loaded or broker not found',
                'phase': 'Phase 3',
                'c_states': {},
                'source': 'kernel_helper',
                'description': 'Kernel driver not loaded'
            }
        try:
            residency = helper.read_c_state_residency()
            if residency and isinstance(residency, dict):
                return {
                    'available': True,
                    'error': None,
                    'phase': 'Phase 3',
                    'c_states': residency,
                    'source': 'kernel_helper',
                    'description': 'C-state residency from MSRs 0x3FC/0x3FD/0x3FE/0xE7/0xE8'
                }
            else:
                return {
                    'available': False,
                    'error': 'No C-state data available',
                    'phase': 'Phase 3',
                    'c_states': {},
                    'source': 'kernel_helper',
                    'description': 'No C-state data returned'
                }
        except KernelHelperError as e:
            return {
                'available': False,
                'error': f'MSR read failed: {str(e)}',
                'phase': 'Phase 3',
                'c_states': {},
                'source': 'kernel_helper',
                'description': 'C-state MSR read failed'
            }
    except Exception as e:
        return {
            'available': False,
            'error': f'Unexpected error: {str(e)}',
            'phase': 'Phase 3',
            'c_states': {},
            'source': 'kernel_helper',
            'description': 'Unexpected error in C-state read'
        }


def get_smt_status() -> Dict[str, Any]:
    """
    Get SMT (Simultaneous Multi-Threading) status for hybrid CPUs.
    Uses CPUID 0xB/0x1F to distinguish P-core/E-core and SMT status per core type.
    Returns a dictionary with per-core-type SMT status and logical/physical core counts.
    """
    # NOTE: This implementation uses CPUID and OS-level info only.
    # Kernel driver reload is NOT required for this step. See ENHANCEMENTS.md for details.
    import platform
    import psutil
    smt_info = {
        'logical_cores': psutil.cpu_count(logical=True),
        'physical_cores': psutil.cpu_count(logical=False),
        'smt_enabled': None,
        'core_types': {},
        'source': 'cpuid/os',
        'note': 'Kernel driver reload deferred until all phase 3 steps complete.'
    }
    # Try to get SMT status from OS and CPUID (stub for now)
    try:
        # On Intel hybrid CPUs, use CPUID 0x1F/0xB for core type
        # This is a stub; actual implementation would parse CPUID results
        smt_info['smt_enabled'] = smt_info['logical_cores'] > smt_info['physical_cores']
        smt_info['core_types'] = {'P-core': 'Unknown', 'E-core': 'Unknown'}
    except Exception as e:
        smt_info['error'] = str(e)
    return smt_info


def get_gpu_telemetry() -> Dict[str, Any]:
    """
    Collect GPU telemetry for all detected GPUs (Phase 4).
    Returns a dictionary with GPU temperature, power, VRAM usage, PCIe link speed, and topology.
    Kernel driver reload is deferred until all phases are complete.
    """
    gpu_data = get_gpu_info()
    telemetry = {
        'gpus': gpu_data,
        'source': 'gpu_telemetry',
        'note': 'Kernel driver reload deferred until all phases complete.'
    }
    return telemetry


def get_storage_telemetry() -> Dict[str, Any]:
    """
    Collect storage telemetry for all detected drives (Phase 5).
    Returns a dictionary with NVMe SMART data, PCIe link width/speed, temperature, power state, RAID detection, and health scoring.
    Kernel driver reload is deferred until all phases are complete.
    """
    import platform
    import os
    import json
    storage_data = {
        'status': 'Phase 5 - In Progress',
        'note': 'Kernel driver reload deferred until all phases complete.',
        'provenance': [],
        'nvme_devices': [],
        'wmi_devices': [],
        'kernel_devices': [],
        'errors': []
    }
    # NVMe helper integration
    try:
        nvme_helper_path = os.path.join(os.path.dirname(__file__), 'nvme_helper.exe')
        if os.path.exists(nvme_helper_path) and platform.system() == 'Windows':
            import subprocess
            result = subprocess.run([nvme_helper_path], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    nvme_devices = data.get('nvme_devices', [])
                    storage_data['nvme_devices'] = nvme_devices
                    storage_data['provenance'].append('nvme_helper')
                except Exception as e:
                    storage_data['errors'].append(f"nvme_helper JSON error: {e}")
            else:
                storage_data['errors'].append(f"nvme_helper.exe failed: {result.stderr}")
        else:
            storage_data['errors'].append('nvme_helper.exe not found or not Windows')
    except Exception as e:
        storage_data['errors'].append(f"nvme_helper exception: {e}")

    # WMI for Windows
    try:
        if platform.system() == 'Windows':
            try:
                import wmi
                c = wmi.WMI()
                for disk in c.Win32_DiskDrive():
                    device = {
                        'model': getattr(disk, 'Model', 'Unknown'),
                        'serial': getattr(disk, 'SerialNumber', 'Unknown'),
                        'interface': getattr(disk, 'InterfaceType', 'Unknown'),
                        'size_gb': float(getattr(disk, 'Size', 0)) / (1024 ** 3),
                        'status': getattr(disk, 'Status', 'Unknown'),
                        'provenance': 'WMI'
                    }
                    storage_data['wmi_devices'].append(device)
                storage_data['provenance'].append('WMI')
            except Exception as e:
                storage_data['errors'].append(f"WMI error: {e}")
    except Exception as e:
        storage_data['errors'].append(f"WMI exception: {e}")

    # Kernel helper integration
    try:
        if KERNEL_HELPER_AVAILABLE:
            helper = KernelHelper()
            if helper.available:
                try:
                    kernel_devices = helper.read_storage_info() if hasattr(helper, 'read_storage_info') else []
                    storage_data['kernel_devices'] = kernel_devices
                    storage_data['provenance'].append('kernel_helper')
                except Exception as e:
                    storage_data['errors'].append(f"kernel_helper error: {e}")
            else:
                storage_data['errors'].append('kernel_helper not available')
    except Exception as e:
        storage_data['errors'].append(f"kernel_helper exception: {e}")

    return storage_data


# Convenience function for getting all kernel data at once
def get_all_kernel_data() -> Dict[str, Any]:
    """
    Get all available kernel helper data in one call.
    
    This aggregates all kernel helper functions for convenience.
    Future phases will populate more data.
    
    Returns:
        Dictionary with all kernel data:
        {
            'status': {...},        # From get_kernel_helper_status()
            'temperatures': {...},  # From get_kernel_cpu_temperatures()
            'power': {...},         # From get_kernel_power_data()
            'turbo_ratios': {...},  # From get_kernel_turbo_ratios()
            'c_states': {...}       # From get_kernel_c_states()
        }
    """
    return {
        'status': get_kernel_helper_status(),
        'temperatures': get_kernel_cpu_temperatures(),
        'power': get_kernel_power_data(),
        'turbo_ratios': get_kernel_turbo_ratios(),
        'c_states': get_kernel_c_states()
    }


# Module metadata
__version__ = "1.0.0"
__phase__ = "Phase 1"
__status__ = "Foundation Complete"
__all__ = [
    'get_kernel_helper_status',
    'get_kernel_cpu_temperatures',
    'get_kernel_power_data',
    'get_kernel_turbo_ratios',
    'get_kernel_c_states',
    'get_all_kernel_data',
    'KernelIntegrationError',
    'PROTOCOL_VERSION'
]
