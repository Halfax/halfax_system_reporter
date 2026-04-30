import subprocess
import platform
import json
import tempfile
import xml.etree.ElementTree as ET

try:
    import pynvml
except Exception:
    pynvml = None


def get_gpu_list():
    """Return a list of detected GPUs and basic properties.
    Best-effort: prefer `nvidia-smi`/NVML, fall back to WMI on Windows.
    Always includes WMI to catch non-NVIDIA GPUs.
    """
    gpus = []
    nvidia_gpu_names = set()  # Track NVIDIA GPUs to avoid duplicates

    # Try NVML first (python bindings)
    if pynvml:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h).decode() if isinstance(pynvml.nvmlDeviceGetName(h), bytes) else str(pynvml.nvmlDeviceGetName(h))
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(h)
                mem = mem_info.total // (1024**3)
                mem_used = mem_info.used
                mem_used_gb = float(mem_used) / (1024**3)
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(h, 0)
                except Exception:
                    temp = None
                gpu_entry = {
                    'name': name,
                    'adapter_ram': float(mem),
                    'memory_used_gb': mem_used_gb,
                    'memory_used_bytes': int(mem_used),
                    'temperature_c': temp,
                    'source': 'pynvml'
                }
                nvidia_gpu_names.add(name)
                # Try to include PCI BDF if available from NVML
                try:
                    pci = pynvml.nvmlDeviceGetPciInfo(h)
                    bdf = getattr(pci, 'busId', None) or getattr(pci, 'pciBusId', None) or getattr(pci, 'bus_id', None)
                    if bdf and isinstance(bdf, str):
                        # Expected format: '0000:65:00.0' -> domain:bus:device.function
                        parts = bdf.split(':')
                        if len(parts) == 3:
                            bus_hex = parts[1]
                            dev_func = parts[2]
                            dev_str, func_str = dev_func.split('.') if '.' in dev_func else (dev_func, '0')
                            try:
                                gpu_entry['pci_bus'] = int(bus_hex, 16)
                                gpu_entry['pci_device'] = int(dev_str, 16)
                                gpu_entry['pci_function'] = int(func_str, 10)
                                gpu_entry['pci_bdf'] = bdf
                            except Exception:
                                pass
                except Exception:
                    pass

                # If kernel helper is available, attempt to read negotiated link info
                try:
                    from halfax_kernel_helper import KernelHelper
                    helper = KernelHelper()
                    if 'pci_bus' in gpu_entry and 'pci_device' in gpu_entry and 'pci_function' in gpu_entry and helper.available:
                        link = helper.get_pcie_link_info(gpu_entry['pci_bus'], gpu_entry['pci_device'], gpu_entry['pci_function'])
                        if link:
                            gpu_entry.update(link)
                        # Best-effort Resizable BAR detection
                        try:
                            rebar = helper.get_resizable_bar_state(gpu_entry['pci_bus'], gpu_entry['pci_device'], gpu_entry['pci_function'])
                            if rebar:
                                gpu_entry['resizable_bar'] = rebar
                        except Exception:
                            pass
                except Exception:
                    # Best-effort; don't fail NVML enumeration
                    pass

                gpus.append(gpu_entry)
            pynvml.nvmlShutdown()
        except Exception:
            pass

    # Fallback: nvidia-smi CLI
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=4)
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(',')]
                name = parts[0]
                ram_mb = float(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                driver = parts[2] if len(parts) > 2 else None
                gpu_entry = {'name': name, 'adapter_ram': ram_mb / 1024.0, 'driver_version': driver, 'source': 'nvidia-smi'}
                nvidia_gpu_names.add(name)
                gpus.append(gpu_entry)
    except Exception:
        pass

    # Always include WMI to catch non-NVIDIA GPUs (Intel, AMD, etc.)
    if platform.system() == 'Windows':
        try:
            ps_cmd = "Get-CimInstance -ClassName Win32_VideoController | ConvertTo-Json"
            result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], capture_output=True, text=True, timeout=4)
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for entry in data:
                        name = entry.get('Name')
                        ram = entry.get('AdapterRAM')
                        driver = entry.get('DriverVersion')
                        
                        # Skip if this is already detected by NVIDIA tools
                        if name in nvidia_gpu_names:
                            continue
                            
                        gpu_entry = {
                            'name': name, 
                            'adapter_ram': (ram / (1024**3)) if ram else None, 
                            'driver_version': driver, 
                            'source': 'wmi'
                        }
                        gpus.append(gpu_entry)
                except Exception:
                    pass
        except Exception:
            pass

    # Attempt DXDiag XML export (best-effort DXGI-like info) before WMI
    if platform.system() == 'Windows' and not gpus:
        dxg = _get_dxdiag_adapters()
        if dxg:
            gpus.extend(dxg)

    return gpus


