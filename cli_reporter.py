import argparse
from datetime import datetime
import json
import os
import sys
import warnings


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import main


warnings.filterwarnings(
    'ignore',
    message=r'Failed to detect kernel helper: .*',
    category=UserWarning,
)


SECTION_ORDER = [
    'overview',
    'system',
    'cpu',
    'memory',
    'gpu',
    'disks',
    'display',
    'network',
    'architecture',
]

SECTION_ALIASES = {
    'arch': 'architecture',
    'disk': 'disks',
    'storage': 'disks',
    'all': 'all',
}

SECTION_TITLES = {
    'overview': 'SYSTEM OVERVIEW',
    'system': 'SYSTEM INFORMATION',
    'cpu': 'CPU INFORMATION',
    'memory': 'MEMORY INFORMATION',
    'gpu': 'GPU INFORMATION',
    'disks': 'DISK INFORMATION',
    'display': 'DISPLAY INFORMATION',
    'network': 'NETWORK INFORMATION',
    'architecture': 'SYSTEM ARCHITECTURE',
}


def _safe_call(label, collector):
    try:
        return collector()
    except Exception as error:
        return {
            'error': str(error),
            'source': label,
        }


def _collect_gpu_info():
    try:
        from gpu_integration import (
            get_gpu_display_association,
            get_gpu_list,
            get_gpu_pcie_info,
            get_gpu_utilization,
            get_intel_gpu_metrics,
        )

        gpus = get_gpu_list()
        gpu_utils = get_gpu_utilization()
        gpu_pcie_info = get_gpu_pcie_info()
        intel_metrics = get_intel_gpu_metrics()
        gpu_display_map = get_gpu_display_association()

        merged_gpus = []
        for gpu in gpus:
            name = gpu.get('name')
            merged = dict(gpu)
            if isinstance(gpu_utils, dict):
                merged.update(gpu_utils.get(name, {}))
            if isinstance(gpu_pcie_info, dict):
                merged.update(gpu_pcie_info.get(name, {}))
            if name and 'Intel' in name and isinstance(intel_metrics, dict):
                merged.update(intel_metrics)
            if isinstance(gpu_display_map, dict) and name in gpu_display_map:
                merged['display_association'] = gpu_display_map[name]
            merged_gpus.append(merged)
        return merged_gpus
    except Exception:
        return main.get_gpu_info()


def _collect_overview(interactive=False):
    system_info = _safe_call('get_system_info', lambda: main.get_system_info(interactive=interactive))
    memory_info = _safe_call('get_memory_extended_info', main.get_memory_extended_info)

    try:
        cpu_brand, cpu_arch = main.get_cpu_info_cores()
    except Exception as error:
        cpu_brand = 'Unavailable'
        cpu_arch = f'Unavailable ({error})'

    overview = {
        'hostname': system_info.get('hostname'),
        'model': system_info.get('model'),
        'manufacturer': system_info.get('manufacturer'),
        'serial': system_info.get('serial'),
        'platform': system_info.get('platform'),
        'os_name': system_info.get('os_name'),
        'os_release': system_info.get('os_release'),
        'processor': cpu_brand,
        'architecture': cpu_arch,
        'processor_count': system_info.get('processor_count'),
        'processor_physical': system_info.get('processor_physical'),
        'total_storage_gb': system_info.get('total_storage_gb'),
        'total_storage_free_gb': system_info.get('total_storage_free_gb'),
        'memory_total_gb': memory_info.get('total'),
        'memory_used_gb': memory_info.get('used'),
        'memory_available_gb': memory_info.get('available'),
        'memory_percent': memory_info.get('percent'),
        'boot_time': system_info.get('boot_time'),
        'uptime': system_info.get('uptime'),
    }
    
    result = {key: value for key, value in overview.items() if value is not None}
    
    # Preserve collection failures if they exist
    if '_collection_failures' in system_info:
        result['_collection_failures'] = system_info['_collection_failures']
    
    return result


def _get_collectors(interactive=False):
    return {
        'overview': lambda: _collect_overview(interactive=interactive),
        'system': lambda: _safe_call('get_system_info', lambda: main.get_system_info(interactive=interactive)),
        'cpu': lambda: _safe_call('get_cpu_extended_info', main.get_cpu_extended_info),
        'memory': lambda: _safe_call('get_memory_extended_info', main.get_memory_extended_info),
        'gpu': _collect_gpu_info,
        'disks': lambda: _safe_call('get_disk_info', main.get_disk_info),
        'display': lambda: _safe_call('get_monitor_info', main.get_monitor_info),
        'network': lambda: _safe_call('get_network_info', main.get_network_info),
        'architecture': lambda: _safe_call('get_pci_topology', main.get_pci_topology),
    }


def collect_sections(section_names, interactive=False):
    """Collect report sections
    
    Args:
        section_names: List of section names to collect
        interactive: If True, enable interactive mode (prompt for sudo password)
    """
    collectors = _get_collectors(interactive=interactive)
    return {name: collectors[name]() for name in section_names}


