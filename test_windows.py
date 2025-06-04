import os
import winrm
import paramiko
import hashlib
import warnings
from dotenv import load_dotenv
from cryptography.utils import CryptographyDeprecationWarning

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)
warnings.filterwarnings('ignore', message='.*TripleDES.*')

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

def verify_output(output, expected_value):
    """Verify if the command output matches the expected value"""
    actual = output['stdout'].strip().lower()
    expected = expected_value.lower()
    
    if actual == expected:
        print(f"[PASS] Test passed: Output matches expected value '{expected_value}'")
        return True
    else:
        print(f"[FAIL] Test failed: Expected '{expected_value}', got '{output['stdout'].strip()}'")
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
            print("[ERROR] Failed to get remote file size")
            return False
            
        remote_size = int(size_result.std_out.decode('utf-8').strip())
        
        # Compare sizes
        if local_size != remote_size:
            print(f"[ERROR] Size verification failed: Local {local_size:,} bytes, Remote {remote_size:,} bytes")
            return False
        
        # Get and compare hashes
        remote_hash = get_remote_file_hash(winrm_session, remote_path)
        
        if not remote_hash:
            print("[ERROR] Failed to get remote file hash")
            return False
            
        if local_hash.lower() != remote_hash.lower():
            print("[ERROR] Hash verification failed")
            return False
            
        print(f"[SUCCESS] File integrity verified (SHA256: {local_hash})")
        return True
        
    except Exception as e:
        print(f"[ERROR] Verification failed: {str(e)}")
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
        print(f"\nExecuting {exe_path}...")
        # Execute the file and wait for it to complete
        ps_command = f"""
        $process = Start-Process -FilePath '{exe_path}' -NoNewWindow -PassThru -Wait
        $process.ExitCode
        """
        result = session.run_ps(ps_command)
        
        if result.status_code == 0:
            print("[SUCCESS] Execution completed")
            
            # Wait a moment to ensure file is ready
            session.run_ps("Start-Sleep -Seconds 2")
            
            # Check if the file exists before trying to pull it
            check_file = session.run_ps(f"Test-Path '{file_to_pull}'")
            if check_file.std_out.decode('utf-8').strip().lower() != 'true':
                print(f"[ERROR] File {file_to_pull} not found after execution")
                return False
                
            print(f"\nPulling file {file_to_pull}...")
            
            # Create SSH client for file transfer
            ssh = create_ssh_client(credentials)
            if not ssh:
                return False
                
            try:
                # Create SFTP client
                sftp = ssh.open_sftp()
                
                # Create runtime directory if it doesn't exist
                runtime_dir = "./runtime"
                if not os.path.exists(runtime_dir):
                    os.makedirs(runtime_dir)
                
                # Get the filename from the path and create full local path
                local_filename = os.path.basename(file_to_pull)
                local_path = os.path.join(runtime_dir, local_filename)
                
                # Download the file
                sftp.get(file_to_pull, local_path)
                print(f"[SUCCESS] File pulled successfully to {local_path}")
                return True
                
            finally:
                sftp.close()
                ssh.close()
        else:
            print(f"[ERROR] Execution failed: {result.std_err.decode('utf-8')}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to execute file or pull results: {str(e)}")
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