def get_gpu_utilization():
    """Best-effort GPU utilization, temperature, power, and clocks via NVML if available."""
    util = {}
    if pynvml:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h).decode() if isinstance(pynvml.nvmlDeviceGetName(h), bytes) else str(pynvml.nvmlDeviceGetName(h))
                
                gpu_data = {}
                
                # Temperature
                try:
                    tmp = pynvml.nvmlDeviceGetTemperature(h, 0)
                    if tmp is not None:
                        gpu_data['temperature_c'] = tmp
                except Exception:
                    gpu_data['temperature_c'] = None
                
                # Utilization rates
                try:
                    util_rates = pynvml.nvmlDeviceGetUtilizationRates(h)
                    gpu_data['core_utilization'] = util_rates.gpu
                    gpu_data['memory_utilization'] = util_rates.memory
                except Exception:
                    gpu_data['core_utilization'] = None
                    gpu_data['memory_utilization'] = None
                
                # Power consumption
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(h)
                    if power is not None:
                        gpu_data['power_w'] = power / 1000.0  # Convert mW to W
                except Exception:
                    gpu_data['power_w'] = None
                
                # Clock speeds
                try:
                    graphics_clock = pynvml.nvmlDeviceGetClockInfo(h, 0)  # Graphics clock
                    memory_clock = pynvml.nvmlDeviceGetClockInfo(h, 1)    # Memory clock
                    gpu_data['clocks'] = {
                        'graphics_mhz': graphics_clock,
                        'memory_mhz': memory_clock
                    }
                except Exception:
                    gpu_data['clocks'] = None
                
                # Memory info
                try:
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(h)
                    gpu_data['memory_used_gb'] = mem_info.used / (1024**3)
                    gpu_data['memory_total_gb'] = mem_info.total / (1024**3)
                except Exception:
                    gpu_data['memory_used_gb'] = None
                    gpu_data['memory_total_gb'] = None
                
                # Power state
                try:
                    pstate = pynvml.nvmlDeviceGetPerformanceState(h)
                    gpu_data['performance_state'] = str(pstate)
                except Exception:
                    gpu_data['performance_state'] = None
                
                util[name] = gpu_data
            pynvml.nvmlShutdown()
        except Exception:
            pass
    
    # Fallback to nvidia-smi CLI for basic metrics
    if not util:
        try:
            result = subprocess.run([
                'nvidia-smi', 
                '--query-gpu=name,utilization.gpu,utilization.memory,temperature.gpu,power.draw,clocks.gr,clocks.mem',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=4)
            
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 7:
                        name = parts[0]
                        gpu_util = parts[1] if parts[1] != '[Not Supported]' else None
                        mem_util = parts[2] if parts[2] != '[Not Supported]' else None
                        temp = parts[3] if parts[3] != '[Not Supported]' else None
                        power = parts[4] if parts[4] != '[Not Supported]' else None
                        graphics_clock = parts[5] if parts[5] != '[Not Supported]' else None
                        memory_clock = parts[6] if parts[6] != '[Not Supported]' else None
                        
                        gpu_data = {}
                        if gpu_util and gpu_util.isdigit():
                            gpu_data['core_utilization'] = int(gpu_util)
                        if mem_util and mem_util.isdigit():
                            gpu_data['memory_utilization'] = int(mem_util)
                        if temp and temp.isdigit():
                            gpu_data['temperature_c'] = int(temp)
                        if power:
                            try:
                                gpu_data['power_w'] = float(power)
                            except:
                                pass
                        if graphics_clock and graphics_clock.isdigit():
                            gpu_data['clocks'] = {'graphics_mhz': int(graphics_clock)}
                        if memory_clock and memory_clock.isdigit():
                            if 'clocks' not in gpu_data:
                                gpu_data['clocks'] = {}
                            gpu_data['clocks']['memory_mhz'] = int(memory_clock)
                        
                        util[name] = gpu_data
        except Exception:
            pass
    
    return util


def get_gpu_display_association():
    """Get GPU display association information (which GPU drives which display)."""
    display_gpu_map = {}
    
    if platform.system() == 'Windows':
        try:
            # Use WMI to get display adapter information
            ps_cmd = """
            Get-CimInstance -ClassName Win32_DesktopMonitor | Select-Object Name, DeviceID, ScreenHeight, ScreenWidth | ConvertTo-Json
            """
            result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], 
                                  capture_output=True, text=True, timeout=4)
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    
                    for monitor in data:
                        monitor_name = monitor.get('Name', 'Unknown Monitor')
                        device_id = monitor.get('DeviceID', 'Unknown')
                        
                        # Try to determine which GPU is driving this display
                        # This is a simplified approach - in reality, this requires more complex analysis
                        display_gpu_map[monitor_name] = {
                            'device_id': device_id,
                            'active_gpu': 'Unknown',  # Will be determined later
                            'resolution': f"{monitor.get('ScreenWidth', 0)}x{monitor.get('ScreenHeight', 0)}" if monitor.get('ScreenWidth') and monitor.get('ScreenHeight') else 'Unknown'
                        }
                except Exception:
                    pass
        except Exception:
            pass
    
    return display_gpu_map


