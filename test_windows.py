import os
import winrm
import paramiko
import hashlib
import warnings
import shutil
from dotenv import load_dotenv
from cryptography.utils import CryptographyDeprecationWarning

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)
warnings.filterwarnings('ignore', message='.*TripleDES.*')

# ANSI Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Status indicators with colors
SUCCESS_EMOJI = f"{GREEN}[PASS]{RESET}"
ERROR_EMOJI = f"{RED}[ERROR]{RESET}"

def print_success(message):
    """Print a success message in green"""
    print(f"{GREEN}{message}{RESET}")

def print_error(message):
    """Print an error message in red"""
    print(f"{RED}{message}{RESET}")

def print_info(message):
    """Print an info message in blue"""
    print(f"{BLUE}{message}{RESET}")

def print_warning(message):
    """Print a warning message in yellow"""
    print(f"{YELLOW}{message}{RESET}")

def load_environment():
    """Load environment variables from .env file"""
    load_dotenv()
    return {
        'host': os.getenv('WINRM_HOST'),
        'username': os.getenv('WINRM_USERNAME'),
        'password': os.getenv('WINRM_PASSWORD'),
        'ssh_port': int(os.getenv('SSH_PORT', '22'))  # Default SSH port is 22
    }

def create_winrm_session(credentials):
    """Create a WinRM session with the provided credentials"""
    return winrm.Session(
        credentials['host'],
        auth=(credentials['username'], credentials['password']),
        transport='ntlm',  # Using NTLM authentication
        server_cert_validation='ignore'  # Ignore SSL certificate validation
    )

