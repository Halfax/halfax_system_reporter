from __future__ import annotations
import re
import json

import main

def base_device_name(dev):
    if not dev:
        return ''
    name = str(dev)
    name = name.split('\\')[-1].split('/')[-1]
    m = re.match(r'(.+?)(p?\d+)$', name)
    if m:
        return m.group(1)
    return name


def render_disk_info(disk_info):
    report_content = ''
    if isinstance(disk_info, dict) and disk_info.get('error'):
        return f"Disk helper error: {disk_info.get('error')}\n"
    elif isinstance(disk_info, (list, tuple)) and disk_info:
        physical = []
        partitions = []
        for d in disk_info:
            if d.get('mountpoint') or d.get('fstype') or d.get('opts'):
                partitions.append(d)
            else:
                physical.append(d)
        phys_map = {}
        for p in physical:
            key = base_device_name(p.get('device')) or p.get('model') or p.get('serial') or f"phys_{len(phys_map)+1}"
            phys_map.setdefault(key, []).append(p)
        unmapped_partitions = []
        for part in partitions:
            part_base = base_device_name(part.get('device'))
            matched = False
            for pk in list(phys_map.keys()):
                if part_base and part_base in pk:
                    phys_map[pk].append(part)
                    matched = True
                    break
            if not matched:
                unmapped_partitions.append(part)
        if phys_map:
            for idx, (key, items) in enumerate(phys_map.items(), 1):
                phys = next((it for it in items if not (it.get('mountpoint') or it.get('fstype'))), items[0])
                report_content += f"─── Physical Device {idx} ───────────────────────────────────────────\n"
                report_content += f"  Device Key:        {key}\n"
                report_content += f"  Device Path:       {phys.get('device','Unknown')}\n"
                report_content += f"  Model:             {phys.get('model','Unknown')}\n"
                report_content += f"  Serial:            {phys.get('serial','Unknown')}\n"
                report_content += f"  Interface:         {phys.get('interface_type', phys.get('source','Unknown'))}\n"
                size = phys.get('size') or phys.get('total') or 0
                try:
                    if isinstance(size, (int, float)):
                        size_gb = size / (1024**3)
                        report_content += f"  Size:              {size_gb:.2f} GB\n"
                    else:
                        report_content += f"  Size:              {size}\n"
                except Exception:
                    report_content += f"  Size:              {size}\n"
                parts = [it for it in items if (it.get('mountpoint') or it.get('fstype'))]
                if parts:
                    for pi, p in enumerate(parts, 1):
                        report_content += f"    ─ Partition {pi} ─────────────────────────────────────────\n"
                        report_content += f"      Mountpoint:     {p.get('mountpoint','Unknown')}\n"
                        report_content += f"      FS:             {p.get('fstype','Unknown')}\n"
                        if p.get('total'):
                            try:
                                total_gb = float(p.get('total',0)) / (1024**3)
                                used_gb = float(p.get('used',0)) / (1024**3) if p.get('used') else 0
                                report_content += f"      Size:           {total_gb:.2f} GB\n"
                                report_content += f"      Used:           {used_gb:.2f} GB ({p.get('percent','N/A')}%)\n"
                            except Exception:
                                report_content += f"      Size:           {p.get('total',0)}\n"
                                report_content += f"      Used:           {p.get('used',0)} ({p.get('percent','N/A')}%)\n"
                        report_content += f"      Device:         {p.get('device','Unknown')}\n"
                report_content += "\n"
        if unmapped_partitions:
            report_content += "─── Unmapped / Mounted Partitions ─────────────────────────────────\n"
            for i, p in enumerate(unmapped_partitions, 1):
                report_content += f"  Partition {i}:\n"
                report_content += f"    Device:         {p.get('device','Unknown')}\n"
                report_content += f"    Mountpoint:     {p.get('mountpoint','Unknown')}\n"
                report_content += f"    FS:             {p.get('fstype','Unknown')}\n"
                if p.get('total'):
                    try:
                        total_gb = float(p.get('total',0)) / (1024**3)
                        used_gb = float(p.get('used',0)) / (1024**3) if p.get('used') else 0
                        report_content += f"    Size:           {total_gb:.2f} GB\n"
                        report_content += f"    Used:           {used_gb:.2f} GB ({p.get('percent','N/A')}%)\n"
                    except Exception:
                        report_content += f"    Size:           {p.get('total',0)}\n"
                        report_content += f"    Used:           {p.get('used',0)} ({p.get('percent','N/A')}%)\n"
                report_content += "\n"
        if not phys_map and not unmapped_partitions:
            report_content = 'No disk information available\n'
    else:
        report_content = 'No disk information available\n'
    return report_content


if __name__ == '__main__':
    try:
        disks = main.get_disk_info()
    except Exception as e:
        print('Error calling get_disk_info():', e)
        disks = []
    print('Raw disk_info:')
    print(json.dumps(disks, indent=2, default=str))
    print('\nRendered summary:\n')
    print(render_disk_info(disks))
    # Debug: show WMI logical-to-physical mapping if available
    try:
        import wmi
        c = wmi.WMI()
        part_to_disk = {}
        for assoc in c.Win32_DiskDriveToDiskPartition():
            antecedent = str(assoc.Antecedent)
            dependent = str(assoc.Dependent)
            import re
            a_match = re.search(r'DeviceID="([^"]+)"', antecedent)
            d_match = re.search(r'DeviceID="([^"]+)"', dependent)
            if a_match and d_match:
                part_to_disk[d_match.group(1)] = a_match.group(1)
        logical_map = {}
        for assoc in c.Win32_LogicalDiskToPartition():
            antecedent = str(assoc.Antecedent)
            dependent = str(assoc.Dependent)
            import re
            p_match = re.search(r'DeviceID="([^"]+)"', antecedent)
            l_match = re.search(r'DeviceID="([^"]+)"', dependent)
            if p_match and l_match:
                logical_map[l_match.group(1).rstrip('\\').upper()] = part_to_disk.get(p_match.group(1))
        print('\nWMI logical->physical mapping (debug):')
        print(json.dumps(logical_map, indent=2))
    except Exception:
        pass
