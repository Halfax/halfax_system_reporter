import traceback
import main

try:
    try:
        from kernel_integration import get_storage_telemetry
    except Exception:
        get_storage_telemetry = lambda: {'error': 'kernel_integration not available'}
    storage_data = get_storage_telemetry()
    print('storage_data type:', type(storage_data))
    print('keys:', list(storage_data.keys()))
    print(storage_data)
        nvme_devs = storage_data.get('nvme_devices') or []
        wmi_devs = storage_data.get('wmi_devices') or []
        print('nvme_devs len:', len(nvme_devs))
        print('wmi_devs len:', len(wmi_devs))
        storage_content = 'Storage telemetry not available'
    if isinstance(storage_data, dict):
        if 'error' in storage_data:
            storage_content = f"Error: {storage_data['error']}"
        elif 'nvme_devices' in storage_data:
            storage_content = ''
                if nvme_devs or wmi_devs:
                    storage_content = ''
                    if nvme_devs:
                        for i, device in enumerate(nvme_devs, 1):
                            storage_content += f"─── NVMe Device {i} ───────────────────────────────────────────\n"
                            storage_content += f"  Device Path:     {device.get('device_path','Unknown')}\n"
                            storage_content += f"  Model:           {device.get('model','Unknown')}\n"
                            storage_content += f"  Serial:          {device.get('serial','Unknown')}\n\n"
                    else:
                        for i, device in enumerate(wmi_devs, 1):
                            storage_content += f"─── Physical Device {i} ─────────────────────────────────\n"
                            storage_content += f"  Model:           {device.get('model','Unknown')}\n"
                            storage_content += f"  Serial:          {device.get('serial','Unknown')}\n"
                            storage_content += f"  Interface:       {device.get('interface','Unknown')}\n"
                            storage_content += f"  Size:            {device.get('size_gb','Unknown')} GB\n\n"
        else:
            storage_content = 'No storage telemetry data available'
    print('storage_content:', storage_content)
except Exception as e:
    traceback.print_exc()
