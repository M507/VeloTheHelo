import sys
import subprocess
import time
from pathlib import Path
import os
import shutil

# ANSI Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(message):
    """Print a formatted header message"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}== {message}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")

def print_success(message):
    """Print a success message in green"""
    print(f"{GREEN}{message}{RESET}")

def print_error(message):
    """Print an error message in red"""
    print(f"{RED}{message}{RESET}")

def print_info(message):
    """Print an info message in blue"""
    print(f"{BLUE}{message}{RESET}")

def cleanup_directories():
    """
    Clean up runtime and runtime_zip directories by removing all contents
    """
    directories = ['runtime', 'runtime_zip']
    for dir_name in directories:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print_info(f"Cleaning {dir_name} directory...")
            try:
                # Remove all contents of the directory
                for item in dir_path.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                print_success(f"Cleaned {dir_name} directory")
            except Exception as e:
                print_error(f"Error cleaning {dir_name} directory: {str(e)}")
        else:
            # Create the directory if it doesn't exist
            dir_path.mkdir(exist_ok=True)
            print_success(f"Created {dir_name} directory")

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
    
    # Clean up directories before starting
    print_header("Cleaning up directories")
    cleanup_directories()
    
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