def get_gpu_pcie_info():
    """Get PCIe information for GPUs using user-mode methods."""
    pcie_info = {}
    
    if platform.system() == 'Windows':
        try:
            # Use WMI to get PCIe information
            ps_cmd = """
            Get-CimInstance -ClassName Win32_VideoController | Select-Object Name, PNPDeviceID | ConvertTo-Json
            """
            result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], 
                                  capture_output=True, text=True, timeout=4)
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    
                    for gpu in data:
                        name = gpu.get('Name', 'Unknown')
                        pnp_device_id = gpu.get('PNPDeviceID', '')
                        
                        # Extract PCIe information from PNPDeviceID
                        # Format: PCI\VEN_xxxx&DEV_xxxx&SUBSYS_xxxxxxxxxxxx&REV_xx\x...
                        if 'PCI\\' in pnp_device_id:
                            pcie_info[name] = {
                                'interface_type': 'PCIe',
                                'device_id': pnp_device_id,
                                'resizable_bar': 'Unknown'  # Will be determined later
                            }
                except Exception:
                    pass
        except Exception:
            pass
    
    return pcie_info


def get_intel_gpu_metrics():
    """Get Intel GPU metrics using Windows Performance Counters."""
    intel_metrics = {}
    
    if platform.system() == 'Windows':
        try:
            # Use PowerShell to get Intel GPU metrics
            ps_cmd = """
            Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue | 
            Select-Object -ExpandProperty CounterSamples | 
            Where-Object {$_.InstanceName -like '*Intel*'} | 
            ConvertTo-Json
            """
            result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], 
                                  capture_output=True, text=True, timeout=4)
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, list):
                        for sample in data:
                            instance_name = sample.get('InstanceName', '')
                            if 'Intel' in instance_name:
                                cooked_value = sample.get('CookedValue', 0)
                                intel_metrics['core_utilization'] = int(cooked_value)
                                break
                except Exception:
                    pass
        except Exception:
            pass
    
    return intel_metrics


