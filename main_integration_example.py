#!/usr/bin/env python3
"""
Halfax System Reporter - Kernel Helper Integration Example

Shows how to integrate the kernel helper as a first-class data source
with proper audit trails, failure-mode UX, and semantic data collection.

This is a template for integrating into your actual main.py.
"""

import json
from datetime import datetime
from typing import Dict, Any
from halfax_kernel_helper import (
    KernelHelper,
    KernelHelperNotAvailable,
    KernelHelperError,
    HelperPresence
)


def gather_kernel_telemetry() -> Dict[str, Any]:
    """
    Gather privileged telemetry via kernel helper (first-class data source).
    
    Returns comprehensive report with:
    - Audit anchor (source identity, capabilities, provenance)
    - Semantic data (temperatures, power, energy)
    - Explicit failure reasons (no silent degradation)
    """
    helper = KernelHelper()
    
    # Start with audit anchor (standardized for all data sources)
    report = {
        "kernel_helper": helper.get_info_dict(),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    # Three-state presence model determines what we collect
    presence = helper.get_presence_state()
    
    if presence == HelperPresence.ABSENT:
        # Helper not available - explicit reason, no silent fallback
        report["data"] = {
            "reason": "kernel_helper_not_available",
            "message": "Driver not loaded or broker not found",
            "fallback": "using_user_mode_apis"  # Document your fallback strategy
        }
        return report
    
    # Helper is present (limited or full) - collect what we can
    report["data"] = {}
    
    #
    # Core Temperatures (semantic API, per-core data with provenance)
    #
    try:
        temps = helper.read_core_temperatures()
        
        # Convert to reportable format with per-metric provenance
        temp_data = {
            "source": "kernel_helper",
            "method": "read_core_temperatures",
            "per_core": {}
        }
        
        for core, data in temps.items():
            if data and 'celsius' in data:
                temp_data["per_core"][f"core_{core}"] = {
                    "celsius": data["celsius"],
                    "tj_max": data["tj_max"],
                    "margin_celsius": data["margin"],
                    "provenance": {
                        "source": data["source"],
                        "msr": data["msr"]
                    }
                }
            elif data and 'error' in data:
                temp_data["per_core"][f"core_{core}"] = {
                    "error": data["error"],
                    "reason": data["reason"]
                }
            else:
                temp_data["per_core"][f"core_{core}"] = {
                    "error": "unavailable",
                    "reason": "MSR read returned None"
                }
        
        report["data"]["temperatures"] = temp_data
        
    except KernelHelperNotAvailable:
        report["data"]["temperatures"] = {
            "error": "kernel_helper_not_available",
            "reason": "Driver became unavailable during collection"
        }
    except KernelHelperError as e:
        report["data"]["temperatures"] = {
            "error": type(e).__name__,
            "reason": str(e)
        }
    
    #
    # Package Power Limits (semantic API with decoded values)
    #
    try:
        power = helper.read_package_power()
        
        if power and 'pl1' in power:
            report["data"]["power_limits"] = {
                "source": power["source"],
                "msr": power["msr"],
                "pl1": {
                    "watts": round(power["pl1"]["watts"], 2),
                    "enabled": power["pl1"]["enabled"],
                    "clamping": power["pl1"]["clamp"]
                },
                "pl2": {
                    "watts": round(power["pl2"]["watts"], 2),
                    "enabled": power["pl2"]["enabled"],
                    "clamping": power["pl2"]["clamp"]
                }
            }
        elif power and 'error' in power:
            report["data"]["power_limits"] = {
                "error": power["error"],
                "reason": power["reason"]
            }
        else:
            report["data"]["power_limits"] = {
                "error": "unavailable",
                "reason": "MSR read returned None"
            }
    except (KernelHelperNotAvailable, KernelHelperError) as e:
        report["data"]["power_limits"] = {
            "error": type(e).__name__,
            "reason": str(e)
        }
    
    #
    # RAPL Energy Counters (for power monitoring over time)
    #
    try:
        energy = helper.read_energy_counters()
        
        if "error" not in energy:
            report["data"]["energy_counters"] = {
                "source": energy["source"],
                "note": "Take deltas over time to compute power consumption",
                "domains": {}
            }
            
            for domain in ["package", "cores", "dram", "uncore"]:
                if domain in energy and "counter" in energy[domain]:
                    report["data"]["energy_counters"]["domains"][domain] = {
                        "counter": energy[domain]["counter"],
                        "joules_per_unit": energy[domain]["joules_per_unit"],
                        "provenance": {
                            "msr": energy[domain]["msr"]
                        }
                    }
                elif domain in energy:
                    report["data"]["energy_counters"]["domains"][domain] = {
                        "error": energy[domain].get("error", "unavailable")
                    }
        else:
            report["data"]["energy_counters"] = {
                "error": "read_failed",
                "reason": energy.get("error", "Unknown error")
            }
    except (KernelHelperNotAvailable, KernelHelperError) as e:
        report["data"]["energy_counters"] = {
            "error": type(e).__name__,
            "reason": str(e)
        }
    
    #
    # Turbo Boost Ratios (CPU frequency limits)
    #
    try:
        ratios = helper.read_turbo_ratios()
        
        if ratios and '1_core_active' in ratios:
            report["data"]["turbo_ratios"] = {
                "source": ratios["source"],
                "msr": ratios["msr"],
                "ratios": {
                    k: {"ratio": v, "ghz": round(v / 10.0, 1)}
                    for k, v in ratios.items()
                    if k not in ["source", "msr"]
                }
            }
        elif ratios and 'error' in ratios:
            report["data"]["turbo_ratios"] = {
                "error": ratios["error"],
                "reason": ratios["reason"]
            }
        else:
            report["data"]["turbo_ratios"] = {
                "error": "unavailable",
                "reason": "MSR read returned None"
            }
    except (KernelHelperNotAvailable, KernelHelperError) as e:
        report["data"]["turbo_ratios"] = {
            "error": type(e).__name__,
            "reason": str(e)
        }
    
    return report


def generate_ui_status_block(report: Dict[str, Any]) -> str:
    """
    Generate UI status block for "Overview" tab.
    
    Shows kernel helper status as: off / limited / full
    with hover/expand for details.
    """
    kernel_info = report.get("kernel_helper", {})
    presence = kernel_info.get("presence", "absent")
    
    # Map presence to UI-friendly labels
    status_labels = {
        "absent": "Off",
        "present_but_limited": "Limited",
        "present_full": "Full"
    }
    
    # Color/icon hints
    status_icons = {
        "absent": "⚪",
        "present_but_limited": "🟡",
        "present_full": "🟢"
    }
    
    status = status_labels.get(presence, "Unknown")
    icon = status_icons.get(presence, "❓")
    
    lines = [
        f"Kernel Helper: {icon} {status}",
    ]
    
    if kernel_info.get("available"):
        lines.append(f"  Version: {kernel_info.get('driver_version', 'unknown')}")
        lines.append(f"  Protocol: v{kernel_info.get('protocol_version', '?')}")
        lines.append(f"  Whitelist: {kernel_info.get('msr_whitelist_version', 'unknown')}")
        
        caps = kernel_info.get("capabilities", {}).get("decoded", {})
        lines.append("  Capabilities:")
        for name, enabled in caps.items():
            check = "✓" if enabled else "✗"
            lines.append(f"    {check} {name}")
    else:
        reason = kernel_info.get("reason", "Unknown")
        lines.append(f"  Reason: {reason}")
    
    return "\n".join(lines)


def main():
    """Demo integration."""
    print("Halfax System Reporter - Kernel Helper Integration Demo")
    print("=" * 60)
    print()
    
    # Gather kernel telemetry
    print("Gathering kernel telemetry...")
    report = gather_kernel_telemetry()
    
    # Show UI status block
    print("\n" + "=" * 60)
    print("UI Status Block (for Overview tab):")
    print("=" * 60)
    print(generate_ui_status_block(report))
    
    # Show full report as JSON
    print("\n" + "=" * 60)
    print("Full Report (for JSON export / internal use):")
    print("=" * 60)
    print(json.dumps(report, indent=2))
    
    # Show example of extracting specific metrics
    print("\n" + "=" * 60)
    print("Example: Extracting Temperature Data for Display")
    print("=" * 60)
    
    temps = report.get("data", {}).get("temperatures", {})
    if "per_core" in temps:
        print("\nCPU Temperatures:")
        for core_name, core_data in sorted(temps["per_core"].items()):
            if "celsius" in core_data:
                print(f"  {core_name}: {core_data['celsius']:.1f}°C")
            elif "error" in core_data:
                print(f"  {core_name}: {core_data['reason']}")
    elif "error" in temps:
        print(f"\nTemperatures unavailable: {temps['reason']}")
    
    # Show provenance example
    print("\n" + "=" * 60)
    print("Example: Per-Metric Provenance (Audit Trail)")
    print("=" * 60)
    
    if "per_core" in temps:
        first_core = list(temps["per_core"].values())[0]
        if "provenance" in first_core:
            print("\nTemperature data provenance:")
            print(f"  Source: {first_core['provenance']['source']}")
            print(f"  Method: {first_core['provenance']['msr']}")
            print("\nThis tells users exactly where the data came from.")
    
    print("\n" + "=" * 60)
    print("Integration Notes:")
    print("=" * 60)
    print("""
1. Add to your main.py:
   from halfax_kernel_helper import KernelHelper
   
   # In your data collection function:
   kernel_data = gather_kernel_telemetry()
   
2. Include in final report:
   report = {
       "system_info": gather_system_info(),
       "kernel_telemetry": kernel_data,  # <-- Add this
       "cpu": gather_cpu_info(),
       ...
   }

3. UI Display:
   - Overview tab: Show generate_ui_status_block() output
   - CPU tab: Show temps["per_core"] data
   - Power tab: Show power_limits and energy_counters
   
4. Failure Mode UX:
   - Never silently drop fields
   - Always show "reason" when data unavailable
   - Distinguish "driver not present" from "MSR not whitelisted"

5. Testing:
   - Run: python test_kernel_broker.py (CLI tests)
   - Run: python test_halfax_kernel_helper.py (Python tests)
   - Both work without driver loaded (mocked tests)
""")


if __name__ == "__main__":
    main()