def _stringify(value):
    if value is None:
        return 'None'
    if isinstance(value, float):
        return f'{value:.2f}'
    return str(value)


def _labelize(key):
    return key.replace('_', ' ').strip().title()


def _boxed_heading(title):
    width = 62
    return [
        '╔' + ('═' * width) + '╗',
        f'║{title:^{width}}║',
        '╚' + ('═' * width) + '╝',
        '',
    ]


def _pick_item_title(item, index):
    if isinstance(item, dict):
        for key in ('name', 'model', 'device', 'device_path', 'mountpoint', 'interface', 'ssid', 'adapter', 'description'):
            value = item.get(key)
            if value:
                return f'[{index}] {value}'
    return f'[{index}]'


def _render_value(value, indent=0):
    prefix = ' ' * indent
    lines = []

    if isinstance(value, dict):
        if not value:
            return [f'{prefix}<empty>']
        scalar_items = []
        nested_items = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                nested_items.append((key, item))
            else:
                scalar_items.append((key, item))

        if scalar_items:
            width = max(len(_labelize(key)) for key, _ in scalar_items)
            for key, item in scalar_items:
                lines.append(f'{prefix}{_labelize(key):<{width}} : {_stringify(item)}')

        for key, item in nested_items:
            lines.append(f'{prefix}{_labelize(key)}:')
            lines.extend(_render_value(item, indent + 2))
        return lines

    if isinstance(value, list):
        if not value:
            return [f'{prefix}<empty>']
        for index, item in enumerate(value, start=1):
            if isinstance(item, (dict, list)):
                lines.append(f'{prefix}{_pick_item_title(item, index)}')
                lines.extend(_render_value(item, indent + 2))
            else:
                lines.append(f'{prefix}- {_stringify(item)}')
        return lines

    return [f'{prefix}{_stringify(value)}']


def render_text_report(report):
    lines = []
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines.extend(_boxed_heading('HALFAX SYSTEM REPORT'))
    lines.append(f'Generated: {timestamp}')
    lines.append('')
    
    # Collect all failures from all sections
    all_failures = []
    
    for section_name, data in report.items():
        # Extract and collect failures
        if isinstance(data, dict) and '_collection_failures' in data:
            all_failures.extend(data['_collection_failures'])
            # Remove the metadata from display
            data = {k: v for k, v in data.items() if k != '_collection_failures'}
        
        lines.extend(_boxed_heading(SECTION_TITLES.get(section_name, _labelize(section_name).upper())))
        lines.extend(_render_value(data))
        lines.append('')
    
    # Display collection failures if any
    if all_failures:
        lines.extend(_boxed_heading('⚠ ITEMS NOT COLLECTED'))
        for failure in all_failures:
            lines.append(f'  • {failure}')
        lines.append('')
    
    lines.extend(_boxed_heading('END OF REPORT'))
    return '\n'.join(lines).rstrip() + '\n'


def _parse_sections(raw_sections):
    if not raw_sections:
        return list(SECTION_ORDER)

    parsed = []
    for raw_section in raw_sections:
        for item in raw_section.split(','):
            section = item.strip().lower()
            if not section:
                continue
            section = SECTION_ALIASES.get(section, section)
            if section == 'all':
                return list(SECTION_ORDER)
            if section not in SECTION_ORDER:
                raise ValueError(
                    f'Unsupported section "{section}". Valid sections: ' + ', '.join(['all', *SECTION_ORDER])
                )
            if section not in parsed:
                parsed.append(section)
    return parsed or list(SECTION_ORDER)


def build_parser():
    parser = argparse.ArgumentParser(
        description='Headless CLI for Halfax System Reporter using the existing collection methods.'
    )
    parser.add_argument(
        '--section',
        action='append',
        help='Section to collect. Repeat or pass comma-separated values. Valid: all, ' + ', '.join(SECTION_ORDER),
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format. Default: text.',
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Enable interactive mode (prompt for sudo password if needed).',
    )
    parser.add_argument(
        '--output',
        help='Write output to a specific file. If not specified, auto-generates timestamped filename (e.g., halfaxsystemreport.20260427_113000.txt).',
    )
    return parser


def main_cli(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        sections = _parse_sections(args.section)
    except ValueError as error:
        parser.error(str(error))

    report = collect_sections(sections, interactive=args.interactive)
    if args.format == 'json':
        rendered = json.dumps(report, indent=2, default=str) + '\n'
        default_ext = 'json'
    else:
        rendered = render_text_report(report)
        default_ext = 'txt'

    # Determine output file
    output_file = args.output
    if not output_file:
        # Auto-generate timestamped filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'halfaxsystemreport.{timestamp}.{default_ext}'

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as handle:
        handle.write(rendered)
    
    # Print confirmation message
    sys.stdout.write(f'✓ Report saved to: {output_file}\n')
    
    return 0


if __name__ == '__main__':
    raise SystemExit(main_cli())