def create_ssh_client(credentials):
    """Create and return a configured SSH client"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            credentials['host'],
            port=credentials['ssh_port'],
            username=credentials['username'],
            password=credentials['password']
        )
        return ssh
    except Exception as e:
        print(f"[ERROR] Failed to establish SSH connection: {str(e)}")
        return None

def execute_command(session, command):
    """Execute a command on the remote host using WinRM"""
    result = session.run_ps(command)  # Using PowerShell
    return {
        'status_code': result.status_code,
        'stdout': result.std_out.decode('utf-8'),
        'stderr': result.std_err.decode('utf-8')
    }

def check_execution_output(output_file):
    """
    Check if the execution was successful by looking for 'Exiting' in the output file
    """
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if "Exiting" in content:
                print_success(f"{SUCCESS_EMOJI} Execution verification passed: Found 'Exiting' in output")
                return True
            else:
                print_error(f"{ERROR_EMOJI} Execution verification failed: 'Exiting' not found in output")
                return False
    except Exception as e:
        print_error(f"{ERROR_EMOJI} Failed to read output file: {str(e)}")
        return False

def verify_output(output, expected_value):
    """Verify if the command output matches the expected value"""
    actual = output['stdout'].strip().lower()
    expected = expected_value.lower()
    
    if actual == expected:
        print(f"{SUCCESS_EMOJI} Test passed: Output matches expected value '{expected_value}'")
        return True
    else:
        print(f"{ERROR_EMOJI} Test failed: Expected '{expected_value}', got '{output['stdout'].strip()}'")
        return False

def get_file_hash(file_path):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read the file in chunks to handle large files efficiently
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_remote_file_hash(session, file_path):
    """Get SHA256 hash of a file on the remote Windows system"""
    ps_command = f"""
    $hash = Get-FileHash -Path '{file_path}' -Algorithm SHA256
    $hash.Hash.ToLower()
    """
    result = session.run_ps(ps_command)
    if result.status_code == 0:
        return result.std_out.decode('utf-8').strip()
    return None

def verify_file_integrity(winrm_session, local_path, remote_path):
    """Verify file integrity by comparing size and hash"""
    try:
        # Get local file details
        local_size = os.path.getsize(local_path)
        local_hash = get_file_hash(local_path)
        
        # Get remote file details using WinRM
        size_result = winrm_session.run_ps(f'(Get-Item "{remote_path}").Length')
        if size_result.status_code != 0:
            print_error(f"{ERROR_EMOJI} Failed to get remote file size")
            return False
            
        remote_size = int(size_result.std_out.decode('utf-8').strip())
        
        # Compare sizes
        if local_size != remote_size:
            print_error(f"{ERROR_EMOJI} Size verification failed: Local {local_size:,} bytes, Remote {remote_size:,} bytes")
            return False
        
        # Get and compare hashes
        remote_hash = get_remote_file_hash(winrm_session, remote_path)
        
        if not remote_hash:
            print_error(f"{ERROR_EMOJI} Failed to get remote file hash")
            return False
            
        if local_hash.lower() != remote_hash.lower():
            print_error(f"{ERROR_EMOJI} Hash verification failed")
            return False
            
        print_success(f"{SUCCESS_EMOJI} File integrity verified (SHA256: {local_hash})")
        return True
        
    except Exception as e:
        print_error(f"{ERROR_EMOJI} Verification failed: {str(e)}")
        return False

def copy_and_verify_file(winrm_session, credentials, local_path, remote_path):
    """
    Copy a file to the remote host using SSH/SCP and verify its presence
    """
    try:
        print(f"Copying file to {remote_path}...")
        
        # Create SSH client
        ssh = create_ssh_client(credentials)
        if not ssh:
            return False
            
        try:
            # Create SFTP client
            sftp = ssh.open_sftp()
            
            # Get file size
            file_size = os.path.getsize(local_path)
            print(f"File size: {file_size / (1024*1024):.2f} MB")
            
            # Copy the file
            sftp.put(local_path, remote_path, callback=lambda sent, total: print(f"Progress: {sent/total*100:.1f}%") if sent % (1024*1024) == 0 else None)
            
            # Verify file integrity
            return verify_file_integrity(winrm_session, local_path, remote_path)
                
        finally:
            sftp.close()
            ssh.close()
            
    except Exception as e:
        print(f"[ERROR] File transfer failed: {str(e)}")
        return False

def clean_runtime_directory():
    """
    Clean the runtime directory by removing all files
    """
    runtime_dir = "./runtime"
    try:
        # Create directory if it doesn't exist
        if not os.path.exists(runtime_dir):
            os.makedirs(runtime_dir)
            print_success(f"{SUCCESS_EMOJI} Created clean runtime directory")
            return True
            
        # Remove all files in the directory
        for filename in os.listdir(runtime_dir):
            file_path = os.path.join(runtime_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print_error(f"{ERROR_EMOJI} Failed to remove {file_path}: {str(e)}")
                return False
                
        print_success(f"{SUCCESS_EMOJI} Cleaned runtime directory")
        return True
        
    except Exception as e:
        print_error(f"{ERROR_EMOJI} Failed to clean runtime directory: {str(e)}")
        return False

def pull_files_by_pattern(session, credentials, remote_pattern, local_dir="./runtime"):
    """
    Pull files matching a pattern from remote system
    Args:
        session: WinRM session
        credentials: Credentials for SSH connection
        remote_pattern: File pattern to match (e.g., "C:\\path\\Collection-*.zip")
        local_dir: Local directory to save files
    """
    try:
        # Get list of files matching pattern
        ps_command = f"""
        Get-ChildItem -Path '{remote_pattern}' | Select-Object -ExpandProperty FullName
        """
        result = session.run_ps(ps_command)
        
        if result.status_code != 0:
            print_error(f"{ERROR_EMOJI} Failed to list files matching pattern")
            return False
            
        # Get file paths as list
        files = result.std_out.decode('utf-8').strip().split('\n')
        files = [f.strip() for f in files if f.strip()]  # Clean up paths
        
        if not files:
            print_warning(f"{YELLOW}No files found matching pattern: {remote_pattern}{RESET}")
            return False
            
        # Create SSH client for file transfer
        ssh = create_ssh_client(credentials)
        if not ssh:
            return False
            
        try:
            # Create SFTP client
            sftp = ssh.open_sftp()
            
            # Download each file
            for remote_path in files:
                try:
                    local_filename = os.path.basename(remote_path)
                    local_path = os.path.join(local_dir, local_filename)
                    
                    print_info(f"\nPulling file {remote_path}...")
                    sftp.get(remote_path, local_path)
                    print_success(f"{SUCCESS_EMOJI} File pulled successfully to {local_path}")
                except Exception as e:
                    print_error(f"{ERROR_EMOJI} Failed to pull {remote_path}: {str(e)}")
                    continue
                    
            return True
                
        finally:
            sftp.close()
            ssh.close()
            
    except Exception as e:
        print_error(f"{ERROR_EMOJI} Failed to pull files: {str(e)}")
        return False

def execute_remote_exe(session, exe_path, file_to_pull, credentials):
    """
    Execute the remote exe file and pull back the specified result file
    Args:
        session: WinRM session
        exe_path: Path to the executable on remote system
        file_to_pull: Path to the file that should be pulled back after execution
        credentials: Credentials for SSH connection
    """
    try:
        print_info(f"\nExecuting {exe_path}...")
        
        # Execute the file with proper command and redirection
        ps_command = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            # Change to the directory containing the exe
            Set-Location (Split-Path -Parent '{exe_path}')
            
            # Execute the command and redirect output
            $output = & '{exe_path}' 2>&1
            
            # Write output to a file
            $output | Out-File -FilePath '{file_to_pull}' -Encoding UTF8
            
            if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {{
                throw "Process exited with code $LASTEXITCODE"
            }}
            
            "Success"
        }} catch {{
            Write-Error "Failed to execute: $_"
            throw
        }}
        """
        
        result = session.run_ps(ps_command)
        
        if result.status_code == 0 and "Success" in result.std_out.decode('utf-8'):
            print_success(f"{SUCCESS_EMOJI} Execution completed")
            
            # Wait a moment to ensure file is ready
            session.run_ps("Start-Sleep -Seconds 2")
            
            # Check if the file exists before trying to pull it
            check_file = session.run_ps(f"Test-Path '{file_to_pull}'")
            if check_file.std_out.decode('utf-8').strip().lower() != 'true':
                print_error(f"{ERROR_EMOJI} File {file_to_pull} not found after execution")
                return False
                
            print_info(f"\nPulling file {file_to_pull}...")
            
            # Clean runtime directory before pulling new file
            if not clean_runtime_directory():
                return False
            
            # Create SSH client for file transfer
            ssh = create_ssh_client(credentials)
            if not ssh:
                return False
                
            try:
                # Create SFTP client
                sftp = ssh.open_sftp()
                
                # Get the filename from the path and create full local path
                local_filename = os.path.basename(file_to_pull)
                local_path = os.path.join("./runtime", local_filename)
                
                # Download the file
                sftp.get(file_to_pull, local_path)
                print_success(f"{SUCCESS_EMOJI} File pulled successfully to {local_path}")
                
                # Check the output file
                print_info("\nVerifying execution output...")
                if check_execution_output(local_path):
                    # After successful log file pull, pull the collection zip files
                    print_info("\nPulling Collection zip files...")
                    collection_pattern = "C:\\Windows\\Temp\\Collection-*.zip"
                    pull_files_by_pattern(session, credentials, collection_pattern)
                    return True
                return False
                
            finally:
                sftp.close()
                ssh.close()
        else:
            error_msg = result.std_err.decode('utf-8') if result.std_err else result.std_out.decode('utf-8')
            print_error(f"{ERROR_EMOJI} Execution failed: {error_msg}")
            return False
            
    except Exception as e:
        print_error(f"{ERROR_EMOJI} Failed to execute file or pull results: {str(e)}")
        return False

