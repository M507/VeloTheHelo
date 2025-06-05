import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Central configuration class for all scripts"""
    
    @staticmethod
    def get(key: str, default: str = '') -> str:
        """Get configuration value from environment or default"""
        value = os.getenv(key)
        if value is None or value.strip() == '':
            return Config.DEFAULTS.get(key, default)
        return value

    @staticmethod
    def print_config():
        """Print current configuration"""
        print("\nCurrent Configuration:")
        print("-" * 50)
        for key in Config.DEFAULTS.keys():
            value = Config.get(key)
            # Mask password in output
            if 'PASSWORD' in key:
                value = '****' if value else ''
            print(f"{key}: {value}")
        print("-" * 50)

    # Default values for all configuration
    DEFAULTS = {
        # WinRM and SSH Configuration
        'WINRM_HOST_WIN10': '',
        'WINRM_HOST_WIN11': '',
        'WINRM_HOST_WINServer12': '',
        'WINRM_HOST_WINServer16': '',
        'WINRM_HOST_WINServer19': '',
        'WINRM_HOST_WINServer22': '',
        'WINRM_HOST_WINServer25': '',
        'WINRM_USERNAME': '',
        'WINRM_PASSWORD': '',
        'SSH_PORT': '22',
        
        # Velociraptor Paths
        'COLLECTOR_FILE': os.path.join('datastore', 'Collector_velociraptor-v0.72.4-windows-amd64.exe'),
        'VELO_BINARY_PATH': os.path.join('binaries', 'velociraptor-v0.72.4-windows-amd64.exe'),
        'VELO_SERVER_CONFIG': os.path.join('datastore', 'server.config.yaml'),
        
        # Artifact Testing Configuration
        'ARTIFACT_TEMPLATE_PATH': os.path.join('specs', 'test.yaml'),
        'ARTIFACT_LIST_FILE': os.path.join('testing', 'All_Windows_Artifacts.txt'),
        'ARTIFACT_SPECS_DIR': 'testing_specs',
        'ARTIFACT_COLLECTORS_DIR': 'collectors',
        
        # Runtime Directories
        'RUNTIME_DIR': 'runtime',
        'RUNTIME_ZIP_DIR': 'runtime_zip'
    }

# Convenience functions for commonly used paths
def get_runtime_dir() -> str:
    return Config.get('RUNTIME_DIR')

def get_runtime_zip_dir() -> str:
    return Config.get('RUNTIME_ZIP_DIR')

def get_velociraptor_path() -> str:
    return Config.get('VELO_BINARY_PATH')

def get_server_config() -> str:
    return Config.get('VELO_SERVER_CONFIG')

def get_winrm_credentials() -> dict:
    """Get WinRM credentials as a dictionary"""
    return {
        'host': os.getenv('WINRM_HOST', ''),  # Use the environment variable set by web interface
        'username': Config.get('WINRM_USERNAME'),
        'password': Config.get('WINRM_PASSWORD'),
        'ssh_port': int(Config.get('SSH_PORT', '22'))
    }

# Initialize paths
def init_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        Config.get('RUNTIME_DIR'),
        Config.get('RUNTIME_ZIP_DIR'),
        Config.get('ARTIFACT_SPECS_DIR'),
        Config.get('ARTIFACT_COLLECTORS_DIR')
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}") 