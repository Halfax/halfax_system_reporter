"""
Standalone script to remove and clean up the HalfaxTelemetry kernel driver before reboot.
Run this script to stop and delete the service, remove driver files, and clean up registry entries.
After reboot, you can safely rebuild and install the new driver.
"""

import subprocess
import os
import sys
import time

DRIVER_SERVICE = "HalfaxTelemetry"
DRIVER_SYS_PATHS = [
    r"C:\Windows\System32\drivers\halfax_telemetry_driver.sys",
    r"C:\Windows\System32\DriverStore\FileRepository\halfax_telemetry_driver.inf*"
]
DRIVER_INF_PATHS = [
    r"C:\Windows\INF\halfax_telemetry.inf"
]
BROKER_EXE = "halfax_kernel_broker.exe"


def run_cmd(cmd, check=True):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
    return result.returncode


def stop_and_delete_service():
    run_cmd(f"sc stop {DRIVER_SERVICE}", check=False)
    time.sleep(2)
    run_cmd(f"sc delete {DRIVER_SERVICE}", check=False)
    time.sleep(2)


def remove_driver_files():
    for path in DRIVER_SYS_PATHS:
        run_cmd(f"del /F /Q {path}", check=False)
    for path in DRIVER_INF_PATHS:
        run_cmd(f"del /F /Q {path}", check=False)


def remove_from_driver_store():
    run_cmd(f"pnputil /delete-driver halfax_telemetry_driver.inf /uninstall /force", check=False)


def main():
    print("--- HalfaxTelemetry Kernel Driver Cleanup ---")
    stop_and_delete_service()
    remove_driver_files()
    remove_from_driver_store()
    print("Cleanup complete. Please reboot before rebuilding and installing the new driver.")

if __name__ == "__main__":
    main()
