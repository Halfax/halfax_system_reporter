#!/usr/bin/env python3
"""
Halfax Telemetry Driver - Complete Rebuild and Deployment Script
=================================================================
This script automates the full rebuild and deployment process:
  1. Auto-detect VS Developer environment
  2. Auto-elevate to Administrator if needed
  3. Build driver (.sys)
  4. Build broker (.exe)
  5. Stop old service
  6. Deploy new driver
  7. Create/start service
  8. Test functionality

Usage: python deploy_driver.py
       (or just double-click if .py is associated with Python)

Service Name: HalfaxTelemetry (original name, capital T)
Device Path: \\.\HalfaxTelemetry (original, no "2")
"""

import os
import sys
import subprocess
import time
import ctypes
import shutil
from pathlib import Path

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def is_admin():
    """Check if running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def elevate():
    """Re-launch script with Administrator privileges."""
    print("\nAdministrator privileges required. Elevating...")
    print()
    
    # Get the path to python.exe
    python_exe = sys.executable
    script_path = os.path.abspath(__file__)
    
    # Use ShellExecuteW to elevate
    ctypes.windll.shell32.ShellExecuteW(
        None, 
        "runas", 
        python_exe, 
        f'"{script_path}"', 
        os.path.dirname(script_path),
        1  # SW_SHOWNORMAL
    )
    sys.exit(0)

def find_vs_installation():
    """Find Visual Studio 2022 installation directory."""
    print("Looking for Visual Studio 2022 installation...")
    
    # Try manual paths first
    manual_paths = [
        r"C:\Program Files\Microsoft Visual Studio\2022\Community",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise"
    ]
    
    for path in manual_paths:
        vcvars_path = Path(path) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
        if vcvars_path.exists():
            print(f"  [OK] Found VS at: {path}")
            return path
    
    # Try vswhere.exe
    vswhere_path = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if vswhere_path.exists():
        try:
            result = subprocess.run(
                [str(vswhere_path), "-latest", "-products", "*", 
                 "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                 "-property", "installationPath"],
                capture_output=True,
                text=True,
                check=True
            )
            vs_path = result.stdout.strip()
            if vs_path:
                vcvars_path = Path(vs_path) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
                if vcvars_path.exists():
                    print(f"  [OK] Found VS at: {vs_path}")
                    return vs_path
        except:
            pass
    
    print("\n  [ERROR] Could not find Visual Studio 2022 installation.")
    print("  Please install Visual Studio 2022 with C++ Desktop Development workload.")
    return None

def setup_vs_environment(vs_path):
    """Set up Visual Studio environment variables."""
    print("\nSetting up VS Developer environment...")
    
    vcvars_path = Path(vs_path) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvars_path.exists():
        print(f"  [ERROR] vcvarsall.bat not found at: {vcvars_path}")
        return False
    
    # Create a batch file that calls vcvarsall and exports environment
    temp_bat = Path("temp_setup_env.bat")
    with open(temp_bat, 'w') as f:
        f.write('@echo off\n')
        f.write(f'call "{vcvars_path}" x64 >nul 2>&1\n')
        f.write('set\n')  # Output all environment variables
    
    try:
        # Run the batch file and capture environment
        result = subprocess.run(
            [str(temp_bat)],
            capture_output=True,
            text=True,
            shell=True
        )
        
        # Parse environment variables
        for line in result.stdout.split('\n'):
            if '=' in line:
                key, _, value = line.partition('=')
                os.environ[key] = value
        
        # Verify msbuild is now in PATH
        msbuild_check = subprocess.run(
            ['where', 'msbuild.exe'],
            capture_output=True,
            text=True
        )
        
        if msbuild_check.returncode == 0:
            print("  [OK] VS environment configured successfully")
            return True
        else:
            print("  [ERROR] Failed to configure VS environment")
            return False
            
    finally:
        if temp_bat.exists():
            temp_bat.unlink()
    
    return False

def run_command(cmd, description, shell=False):
    """Run a command and handle errors."""
    print(f"\n{description}...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=shell,
            check=True
        )
        print(f"  [OK] {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] {description} failed")
        if e.stdout:
            print(f"  Output: {e.stdout}")
        if e.stderr:
            print(f"  Error: {e.stderr}")
        return False

def build_driver():
    """Build the kernel driver."""
    print("\n[Step 1/7] Building kernel driver...")
    
    cmd = [
        'msbuild',
        'halfax_telemetry_driver.vcxproj',
        '/p:Configuration=Release',
        '/p:Platform=x64',
        '/nologo',
        '/verbosity:minimal'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Check if output file exists
        driver_path = Path('x64') / 'Release' / 'halfax_telemetry_driver.sys'
        if driver_path.exists():
            print(f"  [OK] Driver built successfully")
            return True
        else:
            print(f"  [ERROR] Driver .sys file not found after build")
            return False
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Driver build failed")
        if e.stdout:
            print(f"  Output: {e.stdout}")
        if e.stderr:
            print(f"  Error: {e.stderr}")
        return False

def build_broker():
    """Build the kernel broker."""
    print("\n[Step 2/7] Building kernel broker...")
    
    cmd = [
        'cl',
        '/nologo',
        '/EHsc',
        '/std:c++17',
        '/W4',
        '/Ox',
        '/Iinclude',
        'halfax_kernel_broker.cpp',
        'halfax_guid.cpp',
        'setupapi.lib',
        '/Fe:halfax_kernel_broker.exe'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Check if output file exists
        if Path('halfax_kernel_broker.exe').exists():
            print(f"  [OK] Broker built successfully")
            # Clean up intermediate files
            for ext in ['.obj']:
                for f in Path('.').glob(f'*{ext}'):
                    f.unlink(missing_ok=True)
            return True
        else:
            print(f"  [ERROR] Broker .exe file not found after build")
            return False
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Broker build failed")
        if e.stdout:
            print(f"  Output: {e.stdout}")
        if e.stderr:
            print(f"  Error: {e.stderr}")
        return False

def service_exists(service_name):
    """Check if a service exists."""
    result = subprocess.run(
        ['sc.exe', 'query', service_name],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

def stop_service(service_name):
    """Stop a service if it's running."""
    if service_exists(service_name):
        subprocess.run(
            ['sc.exe', 'stop', service_name],
            capture_output=True,
            text=True
        )
        time.sleep(2)

