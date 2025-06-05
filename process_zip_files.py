import os
import shutil
import zipfile
from pathlib import Path
import re
import json
from urllib.parse import unquote
from typing import Tuple, Optional, Dict, Any, List, Set
from datetime import datetime
import pytz

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

def get_source_type(filename: str) -> str:
    """
    Extract the source type from the filename.
    Example: 'Generic.Client.Info.Users.json' -> 'Users'
    """
    # Remove .json extension and split by dots
    parts = filename.replace('.json', '').split('.')
    # Return the last part as source type
    return parts[-1] if parts else 'Unknown'

def update_json_with_source_type(file_path: Path) -> None:
    """
    Add source_type to each JSON line based on the filename.
    """
    source_type = get_source_type(file_path.name)
    
    try:
        # Read all lines from the file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Process each line and add source_type
        updated_lines = []
        for line in lines:
            try:
                # Parse the JSON object from the line
                json_obj = json.loads(line)
                # Add source_type to the object
                json_obj['source_type'] = source_type
                # Convert back to JSON string
                updated_lines.append(json.dumps(json_obj))
            except json.JSONDecodeError:
                # If line is not valid JSON, keep it as is
                updated_lines.append(line)
        
        # Write the updated lines back to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(updated_lines) + '\n')
        
        print(f"Added source_type '{source_type}' to: {file_path.name}")
        
    except Exception as e:
        print(f"Error updating source_type in {file_path.name}: {str(e)}")

