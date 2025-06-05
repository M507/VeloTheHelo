import sys
import subprocess
import time
from pathlib import Path
import os
from colors import print_success, print_error, print_info, print_warning, SUCCESS_EMOJI, ERROR_EMOJI

def print_header(message):
    """Print a formatted header message"""
    print_info(f"\n{'='*80}")
    print_info(f"== {message}")
    print_info(f"{'='*80}\n")

def run_script(script_name):
    """
    Run a Python script and return True if it succeeds, False otherwise
    """
    try:
        print_info(f"Running {script_name}...")
        result = subprocess.run([sys.executable, script_name], check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print_error(f"Error running {script_name}: {str(e)}")
        return False
    except Exception as e:
        print_error(f"Unexpected error running {script_name}: {str(e)}")
        return False

def check_runtime_directory():
    """
    Check if runtime directory exists and has zip files
    """
    runtime_dir = Path("runtime")
    if not runtime_dir.exists():
        print_error("Runtime directory not found")
        return False
    
    zip_files = list(runtime_dir.glob("*.zip"))
    if not zip_files:
        print_error("No zip files found in runtime directory")
        return False
    
    print_success(f"Found {len(zip_files)} zip file(s) in runtime directory")
    return True

def main():
    """
    Main function to orchestrate the execution of both scripts
    """
    start_time = time.time()
    
    print_header("Starting Collector Workflow")
    
    # Step 1: Run test_windows.py
    print_header("Step 1: Running Windows Tests and Collection")
    if not run_script("test_windows.py"):
        print_error("Windows tests failed. Stopping workflow.")
        return
    
    # Verify runtime directory has zip files
    print_header("Verifying Collection Results")
    if not check_runtime_directory():
        print_error("No collection results found. Stopping workflow.")
        return
    
    # Give a small delay to ensure files are fully written
    time.sleep(2)
    
    # Step 2: Run process_zip_files.py
    print_header("Step 2: Processing Collection Files")
    if not run_script("process_zip_files.py"):
        print_error("Processing zip files failed.")
        return
    
    # Calculate total execution time
    execution_time = time.time() - start_time
    
    print_header("Workflow Complete")
    print_success(f"Total execution time: {execution_time:.2f} seconds")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_error("\nWorkflow interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {str(e)}")
        sys.exit(1) 