def delete_service(service_name):
    """Delete a service if it exists."""
    if service_exists(service_name):
        result = subprocess.run(
            ['sc.exe', 'delete', service_name],
            capture_output=True,
            text=True
        )
        time.sleep(2)
        return result.returncode == 0
    return True

def cleanup_old_services():
    """Stop and delete old services."""
    print("\n[Step 3/7] Cleaning up old services...")
    
    # Check both possible service names
    for service_name in ['HalfaxTelemetry', 'halfax_telemetry']:
        if service_exists(service_name):
            print(f"  Stopping service: {service_name}")
            stop_service(service_name)
            print(f"  Deleting service: {service_name}")
            delete_service(service_name)
    
    print("  [OK] Old services cleaned up")

def deploy_driver():
    """Copy driver to System32\drivers."""
    print("\n[Step 4/7] Deploying driver to System32\\drivers...")
    
    source = Path('x64') / 'Release' / 'halfax_telemetry_driver.sys'
    dest = Path(r'C:\Windows\System32\drivers\halfax_telemetry_driver.sys')
    
    try:
        shutil.copy2(source, dest)
        print(f"  [OK] Driver deployed")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to deploy driver: {e}")
        print(f"  The file might be in use. Try rebooting and running this script again.")
        return False

def create_service():
    """Create the HalfaxTelemetry service."""
    print("\n[Step 5/7] Creating service HalfaxTelemetry...")
    
    # First check if service already exists
    if service_exists('HalfaxTelemetry'):
        print(f"  [INFO] Service already exists, deleting first...")
        delete_service('HalfaxTelemetry')
        time.sleep(2)
    
    # Verify driver file exists before creating service
    driver_path = Path(r'C:\Windows\System32\drivers\halfax_telemetry_driver.sys')
    if not driver_path.exists():
        print(f"  [ERROR] Driver file not found: {driver_path}")
        return False
    
    print(f"  [INFO] Driver file verified: {driver_path}")
    
    cmd = [
        'sc.exe',
        'create',
        'HalfaxTelemetry',
        'type=',
        'kernel',
        'start=',
        'demand',
        'binPath=',
        r'C:\Windows\System32\drivers\halfax_telemetry_driver.sys'
    ]
    
    print(f"  [INFO] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(f"  [INFO] Return code: {result.returncode}")
    if result.stdout:
        print(f"  [INFO] Output: {result.stdout}")
    if result.stderr:
        print(f"  [INFO] Error: {result.stderr}")
    
    if result.returncode == 0:
        print(f"  [OK] Service created successfully")
        
        # Verify service was actually created
        if service_exists('HalfaxTelemetry'):
            print(f"  [OK] Service creation verified")
            return True
        else:
            print(f"  [ERROR] Service creation command succeeded but service not found")
            return False
    else:
        print(f"  [ERROR] Failed to create service")
        return False

def start_service():
    """Start the HalfaxTelemetry service."""
    print("\n[Step 6/7] Starting service...")
    
    # First verify service exists
    if not service_exists('HalfaxTelemetry'):
        print(f"  [ERROR] Service does not exist, cannot start")
        return False
    
    print(f"  [INFO] Service exists, attempting to start...")
    
    result = subprocess.run(
        ['sc.exe', 'start', 'HalfaxTelemetry'],
        capture_output=True,
        text=True
    )
    
    print(f"  [INFO] Start command return code: {result.returncode}")
    if result.stdout:
        print(f"  [INFO] Start output: {result.stdout}")
    if result.stderr:
        print(f"  [INFO] Start error: {result.stderr}")
    
    if result.returncode != 0:
        print(f"  [ERROR] Failed to start service")
        print("\n  Check Event Viewer for details:")
        print("    Windows Logs > System")
        print("  Or Code Integrity log:")
        print("    Applications and Services > Microsoft > Windows > CodeIntegrity > Operational")
        return False
    
    print(f"  [INFO] Service start command succeeded, waiting for initialization...")
    time.sleep(3)  # Give driver time to initialize
    
    # Verify service is running
    print(f"  [INFO] Verifying service state...")
    result = subprocess.run(
        ['sc.exe', 'query', 'HalfaxTelemetry'],
        capture_output=True,
        text=True
    )
    
    print(f"  [INFO] Service query result: {result.stdout}")
    
    if 'RUNNING' in result.stdout:
        print(f"  [OK] Service started and running")
        
        # Additional verification: check if device object exists
        print(f"  [INFO] Checking device object availability...")
        device_check = subprocess.run(
            ['dir', '\\\\.\\HalfaxTelemetry'],
            capture_output=True,
            text=True,
            shell=True
        )
        
        if device_check.returncode == 0:
            print(f"  [OK] Device object is accessible")
            return True
        else:
            print(f"  [WARNING] Service running but device object not accessible")
            print(f"  [INFO] Device check error: {device_check.stderr}")
            return False
    else:
        print(f"  [ERROR] Service started but not in RUNNING state")
        print(f"  [INFO] Service state: {result.stdout}")
        return False

def test_broker():
    """Test broker communication with driver."""
    print("\n[Step 7/7] Testing broker communication...")
    
    # First verify broker executable exists
    broker_path = Path('halfax_kernel_broker.exe')
    if not broker_path.exists():
        print(f"  [ERROR] Broker executable not found: {broker_path}")
        return False
    
    print(f"  [INFO] Broker executable found: {broker_path}")
    
    # Test basic version command
    print(f"  [INFO] Testing basic broker communication...")
    result = subprocess.run(
        ['halfax_kernel_broker.exe', '--version'],
        capture_output=True,
        text=True
    )
    
    print(f"  [INFO] Version test return code: {result.returncode}")
    if result.stdout:
        print(f"  [INFO] Version output: {result.stdout.strip()}")
    if result.stderr:
        print(f"  [INFO] Version error: {result.stderr}")
    
    if result.returncode == 0:
        print(f"  [OK] Basic broker communication successful")
        
        # Test hardware access capabilities
        print(f"  [INFO] Testing hardware access capabilities...")
        
        # Test MSR read (safe MSR)
        print(f"  [INFO] Testing MSR read (0xCE)...")
        msr_result = subprocess.run(
            ['halfax_kernel_broker.exe', '--read-msr', '0', '0xCE'],
            capture_output=True,
            text=True
        )
        
        print(f"  [INFO] MSR test return code: {msr_result.returncode}")
        if msr_result.stdout:
            print(f"  [INFO] MSR output: {msr_result.stdout.strip()}")
        if msr_result.stderr:
            print(f"  [INFO] MSR error: {msr_result.stderr}")
        
        if msr_result.returncode == 0:
            print(f"  [OK] Hardware access working - driver fully functional")
            return True
        else:
            print(f"  [WARNING] Basic communication works but hardware access failed")
            print(f"  [INFO] This indicates driver loaded but hardware initialization failed")
            return False
    else:
        print(f"  [ERROR] Broker test failed - no communication with driver")
        return False

def main():
    """Main deployment process."""
    print("\n" + "="*80)
    print("   Halfax Telemetry Driver - Rebuild and Deploy")
    print("="*80 + "\n")
    
    # Check for admin privileges
    if not is_admin():
        elevate()
        return
    
    print("[Step 0/7] Checking prerequisites...")
    
    # Check if we're already in VS environment
    msbuild_check = subprocess.run(
        ['where', 'msbuild.exe'],
        capture_output=True,
        text=True
    )
    
    if msbuild_check.returncode != 0:
        # Need to setup VS environment
        vs_path = find_vs_installation()
        if not vs_path:
            input("\nPress Enter to exit...")
            sys.exit(1)
        
        if not setup_vs_environment(vs_path):
            input("\nPress Enter to exit...")
            sys.exit(1)
    else:
        print("  [OK] VS environment already configured")
    
    # Verify prerequisites
    for tool in ['msbuild.exe', 'cl.exe']:
        result = subprocess.run(
            ['where', tool],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"  [ERROR] {tool} not found after environment setup")
            input("\nPress Enter to exit...")
            sys.exit(1)
    
    print("  [OK] Prerequisites met\n")
    
    # Execute build and deployment steps
    if not build_driver():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    if not build_broker():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    cleanup_old_services()
    
    if not deploy_driver():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    if not create_service():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    if not start_service():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    if not test_broker():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # Success summary
    print("\n" + "="*80)
    print("   DEPLOYMENT SUCCESSFUL")
    print("="*80)
    print("\nService Name:    HalfaxTelemetry")
    print("Service Status:  RUNNING")
    print("Device Path:     \\\\.\\HalfaxTelemetry")
    print("Driver Location: C:\\Windows\\System32\\drivers\\halfax_telemetry_driver.sys")
    print("Broker:          halfax_kernel_broker.exe")
    print("\nNext steps:")
    print("  1. Test MSR read:")
    print("     halfax_kernel_broker.exe --read-msr 0 0xCE")
    print("\n  2. Test Python integration:")
    print("     python main_integration_example.py")
    print("\n  3. Check service anytime:")
    print("     sc.exe query HalfaxTelemetry")
    print("\n" + "="*80 + "\n")
    
    input("Press Enter to exit...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDeployment cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