def update_json_with_system_info(extract_dir: Path, system_info: Dict[str, Any]) -> None:
    """
    Update all JSON files with system information and source type.
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
            # First add source_type to each line
            update_json_with_source_type(file_path)
            
            # Then add system info
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
            
            print(f"Updated with system info: {file_path.name}")
            
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

def delete_index_files(directory: Path) -> None:
    """Delete all .index files in the specified directory and its subdirectories."""
    print("\nDeleting .index files...")
    for root, _, files in os.walk(directory):
        root_path = Path(root)
        for file in files:
            if file.endswith('.index'):
                file_path = root_path / file
                try:
                    file_path.unlink()
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {str(e)}")

def convert_iso_to_epoch(timestamp_str: str) -> Optional[int]:
    """Convert ISO format timestamp to epoch (Unix timestamp)."""
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        dt = pytz.utc.localize(dt)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None

def add_epoch_timestamps(file_path: Path, timestamp_keys: List[str]) -> None:
    """
    Add epoch timestamps for specified keys in JSON files.
    The timestamp must be in ISO format: "2025-06-04T20:08:02Z"
    """
    try:
        # Read all lines from the file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Process each line
        updated_lines = []
        for line in lines:
            try:
                # Parse the JSON object from the line
                json_obj = json.loads(line)
                
                # Process each timestamp key
                for key in timestamp_keys:
                    if key in json_obj and isinstance(json_obj[key], str):
                        epoch_time = convert_iso_to_epoch(json_obj[key])
                        if epoch_time is not None:
                            json_obj[f"{key}_epoch"] = epoch_time
                
                # Convert back to JSON string
                updated_lines.append(json.dumps(json_obj))
            except json.JSONDecodeError:
                # If line is not valid JSON, keep it as is
                updated_lines.append(line)
        
        # Write the updated lines back to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(updated_lines) + '\n')
        
        print(f"Added epoch timestamps in: {file_path.name}")
        
    except Exception as e:
        print(f"Error adding epoch timestamps in {file_path.name}: {str(e)}")

def detect_and_convert_timestamps(file_path: Path, possible_time_keys: List[str]) -> None:
    """
    Automatically detect and convert timestamp values based on key names.
    Looks for keys containing words from possible_time_keys list and attempts to convert their values to epoch.
    """
    try:
        # Read all lines from the file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Process each line
        updated_lines = []
        conversions_made = False
        
        for line in lines:
            try:
                # Parse the JSON object from the line
                json_obj = json.loads(line)
                
                # Process each key in the JSON object
                for key in list(json_obj.keys()):  # Create a list to avoid modification during iteration
                    # Check if key contains any of the possible time indicators
                    if any(time_indicator.lower() in key.lower() for time_indicator in possible_time_keys):
                        # Skip if we already created an epoch version for this key
                        if f"{key}_epoch" in json_obj:
                            continue
                            
                        # Try to convert if the value is a string
                        if isinstance(json_obj[key], str):
                            epoch_time = convert_iso_to_epoch(json_obj[key])
                            if epoch_time is not None:
                                json_obj[f"{key}_epoch"] = epoch_time
                                conversions_made = True
                
                # Convert back to JSON string
                updated_lines.append(json.dumps(json_obj))
            except json.JSONDecodeError:
                # If line is not valid JSON, keep it as is
                updated_lines.append(line)
        
        # Write the updated lines back to the file only if changes were made
        if conversions_made:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated_lines) + '\n')
            print(f"Auto-detected and converted timestamps in: {file_path.name}")
        
    except Exception as e:
        print(f"Error auto-detecting timestamps in {file_path.name}: {str(e)}")

def process_single_zip(zip_path: Path, runtime_zip_dir: Path) -> None:
    """
    Process a single zip file through the following steps:
    1. Display file information
    2. Set up extraction directory
    3. Extract zip file
    4. Rename files
    5. Process basic information
    6. Update JSON files with system info
    7. Add epoch timestamps for known keys
    8. Auto-detect and convert additional timestamps
    9. Delete .index files
    """
    # List of timestamp keys to convert to epoch
    # Add new keys here to convert more timestamps
    timestamp_keys = [
        "visit_time",
        "KeyLastWriteTimestamp",
        "LastUpdated",
        "KeyMTime"
    ]
    
    # List of words that might indicate a timestamp field
    # Add new indicators here to detect more timestamp fields
    possible_time_keys = [
        "time",
        "date",
        "timestamp",
        "modified",
        "created",
        "accessed",
        "updated",
        "last",
        "mtime",
        "ctime",
        "atime"
    ]
    
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
    
    # Process JSON files in results directory
    results_dir = extract_dir / 'results'
    if results_dir.exists():
        # Step 7: Add epoch timestamps for known keys
        print("\nAdding epoch timestamps for known keys...")
        for file_path in results_dir.glob('*.json'):
            if file_path.name != 'Generic.Client.Info.BasicInformation.json':
                add_epoch_timestamps(file_path, timestamp_keys)
        
        # Step 8: Auto-detect and convert additional timestamps
        print("\nAuto-detecting and converting additional timestamps...")
        for file_path in results_dir.glob('*.json'):
            if file_path.name != 'Generic.Client.Info.BasicInformation.json':
                detect_and_convert_timestamps(file_path, possible_time_keys)
    
    # Step 9: Delete .index files
    delete_index_files(extract_dir)

def check_process_single_zip(zip_path: Path, runtime_zip_dir: Path) -> None:
    """
    Validate that all JSON files in the extracted directory have the required keys.
    Only prints issues found during validation.
    """
    print(f"\nValidating processed files for: {zip_path.name}")
    
    # Define required keys that should be present in each JSON line
    required_keys = {
        'source_type',
        'Hostname',
        'OS',
        'Platform',
        'PlatformVersion',
        'Fqdn',
        'MACAddresses'
    }
    
    extract_dir = runtime_zip_dir / zip_path.stem
    results_dir = extract_dir / 'results'
    
    if not results_dir.exists():
        print(f"Error: Results directory not found for {zip_path.name}")
        return
    
    basic_info_filename = 'Generic.Client.Info.BasicInformation.json'
    issues_found = False
    
    # Process each JSON file
    for file_path in results_dir.glob('*.json'):
        # Skip the BasicInformation.json file
        if file_path.name == basic_info_filename:
            continue
            
        try:
            # Read the file line by line
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Check each line
            for line_number, line in enumerate(lines, 1):
                try:
                    json_obj = json.loads(line)
                    
                    # Verify source_type matches filename
                    expected_source_type = get_source_type(file_path.name)
                    actual_source_type = json_obj.get('source_type')
                    if actual_source_type != expected_source_type:
                        issues_found = True
                        print(f"Issue in {file_path.name}, line {line_number}:")
                        print(f"  - Incorrect source_type: expected '{expected_source_type}', got '{actual_source_type}'")
                    
                    # Check for missing required keys
                    missing_keys = required_keys - set(json_obj.keys())
                    if missing_keys:
                        issues_found = True
                        print(f"Issue in {file_path.name}, line {line_number}:")
                        print(f"  - Missing required keys: {', '.join(sorted(missing_keys))}")
                    
                    # Check for empty or None values in required keys
                    empty_keys = {
                        key for key in required_keys - missing_keys
                        if json_obj.get(key) is None or json_obj.get(key) == ''
                    }
                    if empty_keys:
                        issues_found = True
                        print(f"Issue in {file_path.name}, line {line_number}:")
                        print(f"  - Empty values for keys: {', '.join(sorted(empty_keys))}")
                    
                except json.JSONDecodeError:
                    issues_found = True
                    print(f"Issue in {file_path.name}, line {line_number}:")
                    print("  - Invalid JSON format")
                    
        except Exception as e:
            issues_found = True
            print(f"Error processing {file_path.name}: {str(e)}")
    
    if not issues_found:
        print(f"Validation successful: No issues found in {zip_path.name}")

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
        # Validate the processing
        check_process_single_zip(zip_path, runtime_zip_dir)

if __name__ == "__main__":
    process_zip_files() 