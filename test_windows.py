import os
import winrm
import paramiko
from dotenv import load_dotenv

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
            print(f"Total file size: {file_size / (1024*1024):.2f} MB")
            
            # Copy the file
            sftp.put(local_path, remote_path, callback=lambda sent, total: print(f"Progress: {sent/total*100:.1f}%") if sent % (1024*1024) == 0 else None)
            
            print("File copy completed successfully")
            
            # Verify file presence and size using WinRM
            verify_result = winrm_session.run_ps(f'Get-Item "{remote_path}" | Select-Object Length')
            if verify_result.status_code == 0:
                remote_size = int(verify_result.std_out.decode().strip().split('\n')[-1])
                if remote_size == file_size:
                    print(f"[SUCCESS] File successfully verified at {remote_path}")
                    print(f"[SUCCESS] File size matches: {remote_size} bytes")
                    return True
                else:
                    print(f"[ERROR] File size mismatch. Expected: {file_size}, Got: {remote_size}")
                    return False
            else:
                print(f"[ERROR] File verification failed: {verify_result.std_err.decode('utf-8')}")
                return False
                
        finally:
            sftp.close()
            ssh.close()
            
    except Exception as e:
        print(f"[ERROR] An error occurred during file copy: {str(e)}")
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
        copy_and_verify_file(winrm_session, credentials, local_file, remote_file)
        
        # List the directory contents to verify
        print("\nListing directory contents:")
        ls_result = execute_command(winrm_session, f'Get-ChildItem "C:\\Windows\\Temp\\Collector_velociraptor.exe"')
        if ls_result['status_code'] == 0:
            print(f"Directory listing:\n{ls_result['stdout']}")
        else:
            print(f"Failed to list directory: {ls_result['stderr']}")
    
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main() 