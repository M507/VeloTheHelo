import os
import shutil
import zipfile
from pathlib import Path
import re
import json
from urllib.parse import unquote
from typing import Tuple, Optional, Dict, Any, List

def create_directory(directory: Path) -> None:
    """Create directory if it doesn't exist."""
    directory.mkdir(exist_ok=True)

def cleanup_extracted_folders(directory: Path) -> None:
    """Remove all folders in the specified directory while preserving files."""
    if directory.exists():
        print(f"Cleaning up folders in {directory} directory...")
        for item in directory.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
        print("Cleanup complete.")

def extract_filename_info(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract FQDN and timestamp from filename.
    Returns tuple of (fqdn, timestamp) or (None, None) if pattern doesn't match."""
    match = re.match(r'Collection--(.+)--(.+)\.zip', filename)
    if match:
        return match.groups()
    print(f"Could not extract FQDN and timestamp from filename: {filename}")
    print("Expected format: Collection--%FQDN%--%TIMESTAMP%.zip")
    return None, None

def copy_zip_file(source: Path, dest_dir: Path) -> Path:
    """Copy zip file to destination directory and return destination path."""
    dest_path = dest_dir / source.name
    shutil.copy2(source, dest_path)
    return dest_path

def extract_zip_file(zip_path: Path, extract_dir: Path) -> bool:
    """Extract zip file to specified directory.
    Returns True if successful, False otherwise."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"Successfully extracted to: {extract_dir}")
        return True
    except Exception as e:
        print(f"Error extracting {zip_path.name}: {str(e)}")
        return False

def rename_files_in_directory(directory: Path) -> None:
    """
    Recursively rename all files in directory, replacing '%2F' with '.'
    """
    print("Renaming files to replace '%2F' with '.'...")
    for root, dirs, files in os.walk(directory):
        root_path = Path(root)
        
        # Rename files
        for file in files:
            if '%2F' in file:
                old_path = root_path / file
                new_name = file.replace('%2F', '.')
                new_path = root_path / new_name
                try:
                    old_path.rename(new_path)
                    print(f"Renamed: {file} -> {new_name}")
                except Exception as e:
                    print(f"Error renaming {file}: {str(e)}")
        
        # Rename directories
        for dir_name in dirs:
            if '%2F' in dir_name:
                old_dir_path = root_path / dir_name
                new_dir_name = dir_name.replace('%2F', '.')
                new_dir_path = root_path / new_dir_name
                try:
                    old_dir_path.rename(new_dir_path)
                    print(f"Renamed directory: {dir_name} -> {new_dir_name}")
                except Exception as e:
                    print(f"Error renaming directory {dir_name}: {str(e)}")

def read_basic_info(extract_dir: Path) -> Optional[dict]:
    """Read and parse the BasicInformation.json file."""
    json_path = extract_dir / 'results' / 'Generic.Client.Info.BasicInformation.json'
    if not json_path.exists():
        print(f"BasicInformation.json not found at expected path: {json_path}")
        return None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as je:
        print(f"Error parsing JSON file: {str(je)}")
    except Exception as e:
        print(f"Error reading BasicInformation.json: {str(e)}")
    return None

def collect_system_info(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract specific system information from a JSON file.
    """
    keys_to_extract = {
        'Hostname': None,
        'OS': None,
        'Platform': None,
        'PlatformVersion': None,
        'Fqdn': None,
        'MACAddresses': None
    }
    
    def search_dict(d: Dict[str, Any], target_keys: Dict[str, Any]) -> None:
        for key, value in d.items():
            if key in target_keys and target_keys[key] is None:
                target_keys[key] = value
            elif isinstance(value, dict):
                search_dict(value, target_keys)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        search_dict(item, target_keys)
    
    search_dict(json_data, keys_to_extract)
    return {k: v for k, v in keys_to_extract.items() if v is not None}

def read_all_json_files(directory: Path) -> Dict[str, Any]:
    """
    Read all JSON files in the directory and collect system information.
    """
    system_info = {}
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.json'):
                file_path = Path(root) / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        info = collect_system_info(json_data)
                        if info:
                            print(f"Found system information in: {file}")
                            system_info.update(info)
                except Exception as e:
                    print(f"Error reading {file}: {str(e)}")
    
    return system_info

def display_basic_info(json_data: dict, system_info: Dict[str, Any] = None) -> None:
    """Display the basic information and system information in a formatted way."""
    print("\n=== Basic Information ===")
    for key, value in json_data.items():
        # Handle nested dictionaries
        if isinstance(value, dict):
            print(f"\n{key}:")
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value}")
        # Handle lists
        elif isinstance(value, list):
            print(f"\n{key}:")
            for item in value:
                if isinstance(item, dict):
                    for sub_key, sub_value in item.items():
                        print(f"  {sub_key}: {sub_value}")
                else:
                    print(f"  - {item}")
        # Handle simple values
        else:
            print(f"{key}: {value}")
    
    if system_info:
        print("\n=== System Information ===")
        for key, value in system_info.items():
            if isinstance(value, list):
                print(f"\n{key}:")
                for item in value:
                    print(f"  - {item}")
            else:
                print(f"{key}: {value}")
    
    print("=====================\n")

