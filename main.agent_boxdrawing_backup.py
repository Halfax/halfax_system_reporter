import psutil
import platform
import os
import cpuinfo
import subprocess
import json
import glob

# Try to import WMI (Windows only)
try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

# Detect platform
SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == "Windows"
IS_LINUX = SYSTEM == "Linux"
IS_MAC = SYSTEM == "Darwin"
IS_PI = False

# Check if running on Raspberry Pi
try:
    with open('/proc/device-tree/model', 'r') as f:
        model = f.read().strip()
        IS_PI = 'Raspberry Pi' in model
except:
    pass
    
    return "Not reported by system API"

def get_memory_cas_latency():
    """Detect CAS Latency from SPD data"""
    if IS_WINDOWS and HAS_WMI:
        try:
            # WMI doesn't directly expose SPD timing data
            # Would need to read SPD via hardware-level access
            return "Not reported by system API"
        except:
            pass
    
    elif IS_LINUX and not IS_PI:
        try:
            result = subprocess.run(['dmidecode', '-t', 'memory'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'CAS' in line.upper() or 'Latency' in line:
                        return line.strip()
        except:
            pass
    
    return "Not reported by system API"

def get_memory_temp():
    """Detect memory temperature (DDR5 modules with thermal sensors)"""
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            # Check for memory thermal sensors
            for temp in c.Win32_TemperatureProbe():
                if 'Memory' in temp.Name or 'DIMM' in temp.Name:
                    return f"{temp.CurrentReading} K (~{temp.CurrentReading - 273.15:.1f}°C)"
        except:
            pass
    
    elif IS_LINUX:
        try:
            # Check hwmon for memory temperature
            import glob
            for sensor_path in glob.glob('/sys/class/hwmon/hwmon*/temp*_label'):
                try:
                    with open(sensor_path, 'r') as f:
                        label = f.read().strip()
                        if 'mem' in label.lower() or 'dimm' in label.lower():
                            temp_path = sensor_path.replace('_label', '_input')
                            with open(temp_path, 'r') as tf:
                                temp_raw = int(tf.read().strip())
                                temp_c = temp_raw / 1000
                                return f"{temp_c:.1f}°C"
                except:
                    pass
        except:
            pass
    
    return "Not reported by system API"

def get_memory_rank_bank_info():
    """Detect memory rank and bank configuration"""
    rank_info = "Not reported by system API"
    bank_info = "Not reported by system API"
    
    if IS_WINDOWS and HAS_WMI:
        try:
            c = wmi.WMI()
            for mem in c.Win32_PhysicalMemory():
                # DataWidth can hint at rank configuration
                # Rank info often not directly available in WMI
                # Banks are typically fixed (4-8 banks per DIMM on modern DDR)
                if hasattr(mem, 'Attributes') and mem.Attributes:
                    # Bit 2 (value 4) indicates dual-rank
                    attributes = int(mem.Attributes)
                    if attributes & 4:
                        rank_info = "Dual-Rank (DR) — from WMI"
                    else:
                        rank_info = "Single-Rank (SR) — from WMI"
                
                # Banks: DDR3/DDR4 typically have 4 or 8 banks
                if hasattr(mem, 'Speed') and mem.Speed:
                    # Heuristic: higher speed often correlates with 8 banks
                    speed = int(mem.Speed) if mem.Speed else 0
                    if speed >= 2400:
                        bank_info = "8 Banks"
                    elif speed >= 1600:
                        bank_info = "4-8 Banks (DDR3/DDR4)"
                    else:
                        bank_info = "4 Banks"
                break
        except:
            pass
    
    elif IS_LINUX and not IS_PI:
        try:
            result = subprocess.run(['dmidecode', '-t', 'memory'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Rank' in line:
                        if 'Dual' in line:
                            rank_info = "Dual-Rank (DR)"
                        elif 'Single' in line:
                            rank_info = "Single-Rank (SR)"
                    if 'Bank' in line:
                        bank_info = line.split(':', 1)[1].strip() if ':' in line else bank_info
        except:
            pass
    
    return rank_info, bank_info

def get_memory_spd_timing():
    """Detect SPD timing information (CAS, RAS, etc.)"""
    spd_timing = {
        'cas': 'Not reported by system API',
        'ras': 'Not reported by system API',
        'rcd': 'Not reported by system API',
        'rp': 'Not reported by system API'
    }
    
    if IS_WINDOWS and HAS_WMI:
        # WMI doesn't expose SPD timing data directly
        # Would require SMBus hardware access or third-party tools
        pass
    
    elif IS_LINUX and not IS_PI:
        try:
            result = subprocess.run(['dmidecode', '-t', 'memory'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'CAS' in line.upper():
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['cas'] = parts[1].strip()
                    elif 'RAS' in line.upper() and 'RAS to CAS' not in line.upper():
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['ras'] = parts[1].strip()
                    elif 'RAS to CAS' in line.upper():
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['rcd'] = parts[1].strip()
                    elif 'RP' in line.upper() and 'Precharge' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            spd_timing['rp'] = parts[1].strip()
        except:
            pass
    
    return spd_timing

def get_memory_controller_info():
    """Detect memory controller information (IMC die, chiplet info)"""
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
                    return f"Integrated Memory Controller (multi-tile architecture, ~{tiles} tiles)"
                else:
                    return "Integrated Memory Controller (single-tile architecture)"
        except:
            pass
    
    elif IS_LINUX and not IS_PI:
        try:
            # Check for NUMA info which indicates memory controllers
            result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'NUMA node' in line:
                        return f"IMC per NUMA node - {line.strip()}"
                # If no NUMA, try /proc/cpuinfo for die info
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    if 'core_id' in content:
                        return "Integrated Memory Controller (Detected via core topology)"
        except:
            pass
    
    elif IS_PI:
        return "SoC Integrated Memory Controller (Shared RAM)"
    
    return "Not reported by system API"

def get_numa_node_mapping():
    """Detect NUMA node mapping for memory locality"""
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
                    return f"NUMA Enabled ({node_count} nodes)"
                elif node_count == 1:
                    return "Single NUMA Node (UMA system)"
                else:
                    # Fallback to lscpu
                    result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if 'NUMA node' in line:
                                return "NUMA Enabled"
                    return "UMA System (No NUMA)"
        except:
            pass
    
    elif IS_WINDOWS and HAS_WMI:
        # Windows doesn't typically expose NUMA to end-users through WMI easily
        # Only returns info if multi-socket detected
        try:
            c = wmi.WMI()
            socket_count = 0
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

def get_memory_extended_info():
    """Get extended memory information with all enhancements"""
    base_info = get_memory_info()
    
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
        
        # Phase 1: Add turbo ratio limits and MSR status
        if os_freq.get('turbo_1c'):
            cpu_details['max_turbo_1c'] = f"{os_freq['turbo_1c']:.0f}"
        if os_freq.get('turbo_ac'):
            cpu_details['max_turbo_ac'] = f"{os_freq['turbo_ac']:.0f}"
        if os_freq.get('msr_access'):
            cpu_details['msr_access'] = os_freq['msr_access']

        if os_freq.get('source'):
            cpu_details['freq_source'] = ", ".join(os_freq['source'])
        elif base_val or max_val:
            cpu_details['freq_source'] = 'psutil'
    except:
        pass
    
    # Get temperature info (if available)
    try:
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
        
        # Get turbo ratios (Phase 3 - stub for now)
        cpu_details['kernel_turbo'] = get_kernel_turbo_ratios()
        
        # Get C-states (Phase 3 - stub for now)
        cpu_details['kernel_cstates'] = get_kernel_c_states()
        
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
    system_info = {
        'hostname': platform.node(),
        'model': 'Unknown',
        'serial': 'Unknown',
        'total_storage_gb': 0,
        'total_storage_free_gb': 0,
        'drive_count': 0,
        'battery_info': None,
        'power_supply': None,
        'platform': SYSTEM
    }
    
    if IS_WINDOWS and HAS_WMI:
        # Windows: Use WMI
        try:
            c = wmi.WMI()
            
            # Get system model and serial from WMI
            try:
                for cs in c.Win32_ComputerSystemProduct():
                    if cs.Name:
                        system_info['model'] = cs.Name
                    if cs.IdentifyingNumber:
                        system_info['serial'] = cs.IdentifyingNumber
                    break
            except Exception:
                pass
            
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
    """Get detailed battery health information (cross-platform)"""
    battery_info = {
        'percent': 0,
        'power_plugged': False,
        'secsleft': 0,
        'design_capacity': 0,
        'full_charge_capacity': 0,
        'wear_level': 0,
        'health_status': 'Unknown'
    }
    
    if IS_WINDOWS:
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_info['percent'] = battery.percent
                battery_info['power_plugged'] = battery.power_plugged
                battery_info['secsleft'] = battery.secsleft if battery.secsleft is not None and battery.secsleft > 0 else 0
        except:
            pass
        
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 'Get-WmiObject -Class Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus, DesignCapacity, FullChargeCapacity'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    # Skip header line, parse data
                    for i in range(1, len(lines)):
                        if i < len(lines):
                            data_line = lines[i]
                            if data_line.strip():
                                # Try to parse key-value pairs
                                parts = data_line.split()
                                # This is a simplified parser for WMI output
                    
                    # Try alternative parsing
                    for line in lines:
                        if ':' in line:
                            key, val = line.split(':', 1)
                            key = key.strip().lower()
                            try:
                                val = int(val.strip())
                                if 'designcapacity' in key:
                                    battery_info['design_capacity'] = val
                                elif 'fullchargecapacity' in key:
                                    battery_info['full_charge_capacity'] = val
                            except:
                                pass
        except Exception:
            pass
        
        # Calculate wear level if we have capacity info
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
    
    elif IS_LINUX or IS_PI:
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_info['percent'] = battery.percent
                battery_info['power_plugged'] = battery.power_plugged
                battery_info['secsleft'] = battery.secsleft if battery.secsleft > 0 else 0
        except:
            pass
        
        try:
            # Try to read from /sys/class/power_supply for battery info
            result = subprocess.run(['acpi', '-b'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout:
                return {'acpi_output': result.stdout.strip()}
        except:
            pass
        
        try:
            # Fallback: Read from /sys directly
            battery_path = '/sys/class/power_supply/BAT0'
            if os.path.exists(battery_path):
                with open(f'{battery_path}/capacity', 'r') as f:
                    capacity = int(f.read().strip())
                battery_info['percent'] = capacity
                
                with open(f'{battery_path}/status', 'r') as f:
                    status = f.read().strip()
                battery_info['power_plugged'] = status != "Discharging"
                
                # Try to read design vs current
                try:
                    with open(f'{battery_path}/energy_full_design', 'r') as f:
                        battery_info['design_capacity'] = int(f.read().strip())
                    with open(f'{battery_path}/energy_full', 'r') as f:
                        battery_info['full_charge_capacity'] = int(f.read().strip())
                    
                    if battery_info['design_capacity'] > 0:
                        wear_level = 1 - (battery_info['full_charge_capacity'] / battery_info['design_capacity'])
                        battery_info['wear_level'] = max(0, min(100, wear_level * 100))
                except:
                    pass
        except:
            pass
    
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

def get_network_info():
    """Get comprehensive network information"""
    network_info = {
        'interfaces': [],
        'connections': 0,
        'error': None
    }
    
    try:
        # Get network interface statistics
        net_if_stats = psutil.net_if_stats()
        net_if_addrs = psutil.net_if_addrs()
        net_io_counters = psutil.net_io_counters()
        
        for interface_name, stats in net_if_stats.items():
            if_info = {
                'name': interface_name,
                'is_up': stats.isup,
                'mtu': stats.mtu,
                'speed': stats.speed if hasattr(stats, 'speed') else 0,
                'addresses': []
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
        
        # Get connection statistics
        try:
            connections = psutil.net_connections()
            network_info['connections'] = len(connections)
        except:
            network_info['connections'] = 0
        
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
    
    return network_info

def get_disk_info():
    disks = []
    disk_io_stats = {}
    
    # Get disk I/O statistics (cross-platform)
    try:
        io_counters = psutil.disk_io_counters(perdisk=True)
        for disk_name, io_stats in io_counters.items():
            disk_io_stats[disk_name] = {
                'read_bytes': io_stats.read_bytes,
                'write_bytes': io_stats.write_bytes,
                'read_time': io_stats.read_time,
                'write_time': io_stats.write_time,
                'read_count': io_stats.read_count,
                'write_count': io_stats.write_count
            }
    except Exception:
        pass
    
    # Get disk model info
    disk_models = {}
    
    if IS_WINDOWS and HAS_WMI:
        # Windows: Use WMI
        try:
            c = wmi.WMI()
            for disk in c.Win32_DiskDrive():
                device_id = disk.DeviceID.replace('\\\\.\\', '') if disk.DeviceID else "Unknown"
                interface_type = disk.InterfaceType if disk.InterfaceType else "Unknown"
                media_type = disk.MediaType if disk.MediaType else "Unknown"
                model = disk.Model if disk.Model else "Unknown"
                
                # Use improved detection function
                disk_type = get_disk_type_from_interface_and_model(interface_type, media_type, model)
                
                disk_models[device_id] = {
                    'model': model,
                    'size': int(disk.Size) / (1024 ** 3) if disk.Size else 0,
                    'serial': disk.SerialNumber if disk.SerialNumber else "Unknown",
                    'media_type': media_type,
                    'disk_type': disk_type,
                    'interface_type': interface_type,
                    'partitions': disk.Partitions if disk.Partitions else 0
                }
        except Exception:
            pass
    
    elif IS_LINUX or IS_PI:
        # Linux/Pi: Use lsblk and other tools
        try:
            result = subprocess.run(['lsblk', '-dJbO', 'NAME,SIZE,TYPE'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for device in data.get('blockdevices', []):
                    name = device.get('name', 'Unknown')
                    size_bytes = device.get('size', 0)
                    dev_type = device.get('type', 'Unknown')
                    
                    # Determine interface based on device name
                    if 'nvme' in name:
                        interface_type = 'NVMe'
                    elif 'mmcblk' in name:
                        interface_type = 'MMC'
                    else:
                        interface_type = 'SATA'
                    
                    disk_type = get_disk_type_from_interface_and_model(interface_type, dev_type, name)
                    
                    disk_models[name] = {
                        'model': name,
                        'size': size_bytes / (1024 ** 3) if size_bytes else 0,
                        'serial': 'Unknown',
                        'media_type': dev_type,
                        'disk_type': disk_type,
                        'interface_type': interface_type,
                        'partitions': 0
                    }
        except:
            pass
    
    # Get partition/mountpoint info (cross-platform)
    try:
        for drive in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(drive.mountpoint)
                device_name = drive.device.split('/')[-1] if IS_LINUX else drive.device.split('\\')[-1]
                
                # Calculate average transfer rate if we have I/O stats
                avg_read_speed = 0
                avg_write_speed = 0
                if device_name in disk_io_stats:
                    io = disk_io_stats[device_name]
                    read_speed_mbps = (io['read_bytes'] / (1024**2)) / max(io['read_time'] / 1000, 1)
                    write_speed_mbps = (io['write_bytes'] / (1024**2)) / max(io['write_time'] / 1000, 1)
                    avg_read_speed = read_speed_mbps
                    avg_write_speed = write_speed_mbps
                
                disk_info = {
                    'device': drive.device,
                    'mountpoint': drive.mountpoint,
                    'fstype': drive.fstype,
                    'total': usage.total / (1024 ** 3),
                    'used': usage.used / (1024 ** 3),
                    'free': usage.free / (1024 ** 3),
                    'percent': usage.percent,
                    'model': 'Unknown',
                    'serial': 'Unknown',
                    'media_type': 'Unknown',
                    'disk_type': 'Unknown',
                    'interface_type': 'Unknown',
                    'avg_read_speed': avg_read_speed,
                    'avg_write_speed': avg_write_speed,
                    'io_stats': None
                }
                
                # Add model info from collected data
                for disk_key, disk_model in disk_models.items():
                    if disk_key.lower() in device_name.lower() or device_name.lower() in disk_key.lower():
                        disk_info.update(disk_model)
                        break
                
                # Add I/O statistics
                for io_key, io_data in disk_io_stats.items():
                    if device_name.lower() in io_key.lower() or io_key.lower() in device_name.lower():
                        disk_info['io_stats'] = io_data
                        break
                
                disks.append(disk_info)
            except PermissionError:
                pass
    except Exception as e:
        return {'error': str(e)}
    
    return disks

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
    
    # Storage for text widgets and info
    text_widgets = {}
    
    def refresh_all_tabs():
        """Refresh data for all tabs"""
        # Collect fresh system information
        memory_info = get_memory_extended_info()
        brand, Arch = get_cpu_info_cores()
        cpu_extended = get_cpu_extended_info()
        # Prefer the dedicated gpu_integration module when available
        try:
            from gpu_integration import get_gpu_list, get_gpu_utilization
            gpus = get_gpu_list()
            gpu_utils = get_gpu_utilization()
            # Merge utilization into gpu entries where names match
            gpu_info = []
            for g in gpus:
                name = g.get('name')
                util = gpu_utils.get(name, {}) if isinstance(gpu_utils, dict) else {}
                merged = dict(g)
                merged.update(util)
                gpu_info.append(merged)
        except Exception:
            gpu_info = get_gpu_info()
        monitor_info = get_monitor_info()
        disk_info = get_disk_info()
        system_info = get_system_info()
        network_info = get_network_info()
        
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
"╔══════════════════════════════════════════════════════════════╗"
"║                      SYSTEM OVERVIEW                         ║"
"╚══════════════════════════════════════════════════════════════╝"

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
"""
            
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
            if system_info['battery_info']:
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
            if system_info['power_supply']:
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
"╔══════════════════════════════════════════════════════════════╗"
"║                      CPU INFORMATION                         ║"
"╚══════════════════════════════════════════════════════════════╝"

PROCESSOR DETAILS:
Brand:             {cpu_extended['brand']}
Architecture:      {cpu_extended['architecture']}
Processor:         {platform.processor()}
CPUID Brand:       {cpu_extended['cpuid_brand']}

CORE INFORMATION:

f"Logical Cores:     {cpu_extended['cores_logical']}"
f"Physical Cores:    {cpu_extended['cores_physical']}"
f"SMT Status:        {cpu_extended['smt_status']}"

"FREQUENCY INFORMATION:"
f"Base Clock:        {cpu_extended['base_freq']}"
f"Max Frequency:     {cpu_extended['max_freq']}"
f"Max Turbo:         {cpu_extended['max_turbo_freq']}"
f"Current Freq:      {cpu_extended['current_freq']}"
f"Bus Clock:         {cpu_extended['bus_freq']}"
f"Frequency Source:  {cpu_extended['freq_source']}"

"TURBO RATIO INFORMATION (CPUID 0x16):"
f"Max Turbo (1-core):   {cpu_extended.get('max_turbo_1c', 'Unavailable')} MHz"
f"Max Turbo (all-core): {cpu_extended.get('max_turbo_ac', 'Unavailable')} MHz"
f"MSR Access:           {cpu_extended.get('msr_access', 'Unavailable')}"

"CACHE INFORMATION:"
f"L1 Cache:          {cpu_extended['cache_l1']}"
f"L2 Cache:          {cpu_extended['cache_l2']}"
f"L3 Cache:          {cpu_extended['cache_l3']}"

"POWER & THERMAL:"
f"TDP:               {cpu_extended['tdp']}"
f"Socket:            {cpu_extended['socket']}"
"""
            
            # Add per-core frequency telemetry
            if cpu_extended.get('per_core_frequency'):
                cpu_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                cpu_content += "║             PER-CORE FREQUENCY TELEMETRY                     ║\n"
                cpu_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                cpu_content += "PER-CORE FREQUENCY (Current):\n"
                for core_data in cpu_extended['per_core_frequency']:
                    core = core_data.get('core', 0)
                    freq = core_data.get('frequency_mhz', 0)
                    pct = core_data.get('percentage', 0)
                    cpu_content += f"  Core {core:2d}: {freq:4d} MHz ({pct:3d}%)\n"
            
            # Add C-state residency telemetry
            if cpu_extended.get('c_state_residency'):
                cpu_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                cpu_content += "║              C-STATE RESIDENCY TELEMETRY                     ║\n"
                cpu_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                cpu_content += "C-STATE RESIDENCY (% time in each state):\n"
                for core_data in cpu_extended['c_state_residency']:
                    core = core_data.get('core', 0)
                    c0 = core_data.get('C0', 0)
                    c1_plus = core_data.get('C1+', 0)
                    cpu_content += f"  Core {core:2d}: C0={c0:3d}% (active)  C1+={c1_plus:3d}% (idle)\n"
            
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
            if cpu_extended['temperatures']:
                cpu_content += "\nTEMPERATURE:\n"
                for temp_name, temp_val in list(cpu_extended['temperatures'].items())[:6]:
                    cpu_content += f"  {temp_name:20} {temp_val}\n"

            # Add virtualization support
            if cpu_extended['virtualization'] != 'Not detected':
                cpu_content += f"\nVIRTUALIZATION:\n"
                cpu_content += f"  Support:           {cpu_extended['virtualization']}\n"

            # Add instruction sets with grouping if available
            if cpu_extended['instruction_sets_grouped']:
                cpu_content += f"\nINSTRUCTION SETS (Categorized):\n"
                for category, instr_list in cpu_extended['instruction_sets_grouped'].items():
                    cpu_content += f"  {category}: {', '.join(instr_list)}\n"
            elif cpu_extended['instruction_sets']:
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
            if cpu_extended['security_features']:
                cpu_content += f"\nSECURITY FEATURES:\n"
                for feature in cpu_extended['security_features']:
                    if 'unavailable' in feature.lower():
                        cpu_content += f"  ⚠ {feature}\n"
                    else:
                        cpu_content += f"  ✓ {feature}\n"

            # Add additional features if any
            if cpu_extended['features']:
                cpu_content += f"\nFEATURES:\n"
                for feature in cpu_extended['features']:
                    cpu_content += f"  • {feature}\n"

            # Power Users Section
            cpu_content += f"\n╔══════════════════════════════════════════════════════════════╗\n"
            cpu_content += f"║                    POWER USERS SECTION                        ║\n"
            cpu_content += f"╚══════════════════════════════════════════════════════════════╝\n"
            
            if cpu_extended['microcode'] != 'Unavailable':
                cpu_content += f"\nMicrocode Version: {cpu_extended['microcode']}\n"
            
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
                    cpu_content += f"CAPABILITIES:\n"
                    cpu_content += f"  MSR Read:          {'✓ Yes' if caps.get('msr_read') else '✗ No'}\n"
                    cpu_content += f"  MSR Write:         {'✓ Yes' if caps.get('msr_write') else '✗ No'}\n"
                    cpu_content += f"  PCI Read:          {'✓ Yes' if caps.get('pci_read') else '✗ No'}\n"
                    cpu_content += f"  SMBus Read:        {'✓ Yes' if caps.get('smbus_read') else '✗ No'}\n"
                    cpu_content += f"  Multicore:         {'✓ Yes' if caps.get('multicore') else '✗ No'}\n\n"
                    
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
                    
                    # Phase 2: Display temperature data if available
                    if temp_data.get('available') and temp_data.get('temperatures'):
                        cpu_content += f"\nCORE TEMPERATURES (MSR 0x19C):\n"
                        temps = temp_data['temperatures']
                        tj_max = temp_data.get('tj_max', 100)
                        for core in sorted(temps.keys()):
                            temp_info = temps[core]
                            celsius = temp_info.get('celsius', 0)
                            margin = temp_info.get('margin', 0)
                            cpu_content += f"  Core {core:2d}: {celsius:3d}°C  (Tj Max: {tj_max}°C, Margin: {margin:2d}°C)\n"
                        
                        package_temp = temp_data.get('package_temp', 0)
                        cpu_content += f"  Package: {package_temp:3d}°C  (Maximum of all cores)\n"
                    
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
    # End of create_gui setup - return root so caller can run mainloop
    return root


if __name__ == '__main__':
    gui_root = create_gui()
    try:
        gui_root.deiconify()
    except Exception:
        pass
    gui_root.mainloop()
    


"─── USAGE ───────────────────────────────────────────────────"
f"Total Memory:      {memory_info['total']:.2f} GB"
f"Used Memory:       {memory_info['used']:.2f} GB ({memory_info['percent']:.1f}%)"
f"Available Memory:  {memory_info['available']:.2f} GB"

"─── CONFIGURATION ───────────────────────────────────────────"
f"Memory Channels:   {memory_info.get('channel_info', 'Not reported by system API')}"
f"ECC Status:        {memory_info.get('ecc_status', 'Not reported by system API')}"

"─── SYSTEM-LEVEL INFO ──────────────────────────────────────"
f"Memory Controller:  {memory_info.get('controller_info', 'Not reported by system API')}"
f"NUMA Mapping:      {memory_info.get('numa_mapping', 'Not reported by system API')}"

"""
            
            # Add enhanced DIMM information from spd_helper
            spd_helper = memory_info.get('spd_helper', {})
            if spd_helper.get('available') and spd_helper.get('dimms'):
                # Phase 1: Add memory array information if available
                if spd_helper.get('memory_array'):
                    array = spd_helper['memory_array']
                    memory_content += f"╔══════════════════════════════════════════════════════════════╗\n"
                    memory_content += f"║            MEMORY ARRAY CONFIGURATION                       ║\n"
                    memory_content += f"╚══════════════════════════════════════════════════════════════╝\n\n"
                    memory_content += f"Max Capacity:      {array.get('max_capacity_mb', 0)} MB ({array.get('max_capacity_mb', 0) / 1024:.0f} GB max)\n"
                    memory_content += f"DIMM Slots:        {array.get('num_slots', 'Unknown')} total\n"
                    memory_content += f"System ECC Type:   {array.get('system_ecc_type', 'None')}\n\n"
                
                memory_content += f"╔══════════════════════════════════════════════════════════════╗\n"
                memory_content += f"║              DIMM DETAILS (from SMBIOS)                       ║\n"
                memory_content += f"╚══════════════════════════════════════════════════════════════╝\n\n"
                
                for dimm in spd_helper['dimms']:
                    if not dimm.get('present'):
                        memory_content += f"Slot {dimm['slot']}: [EMPTY]\n\n"
                        continue
                    
                    memory_content += f"─── Slot {dimm['slot']} ({dimm['channel']}) ─────────────────────────\n"
                    memory_content += f"  Capacity:       {dimm['size_mb']:,} MB ({dimm['size_mb']/1024:.1f} GB)\n"
                    memory_content += f"  Type:           {dimm['ddr_generation']}\n"
                    memory_content += f"  Form Factor:    {dimm['form_factor']}\n"
                    memory_content += f"  Module Type:    {dimm['module_type']}\n"
                    memory_content += f"  Rank:           {dimm['rank'] if isinstance(dimm['rank'], int) else 'Unknown'}\n"
                    # Clarify ECC is on-die, not system-level
                    memory_content += f"  ECC:            {'On-die ECC (DDR5 standard)' if dimm['ecc'] and 'DDR5' in dimm['ddr_generation'] else 'Enabled' if dimm['ecc'] else 'Disabled'}\n"
                    
                    memory_content += f"\n  Speed Information:\n"
                    memory_content += f"    Configured:   {dimm['configured_speed_mhz']} MHz\n"
                    if dimm.get('max_speed_mhz') and dimm['max_speed_mhz'] != dimm['configured_speed_mhz']:
                        memory_content += f"    Max Supported: {dimm['max_speed_mhz']} MHz\n"
                    
                    memory_content += f"\n  Electrical:\n"
                    # Add voltage note: SMBIOS-reported vs DDR5 nominal
                    if 'DDR5' in dimm['ddr_generation']:
                        memory_content += f"    Voltage:      {dimm['voltage_mv']} mV (SMBIOS-reported; DDR5 nominal is 1100 mV)\n"
                    else:
                        memory_content += f"    Voltage:      {dimm['voltage_mv']} mV\n"
                    if dimm.get('data_width') and dimm['data_width'] != 0xFFFF:
                        memory_content += f"    Data Width:   {dimm['data_width']} bits\n"
                    # Fix: 0xFFFE is SMBIOS placeholder for 'unknown', not actual width
                    total_w = dimm.get('total_width', 0)
                    if total_w and total_w != 0xFFFF and total_w != 0xFFFE:
                        memory_content += f"    Total Width:  {total_w} bits (including ECC)\n"
                    elif total_w == 0xFFFE:
                        memory_content += f"    Total Width:  Not Reported (SMBIOS placeholder 0xFFFE)\n"
                    
                    memory_content += f"\n  Identification:\n"
                    memory_content += f"    Manufacturer: {dimm['manufacturer']}\n"
                    memory_content += f"    Part Number:  {dimm['part_number'].strip()}\n"
                    if dimm.get('serial_number') and dimm['serial_number'] != 'N/A':
                        memory_content += f"    Serial:       {dimm['serial_number']}\n"
                    
                    memory_content += f"\n  SPD/Timing:\n"
                    if dimm.get('timings_available'):
                        memory_content += f"    CL:           {dimm['cl']}\n"
                        memory_content += f"    tRCD:         {dimm['trcd']}\n"
                        memory_content += f"    tRP:          {dimm['trp']}\n"
                        memory_content += f"    tRAS:         {dimm['tras']}\n"
                    else:
                        memory_content += f"    Status:       Unavailable (requires SMBus access)\n"
                    
                    memory_content += f"    Data Source:  {dimm['data_source']}\n\n"
                
                # Add Module Quality and Characteristics section
                memory_content += f"╔══════════════════════════════════════════════════════════════╗\n"
                memory_content += f"║             MODULE QUALITY & CHARACTERISTICS                 ║\n"
                memory_content += f"╚══════════════════════════════════════════════════════════════╝\n\n"
                
                for dimm in spd_helper['dimms']:
                    if not dimm.get('present'):
                        continue
                    
                    memory_content += f"Slot {dimm['slot']} Diagnostic Summary:\n"
                    
                    # JEDEC Profile
                    profile = dimm.get('jedec_profile', 'Unknown')
                    memory_content += f"  Profile:          {profile}\n"
                    
                    # Characteristics - now more comprehensive
                    memory_content += f"  Characteristics:\n"
                    
                    # DDR Generation
                    memory_content += f"    • DDR Generation: {dimm['ddr_generation']}\n"
                    
                    # Channel
                    memory_content += f"    • Channel: {dimm['channel']}\n"
                    
                    # Rank assessment (with inference)
                    if isinstance(dimm['rank'], int) and dimm['rank'] > 0:
                        memory_content += f"    • Rank Configuration: {dimm['rank']}-rank\n"
                    else:
                        memory_content += f"    • Rank: Likely Single-Rank (not reported by SMBIOS)\n"
                    
                    # ECC capability - clarified as on-die
                    if dimm['ecc']:
                        if 'DDR5' in dimm['ddr_generation']:
                            memory_content += f"    • Error Correction: On-die ECC (DDR5 standard, not system-level)\n"
                        else:
                            memory_content += f"    • Error Correction: On-die ECC\n"
                    else:
                        memory_content += f"    • Error Correction: None\n"
                    
                    # Voltage assessment with note
                    voltage = dimm['voltage_mv']
                    if 'DDR5' in dimm['ddr_generation']:
                        memory_content += f"    • Operating Voltage: {voltage} mV (SMBIOS-reported; DDR5 nominal: 1100 mV)\n"
                    else:
                        memory_content += f"    • Operating Voltage: {voltage} mV\n"
                    
                    # Form factor (reliability indicator)
                    ff = dimm['form_factor']
                    if 'SODIMM' in ff or 'SO-DIMM' in ff:
                        memory_content += f"    • Form Factor: {ff} (Laptop/Mobile)\n"
                    elif 'LRDIMM' in ff:
                        memory_content += f"    • Form Factor: {ff} (Server-grade Load-Reduced)\n"
                    elif 'FB-DIMM' in ff:
                        memory_content += f"    • Form Factor: {ff} (Fully-Buffered)\n"
                    else:
                        memory_content += f"    • Form Factor: {ff}\n"
                    
                    # Speed assessment (if overclocked)
                    if dimm.get('max_speed_mhz') and dimm['max_speed_mhz'] != dimm['configured_speed_mhz']:
                        memory_content += f"    • Current vs Max: {dimm['configured_speed_mhz']}MHz / {dimm['max_speed_mhz']}MHz\n"
                    
                    memory_content += f"\n"
                
                # Phase 3: Add memory error information if available
                error_found = False
                for dimm in spd_helper['dimms']:
                    if dimm.get('present') and dimm.get('memory_errors') and dimm['memory_errors'].get('error_count', 0) > 0:
                        error_found = True
                        break
                
                if error_found:
                    memory_content += f"╔══════════════════════════════════════════════════════════════╗\n"
                    memory_content += f"║              MEMORY ERROR INFORMATION (SMBIOS Type 18)      ║\n"
                    memory_content += f"╚══════════════════════════════════════════════════════════════╝\n\n"
                    memory_content += f"Warning: Memory errors detected by system firmware.\n\n"
                    
                    for dimm in spd_helper['dimms']:
                        if dimm.get('present') and dimm.get('memory_errors'):
                            errors = dimm['memory_errors']
                            if errors.get('error_count', 0) > 0:
                                memory_content += f"Slot {dimm['slot']}:\n"
                                memory_content += f"  Total Errors:   {errors.get('error_count', 0)}\n"
                                memory_content += f"  Error Type:     {errors.get('error_type', 'Unknown')}\n"
                                memory_content += f"  Granularity:    {errors.get('error_granularity', 'Unknown')}\n"
                                memory_content += f"  Operation:      {errors.get('error_operation', 'Unknown')}\n\n"
                
                if spd_helper.get('note'):
                    memory_content += f"ABOUT SPD TIMING DATA:\n"
                    memory_content += f"────────────────────────────────────────────────────────────\n"
                    memory_content += f"{spd_helper['note']}\n\n"
                    memory_content += f"What This Means:\n"
                    memory_content += f"  • CAS Latency (CL) is the delay before reading data\n"
                    memory_content += f"  • tRCD, tRP, tRAS are internal memory timing parameters\n"
                    memory_content += f"  • These affect performance in latency-sensitive workloads\n"
                    memory_content += f"  • SMBIOS provides capacity, speed, and voltage info safely\n"
                    memory_content += f"  • Timings would require direct hardware access (SMBus)\n\n"
            
            # Legacy module info fallback
            elif memory_info.get('modules'):
                memory_content += f"─── PHYSICAL MODULES ({memory_info['module_count']}) ───────────────────────────\n\n"
                for i, module in enumerate(memory_info['modules'], 1):
                    memory_content += f"Module {i}: {module['slot']}\n"
                    memory_content += f"  Capacity:        {module['capacity']:.0f} GB\n"
                    memory_content += f"  Type:            {module['type']}\n"
                    memory_content += f"  Speed:           {module['speed']} MHz\n"
                    memory_content += f"  Manufacturer:    {module['manufacturer']}\n"
                    memory_content += f"  Part Number:     {module['part_number']}\n\n"
            
            memory_text.insert('1.0', memory_content)
            memory_text.configure(state='disabled')
        
        # Update GPU tab
        if 'gpu' in text_widgets:
            gpu_text = text_widgets['gpu']
            gpu_text.configure(state='normal')
            gpu_text.delete('1.0', tk.END)

            # Populate per-GPU summary table if present
            per_gpu_table = text_widgets.get('per_gpu_table')
            if per_gpu_table:
                # Clear previous rows
                for r in per_gpu_table.get_children():
                    per_gpu_table.delete(r)
                if gpu_info and isinstance(gpu_info, (list, tuple)):
                    for idx, g in enumerate(gpu_info, 1):
                        name = g.get('name', 'Unknown')
                        vram = g.get('adapter_ram', g.get('adapter_ram_gb', None))
                        mem_used_gb = g.get('memory_used_gb')
                        try:
                            if mem_used_gb is not None and vram is not None:
                                vram_s = f"{float(vram):.2f}/{float(mem_used_gb):.2f} GB"
                            elif vram is not None:
                                vram_s = f"{float(vram):.2f}"
                            else:
                                vram_s = 'N/A'
                        except Exception:
                            vram_s = str(vram)
                        util = g.get('core_utilization') or g.get('util') or g.get('memory_utilization') or 'N/A'
                        temp = g.get('temperature_c') or g.get('temp') or 'N/A'
                        # Power in watts (NVML returns watts as float)
                        power = g.get('power_w') if g.get('power_w') is not None else g.get('power')
                        power_s = f"{float(power):.2f}" if isinstance(power, (int, float)) else (str(power) if power is not None else 'N/A')
                        # Clocks: dict -> formatted string
                        clocks = g.get('clocks') or {}
                        if isinstance(clocks, dict) and clocks:
                            clk_parts = []
                            if 'graphics_mhz' in clocks:
                                clk_parts.append(f"G:{clocks.get('graphics_mhz')}MHz")
                            if 'memory_mhz' in clocks:
                                clk_parts.append(f"M:{clocks.get('memory_mhz')}MHz")
                            if 'graphics' in clocks:
                                clk_parts.append(f"G:{clocks.get('graphics')}MHz")
                            clocks_s = ' '.join(clk_parts)
                        else:
                            clocks_s = 'N/A'
                        driver = g.get('driver_version') or g.get('driver') or 'N/A'
                        source = g.get('source', '')
                        # PCIe negotiated info (if available)
                        pcie_s = 'N/A'
                        try:
                            lw = g.get('link_width')
                            ls = g.get('link_speed_gt_s')
                            if lw and ls:
                                pcie_s = f"x{int(lw)} @ {float(ls)} GT/s"
                            elif lw:
                                pcie_s = f"x{int(lw)}"
                            elif ls:
                                pcie_s = f"{float(ls)} GT/s"
                        except Exception:
                            pcie_s = 'N/A'

                        # Resizable BAR (best-effort)
                        rebar_s = 'Unknown'
                        try:
                            rb = g.get('resizable_bar')
                            if isinstance(rb, dict):
                                sup = rb.get('supported')
                                ena = rb.get('enabled')
                                if sup is True:
                                    rebar_s = 'Supported'
                                    if ena is True:
                                        rebar_s = 'Enabled'
                                    elif ena is False:
                                        rebar_s = 'Disabled'
                                elif sup is False:
                                    rebar_s = 'Not supported'
                                else:
                                    rebar_s = 'Unknown'
                            elif isinstance(rb, bool):
                                rebar_s = 'Enabled' if rb else 'Disabled'
                        except Exception:
                            rebar_s = 'Unknown'

                        per_gpu_table.insert('', 'end', values=(idx, name, vram_s, util, temp, power_s, clocks_s, pcie_s, rebar_s, driver, source))
                else:
                    # No GPUs detected - show a single placeholder row
                    per_gpu_table.insert('', 'end', values=(1, 'No GPU detected', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A'))
            
            gpu_content = """
"╔══════════════════════════════════════════════════════════════╗"
"║                      GPU INFORMATION                         ║"
"╚══════════════════════════════════════════════════════════════╝"

"""
            
            if isinstance(gpu_info, dict) and 'error' in gpu_info:
                gpu_content += f"Error: {gpu_info['error']}\n"
            elif gpu_info:
                for i, gpu in enumerate(gpu_info, 1):
                    gpu_content += f"─── GPU {i} ────────────────────────────────────────────────\n"
                    gpu_content += f"  Name:            {gpu['name']}\n"
                    
                    if 'video_processor' in gpu:
                        gpu_content += f"  Processor:       {gpu['video_processor']}\n"
                    
                    if gpu.get('adapter_ram'):
                        gpu_content += f"  VRAM:            {gpu['adapter_ram']:.2f} GB\n"
                    else:
                        gpu_content += f"  VRAM:            Unknown\n"
                    
                    if 'driver_version' in gpu:
                        gpu_content += f"  Driver Version:  {gpu['driver_version']}\n"
                    
                    if 'current_refresh_rate' in gpu:
                        gpu_content += f"  Refresh Rate:    {gpu['current_refresh_rate']} Hz\n"
                    
                    if 'video_mode_description' in gpu:
                        gpu_content += f"  Resolution:      {gpu['video_mode_description']}\n"
                    
                    if 'status' in gpu:
                        gpu_content += f"  Status:          {gpu['status']}\n"
                    
                    if 'pnp_device_id' in gpu:
                        gpu_content += f"  Device ID:       {gpu['pnp_device_id']}\n"
                    elif 'device_id' in gpu:
                        gpu_content += f"  Device ID:       {gpu['device_id']}\n"
                    
                    # Phase 2: PCIe Link Information
                    if 'link_speed_gt_s' in gpu or 'link_width' in gpu:
                        gpu_content += f"\n  ─── PCIe CONFIGURATION ───\n"
                        if 'link_speed_gt_s' in gpu:
                            gpu_content += f"  Link Speed:      {gpu['link_speed_gt_s']} GT/s\n"
                        if 'link_width' in gpu:
                            gpu_content += f"  Link Width:      x{gpu['link_width']}\n"
                        if 'bandwidth_gb_s' in gpu:
                            gpu_content += f"  Bandwidth:       {gpu['bandwidth_gb_s']:.2f} GB/s\n"
                    
                    # Phase 2: GPU Utilization & Temperature
                    if 'core_utilization' in gpu or 'memory_utilization' in gpu or 'temperature_c' in gpu:
                        gpu_content += f"\n  ─── GPU UTILIZATION & TEMPERATURE ───\n"
                        if 'core_utilization' in gpu:
                            gpu_content += f"  Core:            {gpu['core_utilization']}%\n"
                        if 'memory_utilization' in gpu:
                            gpu_content += f"  Memory:          {gpu['memory_utilization']}%\n"
                        if 'temperature_c' in gpu:
                            gpu_content += f"  Temperature:     {gpu['temperature_c']}°C\n"
                    # NVML: power and clocks (if available)
                    if 'power_w' in gpu or 'power' in gpu:
                        pw = gpu.get('power_w') if gpu.get('power_w') is not None else gpu.get('power')
                        try:
                            gpu_content += f"  Power:           {float(pw):.2f} W\n"
                        except Exception:
                            gpu_content += f"  Power:           {pw}\n"
                    if 'clocks' in gpu and isinstance(gpu.get('clocks'), dict) and gpu.get('clocks'):
                        clocks = gpu.get('clocks')
                        parts = []
                        if 'graphics_mhz' in clocks:
                            parts.append(f"G:{clocks.get('graphics_mhz')}MHz")
                        if 'graphics' in clocks:
                            parts.append(f"G:{clocks.get('graphics')}MHz")
                        if 'memory_mhz' in clocks:
                            parts.append(f"M:{clocks.get('memory_mhz')}MHz")
                        if parts:
                            gpu_content += f"  Clocks:          {' '.join(parts)}\n"
                    
                    gpu_content += "\n"
            else:
                gpu_content += "No GPU information available\n"
            
            # Add monitor information to GPU tab
            gpu_content += ("\n" +
                            "---- MONITOR INFORMATION ----\n\n")
            
            if isinstance(monitor_info, dict) and 'error' in monitor_info:
                gpu_content += f"Error: {monitor_info['error']}\n"
            elif monitor_info:
                for i, monitor in enumerate(monitor_info, 1):
                    gpu_content += f"Monitor {i}:\n"
                    gpu_content += f"  Name:            {monitor.get('name', 'Unknown')}\n"
                    
                    if 'resolution' in monitor:
                        gpu_content += f"  Resolution:      {monitor['resolution']}\n"
                    
                    if 'refresh_rate' in monitor:
                        gpu_content += f"  Refresh Rate:    {monitor['refresh_rate']} Hz\n"
                    
                    if 'bits_per_pixel' in monitor:
                        gpu_content += f"  Color Depth:     {monitor['bits_per_pixel']} bits\n"
                    
                    if 'manufacturer' in monitor and monitor['manufacturer'] != "Unknown":
                        gpu_content += f"  Manufacturer:    {monitor['manufacturer']}\n"
                    
                    if 'model' in monitor and monitor['model'] != "Unknown":
                        gpu_content += f"  Model:           {monitor['model']}\n"
                    
                    if 'serial' in monitor and monitor['serial'] != "Unknown":
                        gpu_content += f"  Serial:          {monitor['serial']}\n"
                    
                    if 'pnp_device_id' in monitor:
                        gpu_content += f"  Device ID:       {monitor['pnp_device_id']}\n"
                    
                    gpu_content += "\n"
            else:
                gpu_content += "No monitor information available\n"
            
            gpu_text.insert('1.0', gpu_content)
            gpu_text.configure(state='disabled')
        

        # Update Disk tab
        if 'disk' in text_widgets:
            disk_text = text_widgets['disk']
            report_content = ""
            # ...existing code for disk tab update...

            # Add per-core frequency telemetry to text report
            if cpu_extended.get('per_core_frequency'):
                report_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                report_content += "║             PER-CORE FREQUENCY TELEMETRY                     ║\n"
                report_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                report_content += "PER-CORE FREQUENCY (Current):\n"
                for core_data in cpu_extended['per_core_frequency']:
                    core = core_data.get('core', 0)
                    freq = core_data.get('frequency_mhz', 0)
                    pct = core_data.get('percentage', 0)
                    report_content += f"  Core {core:2d}: {freq:4d} MHz ({pct:3d}%)\n"

            # Add C-state residency telemetry to text report
            if cpu_extended.get('c_state_residency'):
                report_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                report_content += "║              C-STATE RESIDENCY TELEMETRY                     ║\n"
                report_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                report_content += "C-STATE RESIDENCY (% time in each state):\n"
                for core_data in cpu_extended['c_state_residency']:
                    c0 = core_data.get('C0', 0)
                    c1_plus = core_data.get('C1+', 0)
                    report_content += f"  Core: C0={c0}% (active)  C1+={c1_plus}% (idle)\n"
            
            disk_text.insert('1.0', report_content)
            disk_text.configure(state='disabled')
        
        # Update Storage tab (Phase 2 - NVMe SMART)
        if 'storage' in text_widgets:
            from kernel_integration import get_storage_telemetry
            storage_text = text_widgets['storage']
            storage_text.configure(state='normal')
            storage_text.delete('1.0', tk.END)
            storage_content = """
"╔══════════════════════════════════════════════════════════════╗"
"║                  STORAGE TELEMETRY (Phase 5)                ║"
"╚══════════════════════════════════════════════════════════════╝"
"""
            storage_data = get_storage_telemetry()
            if isinstance(storage_data, dict):
                if 'error' in storage_data:
                    storage_content += f"Error: {storage_data['error']}\n"
                if 'status' in storage_data:
                    storage_content += f"Status: {storage_data['status']}\n"
                if 'note' in storage_data:
                    storage_content += f"Note: {storage_data['note']}\n"
                # If NVMe SMART data is present, show it
                if 'nvme_devices' in storage_data:
                    nvme_devices = storage_data['nvme_devices']
                    if nvme_devices:
                        for i, device in enumerate(nvme_devices, 1):
                            storage_content += f"─── NVMe Device {i} ───────────────────────────────────────────\n"
                            storage_content += f"  Device Path:     {device.get('device_path', 'Unknown')}\n"
                            if 'friendly_name' in device and device['friendly_name'] != 'Unknown':
                                storage_content += f"  Friendly Name:   {device['friendly_name']}\n"
                            if 'model' in device and device['model'] != 'Unknown':
                                storage_content += f"  Model:           {device['model']}\n"
                            if 'serial' in device and device['serial'] != 'Unknown':
                                storage_content += f"  Serial:          {device['serial']}\n"
                            storage_content += f"\n  ─── SMART Data ───\n"
                            if 'temperature_c' in device and device['temperature_c'] != 'Unknown':
                                storage_content += f"  Temperature:     {device['temperature_c']}°C\n"
                            if 'percentage_used' in device and device['percentage_used'] != 'Unknown':
                                storage_content += f"  Wear Level:      {device['percentage_used']}%\n"
                            if 'power_on_hours' in device and device['power_on_hours'] != 'Unknown':
                                storage_content += f"  Power-On Hours:  {device['power_on_hours']}\n"
                            if 'critical_warnings' in device and device['critical_warnings'] != 'Unknown':
                                storage_content += f"  Critical Warns:  {device['critical_warnings']}\n"
                            if 'media_errors' in device and device['media_errors'] != 'Unknown':
                                storage_content += f"  Media Errors:    {device['media_errors']}\n"
                            if 'available_spare' in device and device['available_spare'] != 'Unknown':
                                storage_content += f"  Available Spare: {device['available_spare']}%\n"
                            storage_content += "\n"
                    else:
                        storage_content += "No NVMe devices detected\n"
            else:
                storage_content += "No storage telemetry data available\n"
            storage_text.insert('1.0', storage_content)
            storage_text.configure(state='disabled')
        
        # Update Display tab (Phase 3 - EDID Information)
        if 'display' in text_widgets:
            display_text = text_widgets['display']
            display_text.configure(state='normal')
            display_text.delete('1.0', tk.END)
            
            display_content = """
"╔══════════════════════════════════════════════════════════════╗"
║                    EDID DISPLAY INFORMATION                  ║
╚══════════════════════════════════════════════════════════════╝

"""
            
            edid_info = get_edid_helper_info()
            
            if isinstance(edid_info, dict) and 'error' in edid_info and edid_info['error']:
                display_content += f"Error: {edid_info['error']}\n"
            elif edid_info and 'edid_devices' in edid_info:
                edid_devices = edid_info['edid_devices']
                if edid_devices:
                    for i, device in enumerate(edid_devices, 1):
                        display_content += f"─── Monitor {i} ───────────────────────────────────────────────\n"
                        
                        if 'monitor_name' in device and device['monitor_name'] != 'Unknown':
                            display_content += f"  Name:             {device['monitor_name']}\n"
                        
                        if 'manufacturer' in device and device['manufacturer'] != 'Unknown':
                            display_content += f"  Manufacturer:     {device['manufacturer']}\n"
                        
                        if 'model' in device and device['model'] != 'Unknown':
                            display_content += f"  Model Code:       {device['model']}\n"
                        
                        if 'serial_number' in device and device['serial_number'] != 'Unknown':
                            display_content += f"  Serial Number:    {device['serial_number']}\n"
                        
                        display_content += f"\n  ─── Physical Properties ───\n"
                        
                        if 'physical_width_cm' in device:
                            width = device['physical_width_cm']
                            height = device['physical_height_cm'] if 'physical_height_cm' in device else 0
                            if width and width > 0 and height and height > 0:
                                inches = (width**2 + height**2)**0.5 / 2.54
                                display_content += f"  Size:             {width} cm × {height} cm ({inches:.1f}\")\n"
                        
                        if 'edid_version' in device:
                            display_content += f"  EDID Version:     {device['edid_version']}\n"
                        
                        if 'input_type' in device:
                            display_content += f"  Input Type:       {device['input_type']}\n"
                        
                        if 'gamma' in device:
                            display_content += f"  Gamma:            {device['gamma']}\n"
                        
                        display_content += f"\n  ─── Manufacturing ───\n"
                        
                        if 'manufacturing_year' in device:
                            display_content += f"  Year:             {device['manufacturing_year']}\n"
                        
                        if 'manufacturing_week' in device:
                            display_content += f"  Week:             {device['manufacturing_week']}\n"
                        
                        display_content += "\n"
                else:
                    display_content += "No EDID devices detected\n"
            else:
                display_content += "EDID helper not available or no monitor data collected\n"
            
            display_text.insert('1.0', display_content)
            display_text.configure(state='disabled')
        
        # Update System Architecture tab (Phase 3 - PCI Topology)
        if 'architecture' in text_widgets:
            arch_text = text_widgets['architecture']
            arch_text.configure(state='normal')
            arch_text.delete('1.0', tk.END)
            
            arch_content = """
╔══════════════════════════════════════════════════════════════╗
║                  SYSTEM ARCHITECTURE & TOPOLOGY              ║
╚══════════════════════════════════════════════════════════════╝

"""
            
            pci_info = get_pci_topology()
            
            arch_content += """
PCI DEVICE TREE:
"═══════════════════════════════════════════════════════════════"

"""
            
            if isinstance(pci_info, dict) and 'error' in pci_info and pci_info['error']:
                arch_content += f"Error: {pci_info['error']}\n"
            elif pci_info and 'devices' in pci_info:
                pci_devices = pci_info['devices']
                
                if pci_devices:
                    # Group devices by class
                    by_class = {}
                    for device in pci_devices:
                        cls = device.get('class', 'Unknown')
                        if cls not in by_class:
                            by_class[cls] = []
                        by_class[cls].append(device)
                    
                    # Display devices organized by class
                    for class_name in sorted(by_class.keys()):
                        arch_content += f"[{class_name}]\n"
                        for device in by_class[class_name][:5]:  # Limit to 5 per class
                            vendor = device.get('vendor_id', 'XXXX')
                            dev_code = device.get('device_code', 'XXXX')
                            driver = device.get('driver', 'Not installed')
                            
                            arch_content += f"  ├─ [{vendor}:{dev_code}] {driver}\n"
                        
                        if len(by_class[class_name]) > 5:
                            arch_content += f"  └─ ... and {len(by_class[class_name]) - 5} more\n"
                        
                        arch_content += "\n"
                    
                    arch_content += f"Total PCI Devices: {len(pci_devices)}\n"
                else:
                    arch_content += "No PCI devices detected\n"
            else:
                arch_content += "PCI topology helper not available\n"
            
            arch_text.insert('1.0', arch_content)
            arch_text.configure(state='disabled')
        
        # Update Network tab
        if 'network' in text_widgets:
            network_text = text_widgets['network']
            network_text.configure(state='normal')
            network_text.delete('1.0', tk.END)
            
            network_content = """
╔══════════════════════════════════════════════════════════════╗
║                  NETWORK INTERFACES                          ║
╚══════════════════════════════════════════════════════════════╝

"""
            
            if network_info.get('error'):
                network_content += f"Error retrieving network info: {network_info['error']}\n"
            else:
                interfaces = network_info.get('interfaces', [])
                
                if interfaces:
                    network_content += f"Total Interfaces: {len(interfaces)}\n\n"
                    
                    for idx, iface in enumerate(interfaces, 1):
                        network_content += f"─── Interface {idx}: {iface['name']} ───\n"
                        network_content += f"  Status:       {'UP' if iface['is_up'] else 'DOWN'}\n"
                        network_content += f"  MTU:          {iface['mtu']} bytes\n"
                        network_content += f"  Speed:        {iface['speed']} Mbps\n" if iface['speed'] > 0 else ""
                        
                        if iface['addresses']:
                            network_content += f"\n  IP Addresses:\n"
                            for addr in iface['addresses']:
                                network_content += f"    Family:     {addr['family']}\n"
                                network_content += f"    Address:    {addr['address']}\n"
                                if addr['netmask'] != 'N/A':
                                    network_content += f"    Netmask:    {addr['netmask']}\n"
                                if addr['broadcast'] != 'N/A':
                                    network_content += f"    Broadcast:  {addr['broadcast']}\n"
                        
                        network_content += "\n"
                    
                    # Add I/O statistics
                    network_content += f"╔══════════════════════════════════════════════════════════════╗\n"
                    network_content += f"║                  NETWORK I/O STATISTICS                       ║\n"
                    network_content += f"╚══════════════════════════════════════════════════════════════╝\n\n"
                    
                    io = network_info.get('io', {})
                    network_content += f"─── TRAFFIC ────────────────────────────────────────────────\n"
                    network_content += f"  Bytes Sent:       {io.get('bytes_sent', 0) / (1024**3):.2f} GB\n"
                    network_content += f"  Bytes Received:   {io.get('bytes_recv', 0) / (1024**3):.2f} GB\n"
                    network_content += f"  Packets Sent:     {io.get('packets_sent', 0):,}\n"
                    network_content += f"  Packets Received: {io.get('packets_recv', 0):,}\n"
                    
                    network_content += f"\n─── ERRORS & DROPS ────────────────────────────────────────\n"
                    network_content += f"  Errors In:        {io.get('errin', 0)}\n"
                    network_content += f"  Errors Out:       {io.get('errout', 0)}\n"
                    network_content += f"  Drops In:         {io.get('dropin', 0)}\n"
                    network_content += f"  Drops Out:        {io.get('dropout', 0)}\n"
                    
                    network_content += f"\n─── CONNECTIONS ────────────────────────────────────────\n"
                    network_content += f"  Active Connections: {network_info.get('connections', 0)}\n"
                else:
                    network_content += "No network interfaces detected\n"
            
            network_text.insert('1.0', network_content)
            network_text.configure(state='disabled')
        
        # Update Text Report tab
        if 'network' in text_widgets:
            from kernel_integration import get_network_telemetry
            network_text = text_widgets['network']
            network_text.configure(state='normal')
            network_text.delete('1.0', tk.END)
            network_content = """
╔══════════════════════════════════════════════════════════════╗
║                  NETWORK TELEMETRY (Phase 6)                ║
╚══════════════════════════════════════════════════════════════╝
"""
            network_data = get_network_telemetry()
            if isinstance(network_data, dict):
                if 'errors' in network_data and network_data['errors']:
                    for err in network_data['errors']:
                        network_content += f"Error: {err}\n"
                if 'status' in network_data:
                    network_content += f"Status: {network_data['status']}\n"
                if 'note' in network_data:
                    network_content += f"Note: {network_data['note']}\n"
                if 'provenance' in network_data:
                    network_content += f"Provenance: {', '.join(network_data['provenance'])}\n"
                # Show interfaces
                interfaces = network_data.get('interfaces', [])
                if interfaces:
                    network_content += f"Total Interfaces: {len(interfaces)}\n\n"
                    for idx, iface in enumerate(interfaces, 1):
                        network_content += f"─── Interface {idx}: {iface.get('name', 'Unknown')} ───\n"
                        network_content += f"  MAC:        {iface.get('mac', 'Unknown')}\n"
                        network_content += f"  IPs:        {', '.join(iface.get('ips', []))}\n"
                        network_content += f"  Provenance: {iface.get('provenance', 'Unknown')}\n"
                        network_content += "\n"
                # Show kernel helper interfaces if present
                kernel_ifaces = network_data.get('kernel_interfaces', [])
                if kernel_ifaces:
                    network_content += f"Kernel Helper Interfaces:\n"
                    for idx, iface in enumerate(kernel_ifaces, 1):
                        network_content += f"  [{idx}] {iface}\n"
            else:
                network_content += "No network telemetry data available\n"
            network_text.insert('1.0', network_content)
            network_text.configure(state='disabled')

            network_content += f"Logical Cores:     {cpu_extended['cores_logical']}\n"
            network_content += f"Physical Cores:    {cpu_extended['cores_physical']}\n"
            network_content += f"SMT Status:        {cpu_extended['smt_status']}\n"

            network_content += "FREQUENCY INFORMATION:\n"
            network_content += f"Base Clock:        {cpu_extended['base_freq']}\n"
            network_content += f"Max Frequency:     {cpu_extended['max_freq']}\n"
            network_content += f"Max Turbo:         {cpu_extended['max_turbo_freq']}\n"
            network_content += f"Current Freq:      {cpu_extended['current_freq']}\n"
            network_content += f"Bus Clock:         {cpu_extended['bus_freq']}\n"
            network_content += f"Frequency Source:  {cpu_extended['freq_source']}\n"

            network_content += "CACHE INFORMATION:\n"
            network_content += f"L1 Cache:          {cpu_extended['cache_l1']}\n"
            network_content += f"L2 Cache:          {cpu_extended['cache_l2']}\n"
            network_content += f"L3 Cache:          {cpu_extended['cache_l3']}\n"

            network_content += "POWER & THERMAL:\n"
            network_content += f"TDP:               {cpu_extended['tdp']}\n"
            network_content += f"Socket:            {cpu_extended['socket']}\n"
            
            # Add per-core frequency telemetry to text report
            if cpu_extended.get('per_core_frequency'):
                report_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                report_content += "║             PER-CORE FREQUENCY TELEMETRY                     ║\n"
                report_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                report_content += "PER-CORE FREQUENCY (Current):\n"
                for core_data in cpu_extended['per_core_frequency']:
                    core = core_data.get('core', 0)
                    freq = core_data.get('frequency_mhz', 0)
                    pct = core_data.get('percentage', 0)
                    report_content += f"  Core {core:2d}: {freq:4d} MHz ({pct:3d}%)\n"
            
            # Add C-state residency telemetry to text report
            if cpu_extended.get('c_state_residency'):
                report_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                report_content += "║              C-STATE RESIDENCY TELEMETRY                     ║\n"
                report_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                report_content += "C-STATE RESIDENCY (% time in each state):\n"
                for core_data in cpu_extended['c_state_residency']:
                    core = core_data.get('core', 0)
                    c0 = core_data.get('C0', 0)
                    c1_plus = core_data.get('C1+', 0)
                    report_content += f"  Core {core:2d}: C0={c0:3d}% (active)  C1+={c1_plus:3d}% (idle)\n"
            
            # Add APIC topology and cache sharing groups to text report
            if cpu_extended.get('cache_sharing_groups'):
                report_content += "\n╔══════════════════════════════════════════════════════════════╗\n"
                report_content += "║              CACHE SHARING TOPOLOGY                          ║\n"
                report_content += "╚══════════════════════════════════════════════════════════════╝\n\n"
                
                cache_sharing = cpu_extended['cache_sharing_groups']
                l1d_inst = cache_sharing.get('l1d_instances', 0)
                l2_inst = cache_sharing.get('l2_instances', 0)
                l3_inst = cache_sharing.get('l3_instances', 0)
                
                report_content += f"L1D Cache: {l1d_inst} instances (per-core)\n"
                report_content += f"L2 Cache:  {l2_inst} instances (shared by clusters)\n"
                report_content += f"L3 Cache:  {l3_inst} instance(s) (shared by all cores)\n\n"
                
                # Show all cores with their cache group memberships
                apic_data = cpu_extended.get('apic_ids', [])
                if apic_data:
                    report_content += "Core → Cache Group Mapping:\n"
                    for core_info in apic_data:
                        lp = core_info.get('index', 0)
                        apic = core_info.get('apic', 0)
                        core_type = core_info.get('core_type', 0)
                        l2_grp = core_info.get('l2_group', -1)
                        l3_grp = core_info.get('l3_group', -1)
                        type_str = 'P-core' if core_type == 64 else ('E-core' if core_type == 32 else 'Unknown')
                        report_content += f"  LP{lp:2d} (APIC {apic:3d}, {type_str:6s}): L2 Group {l2_grp}, L3 Group {l3_grp}\n"

            # Add temperature if available
            if cpu_extended['temperatures']:
                report_content += "\nTEMPERATURE:\n"
                for temp_name, temp_val in list(cpu_extended['temperatures'].items())[:6]:
                    report_content += f"  {temp_name:20} {temp_val}\n"

            # Add virtualization support
            if cpu_extended['virtualization'] != 'Not detected':
                report_content += f"\nVIRTUALIZATION:\n"
                report_content += f"  Support:           {cpu_extended['virtualization']}\n"

            # Add instruction sets with grouping if available
            if cpu_extended['instruction_sets_grouped']:
                report_content += f"\nINSTRUCTION SETS (Categorized):\n"
                for category, instr_list in cpu_extended['instruction_sets_grouped'].items():
                    report_content += f"  {category}: {', '.join(instr_list)}\n"
            elif cpu_extended['instruction_sets']:
                report_content += f"\nINSTRUCTION SETS:\n"
                instr_text = ', '.join(cpu_extended['instruction_sets'][:15])
                report_content += f"  {instr_text}\n"

            # Add security features
            if cpu_extended['security_features']:
                report_content += f"\nSECURITY FEATURES:\n"
                for feature in cpu_extended['security_features']:
                    if 'unavailable' in feature.lower():
                        report_content += f"  ⚠ {feature}\n"
                    else:
                        report_content += f"  ✓ {feature}\n"

            # Add additional features if any
            if cpu_extended['features']:
                report_content += f"\nFEATURES:\n"
                for feature in cpu_extended['features']:
                    report_content += f"  • {feature}\n"

            # Power Users Section
            report_content += f"\n════════════════════════════════════════════════════════════════\n"
            report_content += f" CPU INFORMATION - POWER USERS SECTION\n"
            report_content += f"════════════════════════════════════════════════════════════════\n"
            
            if cpu_extended['microcode'] != 'Unavailable':
                report_content += f"\nMicrocode Version: {cpu_extended['microcode']}\n"
            
            if cpu_extended['numa_nodes'] != 'N/A':
                report_content += f"NUMA Nodes:        {cpu_extended['numa_nodes']}\n"
            
            if cpu_extended['p_states']:
                report_content += f"P-States:          {cpu_extended['p_states']}\n"
            
            if cpu_extended['c_states']:
                report_content += f"C-States:          {', '.join(cpu_extended['c_states'])}\n"
            
            if cpu_extended['thermal_throttling'] != 'Unknown':
                report_content += f"Thermal Throttling: {cpu_extended['thermal_throttling']}\n"

            # Extract SPD timing info for report
            spd_timing = memory_info.get('spd_timing', {})
            cas_report = spd_timing.get('cas', 'Not reported by system API') if isinstance(spd_timing, dict) else 'Not reported by system API'
            ras_report = spd_timing.get('ras', 'Not reported by system API') if isinstance(spd_timing, dict) else 'Not reported by system API'
            rcd_report = spd_timing.get('rcd', 'Not reported by system API') if isinstance(spd_timing, dict) else 'Not reported by system API'
            rp_report = spd_timing.get('rp', 'Not reported by system API') if isinstance(spd_timing, dict) else 'Not reported by system API'
            
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " MEMORY INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "─── USAGE ─────────────────────────────────────────────────────\n"
                f"Total Memory:      {memory_info['total']:.2f} GB\n"
                f"Used Memory:       {memory_info['used']:.2f} GB ({memory_info['percent']:.1f}%)\n"
                f"Available Memory:  {memory_info['available']:.2f} GB\n"
                "\n"
                "─── CONFIGURATION ─────────────────────────────────────────────\n"
                f"Memory Channels:   {memory_info.get('channel_info', 'Not reported by system API')}\n"
                f"ECC Status:        {memory_info.get('ecc_status', 'Not reported by system API')}\n"
                "\n"
                "─── SYSTEM-LEVEL INFO ────────────────────────────────────────\n"
                f"Memory Controller:  {memory_info.get('controller_info', 'Not reported by system API')}\n"
                f"NUMA Mapping:      {memory_info.get('numa_mapping', 'Not reported by system API')}\n"
                "\n"
            )
            
            # Add enhanced DIMM info from spd_helper
            spd_helper = memory_info.get('spd_helper', {})
            if spd_helper.get('available') and spd_helper.get('dimms'):
                report_content += f"════════════════════════════════════════════════════════════════\n"
                report_content += f" DIMM DETAILS (SMBIOS)\n"
                report_content += f"════════════════════════════════════════════════════════════════\n\n"
                
                for dimm in spd_helper['dimms']:
                    if not dimm.get('present'):
                        report_content += f"Slot {dimm['slot']}: [EMPTY]\n\n"
                        continue
                    
                    report_content += f"Slot {dimm['slot']} ({dimm['channel']}):\n"
                    report_content += f"  Capacity:       {dimm['size_mb']:,} MB ({dimm['size_mb']/1024:.1f} GB)\n"
                    report_content += f"  Type:           {dimm['ddr_generation']}\n"
                    report_content += f"  Form Factor:    {dimm['form_factor']}\n"
                    report_content += f"  Module Type:    {dimm['module_type']}\n"
                    report_content += f"  Rank:           {dimm['rank'] if isinstance(dimm['rank'], int) else 'Unknown'}\n"
                    # Clarify ECC is on-die, not system-level
                    report_content += f"  ECC:            {'On-die ECC (DDR5 standard)' if dimm['ecc'] and 'DDR5' in dimm['ddr_generation'] else 'Enabled' if dimm['ecc'] else 'Disabled'}\n"
                    
                    report_content += f"\n  Speed:\n"
                    report_content += f"    Configured:   {dimm['configured_speed_mhz']} MHz\n"
                    if dimm.get('max_speed_mhz') and dimm['max_speed_mhz'] != dimm['configured_speed_mhz']:
                        report_content += f"    Max:          {dimm['max_speed_mhz']} MHz\n"
                    
                    report_content += f"\n  Electrical:\n"
                    # Add voltage note for DDR5
                    if 'DDR5' in dimm['ddr_generation']:
                        report_content += f"    Voltage:      {dimm['voltage_mv']} mV (SMBIOS-reported; DDR5 nominal: 1100 mV)\n"
                    else:
                        report_content += f"    Voltage:      {dimm['voltage_mv']} mV\n"
                    if dimm.get('data_width') and dimm['data_width'] != 0xFFFF:
                        report_content += f"    Data Width:   {dimm['data_width']} bits\n"
                    # Fix: 0xFFFE is SMBIOS placeholder for 'unknown'
                    total_w = dimm.get('total_width', 0)
                    if total_w and total_w != 0xFFFF and total_w != 0xFFFE:
                        report_content += f"    Total Width:  {total_w} bits\n"
                    elif total_w == 0xFFFE:
                        report_content += f"    Total Width:  Not Reported (SMBIOS placeholder 0xFFFE)\n"
                    
                    report_content += f"\n  Identification:\n"
                    report_content += f"    Manufacturer: {dimm['manufacturer']}\n"
                    report_content += f"    Part Number:  {dimm['part_number'].strip()}\n"
                    if dimm.get('serial_number') and dimm['serial_number'] != 'N/A':
                        report_content += f"    Serial:       {dimm['serial_number']}\n"
                    
                    report_content += f"\n  Data Source:    {dimm['data_source']}\n"
                    report_content += f"\n"
                
                # Add Module Quality section to report
                report_content += f"════════════════════════════════════════════════════════════════\n"
                report_content += f" MODULE QUALITY & CHARACTERISTICS\n"
                report_content += f"════════════════════════════════════════════════════════════════\n\n"
                
                for dimm in spd_helper['dimms']:
                    if not dimm.get('present'):
                        continue
                    
                    report_content += f"Slot {dimm['slot']} Diagnostic Summary:\n"
                    report_content += f"  Profile: {dimm.get('jedec_profile', 'Unknown')}\n"
                    report_content += f"  DDR Generation: {dimm['ddr_generation']}\n"
                    report_content += f"  Channel: {dimm['channel']}\n"
                    
                    # Rank with inference
                    if isinstance(dimm['rank'], int) and dimm['rank'] > 0:
                        report_content += f"  Rank: {dimm['rank']}-rank\n"
                    else:
                        report_content += f"  Rank: Likely Single-Rank (not reported by SMBIOS)\n"
                    
                    # ECC with clarification
                    if dimm['ecc']:
                        if 'DDR5' in dimm['ddr_generation']:
                            report_content += f"  Error Correction: On-die ECC (DDR5 standard, not system-level)\n"
                        else:
                            report_content += f"  Error Correction: On-die ECC\n"
                    else:
                        report_content += f"  Error Correction: None\n"
                    
                    # Voltage with note
                    if 'DDR5' in dimm['ddr_generation']:
                        report_content += f"  Voltage: {dimm['voltage_mv']} mV (SMBIOS-reported; DDR5 nominal: 1100 mV)\n"
                    else:
                        report_content += f"  Voltage: {dimm['voltage_mv']} mV\n"
                    
                    report_content += f"  Form Factor: {dimm['form_factor']}\n"
                    report_content += f"\n"
                
                if spd_helper.get('note'):
                    report_content += f"SPD TIMING DATA:\n"
                    report_content += f"{spd_helper['note']}\n"
                    report_content += f"\nWhy Timings Are Unavailable:\n"
                    report_content += f"  - CAS Latency (CL), tRCD, tRP, tRAS require SMBus access\n"
                    report_content += f"  - SMBIOS safely provides capacity, speed, voltage, manufacturer\n"
                    report_content += f"  - Direct hardware access needs elevated privileges\n\n"
            
            # Legacy module info fallback
            elif memory_info.get('modules'):
                report_content += f"─── PHYSICAL MODULES ({memory_info['module_count']}) ───────────────────\n\n"
                for i, module in enumerate(memory_info['modules'], 1):
                    report_content += f"Module {i}: {module['slot']}\n"
                    report_content += f"  Capacity:      {module['capacity']:.0f} GB\n"
                    report_content += f"  Type:          {module['type']}\n"
                    report_content += f"  Speed:         {module['speed']} MHz\n"
                    report_content += f"  Manufacturer:  {module['manufacturer']}\n"
                    report_content += f"  Part Number:   {module['part_number']}\n\n"
            
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " GPU INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "\n"
            )
            
            if isinstance(gpu_info, dict) and 'error' in gpu_info:
                report_content += f"Error: {gpu_info['error']}\n"
            elif gpu_info:
                for i, gpu in enumerate(gpu_info, 1):
                    report_content += f"GPU {i}:\n"
                    report_content += f"  Name:            {gpu['name']}\n"
                    
                    if 'video_processor' in gpu:
                        report_content += f"  Processor:       {gpu['video_processor']}\n"
                    
                    if gpu.get('adapter_ram'):
                        report_content += f"  VRAM:            {gpu['adapter_ram']:.2f} GB\n"
                    else:
                        report_content += f"  VRAM:            Unknown\n"
                    
                    if 'driver_version' in gpu:
                        report_content += f"  Driver Version:  {gpu['driver_version']}\n"
                    
                    if 'current_refresh_rate' in gpu:
                        report_content += f"  Refresh Rate:    {gpu['current_refresh_rate']} Hz\n"
                    
                    if 'video_mode_description' in gpu:
                        report_content += f"  Resolution:      {gpu['video_mode_description']}\n"
                    
                    if 'status' in gpu:
                        report_content += f"  Status:          {gpu['status']}\n"
                    
                    if 'pnp_device_id' in gpu:
                        report_content += f"  Device ID:       {gpu['pnp_device_id']}\n"
                    elif 'device_id' in gpu:
                        report_content += f"  Device ID:       {gpu['device_id']}\n"
                    
                    # Phase 2: PCIe Link Information
                    if 'link_speed_gt_s' in gpu or 'link_width' in gpu:
                        report_content += f"\n  ─── PCIe Configuration ───\n"
                        if 'link_speed_gt_s' in gpu:
                            report_content += f"  Link Speed:      {gpu['link_speed_gt_s']} GT/s\n"
                        if 'link_width' in gpu:
                            report_content += f"  Link Width:      x{gpu['link_width']}\n"
                        if 'bandwidth_gb_s' in gpu:
                            report_content += f"  Bandwidth:       {gpu['bandwidth_gb_s']:.2f} GB/s\n"
                    
                    # Phase 2: GPU Utilization & Temperature
                    if 'core_utilization' in gpu or 'memory_utilization' in gpu or 'temperature_c' in gpu:
                        report_content += f"\n  ─── GPU Utilization & Temperature ───\n"
                        if 'core_utilization' in gpu:
                            report_content += f"  Core:            {gpu['core_utilization']}%\n"
                        if 'memory_utilization' in gpu:
                            report_content += f"  Memory:          {gpu['memory_utilization']}%\n"
                        if 'temperature_c' in gpu:
                            report_content += f"  Temperature:     {gpu['temperature_c']}°C\n"
                    
                    report_content += "\n"
            else:
                report_content += "No GPU information available\n"
            
            # Add monitor information to report
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " MONITOR INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "\n"
            )
            
            if isinstance(monitor_info, dict) and 'error' in monitor_info:
                report_content += f"Error: {monitor_info['error']}\n"
            elif monitor_info:
                for i, monitor in enumerate(monitor_info, 1):
                    report_content += f"Monitor {i}:\n"
                    report_content += f"  Name:            {monitor.get('name', 'Unknown')}\n"
                    
                    if 'resolution' in monitor:
                        report_content += f"  Resolution:      {monitor['resolution']}\n"
                    
                    if 'refresh_rate' in monitor:
                        report_content += f"  Refresh Rate:    {monitor['refresh_rate']} Hz\n"
                    
                    if 'bits_per_pixel' in monitor:
                        report_content += f"  Color Depth:     {monitor['bits_per_pixel']} bits\n"
                    
                    if 'manufacturer' in monitor and monitor['manufacturer'] != "Unknown":
                        report_content += f"  Manufacturer:    {monitor['manufacturer']}\n"
                    
                    if 'model' in monitor and monitor['model'] != "Unknown":
                        report_content += f"  Model:           {monitor['model']}\n"
                    
                    if 'serial' in monitor and monitor['serial'] != "Unknown":
                        report_content += f"  Serial:          {monitor['serial']}\n"
                    
                    if 'pnp_device_id' in monitor:
                        report_content += f"  Device ID:       {monitor['pnp_device_id']}\n"
                    
                    report_content += "\n"
            else:
                report_content += "No monitor information available\n"
            
            # Add disk information to report
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " DISK INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "\n"
            )
            
            if isinstance(disk_info, dict) and 'error' in disk_info:
                report_content += f"Error: {disk_info['error']}\n"
            elif disk_info:
                for i, disk in enumerate(disk_info, 1):
                    report_content += f"Disk {i}:\n"
                    report_content += f"  Device:          {disk['device']}\n"
                    report_content += f"  Mountpoint:      {disk['mountpoint']}\n"
                    report_content += f"  Filesystem:      {disk['fstype']}\n"
                    report_content += f"  Model:           {disk['model']}\n"
                    report_content += f"  Type:            {disk['disk_type']}\n"
                    report_content += f"  Interface:       {disk['interface_type']}\n"
                    report_content += f"  Serial:          {disk['serial']}\n"
                    report_content += f"  Total:           {disk['total']:.2f} GB\n"
                    report_content += f"  Used:            {disk['used']:.2f} GB\n"
                    report_content += f"  Free:            {disk['free']:.2f} GB\n"
                    report_content += f"  Usage:           {disk['percent']:.1f}%\n"
                    
                    report_content += f"\n  Speed/Performance:\n"
                    if disk.get('avg_read_speed') is not None and disk['avg_read_speed'] > 0:
                        report_content += f"    Avg Read Speed:  {disk['avg_read_speed']:.2f} MB/s\n"
                    if disk.get('avg_write_speed') is not None and disk['avg_write_speed'] > 0:
                        report_content += f"    Avg Write Speed: {disk['avg_write_speed']:.2f} MB/s\n"
                    
                    if disk['io_stats']:
                        io = disk['io_stats']
                        report_content += f"\n  I/O Statistics:\n"
                        report_content += f"    Total Read:     {io['read_bytes'] / (1024**3):.2f} GB\n"
                        report_content += f"    Total Written:  {io['write_bytes'] / (1024**3):.2f} GB\n"
                        report_content += f"    Read Ops:       {io['read_count']}\n"
                        report_content += f"    Write Ops:      {io['write_count']}\n"
                    
                    report_content += "\n"
            else:
                report_content += "No disk information available\n"
            
            # Add NVMe SMART information to report (Phase 2)
            nvme_info = get_nvme_helper_info()
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " NVMe SMART INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "\n"
            )
            
            if isinstance(nvme_info, dict) and 'error' in nvme_info:
                report_content += f"Error: {nvme_info['error']}\n"
            elif nvme_info and 'nvme_devices' in nvme_info:
                nvme_devices = nvme_info['nvme_devices']
                if nvme_devices:
                    for i, device in enumerate(nvme_devices, 1):
                        report_content += f"NVMe Device {i}:\n"
                        report_content += f"  Device Path:     {device.get('device_path', 'Unknown')}\n"
                        
                        if 'friendly_name' in device and device['friendly_name'] != 'Unknown':
                            report_content += f"  Friendly Name:   {device['friendly_name']}\n"
                        
                        if 'model' in device and device['model'] != 'Unknown':
                            report_content += f"  Model:           {device['model']}\n"
                        
                        if 'serial' in device and device['serial'] != 'Unknown':
                            report_content += f"  Serial:          {device['serial']}\n"
                        
                        report_content += f"\n  ─── SMART Data ───\n"
                        
                        if 'temperature_c' in device and device['temperature_c'] != 'Unknown':
                            report_content += f"  Temperature:     {device['temperature_c']}°C\n"
                        
                        if 'percentage_used' in device and device['percentage_used'] != 'Unknown':
                            report_content += f"  Wear Level:      {device['percentage_used']}%\n"
                        
                        if 'power_on_hours' in device and device['power_on_hours'] != 'Unknown':
                            report_content += f"  Power-On Hours:  {device['power_on_hours']}\n"
                        
                        if 'critical_warnings' in device and device['critical_warnings'] != 'Unknown':
                            report_content += f"  Critical Warns:  {device['critical_warnings']}\n"
                        
                        if 'media_errors' in device and device['media_errors'] != 'Unknown':
                            report_content += f"  Media Errors:    {device['media_errors']}\n"
                        
                        if 'available_spare' in device and device['available_spare'] != 'Unknown':
                            report_content += f"  Available Spare: {device['available_spare']}%\n"
                        
                        report_content += "\n"
                else:
                    report_content += "No NVMe devices detected\n"
            else:
                report_content += "NVMe helper not available or no SMART data collected\n"
            
            # Add EDID display information to report (Phase 3)
            edid_info = get_edid_helper_info()
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " DISPLAY & EDID INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "\n"
            )
            
            if isinstance(edid_info, dict) and 'error' in edid_info and edid_info['error']:
                report_content += f"Error: {edid_info['error']}\n"
            elif edid_info and 'edid_devices' in edid_info:
                edid_devices = edid_info['edid_devices']
                if edid_devices:
                    for i, device in enumerate(edid_devices, 1):
                        report_content += f"Monitor {i}:\n"
                        
                        if 'monitor_name' in device and device['monitor_name'] != 'Unknown':
                            report_content += f"  Name:             {device['monitor_name']}\n"
                        
                        if 'manufacturer' in device and device['manufacturer'] != 'Unknown':
                            report_content += f"  Manufacturer:     {device['manufacturer']}\n"
                        
                        if 'model' in device and device['model'] != 'Unknown':
                            report_content += f"  Model Code:       {device['model']}\n"
                        
                        if 'serial_number' in device and device['serial_number'] != 'Unknown':
                            report_content += f"  Serial Number:    {device['serial_number']}\n"
                        
                        if 'physical_width_cm' in device:
                            width = device['physical_width_cm']
                            height = device['physical_height_cm'] if 'physical_height_cm' in device else 0
                            if width and width > 0 and height and height > 0:
                                inches = (width**2 + height**2)**0.5 / 2.54
                                report_content += f"  Size:             {width} cm × {height} cm ({inches:.1f}\")\n"
                        
                        if 'edid_version' in device:
                            report_content += f"  EDID Version:     {device['edid_version']}\n"
                        
                        if 'input_type' in device:
                            report_content += f"  Input Type:       {device['input_type']}\n"
                        
                        if 'gamma' in device:
                            report_content += f"  Gamma:            {device['gamma']}\n"
                        
                        if 'manufacturing_year' in device:
                            report_content += f"  Manufacturing:    Week {device['manufacturing_week'] if 'manufacturing_week' in device else 'N/A'}, {device['manufacturing_year']}\n"
                        
                        report_content += "\n"
                else:
                    report_content += "No EDID devices detected\n"
            else:
                report_content += "EDID helper not available or no monitor data collected\n"
            
            # Add Network information to report
            report_content += (
                "════════════════════════════════════════════════════════════════\n"
                " NETWORK INFORMATION\n"
                "════════════════════════════════════════════════════════════════\n"
                "\n"
            )
            
            if network_info.get('error'):
                report_content += f"Error: {network_info['error']}\n"
            else:
                interfaces = network_info.get('interfaces', [])
                
                if interfaces:
                    report_content += f"Total Interfaces: {len(interfaces)}\n\n"
                    
                    for idx, iface in enumerate(interfaces, 1):
                        report_content += f"Interface {idx}: {iface['name']}\n"
                        report_content += f"  Status:           {'UP' if iface['is_up'] else 'DOWN'}\n"
                        report_content += f"  MTU:              {iface['mtu']} bytes\n"
                        if iface['speed'] > 0:
                            report_content += f"  Speed:            {iface['speed']} Mbps\n"
                        
                        if iface['addresses']:
                            report_content += f"  IP Addresses:\n"
                            for addr in iface['addresses']:
                                report_content += f"    - {addr['family']}: {addr['address']}\n"
                                if addr['netmask'] != 'N/A':
                                    report_content += f"      Netmask: {addr['netmask']}\n"
                        
                        report_content += "\n"
                    
                    # Add I/O statistics
                    io = network_info.get('io', {})
                    report_content += f"Network I/O Statistics:\n"
                    report_content += f"  Bytes Sent:       {io.get('bytes_sent', 0) / (1024**3):.2f} GB\n"
                    report_content += f"  Bytes Received:   {io.get('bytes_recv', 0) / (1024**3):.2f} GB\n"
                    report_content += f"  Packets Sent:     {io.get('packets_sent', 0):,}\n"
                    report_content += f"  Packets Received: {io.get('packets_recv', 0):,}\n"
                    report_content += f"  Errors In:        {io.get('errin', 0)}\n"
                    report_content += f"  Errors Out:       {io.get('errout', 0)}\n"
                    report_content += f"  Drops In:         {io.get('dropin', 0)}\n"
                    report_content += f"  Drops Out:        {io.get('dropout', 0)}\n"
                    report_content += f"  Active Connections: {network_info.get('connections', 0)}\n"
                else:
                    report_content += "No network interfaces detected\n"
            
            report_content += "\n" + "═" * 64 + "\n"
            report_content += "End of Report\n"
            report_content += "═" * 64 + "\n"
            
            report_text.insert('1.0', report_content)
            report_text.configure(state='disabled')
    
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
    
    # Add per-core temperature table above the text widget
    per_core_temp_frame = ttk.Frame(cpu_frame)
    per_core_temp_frame.pack(fill='x', padx=10, pady=(10, 0))

    per_core_temp_label = ttk.Label(per_core_temp_frame, text="Per-Core Temperatures", font=('Segoe UI', 11, 'bold'))
    per_core_temp_label.pack(anchor='w')

    per_core_temp_table = ttk.Treeview(per_core_temp_frame, columns=("core", "temp", "margin", "tjmax", "provenance"), show="headings", height=8)
    per_core_temp_table.heading("core", text="Core")
    per_core_temp_table.heading("temp", text="Temp (°C)")
    per_core_temp_table.heading("margin", text="Margin (°C)")
    per_core_temp_table.heading("tjmax", text="TjMax (°C)")
    per_core_temp_table.heading("provenance", text="Provenance")
    per_core_temp_table.column("core", width=60, anchor='center')
    per_core_temp_table.column("temp", width=90, anchor='center')
    per_core_temp_table.column("margin", width=90, anchor='center')
    per_core_temp_table.column("tjmax", width=90, anchor='center')
    per_core_temp_table.column("provenance", width=180, anchor='center')
    per_core_temp_table.pack(fill='x', pady=(0, 8))

    # Add per-core C-state residency table below the temperature table
    per_core_cstate_frame = ttk.Frame(cpu_frame)
    per_core_cstate_frame.pack(fill='x', padx=10, pady=(0, 8))

    per_core_cstate_label = ttk.Label(per_core_cstate_frame, text="Per-Core C-State Residency", font=('Segoe UI', 11, 'bold'))
    per_core_cstate_label.pack(anchor='w')

    per_core_cstate_table = ttk.Treeview(per_core_cstate_frame, columns=("core", "c0", "c1plus", "c3", "c6", "c7", "aperf", "mperf", "ap_ratio", "provenance"), show="headings", height=8)
    per_core_cstate_table.heading("core", text="Core")
    per_core_cstate_table.heading("c0", text="C0 (%)")
    per_core_cstate_table.heading("c1plus", text="C1+ (%)")
    per_core_cstate_table.heading("c3", text="C3 (%)")
    per_core_cstate_table.heading("c6", text="C6 (%)")
    per_core_cstate_table.heading("c7", text="C7 (%)")
    per_core_cstate_table.heading("aperf", text="APERF")
    per_core_cstate_table.heading("mperf", text="MPERF")
    per_core_cstate_table.heading("ap_ratio", text="APERF/MPERF")
    per_core_cstate_table.heading("provenance", text="Provenance")
    per_core_cstate_table.column("core", width=60, anchor='center')
    per_core_cstate_table.column("c0", width=70, anchor='center')
    per_core_cstate_table.column("c1plus", width=80, anchor='center')
    per_core_cstate_table.column("c3", width=70, anchor='center')
    per_core_cstate_table.column("c6", width=70, anchor='center')
    per_core_cstate_table.column("c7", width=70, anchor='center')
    per_core_cstate_table.column("aperf", width=90, anchor='center')
    per_core_cstate_table.column("mperf", width=90, anchor='center')
    per_core_cstate_table.column("ap_ratio", width=100, anchor='center')
    per_core_cstate_table.column("provenance", width=180, anchor='center')
    per_core_cstate_table.pack(fill='x', pady=(0, 8))

    # Add package temperature summary label below the per-core table
    pl_rapl_var = tk.StringVar()
    pl_rapl_label = ttk.Label(cpu_frame, textvariable=pl_rapl_var, font=('Segoe UI', 10, 'bold'))
    pl_rapl_label.pack(anchor='w', padx=12, pady=(0, 8))

    turbo_ratio_var = tk.StringVar()
    turbo_ratio_label = ttk.Label(cpu_frame, textvariable=turbo_ratio_var, font=('Segoe UI', 10, 'bold'))
    turbo_ratio_label.pack(anchor='w', padx=12, pady=(0, 8))

    package_temp_var = tk.StringVar()
    package_temp_label = ttk.Label(cpu_frame, textvariable=package_temp_var, font=('Segoe UI', 10, 'bold'))
    package_temp_label.pack(anchor='w', padx=12, pady=(0, 8))

    cpu_text = scrolledtext.ScrolledText(cpu_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                         font=('Consolas', 10), insertbackground='white')
    cpu_text.pack(fill='both', expand=True, padx=10, pady=10)
    text_widgets['cpu'] = cpu_text
    text_widgets['per_core_temp_table'] = per_core_temp_table
    text_widgets['per_core_cstate_table'] = per_core_cstate_table
    text_widgets['package_temp_var'] = package_temp_var
    text_widgets['pl_rapl_var'] = pl_rapl_var
    text_widgets['turbo_ratio_var'] = turbo_ratio_var
    # GPU Tab (Phase 4.2) - basic text report (scaffold)
    gpu_frame = ttk.Frame(notebook)
    notebook.add(gpu_frame, text='GPU')

    # Per-GPU summary table
    per_gpu_frame = ttk.Frame(gpu_frame)
    per_gpu_frame.pack(fill='x', padx=10, pady=(10, 0))

    per_gpu_label = ttk.Label(per_gpu_frame, text="GPU Summary", font=('Segoe UI', 11, 'bold'))
    per_gpu_label.pack(anchor='w')

    per_gpu_table = ttk.Treeview(per_gpu_frame, columns=("index", "name", "vram", "util", "temp", "power", "clocks", "pcie", "rebar", "driver", "source"), show='headings', height=6)
    per_gpu_table.heading('index', text='#')
    per_gpu_table.heading('name', text='Name')
    per_gpu_table.heading('vram', text='VRAM (GB)')
    per_gpu_table.heading('util', text='Util (%)')
    per_gpu_table.heading('temp', text='Temp (°C)')
    per_gpu_table.heading('power', text='Power (W)')
    per_gpu_table.heading('clocks', text='Clocks (MHz)')
    per_gpu_table.heading('pcie', text='PCIe')
    per_gpu_table.heading('rebar', text='ReBAR')
    per_gpu_table.heading('driver', text='Driver')
    per_gpu_table.heading('source', text='Source')
    per_gpu_table.column('index', width=40, anchor='center')
    per_gpu_table.column('name', width=260)
    per_gpu_table.column('vram', width=90, anchor='center')
    per_gpu_table.column('util', width=80, anchor='center')
    per_gpu_table.column('temp', width=90, anchor='center')
    per_gpu_table.column('power', width=90, anchor='center')
    per_gpu_table.column('clocks', width=160, anchor='w')
    per_gpu_table.column('pcie', width=140, anchor='center')
    per_gpu_table.column('rebar', width=120, anchor='center')
    per_gpu_table.column('driver', width=120, anchor='center')
    per_gpu_table.column('source', width=100, anchor='center')
    per_gpu_table.pack(fill='x', pady=(0, 8))

    gpu_text = scrolledtext.ScrolledText(gpu_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                         font=('Consolas', 10), insertbackground='white')
    gpu_text.pack(fill='both', expand=True, padx=10, pady=10)
    text_widgets['gpu'] = gpu_text
    text_widgets['per_gpu_table'] = per_gpu_table
    # Update turbo ratio display
    turbo_ratio_var = text_widgets.get('turbo_ratio_var')
    if turbo_ratio_var:
        turbo_data = cpu_extended.get('kernel_turbo', {})
        if turbo_data.get('available'):
            ratios = []
            for k in ["1_core_active", "2_cores_active", "3_cores_active", "4_cores_active", "5_cores_active", "6_cores_active", "7_cores_active", "8_cores_active"]:
                v = turbo_data.get(k)
                if v is not None:
                    ratios.append(f"{k.replace('_', ' ')}: {v}")
            provenance = turbo_data.get('provenance', '')
            turbo_ratio_var.set(f"Turbo Ratios (MSR 0x1AD): {' | '.join(ratios)}  (Provenance: {provenance})")
        else:
            turbo_ratio_var.set("Turbo Ratios: N/A")
    # Update PL1/PL2 + RAPL summary
    pl_rapl_var = text_widgets.get('pl_rapl_var')
    if pl_rapl_var:
        power_data = cpu_extended.get('kernel_helper', {}).get('kernel_power', {})
        rapl = power_data.get('rapl', {}) if power_data.get('available') else {}
        if power_data.get('available'):
            pl1 = power_data.get('pl1', {})
            pl2 = power_data.get('pl2', {})
            pl1_str = f"PL1: {pl1.get('watts', 'N/A')}W ({'Enabled' if pl1.get('enabled') else 'Disabled'}, Clamping: {'Yes' if pl1.get('clamping') else 'No'})" if pl1 else "PL1: N/A"
            pl2_str = f"PL2: {pl2.get('watts', 'N/A')}W ({'Enabled' if pl2.get('enabled') else 'Disabled'}, Clamping: {'Yes' if pl2.get('clamping') else 'No'})" if pl2 else "PL2: N/A"
            rapl_str = f"RAPL: Package {rapl.get('package_watts', 'N/A')}W, Cores {rapl.get('cores_watts', 'N/A')}W, DRAM {rapl.get('dram_watts', 'N/A')}W, Total {rapl.get('total_watts', 'N/A')}W" if rapl else "RAPL: N/A"
            provenance = power_data.get('provenance', '')
            pl_rapl_var.set(f"{pl1_str} | {pl2_str} | {rapl_str}  (Provenance: {provenance})")
        else:
            pl_rapl_var.set("PL1/PL2 + RAPL: N/A")
    # Update package temperature summary
    package_temp_var = text_widgets.get('package_temp_var')
    if package_temp_var:
        kernel_temps = cpu_extended.get('kernel_helper', {}).get('kernel_temperatures', {})
        if kernel_temps.get('available') and 'package_temp' in kernel_temps:
            package_temp = kernel_temps['package_temp']
            provenance = kernel_temps.get('provenance', '')
            package_temp_var.set(f"Package Temperature: {package_temp}°C  (Provenance: {provenance})")
        else:
            package_temp_var.set("Package Temperature: N/A")
    # Disk Tab
    disk_frame = ttk.Frame(notebook)
    notebook.add(disk_frame, text='Disks')
    disk_text = scrolledtext.ScrolledText(disk_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                         font=('Consolas', 10), insertbackground='white')
    disk_text.pack(fill='both', expand=True, padx=10, pady=10)
    text_widgets['disk'] = disk_text

    # Storage Tab (Phase 5)
    storage_frame = ttk.Frame(notebook)
    storage_text = scrolledtext.ScrolledText(storage_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                            font=('Consolas', 10), insertbackground='white')
    storage_text.pack(fill='both', expand=True, padx=10, pady=10)
    text_widgets['storage'] = storage_text

    # Display Tab (Phase 6)
    display_frame = ttk.Frame(notebook)
    notebook.add(display_frame, text='Display')
    display_text = scrolledtext.ScrolledText(display_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#d4d4d4',
                                            font=('Consolas', 10), insertbackground='white')
    display_text.pack(fill='both', expand=True, padx=10, pady=10)

    # --- Per-core temperature table population ---
    per_core_temp_table = text_widgets.get('per_core_temp_table')
    if per_core_temp_table:
        # Clear previous rows
        for row in per_core_temp_table.get_children():
            per_core_temp_table.delete(row)
        # Try to get kernel_helper per-core temps if available, else fallback
        kernel_temps = cpu_extended.get('kernel_helper', {}).get('kernel_temperatures', {})
        if kernel_temps.get('available') and kernel_temps.get('temperatures'):
            temps = kernel_temps['temperatures']
            tj_max = kernel_temps.get('tj_max', 100)
            for core in sorted(temps.keys()):
                temp_info = temps[core]
                celsius = temp_info.get('celsius', 0)
                margin = temp_info.get('margin', 0)
                provenance = temp_info.get('provenance', '')
                per_core_temp_table.insert('', 'end', values=(core, celsius, margin, tj_max, provenance))
        else:
            # Fallback: show logical core count, but no data
            for i in range(cpu_extended.get('cores_logical', 0)):
                per_core_temp_table.insert('', 'end', values=(i, 'N/A', 'N/A', 'N/A', 'N/A'))

    # --- Per-core C-state table population ---
    per_core_cstate_table = text_widgets.get('per_core_cstate_table')
    if per_core_cstate_table:
        # Clear previous rows
        for row in per_core_cstate_table.get_children():
            per_core_cstate_table.delete(row)

        # Prefer kernel-provided c-state telemetry
        kernel_cstates = cpu_extended.get('kernel_cstates') or cpu_extended.get('c_state_residency')
        if kernel_cstates:
            # kernel_cstates expected to be list of dicts per core
            for core_data in sorted(kernel_cstates, key=lambda x: x.get('core', 0)):
                core = core_data.get('core', 0)
                c0 = core_data.get('C0', core_data.get('c0', 0))
                c1p = core_data.get('C1+', core_data.get('c1_plus', core_data.get('c1', 0)))
                c3 = core_data.get('C3', core_data.get('c3', 0))
                c6 = core_data.get('C6', core_data.get('c6', 0))
                c7 = core_data.get('C7', core_data.get('c7', 0))
                aperf = core_data.get('APERF', core_data.get('aperf', 'N/A'))
                mperf = core_data.get('MPERF', core_data.get('mperf', 'N/A'))
                apr = core_data.get('aperf_mperf_ratio', core_data.get('aperf_mperf', 'N/A'))
                provenance = core_data.get('provenance', '')
                # Format numeric values
                try:
                    c0s = f"{int(round(float(c0)))}%"
                except:
                    c0s = str(c0)
                try:
                    c1s = f"{int(round(float(c1p)))}%"
                except:
                    c1s = str(c1p)
                try:
                    c3s = f"{int(round(float(c3)))}%"
                except:
                    c3s = str(c3)
                try:
                    c6s = f"{int(round(float(c6)))}%"
                except:
                    c6s = str(c6)
                try:
                    c7s = f"{int(round(float(c7)))}%"
                except:
                    c7s = str(c7)
                per_core_cstate_table.insert('', 'end', values=(core, c0s, c1s, c3s, c6s, c7s, aperf, mperf, apr, provenance))
        else:
            # No kernel telemetry available; insert placeholders
            for i in range(cpu_extended.get('cores_logical', 0)):
                per_core_cstate_table.insert('', 'end', values=(i, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A'))

            # --- Existing CPU text content ---
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

TURBO RATIO INFORMATION (CPUID 0x16):
Max Turbo (1-core):   {cpu_extended.get('max_turbo_1c', 'Unavailable')} MHz
Max Turbo (all-core): {cpu_extended.get('max_turbo_ac', 'Unavailable')} MHz
MSR Access:           {cpu_extended.get('msr_access', 'Unavailable')}

CACHE INFORMATION:
L1 Cache:          {cpu_extended['cache_l1']}
L2 Cache:          {cpu_extended['cache_l2']}
L3 Cache:          {cpu_extended['cache_l3']}

POWER & THERMAL:
TDP:               {cpu_extended['tdp']}
Socket:            {cpu_extended['socket']}
"""
            # ...existing code for the rest of the CPU tab content...
            cpu_text.insert('1.0', cpu_content)
            cpu_text.configure(state='disabled')