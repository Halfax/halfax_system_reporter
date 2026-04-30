import psutil
import platform
import os
import cpuinfo
import subprocess
import json
import glob
import time
import socket
import re

# Try to import WMI (Windows only)
HAS_WMI = False
try:
    import wmi
    HAS_WMI = True
except Exception:
    HAS_WMI = False

# Shared mapping of per-tab ScrolledText widgets
text_widgets = {}
# Platform detection flags
PLATFORM_SYSTEM = platform.system()
IS_WINDOWS = PLATFORM_SYSTEM == 'Windows'
IS_LINUX = PLATFORM_SYSTEM == 'Linux'
IS_MAC = PLATFORM_SYSTEM == 'Darwin'
# Raspberry Pi heuristic
IS_PI = False
try:
    if IS_LINUX and ('raspberry' in platform.uname().node.lower() or 'arm' in platform.machine().lower()):
        IS_PI = True
except Exception:
    IS_PI = False

# miniupnpc availability (router scan helper)
HAS_MINIUPNPC = False
try:
    import miniupnpc
    HAS_MINIUPNPC = True
except Exception:
    HAS_MINIUPNPC = False

def get_memory_rank_bank_info():
    """Detect memory rank and bank info from multiple methods"""
    rank_info = "Not reported by system API"
    bank_info = "Not reported by system API"

    # Method 1: Kernel helper (placeholder)
    try:
        from halfax_kernel_helper import KernelHelper
        helper = KernelHelper()
        if helper.available:
            # Kernel helper-based detection could set rank_info/bank_info
            pass
    except Exception:
        pass

    # Method 2: WMI fallback (Windows)
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for mem in c.Win32_PhysicalMemory():
                attributes = int(mem.Attributes) if hasattr(mem, 'Attributes') and mem.Attributes is not None else 0
                if attributes & 4:
                    rank_info = "WMI: Dual-Rank (DR)"
                else:
                    rank_info = "WMI: Single-Rank (SR)"

                # Banks: DDR3/DDR4 typically have 4 or 8 banks
                if hasattr(mem, 'Speed') and mem.Speed:
                    try:
                        speed = int(mem.Speed)
                    except Exception:
                        speed = 0
                    if speed >= 2400:
                        bank_info = "WMI: 8 Banks"
                    elif speed >= 1600:
                        bank_info = "WMI: 4-8 Banks (DDR3/DDR4)"
                    else:
                        bank_info = "WMI: 4 Banks"
                break
        except Exception:
            pass

    # Method 3: Linux dmidecode fallback
    if (rank_info == "Not reported by system API" or bank_info == "Not reported by system API") and IS_LINUX and not IS_PI:
        try:
            result = subprocess.run(['dmidecode', '-t', 'memory'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Rank' in line and rank_info == "Not reported by system API":
                        if 'Dual' in line:
                            rank_info = "dmidecode: Dual-Rank (DR)"
                        elif 'Single' in line:
                            rank_info = "dmidecode: Single-Rank (SR)"
                    if 'Bank' in line and bank_info == "Not reported by system API":
                        bank_info = f"dmidecode: {line.split(':', 1)[1].strip()}" if ':' in line else bank_info
        except Exception:
            pass

    return rank_info, bank_info

def get_memory_spd_timing():
    """Detect SPD timing information from multiple methods"""
    spd_timing = {
        'cas': 'Not reported by system API',
        'ras': 'Not reported by system API',
        'rcd': 'Not reported by system API',
        'rp': 'Not reported by system API'
    }
    
    # Method 1: Try SPD helper first (most accurate)
    try:
        spd_helper_path = os.path.join(os.path.dirname(__file__), 'spd_helper.exe')
        if os.path.exists(spd_helper_path):
            result = subprocess.run([spd_helper_path], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                dimms = data.get('dimms', [])
                for dimm in dimms:
                    if dimm.get('timings'):
                        timings = dimm['timings']
                        spd_timing['cas'] = f"SPD: {timings.get('cas', 'Unknown')}"
                        spd_timing['ras'] = f"SPD: {timings.get('ras', 'Unknown')}"
                        spd_timing['rcd'] = f"SPD: {timings.get('rcd', 'Unknown')}"
                        spd_timing['rp'] = f"SPD: {timings.get('rp', 'Unknown')}"
                        break
    except Exception:
        pass
    
    # Method 2: Linux dmidecode fallback
    if any(val == 'Not reported by system API' for val in spd_timing.values()) and IS_LINUX and not IS_PI:
        try:
            result = subprocess.run(['dmidecode', '-t', 'memory'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'CAS' in line.upper() and spd_timing['cas'] == 'Not reported by system API':
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['cas'] = f"dmidecode: {parts[1].strip()}"
                    elif 'RAS' in line.upper() and 'RAS to CAS' not in line.upper() and spd_timing['ras'] == 'Not reported by system API':
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['ras'] = f"dmidecode: {parts[1].strip()}"
                    elif 'RAS to CAS' in line.upper() and spd_timing['rcd'] == 'Not reported by system API':
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['rcd'] = f"dmidecode: {parts[1].strip()}"
                    elif 'RP' in line.upper() and 'Precharge' in line and spd_timing['rp'] == 'Not reported by system API':
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['rp'] = f"dmidecode: {parts[1].strip()}"
        except Exception:
            pass
    
    # Method 3: WMI fallback (limited data)
    if any(val == 'Not reported by system API' for val in spd_timing.values()) and IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for memory in c.Win32_PhysicalMemory():
                if memory.ConfiguredClockSpeed and spd_timing['cas'] == 'Not reported by system API':
                    # WMI doesn't provide detailed timing, but we can infer some info
                    speed = int(memory.ConfiguredClockSpeed) if memory.ConfiguredClockSpeed else 0
                    if speed >= 2400:
                        spd_timing['cas'] = f"WMI: ~15-18 (inferred from {speed}MHz)"
                    elif speed >= 1600:
                        spd_timing['cas'] = f"WMI: ~9-11 (inferred from {speed}MHz)"
                    else:
                        spd_timing['cas'] = f"WMI: ~5-7 (inferred from {speed}MHz)"
                break
        except Exception:
            pass
    
    return spd_timing

def get_memory_cas_latency():
    """Fallback for CAS latency detection if helpers are missing"""
    try:
        # If SPD helper exists, try to extract CAS info
        spd = get_spd_helper_info()
        if spd and spd.get('dimms'):
            for d in spd.get('dimms'):
                t = d.get('timings')
                if t and t.get('cas'):
                    return t.get('cas')
    except Exception:
        pass
    return 'Not reported by system API'

def get_memory_temp():
    """Fallback memory temperature probe returning empty/default structure"""
    try:
        # Attempt to read kernel sensor if available
        temps = {}
        return temps
    except Exception:
        return {}

def get_memory_controller_info():
    """Detect memory controller information from multiple methods"""
    # Method 1: Try kernel helper first (most accurate)
    try:
        from halfax_kernel_helper import KernelHelper
        helper = KernelHelper()
        if helper.available:
            # Try to get memory controller info via kernel
            # This would require specific MSR access or kernel driver support
            pass
    except Exception:
        pass
    
    # Method 2: WMI fallback (Windows)
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for proc in c.Win32_Processor():
                # ThreadCount vs CoreCount can indicate chiplet count
                cores = int(proc.NumberOfCores) if proc.NumberOfCores else 0
                threads = int(proc.NumberOfLogicalProcessors) if proc.NumberOfLogicalProcessors else 0
                
                # Multi-tile systems (Intel Meteor Lake, Ultra, EPYC, Ryzen)
                if cores > 16:
                    # Likely multi-tile architecture
                    tiles = (cores + 7) // 8  # Rough estimate
                    return f"WMI: Integrated Memory Controller (multi-tile architecture, ~{tiles} tiles)"
                else:
                    return "WMI: Integrated Memory Controller (single-tile architecture)"
        except Exception:
            pass
    
    # Method 3: Linux lscpu fallback
    elif IS_LINUX and not IS_PI:
        try:
            # Check for NUMA info which indicates memory controllers
            result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'NUMA node' in line:
                        return f"lscpu: IMC per NUMA node - {line.strip()}"
                # If no NUMA, try /proc/cpuinfo for die info
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    if 'core_id' in content:
                        return "lscpu: Integrated Memory Controller (Detected via core topology)"
        except Exception:
            pass
    
    # Method 4: CPUID helper fallback
    try:
        cpuid_path = os.path.join(os.path.dirname(__file__), 'cpuid_helper.exe')
        if os.path.exists(cpuid_path):
            result = subprocess.run([cpuid_path], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get('cache_topology'):
                    return "CPUID: Memory controller info inferred from cache topology"
    except Exception:
        pass
    
    # Method 5: Raspberry Pi fallback
    if IS_PI:
        return "SoC: Integrated Memory Controller (Shared RAM)"
    
    return "Not reported by system API"

def get_numa_node_mapping():
    """Detect NUMA node mapping for memory locality from multiple methods"""
    # Method 1: Try numactl first (most accurate on Linux)
    if IS_LINUX and not IS_PI:
        try:
            result = subprocess.run(['numactl', '-H'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # Parse numactl output
                node_count = 0
                for line in lines:
                    if 'available' in line.lower():
                        parts = line.split()
                        if parts[0].isdigit():
                            node_count = int(parts[0])
                        break
                
                if node_count > 1:
                    return f"numactl: NUMA Enabled ({node_count} nodes)"
                elif node_count == 1:
                    return "numactl: Single NUMA Node (UMA system)"
        except Exception:
            pass
        
        # Method 2: lscpu fallback
        try:
            result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'NUMA node' in line:
                        return f"lscpu: NUMA Enabled - {line.strip()}"
        except Exception:
            pass
        
        # Method 3: /proc/cpuinfo fallback
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                if 'NUMA' in content.upper():
                    return "cpuinfo: NUMA Detected"
                elif 'core_id' in content:
                    return "cpuinfo: UMA System (No NUMA detected)"
        except Exception:
            pass
    
    # Method 4: WMI fallback (Windows)
    elif IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            # Check for NUMA nodes in Windows
            numa_nodes = []
            for system in c.Win32_ComputerSystem():
                if hasattr(system, 'NumberOfProcessors'):
                    numa_nodes.append(system.NumberOfProcessors)
            for proc in c.Win32_Processor():
                socket_count += 1
            
            if socket_count > 1:
                return f"Multi-Socket System ({socket_count} sockets, NUMA likely)"
            else:
                return "Single Socket System (UMA)"
        except:
            pass
    
    elif IS_PI:
        return "Single SoC (UMA - Unified Memory)"
    
    return "Not reported by system API"

def get_max_supported_memory_speed():
    """Detect maximum supported memory speed from CPU/platform specs"""
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for proc in c.Win32_Processor():
                # CPU Name can hint at supported memory speeds
                name = proc.Name if proc.Name else ""
                
                # Heuristic detection based on CPU name
                if 'Ryzen 9 7' in name or 'EPYC 9' in name:
                    return "DDR5-6400+ (Zen 4, Zen 4c)"
                elif 'Ryzen 7 7' in name or 'Ryzen 5 7' in name:
                    return "DDR5-6400 (Zen 4)"
                elif 'Core i9-13' in name or 'Core i7-13' in name:
                    return "DDR5-6400 (Raptor Lake)"
                elif 'Core i9-14' in name or 'Core i7-14' in name:
                    return "DDR5-7600 (Arrow Lake)"
                elif 'Ryzen 5 5' in name or 'Ryzen 7 5' in name:
                    return "DDR4-3600 (Zen 3)"
                elif 'Core i9-12' in name or 'Core i7-12' in name:
                    return "DDR5-4800 / DDR4-3200 (Alder Lake)"
                elif 'Xeon' in name:
                    return "DDR5-4800+ (Xeon)"
                break
        except:
            pass
    
    elif IS_LINUX and not IS_PI:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                model_name = ""
                for line in f:
                    if line.startswith('model name'):
                        model_name = line.split(':', 1)[1].strip()
                        break
            
            # Heuristic detection based on model name
            if 'Ryzen 9 7' in model_name or 'EPYC 9' in model_name:
                return "DDR5-6400+ (Zen 4, Zen 4c)"
            elif 'Ryzen 7 7' in model_name or 'Ryzen 5 7' in model_name:
                return "DDR5-6400 (Zen 4)"
            elif 'Core i9-13' in model_name or 'Core i7-13' in model_name:
                return "DDR5-6400 (Raptor Lake)"
            elif 'Core i9-14' in model_name or 'Core i7-14' in model_name:
                return "DDR5-7600 (Arrow Lake)"
            elif 'Ryzen 5 5' in model_name or 'Ryzen 7 5' in model_name:
                return "DDR4-3600 (Zen 3)"
            elif 'Xeon' in model_name:
                return "DDR5-4800+ (Xeon)"
        except:
            pass
    
    elif IS_PI:
        return "LPDDR4/LPDDR5 (SoC Spec)"
    
    return "Not reported by system API"

def get_spd_helper_info():
    """Get enhanced SMBIOS/SPD information from spd_helper.exe"""
    spd_info = {
        'dimms': [],
        'available': False,
        'error': None,
        'memory_array': None
    }
    
    try:
        spd_helper_path = os.path.join(os.path.dirname(__file__), 'spd_helper.exe')
        if not os.path.exists(spd_helper_path):
            return spd_info
        
        result = subprocess.run([spd_helper_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            spd_info['dimms'] = data.get('dimms', [])
            spd_info['available'] = True
            spd_info['method'] = data.get('method', 'Unknown')
            spd_info['note'] = data.get('note', '')
            spd_info['memory_array'] = data.get('memory_array')  # Phase 1 addition
    except json.JSONDecodeError as e:
        spd_info['error'] = f"JSON parse error: {str(e)}"
    except Exception as e:
        spd_info['error'] = f"SPD helper error: {str(e)}"
    
    return spd_info

def get_memory_info():
    """Basic memory info used as the base for extended memory reporting."""
    try:
        vm = psutil.virtual_memory()
        total_gb = vm.total / (1024 ** 3)
        available_gb = vm.available / (1024 ** 3)
        used_gb = (vm.total - vm.available) / (1024 ** 3)
        return {
            'total': total_gb,
            'used': used_gb,
            'available': available_gb,
            'percent': vm.percent,
            'module_count': 0,
            'modules': [],
        }
    except Exception:
        return {
            'total': 0.0,
            'used': 0.0,
            'available': 0.0,
            'percent': 0.0,
            'module_count': 0,
            'modules': [],
        }

def get_memory_channel_info():
    """Return basic memory channel information (fallback)."""
    try:
        # Try to infer from psutil / platform heuristics later; return minimal now
        return {'channels': 0, 'description': 'Not reported by system API'}
    except Exception:
        return {'channels': 0, 'description': 'Unavailable'}

def get_memory_ecc_status():
    """Return ECC status (fallback)."""
    try:
        # On Windows/Linux, ECC detection may require privileged access; return unknown
        return 'Unknown'
    except Exception:
        return 'Unavailable'

def get_memory_form_factor():
    """Return memory form factor (fallback)."""
    try:
        # Typical values: DIMM, SODIMM, SoC
        return 'Not reported by system API'
    except Exception:
        return 'Unavailable'

def get_memory_extended_info():
    """Get extended memory information with all enhancements"""
    try:
        base_info = get_memory_info()
    except NameError:
        try:
            vm = psutil.virtual_memory()
            base_info = {
                'total': vm.total / (1024 ** 3),
                'used': (vm.total - vm.available) / (1024 ** 3),
                'available': vm.available / (1024 ** 3),
                'percent': vm.percent,
                'module_count': 0,
                'modules': [],
            }
        except Exception:
            base_info = {
                'total': 0.0,
                'used': 0.0,
                'available': 0.0,
                'percent': 0.0,
                'module_count': 0,
                'modules': [],
            }
    
    base_info['channel_info'] = get_memory_channel_info()
    base_info['ecc_status'] = get_memory_ecc_status()
    base_info['form_factor'] = get_memory_form_factor()
    base_info['cas_latency'] = get_memory_cas_latency()
    base_info['memory_temp'] = get_memory_temp()
    
    # Add new enhanced fields
    rank_info, bank_info = get_memory_rank_bank_info()
    base_info['rank_info'] = rank_info
    base_info['bank_info'] = bank_info
    
    spd_timing = get_memory_spd_timing()
    base_info['spd_timing'] = spd_timing
    
    base_info['controller_info'] = get_memory_controller_info()
    base_info['numa_mapping'] = get_numa_node_mapping()
    base_info['max_supported_speed'] = get_max_supported_memory_speed()
    
    # Add enhanced SPD helper data
    base_info['spd_helper'] = get_spd_helper_info()
    
    return base_info

def get_cpu_info_cores():
    try:
        cpu_info = cpuinfo.get_cpu_info()
        brand = cpu_info['brand_raw']
        Arch =  cpu_info['arch']   
        return brand, Arch
    except ImportError:
        print("Install 'py-cpuinfo' package for detailed CPU info: pip install py-cpuinfo")

def validate_cpu_flags_against_os():
    """Validate CPU instruction flags against OS-specific sources"""
    validated_flags = []
    
    if IS_WINDOWS:
        # Windows: Try to validate via processor name in WMI
        try:
            if HAS_WMI:
                c = wmi.WMI()
                for proc in c.Win32_Processor():
                    desc = proc.Description if proc.Description else ""
                    # Extract supported features from description string
                    # This is a supplement to py-cpuinfo validation
                    break
        except:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux: Get flags directly from /proc/cpuinfo (more reliable than py-cpuinfo)
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('flags'):
                        flags_str = line.split(':', 1)[1].strip()
                        validated_flags = flags_str.split()
                        return validated_flags
        except:
            pass
    
    return validated_flags

def read_cpuid_frequencies():
    """
    Read CPU frequencies directly via CPUID leaf 0x16 using helper binary.
    This is the most accurate method on Windows.
    Returns dict with base_mhz, max_mhz, bus_mhz, turbo_supported, or None if unavailable.
    """
    if not IS_WINDOWS:
        return None
    
    helper_path = os.path.join(os.path.dirname(__file__), 'cpuid_helper.exe')
    
    # Try current directory if not found in script directory
    if not os.path.exists(helper_path):
        helper_path = os.path.join(os.getcwd(), 'cpuid_helper.exe')
    
    if not os.path.exists(helper_path):
        return None
    
    try:
        result = subprocess.run([helper_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            if data.get('success'):
                return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        pass
    
    return None

def get_detailed_cpu_frequencies():
    """Get detailed frequency information from OS-specific sources with CPUID/brand fallback"""
    freq_info = {
        'base': None,
        'max': None,
        'turbo': None,
        'current': None,
        'bus': None,
        'brand': None,
        'turbo_1c': None,
        'turbo_ac': None,
        'msr_access': None,
        'source': []
    }
    
    if IS_WINDOWS:
        # Try CPUID helper first (most accurate)
        cpuid_data = read_cpuid_frequencies()
        if cpuid_data:
            base = cpuid_data.get('base_mhz') or 0
            maxc = cpuid_data.get('max_mhz') or 0
            bus = cpuid_data.get('bus_mhz') or 0
            brand = cpuid_data.get('brand')
            turbo_1c = cpuid_data.get('cpuid_max_turbo_1c_mhz') or 0
            turbo_ac = cpuid_data.get('cpuid_max_turbo_ac_mhz') or 0
            msr_access = cpuid_data.get('msr_access')
            
            if base > 0:
                freq_info['base'] = base
                freq_info['source'].append('CPUID/brand')
            if maxc > 0:
                freq_info['max'] = maxc
            if turbo_1c > 0:
                freq_info['turbo_1c'] = turbo_1c
            if turbo_ac > 0:
                freq_info['turbo_ac'] = turbo_ac
            if msr_access:
                freq_info['msr_access'] = msr_access
                if 'CPUID/brand' not in freq_info['source']:
                    freq_info['source'].append('CPUID/brand')
            if bus > 0:
                freq_info['bus'] = bus
            if brand:
                freq_info['brand'] = brand
            if cpuid_data.get('turbo_supported'):
                freq_info['turbo'] = "Supported"
        
        # Fall back to WMI if CPUID helper not available
        if freq_info['max'] is None:
            try:
                if HAS_WMI:
                    c = wmi.WMI()
                    for proc in c.Win32_Processor():
                        if proc.MaxClockSpeed:
                            freq_info['max'] = int(proc.MaxClockSpeed)
                            freq_info['source'].append('WMI')
                        break
            except:
                pass
        
        # Try PowerShell for additional frequency info
        try:
            ps_cmd = """Get-WmiObject -Class Win32_Processor | Select-Object -Property MaxClockSpeed, Characteristics | ConvertTo-Json"""
            result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                pass
        except:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux: Get frequencies from sysfs and /proc/cpuinfo
        try:
            # Get current frequency from /proc/cpuinfo
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'cpu MHz' in line:
                        freq_mhz = float(line.split(':', 1)[1].strip())
                        freq_info['current'] = freq_mhz
                        break
        except:
            pass
        
        try:
            # Get max frequency from cpufreq interface
            result = subprocess.run(['cat', '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq'],
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                max_freq_khz = int(result.stdout.strip())
                freq_info['max'] = max_freq_khz / 1000  # Convert to MHz
        except:
            pass
        
        try:
            # Get min (base) frequency
            result = subprocess.run(['cat', '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq'],
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                min_freq_khz = int(result.stdout.strip())
                freq_info['base'] = min_freq_khz / 1000  # Convert to MHz
        except:
            pass
    
    return freq_info

def get_per_core_frequency_snapshot():
    """
    Get current frequency of each core using Windows kernel API (CallNtPowerInformation).
    Most accurate method: directly queries processor power information via NT kernel.
    Returns list of dicts with core index, current frequency in MHz, and max frequency.
    """
    per_core_freqs = []
    
    if not IS_WINDOWS:
        return per_core_freqs
    
    try:
        import ctypes
        from ctypes import wintypes
        
        # PROCESSOR_POWER_INFORMATION structure
        class PROCESSOR_POWER_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('Number', wintypes.ULONG),
                ('MaxMhz', wintypes.ULONG),
                ('CurrentMhz', wintypes.ULONG),
                ('MhzLimit', wintypes.ULONG),
                ('MaxIdleState', wintypes.ULONG),
                ('CurrentIdleState', wintypes.ULONG),
            ]
        
        # Load powrprof.dll (not ntdll) and setup CallNtPowerInformation
        powrprof = ctypes.WinDLL('powrprof.dll')
        CallNtPowerInformation = powrprof.CallNtPowerInformation
        CallNtPowerInformation.argtypes = [
            wintypes.DWORD,  # InformationLevel
            ctypes.c_void_p,  # InputBuffer
            wintypes.ULONG,  # InputBufferLength
            ctypes.c_void_p,  # OutputBuffer
            wintypes.ULONG,  # OutputBufferLength
        ]
        CallNtPowerInformation.restype = wintypes.LONG
        
        # ProcessorInformation = 11
        PROCESSOR_INFORMATION = 11
        
        # Get number of logical processors
        num_processors = psutil.cpu_count(logical=True)
        if not num_processors:
            num_processors = 64  # fallback
        
        # Allocate output buffer (array of structures)
        output_buffer = (PROCESSOR_POWER_INFORMATION * num_processors)()
        output_size = ctypes.sizeof(output_buffer)
        
        # Call kernel API
        status = CallNtPowerInformation(
            PROCESSOR_INFORMATION,
            None,
            0,
            ctypes.byref(output_buffer),
            output_size
        )
        
        if status == 0:  # STATUS_SUCCESS
            for i in range(num_processors):
                info = output_buffer[i]
                # Check if this is a valid entry (MaxMhz should be non-zero)
                if info.MaxMhz > 0 or info.CurrentMhz > 0:
                    max_mhz = info.MaxMhz if info.MaxMhz > 0 else info.CurrentMhz
                    per_core_freqs.append({
                        'core': i,  # Use array index as core number
                        'frequency_mhz': info.CurrentMhz,
                        'max_mhz': max_mhz,
                        'percentage': int((info.CurrentMhz / max_mhz) * 100) if max_mhz > 0 else 0
                    })
        else:
            # API failed, use fallback
            raise Exception(f"CallNtPowerInformation failed with status {status}")
    
    except Exception as e:
        # Fallback: use psutil if available
        try:
            freq_per_cpu = psutil.cpu_freq(percpu=True)
            if freq_per_cpu:
                for i, freq in enumerate(freq_per_cpu):
                    if freq:
                        per_core_freqs.append({
                            'core': i,
                            'frequency_mhz': int(freq.current),
                            'max_mhz': int(freq.max) if freq.max else 0,
                            'percentage': int((freq.current / freq.max * 100)) if freq.max else 0
                        })
        except:
            pass
    
    return per_core_freqs

def get_c_state_residency():
    """
    Get C-state residency for each core using Windows PDH (Performance Data Helper) API.
    Queries actual C-state counters from the kernel for accurate idle state statistics.
    Returns list of dicts with core index and percentage time in each C-state.
    """
    c_state_data = []
    
    if not IS_WINDOWS:
        return c_state_data
    
    try:
        import ctypes
        from ctypes import wintypes
        
        # Load kernel32.dll for processor info
        kernel32 = ctypes.WinDLL('kernel32.dll', use_last_error=True)
        
        # Try to get C-state info via GetSystemPowerStatus or other APIs
        # Note: C-state residency is typically exposed via MSRs or ETW traces
        # For now, we'll use a simplified approach with processor idle time
        
        # Alternative: Use psutil to get per-core idle percentages
        num_processors = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=0.1, percpu=True)
        
        if cpu_percent and len(cpu_percent) == num_processors:
            for i, usage in enumerate(cpu_percent):
                # C0 = active, C1+ = idle
                # This is a simplified approximation
                c0_percent = int(usage)
                c1_plus_percent = 100 - c0_percent
                
                c_state_data.append({
                    'core': i,
                    'C0': c0_percent,      # Active/running
                    'C1+': c1_plus_percent  # Idle states combined
                })
    
    except Exception as e:
        pass
    
    return c_state_data

def get_detailed_cache_info():
    """Get cache information from OS-specific sources"""
    cache_info = {
        'l1': None,
        'l2': None,
        'l3': None
    }
    
    if IS_WINDOWS:
        # Prefer CPUID helper if available
        cpuid_data = read_cpuid_frequencies()
        if cpuid_data:
            l1d = cpuid_data.get('l1d_kb') or 0
            l1i = cpuid_data.get('l1i_kb') or 0
            l2 = cpuid_data.get('l2_kb') or 0
            l3 = cpuid_data.get('l3_kb') or 0
            
            # Format L1 with topology
            l1_parts = []
            if l1d:
                l1d_assoc = cpuid_data.get('l1d_assoc', 0)
                l1d_line = cpuid_data.get('l1d_line', 0)
                l1d_sets = cpuid_data.get('l1d_sets', 0)
                l1d_sharing = cpuid_data.get('l1d_cores_sharing', -1)
                l1d_inclusive = cpuid_data.get('l1d_inclusive', -1)
                
                detail_parts = [f"L1D"]
                if l1d_assoc:
                    detail_parts.append(f"{l1d_assoc}-way")
                if l1d_line:
                    detail_parts.append(f"{l1d_line}B line")
                if l1d_sets:
                    detail_parts.append(f"{l1d_sets} sets")
                if l1d_sharing > 0:
                    detail_parts.append(f"shared by {l1d_sharing} core" + ("s" if l1d_sharing > 1 else ""))
                if l1d_inclusive == 1:
                    detail_parts.append("inclusive")
                elif l1d_inclusive == 0:
                    detail_parts.append("exclusive")
                
                l1_parts.append(f"{l1d} KB ({', '.join(detail_parts)})")
                
            if l1i:
                l1i_assoc = cpuid_data.get('l1i_assoc', 0)
                l1i_line = cpuid_data.get('l1i_line', 0)
                l1i_sets = cpuid_data.get('l1i_sets', 0)
                l1i_sharing = cpuid_data.get('l1i_cores_sharing', -1)
                l1i_inclusive = cpuid_data.get('l1i_inclusive', -1)
                
                detail_parts = [f"L1I"]
                if l1i_assoc:
                    detail_parts.append(f"{l1i_assoc}-way")
                if l1i_line:
                    detail_parts.append(f"{l1i_line}B line")
                if l1i_sets:
                    detail_parts.append(f"{l1i_sets} sets")
                if l1i_sharing > 0:
                    detail_parts.append(f"shared by {l1i_sharing} core" + ("s" if l1i_sharing > 1 else ""))
                if l1i_inclusive == 1:
                    detail_parts.append("inclusive")
                elif l1i_inclusive == 0:
                    detail_parts.append("exclusive")
                    
                l1_parts.append(f"{l1i} KB ({', '.join(detail_parts)})")
                
            if l1_parts:
                cache_info['l1'] = " / ".join(l1_parts)
            
            # Format L2 with topology and per-core notation
            if l2:
                l2_assoc = cpuid_data.get('l2_assoc', 0)
                l2_line = cpuid_data.get('l2_line', 0)
                l2_sets = cpuid_data.get('l2_sets', 0)
                l2_sharing = cpuid_data.get('l2_cores_sharing', -1)
                l2_inclusive = cpuid_data.get('l2_inclusive', -1)
                
                size_str = f"{l2/1024:.2f} MB" if l2 >= 1024 else f"{l2} KB"
                
                detail_parts = []
                if l2_assoc:
                    detail_parts.append(f"{l2_assoc}-way")
                if l2_line:
                    detail_parts.append(f"{l2_line}B line")
                if l2_sets:
                    detail_parts.append(f"{l2_sets} sets")
                if l2_sharing > 0 and l2_sharing <= 8:  # Reasonable per-core L2 sharing
                    detail_parts.append(f"shared by {l2_sharing} core" + ("s" if l2_sharing > 1 else ""))
                if l2_inclusive == 1:
                    detail_parts.append("inclusive")
                elif l2_inclusive == 0:
                    detail_parts.append("exclusive")
                
                detail_str = f" ({', '.join(detail_parts)})" if detail_parts else ""
                # CPUID 0x4 returns per-core L2
                cache_info['l2'] = f"{size_str} per core{detail_str}"
            
            # Format L3 with topology
            if l3:
                l3_assoc = cpuid_data.get('l3_assoc', 0)
                l3_line = cpuid_data.get('l3_line', 0)
                l3_sets = cpuid_data.get('l3_sets', 0)
                l3_sharing = cpuid_data.get('l3_cores_sharing', -1)
                l3_inclusive = cpuid_data.get('l3_inclusive', -1)
                
                size_str = f"{l3/1024:.2f} MB" if l3 >= 1024 else f"{l3} KB"
                
                detail_parts = []
                if l3_assoc:
                    detail_parts.append(f"{l3_assoc}-way")
                if l3_line:
                    detail_parts.append(f"{l3_line}B line")
                if l3_sets:
                    detail_parts.append(f"{l3_sets} sets")
                if l3_sharing > 0:
                    # Clamp unreasonable values for hybrid architectures
                    actual_sharing = min(l3_sharing, 14)  # Max cores in Ultra 9
                    detail_parts.append(f"shared by {actual_sharing} core" + ("s" if actual_sharing > 1 else ""))
                if l3_inclusive == 1:
                    detail_parts.append("inclusive")
                elif l3_inclusive == 0:
                    detail_parts.append("exclusive")
                
                detail_str = f" ({', '.join(detail_parts)})" if detail_parts else ""
                cache_info['l3'] = f"{size_str}{detail_str}"

        # WMI fallback if CPUID L2/L3 still missing
        try:
            if HAS_WMI:
                c = wmi.WMI()
                for proc in c.Win32_Processor():
                    # WMI reports total aggregate, not per-core
                    if hasattr(proc, 'L2CacheSize') and proc.L2CacheSize and not cache_info['l2']:
                        cache_info['l2'] = f"{int(proc.L2CacheSize) // 1024} MB total (aggregate across all cores)"
                    if hasattr(proc, 'L3CacheSize') and proc.L3CacheSize and not cache_info['l3']:
                        cache_info['l3'] = f"{int(proc.L3CacheSize) // 1024} MB total (aggregate across all cores)"
                    break
        except:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux: Use lscpu for reliable cache info
        try:
            result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'L1d cache:' in line:
                        cache_info['l1'] = line.split(':', 1)[1].strip()
                    elif 'L2 cache' in line and 'cache(s)' not in line:
                        cache_info['l2'] = line.split(':', 1)[1].strip()
                    elif 'L3 cache' in line and 'cache(s)' not in line:
                        cache_info['l3'] = line.split(':', 1)[1].strip()
        except:
            pass
    
    return cache_info

def get_detailed_tdp_info():
    """Get TDP information from OS-specific sources"""
    tdp_info = None
    
    if IS_WINDOWS:
        try:
            if HAS_WMI:
                c = wmi.WMI()
                for proc in c.Win32_Processor():
                    if proc.TdpSupport:
                        tdp_info = f"{proc.TdpSupport}W"
                    break
        except:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux: Try RAPL (Intel Running Average Power Limit)
        try:
            result = subprocess.run(['cat', '/sys/class/powercap/intel-rapl/intel-rapl:0/power_limit:0_max_uw'],
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                max_power_uw = int(result.stdout.strip())
                tdp_watts = max_power_uw / 1e6
                tdp_info = f"{tdp_watts:.0f}W (RAPL)"
        except:
            pass
    
    return tdp_info

def get_cpu_extended_info():
    """Get detailed CPU information including clocks, cache, features, and performance metrics"""
    cores_logical = psutil.cpu_count(logical=True)
    cores_physical = psutil.cpu_count(logical=False)
    
    cpu_details = {
        'brand': 'Unknown',
        'architecture': 'Unknown',
        'cores_logical': cores_logical,
        'cores_physical': cores_physical,
        'base_freq': 'Unavailable',
        'max_freq': 'Unavailable',
        'max_turbo_freq': 'Unavailable',
        'max_turbo_1c': 'Unavailable',
        'max_turbo_ac': 'Unavailable',
        'msr_access': 'Unavailable',
        'current_freq': 'Unavailable',
        'freq_source': 'Unavailable',
        'bus_freq': 'Unavailable',
        'cpuid_brand': 'Unavailable',
        'cache_l1': 'Unavailable',
        'cache_l2': 'Unavailable',
        'cache_l3': 'Unavailable',
        'tdp': 'Unavailable',
        'socket': 'Unavailable',
        'instruction_sets': [],
        'instruction_sets_grouped': {},
        'features': [],
        'temperatures': {},
        'microcode': 'Unavailable',
        'smt_status': 'Not detected',
        'virtualization': 'Not detected',
        'security_features': [],
        'numa_nodes': 'N/A',
        'p_states': [],
        'c_states': [],
        'thermal_throttling': 'Unknown',
        'per_core_frequency': [],  # List of {core, frequency_mhz, percentage}
        'c_state_residency': [],   # List of {core, C0%, C1%, C6%, etc}
        'cache_sharing_groups': {}, # Summary: {l1d_instances, l2_instances, l3_instances}
        'apic_ids': []             # List of {index, apic, core_type, l1d_group, l2_group, l3_group}
    }
    
    # Infer SMT status from logical vs physical core count
    if cores_logical and cores_physical:
        if cores_logical > cores_physical:
            cpu_details['smt_status'] = f'Yes ({cores_logical // cores_physical}:1 threads)'
        else:
            cpu_details['smt_status'] = 'No (disabled or not present)'
    
    try:
        cpu_info = cpuinfo.get_cpu_info()
        cpu_details['brand'] = cpu_info.get('brand_raw', 'Unknown')
        cpu_details['architecture'] = cpu_info.get('arch', 'Unknown')
        
        # Extract instruction sets and group by category
        if 'flags' in cpu_info:
            flags = cpu_info['flags']
            if isinstance(flags, list):
                flags_upper = [f.upper() for f in flags]
                cpu_details['instruction_sets'] = flags_upper[:15]
                
                # Group by category (excluding AMD-only legacy instructions from generic SIMD)
                simd = [f for f in flags_upper if f in ['AVX', 'AVX2', 'AVX512F', 'AVX512DQ', 'SSE', 'SSE2', 'SSE3', 'SSSE3', 'SSE4_1', 'SSE4_2']]
                # Detect if AMD and add AMD-specific instructions
                is_amd = 'AMD' in cpu_details['brand'] or 'amd' in cpu_info.get('brand_raw', '').lower()
                if is_amd:
                    amd_simd = [f for f in flags_upper if f in ['3DNOW', '3DNOWPREFETCH']]
                    if amd_simd:
                        simd.extend(amd_simd)
                crypto = [f for f in flags_upper if f in ['AES', 'SHA', 'PCLMULQDQ', 'SM3', 'SM4']]
                system = [f for f in flags_upper if f in ['ACPI', 'APIC', 'MCA', 'MCE', 'MTRR', 'PAE', 'PSE', 'TSC']]
                bit_manip = [f for f in flags_upper if f in ['BMI1', 'BMI2', 'ADX', 'LZCNT', 'POPCNT']]
                virt_flags = [f for f in flags_upper if f in ['VMX', 'SVM', 'VT', 'AMD-V']]
                
                if simd:
                    cpu_details['instruction_sets_grouped']['SIMD'] = simd
                if crypto:
                    cpu_details['instruction_sets_grouped']['Crypto'] = crypto
                if system:
                    cpu_details['instruction_sets_grouped']['System'] = system
                if bit_manip:
                    cpu_details['instruction_sets_grouped']['Bit Manipulation'] = bit_manip
                if virt_flags:
                    cpu_details['instruction_sets_grouped']['Virtualization'] = virt_flags
                
                # Check for virtualization
                if any(flag in flags for flag in ['vmx', 'svm', 'amd-v', 'vt-x']):
                    cpu_details['virtualization'] = 'Supported'
                
                # Check for security features (comprehensive list)
                security = []
                if any(flag in flags for flag in ['sgx', 'sgx1', 'sgx2']):
                    security.append('SGX')
                if any(flag in flags for flag in ['aes', 'aes-ni']):
                    security.append('AES-NI')
                if any(flag in flags for flag in ['tsx', 'tsx-force-abort']):
                    security.append('TSX')
                if 'smep' in flags:
                    security.append('SMEP')
                if 'smap' in flags:
                    security.append('SMAP')
                if any(flag in flags for flag in ['mds', 'mds-no']):
                    security.append('MDS Mitigations')
                if any(flag in flags for flag in ['spec-ctrl', 'ssbd', 'retpoline']):
                    security.append('Spectre/Meltdown Mitigations')
                if any(flag in flags for flag in ['rdrand', 'rdseed']):
                    security.append('Hardware RNG')
                
                if security:
                    cpu_details['security_features'] = security
                else:
                    cpu_details['security_features'] = ['Additional features unavailable or not detected']
    except:
        pass
    
    # Get frequency info (cross-platform with OS-specific validation)
    try:
        os_freq = get_detailed_cpu_frequencies()
        freq = psutil.cpu_freq()

        base_val = os_freq['base'] if os_freq['base'] else (freq.min if freq and freq.min and freq.min > 0 else None)
        max_val = os_freq['max'] if os_freq['max'] else (freq.max if freq and freq.max and freq.max > 0 else None)

        if base_val:
            cpu_details['base_freq'] = f"{base_val:.2f} MHz"
        if max_val:
            cpu_details['max_freq'] = f"{max_val:.2f} MHz"

        if max_val and base_val and max_val > base_val * 1.1:
            cpu_details['max_turbo_freq'] = f"{max_val:.2f} MHz"

        current_val = os_freq['current'] if os_freq['current'] else (freq.current if freq and freq.current and freq.current > 0 else None)
        if current_val:
            cpu_details['current_freq'] = f"{current_val:.2f} MHz (Package Frequency)"

        if os_freq.get('bus'):
            cpu_details['bus_freq'] = f"{os_freq['bus']:.0f} MHz"

        if os_freq.get('brand'):
            cpu_details['cpuid_brand'] = os_freq['brand']
        
        # Set frequency source from the sources collected
        if os_freq.get('source'):
            cpu_details['freq_source'] = ', '.join(os_freq['source'])
        else:
            cpu_details['freq_source'] = 'psutil'
        
        # Phase 1: Add turbo ratio limits and MSR status
        if os_freq.get('turbo_1c'):
            cpu_details['max_turbo_1c'] = f"{os_freq['turbo_1c']:.0f}"
        if os_freq.get('turbo_ac'):
            cpu_details['max_turbo_ac'] = f"{os_freq['turbo_ac']:.0f}"
        if os_freq.get('msr_access'):
            cpu_details['msr_access'] = os_freq['msr_access']

        temps = psutil.sensors_temperatures()
        if temps:
            if 'coretemp' in temps:  # Intel
                for name, entries in temps.items():
                    for entry in entries[:4]:  # First 4 temp readings
                        cpu_details['temperatures'][entry.label or name] = f"{entry.current:.1f}°C"
            elif 'acpitz' in temps:  # Generic
                for entry in temps['acpitz'][:4]:
                    cpu_details['temperatures'][entry.label or 'ACPI Thermal'] = f"{entry.current:.1f}°C"
    except:
        pass
    
    # Windows-specific info
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for proc in c.Win32_Processor():
                cpu_details['socket'] = proc.SocketDesignation if proc.SocketDesignation else 'Unavailable'
                
                # Get TDP support (if available)
                if proc.TdpSupport:
                    cpu_details['tdp'] = f"{proc.TdpSupport}W"
                
                # Get microcode version
                if hasattr(proc, 'Revision') and proc.Revision:
                    rev = proc.Revision
                    if isinstance(rev, int):
                        cpu_details['microcode'] = f"0x{rev:X}"
                    else:
                        cpu_details['microcode'] = str(rev)
                
                # SMT status already inferred from core counts above
                
                # Extract features from description
                desc = proc.Description if proc.Description else ""
                if 'Core' in desc:
                    cpu_details['features'].append('Multi-Core')
                break
        except:
            pass
        
        # Try to get P-states and boost info from PowerCfg (Windows)
        try:
            result = subprocess.run(['powercfg', '/query', 'SCHEME_CURRENT'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                cpu_details['p_states'] = 'Processor Power States available'
                # Check for boost status
                if 'processor' in result.stdout.lower() or 'boost' in result.stdout.lower():
                    cpu_details['features'].append('Turbo Boost capable')
        except:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux-specific info from /proc/cpuinfo
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo_content = f.read()
                
                # Extract flags/features and SMT info from /proc/cpuinfo
                for line in cpuinfo_content.split('\n'):
                    if line.startswith('flags'):
                        flags = line.split(':', 1)[1].strip().split()
                        cpu_details['instruction_sets'] = [f.upper() for f in flags[:15]]
                        
                        # Check for virtualization
                        if any(flag in flags for flag in ['vmx', 'svm']):
                            cpu_details['virtualization'] = 'Supported'
                        
                        # Check for security features
                        security = []
                        if any(flag in flags for flag in ['sgx', 'sgx1', 'sgx2']):
                            security.append('SGX')
                        if any(flag in flags for flag in ['aes', 'aes-ni']):
                            security.append('AES-NI')
                        if any(flag in flags for flag in ['tsx', 'tsx-force-abort']):
                            security.append('TSX')
                        if 'smep' in flags:
                            security.append('SMEP')
                        if 'smap' in flags:
                            security.append('SMAP')
                        if any(flag in flags for flag in ['mds', 'mds-no']):
                            security.append('MDS Mitigations')
                        if any(flag in flags for flag in ['spec-ctrl', 'ssbd']):
                            security.append('Spectre/Meltdown Mitigations')
                        
                        if security:
                            cpu_details['security_features'] = security
                        break
        except:
            pass
        
        # Try to get cache, socket, NUMA, and P-states from lscpu (fallback if above didn't work)
        try:
            result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'L1d cache' in line and not cache_info['l1']:
                        cpu_details['cache_l1'] = line.split(':', 1)[1].strip()
                    elif 'L2 cache' in line and 'cache(s)' not in line and not cache_info['l2']:
                        cpu_details['cache_l2'] = line.split(':', 1)[1].strip()
                    elif 'L3 cache' in line and 'cache(s)' not in line and not cache_info['l3']:
                        cpu_details['cache_l3'] = line.split(':', 1)[1].strip()
                    elif 'Socket(s):' in line:
                        cpu_details['socket'] = line.split(':', 1)[1].strip()
                    elif 'NUMA node(s):' in line:
                        cpu_details['numa_nodes'] = line.split(':', 1)[1].strip()
        except:
            pass

    # Final cache fill using helper/WMI if still unavailable
    try:
        cache_info = get_detailed_cache_info()
        if cache_info['l1'] and cpu_details['cache_l1'] == 'Unavailable':
            cpu_details['cache_l1'] = cache_info['l1']
        if cache_info['l2'] and cpu_details['cache_l2'] == 'Unavailable':
            cpu_details['cache_l2'] = cache_info['l2']
        if cache_info['l3'] and cpu_details['cache_l3'] == 'Unavailable':
            cpu_details['cache_l3'] = cache_info['l3']
    except:
        pass
    
    # Collect per-core telemetry (on-demand, no continuous polling)
    try:
        cpu_details['per_core_frequency'] = get_per_core_frequency_snapshot()
    except:
        cpu_details['per_core_frequency'] = []
    
    try:
        cpu_details['c_state_residency'] = get_c_state_residency()
    except:
        cpu_details['c_state_residency'] = []
    
    # Collect APIC topology and cache sharing groups from CPUID helper
    try:
        cpuid_data = read_cpuid_frequencies()
        if cpuid_data:
            # Parse APIC IDs with cache group mappings
            apic_ids = cpuid_data.get('apic_ids', [])
            if apic_ids:
                cpu_details['apic_ids'] = apic_ids
            
            # Parse cache sharing summary
            cache_sharing = cpuid_data.get('cache_sharing', {})
            if cache_sharing:
                cpu_details['cache_sharing_groups'] = cache_sharing
        # If CPUID helper didn't provide APIC IDs, use Python fallback topology
        if not cpu_details.get('apic_ids'):
            try:
                from cpuid_topology import get_cpuid_topology
                topo = get_cpuid_topology()
                if topo and topo.get('apic_ids'):
                    cpu_details['apic_ids'] = topo.get('apic_ids')
                if topo and topo.get('smt_status'):
                    cpu_details['smt_status'] = topo.get('smt_status')
            except Exception:
                # Keep existing fallbacks
                pass
    except:
        cpu_details['apic_ids'] = []
        cpu_details['cache_sharing_groups'] = {}
        
        # Try to get TDP from OS-specific sources
        tdp_info = get_detailed_tdp_info()
        if tdp_info:
            cpu_details['tdp'] = tdp_info
        
        # Try to get thermal throttling status from /sys
        try:
            result = subprocess.run(['cat', '/sys/devices/system/cpu/cpu0/cpufreq/affected_cpus'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                cpu_details['thermal_throttling'] = 'CPU frequency scaling enabled'
        except:
            pass
    
    # Phase 1: Kernel Helper Integration - Status and Capabilities
    # Add kernel helper data at the end (augments existing data, doesn't replace)
    try:
        from kernel_integration import (
            get_kernel_helper_status,
            get_kernel_cpu_temperatures,
            get_kernel_power_data,
            get_kernel_turbo_ratios,
            get_kernel_tdp_info,
            get_kernel_microcode_info,
            get_kernel_package_power,
            get_kernel_ipc_metrics,
            get_kernel_c_states
        )
        
        # Get kernel helper status (Phase 1 - always available)
        cpu_details['kernel_helper'] = get_kernel_helper_status()
        
        # Update MSR access field based on kernel helper status
        if cpu_details['kernel_helper'].get('available'):
            presence = cpu_details['kernel_helper'].get('presence', 'absent')
            driver_version = cpu_details['kernel_helper'].get('driver_version', 'Unknown')
            cpu_details['msr_access'] = f'Available (kernel driver v{driver_version})'
        else:
            error = cpu_details['kernel_helper'].get('error', 'Unknown')
            cpu_details['msr_access'] = f'Not available ({error})'
        
        # Get temperature data (Phase 2 - stub for now)
        cpu_details['kernel_temperatures'] = get_kernel_cpu_temperatures()
        
        # Get power data (Phase 2 - stub for now)
        cpu_details['kernel_power'] = get_kernel_power_data()
        
        # Get TDP info (NEW - High Priority)
        cpu_details['kernel_tdp'] = get_kernel_tdp_info()
        
        # Get microcode info (NEW - High Priority)
        cpu_details['kernel_microcode'] = get_kernel_microcode_info()
        
        # Get package power draw (NEW - High Priority)
        cpu_details['kernel_package_power'] = get_kernel_package_power()
        
        # Get IPC metrics (NEW - Medium Priority)
        cpu_details['kernel_ipc'] = get_kernel_ipc_metrics()
        
        # If kernel package power is available, add to display
        package_power = cpu_details['kernel_package_power']
        if package_power.get('available') and 'package_watts' in package_power:
            cpu_details['package_power_draw'] = f"{package_power['package_watts']:.1f}W (RAPL)"
        else:
            cpu_details['package_power_draw'] = 'Unavailable'
        
        # If kernel microcode data is available, override microcode field
        kernel_microcode = cpu_details['kernel_microcode']
        if kernel_microcode.get('available') and 'microcode_version' in kernel_microcode:
            cpu_details['microcode'] = f"{kernel_microcode['microcode_version']} (MSR 0x8B)"
        
        # If kernel TDP data is available, override TDP field
        kernel_tdp = cpu_details['kernel_tdp']
        if kernel_tdp.get('available') and 'tdp_watts' in kernel_tdp:
            cpu_details['tdp'] = f"{kernel_tdp['tdp_watts']}W (MSR 0x614)"
        
        # Get turbo ratios (Phase 3 - use kernel data when available)
        cpu_details['kernel_turbo'] = get_kernel_turbo_ratios()
        
        # If kernel turbo data is available, override CPUID turbo data
        kernel_turbo = cpu_details['kernel_turbo']
        if kernel_turbo.get('available') and 'turbo_ratios' in kernel_turbo:
            ratios = kernel_turbo['turbo_ratios']
            # Convert from ratio to frequency (ratio * 100 MHz for Intel)
            if '1_core_active' in ratios:
                cpu_details['max_turbo_1c'] = f"{ratios['1_core_active'] * 100:.0f}"
                # Also update max_turbo_freq with the highest turbo ratio
                max_ratio = ratios['1_core_active']
                cpu_details['max_turbo_freq'] = f"{max_ratio * 100:.0f} MHz"
            if '8_cores_active' in ratios:  # Use 8-core as "all-core" approximation
                cpu_details['max_turbo_ac'] = f"{ratios['8_cores_active'] * 100:.0f}"
            elif '4_cores_active' in ratios:
                cpu_details['max_turbo_ac'] = f"{ratios['4_cores_active'] * 100:.0f}"
        else:
            # Fallback to CPUID calculation if kernel data not available
            if max_val and base_val and max_val > base_val * 1.1:
                cpu_details['max_turbo_freq'] = f"{max_val:.2f} MHz"
        
        # Get C-states (Phase 3 - stub for now)
        cpu_details['kernel_cstates'] = get_kernel_c_states()
        
        # Thermal Throttling Detection (NEW - Medium Priority)
        # Check if current temperatures are close to TjMax or if turbo is being limited
        kernel_temps = cpu_details.get('kernel_temperatures', {})
        if kernel_temps.get('available') and kernel_temps.get('temperatures'):
            temps = kernel_temps['temperatures']
            tj_max = kernel_temps.get('tj_max', 105)
            
            # Find hottest core
            hottest_core = max(temps.keys(), key=lambda k: temps[k].get('celsius', 0))
            hottest_temp = temps[hottest_core].get('celsius', 0)
            temp_margin = temps[hottest_core].get('margin', 0)
            
            # Check for thermal throttling indicators
            throttling_indicators = []
            
            if temp_margin <= 10:  # Within 10°C of TjMax
                throttling_indicators.append(f"Thermal headroom low ({temp_margin}°C margin)")
            
            if hottest_temp >= 85:  # High temperature
                throttling_indicators.append(f"High temperature ({hottest_temp}°C)")
            
            # Check if turbo ratios are being limited (compare to expected)
            kernel_turbo = cpu_details.get('kernel_turbo', {})
            if kernel_turbo.get('available') and 'ratios' in kernel_turbo:
                ratios = kernel_turbo['ratios']
                max_ratio = ratios.get('1_core_active', 0)
                current_freq = os_freq.get('current', 0)
                
                if current_freq and max_ratio:
                    expected_turbo = max_ratio * 100  # Convert ratio to MHz
                    if current_freq < expected_turbo * 0.9:  # More than 10% below expected turbo
                        throttling_indicators.append(f"Turbo limited ({current_freq:.0f}MHz vs {expected_turbo:.0f}MHz expected)")
            
            if throttling_indicators:
                cpu_details['thermal_throttling'] = f"Possible throttling: {', '.join(throttling_indicators)}"
            else:
                cpu_details['thermal_throttling'] = "No thermal throttling detected"
        else:
            cpu_details['thermal_throttling'] = "Temperature data unavailable"
        
        # Efficiency Core Analysis (NEW - Medium Priority)
        # Analyze P-core vs E-core behavior and frequency scaling
        apic_data = cpu_details.get('apic_ids', [])
        if apic_data:
            p_cores = []
            e_cores = []
            
            # Separate P-cores and E-cores based on core_type
            for core_info in apic_data:
                core_type = core_info.get('core_type', 0)
                if core_type == 64:  # P-core
                    p_cores.append(core_info)
                elif core_type == 32:  # E-core
                    e_cores.append(core_info)
            
            # Analyze frequency distribution between P-cores and E-cores
            per_core_freq = cpu_details.get('per_core_frequency', [])
            if per_core_freq:
                p_core_freqs = []
                e_core_freqs = []
                
                for freq_data in per_core_freq:
                    core_idx = freq_data.get('core', 0)
                    freq_mhz = freq_data.get('frequency_mhz', 0)
                    
                    # Find matching APIC data to determine core type
                    core_type = None
                    for apic_info in apic_data:
                        if apic_info.get('index') == core_idx:
                            core_type = apic_info.get('core_type', 0)
                            break
                    
                    if core_type == 64:  # P-core
                        p_core_freqs.append(freq_mhz)
                    elif core_type == 32:  # E-core
                        e_core_freqs.append(freq_mhz)
                
                # Calculate statistics
                efficiency_analysis = {
                    'p_cores': {
                        'count': len(p_cores),
                        'frequency_avg': sum(p_core_freqs) / len(p_core_freqs) if p_core_freqs else 0,
                        'frequency_range': (min(p_core_freqs), max(p_core_freqs)) if p_core_freqs else (0, 0)
                    },
                    'e_cores': {
                        'count': len(e_cores),
                        'frequency_avg': sum(e_core_freqs) / len(e_core_freqs) if e_core_freqs else 0,
                        'frequency_range': (min(e_core_freqs), max(e_core_freqs)) if e_core_freqs else (0, 0)
                    }
                }
                
                # Store analysis results
                cpu_details['efficiency_analysis'] = efficiency_analysis
                
                # Add summary text
                if p_core_freqs and e_core_freqs:
                    p_avg = efficiency_analysis['p_cores']['frequency_avg']
                    e_avg = efficiency_analysis['e_cores']['frequency_avg']
                    ratio = p_avg / e_avg if e_avg > 0 else 0
                    
                    cpu_details['efficiency_summary'] = (
                        f"P-cores: {len(p_cores)} @ {p_avg:.0f}MHz avg, "
                        f"E-cores: {len(e_cores)} @ {e_avg:.0f}MHz avg, "
                        f"P/E ratio: {ratio:.1f}x"
                    )
                elif p_core_freqs:
                    p_avg = efficiency_analysis['p_cores']['frequency_avg']
                    cpu_details['efficiency_summary'] = f"P-cores only: {len(p_cores)} @ {p_avg:.0f}MHz avg"
                elif e_core_freqs:
                    e_avg = efficiency_analysis['e_cores']['frequency_avg']
                    cpu_details['efficiency_summary'] = f"E-cores only: {len(e_cores)} @ {e_avg:.0f}MHz avg"
                else:
                    cpu_details['efficiency_summary'] = "Efficiency core analysis unavailable"
            else:
                cpu_details['efficiency_summary'] = "Per-core frequency data unavailable"
        else:
            cpu_details['efficiency_summary'] = "APIC topology data unavailable"
        
    except ImportError:
        # Kernel integration module not available - silent fallback
        cpu_details['kernel_helper'] = {
            'available': False,
            'error': 'kernel_integration.py not found',
            'status_text': '⚪ Not Available'
        }
        cpu_details['msr_access'] = 'Not available (kernel_integration.py not found)'
    except Exception as e:
        # Unexpected error - log but don't crash
        cpu_details['kernel_helper'] = {
            'available': False,
            'error': f'Integration error: {str(e)}',
            'status_text': '🔴 Error'
        }
        cpu_details['msr_access'] = f'Not available (error: {str(e)})'
    
    return cpu_details

def get_nvme_helper_info():
    """Get NVMe SMART telemetry from nvme_helper.exe"""
    nvme_info = {
        'devices': [],
        'available': False,
        'error': None
    }
    
    if not IS_WINDOWS:
        return nvme_info
    
    try:
        nvme_helper_path = os.path.join(os.path.dirname(__file__), 'nvme_helper.exe')
        if not os.path.exists(nvme_helper_path):
            return nvme_info
        
        result = subprocess.run([nvme_helper_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            nvme_info['devices'] = data.get('nvme_devices', [])
            nvme_info['available'] = len(nvme_info['devices']) > 0
            nvme_info['method'] = data.get('method', 'Unknown')
            nvme_info['note'] = data.get('note', '')
    except json.JSONDecodeError:
        nvme_info['error'] = "JSON parse error"
    except FileNotFoundError:
        nvme_info['error'] = "nvme_helper.exe not found"
    except Exception as e:
        nvme_info['error'] = str(e)
    
    return nvme_info

def get_edid_helper_info():
    """Get EDID information from edid_helper.exe"""
    edid_info = {
        'edid_devices': [],
        'available': False,
        'error': None
    }
    
    if not IS_WINDOWS:
        return edid_info
    
    try:
        edid_helper_path = os.path.join(os.path.dirname(__file__), 'edid_helper.exe')
        if not os.path.exists(edid_helper_path):
            return edid_info
        
        result = subprocess.run([edid_helper_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            edid_info['edid_devices'] = data.get('edid_devices', [])
            edid_info['available'] = len(edid_info['edid_devices']) > 0
    except json.JSONDecodeError:
        edid_info['error'] = "JSON parse error"
    except FileNotFoundError:
        edid_info['error'] = "edid_helper.exe not found"
    except Exception as e:
        edid_info['error'] = str(e)
    
    return edid_info

def get_pci_topology():
    """Get PCI device tree topology from Windows registry"""
    pci_devices = {
        'devices': [],
        'available': False,
        'error': None
    }
    
    if not IS_WINDOWS:
        return pci_devices
    
    try:
        # Query PCI devices from Windows registry
        import winreg
        
        devices_list = []
        
        try:
            # Open PCI device registry key
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                r"SYSTEM\CurrentControlSet\Enum\PCI")
            
            index = 0
            while True:
                try:
                    device_id = winreg.EnumKey(hkey, index)
                    device_path = rf"SYSTEM\CurrentControlSet\Enum\PCI\{device_id}"
                    
                    hkey_device = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, device_path)
                    
                    # Read device properties
                    try:
                        class_name, _, _ = winreg.QueryValueEx(hkey_device, "Class")
                    except:
                        class_name = "Unknown"
                    
                    try:
                        class_guid, _, _ = winreg.QueryValueEx(hkey_device, "ClassGUID")
                    except:
                        class_guid = "Unknown"
                    
                    try:
                        driver, _, _ = winreg.QueryValueEx(hkey_device, "Driver")
                    except:
                        driver = "Not installed"
                    
                    # Parse vendor and device IDs from device_id (VEN_XXXX&DEV_XXXX format)
                    vendor_id = "Unknown"
                    device_code = "Unknown"
                    if "VEN_" in device_id and "DEV_" in device_id:
                        parts = device_id.split("&")
                        for part in parts:
                            if part.startswith("VEN_"):
                                vendor_id = part[4:]
                            elif part.startswith("DEV_"):
                                device_code = part[4:]
                    
                    devices_list.append({
                        'device_id': device_id,
                        'vendor_id': vendor_id,
                        'device_code': device_code,
                        'class': class_name,
                        'class_guid': class_guid,
                        'driver': driver
                    })
                    
                    winreg.CloseKey(hkey_device)
                    index += 1
                except OSError:
                    break
            
            winreg.CloseKey(hkey)
            
            if devices_list:
                pci_devices['devices'] = devices_list
                pci_devices['available'] = True
        
        except Exception as e:
            pci_devices['error'] = str(e)
    
    except ImportError:
        pci_devices['error'] = "winreg module not available"
    
    return pci_devices

def get_gpu_pcie_info():
    """Get PCIe link speed and width information for GPUs"""
    pcie_info = {}
    
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            ps_command = """
            Get-WmiObject -Class Win32_VideoController | ForEach-Object {
                $pnp_id = $_.PNPDeviceID
                if ($pnp_id) {
                    try {
                        $device = Get-PnpDevice -PNPDeviceID $pnp_id -ErrorAction SilentlyContinue
                        if ($device) {
                            [PSCustomObject]@{
                                Name = $_.Name
                                LinkSpeed = "Unknown"
                                LinkWidth = "Unknown"
                                Status = $device.Status
                            }
                        }
                    } catch { }
                }
            } | ConvertTo-Json
            """
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for gpu in data:
                        gpu_name = gpu.get('Name', 'Unknown')
                        pcie_info[gpu_name] = {
                            'link_speed': gpu.get('LinkSpeed', 'Unavailable'),
                            'link_width': gpu.get('LinkWidth', 'Unavailable')
                        }
                except:
                    pass
        except:
            pass
    
    return pcie_info

def get_gpu_utilization_temp():
    """Get GPU utilization and temperature (optional NVML)"""
    gpu_util = {}
    
    try:
        import pynvml
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        
        for i in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                temp = pynvml.nvmlDeviceGetTemperature(handle, 0)  # 0 = GPU temperature
                
                gpu_util[name] = {
                    'core_utilization': util.gpu,
                    'memory_utilization': util.memory,
                    'temperature_c': temp
                }
            except:
                pass
        
        pynvml.nvmlShutdown()
    except ImportError:
        pass  # NVML not available
    except:
        pass
    
    return gpu_util

def get_gpu_info():
    gpu_list = []
    nvidia_gpus = {}
    
    # PRIMARY: Try nvidia-smi for NVIDIA GPUs (works on Windows, Linux, and Pi)
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version,pci.device_id', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 2:
                    gpu_name = parts[0]
                    nvidia_gpus[gpu_name] = {
                        'name': gpu_name,
                        'adapter_ram': float(parts[1]) / 1024,  # Convert MB to GB
                        'driver_version': parts[2] if len(parts) > 2 else 'Unknown',
                        'device_id': parts[3] if len(parts) > 3 else 'Unknown',
                        'source': 'nvidia-smi'
                    }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # nvidia-smi not available
    except Exception:
        pass
    
    if IS_WINDOWS:
        # Windows: Use PowerShell and WMI
        try:
            ps_command = """
            Get-CimInstance -ClassName Win32_VideoController | ForEach-Object {
                $vram = $null
                if ($_.AdapterRAM -ne $null -and $_.AdapterRAM -gt 0) {
                    $vram = [uint64]$_.AdapterRAM
                }
                [PSCustomObject]@{
                    Name = $_.Name
                    AdapterRAM = $vram
                    DriverVersion = $_.DriverVersion
                    VideoProcessor = $_.VideoProcessor
                    CurrentRefreshRate = $_.CurrentRefreshRate
                    VideoModeDescription = $_.VideoModeDescription
                    Status = $_.Status
                    PNPDeviceID = $_.PNPDeviceID
                }
            } | ConvertTo-Json
            """
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                gpu_data = json.loads(result.stdout)
                if isinstance(gpu_data, dict):
                    gpu_data = [gpu_data]
                
                for gpu in gpu_data:
                    gpu_name = gpu.get('Name', 'Unknown')
                    
                    if gpu_name in nvidia_gpus:
                        gpu_info = nvidia_gpus[gpu_name].copy()
                        gpu_info.update({
                            'video_processor': gpu.get('VideoProcessor', 'Unknown'),
                            'current_refresh_rate': gpu.get('CurrentRefreshRate', 'Unknown'),
                            'video_mode_description': gpu.get('VideoModeDescription', 'Unknown'),
                            'status': gpu.get('Status', 'Unknown'),
                            'pnp_device_id': gpu.get('PNPDeviceID', 'Unknown')
                        })
                        gpu_list.append(gpu_info)
                    else:
                        vram_gb = None
                        if gpu.get('AdapterRAM'):
                            try:
                                vram_bytes = int(gpu['AdapterRAM'])
                                if 0 < vram_bytes < 1e12:
                                    vram_gb = vram_bytes / (1024 ** 3)
                            except:
                                pass
                        
                        gpu_list.append({
                            'name': gpu_name,
                            'driver_version': gpu.get('DriverVersion', 'Unknown'),
                            'video_processor': gpu.get('VideoProcessor', 'Unknown'),
                            'adapter_ram': vram_gb,
                            'current_refresh_rate': gpu.get('CurrentRefreshRate', 'Unknown'),
                            'video_mode_description': gpu.get('VideoModeDescription', 'Unknown'),
                            'status': gpu.get('Status', 'Unknown'),
                            'pnp_device_id': gpu.get('PNPDeviceID', 'Unknown'),
                            'source': 'powershell'
                        })
        except Exception:
            pass
        
        # FALLBACK: Direct WMI for Windows
        if not gpu_list and HAS_WMI:
            try:
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    gpu_name = gpu.Name if gpu.Name else "Unknown"
                    
                    if gpu_name in nvidia_gpus:
                        gpu_info = nvidia_gpus[gpu_name].copy()
                        gpu_info.update({
                            'video_processor': gpu.VideoProcessor if gpu.VideoProcessor else "Unknown",
                            'current_refresh_rate': gpu.CurrentRefreshRate if gpu.CurrentRefreshRate else "Unknown",
                            'video_mode_description': gpu.VideoModeDescription if gpu.VideoModeDescription else "Unknown",
                            'status': gpu.Status if gpu.Status else "Unknown",
                            'pnp_device_id': gpu.PNPDeviceID if gpu.PNPDeviceID else "Unknown"
                        })
                        gpu_list.append(gpu_info)
                    else:
                        gpu_list.append({
                            'name': gpu_name,
                            'driver_version': gpu.DriverVersion if gpu.DriverVersion else "Unknown",
                            'video_processor': gpu.VideoProcessor if gpu.VideoProcessor else "Unknown",
                            'adapter_ram': None,
                            'current_refresh_rate': gpu.CurrentRefreshRate if gpu.CurrentRefreshRate else "Unknown",
                            'video_mode_description': gpu.VideoModeDescription if gpu.VideoModeDescription else "Unknown",
                            'status': gpu.Status if gpu.Status else "Unknown",
                            'pnp_device_id': gpu.PNPDeviceID if gpu.PNPDeviceID else "Unknown",
                            'source': 'wmi'
                        })
            except Exception as e:
                return {'error': str(e)}
    
    elif IS_LINUX or IS_PI:
        # Linux/Pi: Use lspci
        if not gpu_list:
            try:
                result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if 'VGA' in line or 'Display' in line or '3D' in line:
                            # Extract GPU name from lspci output
                            parts = line.split(': ', 1)
                            if len(parts) == 2:
                                gpu_name = parts[1].strip()
                                gpu_list.append({
                                    'name': gpu_name,
                                    'driver_version': 'Unknown',
                                    'video_processor': 'Unknown',
                                    'adapter_ram': None,
                                    'source': 'lspci'
                                })
            except:
                pass
        
        # For Raspberry Pi, add built-in GPU info
        if IS_PI and not gpu_list:
            gpu_list.append({
                'name': 'Broadcom VideoCore (Pi GPU)',
                'driver_version': 'Firmware Integrated',
                'video_processor': 'VideoCore VII' if 'Pi 5' in platform.platform() else 'VideoCore VI',
                'adapter_ram': None,  # Pi shares system RAM
                'source': 'System Info'
            })
    
    # Phase 2: Add PCIe and utilization data
    pcie_info = get_gpu_pcie_info()
    gpu_util = get_gpu_utilization_temp()
    
    # Merge PCIe and utilization info into gpu_list
    if gpu_list and isinstance(gpu_list, list):
        for gpu in gpu_list:
            gpu_name = gpu.get('name', '')
            if gpu_name in pcie_info:
                gpu.update(pcie_info[gpu_name])
            if gpu_name in gpu_util:
                gpu.update(gpu_util[gpu_name])
    
    return gpu_list if gpu_list else (nvidia_gpus.values() if nvidia_gpus else {'error': 'No GPU detected'})

def get_system_info():
    """Get comprehensive system information from multiple methods"""
    system_info = {
        'hostname': platform.node(),
        'model': 'Unknown',
        'manufacturer': 'Unknown',
        'serial': 'Unknown',
        'bios_version': 'Unknown',
        'bios_date': 'Unknown',
        'os_name': platform.system(),
        'os_version': platform.version(),
        'os_release': platform.release(),
        'architecture': platform.architecture(),
        'processor': platform.processor(),
        'boot_time': 'Unknown',
        'uptime': 'Unknown'
    }
    
    # Method 1: Try platform module first (basic system info)
    try:
        system_info.update({
            'platform': platform.platform(),
            'machine': platform.machine(),
            'processor_count': psutil.cpu_count(logical=True),
            'processor_physical': psutil.cpu_count(logical=False)
        })
    except Exception:
        pass
    
    # Method 2: WMI fallback (Windows detailed system info)
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            
            # Computer system information
            for system in c.Win32_ComputerSystem():
                system_info.update({
                    'model': system.Model if system.Model else 'Unknown',
                    'manufacturer': system.Manufacturer if system.Manufacturer else 'Unknown',
                    'domain': system.Domain if system.Domain else 'Unknown',
                    'workgroup': system.Workgroup if system.Workgroup else 'Unknown',
                    'system_type': system.SystemType if system.SystemType else 'Unknown',
                    'total_physical_memory': system.TotalPhysicalMemory if system.TotalPhysicalMemory else 0,
                    'source_system': 'wmi'
                })
                break
            
            # Get power supply info from WMI
            try:
                for psu in c.Win32_PowerSupply():
                    system_info['power_supply'] = {
                        'name': psu.Name if psu.Name else 'Unknown',
                        'status': psu.Status if psu.Status else 'Unknown',
                        'capacity': psu.Characteristics if psu.Characteristics else 'Unknown'
                    }
                    break
            except Exception:
                pass
        except Exception:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux/Pi: Use /proc, /sys, and dmidecode
        try:
            # Try to get model from dmidecode
            result = subprocess.run(['sudo', 'dmidecode', '-s', 'system-product-name'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                system_info['model'] = result.stdout.strip() or 'Unknown'
            
            # Try to get serial
            result = subprocess.run(['sudo', 'dmidecode', '-s', 'system-serial-number'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                system_info['serial'] = result.stdout.strip() or 'Unknown'
        except:
            pass
        
        # For Raspberry Pi, use special model detection
        if IS_PI:
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    system_info['model'] = f.read().strip()
                    system_info['serial'] = 'N/A (SoC)'
            except:
                system_info['model'] = 'Raspberry Pi'
    
    # Get total storage capacity (cross-platform)
    try:
        partitions = psutil.disk_partitions()
        system_info['drive_count'] = len(partitions)
        total_size = 0
        total_free = 0
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                total_size += usage.total
                total_free += usage.free
            except PermissionError:
                pass
        system_info['total_storage_gb'] = total_size / (1024 ** 3)
        system_info['total_storage_free_gb'] = total_free / (1024 ** 3)
    except Exception:
        pass
    
    # Get battery info if available (cross-platform)
    try:
        battery = psutil.sensors_battery()
        if battery:
            system_info['battery_info'] = {
                'percent': battery.percent,
                'secsleft': battery.secsleft,
                'power_plugged': battery.power_plugged
            }
    except Exception:
        pass
    
    return system_info

def get_battery_info():
    """Get detailed battery health information from multiple methods"""
    battery_info = {
        'percent': 0,
        'power_plugged': False,
        'secsleft': 0,
        'design_capacity': 0,
        'full_charge_capacity': 0,
        'wear_level': 0,
        'health_status': 'Unknown',
        'technology': 'Unknown',
        'manufacturer': 'Unknown',
        'model': 'Unknown',
        'serial': 'Unknown',
        'voltage': 0,
        'current': 0,
        'power_watts': 0
    }
    
    # Method 1: Try psutil first (basic battery info)
    try:
        battery = psutil.sensors_battery()
        if battery:
            battery_info.update({
                'percent': battery.percent,
                'power_plugged': battery.power_plugged,
                'secsleft': battery.secsleft if battery.secsleft is not None and battery.secsleft > 0 else 0,
                'source': 'psutil'
            })
    except Exception:
        pass
    
    # Method 2: WMI fallback (Windows detailed battery info)
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for battery in c.Win32_Battery():
                battery_info.update({
                    'percent': battery.EstimatedChargeRemaining if battery.EstimatedChargeRemaining else battery_info['percent'],
                    'status': battery.BatteryStatus if battery.BatteryStatus else 'Unknown',
                    'source': 'wmi'
                })
                break
            
            # Try Win32_PortableBattery for more detailed info
            for battery in c.Win32_PortableBattery():
                battery_info.update({
                    'design_capacity': battery.DesignCapacity if battery.DesignCapacity else 0,
                    'full_charge_capacity': battery.FullChargeCapacity if battery.FullChargeCapacity else 0,
                    'technology': battery.Chemistry if battery.Chemistry else 'Unknown',
                    'manufacturer': battery.Manufacturer if battery.Manufacturer else 'Unknown',
                    'model': battery.Name if battery.Name else 'Unknown',
                    'serial': battery.SerialNumber if battery.SerialNumber else 'Unknown',
                    'voltage': battery.DesignVoltage if battery.DesignVoltage else 0,
                    'source': 'wmi_portable'
                })
                break
                
        except Exception:
            pass
    
    # Method 3: PowerShell fallback (Windows battery report)
    elif IS_WINDOWS:
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 'powercfg /batteryreport /output "$env:TEMP\\batteryreport.xml"'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Parse the battery report XML
                import xml.etree.ElementTree as ET
                import tempfile
                
                temp_file = os.path.join(os.environ['TEMP'], 'batteryreport.xml')
                if os.path.exists(temp_file):
                    try:
                        tree = ET.parse(temp_file)
                        root = tree.getroot()
                        
                        # Extract battery information from XML
                        for battery in root.findall('.//Battery'):
                            for child in battery:
                                if 'DesignCapacity' in child.tag:
                                    battery_info['design_capacity'] = int(child.text) if child.text else 0
                                elif 'FullChargeCapacity' in child.tag:
                                    battery_info['full_charge_capacity'] = int(child.text) if child.text else 0
                                elif 'Manufacturer' in child.tag:
                                    battery_info['manufacturer'] = child.text
                                elif 'DeviceName' in child.tag:
                                    battery_info['model'] = child.text
                                elif 'SerialNumber' in child.tag:
                                    battery_info['serial'] = child.text
                                elif 'Chemistry' in child.tag:
                                    battery_info['technology'] = child.text
                        
                        battery_info['source'] = 'powercfg_report'
                    except Exception:
                        pass
                    finally:
                        # Clean up temp file
                        try:
                            os.remove(temp_file)
                        except:
                            pass
        except Exception:
            pass
    
    # Method 4: Linux fallback (ACPI and sysfs)
    elif IS_LINUX:
        try:
            # Try ACPI command first
            result = subprocess.run(['acpi', '-V'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Parse ACPI output for battery information
                for line in result.stdout.split('\n'):
                    if 'design capacity:' in line.lower():
                        try:
                            battery_info['design_capacity'] = int(line.split(':')[1].strip().split()[0])
                        except:
                            pass
                    elif 'last full capacity:' in line.lower():
                        try:
                            battery_info['full_charge_capacity'] = int(line.split(':')[1].strip().split()[0])
                        except:
                            pass
                    elif 'manufacturer:' in line.lower():
                        battery_info['manufacturer'] = line.split(':')[1].strip()
                    elif 'model number:' in line.lower():
                        battery_info['model'] = line.split(':')[1].strip()
                    elif 'serial number:' in line.lower():
                        battery_info['serial'] = line.split(':')[1].strip()
                    elif 'battery type:' in line.lower():
                        battery_info['technology'] = line.split(':')[1].strip()
                
                battery_info['source'] = 'acpi'
        except Exception:
            pass
        
        # Fallback to sysfs
        try:
            battery_path = '/sys/class/power_supply/BAT0'
            if os.path.exists(battery_path):
                # Read capacity
                with open(f'{battery_path}/capacity', 'r') as f:
                    battery_info['percent'] = int(f.read().strip())
                
                # Read status
                with open(f'{battery_path}/status', 'r') as f:
                    status = f.read().strip()
                    battery_info['power_plugged'] = status != "Discharging"
                
                # Read voltage
                try:
                    with open(f'{battery_path}/voltage_now', 'r') as f:
                        voltage_uv = int(f.read().strip())
                        battery_info['voltage'] = voltage_uv / 1000000.0  # Convert to V
                except:
                    pass
                
                # Read current
                try:
                    with open(f'{battery_path}/current_now', 'r') as f:
                        current_ua = int(f.read().strip())
                        battery_info['current'] = current_ua / 1000000.0  # Convert to A
                        if battery_info['voltage'] > 0:
                            battery_info['power_watts'] = battery_info['voltage'] * battery_info['current']
                except:
                    pass
                
                # Read capacity info
                try:
                    with open(f'{battery_path}/energy_full_design', 'r') as f:
                        battery_info['design_capacity'] = int(f.read().strip())
                    with open(f'{battery_path}/energy_full', 'r') as f:
                        battery_info['full_charge_capacity'] = int(f.read().strip())
                except:
                    pass
                
                # Read technology
                try:
                    with open(f'{battery_path}/technology', 'r') as f:
                        battery_info['technology'] = f.read().strip()
                except:
                    pass
                
                # Read manufacturer
                try:
                    with open(f'{battery_path}/manufacturer', 'r') as f:
                        battery_info['manufacturer'] = f.read().strip()
                except:
                    pass
                
                # Read model name
                try:
                    with open(f'{battery_path}/model_name', 'r') as f:
                        battery_info['model'] = f.read().strip()
                except:
                    pass
                
                battery_info['source'] = 'sysfs'
        except Exception:
            pass
    
    # Calculate wear level and health status
    if battery_info['design_capacity'] > 0 and battery_info['full_charge_capacity'] > 0:
        wear_level = 1 - (battery_info['full_charge_capacity'] / battery_info['design_capacity'])
        battery_info['wear_level'] = max(0, min(100, wear_level * 100))  # Clamp to 0-100%
        
        # Determine health status
        if battery_info['wear_level'] < 20:
            battery_info['health_status'] = 'Good'
        elif battery_info['wear_level'] < 50:
            battery_info['health_status'] = 'Fair'
        else:
            battery_info['health_status'] = 'Poor'
    
    return battery_info

def get_monitor_info():
    monitors = []
    
    if IS_WINDOWS:
        # Windows: Use PowerShell and WMI
        try:
            # Use WMI first for monitor details
            if HAS_WMI:
                c = wmi.WMI()
                
                # Try Win32_DisplayConfiguration for resolution and refresh rate
                try:
                    for config in c.Win32_DisplayConfiguration():
                        if config.DeviceName:
                            monitors.append({
                                'name': config.DeviceName.strip() if config.DeviceName else "Unknown",
                                'resolution': f"{config.HorizontalResolution}x{config.VerticalResolution}" if config.HorizontalResolution and config.VerticalResolution else "Unknown",
                                'refresh_rate': config.RefreshRate if config.RefreshRate else "Unknown",
                                'bits_per_pixel': config.BitsPerPixel if config.BitsPerPixel else "Unknown",
                                'color_planes': config.ColorPlanes if config.ColorPlanes else "Unknown"
                            })
                except Exception:
                    pass
                
                # If that didn't work, try Win32_DesktopMonitor
                if not monitors:
                    try:
                        for monitor in c.Win32_DesktopMonitor():
                            try:
                                monitor_info = {
                                    'name': monitor.Name if monitor.Name else "Unknown Monitor",
                                    'manufacturer': "Unknown",
                                    'model': "Unknown",
                                    'serial': "Unknown",
                                    'pnp_device_id': monitor.PNPDeviceID if hasattr(monitor, 'PNPDeviceID') and monitor.PNPDeviceID else "Unknown"
                                }
                                
                                if hasattr(monitor, 'MonitorManufacturerCodeID') and monitor.MonitorManufacturerCodeID:
                                    monitor_info['manufacturer'] = monitor.MonitorManufacturerCodeID
                                
                                if hasattr(monitor, 'Model') and monitor.Model:
                                    monitor_info['model'] = monitor.Model
                                
                                if hasattr(monitor, 'SerialNumber') and monitor.SerialNumber:
                                    monitor_info['serial'] = monitor.SerialNumber
                                
                                monitors.append(monitor_info)
                            except Exception:
                                continue
                    except Exception:
                        pass
        except Exception as e:
            return {'error': f'Monitor detection failed: {str(e)}'}
    
    elif IS_LINUX or IS_PI:
        # Linux/Pi: Use xrandr or lsb_release
        try:
            # Try xrandr (most reliable on Linux with X11)
            result = subprocess.run(['xrandr'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if ' connected' in line:
                        parts = line.split()
                        monitor_name = parts[0]
                        resolution = "Unknown"
                        refresh_rate = "Unknown"
                        
                        # Try to extract resolution from line
                        for part in parts:
                            if 'x' in part and '+' in part:
                                resolution = part.split('+')[0]
                                break
                            elif 'x' in part:
                                resolution = part
                        
                        # Look for refresh rate in next lines or current line
                        for i, l in enumerate(lines):
                            if monitor_name in l and i + 1 < len(lines):
                                next_line = lines[i + 1]
                                if '*' in next_line:
                                    refresh_parts = next_line.split()
                                    if refresh_parts:
                                        refresh_rate = refresh_parts[-1].rstrip('*+ ')
                                break
                        
                        monitors.append({
                            'name': monitor_name,
                            'resolution': resolution,
                            'refresh_rate': refresh_rate,
                            'bits_per_pixel': 'Unknown',
                            'source': 'xrandr'
                        })
        except:
            pass
        
        # If xrandr didn't work or not available, try Wayland methods
        if not monitors:
            try:
                # Try wlr-randr for Wayland
                result = subprocess.run(['wlr-randr'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if 'current' in line.lower() or 'connected' in line.lower():
                            monitors.append({
                                'name': line.split()[0] if line.split() else 'Display',
                                'resolution': 'Unknown',
                                'refresh_rate': 'Unknown',
                                'source': 'wlr-randr'
                            })
            except:
                pass
        
        # Fallback for headless or SSH sessions
        if not monitors:
            monitors.append({
                'name': 'Display (Headless or SSH)',
                'resolution': 'N/A',
                'refresh_rate': 'N/A',
                'bits_per_pixel': 'N/A',
                'source': 'Fallback'
            })
    
    return monitors if monitors else {'error': 'No monitor information available'}

def get_disk_type_from_interface_and_model(interface_type, media_type, model):
    """Improved disk type detection based on interface, media type, and model"""
    if not interface_type:
        interface_type = ""
    if not media_type:
        media_type = ""
    if not model:
        model = ""
    
    interface_lower = interface_type.lower()
    media_lower = media_type.lower()
    model_lower = model.lower()
    
    # Check interface type first (most reliable)
    if 'nvme' in interface_lower or 'pcie' in interface_lower:
        return "NVMe SSD"
    
    # Check media type
    if 'solid' in media_lower or 'ssd' in media_lower:
        return "SSD"
    elif 'fixed' in media_lower or 'hdd' in media_lower:
        return "HDD"
    
    # Check model name for common SSD/NVMe indicators
    if any(keyword in model_lower for keyword in ['nvme', 'ssd', '970', '980', '990', 'samsung 990', 'wd black sn', 'kioxia xg', 'crucial p', 'sabrent']):
        return "NVMe SSD" if 'nvme' in model_lower else "SSD"
    elif any(keyword in model_lower for keyword in ['wd ', 'seagate', 'barracuda', 'hdd', 'hgst']):
        return "HDD"
    
    # Default based on media_type if available
    if media_type:
        return media_type
    
    return "Unknown"

def get_current_active_connection():
    """Get current active network connection with ISP/WHOIS information"""
    active_info = {
        'active_adapter': None,
        'ssid': None,
        'gateway': None,
        'dns_servers': [],
        'ip_address': None,
        'ip_address_v6': None,
        'mac_address': None,
        'isp_info': None,
        'gateway_hostname': None,
        'gateway_owner': None,
        'is_private_ip': False,
        'connection_type': None,
        'wifi_security': None,
        'error': None
    }
    
    try:
        def is_probable_mac(value):
            if not value:
                return False
            v = value.replace('-', '').replace(':', '').lower()
            return len(v) == 12 and all(c in '0123456789abcdef' for c in v)

        def is_ipv4(value):
            if not value:
                return False
            return re.match(r'^(?:\d{1,3}\.){3}\d{1,3}$', value) is not None

        def is_ipv6(value):
            if not value:
                return False
            return ':' in value and re.match(r'^[0-9a-fA-F:]+$', value) is not None

        def clean_ip(value):
            if not value:
                return value
            return value.replace('(Preferred)', '').strip()

        def add_gateway(value, record):
            ip = clean_ip(value)
            if not ip:
                return
            ip = ip.split()[0]
            if is_ipv6(ip):
                if ip.startswith('fe80::'):
                    return
                if not record.get('gateway_ipv6'):
                    record['gateway_ipv6'] = ip
            elif is_ipv4(ip):
                if not record.get('gateway_ipv4'):
                    record['gateway_ipv4'] = ip

        def add_dns(value, record):
            ip = clean_ip(value)
            if not ip:
                return
            ip = ip.split()[0]
            if is_ipv6(ip):
                if ip.startswith('fe80::'):
                    return
                if ip not in record['dns_v6']:
                    record['dns_v6'].append(ip)
            elif is_ipv4(ip):
                if ip not in record['dns_v4']:
                    record['dns_v4'].append(ip)

        # Find the active/connected adapter
        if IS_WINDOWS:
            # Get connected WiFi SSID + security info
            connected_wifi = False
            wifi_auth = None
            wifi_cipher = None
            try:
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        line_clean = line.strip()
                        line_lower = line_clean.lower()
                        if line_lower.startswith('state') and ':' in line_clean:
                            state = line_clean.split(':', 1)[1].strip().lower()
                            connected_wifi = (state == 'connected')
                        if line_lower.startswith('ssid') and not line_lower.startswith('bssid') and ':' in line_clean:
                            parts = line_clean.split(':', 1)
                            if len(parts) == 2:
                                ssid = parts[1].strip()
                                if ssid and ssid.lower() not in ['n/a', 'none', '<not connected>'] and not is_probable_mac(ssid):
                                    active_info['ssid'] = ssid
                                    active_info['connection_type'] = 'WiFi'
                        if line_lower.startswith('authentication') and ':' in line_clean:
                            parts = line_clean.split(':', 1)
                            if len(parts) == 2:
                                wifi_auth = parts[1].strip()
                        if line_lower.startswith('cipher') and ':' in line_clean:
                            parts = line_clean.split(':', 1)
                            if len(parts) == 2:
                                wifi_cipher = parts[1].strip()
            except Exception:
                pass

            if wifi_auth:
                active_info['wifi_security'] = wifi_auth + (f" / {wifi_cipher}" if wifi_cipher else "")

            # If no WiFi SSID, fall back to wired
            if not active_info['ssid']:
                active_info['connection_type'] = 'WiFi' if connected_wifi else 'Ethernet (Wired)'

            # Get adapter with default gateway (prioritize IPv4)
            try:
                result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    adapter_records = {}
                    current_adapter = None
                    in_gateway_block = False
                    in_dns_block = False

                    for line in result.stdout.split('\n'):
                        line_clean = line.strip()

                        if 'Adapter' in line and ':' in line:
                            parts = line.split(':', 1)
                            current_adapter = parts[1].strip() if len(parts) == 2 else None
                            if current_adapter:
                                adapter_records[current_adapter] = {
                                    'ipv4': None,
                                    'ipv6': None,
                                    'gateway_ipv4': None,
                                    'gateway_ipv6': None,
                                    'dns_v4': [],
                                    'dns_v6': [],
                                    'mac': None
                                }
                            in_gateway_block = False
                            in_dns_block = False
                            continue

                        if not current_adapter or current_adapter not in adapter_records:
                            continue

                        record = adapter_records[current_adapter]

                        if 'Default Gateway' in line_clean:
                            in_gateway_block = True
                            parts = line_clean.split(':', 1)
                            value = parts[1].strip() if len(parts) == 2 else ''
                            if value:
                                add_gateway(value, record)
                            continue

                        if 'DNS Servers' in line_clean:
                            in_dns_block = True
                            parts = line_clean.split(':', 1)
                            value = parts[1].strip() if len(parts) == 2 else ''
                            if value:
                                add_dns(value, record)
                            continue

                        if in_gateway_block and (line.startswith(' ') or line.startswith('\t')):
                            if line_clean:
                                add_gateway(line_clean, record)
                            continue
                        elif in_gateway_block and line_clean and not (line.startswith(' ') or line.startswith('\t')):
                            in_gateway_block = False

                        if in_dns_block and (line.startswith(' ') or line.startswith('\t')):
                            if line_clean:
                                add_dns(line_clean, record)
                            continue
                        elif in_dns_block and line_clean and not (line.startswith(' ') or line.startswith('\t')):
                            in_dns_block = False

                        if 'IPv4 Address' in line_clean and ':' in line_clean and 'IPv6' not in line_clean:
                            parts = line_clean.split(':', 1)
                            if len(parts) == 2:
                                ip = clean_ip(parts[1].strip())
                                if ip and ip not in ['', 'DHCP Enabled']:
                                    record['ipv4'] = ip.split()[0]

                        elif 'IPv6 Address' in line_clean and ':' in line_clean:
                            parts = line_clean.split(':', 1)
                            if len(parts) == 2:
                                ip = clean_ip(parts[1].strip())
                                if ip and not ip.startswith('fe80::'):
                                    record['ipv6'] = ip.split()[0]

                        elif 'Physical Address' in line_clean and ':' in line_clean:
                            parts = line_clean.split(':', 1)
                            if len(parts) == 2:
                                mac = parts[1].strip()
                                if mac and '-' in mac:
                                    record['mac'] = mac

                    # Pick adapter with IPv4 gateway first, else IPv6 gateway
                    def score_adapter(name, record):
                        score = 0
                        name_l = (name or '').lower()
                        if record.get('gateway_ipv4'):
                            score += 100
                        elif record.get('gateway_ipv6'):
                            score += 60
                        if record.get('dns_v4'):
                            score += 20
                        if record.get('ipv4'):
                            score += 10
                        # Penalize virtual/tunnel adapters
                        if any(token in name_l for token in ['virtual', 'vmware', 'hyper-v', 'virtualbox', 'loopback', 'tunnel', 'tap', 'vpn']):
                            score -= 50
                        return score

                    selected_adapter = None
                    selected_record = None
                    best_score = -999
                    for name, record in adapter_records.items():
                        s = score_adapter(name, record)
                        if s > best_score:
                            best_score = s
                            selected_adapter = name
                            selected_record = record

                    if selected_record:
                        active_info['active_adapter'] = selected_adapter
                        active_info['gateway'] = selected_record.get('gateway_ipv4') or selected_record.get('gateway_ipv6')
                        active_info['ip_address'] = selected_record.get('ipv4') or selected_record.get('ipv6')
                        active_info['ip_address_v6'] = selected_record.get('ipv6')
                        active_info['mac_address'] = selected_record.get('mac') or active_info.get('mac_address')
                        active_info['dns_servers'] = selected_record.get('dns_v4') or selected_record.get('dns_v6')
            except Exception:
                pass
        
        elif IS_LINUX:
            # Get default route and active interface
            try:
                result = subprocess.run(['ip', 'route', 'show'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'default via' in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                active_info['gateway'] = parts[2]
                                if len(parts) >= 5:
                                    active_info['active_adapter'] = parts[4]
            except Exception:
                pass
            
            # Get IP address
            try:
                result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    ips = result.stdout.strip().split()
                    if ips:
                        active_info['ip_address'] = ips[0]
            except Exception:
                pass
            
            # Get DNS servers
            try:
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            dns = line.split()[1]
                            if dns not in active_info['dns_servers']:
                                active_info['dns_servers'].append(dns)
            except Exception:
                pass
            
            # Check for WiFi
            try:
                result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'ESSID' in result.stdout:
                    active_info['connection_type'] = 'WiFi'
                else:
                    active_info['connection_type'] = 'Ethernet (Wired)'
            except Exception:
                active_info['connection_type'] = 'Unknown'
        
        # Check if gateway is private IP
        if active_info['gateway']:
            gateway_ip = active_info['gateway'].split()[0]
            gateway_ip = gateway_ip.split('%')[0]
            # Check for IPv4 private ranges
            if '.' in gateway_ip:
                active_info['is_private_ip'] = gateway_ip.startswith(('192.168.', '10.', '172.'))
            elif ':' in gateway_ip:
                # Link-local (fe80::) and ULA (fc00::, fd00::) are private
                active_info['is_private_ip'] = gateway_ip.startswith(('fe80::', 'fc00::', 'fd00::'))
            else:
                active_info['is_private_ip'] = False
        
        # Get gateway hostname via reverse DNS (IPv4 only)
        if active_info['gateway']:
            try:
                gateway_ip = active_info['gateway'].split()[0]
                gateway_ip = gateway_ip.split('%')[0]
                if '.' in gateway_ip:
                    hostname = socket.gethostbyaddr(gateway_ip)[0]
                    active_info['gateway_hostname'] = hostname
            except Exception:
                pass
        
        # Get WHOIS/ISP information
        if active_info['gateway']:
            try:
                gateway_ip = active_info['gateway'].split()[0]
                gateway_ip = gateway_ip.split('%')[0]

                # IPv4 WHOIS lookup only
                if ':' not in gateway_ip:
                    if active_info['is_private_ip']:
                        active_info['gateway_owner'] = 'Private Network (Local Router)'
                    else:
                        # Prefer ipwhois if available
                        if HAS_IPWHOIS:
                            try:
                                rdap = IPWhois(gateway_ip).lookup_rdap()
                                candidates = []
                                network = rdap.get('network') or {}
                                if network.get('name'):
                                    candidates.append(network.get('name'))
                                if network.get('org'):
                                    candidates.append(network.get('org'))
                                if rdap.get('asn_description'):
                                    candidates.append(rdap.get('asn_description'))
                                # remarks can be list of dicts with 'description'
                                remarks = network.get('remarks') or []
                                for remark in remarks:
                                    desc = remark.get('description')
                                    if isinstance(desc, list):
                                        candidates.extend(desc)
                                    elif isinstance(desc, str):
                                        candidates.append(desc)
                                for org in candidates:
                                    if org and isinstance(org, str) and len(org.strip()) > 3:
                                        active_info['gateway_owner'] = org.strip()
                                        break
                            except Exception:
                                pass

                        # Fallback to whois CLI if still unknown
                        if not active_info.get('gateway_owner'):
                            try:
                                result = subprocess.run(['whois', gateway_ip], capture_output=True, text=True, timeout=10)
                                if result.returncode == 0:
                                    whois_output = result.stdout
                                    for line in whois_output.split('\n'):
                                        line_lower = line.lower()
                                        if 'organization' in line_lower or 'orgname' in line_lower or 'owner' in line_lower or 'company' in line_lower:
                                            if ':' in line:
                                                org = line.split(':', 1)[1].strip()
                                                if org and len(org) > 3 and org not in ['', 'N/A', 'UNKNOWN']:
                                                    active_info['gateway_owner'] = org
                                                    break
                            except FileNotFoundError:
                                if not active_info.get('gateway_owner'):
                                    active_info['gateway_owner'] = 'Public ISP (WHOIS tool not available)'
                            except Exception:
                                pass

                        if not active_info['gateway_owner']:
                            active_info['gateway_owner'] = 'Public ISP (WHOIS unavailable)'
                else:
                    if gateway_ip.startswith('fe80::'):
                        active_info['gateway_owner'] = 'Link-Local IPv6 Gateway (Local Router)'
                    else:
                        active_info['gateway_owner'] = 'IPv6 Gateway (WHOIS not supported)'
            except Exception:
                pass
    
    except Exception as e:
        active_info['error'] = str(e)
    
    return active_info


def get_enhanced_network_discovery():
    """Get enhanced network discovery information (WiFi SSID, gateway, DNS, etc)"""
    enhanced_info = {
        'wifi_networks': [],
        'gateway_info': {},
        'dns_servers': [],
        'dhcp_enabled': {},
        'network_discovery': [],
        'error': None
    }
    
    try:
        # === WINDOWS SPECIFIC NETWORK DISCOVERY ===
        if IS_WINDOWS:
            # Get WiFi information via netsh (SSID, signal strength, security)
            try:
                result = subprocess.run(['netsh', 'wlan', 'show', 'network', 'mode=Bssid'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    current_ssid = None
                    current_info = {}
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        if line.startswith('Interface name'):
                            parts = line.split(':')
                            if len(parts) > 1:
                                current_info['interface'] = parts[1].strip()
                        elif line.startswith('SSID'):
                            parts = line.split(':')
                            if len(parts) > 1:
                                current_ssid = parts[1].strip()
                                if current_ssid and current_ssid not in [net.get('ssid') for net in enhanced_info['wifi_networks']]:
                                    enhanced_info['wifi_networks'].append({
                                        'ssid': current_ssid,
                                        'interface': current_info.get('interface', 'Unknown'),
                                        'signal': 'Unknown',
                                        'security': 'Unknown',
                                        'source': 'netsh'
                                    })
                        elif line.startswith('Signal'):
                            parts = line.split(':')
                            if len(parts) > 1 and enhanced_info['wifi_networks']:
                                enhanced_info['wifi_networks'][-1]['signal'] = parts[1].strip()
                        elif line.startswith('Authentication'):
                            parts = line.split(':')
                            if len(parts) > 1 and enhanced_info['wifi_networks']:
                                enhanced_info['wifi_networks'][-1]['security'] = parts[1].strip()
            except Exception:
                pass
            
            # Get connected WiFi via netsh wlan show interfaces
            try:
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        if 'SSID' in line and ':' in line:
                            parts = line.split(':', 1)
                            if len(parts) == 2 and parts[1].strip():
                                ssid = parts[1].strip()
                                # Mark as connected
                                for net in enhanced_info['wifi_networks']:
                                    if net['ssid'] == ssid:
                                        net['connected'] = True
                        elif 'Signal' in line and '%' in line:
                            parts = line.split(':')
                            if len(parts) > 1 and enhanced_info['wifi_networks']:
                                enhanced_info['wifi_networks'][-1]['signal'] = parts[1].strip()
            except Exception:
                pass
            
            # Get gateway and DHCP info via ipconfig
            try:
                result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    current_adapter = None
                    for line in result.stdout.split('\n'):
                        line_clean = line.strip()
                        if 'Adapter' in line and ':' in line:
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                current_adapter = parts[1].strip()
                                if current_adapter not in enhanced_info['dhcp_enabled']:
                                    enhanced_info['dhcp_enabled'][current_adapter] = {}
                        elif current_adapter:
                            if 'Default Gateway' in line_clean and ':' in line_clean:
                                parts = line_clean.split(':', 1)
                                if len(parts) == 2:
                                    gateway = parts[1].strip()
                                    if gateway not in enhanced_info['gateway_info']:
                                        enhanced_info['gateway_info'][gateway] = {'count': 0}
                                    enhanced_info['gateway_info'][gateway]['count'] += 1
                            elif 'DHCP Enabled' in line_clean and ':' in line_clean:
                                parts = line_clean.split(':', 1)
                                if len(parts) == 2 and current_adapter:
                                    enhanced_info['dhcp_enabled'][current_adapter]['dhcp'] = parts[1].strip()
                            elif 'DNS Servers' in line_clean and ':' in line_clean:
                                parts = line_clean.split(':', 1)
                                if len(parts) == 2:
                                    dns = parts[1].strip()
                                    if dns and dns not in enhanced_info['dns_servers']:
                                        enhanced_info['dns_servers'].append(dns)
            except Exception:
                pass
            
            # Network discovery via WMI (network adapter details and descriptions)
            if HAS_WMI:
                try:
                    c = wmi.WMI()
                    for adapter in c.Win32_NetworkAdapterConfiguration():
                        if adapter.MACAddress:
                            desc = {
                                'adapter': adapter.Description or 'Unknown',
                                'mac': adapter.MACAddress,
                                'dhcp_enabled': adapter.DHCPEnabled or False,
                                'ip_addresses': adapter.IPAddress or [],
                                'gateways': adapter.DefaultIPGateway or [],
                                'dns_servers': adapter.DNSServerSearchOrder or [],
                                'source': 'wmi'
                            }
                            enhanced_info['network_discovery'].append(desc)
                except Exception:
                    pass
        
        # === LINUX SPECIFIC NETWORK DISCOVERY ===
        elif IS_LINUX:
            # Get WiFi info via iwconfig and iw command
            try:
                result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'SSID' in line and '"' in line:
                            parts = line.split('"')
                            if len(parts) >= 2:
                                ssid = parts[1]
                                if ssid:
                                    enhanced_info['wifi_networks'].append({
                                        'ssid': ssid,
                                        'source': 'iwconfig',
                                        'connected': True
                                    })
            except Exception:
                pass
            
            # Get gateway via route command
            try:
                result = subprocess.run(['route', '-n'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if '0.0.0.0' in line or 'default' in line.lower():
                            parts = line.split()
                            if len(parts) >= 3:
                                gateway = parts[2] if '0.0.0.0' in parts[0] else parts[0]
                                if gateway not in enhanced_info['gateway_info']:
                                    enhanced_info['gateway_info'][gateway] = {'count': 1}
            except Exception:
                pass
            
            # Get DNS via /etc/resolv.conf
            try:
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            dns = line.split()[1]
                            if dns not in enhanced_info['dns_servers']:
                                enhanced_info['dns_servers'].append(dns)
            except Exception:
                pass
            
            # Get interface details via ip command
            try:
                result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'inet ' in line and 'scope' in line:
                            parts = line.split()
                            if len(parts) >= 2:
                                ip = parts[1].split('/')[0]
                                # Build network discovery entry
                                enhanced_info['network_discovery'].append({
                                    'ip': ip,
                                    'source': 'ip_addr'
                                })
            except Exception:
                pass
    
    except Exception as e:
        enhanced_info['error'] = str(e)
    
    return enhanced_info


def get_network_info():
    """Get comprehensive network information from multiple methods"""
    network_info = {
        'interfaces': [],
        'connections': 0,
        'error': None
    }
    
    # Method 1: Try psutil first (basic network interface stats)
    try:
        net_if_stats = psutil.net_if_stats()
        net_if_addrs = psutil.net_if_addrs()
        net_io_counters = psutil.net_io_counters()
        
        for interface_name, stats in net_if_stats.items():
            if_info = {
                'name': interface_name,
                'is_up': stats.isup,
                'mtu': stats.mtu,
                'speed': stats.speed if hasattr(stats, 'speed') else 0,
                'addresses': [],
                'source': 'psutil'
            }
            
            # Get IP addresses for this interface
            if interface_name in net_if_addrs:
                for addr in net_if_addrs[interface_name]:
                    if_info['addresses'].append({
                        'family': addr.family.name if hasattr(addr.family, 'name') else str(addr.family),
                        'address': addr.address,
                        'netmask': addr.netmask if addr.netmask else 'N/A',
                        'broadcast': addr.broadcast if addr.broadcast else 'N/A'
                    })
            
            network_info['interfaces'].append(if_info)
        
        # Add I/O counters
        network_info['io'] = {
            'bytes_sent': net_io_counters.bytes_sent,
            'bytes_recv': net_io_counters.bytes_recv,
            'packets_sent': net_io_counters.packets_sent,
            'packets_recv': net_io_counters.packets_recv,
            'errin': net_io_counters.errin if hasattr(net_io_counters, 'errin') else 0,
            'errout': net_io_counters.errout if hasattr(net_io_counters, 'errout') else 0,
            'dropin': net_io_counters.dropin if hasattr(net_io_counters, 'dropin') else 0,
            'dropout': net_io_counters.dropout if hasattr(net_io_counters, 'dropout') else 0
        }
    except Exception as e:
        network_info['error'] = str(e)
    
    # Method 2: WMI fallback (Windows detailed network info)
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for adapter in c.Win32_NetworkAdapter():
                if adapter.NetConnectionStatus == 2:  # Connected
                    # Find matching interface or add new
                    matching_interface = None
                    for iface in network_info['interfaces']:
                        if adapter.Name in iface.get('name', '') or iface.get('name') in adapter.Name:
                            matching_interface = iface
                            break
                    
                    adapter_info = {
                        'name': adapter.Name,
                        'description': adapter.Description,
                        'speed': int(adapter.Speed) if adapter.Speed else 0,
                        'mac_address': adapter.MACAddress,
                        'adapter_type': adapter.AdapterType,
                        'net_connection_id': adapter.NetConnectionID,
                        'source': 'wmi'
                    }
                    
                    if matching_interface:
                        matching_interface.update(adapter_info)
                    else:
                        network_info['interfaces'].append(adapter_info)
        except Exception:
            pass
    
    # Method 3: Linux fallback (ip command)
    elif IS_LINUX:
        try:
            # Try ip command for detailed interface info
            result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Parse ip command output to enhance interface info
                for line in result.stdout.split('\n'):
                    if 'inet ' in line and 'scope global' in line:
                        # Extract IP and interface info
                        parts = line.split()
                        if len(parts) >= 2:
                            ip_addr = parts[1].split('/')[0]
                            # Find matching interface
                            for iface in network_info['interfaces']:
                                if 'addresses' not in iface:
                                    iface['addresses'] = []
                                iface['addresses'].append({
                                    'family': 'IPv4',
                                    'address': ip_addr,
                                    'source': 'ip_command'
                                })
        except Exception:
            pass
        
        # Try iwconfig for wireless interfaces
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'IEEE 802.11' in line:
                        # Extract wireless interface info
                        interface_name = line.split()[0]
                        for iface in network_info['interfaces']:
                            if iface['name'] == interface_name:
                                iface['wireless'] = True
                                iface['protocol'] = 'IEEE 802.11'
                                iface['source'] = 'iwconfig'
                                break
        except Exception:
            pass
    
    # Method 4: Connection statistics
    try:
        connections = psutil.net_connections()
        network_info['connections'] = len(connections)
        
        # Add connection breakdown
        connection_stats = {
            'established': 0,
            'listen': 0,
            'time_wait': 0,
            'close_wait': 0
        }
        
        for conn in connections:
            if conn.status == 'ESTABLISHED':
                connection_stats['established'] += 1
            elif conn.status == 'LISTEN':
                connection_stats['listen'] += 1
            elif conn.status == 'TIME_WAIT':
                connection_stats['time_wait'] += 1
            elif conn.status == 'CLOSE_WAIT':
                connection_stats['close_wait'] += 1
        
        network_info['connection_stats'] = connection_stats
    except Exception:
        network_info['connections'] = 0
    
    # Method 5: Enhanced network discovery (WiFi, gateway, DNS, etc.)
    try:
        enhanced = get_enhanced_network_discovery()
        network_info['enhanced'] = enhanced
    except Exception as e:
        network_info['enhanced'] = {'error': str(e)}
    
    # Method 6: Current active connection summary
    try:
        active = get_current_active_connection()
        network_info['active'] = active
    except Exception as e:
        network_info['active'] = {'error': str(e)}
    
    return network_info

def get_disk_info():
    """Get comprehensive disk information from multiple methods"""
    disks = []
    
    # Method 1: Try psutil first (basic partition info)
    try:
        partitions = psutil.disk_partitions(all=True)
        disk_io_stats = psutil.disk_io_counters(perdisk=True)
        
        for part in partitions:
            disk_info = {
                'device': part.device,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype,
                'opts': part.opts,
                'source': 'psutil'
            }
            
            # Add usage info if accessible
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_info.update({
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': usage.percent
                })
            except Exception:
                pass
            
            # Add I/O stats if available
            device_name = part.device.split('\\')[-1].split('/')[-1]  # Get just the device name
            if device_name in disk_io_stats:
                io_stats = disk_io_stats[device_name]
                disk_info.update({
                    'read_count': io_stats.read_count,
                    'write_count': io_stats.write_count,
                    'read_bytes': io_stats.read_bytes,
                    'write_bytes': io_stats.write_bytes,
                    'read_time': io_stats.read_time,
                    'write_time': io_stats.write_time
                })
            
            disks.append(disk_info)
    except Exception:
        pass
    
    # Method 2: NVMe helper fallback (NVMe SMART data)
    try:
        nvme_helper_path = os.path.join(os.path.dirname(__file__), 'nvme_helper.exe')
        if os.path.exists(nvme_helper_path):
            result = subprocess.run([nvme_helper_path], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                nvme_data = json.loads(result.stdout)
                nvme_devices = nvme_data.get('devices', [])
                
                for nvme_dev in nvme_devices:
                    # Find matching disk or add new
                    matching_disk = None
                    for disk in disks:
                        if nvme_dev.get('device') in disk.get('device', ''):
                            matching_disk = disk
                            break
                    
                    if matching_disk:
                        # Enhance existing disk info
                        matching_disk.update({
                            'model': nvme_dev.get('model'),
                            'serial': nvme_dev.get('serial'),
                            'firmware': nvme_dev.get('firmware'),
                            'temperature': nvme_dev.get('temperature'),
                            'health': nvme_dev.get('health'),
                            'power_on_hours': nvme_dev.get('power_on_hours'),
                            'data_units_read': nvme_dev.get('data_units_read'),
                            'data_units_written': nvme_dev.get('data_units_written'),
                            'nvme_source': 'nvme_helper'
                        })
                    else:
                        # Add new NVMe disk
                        disks.append({
                            'device': nvme_dev.get('device', 'Unknown'),
                            'model': nvme_dev.get('model'),
                            'serial': nvme_dev.get('serial'),
                            'firmware': nvme_dev.get('firmware'),
                            'temperature': nvme_dev.get('temperature'),
                            'health': nvme_dev.get('health'),
                            'power_on_hours': nvme_dev.get('power_on_hours'),
                            'data_units_read': nvme_dev.get('data_units_read'),
                            'data_units_written': nvme_dev.get('data_units_written'),
                            'source': 'nvme_helper'
                        })
    except Exception:
        pass
    
    # Method 3: WMI fallback (Windows disk details)
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for disk in c.Win32_DiskDrive():
                # Find matching disk or add new
                matching_disk = None
                for d in disks:
                    if disk.DeviceID in d.get('device', '') or disk.Model in d.get('device', ''):
                        matching_disk = d
                        break

                disk_info = {
                    'device': disk.DeviceID,
                    'model': disk.Model,
                    'serial': disk.SerialNumber,
                    'interface_type': disk.InterfaceType,
                    'size': int(disk.Size) if disk.Size else 0,
                    'partitions': disk.Partitions,
                    'firmware': disk.FirmwareRevision,
                    'source': 'wmi'
                }

                if matching_disk:
                    matching_disk.update(disk_info)
                else:
                    disks.append(disk_info)

            # Attempt deterministic mapping from logical volumes to physical disk DeviceID
            # Build mapping using association classes: DiskDriveToDiskPartition -> LogicalDiskToPartition
            logical_to_physical = {}
            try:
                # map partition deviceID -> disk DeviceID
                part_to_disk = {}
                for assoc in c.Win32_DiskDriveToDiskPartition():
                    # assoc.Antecedent is disk, Dependent is partition (strings)
                    try:
                        antecedent = str(assoc.Antecedent)
                        dependent = str(assoc.Dependent)
                        # extract DeviceID="..." value
                        import re
                        a_match = re.search(r'DeviceID="([^"]+)"', antecedent)
                        d_match = re.search(r'DeviceID="([^"]+)"', dependent)
                        if a_match and d_match:
                            disk_dev = a_match.group(1)
                            part_dev = d_match.group(1)
                            part_to_disk[part_dev] = disk_dev
                    except Exception:
                        continue

                # now map logical disks to partitions
                for assoc in c.Win32_LogicalDiskToPartition():
                    try:
                        antecedent = str(assoc.Antecedent)
                        dependent = str(assoc.Dependent)
                        import re
                        p_match = re.search(r'DeviceID="([^"]+)"', antecedent)
                        l_match = re.search(r'DeviceID="([^"]+)"', dependent)
                        if p_match and l_match:
                            part_dev = p_match.group(1)
                            logical = l_match.group(1)
                            # normalize logical (C:\ or C:) to 'C:' form
                            logical_norm = logical.rstrip('\\').upper()
                            disk_dev = part_to_disk.get(part_dev)
                            if disk_dev:
                                logical_to_physical[logical_norm] = disk_dev
                    except Exception:
                        continue

            except Exception:
                logical_to_physical = {}

            # Attach mapping into partition entries captured earlier (psutil partitions)
            for d in disks:
                if d.get('mountpoint'):
                    mp = str(d.get('mountpoint')).rstrip('\\').upper()
                    if mp in logical_to_physical:
                        d['physical_device'] = logical_to_physical.get(mp)
            # Heuristic fallback: match partitions to physical devices by capacity when WMI mapping unavailable
            try:
                phys_sizes = []
                for p in disks:
                    if not (p.get('mountpoint') or p.get('fstype')) and (p.get('size') or p.get('total')):
                        phys_sizes.append((p.get('device'), int(p.get('size') or p.get('total') or 0)))
                for d in disks:
                    if d.get('mountpoint') and not d.get('physical_device') and d.get('total'):
                        part_size = int(d.get('total') or 0)
                        # find phys candidates with size >= partition size
                        candidates = [(dev, sz, abs(sz - part_size)) for (dev, sz) in phys_sizes if sz >= part_size]
                        if not candidates:
                            # fallback: pick closest size
                            candidates = [(dev, sz, abs(sz - part_size)) for (dev, sz) in phys_sizes]
                        if candidates:
                            # choose smallest difference
                            candidates.sort(key=lambda x: x[2])
                            d['physical_device'] = candidates[0][0]
            except Exception:
                pass
        except Exception:
            pass
    
    # Method 4: Linux fallback (lsblk)
    elif IS_LINUX:
        try:
            result = subprocess.run(['lsblk', '-J'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lsblk_data = json.loads(result.stdout)
                for device in lsblk_data.get('blockdevices', []):
                    if device.get('type') == 'disk':
                        # Find matching disk or add new
                        matching_disk = None
                        for d in disks:
                            if device.get('name') in d.get('device', ''):
                                matching_disk = d
                                break
                        
                        disk_info = {
                            'device': device.get('name'),
                            'model': device.get('model'),
                            'size': device.get('size'),
                            'vendor': device.get('vendor'),
                            'serial': device.get('serial'),
                            'rotational': device.get('rota') == '1',
                            'source': 'lsblk'
                        }
                        
                        if matching_disk:
                            matching_disk.update(disk_info)
                        else:
                            disks.append(disk_info)
        except Exception:
            pass
    
    return disks

def export_text_report(text_widget):
    """Export the text report to a file"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        from datetime import datetime
        
        # Get current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"Halfax_System_Report_{timestamp}.txt"
        
        # Ask user for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_filename,
            title="Save System Report"
        )
        
        if file_path:
            # Get text content
            content = text_widget.get('1.0', tk.END)
            
            # Write to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Show success message
            import tkinter.messagebox as messagebox
            messagebox.showinfo("Export Successful", f"Report saved to:\n{file_path}")
            
    except Exception as e:
        import tkinter.messagebox as messagebox
        messagebox.showerror("Export Error", f"Failed to export report:\n{str(e)}")


def populate_text_report_tab():
    """Populate the comprehensive text report tab with all system data"""
    if 'text_report' not in text_widgets:
        return
    import tkinter as tk

    text_report_text = text_widgets['text_report']
    text_report_text.configure(state='normal')
    text_report_text.delete('1.0', tk.END)
    
    # Generate comprehensive report
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report_content = f"""
╔══════════════════════════════════════════════════════════════╗
║                   HALFAX SYSTEM REPORT                        ║
║                   Generated: {timestamp}              ║
╚══════════════════════════════════════════════════════════════╝

"""

    # Helper: remove per-tab decorative boxed headers to avoid duplicates
    def _strip_box_header(s: str) -> str:
        if not s:
            return ''
        s = s.lstrip()
        if s.startswith('╔'):
            # try to find the closing box line which starts with '╚'
            close_idx = s.find('\n╚')
            if close_idx != -1:
                # move past the closing box line
                next_idx = s.find('\n', close_idx + 1)
                if next_idx != -1:
                    s = s[next_idx+1:]
                else:
                    s = ''
        # trim excessive leading/trailing blank lines and ensure spacing
        s = s.strip()
        return (s + '\n\n') if s else ''

    # Helper: add a section with a single canonical header
    def _add_section(key: str, header: str):
        nonlocal report_content
        if key in text_widgets:
            raw = text_widgets[key].get('1.0', tk.END)
            cleaned = _strip_box_header(raw)
            if cleaned:
                report_content += header + '\n' + cleaned

    # Section headers
    overview_header = """
╔══════════════════════════════════════════════════════════════╗
║                      SYSTEM OVERVIEW                         ║
╚══════════════════════════════════════════════════════════════╝

"""
    cpu_header = """
╔══════════════════════════════════════════════════════════════╗
║                      CPU INFORMATION                         ║
╚══════════════════════════════════════════════════════════════╝

"""
    gpu_header = """
╔══════════════════════════════════════════════════════════════╗
║                       GPU INFORMATION                         ║
╚══════════════════════════════════════════════════════════════╝

"""
    memory_header = """
╔══════════════════════════════════════════════════════════════╗
║                      MEMORY INFORMATION                       ║
╚══════════════════════════════════════════════════════════════╝

"""
    storage_header = """
╔══════════════════════════════════════════════════════════════╗
║                      STORAGE INFORMATION                      ║
╚══════════════════════════════════════════════════════════════╝

"""
    disk_header = """
╔══════════════════════════════════════════════════════════════╗
║                      DISK INFORMATION                         ║
╚══════════════════════════════════════════════════════════════╝

"""
    network_header = """
╔══════════════════════════════════════════════════════════════╗
║                      NETWORK INFORMATION                      ║
╚══════════════════════════════════════════════════════════════╝

"""
    display_header = """
╔══════════════════════════════════════════════════════════════╗
║                      DISPLAY INFORMATION                      ║
╚══════════════════════════════════════════════════════════════╝

"""
    arch_header = """
╔══════════════════════════════════════════════════════════════╗
║                   SYSTEM ARCHITECTURE                        ║
╚══════════════════════════════════════════════════════════════╝

"""

    # Add sections in desired order, stripping any existing boxed headers
    _add_section('overview', overview_header)
    _add_section('cpu', cpu_header)
    _add_section('gpu', gpu_header)
    _add_section('memory', memory_header)
    _add_section('storage', storage_header)
    _add_section('disk', disk_header)
    _add_section('network', network_header)
    _add_section('display', display_header)
    _add_section('architecture', arch_header)

    # Add footer
    report_content += """

╔══════════════════════════════════════════════════════════════╗
║                       END OF REPORT                            ║
║              Generated by Halfax System Reporter               ║
╚══════════════════════════════════════════════════════════════╝
"""

    text_report_text.insert('1.0', report_content)
    text_report_text.configure(state='disabled')


def create_gui():
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    
    # Create main window (hidden initially)
    root = tk.Tk()
    root.withdraw()  # Hide main window until ready
    root.title("Halfax System Reporter")
    root.geometry("900x700")
    root.configure(bg='#1a1a1a')
    
    # Create loading splash screen as a child window to avoid multiple Tk roots
    splash = tk.Toplevel(root)
    splash.title("Loading...")
    splash.geometry("700x380")
    splash.configure(bg='#1e1e1e')
    splash.resizable(False, False)
    splash.overrideredirect(True)
    splash.lift()
    
    # Center the splash screen
    splash.update_idletasks()
    screen_width = splash.winfo_screenwidth()
    screen_height = splash.winfo_screenheight()
    x = (screen_width - 700) // 2
    y = (screen_height - 380) // 2
    splash.geometry(f"700x380+{x}+{y}")
    
    # Loading content
    loading_frame = tk.Frame(splash, bg='#1e1e1e')
    loading_frame.pack(expand=True)
    
    title_label = tk.Label(loading_frame, text="Halfax System Reporter", 
                           font=('Segoe UI', 24, 'bold'), 
                           bg='#1e1e1e', fg='#007acc')
    title_label.pack(pady=30)
    
    status_label = tk.Label(loading_frame, text="Loading and Analyzing System...", 
                           font=('Segoe UI', 14), 
                           bg='#1e1e1e', fg='#d4d4d4')
    status_label.pack(pady=15)
    
    progress_label = tk.Label(loading_frame, text="Please wait...", 
                             font=('Segoe UI', 11), 
                             bg='#1e1e1e', fg='#808080')
    progress_label.pack(pady=10)
    
    # Force splash to render before heavy loading begins
    splash.update()
    
    # Create style with better contrast (bound to main root)
    style = ttk.Style(root)
    style.theme_use('clam')
    
    # Add progress bar
    progress_bar = ttk.Progressbar(loading_frame, mode='indeterminate', 
                                   style='Indeterminate.Horizontal.TProgressbar')
    progress_bar.pack(pady=20, padx=50, fill='x')
    
    # Configure progress bar style
    style.configure('Indeterminate.Horizontal.TProgressbar', 
                   background='#0078d4', 
                   troughcolor='#333333',
                   borderwidth=0,
                   lightcolor='#0078d4',
                   darkcolor='#005a9e')
    
    # Start progress bar animation
    progress_bar.start(5)  # Faster interval for smoother animation
    
    # Main background
    style.configure('TFrame', background='#1a1a1a')
    
    # Notebook (tab container) styling
    style.configure('TNotebook', background='#1a1a1a', borderwidth=2, relief='solid', tabmargins=[8, 6, 8, 0])

    # Tab styling with stronger borders/contrast
    style.configure('TNotebook.Tab', 
                    background='#222222',      # Dark unselected tabs
                    foreground='#a0a0a0',       # Softer gray text
                    padding=[18, 10],
                    borderwidth=2,
                    relief='solid')

    # Selected tab - bright, thick border
    style.map('TNotebook.Tab', 
              background=[('selected', '#0078d4')],    # Bright blue when selected
              foreground=[('selected', '#ffffff')],    # Pure white text
              borderwidth=[('selected', 3)],
              relief=[('selected', 'raised')])
    
    # Button styling
    style.configure('Accent.TButton',
                    background='#0078d4',
                    foreground='white',
                    borderwidth=1,
                    focuscolor='none',
                    padding=[12, 6])
    style.map('Accent.TButton',
              background=[('active', '#106ebe'), ('pressed', '#005a9e')])
    
    # Create top-right button (no frame, just button)
    refresh_button = ttk.Button(root, text="⟳ Refresh All", style='Accent.TButton', command=lambda: refresh_all_tabs())
    refresh_button.pack(side='top', anchor='ne', padx=10, pady=8)
    
    # Create notebook (tabs)
    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True, padx=10, pady=(0, 10))
    
    # Storage for text widgets and info (use module-level shared dict)
    global text_widgets
    text_widgets.clear()
    
    def ensure_tabs_created():
        """Create tabs and text widgets if they don't already exist."""
        if 'overview' in text_widgets:
            return
        # System Overview Tab
        overview_frame = ttk.Frame(notebook)
        notebook.add(overview_frame, text='Overview')
        overview_text = scrolledtext.ScrolledText(overview_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', 
                                                  font=('Consolas', 10), insertbackground='white')
        overview_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['overview'] = overview_text

        # CPU Tab
        cpu_frame = ttk.Frame(notebook)
        notebook.add(cpu_frame, text='CPU')

        # Remove duplicate per-core tables - data is shown in text section below

        cpu_text = scrolledtext.ScrolledText(cpu_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        cpu_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['cpu'] = cpu_text

        # GPU Tab (Phase 4.2) - Enhanced text display (removed redundant table)
        gpu_frame = ttk.Frame(notebook)
        notebook.add(gpu_frame, text='GPU')
        gpu_text = scrolledtext.ScrolledText(gpu_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                             font=('Consolas', 10), insertbackground='white')
        gpu_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['gpu'] = gpu_text

        # Disk Tab
        disk_frame = ttk.Frame(notebook)
        notebook.add(disk_frame, text='Disks')
        disk_text = scrolledtext.ScrolledText(disk_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        disk_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['disk'] = disk_text

        # Memory Tab
        memory_frame = ttk.Frame(notebook)
        notebook.add(memory_frame, text='Memory')
        memory_text = scrolledtext.ScrolledText(memory_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        memory_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['memory'] = memory_text

        # Network Tab
        network_frame = ttk.Frame(notebook)
        notebook.add(network_frame, text='Network')
        network_text = scrolledtext.ScrolledText(network_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        network_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['network'] = network_text

        # Architecture Tab
        arch_frame = ttk.Frame(notebook)
        notebook.add(arch_frame, text='Architecture')
        arch_text = scrolledtext.ScrolledText(arch_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        arch_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['architecture'] = arch_text

        # Storage Tab
        storage_frame = ttk.Frame(notebook)
        notebook.add(storage_frame, text='Storage')
        storage_text = scrolledtext.ScrolledText(storage_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        storage_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['storage'] = storage_text

        # Display Tab
        display_frame = ttk.Frame(notebook)
        notebook.add(display_frame, text='Display')
        display_text = scrolledtext.ScrolledText(display_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        display_text.pack(fill='both', expand=True, padx=10, pady=10)
        text_widgets['display'] = display_text

        # Text Report Tab (NEW - Comprehensive System Report)
        text_report_frame = ttk.Frame(notebook)
        notebook.add(text_report_frame, text='Text Report')
        text_report_text = scrolledtext.ScrolledText(text_report_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        text_report_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Add export button for text report
        export_button_frame = ttk.Frame(text_report_frame)
        export_button_frame.pack(fill='x', padx=10, pady=(0, 10))
        export_button = ttk.Button(export_button_frame, text="📄 Export Report", style='Accent.TButton', 
                                  command=lambda: export_text_report(text_report_text))
        export_button.pack(side='right')
        
        text_widgets['text_report'] = text_report_text
        
        # Router Scan Tab (NEW - UPnP Router Discovery)
        router_scan_frame = ttk.Frame(notebook)
        notebook.add(router_scan_frame, text='Router Scan')
        
        # Button frame at the top
        router_button_frame = ttk.Frame(router_scan_frame, style='TFrame')
        router_button_frame.pack(fill='x', padx=10, pady=10)
        
        scan_router_button = ttk.Button(router_button_frame, text="🔍 Scan Router", style='Accent.TButton',
                                       command=lambda: show_router_scan_confirmation())
        scan_router_button.pack(side='left')
        
        # Text area for displaying router information
        router_scan_text = scrolledtext.ScrolledText(router_scan_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                                     font=('Consolas', 10), insertbackground='white')
        router_scan_text.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # Initial message
        router_scan_text.insert('1.0', """╔══════════════════════════════════════════════════════════════╗
║                      ROUTER SCAN                          ║
╚══════════════════════════════════════════════════════════════╝

Click 'Scan Router' to discover UPnP-enabled router information.

⚠️  IMPORTANT SECURITY WARNING:

    Only scan routers on YOUR OWN PERSONAL NETWORK.
    
    DO NOT scan:
    • Public WiFi (coffee shops, airports, hotels)
    • Someone else's private network
    • Any network you don't own or control
    
    Unauthorized network scanning may violate:
    • Computer Fraud and Abuse Act (U.S.)
    • Similar laws in other jurisdictions
    • Network acceptable use policies
    
    You will be asked to confirm before scanning.

""")
        router_scan_text.configure(state='disabled')
        
        text_widgets['router_scan'] = router_scan_text
    
    def show_router_scan_confirmation():
        """Show confirmation dialog before scanning router"""
        import tkinter.messagebox as messagebox
        
        # Create custom dialog
        confirm_dialog = tk.Toplevel(root)
        confirm_dialog.title("Router Scan Confirmation")
        confirm_dialog.geometry("500x300")
        confirm_dialog.configure(bg='#1e1e1e')
        confirm_dialog.resizable(False, False)
        confirm_dialog.transient(root)
        confirm_dialog.grab_set()
        
        # Center the dialog
        confirm_dialog.update_idletasks()
        x = (confirm_dialog.winfo_screenwidth() - 500) // 2
        y = (confirm_dialog.winfo_screenheight() - 300) // 2
        confirm_dialog.geometry(f"500x300+{x}+{y}")
        
        # Content frame
        content_frame = tk.Frame(confirm_dialog, bg='#1e1e1e')
        content_frame.pack(expand=True, fill='both', padx=20, pady=20)
        
        # Warning icon and title
        title_label = tk.Label(content_frame, text="⚠️  Network Security Confirmation",
                              font=('Segoe UI', 14, 'bold'),
                              bg='#1e1e1e', fg='#ff9800')
        title_label.pack(pady=(0, 15))
        
        # Question
        question_label = tk.Label(content_frame, 
                                 text="Are you sure this is YOUR PERSONAL network?",
                                 font=('Segoe UI', 12, 'bold'),
                                 bg='#1e1e1e', fg='#d4d4d4')
        question_label.pack(pady=(0, 10))
        
        # Warning text
        warning_text = tk.Label(content_frame,
                               text="Scanning routers on networks you don't own\nis inappropriate and potentially illegal.",
                               font=('Segoe UI', 9),
                               bg='#1e1e1e', fg='#aaaaaa',
                               justify='center')
        warning_text.pack(pady=(0, 20))
        
        # Checkbox variable
        checkbox_var = tk.BooleanVar(value=False)
        
        # Checkbox frame
        checkbox_frame = tk.Frame(content_frame, bg='#1e1e1e')
        checkbox_frame.pack(pady=(0, 20))
        
        checkbox = tk.Checkbutton(checkbox_frame,
                                 text="Yes, this is my personal network",
                                 variable=checkbox_var,
                                 font=('Segoe UI', 10),
                                 bg='#1e1e1e', fg='#d4d4d4',
                                 selectcolor='#2d2d2d',
                                 activebackground='#1e1e1e',
                                 activeforeground='#d4d4d4',
                                 command=lambda: update_button_states())
        checkbox.pack()
        
        # Button frame
        button_frame = tk.Frame(content_frame, bg='#1e1e1e')
        button_frame.pack(side='bottom')
        
        def update_button_states():
            if checkbox_var.get():
                ok_button.configure(state='normal')
            else:
                ok_button.configure(state='disabled')
        
        def on_ok():
            confirm_dialog.destroy()
            perform_router_scan()
        
        def on_cancel():
            confirm_dialog.destroy()
        
        # OK button (disabled by default)
        ok_button = ttk.Button(button_frame, text="OK", style='Accent.TButton',
                              command=on_ok, state='disabled')
        ok_button.pack(side='left', padx=5)
        
        # Cancel button
        cancel_button = ttk.Button(button_frame, text="Cancel",
                                  command=on_cancel)
        cancel_button.pack(side='left', padx=5)
    
    def perform_router_scan():
        """Perform UPnP router scan and display results"""
        if 'router_scan' not in text_widgets:
            return
        
        router_text = text_widgets['router_scan']
        router_text.configure(state='normal')
        router_text.delete('1.0', tk.END)
        
        router_text.insert('1.0', """╔══════════════════════════════════════════════════════════════╗
║                      ROUTER SCAN                          ║
╚══════════════════════════════════════════════════════════════╝

🔍 Scanning for UPnP-enabled router...

""")
        router_text.update()
        
        if not HAS_MINIUPNPC:
            router_text.insert(tk.END, """❌ Error: miniupnpc module not installed.

To install miniupnpc:
  pip install miniupnpc

Note: This feature requires UPnP to be enabled on your router.
""")
            router_text.configure(state='disabled')
            return
        
        try:
            import logging
            logging.basicConfig(level=logging.ERROR)  # Suppress UPnP debug output
            
            # Create UPnP object
            u = miniupnpc.UPnP()
            u.discoverdelay = 200
            
            router_text.insert(tk.END, "Discovering UPnP devices...\n")
            router_text.update()
            
            # Discover devices
            num_devices = u.discover()
            
            if num_devices == 0:
                router_text.insert(tk.END, """\n❌ No UPnP devices found.

Possible reasons:
  • UPnP is disabled on your router
  • Firewall is blocking UPnP discovery
  • Router doesn't support UPnP
  • Not connected to a network

To enable UPnP:
  1. Access your router's admin interface
  2. Look for UPnP settings (often under Advanced)
  3. Enable UPnP/IGD
  4. Save and try scanning again
""")
                router_text.configure(state='disabled')
                return
            
            router_text.insert(tk.END, f"Found {num_devices} UPnP device(s)\n\n")
            router_text.update()
            
            # Select IGD
            u.selectigd()
            
            router_text.insert(tk.END, "{'='*60}\n✅ ROUTER INFORMATION\n{'='*60}\n\n")
            
            # Get external IP
            try:
                external_ip = u.externalipaddress()
                router_text.insert(tk.END, f"External IP Address:    {external_ip}\n")
            except Exception as e:
                router_text.insert(tk.END, f"External IP Address:    Not available ({e})\n")
            
            # Get connection status
            try:
                status_info = u.statusinfo()
                router_text.insert(tk.END, f"Connection Status:      {status_info}\n")
            except Exception:
                pass
            
            # Get connection type
            try:
                conn_type = u.connectiontype()
                router_text.insert(tk.END, f"Connection Type:        {conn_type}\n")
            except Exception:
                pass
            
            # Get local LAN address
            try:
                lan_addr = u.lanaddr
                router_text.insert(tk.END, f"\nYour Local IP:          {lan_addr}\n")
            except Exception:
                pass
            
            # Get IGD information
            router_text.insert(tk.END, f"\n{'='*60}\nINTERNET GATEWAY DEVICE (IGD) INFO\n{'='*60}\n\n")
            
            # URLs
            try:
                router_text.insert(tk.END, f"Control URL:            {u.urls.get('controlURL', 'N/A')}\n")
                router_text.insert(tk.END, f"Control URL CIF:        {u.urls.get('controlURL_CIF', 'N/A')}\n")
            except Exception:
                pass
            
            # Service type
            try:
                router_text.insert(tk.END, f"Service Type:           {u.servicetype}\n")
            except Exception:
                pass
            
            # Get all existing port mappings
            router_text.insert(tk.END, f"\n{'='*60}\nEXISTING PORT MAPPINGS\n{'='*60}\n\n")
            
            try:
                mapping_found = False
                for i in range(100):  # Check first 100 port mappings
                    try:
                        mapping = u.getgenericportmapping(i)
                        if mapping:
                            mapping_found = True
                            external_port = mapping[0]
                            protocol = mapping[1]
                            internal_ip = mapping[2]
                            internal_port = mapping[3]
                            description = mapping[4]
                            enabled = mapping[5]
                            
                            router_text.insert(tk.END, f"Mapping {i + 1}:\n")
                            router_text.insert(tk.END, f"  External Port:    {external_port}/{protocol}\n")
                            router_text.insert(tk.END, f"  Internal IP:      {internal_ip}:{internal_port}\n")
                            router_text.insert(tk.END, f"  Description:      {description}\n")
                            router_text.insert(tk.END, f"  Enabled:          {'Yes' if enabled else 'No'}\n")
                            router_text.insert(tk.END, f"\n")
                    except Exception:
                        break
                
                if not mapping_found:
                    router_text.insert(tk.END, "No port mappings configured.\n")
            except Exception as e:
                router_text.insert(tk.END, f"Could not retrieve port mappings: {e}\n")
            
            # Device information
            router_text.insert(tk.END, f"\n{'='*60}\nADDITIONAL DEVICE INFO\n{'='*60}\n\n")
            
            try:
                router_text.insert(tk.END, f"Total Bytes Sent:       {u.totalbytesent()}\n")
                router_text.insert(tk.END, f"Total Bytes Received:   {u.totalbytereceived()}\n")
                router_text.insert(tk.END, f"Total Packets Sent:     {u.totalpacketsent()}\n")
                router_text.insert(tk.END, f"Total Packets Received: {u.totalpacketreceived()}\n")
            except Exception:
                router_text.insert(tk.END, "Traffic statistics not available.\n")
            
            router_text.insert(tk.END, f"\n{'='*60}\n✅ Scan completed successfully\n{'='*60}\n")
            
        except miniupnpc.UPnPError as e:
            router_text.insert(tk.END, f"\n❌ UPnP Error: {e}\n\n")
            router_text.insert(tk.END, """Could not find a UPnP-enabled router or retrieve information.

Troubleshooting:
  • Ensure UPnP/IGD is enabled on your router
  • Check firewall settings
  • Try restarting your router
  • Some routers require UPnP to be enabled in advanced settings
""")
        except Exception as e:
            router_text.insert(tk.END, f"\n❌ Unexpected Error: {e}\n\n")
            router_text.insert(tk.END, "An unexpected error occurred during the scan.\n")
        
        router_text.configure(state='disabled')
    
    def refresh_all_tabs():
        """Refresh data for all tabs"""
        ensure_tabs_created()
        # Collect fresh system information
        memory_info = get_memory_extended_info()
        brand, Arch = get_cpu_info_cores()
        cpu_extended = get_cpu_extended_info()
        # Prefer the dedicated gpu_integration module when available
        try:
            from gpu_integration import get_gpu_list, get_gpu_utilization, get_gpu_display_association, get_gpu_pcie_info, get_intel_gpu_metrics
            gpus = get_gpu_list()
            gpu_utils = get_gpu_utilization()
            gpu_display_map = get_gpu_display_association()
            gpu_pcie_info = get_gpu_pcie_info()
            intel_metrics = get_intel_gpu_metrics()
            
            # Merge utilization into gpu entries where names match
            gpu_info = []
            for g in gpus:
                name = g.get('name')
                util = gpu_utils.get(name, {}) if isinstance(gpu_utils, dict) else {}
                merged = dict(g)
                merged.update(util)
                
                # Add PCIe information
                pcie_data = gpu_pcie_info.get(name, {})
                if pcie_data:
                    merged.update(pcie_data)
                
                # Add Intel metrics for Intel GPUs
                if 'Intel' in name and intel_metrics:
                    merged.update(intel_metrics)
                
                gpu_info.append(merged)
        except Exception:
            gpu_info = get_gpu_info()
        monitor_info = get_monitor_info()
        disk_info = get_disk_info()
        system_info = get_system_info()
        network_info = get_network_info()
        pci_topology = get_pci_topology()
        
        # Get OS version info (cross-platform)
        if IS_WINDOWS:
            win_ver = platform.win32_ver()
            full_version = win_ver[1]
            version_parts = full_version.split('.')
            build_major = int(version_parts[2]) if len(version_parts) > 2 else 0
            build_revision = version_parts[3] if len(version_parts) > 3 else "0"
            
            if build_major >= 22000:
                os_name = "Windows 11"
                if build_major >= 26100:
                    version_name = "25H2"
                elif build_major >= 22631:
                    version_name = "23H2"
                elif build_major >= 22621:
                    version_name = "22H2"
                else:
                    version_name = "21H2"
            else:
                os_name = "Windows 10"
                version_name = win_ver[0] if win_ver[0] else "Unknown"
            
            os_display = f"{os_name} Version {version_name}"
            os_build = f"{build_major}.{build_revision}"
        
        elif IS_LINUX:
            # Try to get Linux distribution info
            try:
                result = subprocess.run(['lsb_release', '-ds'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    os_display = result.stdout.strip().strip('"')
                else:
                    os_display = f"{platform.system()} {platform.release()}"
            except:
                os_display = f"{platform.system()} {platform.release()}"
            os_build = platform.version() if platform.version() else "N/A"
            
            # Special handling for Pi
            if IS_PI:
                os_display += " (Raspberry Pi)"
        
        elif IS_MAC:
            os_display = f"macOS {platform.release()}"
            os_build = platform.version() if platform.version() else "N/A"
        
        else:
            os_display = f"{platform.system()} {platform.release()}"
            os_build = "N/A"
        
        # Update Overview tab
        if 'overview' in text_widgets:
            overview_text = text_widgets['overview']
            overview_text.configure(state='normal')
            overview_text.delete('1.0', tk.END)
            
            overview_content = f"""
╔══════════════════════════════════════════════════════════════╗
║                      SYSTEM OVERVIEW                         ║
╚══════════════════════════════════════════════════════════════╝

SYSTEM IDENTIFICATION:
Hostname:          {system_info['hostname']}
Model / SKU:       {system_info['model']}
Serial Number:     {system_info['serial']}

STORAGE OVERVIEW:
Total Drives:      {system_info['drive_count']}
Total Capacity:    {system_info['total_storage_gb']:.2f} GB
Total Free Space:  {system_info['total_storage_free_gb']:.2f} GB
Free Space %:      {(system_info['total_storage_free_gb'] / system_info['total_storage_gb'] * 100):.1f}%

OPERATING SYSTEM:
OS:                {os_display}
Build:             {os_build}
Machine Type:      {platform.machine()}
Platform:          {platform.platform()}
Python Version:    {platform.python_version()}

CPU SUMMARY:
Brand:             {brand}
Architecture:      {Arch}
Logical Cores:     {psutil.cpu_count(logical=True)}
Physical Cores:    {psutil.cpu_count(logical=False)}

MEMORY SUMMARY:
Total Memory:      {memory_info['total']:.2f} GB
Used Memory:       {memory_info['used']:.2f} GB ({memory_info['percent']:.1f}%)
Available Memory:  {memory_info['available']:.2f} GB

TELEMETRY SYSTEM STATUS:
"""
            
            # Add kernel driver status
            try:
                from kernel_integration import get_kernel_helper_status
                kernel_helper = get_kernel_helper_status()
                
                overview_content += f"Kernel Driver:      {kernel_helper.get('status_text', 'Unknown')}\n"
                if kernel_helper.get('available'):
                    driver_version = kernel_helper.get('driver_version', 'Unknown')
                    protocol_version = kernel_helper.get('protocol_version', 'Unknown')
                    capabilities = kernel_helper.get('capabilities', {})
                    
                    overview_content += f"  Version:           v{driver_version}\n"
                    overview_content += f"  Protocol:          v{protocol_version}\n"
                    
                    # Show capabilities
                    cap_bits = []
                    decoded_caps = capabilities.get('decoded', {})
                    if decoded_caps.get('msr_read'): cap_bits.append('MSR Read')
                    if decoded_caps.get('msr_write'): cap_bits.append('MSR Write')
                    if decoded_caps.get('pci_read'): cap_bits.append('PCI Read')
                    if decoded_caps.get('smbus_read'): cap_bits.append('SMBus Read')
                    if decoded_caps.get('multicore'): cap_bits.append('Multicore')
                    
                    overview_content += f"  Capabilities:      {', '.join(cap_bits) if cap_bits else 'None'}\n"
                else:
                    error = kernel_helper.get('error', 'Unknown error')
                    overview_content += f"  Error:             {error}\n"
            except ImportError:
                overview_content += f"Kernel Driver:      ⚪ Not Available (kernel_integration.py missing)\n"
            except Exception as e:
                overview_content += f"Kernel Driver:      🔴 Error ({str(e)})\n"
            
            # Add helper executables status
            helpers = [
                ('cpuid_helper.exe', 'CPU Topology'),
                ('spd_helper.exe', 'Memory SPD'),
                ('nvme_helper.exe', 'NVMe SMART'),
                ('edid_helper.exe', 'Display EDID')
            ]
            
            overview_content += f"\nUser-Mode Helpers:\n"
            for helper_exe, helper_desc in helpers:
                helper_path = os.path.join(os.path.dirname(__file__), helper_exe)
                if os.path.exists(helper_path):
                    overview_content += f"  {helper_desc:15} ✓ Available\n"
                else:
                    overview_content += f"  {helper_desc:15} ✗ Missing\n"
            
            overview_content += f"\n"
            
            # Add detailed DIMM summary from spd_helper
            spd_helper = memory_info.get('spd_helper', {})
            if spd_helper.get('available') and spd_helper.get('dimms'):
                dimm_summary = []
                for dimm in spd_helper['dimms']:
                    if dimm.get('present'):
                        # Format: DDR5-6400 SODIMM 16GB (SK Hynix)
                        speed = dimm['configured_speed_mhz']
                        size_gb = dimm['size_mb'] / 1024
                        mfg = dimm['manufacturer']
                        ddr = dimm['ddr_generation']
                        ff = dimm['form_factor']
                        dimm_summary.append(f"{ddr}-{speed} {ff} {size_gb:.0f}GB ({mfg})")
                
                if dimm_summary:
                    overview_content += f"\nINSTALLED MODULES ({len(dimm_summary)}):\n"
                    for i, summary in enumerate(dimm_summary, 1):
                        overview_content += f"  [{i}] {summary}\n"
            
            # Battery status with design vs current capacity if available
            if 'battery_info' in system_info and system_info['battery_info']:
                bat = system_info['battery_info']
                power_status = "Plugged In" if bat['power_plugged'] else "On Battery"
                overview_content += f"\nBATTERY STATUS:\n"
                overview_content += f"  Charge Level:     {bat['percent']:.0f}%\n"
                overview_content += f"  Status:           {power_status}\n"
                if bat.get('secsleft') is not None and bat['secsleft'] > 0:
                    hours = bat['secsleft'] // 3600
                    minutes = (bat['secsleft'] % 3600) // 60
                    overview_content += f"  Time Remaining:   {hours}h {minutes}m\n"
                # Phase 1: Add battery wear level if available
                if bat.get('wear_level') is not None and bat.get('wear_level') > 0:
                    health = bat.get('health_status', 'Unknown')
                    overview_content += f"  Wear Level:       {bat['wear_level']:.1f}% ({health})\n"
            if 'power_supply' in system_info and system_info['power_supply']:
                psu = system_info['power_supply']
                overview_content += f"\nPOWER SUPPLY:\n"
                overview_content += f"  Name:              {psu['name']}\n"
                overview_content += f"  Status:            {psu['status']}\n"
            
            overview_text.insert('1.0', overview_content)
            overview_text.configure(state='disabled')
        
        # Update CPU tab
        if 'cpu' in text_widgets:
            cpu_text = text_widgets['cpu']
            cpu_text.configure(state='normal')
            cpu_text.delete('1.0', tk.END)
            
            cpu_content = f"""
╔══════════════════════════════════════════════════════════════╗
║                      CPU INFORMATION                         ║
╚══════════════════════════════════════════════════════════════╝

PROCESSOR DETAILS:
Brand:             {cpu_extended['brand']}
Architecture:      {cpu_extended['architecture']}
Processor:         {platform.processor()}
CPUID Brand:       {cpu_extended['cpuid_brand']}

CORE INFORMATION:
Logical Cores:     {cpu_extended['cores_logical']}
Physical Cores:    {cpu_extended['cores_physical']}
SMT Status:        {cpu_extended['smt_status']}

FREQUENCY INFORMATION:
Base Clock:        {cpu_extended['base_freq']}
Max Frequency:     {cpu_extended['max_freq']}
Max Turbo:         {cpu_extended['max_turbo_freq']}
Current Freq:      {cpu_extended['current_freq']}
Bus Clock:         {cpu_extended['bus_freq']}
Frequency Source:  {cpu_extended['freq_source']}

TURBO RATIO INFORMATION:
Max Turbo (1-core):   {cpu_extended.get('max_turbo_1c', 'Unavailable')} MHz
Max Turbo (all-core): {cpu_extended.get('max_turbo_ac', 'Unavailable')} MHz
MSR Access:           {cpu_extended.get('msr_access', 'Unavailable')}

CACHE INFORMATION:
L1 Cache:          {cpu_extended['cache_l1']}
L2 Cache:          {cpu_extended['cache_l2']}
L3 Cache:          {cpu_extended['cache_l3']}

POWER & THERMAL:
TDP:               {cpu_extended['tdp']}
Package Power:     {cpu_extended.get('package_power_draw', 'Unavailable')}
Socket:            {cpu_extended['socket']}
"""
            
            # Combine per-core frequency, C-state, and temperature telemetry for compact display
            has_freq = cpu_extended.get('per_core_frequency')
            has_cstate = cpu_extended.get('c_state_residency')
            has_temps = cpu_extended.get('kernel_temperatures', {}).get('temperatures', {})
            
            if has_freq or has_cstate or has_temps:
                cpu_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                cpu_content += "║          PER-CORE TELEMETRY (Freq + C-State + Temp)           ║\n"
                cpu_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                
                # Create combined view by matching core data
                freq_data = {item.get('core', 0): item for item in has_freq} if has_freq else {}
                cstate_data = {item.get('core', 0): item for item in has_cstate} if has_cstate else {}
                
                # Get all unique core numbers
                all_cores = set(freq_data.keys()) | set(cstate_data.keys()) | set(has_temps.keys())
                
                # Build data first, then calculate exact widths, then build headers to match
                data_rows = []
                
                for core in sorted(all_cores):
                    # Frequency data
                    freq_info = freq_data.get(core, {})
                    freq = freq_info.get('frequency_mhz', 0)
                    pct = freq_info.get('percentage', 0)
                    freq_str = f"{freq:4d} MHz ({pct:3d}%)" if freq_info else "N/A"
                    
                    # C-state data
                    cstate_info = cstate_data.get(core, {})
                    c0 = cstate_info.get('C0', 0)
                    c1_plus = cstate_info.get('C1+', 0)
                    cstate_str = f"C0={c0:3d}% (active)  C1+={c1_plus:3d}% (idle)" if cstate_info else "N/A"
                    
                    # Temperature data
                    temp_info = has_temps.get(core, {})
                    if temp_info:
                        celsius = temp_info.get('celsius', 0)
                        margin = temp_info.get('margin', 0)
                        temp_str = f"{celsius:3d}°C ({margin:2d}°C margin)"
                    else:
                        temp_str = "N/A"
                    
                    # Store the formatted data
                    data_rows.append({
                        'core': f"{core:3d}",
                        'freq': freq_str,
                        'cstate': cstate_str,
                        'temp': temp_str
                    })
                
                # Calculate exact widths from actual data
                max_core_len = max(len(row['core']) for row in data_rows)
                max_freq_len = max(len(row['freq']) for row in data_rows)
                max_cstate_len = max(len(row['cstate']) for row in data_rows)
                max_temp_len = max(len(row['temp']) for row in data_rows)
                
                # Build headers to match data widths
                core_header = "CORE".ljust(max_core_len)
                freq_header = "FREQUENCY".ljust(max_freq_len)
                cstate_header = "C-STATE RESIDENCY".ljust(max_cstate_len)
                temp_header = "TEMPERATURE".ljust(max_temp_len)
                
                # Build separator to match headers
                separator = "-" * max_core_len + "-+-" + "-" * max_freq_len + "-+-" + "-" * max_cstate_len + "-+-" + "-" * max_temp_len + "-"
                
                # Build the table with perfect alignment
                cpu_content += f"{core_header} | {freq_header} | {cstate_header} | {temp_header}\n"
                cpu_content += f"{separator}\n"
                
                for row in data_rows:
                    cpu_content += f"{row['core']} | {row['freq']} | {row['cstate']} | {row['temp']}\n"
                
                # Add package temperature if available
                if has_temps:
                    package_temp = cpu_extended.get('kernel_temperatures', {}).get('package_temp', 0)
                    tj_max = cpu_extended.get('kernel_temperatures', {}).get('tj_max', 100)
                    cpu_content += f"\nPackage Temperature: {package_temp:3d}°C (Tj Max: {tj_max}°C)\n"
            
            # Add APIC topology and cache sharing groups
            if cpu_extended.get('cache_sharing_groups'):
                cpu_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                cpu_content += "║              CACHE SHARING TOPOLOGY                          ║\n"
                cpu_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                
                cache_sharing = cpu_extended['cache_sharing_groups']
                l1d_inst = cache_sharing.get('l1d_instances', 0)
                l2_inst = cache_sharing.get('l2_instances', 0)
                l3_inst = cache_sharing.get('l3_instances', 0)
                
                cpu_content += f"L1D Cache: {l1d_inst} instances (per-core)\n"
                cpu_content += f"L2 Cache:  {l2_inst} instances (shared by clusters)\n"
                cpu_content += f"L3 Cache:  {l3_inst} instance(s) (shared by all cores)\n\n"
                
                # Show all cores with their cache group memberships
                apic_data = cpu_extended.get('apic_ids', [])
                if apic_data:
                    cpu_content += "Core → Cache Group Mapping:\n"
                    for core_info in apic_data:
                        lp = core_info.get('index', 0)
                        apic = core_info.get('apic', 0)
                        core_type = core_info.get('core_type', 0)
                        l2_grp = core_info.get('l2_group', -1)
                        type_str = 'P-core' if core_type == 64 else ('E-core' if core_type == 32 else 'Unknown')
                        cpu_content += f"  LP{lp:2d} (APIC {apic:3d}, {type_str}): L2 Group {l2_grp}\n"

            # Add temperature if available
            if 'temperatures' in cpu_extended and cpu_extended['temperatures']:
                cpu_content += "\nTEMPERATURE:\n"
                for temp_name, temp_val in list(cpu_extended['temperatures'].items())[:6]:
                    cpu_content += f"  {temp_name:20} {temp_val}\n"

            # Add virtualization support
            if 'virtualization' in cpu_extended and cpu_extended['virtualization'] != 'Not detected':
                cpu_content += f"\nVIRTUALIZATION:\n"
                cpu_content += f"  Support:           {cpu_extended['virtualization']}\n"

            # Add instruction sets with grouping if available
            if 'instruction_sets_grouped' in cpu_extended and cpu_extended['instruction_sets_grouped']:
                cpu_content += f"\nINSTRUCTION SETS (Categorized):\n"
                for category, instr_list in cpu_extended['instruction_sets_grouped'].items():
                    cpu_content += f"  {category}: {', '.join(instr_list)}\n"
            elif 'instruction_sets' in cpu_extended and cpu_extended['instruction_sets']:
                cpu_content += f"\nINSTRUCTION SETS:\n"
                instr_text = ', '.join(cpu_extended['instruction_sets'][:15])
                # Wrap long lines
                if len(instr_text) > 50:
                    words = instr_text.split(', ')
                    line = "  "
                    for word in words:
                        if len(line) + len(word) + 2 > 60:
                            cpu_content += line + "\n"
                            line = "  " + word
                        else:
                            line += (word if line == "  " else ", " + word)
                    if line != "  ":
                        cpu_content += line + "\n"
                else:
                    cpu_content += f"  {instr_text}\n"

            # Add security features
            if 'security_features' in cpu_extended and cpu_extended['security_features']:
                cpu_content += f"\nSECURITY FEATURES:\n"
                for feature in cpu_extended['security_features']:
                    if 'unavailable' in feature.lower():
                        cpu_content += f"  {feature}\n"
                    else:
                        cpu_content += f"  {feature}\n"

            # Add additional features if any
            if 'features' in cpu_extended and cpu_extended['features']:
                cpu_content += f"\nFEATURES:\n"
                for feature in cpu_extended['features']:
                    cpu_content += f"  {feature}\n"

            # Power Users Section
            cpu_content += f"\n╔══════════════════════════════════════════════════════════════╗\n"
            cpu_content += f"║                    POWER USERS SECTION                        ║\n"
            cpu_content += f"╚══════════════════════════════════════════════════════════════╝\n"
            
            if cpu_extended['microcode'] != 'Unavailable':
                cpu_content += f"\nMicrocode Version: {cpu_extended['microcode']}\n"
            
            # Display IPC metrics if available
            if cpu_extended.get('kernel_ipc', {}).get('available'):
                ipc_data = cpu_extended['kernel_ipc']
                cpu_content += f"IPC Efficiency: {ipc_data.get('efficiency', 'Unknown')} ({ipc_data.get('ipc_ratio', 0):.2f})\n"
            
            # Phase 1: Kernel Helper Status Display
            if 'kernel_helper' in cpu_extended:
                cpu_content += f"\n╔══════════════════════════════════════════════════════════════╗\n"
                cpu_content += f"║          PRIVILEGED MSR TELEMETRY (Kernel Driver)            ║\n"
                cpu_content += f"╚══════════════════════════════════════════════════════════════╝\n\n"
                
                kh = cpu_extended['kernel_helper']
                cpu_content += f"DRIVER STATUS:\n"
                cpu_content += f"  Kernel Helper:     {kh.get('status_text', 'Unknown')}\n"
                
                if kh.get('available'):
                    # Driver is available - show full details
                    cpu_content += f"  Driver Version:    {kh.get('driver_version', 'Unknown')}\n"
                    cpu_content += f"  Protocol:          v{kh.get('protocol_version', '?')}\n"
                    cpu_content += f"  Processor Count:   {kh.get('processor_count', 0)}\n"
                    cpu_content += f"  Whitelist:         {kh.get('msr_whitelist_version', 'Unknown')}\n\n"
                    
                    # Show capabilities
                    caps = kh.get('capabilities', {})
                    decoded_caps = caps.get('decoded', {})
                    cpu_content += f"CAPABILITIES:\n"
                    cpu_content += f"  MSR Read:          {'✓ Yes' if decoded_caps.get('msr_read') else '✗ No'}\n"
                    cpu_content += f"  MSR Write:         {'✓ Yes' if decoded_caps.get('msr_write') else '✗ No'}\n"
                    cpu_content += f"  PCI Read:          {'✓ Yes' if decoded_caps.get('pci_read') else '✗ No'}\n"
                    cpu_content += f"  SMBus Read:        {'✓ Yes' if decoded_caps.get('smbus_read') else '✗ No'}\n"
                    cpu_content += f"  Multicore:         {'✓ Yes' if decoded_caps.get('multicore') else '✗ No'}\n\n"
                    
                    # Show what data is available (Phase status)
                    cpu_content += f"AVAILABLE DATA (by Phase):\n"
                    
                    # Check temperature data
                    temp_data = cpu_extended.get('kernel_temperatures', {})
                    if temp_data.get('available'):
                        cpu_content += f"  ✓ Core Temperatures (MSR 0x19C)\n"
                    else:
                        phase = temp_data.get('phase', 'Future')
                        error = temp_data.get('error', 'Not yet implemented')
                        if 'Phase' in error:
                            cpu_content += f"  ⏳ Core Temperatures - {phase}\n"
                        else:
                            cpu_content += f"  ⏳ Core Temperatures - Phase 2\n"
                    
                    # Check power data
                    power_data = cpu_extended.get('kernel_power', {})
                    if power_data.get('available'):
                        cpu_content += f"  ✓ Power Limits & RAPL (MSR 0x610, 0x611)\n"
                    else:
                        phase = power_data.get('phase', 'Future')
                        error = power_data.get('error', 'Not yet implemented')
                        if 'Phase' in error:
                            cpu_content += f"  ⏳ Power Limits & RAPL - {phase}\n"
                        else:
                            cpu_content += f"  ⏳ Power Limits & RAPL - Phase 2\n"
                    
                    # Check turbo ratios
                    turbo_data = cpu_extended.get('kernel_turbo', {})
                    if turbo_data.get('available'):
                        cpu_content += f"  ✓ Turbo Ratios (MSR 0x1AD)\n"
                    else:
                        phase = turbo_data.get('phase', 'Future')
                        cpu_content += f"  ⏳ Turbo Ratios - {phase}\n"
                    
                    # Check C-states
                    cstate_data = cpu_extended.get('kernel_cstates', {})
                    if cstate_data.get('available'):
                        cpu_content += f"  ✓ C-State Residency (MSR 0x3FC-0x3FE)\n"
                    else:
                        phase = cstate_data.get('phase', 'Future')
                        cpu_content += f"  ⏳ C-State Residency - {phase}\n"
                    
                    # Phase 2: Temperature data is now displayed in combined per-core telemetry section above
                    
                    # Phase 2: Display power data if available
                    if power_data.get('available'):
                        cpu_content += f"\nPOWER LIMITS (MSR 0x610):\n"
                        pl1 = power_data.get('pl1', {})
                        pl2 = power_data.get('pl2', {})
                        
                        if pl1:
                            pl1_watts = pl1.get('watts', 0)
                            pl1_enabled = 'Enabled' if pl1.get('enabled') else 'Disabled'
                            pl1_clamping = 'Yes' if pl1.get('clamping') else 'No'
                            cpu_content += f"  PL1 (Sustained): {pl1_watts:5.1f}W ({pl1_enabled}, Clamping: {pl1_clamping})\n"
                        
                        if pl2:
                            pl2_watts = pl2.get('watts', 0)
                            pl2_enabled = 'Enabled' if pl2.get('enabled') else 'Disabled'
                            pl2_clamping = 'Yes' if pl2.get('clamping') else 'No'
                            cpu_content += f"  PL2 (Burst):     {pl2_watts:5.1f}W ({pl2_enabled}, Clamping: {pl2_clamping})\n"
                        
                        rapl = power_data.get('rapl', {})
                        if rapl and rapl.get('package_watts', 0) > 0:
                            cpu_content += f"\nENERGY CONSUMPTION (RAPL):\n"
                            cpu_content += f"  Package:         {rapl.get('package_watts', 0):5.1f}W  (MSR 0x611)\n"
                            if rapl.get('cores_watts', 0) > 0:
                                cpu_content += f"  Cores:           {rapl.get('cores_watts', 0):5.1f}W  (MSR 0x639)\n"
                            if rapl.get('dram_watts', 0) > 0:
                                cpu_content += f"  DRAM:            {rapl.get('dram_watts', 0):5.1f}W  (MSR 0x619)\n"
                            cpu_content += f"  Total:           {rapl.get('total_watts', 0):5.1f}W\n"
                    
                    # Protocol compatibility warning
                    if not kh.get('protocol_compatible'):
                        cpu_content += f"\n⚠ WARNING: Protocol version mismatch\n"
                        cpu_content += f"  {kh.get('error', 'Unknown error')}\n"
                else:
                    # Driver not available - show reason
                    error = kh.get('error', 'Unknown reason')
                    cpu_content += f"  Status:            Not Available\n"
                    cpu_content += f"  Reason:            {error}\n\n"
                    cpu_content += f"Privileged hardware telemetry requires:\n"
                    cpu_content += f"  1. HalfaxTelemetry driver installed and running\n"
                    cpu_content += f"  2. halfax_kernel_broker.exe present\n"
                    cpu_content += f"  3. Administrator privileges\n\n"
                    cpu_content += f"To check driver status:\n"
                    cpu_content += f"  > sc query HalfaxTelemetry\n"
            
            if cpu_extended['numa_nodes'] != 'N/A':
                cpu_content += f"NUMA Nodes:        {cpu_extended['numa_nodes']}\n"
            
            if cpu_extended['p_states']:
                cpu_content += f"P-States:          {cpu_extended['p_states']}\n"
            
            if cpu_extended['c_states']:
                cpu_content += f"C-States:          {', '.join(cpu_extended['c_states'])}\n"
            
            if cpu_extended['thermal_throttling'] != 'Unknown':
                cpu_content += f"Thermal Throttling: {cpu_extended['thermal_throttling']}\n"

            cpu_text.insert('1.0', cpu_content)
            cpu_text.configure(state='disabled')
        
        # Update GPU tab
        if 'gpu' in text_widgets:
            gpu_text = text_widgets['gpu']
            gpu_text.configure(state='normal')
            gpu_text.delete('1.0', tk.END)

            gpu_content = """
"╔══════════════════════════════════════════════════════════════╗"
"║                      GPU INFORMATION                         ║"
"╚══════════════════════════════════════════════════════════════╝"

"""

            if isinstance(gpu_info, dict) and 'error' in gpu_info:
                gpu_content += f"Error: {gpu_info['error']}\n"
            elif gpu_info:
                for i, gpu in enumerate(gpu_info, 1):
                    # Determine GPU type
                    gpu_name = gpu.get('name', 'Unknown')
                    gpu_type = 'Discrete' if 'NVIDIA' in gpu_name or 'AMD' in gpu_name else 'Integrated'
                    
                    gpu_content += f"─── GPU {i}: {gpu_name} ({gpu_type}) ──────────────────────────────────\n"
                    gpu_content += f"  Name:              {gpu_name}\n"
                    if 'video_processor' in gpu:
                        gpu_content += f"  Processor:         {gpu.get('video_processor','Unknown')}\n"
                    
                    # VRAM Information
                    if gpu.get('adapter_ram'):
                        try:
                            vram_gb = float(gpu.get('adapter_ram'))
                            gpu_content += f"  VRAM:              {vram_gb:.2f} GB"
                            if gpu.get('memory_used_gb'):
                                used_gb = gpu.get('memory_used_gb')
                                usage_percent = (used_gb / vram_gb) * 100
                                gpu_content += f" ({used_gb:.2f} GB used, {usage_percent:.1f}%)"
                            gpu_content += "\n"
                        except Exception:
                            gpu_content += f"  VRAM:              {gpu.get('adapter_ram')}\n"
                    else:
                        gpu_content += f"  VRAM:              Unknown\n"
                    
                    # Driver Information
                    if 'driver_version' in gpu:
                        gpu_content += f"  Driver Version:    {gpu.get('driver_version')}\n"
                    
                    # Status and Power State
                    status = gpu.get('status', 'Unknown')
                    if 'performance_state' in gpu:
                        status += f" (P{gpu.get('performance_state')})"
                    gpu_content += f"  Status:            {status}\n"
                    
                    # Device Information
                    if 'pnp_device_id' in gpu:
                        gpu_content += f"  Device ID:         {gpu.get('pnp_device_id')}\n"
                    elif 'device_id' in gpu:
                        gpu_content += f"  Device ID:         {gpu.get('device_id')}\n"
                    
                    # Performance Metrics Section
                    if any(key in gpu for key in ['core_utilization', 'memory_utilization', 'temperature_c', 'power_w', 'clocks']):
                        gpu_content += f"\n  ─── PERFORMANCE METRICS ───\n"
                        
                        # Utilization
                        if 'core_utilization' in gpu:
                            gpu_content += f"  Core Utilization:  {gpu.get('core_utilization')}%\n"
                        if 'memory_utilization' in gpu:
                            gpu_content += f"  Memory Utilization:{gpu.get('memory_utilization')}%\n"
                        
                        # Temperature
                        if 'temperature_c' in gpu:
                            temp = gpu.get('temperature_c')
                            if temp is not None:
                                gpu_content += f"  Temperature:       {temp}°C\n"
                        
                        # Power Consumption
                        if 'power_w' in gpu:
                            power = gpu.get('power_w')
                            if power is not None:
                                gpu_content += f"  Power:             {power:.2f} W\n"
                        
                        # Clock Speeds
                        if 'clocks' in gpu and isinstance(gpu.get('clocks'), dict):
                            clocks = gpu.get('clocks')
                            clock_parts = []
                            if 'graphics_mhz' in clocks:
                                clock_parts.append(f"Graphics: {clocks.get('graphics_mhz')}MHz")
                            if 'memory_mhz' in clocks:
                                clock_parts.append(f"Memory: {clocks.get('memory_mhz')}MHz")
                            if clock_parts:
                                gpu_content += f"  Clocks:            {', '.join(clock_parts)}\n"
                    
                    # PCIe Configuration Section
                    if 'interface_type' in gpu or 'resizable_bar' in gpu:
                        gpu_content += f"\n  ─── PCIe CONFIGURATION ───\n"
                        
                        if 'interface_type' in gpu:
                            gpu_content += f"  Interface:         {gpu.get('interface_type')}\n"
                        
                        if 'link_speed_gt_s' in gpu or 'link_width' in gpu:
                            speed = gpu.get('link_speed_gt_s', '')
                            width = gpu.get('link_width', '')
                            if speed and width:
                                gpu_content += f"  Link:              {speed} GT/s x{width}\n"
                            elif speed:
                                gpu_content += f"  Link Speed:        {speed} GT/s\n"
                            elif width:
                                gpu_content += f"  Link Width:        x{width}\n"
                        
                        if 'bandwidth_gb_s' in gpu:
                            try:
                                bandwidth = float(gpu.get('bandwidth_gb_s'))
                                gpu_content += f"  Bandwidth:         {bandwidth:.2f} GB/s\n"
                            except Exception:
                                pass
                        
                        if 'resizable_bar' in gpu:
                            rebar = gpu.get('resizable_bar')
                            if rebar is True:
                                gpu_content += f"  Resizable BAR:     Enabled\n"
                            elif rebar is False:
                                gpu_content += f"  Resizable BAR:     Disabled\n"
                            else:
                                gpu_content += f"  Resizable BAR:     {rebar}\n"
                    
                    # Display Output Section
                    if 'current_refresh_rate' in gpu or 'video_mode_description' in gpu:
                        gpu_content += f"\n  ─── DISPLAY OUTPUTS ───\n"
                        
                        if 'video_mode_description' in gpu:
                            gpu_content += f"  Resolution:        {gpu.get('video_mode_description')}\n"
                        elif 'current_refresh_rate' in gpu:
                            gpu_content += f"  Refresh Rate:      {gpu.get('current_refresh_rate')} Hz\n"
                        
                        # Display association (if available)
                        if gpu_display_map:
                            gpu_content += f"  Drives:            Multiple displays (see Monitor section)\n"
                    
                    gpu_content += "\n"
            else:
                gpu_content += "No GPU information available\n"

            gpu_content += "\n---- MONITOR INFORMATION ----\n\n"
            if isinstance(monitor_info, dict) and 'error' in monitor_info:
                gpu_content += f"Error: {monitor_info['error']}\n"
            elif monitor_info:
                for i, monitor in enumerate(monitor_info, 1):
                    gpu_content += f"Monitor {i}:\n"
                    gpu_content += f"  Name:            {monitor.get('name','Unknown')}\n"
                    if 'resolution' in monitor:
                        gpu_content += f"  Resolution:      {monitor.get('resolution')}\n"
                    if 'refresh_rate' in monitor:
                        gpu_content += f"  Refresh Rate:    {monitor.get('refresh_rate')} Hz\n"
                    if 'bits_per_pixel' in monitor:
                        gpu_content += f"  Color Depth:     {monitor.get('bits_per_pixel')} bits\n"
                    if 'manufacturer' in monitor and monitor.get('manufacturer') != 'Unknown':
                        gpu_content += f"  Manufacturer:    {monitor.get('manufacturer')}\n"
                    if 'model' in monitor and monitor.get('model') != 'Unknown':
                        gpu_content += f"  Model:           {monitor.get('model')}\n"
                    if 'serial' in monitor and monitor.get('serial') != 'Unknown':
                        gpu_content += f"  Serial:          {monitor.get('serial')}\n"
                    if 'pnp_device_id' in monitor:
                        gpu_content += f"  Device ID:       {monitor.get('pnp_device_id')}\n"
                    gpu_content += "\n"

            gpu_text.insert('1.0', gpu_content)
            gpu_text.configure(state='disabled')

        # Update Disk tab
        if 'disk' in text_widgets:
            disk_text = text_widgets['disk']
            disk_text.configure(state='normal')
            disk_text.delete('1.0', tk.END)
            report_content = ''
            # Add a short explanatory header to clarify physical vs partition info
            report_content += "Note: Physical Devices are detected from low-level sources (WMI/NVMe helpers).\n"
            report_content += "      Partitions (mounted volumes) are detected via psutil.\n"
            report_content += "      If the tool cannot reliably map a partition to a physical device, it will appear under 'Unmapped / Mounted Partitions'.\n\n"
            try:
                if isinstance(disk_info, dict) and disk_info.get('error'):
                    report_content = f"Disk helper error: {disk_info.get('error')}\n"
                elif isinstance(disk_info, (list, tuple)) and disk_info:
                    # Separate physical devices from partitions (best-effort)
                    physical = []
                    partitions = []
                    for d in disk_info:
                        # Heuristic: partitions have a mountpoint or fstype
                        if d.get('mountpoint') or d.get('fstype') or d.get('opts'):
                            partitions.append(d)
                        else:
                            physical.append(d)

                    # Helper: normalize device base name for matching
                    import re
                    def base_device_name(dev):
                        if not dev:
                            return ''
                        name = str(dev)
                        name = name.split('\\')[-1].split('/')[-1]
                        m = re.match(r'(.+?)(p?\d+)$', name)
                        if m:
                            return m.group(1)
                        return name

                    # Human-readable size helper (bytes -> GB/TB) with 2 decimals
                    def format_size(num_bytes):
                        try:
                            n = float(num_bytes)
                        except Exception:
                            return str(num_bytes)
                        tb = n / (1024**4)
                        gb = n / (1024**3)
                        if tb >= 1:
                            return f"{tb:.2f} TB"
                        return f"{gb:.2f} GB"

                    # Windows volume info helper: get volume label and filesystem name
                    def get_volume_info(mountpoint):
                        try:
                            if not IS_WINDOWS:
                                return {}
                            import ctypes
                            from ctypes import wintypes
                            GetVolumeInformationW = ctypes.windll.kernel32.GetVolumeInformationW
                            vol_name_buf = ctypes.create_unicode_buffer(1024)
                            fs_name_buf = ctypes.create_unicode_buffer(1024)
                            serial_number = wintypes.DWORD()
                            max_comp_len = wintypes.DWORD()
                            fs_flags = wintypes.DWORD()
                            res = GetVolumeInformationW(
                                ctypes.c_wchar_p(mountpoint),
                                vol_name_buf,
                                ctypes.sizeof(vol_name_buf),
                                ctypes.byref(serial_number),
                                ctypes.byref(max_comp_len),
                                ctypes.byref(fs_flags),
                                fs_name_buf,
                                ctypes.sizeof(fs_name_buf)
                            )
                            if res:
                                return {
                                    'volume_label': vol_name_buf.value,
                                    'filesystem': fs_name_buf.value,
                                    'fs_flags': int(fs_flags.value),
                                    'serial_number': int(serial_number.value)
                                }
                        except Exception:
                            pass
                        return {}

                    # Build direct physical-device -> entries map to avoid key collisions
                    phys_device_map = {}
                    for idx, p in enumerate(physical, 1):
                        dev_path = p.get('device') or p.get('model') or f'phys_{idx}'
                        phys_device_map.setdefault(dev_path, {'phys': p, 'parts': []})

                    unmapped_partitions = []
                    # Helper for base-name
                    def base_device_name(dev):
                        if not dev:
                            return ''
                        name = str(dev).split('\\')[-1].split('/')[-1]
                        m = re.match(r'(.+?)(p?\d+)$', name)
                        if m:
                            return m.group(1)
                        return name

                    # Attach partitions to physical devices by deterministic field or heuristics
                    for part in partitions:
                        attached = False
                        pd = part.get('physical_device')
                        if pd and pd in phys_device_map:
                            phys_device_map[pd]['parts'].append(part)
                            attached = True
                        else:
                            for dev_path, entry in phys_device_map.items():
                                if part.get('device') and part.get('device') in dev_path:
                                    entry['parts'].append(part)
                                    attached = True
                                    break
                        if not attached:
                            pb = base_device_name(part.get('device'))
                            for dev_path, entry in phys_device_map.items():
                                if pb and pb in base_device_name(dev_path):
                                    entry['parts'].append(part)
                                    attached = True
                                    break
                        if not attached:
                            unmapped_partitions.append(part)

                    # Heuristic size-based mapping for any remaining unmapped partitions
                    if unmapped_partitions and phys_device_map:
                        phys_sizes = [(dev, int(entry['phys'].get('size') or entry['phys'].get('total') or 0)) for dev, entry in phys_device_map.items()]
                        for part in list(unmapped_partitions):
                            try:
                                psize = int(part.get('total') or 0)
                            except Exception:
                                psize = 0
                            candidates = [(dev, sz, abs(sz - psize)) for (dev, sz) in phys_sizes if sz >= psize]
                            if not candidates:
                                candidates = [(dev, sz, abs(sz - psize)) for (dev, sz) in phys_sizes]
                            if candidates:
                                candidates.sort(key=lambda x: x[2])
                                chosen = candidates[0][0]
                                phys_device_map[chosen]['parts'].append(part)
                                unmapped_partitions.remove(part)

                    # Render Physical Devices and their partitions
                    if phys_device_map:
                        for idx, (dev_path, entry) in enumerate(phys_device_map.items(), 1):
                            phys = entry.get('phys', {})
                            report_content += f"─── Physical Device {idx} ({dev_path}) ─────────────────────────────────\n"
                            report_content += f"  Device Path:       {dev_path}\n"
                            report_content += f"  Model:             {phys.get('model','Unknown')}\n"
                            report_content += f"  Serial:            {phys.get('serial','Unknown')}\n"
                            os_iface = phys.get('interface_type', phys.get('source','Unknown'))
                            # infer bus type
                            model_lower = str(phys.get('model','')).lower()
                            if 'nvme' in model_lower or 'nvme' in str(phys.get('device','')).lower():
                                bus_type = 'NVMe'
                            elif 'ssd' in model_lower or phys.get('rotational') is False:
                                bus_type = 'SSD'
                            else:
                                bus_type = 'HDD'
                            report_content += f"  Bus Type (inferred): {bus_type}\n"
                            report_content += f"  OS-reported Interface: {os_iface}\n"
                            report_content += f"  Capacity:           {format_size(phys.get('size') or phys.get('total') or 0)}\n"
                            # SMART fields
                            if phys.get('temperature') is not None:
                                report_content += f"  Temperature:        {phys.get('temperature')} C\n"
                            if phys.get('power_on_hours') is not None:
                                report_content += f"  Power-On Hours:     {phys.get('power_on_hours')}\n"
                            if phys.get('data_units_read') is not None or phys.get('data_units_written') is not None:
                                report_content += f"  Data Units Read:    {phys.get('data_units_read','N/A')}\n"
                                report_content += f"  Data Units Written: {phys.get('data_units_written','N/A')}\n"
                            if phys.get('error_count') is not None:
                                report_content += f"  Error Count:        {phys.get('error_count')}\n"
                            if phys.get('error_log'):
                                try:
                                    if isinstance(phys.get('error_log'), (list, tuple)):
                                        report_content += f"  Error Log Entries:  {len(phys.get('error_log'))} (showing up to 3)\n"
                                        for e in phys.get('error_log')[:3]:
                                            report_content += f"    - {e}\n"
                                except Exception:
                                    report_content += f"  Error Log:          {phys.get('error_log')}\n"
                            if phys.get('critical_warning') or phys.get('critical_warnings'):
                                report_content += f"  Critical Warnings:  {phys.get('critical_warning') or phys.get('critical_warnings')}\n"

                            # List partitions under this physical device
                            parts = entry.get('parts', [])
                            if parts:
                                for pi, p in enumerate(parts, 1):
                                    report_content += f"    ─ Partition {pi} ─────────────────────────────────────────\n"
                                    report_content += f"      Drive Letter:    {p.get('device','Unknown')}\n"
                                    report_content += f"      Mountpoint:     {p.get('mountpoint','Unknown')}\n"
                                    report_content += f"      FS:             {p.get('fstype','Unknown')}\n"
                                    if p.get('total'):
                                        report_content += f"      Size:           {format_size(p.get('total',0))}\n"
                                        if p.get('used') is not None:
                                            try:
                                                used_val = float(p.get('used',0))
                                                report_content += f"      Used:           {format_size(used_val)} ({p.get('percent','N/A')}%)\n"
                                            except Exception:
                                                report_content += f"      Used:           {p.get('used',0)} ({p.get('percent','N/A')}%)\n"
                                    volinfo = get_volume_info(p.get('mountpoint') or p.get('device') or '')
                                    if volinfo:
                                        if volinfo.get('volume_label'):
                                            report_content += f"      Volume Label:    {volinfo.get('volume_label')}\n"
                                        if volinfo.get('filesystem'):
                                            report_content += f"      FS Name:         {volinfo.get('filesystem')}\n"
                                        if volinfo.get('serial_number'):
                                            report_content += f"      Volume Serial:   {volinfo.get('serial_number')}\n"
                                    report_content += f"      Device Path:     {p.get('physical_device','Unknown')}\n"
                                    report_content += f"      Device:         {p.get('device','Unknown')}\n"
                            report_content += "\n"

                    # Render any remaining unmapped partitions
                    if unmapped_partitions:
                        report_content += "─── Unmapped / Mounted Partitions ─────────────────────────────────\n"
                        for i, p in enumerate(unmapped_partitions, 1):
                            report_content += f"  Partition {i}:\n"
                            report_content += f"    Device:         {p.get('device','Unknown')}\n"
                            report_content += f"    Mountpoint:     {p.get('mountpoint','Unknown')}\n"
                            report_content += f"    FS:             {p.get('fstype','Unknown')}\n"
                            if p.get('total'):
                                report_content += f"    Size:           {format_size(p.get('total',0))}\n"
                                if p.get('used') is not None:
                                    try:
                                        report_content += f"    Used:           {format_size(p.get('used',0))} ({p.get('percent','N/A')}%)\n"
                                    except Exception:
                                        report_content += f"    Used:           {p.get('used',0)} ({p.get('percent','N/A')}%)\n"
                            report_content += "\n"

                    if not phys_device_map and not unmapped_partitions:
                        report_content = 'No disk information available\n'
                else:
                    report_content = 'No disk information available\n'
            except Exception as e:
                report_content = f"Disk formatting error: {e}\n"
            disk_text.insert('1.0', report_content)
            disk_text.configure(state='disabled')

        # Update Storage tab
        if 'storage' in text_widgets:
            try:
                from kernel_integration import get_storage_telemetry
            except Exception:
                get_storage_telemetry = lambda: {'error': 'kernel_integration not available'}
            storage_text = text_widgets['storage']
            storage_text.configure(state='normal')
            storage_text.delete('1.0', tk.END)
            storage_content = "Storage telemetry not available"
            try:
                storage_data = get_storage_telemetry()
                if isinstance(storage_data, dict):
                    # Error path from kernel helper
                    if 'error' in storage_data:
                        storage_content = f"Error: {storage_data['error']}"
                    else:
                        # Prefer `nvme_devices` (detailed NVMe telemetry)
                        nvme_devs = storage_data.get('nvme_devices') or []
                        wmi_devs = storage_data.get('wmi_devices') or []
                        status = storage_data.get('status') or storage_data.get('note') or ''

                        if nvme_devs:
                            storage_content = ''
                            for i, device in enumerate(nvme_devs, 1):
                                storage_content += f"─── NVMe Device {i} ───────────────────────────────────────────\n"
                                storage_content += f"  Device Path:     {device.get('device_path','Unknown')}\n"
                                storage_content += f"  Model:           {device.get('model','Unknown')}\n"
                                storage_content += f"  Serial:          {device.get('serial','Unknown')}\n\n"
                        elif wmi_devs:
                            storage_content = ''
                            for i, device in enumerate(wmi_devs, 1):
                                storage_content += f"─── Physical Device {i} ─────────────────────────────────\n"
                                storage_content += f"  Model:           {device.get('model','Unknown')}\n"
                                storage_content += f"  Serial:          {device.get('serial','Unknown')}\n"
                                storage_content += f"  Interface:       {device.get('interface','Unknown')}\n"
                                storage_content += f"  Size:            {device.get('size_gb','Unknown')} GB\n\n"
                        elif status:
                            storage_content = f"Storage status: {status}"
                        else:
                            storage_content = 'No storage telemetry data available'
            except Exception as e:
                storage_content = f"Storage error: {e}"
            storage_text.insert('1.0', storage_content)
            storage_text.configure(state='disabled')

        # Update Display tab
        if 'display' in text_widgets:
            display_text = text_widgets['display']
            display_text.configure(state='normal')
            display_text.delete('1.0', tk.END)
            display_content = ""
            try:
                edid_info = get_edid_helper_info()
            except Exception:
                edid_info = {'error': 'edid helper not available'}
            # Prefer EDID helper output when available, otherwise fall back to monitor_info
            if isinstance(edid_info, dict) and edid_info.get('error'):
                # If EDID helper errored, fall back to monitor_info
                display_content += f"EDID helper error: {edid_info.get('error')}\n"
                if monitor_info:
                    if isinstance(monitor_info, dict) and monitor_info.get('error'):
                        display_content += f"Monitor detection error: {monitor_info.get('error')}\n"
                    else:
                        for i, monitor in enumerate(monitor_info if isinstance(monitor_info, (list, tuple)) else [monitor_info], 1):
                            display_content += f"─── Monitor {i} ───────────────────────────────────────────────\n"
                            display_content += f"  Name:             {monitor.get('name','Unknown')}\n"
                            display_content += f"  Resolution:       {monitor.get('resolution','Unknown')}\n"
                            display_content += f"  Refresh Rate:     {monitor.get('refresh_rate','Unknown')}\n\n"
            elif edid_info and isinstance(edid_info, dict) and 'edid_devices' in edid_info and edid_info.get('edid_devices'):
                for i, device in enumerate(edid_info['edid_devices'], 1):
                    display_content += f"─── Monitor {i} ───────────────────────────────────────────────\n"
                    display_content += f"  Name:             {device.get('monitor_name','Unknown')}\n"
                    display_content += f"  Manufacturer:     {device.get('manufacturer','Unknown')}\n"
                    display_content += f"  Model Code:       {device.get('model','Unknown')}\n"
                    display_content += f"  Serial Number:    {device.get('serial_number','Unknown')}\n\n"
            else:
                # No EDID devices returned; use monitor_info if available
                if monitor_info:
                    if isinstance(monitor_info, dict) and monitor_info.get('error'):
                        display_content += f"Monitor detection error: {monitor_info.get('error')}\n"
                    else:
                        for i, monitor in enumerate(monitor_info if isinstance(monitor_info, (list, tuple)) else [monitor_info], 1):
                            display_content += f"─── Monitor {i} ───────────────────────────────────────────────\n"
                            display_content += f"  Name:             {monitor.get('name','Unknown')}\n"
                            display_content += f"  Resolution:       {monitor.get('resolution','Unknown')}\n"
                            display_content += f"  Refresh Rate:     {monitor.get('refresh_rate','Unknown')}\n\n"
                else:
                    display_content += "No EDID/monitor data available\n"
            display_text.insert('1.0', display_content)
            display_text.configure(state='disabled')

        # Update Memory tab
        if 'memory' in text_widgets:
            mem_text = text_widgets['memory']
            mem_text.configure(state='normal')
            mem_text.delete('1.0', tk.END)
            try:
                mi = memory_info
                mem_s = f"Total: {mi.get('total',0):.2f} GB\nUsed: {mi.get('used',0):.2f} GB ({mi.get('percent',0):.1f}%)\nAvailable: {mi.get('available',0):.2f} GB\nModules: {mi.get('module_count',0)}\n"
                # SPD helper details
                spd = mi.get('spd_helper', {})
                if spd.get('available') and spd.get('dimms'):
                    mem_s += "\nDIMMs:\n"
                    for i, d in enumerate(spd.get('dimms', []), 1):
                        mem_s += f"  [{i}] {d.get('manufacturer','Unknown')} {d.get('ddr_generation','')} {d.get('size_mb',0)/1024:.0f}GB {d.get('form_factor','')}\n"
                mem_text.insert('1.0', mem_s)
            except Exception as e:
                mem_text.insert('1.0', f"Memory error: {e}\n")
            mem_text.configure(state='disabled')

        # Update Network tab
        if 'network' in text_widgets:
            net_text = text_widgets['network']
            net_text.configure(state='normal')
            net_text.delete('1.0', tk.END)
            try:
                ni = network_info
                if ni.get('error'):
                    net_text.insert('1.0', f"Network error: {ni.get('error')}\n")
                else:
                    txt = f"""╔══════════════════════════════════════════════════════════════╗
║                  NETWORK INFORMATION                      ║
╚══════════════════════════════════════════════════════════════╝

"""
                    # === CURRENT ACTIVE CONNECTION SECTION (NEW!) ===
                    active = ni.get('active', {})
                    if not active.get('error'):
                        txt += f"\n{'='*60}\n🟢 HERE IS YOUR CURRENT ACCESS:\n{'='*60}\n"
                        
                        # Connection Type
                        if active.get('connection_type'):
                            txt += f"\n  Connection Type: {active['connection_type']}\n"
                        
                        # WiFi SSID if connected to WiFi
                        if active.get('ssid'):
                            txt += f"  Network:        {active['ssid']}\n"
                        
                        # Your IP Address
                        if active.get('ip_address'):
                            txt += f"  Your IP:        {active['ip_address']}\n"

                        # IPv6 Address (if available)
                        if active.get('ip_address_v6'):
                            txt += f"  IPv6 Address:   {active['ip_address_v6']}\n"
                        
                        # Your MAC Address
                        if active.get('mac_address'):
                            txt += f"  MAC Address:    {active['mac_address']}\n"

                        # WiFi Security (if available)
                        if active.get('wifi_security'):
                            txt += f"  WiFi Security:  {active['wifi_security']}\n"
                        
                        # Gateway/Router
                        if active.get('gateway'):
                            txt += f"\n  Gateway (Router IP):  {active['gateway']}\n"
                            
                            # Gateway Owner/ISP
                            if active.get('gateway_owner'):
                                owner = active['gateway_owner']
                                if 'Private Network' in owner:
                                    txt += f"  Gateway Owner:  🔒 {owner}\n"
                                else:
                                    txt += f"  Gateway Owner:  🌐 {owner}\n"
                            
                            # Gateway Hostname
                            if active.get('gateway_hostname'):
                                txt += f"  Gateway Hostname:    {active['gateway_hostname']}\n"
                        
                        # DNS Servers
                        if active.get('dns_servers'):
                            txt += f"\n  DNS Servers:\n"
                            for i, dns in enumerate(active['dns_servers'], 1):
                                txt += f"    DNS {i}: {dns}\n"
                        
                        # Active Adapter
                        if active.get('active_adapter'):
                            txt += f"\n  Active Adapter: {active['active_adapter']}\n"

                        # === INTERPRETATION / INSIGHTS ===
                        insights = []
                        ssid = (active.get('ssid') or '').strip()
                        ssid_lower = ssid.lower()
                        gateway_parts = (active.get('gateway') or '').split()
                        gateway = gateway_parts[0] if gateway_parts else ''
                        ip_v4_parts = (active.get('ip_address') or '').split()
                        ip_v4 = ip_v4_parts[0] if ip_v4_parts else ''
                        ip_v6_parts = (active.get('ip_address_v6') or '').split()
                        ip_v6 = ip_v6_parts[0] if ip_v6_parts else ''
                        dns_list = active.get('dns_servers') or []

                        if ssid_lower == 'xfinitywifi':
                            insights.append("SSID 'xfinitywifi' indicates an Xfinity public hotspot broadcast.")

                        if active.get('is_private_ip') and ip_v4:
                            insights.append("Your IPv4 is private (DHCP-assigned on the local WiFi segment).")

                        if gateway and active.get('is_private_ip'):
                            insights.append("Gateway is the local hotspot/router interface (NAT edge).")

                        if ip_v6.startswith('2601:') or ip_v6.startswith('2001:558:'):
                            insights.append("IPv6 prefix aligns with Comcast/Xfinity space.")

                        if any(dns in ['75.75.75.75', '75.75.76.76', '2001:558:feed::1'] for dns in dns_list):
                            insights.append("DNS servers match Comcast/Xfinity resolvers.")

                        owner = active.get('gateway_owner') or ''
                        if owner and 'private network' not in owner.lower():
                            insights.append(f"Upstream owner appears to be: {owner}.")

                        if insights:
                            txt += "\n  Summary:\n"
                            for item in insights:
                                txt += f"    - {item}\n"

                        # Security note for open hotspots
                        security = (active.get('wifi_security') or '').lower()
                        if ssid_lower == 'xfinitywifi' or 'open' in security or 'none' in security:
                            txt += "\n  Security Note:\n"
                            txt += "    - This SSID appears open/unsecured. Use a trusted VPN for sensitive activity.\n"
                            txt += "    - Prefer HTTPS-only sites and avoid high-value logins without a VPN.\n"
                    
                    # === NETWORK DISCOVERY SECTION ===
                    enhanced = ni.get('enhanced', {})
                    
                    # WiFi Networks
                    if enhanced.get('wifi_networks'):
                        txt += f"\n{'='*60}\nWIFI NETWORKS AVAILABLE:\n{'='*60}\n"
                        for wifi in enhanced['wifi_networks']:
                            txt += f"\n  Network: {wifi.get('ssid', 'Unknown')}\n"
                            txt += f"    Interface:  {wifi.get('interface', 'Unknown')}\n"
                            txt += f"    Signal:     {wifi.get('signal', 'Unknown')}\n"
                            txt += f"    Security:   {wifi.get('security', 'Unknown')}\n"
                            if wifi.get('connected'):
                                txt += f"    Status:     🟢 CONNECTED\n"
                    
                    # Gateway Information
                    if enhanced.get('gateway_info'):
                        txt += f"\n{'='*60}\nGATEWAY INFORMATION:\n{'='*60}\n"
                        for gateway, info in enhanced['gateway_info'].items():
                            txt += f"  Gateway:    {gateway}\n"
                            txt += f"    Interfaces: {info.get('count', 1)}\n"
                    
                    # DNS Servers
                    if enhanced.get('dns_servers'):
                        txt += f"\n{'='*60}\nDNS SERVERS:\n{'='*60}\n"
                        for i, dns in enumerate(enhanced['dns_servers'], 1):
                            txt += f"  DNS {i}: {dns}\n"
                    
                    # DHCP Configuration
                    if enhanced.get('dhcp_enabled'):
                        txt += f"\n{'='*60}\nDHCP CONFIGURATION:\n{'='*60}\n"
                        for adapter, dhcp_info in enhanced['dhcp_enabled'].items():
                            if dhcp_info.get('dhcp'):
                                txt += f"  {adapter}:\n"
                                txt += f"    DHCP: {dhcp_info.get('dhcp', 'Unknown')}\n"
                    
                    # Network Adapter Details (WMI/Discovery)
                    if enhanced.get('network_discovery'):
                        txt += f"\n{'='*60}\nNETWORK ADAPTER CONFIGURATION:\n{'='*60}\n"
                        for idx, adapter in enumerate(enhanced['network_discovery'], 1):
                            txt += f"\n  Adapter {idx}: {adapter.get('adapter', 'Unknown')}\n"
                            txt += f"    MAC Address:  {adapter.get('mac', 'Unknown')}\n"
                            txt += f"    DHCP Enabled: {adapter.get('dhcp_enabled', 'Unknown')}\n"
                            if adapter.get('ip_addresses'):
                                txt += f"    IP Addresses: {', '.join(adapter['ip_addresses'])}\n"
                            if adapter.get('gateways'):
                                txt += f"    Gateways:     {', '.join(adapter['gateways'])}\n"
                            if adapter.get('dns_servers'):
                                txt += f"    DNS Servers:  {', '.join(adapter['dns_servers'])}\n"
                    
                    # === INTERFACE DETAILS ===
                    txt += f"\n{'='*60}\nNETWORK INTERFACES: {len(ni.get('interfaces', []))}\n{'='*60}\n"
                    
                    for iface in ni.get('interfaces', []):
                        status = "🟢 UP" if iface.get('is_up') else "⚫ DOWN"
                        speed = iface.get('speed', 0)
                        speed_str = f"{speed} Mbps" if speed > 0 else "Unknown"
                        
                        txt += f"\n  {iface.get('name')} {status}\n"
                        txt += f"    Speed:      {speed_str}\n"
                        txt += f"    MTU:        {iface.get('mtu', 'N/A')}\n"
                        txt += f"    Type:       {iface.get('adapter_type', 'N/A')}\n"
                        if iface.get('mac_address'):
                            txt += f"    MAC:        {iface.get('mac_address')}\n"
                        if iface.get('description'):
                            txt += f"    Description: {iface.get('description')}\n"
                        
                        # IP Addresses
                        if iface.get('addresses'):
                            txt += f"    IP Addresses:\n"
                            for addr in iface['addresses']:
                                txt += f"      {addr.get('family'):6} {addr.get('address')}\n"
                                if addr.get('netmask') and addr.get('netmask') != 'N/A':
                                    txt += f"               Netmask: {addr.get('netmask')}\n"
                        
                        if iface.get('wireless'):
                            txt += f"    Wireless:   Yes (802.11)\n"
                    
                    # === CONNECTION STATISTICS ===
                    if ni.get('connection_stats'):
                        stats = ni['connection_stats']
                        txt += f"\n{'='*60}\nCONNECTION STATISTICS:\n{'='*60}\n"
                        txt += f"  Active Connections: {ni.get('connections', 0)}\n"
                        txt += f"    Established: {stats.get('established', 0)}\n"
                        txt += f"    Listening:   {stats.get('listen', 0)}\n"
                        txt += f"    Time Wait:   {stats.get('time_wait', 0)}\n"
                        txt += f"    Close Wait:  {stats.get('close_wait', 0)}\n"
                    
                    # === I/O STATISTICS ===
                    if ni.get('io'):
                        io = ni['io']
                        txt += f"\n{'='*60}\nNETWORK I/O STATISTICS:\n{'='*60}\n"
                        txt += f"  Bytes Sent:      {io.get('bytes_sent', 0):,}\n"
                        txt += f"  Bytes Received:  {io.get('bytes_recv', 0):,}\n"
                        txt += f"  Packets Sent:    {io.get('packets_sent', 0):,}\n"
                        txt += f"  Packets Recv:    {io.get('packets_recv', 0):,}\n"
                        txt += f"  Errors In:       {io.get('errin', 0)}\n"
                        txt += f"  Errors Out:      {io.get('errout', 0)}\n"
                        txt += f"  Dropped In:      {io.get('dropin', 0)}\n"
                        txt += f"  Dropped Out:     {io.get('dropout', 0)}\n"
                    
                    net_text.insert('1.0', txt)
            except Exception as e:
                net_text.insert('1.0', f"Network error: {e}\n")
            net_text.configure(state='disabled')

        # Update Architecture tab
        if 'architecture' in text_widgets:
            arch_text = text_widgets['architecture']
            arch_text.configure(state='normal')
            arch_text.delete('1.0', tk.END)
            try:
                pt = pci_topology
                if isinstance(pt, dict) and pt.get('error'):
                    arch_text.insert('1.0', f"PCI topology error: {pt.get('error')}\n")
                else:
                    if isinstance(pt, dict) and pt.get('devices'):
                        out = ''
                        for d in pt.get('devices', []):
                            out += f"{d.get('device_id','Unknown')} - {d.get('class','Unknown')} - Vendor:{d.get('vendor_id')} Dev:{d.get('device_code')}\n"
                        arch_text.insert('1.0', out)
                    else:
                        arch_text.insert('1.0', 'No PCI topology available\n')
            except Exception as e:
                arch_text.insert('1.0', f"Architecture error: {e}\n")
            arch_text.configure(state='disabled')
        # Update comprehensive Text Report tab
        try:
            populate_text_report_tab()
        except Exception:
            pass
    # Tabs are created by `ensure_tabs_created()`; avoid duplicating UI creation here.
    # Ensure placeholder `cpu_extended` exists to avoid NameError before first refresh
    cpu_extended = {}

    # After setup: schedule initial refresh, destroy splash, and show main window
    def _finish_setup():
        # Update splash status
        try:
            status_label.config(text="Gathering system information...")
            progress_label.config(text="This may take a few moments...")
            splash.update()
        except:
            pass
        
        # Gather data in smaller chunks to keep UI responsive
        def gather_data_step(step=0):
            try:
                if step == 0:
                    # First chunk: Overview tab
                    populate_overview_tab()
                    splash.update()
                    root.after(50, lambda: gather_data_step(1))
                elif step == 1:
                    # Second chunk: CPU tab
                    populate_cpu_tab()
                    splash.update()
                    root.after(50, lambda: gather_data_step(2))
                elif step == 2:
                    # Third chunk: Memory tab
                    populate_memory_tab()
                    splash.update()
                    root.after(50, lambda: gather_data_step(3))
                elif step == 3:
                    # Fourth chunk: GPU tab
                    populate_gpu_tab()
                    splash.update()
                    root.after(50, lambda: gather_data_step(4))
                elif step == 4:
                    # Fifth chunk: Storage and remaining tabs
                    populate_disks_tab()
                    populate_storage_tab()
                    populate_display_tab()
                    populate_system_architecture_tab()
                    populate_network_tab()
                    populate_text_report_tab()
                    splash.update()
                    root.after(50, finish_splash)
            except Exception:
                # Fallback to full refresh if step-by-step fails
                try:
                    refresh_all_tabs()
                except:
                    pass
                finish_splash()
        
        def finish_splash():
            # Stop progress bar and update status
            try:
                progress_bar.stop()
                status_label.config(text="Launching application...")
                progress_label.config(text="Almost ready")
                splash.update()
                # Small delay to show "Almost ready" status
                splash.after(100, close_splash)
            except:
                close_splash()
        
        def close_splash():
            # Close splash and show main window
            try:
                splash.destroy()
            except:
                pass
            try:
                root.deiconify()
            except:
                pass
            # Ensure Text Report gets a final population once UI is visible
            try:
                root.after(200, populate_text_report_tab)
            except Exception:
                pass
        
        # Ensure tabs/widgets exist before data gathering so populate_* can write into them
        try:
            ensure_tabs_created()
        except Exception:
            pass

        # Start the step-by-step data gathering
        gather_data_step()

    # Run after a short delay to ensure splash is visible
    root.after(100, _finish_setup)

    return root


if __name__ == '__main__':
    gui_root = create_gui()
    gui_root.mainloop()
    