def extract_system_info(basic_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract system information from BasicInformation.json
    """
    keys_to_extract = ['Hostname', 'OS', 'Platform', 'PlatformVersion', 'Fqdn', 'MACAddresses']
    system_info = {}
    
    def search_dict(d: Dict[str, Any], target_keys: List[str]) -> None:
        for key, value in d.items():
            if key in target_keys:
                system_info[key] = value
            elif isinstance(value, dict):
                search_dict(value, target_keys)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        search_dict(item, target_keys)
    
    search_dict(basic_info, keys_to_extract)
    return system_info

def update_json_files(extract_dir: Path, system_info: Dict[str, Any]) -> None:
    """
    Update all JSON files in the results directory with system information.
    Each line in the files is treated as a separate JSON object.
    """
    results_dir = extract_dir / 'results'
    if not results_dir.exists():
        print("Results directory not found")
        return
        
    basic_info_filename = 'Generic.Client.Info.BasicInformation.json'
    
    print("\nUpdating JSON files with system information...")
    for file_path in results_dir.glob('*.json'):
        # Skip the BasicInformation.json file
        if file_path.name == basic_info_filename:
            continue
            
        try:
            # Read all lines from the file
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Process each line and add system info
            updated_lines = []
            for line in lines:
                try:
                    # Parse the JSON object from the line
                    json_obj = json.loads(line)
                    # Add system info to the object
                    json_obj.update(system_info)
                    # Convert back to JSON string
                    updated_lines.append(json.dumps(json_obj))
                except json.JSONDecodeError:
                    # If line is not valid JSON, keep it as is
                    updated_lines.append(line)
            
            # Write the updated lines back to the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated_lines) + '\n')
            
            print(f"Updated: {file_path.name}")
            
        except Exception as e:
            print(f"Error updating {file_path.name}: {str(e)}")

def setup_extraction_directory(zip_path: Path, runtime_zip_dir: Path) -> Tuple[Path, Path]:
    """
    Set up the directory for zip extraction.
    Returns tuple of (destination zip path, extraction directory path)
    """
    dest_path = copy_zip_file(zip_path, runtime_zip_dir)
    extract_dir = runtime_zip_dir / zip_path.stem
    create_directory(extract_dir)
    return dest_path, extract_dir

def process_file_info(zip_path: Path) -> None:
    """
    Process and display the file information (FQDN and timestamp).
    """
    fqdn, timestamp = extract_filename_info(zip_path.name)
    if fqdn and timestamp:
        print(f"FQDN: {fqdn}")
        print(f"Timestamp: {timestamp}")

def process_basic_information(extract_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Process the basic information file and return system info if found.
    """
    basic_info = read_basic_info(extract_dir)
    if not basic_info:
        print("No basic information found")
        return None
    
    system_info = extract_system_info(basic_info)
    if not system_info:
        print("No system information found in BasicInformation.json")
        return None
    
    return system_info

def update_json_with_system_info(extract_dir: Path, system_info: Dict[str, Any]) -> None:
    """
    Update all JSON files with system information and display basic info.
    """
    update_json_files(extract_dir, system_info)

def process_single_zip(zip_path: Path, runtime_zip_dir: Path) -> None:
    """
    Process a single zip file through the following steps:
    1. Display file information
    2. Set up extraction directory
    3. Extract zip file
    4. Rename files
    5. Process basic information
    6. Update JSON files with system info
    """
    print(f"\nProcessing: {zip_path.name}")
    
    # Step 1: Process file information
    process_file_info(zip_path)
    
    # Step 2: Set up extraction directory
    dest_path, extract_dir = setup_extraction_directory(zip_path, runtime_zip_dir)
    
    # Step 3: Extract zip file
    if not extract_zip_file(dest_path, extract_dir):
        print(f"Failed to extract {zip_path.name}")
        return
    
    # Step 4: Rename files
    rename_files_in_directory(extract_dir)
    
    # Step 5: Process basic information
    system_info = process_basic_information(extract_dir)
    if not system_info:
        return
    
    # Step 6: Update JSON files with system info
    update_json_with_system_info(extract_dir, system_info)

def process_zip_files():
    """Main function to process all zip files."""
    # Setup directories
    runtime_zip_dir = Path('runtime_zip')
    runtime_dir = Path('runtime')
    
    # Create and clean directories
    create_directory(runtime_zip_dir)
    cleanup_extracted_folders(runtime_zip_dir)
    
    # Check source directory
    if not runtime_dir.exists():
        print(f"Error: Source directory '{runtime_dir}' does not exist!")
        return
    
    # Get and process zip files
    zip_files = list(runtime_dir.glob('*.zip'))
    if not zip_files:
        print("No zip files found in runtime directory!")
        return
    
    # Process each zip file
    for zip_path in zip_files:
        process_single_zip(zip_path, runtime_zip_dir)

if __name__ == "__main__":
    process_zip_files() 