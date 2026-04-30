import psutil


def get_cpuid_topology():
    """
    Best-effort CPUID topology parser fallback.
    If a user-mode `cpuid_helper.exe` is present and provides topology, prefer that.
    This function builds a conservative APIC/core mapping when helper output is unavailable.

    Returns a dict:
      {
        'apic_ids': [ { 'index': N, 'apic': X, 'core_type': 64, 'l1d_group': N, 'l2_group': N, 'l3_group': 0 }, ... ],
        'smt_status': 'Yes/No (N:1 threads)'
      }
    """
    topology = {
        'apic_ids': [],
        'smt_status': 'Unknown'
    }

    try:
        logical = psutil.cpu_count(logical=True) or 1
        physical = psutil.cpu_count(logical=False) or logical
        # Infer SMT status
        if logical and physical and logical > physical:
            topology['smt_status'] = f'Yes ({logical // physical}:1 threads)'
        else:
            topology['smt_status'] = 'No (disabled or not present)'

        # Conservative mapping: APIC == logical index, mark all cores as P-core (core_type 64)
        for i in range(logical):
            entry = {
                'index': i,
                'apic': i,
                'core_type': 64,  # 64 -> P-core by convention in this project
                'l1d_group': i,
                'l2_group': i,
                'l3_group': 0
            }
            topology['apic_ids'].append(entry)

    except Exception:
        topology['apic_ids'] = []
        topology['smt_status'] = 'Unknown'

    return topology