def _get_dxdiag_adapters():
    """Best-effort parse of `dxdiag /x` XML output to enumerate adapters.
    Returns list similar to `get_gpu_list()` or empty on failure.
    """
    if platform.system() != 'Windows':
        return []

    try:
        tf = tempfile.NamedTemporaryFile(prefix='dxdiag_', suffix='.xml', delete=False)
        tf.close()
        cmd = ['dxdiag', '/x', tf.name]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if proc.returncode != 0:
            return []
        try:
            tree = ET.parse(tf.name)
            root = tree.getroot()
            # dxdiag XML format: DirectXDiagnostic -> DisplayDevices -> DisplayDevice
            dd = root.find('.//DisplayDevices')
            gpus = []
            if dd is None:
                return []
            for dev in dd.findall('DisplayDevice'):
                name = dev.findtext('CardName') or dev.findtext('DeviceKey') or dev.findtext('Description')
                try:
                    mem_text = dev.findtext('DisplayMemory') or dev.findtext('DedicatedMemory')
                    # Attempt to parse memory like "4096 MB"
                    mem_gb = None
                    if mem_text:
                        parts = mem_text.split()
                        for p in parts:
                            try:
                                v = float(p)
                                # assume MB unless suffix indicates GB
                                if 'gb' in mem_text.lower():
                                    mem_gb = v
                                else:
                                    mem_gb = v / 1024.0
                                break
                            except Exception:
                                continue
                except Exception:
                    mem_gb = None

                driver = dev.findtext('DriverVersion') or dev.findtext('Driver')
                gpus.append({'name': name, 'adapter_ram': mem_gb, 'driver_version': driver, 'source': 'dxdiag'})
            return gpus
        except Exception:
            return []
    except Exception:
        return []


def get_multi_gpu_topology(gpu_list):
    """
    Return a simple topology summary grouping GPUs by PCI bus.

    Example return:
      [{"bus": 65, "gpus": [gpu0_entry, gpu1_entry]}, ...]
    """
    if not gpu_list:
        return []
    groups = {}
    for g in gpu_list:
        bus = g.get('pci_bus')
        if bus is None:
            bus = 'unknown'
        groups.setdefault(bus, []).append(g)
    topology = []
    for bus, members in groups.items():
        topology.append({'bus': bus, 'gpus': members})
    return topology


def get_gpu_power():
    """Placeholder: return per-GPU power draw if available (watts)."""
    # NVML/ADL/DXGI paths to be implemented; return empty dict for now
    return {}


def get_gpu_clocks():
    """Placeholder: return per-GPU clocks (core/mem) if available."""
    return {}


def _get_adl_adapters():
    """Placeholder for AMD ADL integration.
    Best-effort: try to import Python ADL bindings or use a CLI if available.
    Returns list of GPU dicts or empty list.
    """
    # ADL bindings are not guaranteed; this is a safe stub for now.
    try:
        import adl  # type: ignore
    except Exception:
        return []

    try:
        adapters = []
        # Example pseudo-API usage; real ADL bindings vary by package
        for i, dev in enumerate(adl.get_adapters()):
            adapters.append({
                'name': dev.name,
                'adapter_ram': getattr(dev, 'vram_gb', None),
                'driver_version': getattr(dev, 'driver', None),
                'source': 'adl'
            })
        return adapters
    except Exception:
        return []


def _get_intel_adapters():
    """Placeholder for Intel iGPU telemetry.
    Attempts to use DXGI/DXGIAdapter information via `dxdiag` fallback already present.
    This stub returns empty until a preferred Intel telemetry path (DXGI/IGC) is added.
    """
    # Future: implement DXGI IDXGIAdapter/IDXGIAdapter3 queries via ctypes/win32
    return []
