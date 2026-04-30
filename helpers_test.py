import traceback

import main

helpers = [
    'get_memory_extended_info',
    'get_cpu_info_cores',
    'get_cpu_extended_info',
    'get_gpu_info',
    'get_monitor_info',
    'get_disk_info',
    'get_system_info',
    'get_network_info',
    'get_pci_topology'
]

for h in helpers:
    print('---', h)
    try:
        fn = getattr(main, h)
        res = fn()
        print('OK, type:', type(res))
    except Exception as e:
        print('ERROR:', e)
        traceback.print_exc()