def main():
    # Load environment variables
    credentials = load_environment()
    
    # Verify all required credentials are present
    required_vars = ['host', 'username', 'password']
    missing_vars = [var for var in required_vars if not credentials[var]]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    try:
        # Create WinRM session
        winrm_session = create_winrm_session(credentials)
        
        # Execute whoami command
        print("Executing 'whoami' command...")
        result = execute_command(winrm_session, 'whoami')
        
        if result['status_code'] == 0:
            print(f"Command output: {result['stdout']}")
            # Verify if the output matches 'administrator'
            verify_output(result, 'win10-stand-alo\\administrator')
        else:
            print(f"Command failed with error: {result['stderr']}")

        # Copy and verify the Velociraptor collector file
        local_file = "datastore/Collector_velociraptor-v0.72.4-windows-amd64.exe"
        remote_file = "C:\\Windows\\Temp\\Collector_velociraptor.exe"
        print("\nStarting file copy operation...")
        if copy_and_verify_file(winrm_session, credentials, local_file, remote_file):
            # If file copy and verification succeeded, execute the file and pull back result
            file_to_pull = "C:\\Windows\\Temp\\Collector_velociraptor-v0.72.4-windows-amd64.exe.log"
            execute_remote_exe(winrm_session, remote_file, file_to_pull, credentials)
    
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main() 