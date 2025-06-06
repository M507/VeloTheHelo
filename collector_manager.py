import os
import sys
import shutil
import zipfile
import winrm
import paramiko
import hashlib
import warnings
import json
import queue
import threading
import time
import logging
from pathlib import Path
from datetime import datetime
import pytz
from typing import Tuple, Optional, Dict, Any, List, Set
from urllib.parse import unquote
from cryptography.utils import CryptographyDeprecationWarning
from config import Config, init_directories, get_winrm_credentials
from colors import print_success, print_error, print_info, print_warning, SUCCESS_EMOJI, ERROR_EMOJI, logger
import re
import subprocess
from process_zip_files import process_single_zip, check_process_single_zip

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)
warnings.filterwarnings('ignore', message='.*TripleDES.*')

class SpecFileGenerator:
    def __init__(self, template_path: str, artifacts_path: str, output_dir: str):
        print_info(f"\nInitializing SpecFileGenerator")
        print_info(f"Template path: {template_path}")
        print_info(f"Artifacts path: {artifacts_path}")
        print_info(f"Output directory: {output_dir}")
        
        self.template_path = template_path
        self.artifacts_path = artifacts_path
        self.output_dir = output_dir
        self.template_encoding = None

    def try_read_file(self, file_path: str) -> Tuple[Optional[List[str]], Optional[str]]:
        """Try to read a file with different encodings."""
        print_info(f"\nAttempting to read {file_path}")
        
        # First try UTF-16
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                lines = f.readlines()
                print_success(f"Successfully read {len(lines)} lines with UTF-16")
                return lines, 'utf-16'
        except UnicodeError:
            print_info("UTF-16 encoding failed, trying others...")
            pass

        # Then try other encodings
        for encoding in ['utf-8', 'latin1', 'ascii']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                    print_success(f"Successfully read {len(lines)} lines with {encoding}")
                    return lines, encoding
            except UnicodeDecodeError:
                print_info(f"{encoding} encoding failed, trying next...")
                continue
            except Exception as e:
                print_error(f"Error reading file {file_path}: {e}")
        
        print_error(f"Failed to read {file_path} with any encoding")
        return None, None

    def find_section_markers(self, lines: List[str]) -> Tuple[int, int]:
        """Find the start and end markers in the template."""
        print_info("\nFinding section markers in template")
        start = -1
        end = -1
        
        for i, line in enumerate(lines):
            if "The list of artifacts and their args." in line:
                start = i
                print_info(f"Found start marker at line {i}")
            elif "Can be ZIP" in line:
                end = i
                print_info(f"Found end marker at line {i}")
                break
        
        if start == -1 or end == -1:
            print_error("Could not find both section markers")
        else:
            print_success(f"Found section markers: Start={start}, End={end}")
        
        return start, end

    def create_spec_file(self, artifact: str) -> Optional[str]:
        """Create a spec file for a single artifact."""
        print_info(f"\nCreating spec file for artifact: {artifact}")
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                print_success(f"Created output directory: {self.output_dir}")

            # Read template file
            print_info(f"Reading template file: {self.template_path}")
            template_lines, self.template_encoding = self.try_read_file(self.template_path)
            if not template_lines:
                print_error("Failed to read template file")
                return None

            # Find section markers
            print_info("Looking for section markers")
            start, end = self.find_section_markers(template_lines)
            if start == -1 or end == -1:
                print_error("Could not find section markers in template")
                return None

            # Split template into header and footer
            print_info("Splitting template into sections")
            header_lines = template_lines[:start + 2]  # Include the marker and "Artifacts:" line
            footer_lines = template_lines[end:]

            # Create the new content
            print_info("Creating new content")
            new_content = header_lines.copy()
            new_content.append(f" {artifact}:\n")
            new_content.append("    All: Y\n")
            new_content.append(" Generic.Client.Info:\n")
            new_content.append("    All: Y\n")
            new_content.extend(footer_lines)
            
            # Create a more descriptive filename
            clean_artifact_name = artifact.replace('.', '_')
            spec_filename = f"single_artifact_spec_{clean_artifact_name}.yaml"
            spec_path = os.path.join(self.output_dir, spec_filename)
            
            print_info(f"Writing spec file: {spec_path}")
            print_info(f"Content length: {len(new_content)} lines")
            
            with open(spec_path, 'w', newline='', encoding=self.template_encoding or 'utf-8') as spec_file:
                spec_file.writelines(new_content)
            
            print_success(f"Successfully created spec file for {artifact}")
            return spec_path
            
        except Exception as e:
            print_error(f"Error creating spec file for {artifact}: {e}")
            return None

    def create_combined_spec_file(self, artifacts: List[str], spec_name: str = "combined_artifacts") -> Optional[str]:
        """Create a spec file that includes multiple artifacts."""
        print_info(f"\nCreating combined spec file for artifacts: {', '.join(artifacts)}")
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                print_success(f"Created output directory: {self.output_dir}")

            # Read template file
            print_info(f"Reading template file: {self.template_path}")
            template_lines, self.template_encoding = self.try_read_file(self.template_path)
            if not template_lines:
                print_error("Failed to read template file")
                return None

            # Find section markers
            print_info("Looking for section markers")
            start, end = self.find_section_markers(template_lines)
            if start == -1 or end == -1:
                print_error("Could not find section markers in template")
                return None

            # Split template into header and footer
            print_info("Splitting template into sections")
            header_lines = template_lines[:start + 2]  # Include the marker and "Artifacts:" line
            footer_lines = template_lines[end:]

            # Create the new content
            print_info("Creating new content with multiple artifacts")
            new_content = header_lines.copy()
            
            # Add each artifact to the spec
            for artifact in artifacts:
                new_content.append(f" {artifact}:\n")
                new_content.append("    All: Y\n")
            
            # Add Generic.Client.Info
            new_content.append(" Generic.Client.Info:\n")
            new_content.append("    All: Y\n")
            new_content.extend(footer_lines)
            
            # Create a descriptive filename
            spec_filename = f"{spec_name}.yaml"
            spec_path = os.path.join(self.output_dir, spec_filename)
            
            print_info(f"Writing combined spec file: {spec_path}")
            print_info(f"Content length: {len(new_content)} lines")
            
            with open(spec_path, 'w', newline='', encoding=self.template_encoding or 'utf-8') as spec_file:
                spec_file.writelines(new_content)
            
            print_success(f"Successfully created combined spec file with {len(artifacts)} artifacts")
            return spec_path
            
        except Exception as e:
            print_error(f"Error creating combined spec file: {e}")
            return None

class CollectorManager:
    def __init__(self, mode='batch'):
        """Initialize the CollectorManager with specified mode"""
        print_info(f"\nInitializing CollectorManager in {mode} mode")
        logger.info(f"Initializing CollectorManager in {mode} mode")
        self.mode = mode
        self.progress_queue = queue.Queue()
        self.status = {
            'processing': False,
            'total_artifacts': 0,
            'processed': 0,
            'current_artifact': '',
            'messages': [],
            'completed': False,
            'task_start_time': None,
            'artifact_stats': {
                'successful': [],
                'failed': []
            }
        }
        self.winrm_session = None
        self.credentials = None
        print_success("CollectorManager initialized successfully")
        logger.debug("CollectorManager initialized with empty status")

    @staticmethod
    def clean_all_directories(directories: Optional[List[str]] = None) -> bool:
        """Clean specified directories or all working directories if none specified"""
        print_info("\nStarting directory cleanup...")
        logger.info("Starting directory cleanup")
        try:
            if directories is None:
                directories = [
                    Config.get('ARTIFACT_SPECS_DIR'),
                    'collectors',
                    'runtime_zip',
                    'runtime'
                ]
            
            for directory in directories:
                try:
                    print_info(f"Processing directory: {directory}")
                    logger.debug(f"Cleaning directory: {directory}")
                    if os.path.exists(directory):
                        shutil.rmtree(directory)
                        print_success(f"Removed existing directory: {directory}")
                        logger.debug(f"Removed existing directory: {directory}")
                    os.makedirs(directory)
                    print_success(f"Created fresh directory: {directory}")
                    logger.debug(f"Created fresh directory: {directory}")
                except Exception as e:
                    print_error(f"Failed to clean directory {directory}: {str(e)}")
                    logger.error(f"Failed to clean directory {directory}: {str(e)}")
                    return False
            print_success("All directories cleaned successfully")
            return True
        except Exception as e:
            print_error(f"Directory cleanup failed: {str(e)}")
            logger.error(f"Directory cleanup failed: {str(e)}")
            return False

    def initialize_connections(self) -> bool:
        """Initialize WinRM and SSH connections"""
        logger.info("Initializing connections")
        try:
            self.credentials = get_winrm_credentials()
            self.credentials['local_file'] = Config.get('COLLECTOR_FILE')
            
            logger.debug(f"Using host: {self.credentials['host']}")
            logger.debug(f"Using username: {self.credentials['username']}")
            logger.debug(f"Local file: {self.credentials['local_file']}")
            
            required_vars = ['host', 'username', 'password']
            missing_vars = [var for var in required_vars if not self.credentials[var]]
            
            if missing_vars:
                logger.error(f"Missing required credentials: {', '.join(missing_vars)}")
                self.update_status(f"Missing required credentials: {', '.join(missing_vars)}", True)
                return False
            
            self.winrm_session = self.create_winrm_session(self.credentials)
            logger.info("Successfully initialized connections")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize connections: {str(e)}")
            self.update_status(f"Failed to initialize connections: {str(e)}", True)
            return False

    def create_artifact_spec(self, artifact_name: str) -> Optional[str]:
        """Create spec file for a single artifact"""
        logger.info(f"Creating spec for artifact: {artifact_name}")
        try:
            self.update_status(f"Creating spec for {artifact_name}")
            
            spec_generator = SpecFileGenerator(
                Config.get('ARTIFACT_TEMPLATE_PATH'),
                Config.get('ARTIFACT_LIST_FILE'),
                Config.get('ARTIFACT_SPECS_DIR')
            )
            
            logger.debug(f"Template path: {Config.get('ARTIFACT_TEMPLATE_PATH')}")
            logger.debug(f"Artifact list: {Config.get('ARTIFACT_LIST_FILE')}")
            logger.debug(f"Specs directory: {Config.get('ARTIFACT_SPECS_DIR')}")
            
            spec_path = spec_generator.create_spec_file(artifact_name)
            if spec_path:
                logger.info(f"Successfully created spec file at: {spec_path}")
                self.update_status(f"Created spec file for {artifact_name}")
                return spec_path
            else:
                logger.error(f"Failed to create spec for {artifact_name}")
                self.update_status(f"Failed to create spec for {artifact_name}", True)
                return None
        except Exception as e:
            logger.error(f"Error creating spec: {str(e)}")
            self.update_status(f"Error creating spec: {str(e)}", True)
            return None

    def build_collector_exe(self, artifact_name: str, spec_path: str) -> Optional[str]:
        """Build collector executable from spec file"""
        print_info(f"\nStarting collector build for {artifact_name}")
        logger.info(f"Starting collector build for {artifact_name}")
        try:
            self.update_status(f"Building collector for {artifact_name}")
            
            # Log all config values
            print_info("\nConfiguration values:")
            print_info(f"VELO_BINARY_PATH: {Config.get('VELO_BINARY_PATH')}")
            print_info(f"VELO_SERVER_CONFIG: {Config.get('VELO_SERVER_CONFIG')}")
            print_info(f"VELO_DATASTORE: {Config.get('VELO_DATASTORE')}")
            print_info(f"ARTIFACT_COLLECTORS_DIR: {Config.get('ARTIFACT_COLLECTORS_DIR')}")
            
            logger.debug("Config values:")
            logger.debug(f"VELO_BINARY_PATH: {Config.get('VELO_BINARY_PATH')}")
            logger.debug(f"VELO_SERVER_CONFIG: {Config.get('VELO_SERVER_CONFIG')}")
            logger.debug(f"VELO_DATASTORE: {Config.get('VELO_DATASTORE')}")
            logger.debug(f"ARTIFACT_COLLECTORS_DIR: {Config.get('ARTIFACT_COLLECTORS_DIR')}")
            
            # Ensure spec file exists
            if not os.path.exists(spec_path):
                print_error(f"Spec file not found: {spec_path}")
                logger.error(f"Spec file not found: {spec_path}")
                self.update_status(f"Spec file not found at: {spec_path}", True)
                return None

            # Create collectors directory if it doesn't exist
            collectors_dir = Config.get('ARTIFACT_COLLECTORS_DIR')
            print_info(f"Creating collectors directory: {collectors_dir}")
            logger.debug(f"Creating collectors directory: {collectors_dir}")
            os.makedirs(collectors_dir, exist_ok=True)
            
            # Define source and target collector paths
            source_collector = os.path.join(
                Config.get('VELO_DATASTORE'),
                "Collector_velociraptor-v0.72.4-windows-amd64.exe"
            )
            
            # Create a safe filename by replacing spaces and special characters
            safe_name = artifact_name.replace(" ", "_").replace(".", "_")
            target_collector = os.path.join(
                collectors_dir,
                f"collector_{safe_name}.exe"
            )
            
            print_info(f"Source collector path: {source_collector}")
            print_info(f"Target collector path: {target_collector}")
            logger.debug(f"Source collector path: {source_collector}")
            logger.debug(f"Target collector path: {target_collector}")
            
            # Build the command with full paths
            velo_binary = Config.get('VELO_BINARY_PATH')
            velo_config = Config.get('VELO_SERVER_CONFIG')
            velo_datastore = Config.get('VELO_DATASTORE')
            
            if not os.path.exists(velo_binary):
                print_error(f"Velociraptor binary not found: {velo_binary}")
                logger.error(f"Velociraptor binary not found: {velo_binary}")
                self.update_status(f"Velociraptor binary not found at: {velo_binary}", True)
                return None
                
            if not os.path.exists(velo_config):
                print_error(f"Velociraptor config not found: {velo_config}")
                logger.error(f"Velociraptor config not found: {velo_config}")
                self.update_status(f"Velociraptor config not found at: {velo_config}", True)
                return None

            # Construct command as a list for subprocess
            cmd = [velo_binary, "--config", velo_config, "collector"]
            if velo_datastore:
                cmd.extend(["--datastore", velo_datastore])
            cmd.append(spec_path)
            
            print_info(f"\nExecuting build command:\n{' '.join(cmd)}")
            logger.info(f"Build command: {' '.join(cmd)}")
            self.update_status(f"Running build command: {' '.join(cmd)}")
            
            # Execute the command using subprocess.run
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False  # Don't raise exception on non-zero exit
                )
                print_info(f"Build command result code: {result.returncode}")
                logger.debug(f"Build command result: {result.returncode}")
                
                if result.stderr:
                    print_error(f"Command stderr: {result.stderr}")
                    logger.error(f"Command stderr: {result.stderr}")
                
                if result.stdout:
                    print_info(f"Command stdout: {result.stdout}")
                    logger.info(f"Command stdout: {result.stdout}")
                
                if result.returncode == 0:
                    if os.path.exists(source_collector):
                        # Move the collector from datastore to collectors directory
                        try:
                            shutil.copy2(source_collector, target_collector)
                            file_size = os.path.getsize(target_collector)
                            success_msg = f"Successfully copied collector to {target_collector} (Size: {file_size/1024:.2f} KB)"
                            print_success(success_msg)
                            logger.info(success_msg)
                            self.update_status(success_msg)
                            return target_collector
                        except Exception as e:
                            error_msg = f"Failed to copy collector from {source_collector} to {target_collector}: {str(e)}"
                            print_error(error_msg)
                            logger.error(error_msg)
                            self.update_status(error_msg, True)
                            return None
                    else:
                        error_msg = f"Build command succeeded but collector not found at: {source_collector}"
                        print_error(error_msg)
                        logger.error(error_msg)
                        self.update_status(error_msg, True)
                        return None
                else:
                    error_msg = f"Failed to build collector. Command exit code: {result.returncode}"
                    if result.stderr:
                        error_msg += f"\nError: {result.stderr}"
                    print_error(error_msg)
                    logger.error(error_msg)
                    self.update_status(error_msg, True)
                    return None
            except Exception as e:
                error_msg = f"Failed to execute build command: {str(e)}"
                print_error(error_msg)
                logger.error(error_msg)
                self.update_status(error_msg, True)
                return None
            
        except Exception as e:
            print_error(f"Collector build failed: {str(e)}")
            logger.error(f"Collector build failed: {str(e)}")
            self.update_status(f"Error building collector: {str(e)}", True)
            return None

    def push_and_execute_collector(self, local_path: str, artifact_name: str) -> bool:
        """Push collector to remote system and execute it"""
        try:
            logger.info(f"Starting push and execute operation for artifact: {artifact_name}")
            logger.debug(f"Local collector path: {local_path}")
            
            if not os.path.exists(local_path):
                error_msg = f"Collector file not found at: {local_path}"
                logger.error(error_msg)
                self.update_status(error_msg, True)
                return False

            remote_file = f"C:\\Windows\\Temp\\Collector_{artifact_name}.exe"
            log_file = f"C:\\Windows\\Temp\\Collector_{artifact_name}.log"
            
            logger.debug(f"Remote collector path: {remote_file}")
            logger.debug(f"Remote log file path: {log_file}")
            
            self.update_status(f"Pushing collector to {remote_file}")
            logger.info(f"Copying collector to remote system: {remote_file}")
            if not self.copy_and_verify_file(self.winrm_session, self.credentials, local_path, remote_file):
                error_msg = "Failed to copy collector to remote system"
                logger.error(error_msg)
                self.update_status(error_msg, True)
                return False
            logger.info("Successfully copied collector to remote system")
            
            self.update_status("Executing collector")
            logger.info("Starting collector execution")
            ps_command = f"""
            $ErrorActionPreference = 'Stop'
            try {{
                Set-Location (Split-Path -Parent '{remote_file}')
                $output = & '{remote_file}' 2>&1
                $output | Out-File -FilePath '{log_file}' -Encoding UTF8
                if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {{
                    throw "Process exited with code $LASTEXITCODE"
                }}
                "Success"
            }} catch {{
                Write-Error "Failed to execute: $_"
                throw
            }}
            """
            
            logger.debug("Executing PowerShell command for collector")
            result = self.execute_command(self.winrm_session, ps_command)
            if result['status_code'] == 0 and "Success" in result['stdout']:
                logger.info("Collector execution completed successfully")
                self.update_status("Execution completed")
                
                logger.debug("Waiting for file operations to complete")
                self.winrm_session.run_ps("Start-Sleep -Seconds 2")
                
                logger.debug(f"Checking for log file: {log_file}")
                check_file = self.winrm_session.run_ps(f"Test-Path '{log_file}'")
                if check_file.std_out.decode('utf-8').strip().lower() != 'true':
                    error_msg = f"File {log_file} not found after execution"
                    logger.error(error_msg)
                    self.update_status(error_msg, True)
                    return False
                logger.info("Log file found on remote system")
                
                self.update_status(f"Pulling log file {log_file}...")
                logger.info("Starting log file retrieval")
                if not self.clean_runtime_directory():
                    logger.error("Failed to clean runtime directory")
                    return False
                
                logger.debug("Creating SSH client for file transfer")
                ssh = self.create_ssh_client(self.credentials)
                if not ssh:
                    logger.error("Failed to create SSH client")
                    return False
                
                try:
                    sftp = ssh.open_sftp()
                    local_filename = os.path.basename(log_file)
                    local_path = os.path.join("./runtime", local_filename)
                    logger.debug(f"Pulling log file to: {local_path}")
                    sftp.get(log_file, local_path)
                    logger.info(f"Successfully pulled log file to: {local_path}")
                    self.update_status(f"Log file pulled successfully to {local_path}")
                    
                    self.update_status("Verifying execution output...")
                    logger.info("Starting execution output verification")
                    if self.check_execution_output(local_path):
                        success_msg = "Execution verification completed successfully"
                        logger.info(success_msg)
                        self.update_status(success_msg)
                        return True
                    logger.error("Execution verification failed")
                    return False
                finally:
                    logger.debug("Closing SFTP and SSH connections")
                    sftp.close()
                    ssh.close()
            else:
                error_msg = result['stderr'] if result['stderr'] else result['stdout']
                logger.error(f"Execution failed: {error_msg}")
                self.update_status(f"Execution failed: {error_msg}", True)
                return False
        except Exception as e:
            error_msg = f"Failed to execute file or pull results: {str(e)}"
            logger.error(error_msg, exc_info=True)  # Include full exception traceback
            self.update_status(error_msg, True)
            return False

    def pull_collection_data(self) -> bool:
        """Pull all collection data from remote system"""
        try:
            print_info("\nPulling collection data")
            
            # Clean runtime directory before pulling files
            if not self.clean_runtime_directory():
                return False
            
            # Pull all collection zip files
            print_info("\nPulling Collection zip files...")
            collection_pattern = "C:\\Windows\\Temp\\Collection-*.zip"
            if not self.pull_files_by_pattern(collection_pattern):
                print_error("Failed to pull collection zip files")
                return False
            
            return True
            
        except Exception as e:
            print_error(f"Error pulling collection data: {str(e)}")
            return False

    def check_process_single_zip(self, zip_path: Path, runtime_zip_dir: Optional[Path] = None) -> bool:
        """
        Validate processed files for required keys and proper formatting
        Args:
            zip_path: Path to the zip file to process
            runtime_zip_dir: Optional directory where files are extracted. If not provided, uses default runtime_zip
        Returns:
            bool: True if validation passed, False otherwise
        """
        print_info(f"\nValidating processed files for: {zip_path.name}")
        
        # Define required keys
        required_keys = {
            'source_type',
            'Hostname',
            'OS',
            'Platform',
            'PlatformVersion',
            'Fqdn',
            'MACAddresses'
        }
        
        # Use provided runtime_zip_dir or default
        if runtime_zip_dir is None:
            runtime_zip_dir = Path('runtime_zip')
            runtime_zip_dir.mkdir(exist_ok=True)
        
        extract_dir = runtime_zip_dir / zip_path.stem
        results_dir = extract_dir / 'results'
        
        if not results_dir.exists():
            print_error(f"Results directory not found for {zip_path.name}")
            return False
        
        basic_info_filename = 'Generic.Client.Info.BasicInformation.json'
        issues_found = False
        
        # Process each JSON file
        for file_path in results_dir.glob('*.json'):
            if file_path.name == basic_info_filename:
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                
                for line_number, line in enumerate(lines, 1):
                    try:
                        json_obj = json.loads(line)
                        
                        # Verify source_type matches filename
                        expected_source_type = self.get_source_type(file_path.name)
                        actual_source_type = json_obj.get('source_type')
                        if actual_source_type != expected_source_type:
                            issues_found = True
                            print_error(f"Issue in {file_path.name}, line {line_number}:")
                            print_error(f"  - Incorrect source_type: expected '{expected_source_type}', got '{actual_source_type}'")
                        
                        # Check for missing required keys
                        missing_keys = required_keys - set(json_obj.keys())
                        if missing_keys:
                            issues_found = True
                            print_error(f"Issue in {file_path.name}, line {line_number}:")
                            print_error(f"  - Missing required keys: {', '.join(sorted(missing_keys))}")
                        
                        # Check for empty values
                        empty_keys = {
                            key for key in required_keys - missing_keys
                            if json_obj.get(key) is None or json_obj.get(key) == ''
                        }
                        if empty_keys:
                            issues_found = True
                            print_error(f"Issue in {file_path.name}, line {line_number}:")
                            print_error(f"  - Empty values for keys: {', '.join(sorted(empty_keys))}")
                        
                    except json.JSONDecodeError:
                        issues_found = True
                        print_error(f"Issue in {file_path.name}, line {line_number}:")
                        print_error("  - Invalid JSON format")
                        
            except Exception as e:
                issues_found = True
                print_error(f"Error processing {file_path.name}: {str(e)}")
        
        if not issues_found:
            print_success(f"Validation successful: No issues found in {zip_path.name}")
        
        return not issues_found

    def extract_filename_info(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract FQDN and timestamp from filename"""
        match = re.match(r'Collection--(.+)--(.+)\.zip', filename)
        if match:
            return match.groups()
        print_error(f"Could not extract FQDN and timestamp from filename: {filename}")
        return None, None

    def rename_files_in_directory(self, directory: Path) -> None:
        """Rename files and directories replacing '%2F' with '.'"""
        print_info(f"Renaming files in {directory}")
        
        # First rename all files (collect paths first to avoid modification during iteration)
        files_to_rename = []
        for item in directory.rglob('*'):
            if item.is_file() and '%2F' in item.name:
                files_to_rename.append(item)
        
        # Rename the files
        for old_path in files_to_rename:
            try:
                new_name = old_path.name.replace('%2F', '.')
                new_path = old_path.parent / new_name
                if new_path.exists():
                    print_warning(f"Skipping {old_path.name} - {new_name} already exists")
                    continue
                old_path.rename(new_path)
                print_info(f"Renamed file: {old_path.name} -> {new_name}")
            except Exception as e:
                print_error(f"Error renaming {old_path.name}: {str(e)}")
        
        # Then rename directories bottom-up (collect paths first to avoid modification during iteration)
        dirs_to_rename = []
        for item in directory.rglob('*'):
            if item.is_dir() and '%2F' in item.name:
                dirs_to_rename.append(item)
        
        # Sort directories by depth (deepest first) to handle nested paths
        dirs_to_rename.sort(key=lambda x: len(x.parts), reverse=True)
        
        # Rename the directories
        for old_path in dirs_to_rename:
            try:
                new_name = old_path.name.replace('%2F', '.')
                new_path = old_path.parent / new_name
                if new_path.exists():
                    print_warning(f"Skipping {old_path.name} - {new_name} already exists")
                    continue
                old_path.rename(new_path)
                print_info(f"Renamed directory: {old_path.name} -> {new_name}")
            except Exception as e:
                print_error(f"Error renaming directory {old_path.name}: {str(e)}")

    def process_basic_information(self, extract_dir: Path) -> Optional[Dict[str, Any]]:
        """Process basic information file and extract system info"""
        json_path = extract_dir / 'results' / 'Generic.Client.Info.BasicInformation.json'
        if not json_path.exists():
            print_error(f"BasicInformation.json not found at expected path: {json_path}")
            return None
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                basic_info = json.load(f)
                return self.extract_system_info(basic_info)
        except Exception as e:
            print_error(f"Error reading BasicInformation.json: {str(e)}")
            return None

    def extract_system_info(self, basic_info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract system information from BasicInformation.json"""
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

    def get_source_type(self, filename: str) -> str:
        """Extract source type from filename"""
        # Replace %2F with . to match the renamed files
        filename = filename.replace('%2F', '.')
        parts = filename.replace('.json', '').split('.')
        return parts[-1] if parts else 'Unknown'

    def update_json_with_system_info(self, extract_dir: Path, system_info: Dict[str, Any]) -> None:
        """Update JSON files with system information and source type"""
        results_dir = extract_dir / 'results'
        if not results_dir.exists():
            print_error("Results directory not found")
            return
        
        print_info("\nUpdating JSON files with system information...")
        for file_path in results_dir.glob('*.json'):
            if file_path.name == 'Generic.Client.Info.BasicInformation.json':
                continue
            
            try:
                # Add source_type and system info to each line
                source_type = self.get_source_type(file_path.name)
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                
                updated_lines = []
                for line in lines:
                    try:
                        json_obj = json.loads(line)
                        json_obj['source_type'] = source_type
                        json_obj.update(system_info)
                        updated_lines.append(json.dumps(json_obj))
                    except json.JSONDecodeError:
                        updated_lines.append(line)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(updated_lines) + '\n')
                
                print_success(f"Updated: {file_path.name}")
                
            except Exception as e:
                print_error(f"Error updating {file_path.name}: {str(e)}")

    def add_timestamps_to_json_files(self, extract_dir: Path) -> None:
        """Add epoch timestamps to JSON files"""
        results_dir = extract_dir / 'results'
        if not results_dir.exists():
            return
            
        timestamp_keys = [
            "visit_time",
            "KeyLastWriteTimestamp",
            "LastUpdated",
            "KeyMTime"
        ]
        
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
        
        print_info("\nAdding timestamps to JSON files...")
        for file_path in results_dir.glob('*.json'):
            if file_path.name != 'Generic.Client.Info.BasicInformation.json':
                self.add_epoch_timestamps(file_path, timestamp_keys)
                self.detect_and_convert_timestamps(file_path, possible_time_keys)

    def convert_iso_to_epoch(self, timestamp_str: str) -> Optional[int]:
        """Convert ISO format timestamp to epoch"""
        try:
            dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
            dt = pytz.utc.localize(dt)
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return None

    def add_epoch_timestamps(self, file_path: Path, timestamp_keys: List[str]) -> None:
        """Add epoch timestamps for specified keys"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            updated_lines = []
            for line in lines:
                try:
                    json_obj = json.loads(line)
                    for key in timestamp_keys:
                        if key in json_obj and isinstance(json_obj[key], str):
                            epoch_time = self.convert_iso_to_epoch(json_obj[key])
                            if epoch_time is not None:
                                json_obj[f"{key}_epoch"] = epoch_time
                    updated_lines.append(json.dumps(json_obj))
                except json.JSONDecodeError:
                    updated_lines.append(line)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated_lines) + '\n')
            
            print_success(f"Added epoch timestamps in: {file_path.name}")
            
        except Exception as e:
            print_error(f"Error adding epoch timestamps in {file_path.name}: {str(e)}")

    def detect_and_convert_timestamps(self, file_path: Path, possible_time_keys: List[str]) -> None:
        """Auto-detect and convert timestamp values"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            updated_lines = []
            conversions_made = False
            
            for line in lines:
                try:
                    json_obj = json.loads(line)
                    for key in list(json_obj.keys()):
                        if any(time_indicator.lower() in key.lower() for time_indicator in possible_time_keys):
                            if f"{key}_epoch" in json_obj:
                                continue
                            if isinstance(json_obj[key], str):
                                epoch_time = self.convert_iso_to_epoch(json_obj[key])
                                if epoch_time is not None:
                                    json_obj[f"{key}_epoch"] = epoch_time
                                    conversions_made = True
                    updated_lines.append(json.dumps(json_obj))
                except json.JSONDecodeError:
                    updated_lines.append(line)
            
            if conversions_made:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(updated_lines) + '\n')
                print_success(f"Auto-detected and converted timestamps in: {file_path.name}")
            
        except Exception as e:
            print_error(f"Error auto-detecting timestamps in {file_path.name}: {str(e)}")

    def delete_index_files(self, directory: Path) -> None:
        """Delete all .index files"""
        print_info("\nDeleting .index files...")
        for root, _, files in os.walk(directory):
            root_path = Path(root)
            for file in files:
                if file.endswith('.index'):
                    file_path = root_path / file
                    try:
                        file_path.unlink()
                        print_success(f"Deleted: {file_path}")
                    except Exception as e:
                        print_error(f"Error deleting {file_path}: {str(e)}")

    def update_artifact_statistics(self, artifact_name: str, success: bool, execution_time: float) -> None:
        """Update statistics for processed artifact"""
        artifact_info = {
            'name': artifact_name,
            'execution_time': execution_time,
            'timestamp': time.strftime('%H:%M:%S')
        }
        
        if success:
            self.status['artifact_stats']['successful'].append(artifact_info)
        else:
            self.status['artifact_stats']['failed'].append(artifact_info)
        
        self.status['processed'] += 1

    def process_single_artifact(self, artifact_name: str, build_collectors: bool) -> bool:
        """Process a single artifact through all steps"""
        try:
            start_time = time.time()
            print_info(f"\nStarting to process artifact: {artifact_name}")
            
            # Step 1: Create artifact spec
            print_info("\nStep 1: Creating artifact spec")
            spec_path = self.create_artifact_spec(artifact_name)
            if not spec_path:
                self.update_artifact_statistics(artifact_name, False, time.time() - start_time)
                return False
            
            if build_collectors:
                # Step 2: Build collector executable
                print_info("\nStep 2: Building collector executable")
                collector_path = self.build_collector_exe(artifact_name, spec_path)
                if not collector_path:
                    self.update_artifact_statistics(artifact_name, False, time.time() - start_time)
                    return False
                
                # Step 3: Push and execute collector
                print_info("\nStep 3: Pushing and executing collector")
                if not self.push_and_execute_collector(collector_path, artifact_name):
                    self.update_artifact_statistics(artifact_name, False, time.time() - start_time)
                    return False
            
            execution_time = time.time() - start_time
            self.update_artifact_statistics(artifact_name, True, execution_time)
            print_success(f"\nSuccessfully processed {artifact_name} in {execution_time:.2f} seconds")
            return True
            
        except Exception as e:
            print_error(f"Error processing artifact {artifact_name}: {str(e)}")
            self.update_artifact_statistics(artifact_name, False, time.time() - start_time)
            return False

    def execute_remote_exe(self, session, exe_path, file_to_pull, credentials):
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
                print_success(f"Execution completed")
                
                # Wait a moment to ensure file is ready
                session.run_ps("Start-Sleep -Seconds 2")
                
                # Check if the file exists before trying to pull it
                check_file = session.run_ps(f"Test-Path '{file_to_pull}'")
                if check_file.std_out.decode('utf-8').strip().lower() != 'true':
                    print_error(f"File {file_to_pull} not found after execution")
                    return False
                    
                print_info(f"\nPulling file {file_to_pull}...")
                
                # Clean runtime directory before pulling new file
                if not self.clean_runtime_directory():
                    return False
                
                # Create SSH client for file transfer
                ssh = self.create_ssh_client(credentials)
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
                    self.update_status(f"File pulled successfully to {local_path}")
                    
                    # Check the output file
                    print_info("\nVerifying execution output...")
                    if self.check_execution_output(local_path):
                        # After successful log file pull, pull the collection zip files
                        print_info("\nPulling Collection zip files...")
                        collection_pattern = "C:\\Windows\\Temp\\Collection-*.zip"
                        self.pull_files_by_pattern(collection_pattern)
                        return True
                    return False
                    
                finally:
                    logger.debug("Closing SFTP and SSH connections")
                    sftp.close()
                    ssh.close()
            else:
                error_msg = result.std_err.decode('utf-8') if result.std_err else result.std_out.decode('utf-8')
                print_error(f"Execution failed: {error_msg}")
                return False
                
        except Exception as e:
            print_error(f"Failed to execute file or pull results: {str(e)}")
            return False

    def check_execution_output(self, output_file):
        """Check if the execution was successful by looking for 'Exiting' in the output"""
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "Exiting" in content:
                    print_success("Execution verification passed: Found 'Exiting' in output")
                    return True
                else:
                    print_error("Execution verification failed: 'Exiting' not found in output")
                    return False
        except Exception as e:
            print_error(f"Failed to read output file: {str(e)}")
            return False

    def run(self, artifacts: Optional[List[str]] = None, build_collectors: bool = False) -> bool:
        """Main entry point for running the collector manager"""
        try:
            if self.mode == 'batch':
                if not artifacts:
                    print_error("Artifacts list required for batch mode")
                    logger.error("Artifacts list required for batch mode")
                    return False
                logger.info(f"Starting batch mode with build_collectors={build_collectors}")
                return self.run_batch_mode(artifacts, build_collectors)
                
            elif self.mode == 'individual':
                if not artifacts:
                    print_error("Artifacts list required for individual mode")
                    logger.error("Artifacts list required for individual mode")
                    return False
                logger.info(f"Starting individual mode with build_collectors={build_collectors}")
                return self.run_individual_mode(artifacts, build_collectors)
                
            elif self.mode == 'windows_test':
                return self.run_windows_test()
                
            elif self.mode == 'process_zip':
                return self.process_zip_files()
                
            else:
                print_error(f"Unknown mode: {self.mode}")
                logger.error(f"Unknown mode: {self.mode}")
                return False
                
        except Exception as e:
            print_error(f"Error in CollectorManager.run: {str(e)}")
            logger.error(f"Error in CollectorManager.run: {str(e)}")
            return False

    def run_batch_mode(self, artifacts: List[str], build_collectors: bool = False) -> bool:
        """Run batch processing of artifacts"""
        logger.info(f"Starting batch mode with {len(artifacts)} artifacts and build_collectors={build_collectors}")
        self.status['processing'] = True
        self.status['completed'] = False
        self.status['total_artifacts'] = len(artifacts)
        self.status['processed'] = 0
        
        try:
            # Initialize directories and connections
            logger.debug("Cleaning directories")
            if not self.clean_all_directories():
                logger.error("Failed to clean directories")
                self.update_status("Failed to clean directories", True)
                return False
            
            logger.debug("Initializing directories")
            init_directories()
            
            if build_collectors:
                logger.info("Build collectors flag is True, initializing connections")
                if not self.initialize_connections():
                    logger.error("Failed to initialize connections")
                    return False
            else:
                logger.info("Build collectors flag is False, skipping connection initialization")
            
            # Process each artifact
            logger.info("Starting artifact processing")
            overall_success = True
            for artifact in artifacts:
                logger.debug(f"Processing artifact: {artifact} with build_collectors={build_collectors}")
                if not self.process_single_artifact(artifact, build_collectors):
                    logger.warning(f"Failed to process artifact: {artifact}")
                    overall_success = False
            
            # After all artifacts are processed, pull all zip files at once
            if build_collectors and overall_success:
                logger.info("All artifacts processed, pulling collection data")
                print_info("\nPulling all collection data...")
                if not self.pull_collection_data():
                    logger.error("Failed to pull collection data")
                    overall_success = False
                else:
                    # Process the pulled data
                    print_info("\nProcessing collection data...")
                    if not self.process_collection_data():
                        logger.error("Failed to process collection data")
                        overall_success = False
            
            return overall_success
            
        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")
            self.update_status(f"Error in batch processing: {str(e)}", True)
            return False
        finally:
            self.status['processing'] = False
            self.status['completed'] = True
            self.status['task_start_time'] = None
            
            if self.winrm_session:
                logger.debug("Cleaning up remote files")
                self.cleanup_remote_files(self.winrm_session)

    def update_status(self, message: str, is_error: bool = False) -> None:
        """Update processing status and send to queue"""
        current_time = time.time()
        elapsed = ""
        
        if self.status['task_start_time'] is not None:
            elapsed = f"(took {current_time - self.status['task_start_time']:.2f}s)"
        
        self.status['task_start_time'] = current_time
        
        status_update = {
            'message': message,
            'timestamp': time.strftime('%H:%M:%S'),
            'type': 'error' if is_error else 'info',
            'elapsed': elapsed
        }
        
        log_level = logging.ERROR if is_error else logging.INFO
        logger.log(log_level, f"{message} {elapsed}")
        
        self.progress_queue.put(status_update)
        self.status['messages'].append(status_update)

    def create_winrm_session(self, credentials: Dict[str, str]) -> winrm.Session:
        """Create a WinRM session"""
        return winrm.Session(
            credentials['host'],
            auth=(credentials['username'], credentials['password']),
            transport='ntlm',
            server_cert_validation='ignore'
        )

    def create_ssh_client(self, credentials: Dict[str, str]) -> Optional[paramiko.SSHClient]:
        """Create SSH client"""
        try:
            # Log all connection parameters
            logger.info("Creating SSH client with parameters:")
            
            # Check if credentials is None
            if credentials is None:
                logger.error("Credentials object is None")
                print_error("Credentials object is None")
                return None
                
            # Check if credentials is empty
            if not credentials:
                logger.error("Credentials dictionary is empty")
                print_error("Credentials dictionary is empty")
                return None
            
            # Check for required credential fields
            required_fields = ['host', 'username', 'password']
            missing_fields = [field for field in required_fields if not credentials.get(field)]
            if missing_fields:
                logger.error(f"Missing required credentials: {', '.join(missing_fields)}")
                print_error(f"Missing required credentials: {', '.join(missing_fields)}")
                return None
            
            logger.info(f"Host: {credentials['host']}")
            logger.info(f"Username: {credentials['username']}")
            logger.info(f"Port: {credentials.get('ssh_port', 22)}")
            logger.debug("Password: [REDACTED]")  # Don't log the actual password
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.info("Attempting SSH connection...")
            ssh.connect(
                credentials['host'],
                port=int(credentials.get('ssh_port', 22)),
                username=credentials['username'],
                password=credentials['password']
            )
            logger.info("SSH connection established successfully")
            return ssh
        except Exception as e:
            logger.error(f"Failed to establish SSH connection: {str(e)}")
            self.update_status(f"Failed to establish SSH connection: {str(e)}", True)
            return None

    def execute_command(self, session: winrm.Session, command: str) -> Dict[str, Any]:
        """Execute a command via WinRM"""
        result = session.run_ps(command)
        return {
            'status_code': result.status_code,
            'stdout': result.std_out.decode('utf-8'),
            'stderr': result.std_err.decode('utf-8')
        }

    def verify_file_integrity(self, winrm_session, local_path, remote_path):
        """Verify file integrity by comparing size and hash"""
        try:
            # Get local file details
            local_size = os.path.getsize(local_path)
            local_hash = self.get_file_hash(local_path)
            
            # Get remote file details using WinRM
            size_result = winrm_session.run_ps(f'(Get-Item "{remote_path}").Length')
            if size_result.status_code != 0:
                print_error(f"Failed to get remote file size")
                return False
                
            remote_size = int(size_result.std_out.decode('utf-8').strip())
            
            # Compare sizes
            if local_size != remote_size:
                print_error(f"Size verification failed: Local {local_size:,} bytes, Remote {remote_size:,} bytes")
                return False
            
            # Get and compare hashes
            remote_hash = self.get_remote_file_hash(winrm_session, remote_path)
            
            if not remote_hash:
                print_error(f"Failed to get remote file hash")
                return False
                
            if local_hash.lower() != remote_hash.lower():
                print_error(f"Hash verification failed")
                return False
                
            print_success(f"File integrity verified (SHA256: {local_hash})")
            return True
            
        except Exception as e:
            print_error(f"Verification failed: {str(e)}")
            return False

    def get_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def get_remote_file_hash(self, session: winrm.Session, file_path: str) -> Optional[str]:
        """Get remote file hash"""
        ps_command = f"""
        $hash = Get-FileHash -Path '{file_path}' -Algorithm SHA256
        $hash.Hash.ToLower()
        """
        result = session.run_ps(ps_command)
        if result.status_code == 0:
            return result.std_out.decode('utf-8').strip()
        return None

    def process_files(self, input_dir: str = 'runtime', output_dir: str = 'runtime_zip', mode: str = 'collection') -> bool:
        """Process files in input directory and save results to output directory"""
        try:
            print_info(f"\nProcessing files from: {input_dir}")
            print_info(f"Saving results to: {output_dir}")
            
            input_dir = Path(input_dir)
            output_dir = Path(output_dir)
            
            # Create output directory if it doesn't exist
            output_dir.mkdir(exist_ok=True)
            
            if not input_dir.exists():
                print_error(f"Error: Source directory '{input_dir}' does not exist!")
                return False
            
            # Find zip files
            zip_files = list(input_dir.glob('*.zip'))
            if not zip_files:
                print_warning("No zip files found!")
                return False
            
            # Step 1: First unzip all files
            print_info("\nStep 1: Unzipping files")
            for zip_path in zip_files:
                if not self.unzip_collection_file(zip_path, output_dir):
                    print_error(f"Failed to unzip {zip_path.name}")
                    return False
            
            # Step 2: Process extracted files
            print_info("\nStep 2: Processing extracted files")
            if mode == 'collection':
                success = self.process_extracted_files(output_dir)
            else:  # mode == 'zip'
                success = True
                for zip_path in zip_files:
                    try:
                        process_single_zip(zip_path, output_dir)
                        if not check_process_single_zip(zip_path, output_dir):
                            success = False
                    except Exception as e:
                        print_error(f"Error processing {zip_path.name}: {str(e)}")
                        success = False
            
            return success
            
        except Exception as e:
            print_error(f"Error processing files: {str(e)}")
            return False

    def process_zip_files(self, input_dir: str = 'runtime', output_dir: str = 'runtime_zip') -> bool:
        """Process all zip files in input directory and save results to output directory"""
        return self.process_files(input_dir, output_dir, mode='zip')

    def process_collection_data(self) -> bool:
        """Process all collection data"""
        return self.process_files(mode='collection')

    def run_windows_test(self) -> bool:
        """Run Windows testing functionality"""
        credentials = get_winrm_credentials()
        credentials['local_file'] = Config.get('COLLECTOR_FILE')
        
        required_vars = ['host', 'username', 'password']
        missing_vars = [var for var in required_vars if not credentials[var]]
        
        if missing_vars:
            print_error(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
            return False
        
        try:
            init_directories()
            winrm_session = self.create_winrm_session(credentials)
            
            result = self.execute_command(winrm_session, 'whoami')
            
            if result['status_code'] == 0:
                print_success(f"Command output: {result['stdout']}")
                
                if not self.cleanup_remote_files(winrm_session):
                    print_warning("Proceeding despite cleanup issues...")
                
                local_file = credentials['local_file']
                remote_file = "C:\\Windows\\Temp\\Collector_velociraptor.exe"
                
                if self.copy_and_verify_file(winrm_session, credentials, local_file, remote_file):
                    file_to_pull = "C:\\Windows\\Temp\\Collector_velociraptor-v0.72.4-windows-amd64.exe.log"
                    return self.execute_remote_exe(winrm_session, remote_file, file_to_pull, credentials)
            
            print_error(f"Command failed with error: {result['stderr']}")
            return False
            
        except Exception as e:
            print_error(f"An error occurred: {str(e)}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current status information"""
        while not self.progress_queue.empty():
            try:
                self.progress_queue.get_nowait()
            except queue.Empty:
                break

        status_copy = self.status.copy()
        status_copy['results'] = self.get_results() if self.status['completed'] else []
        return status_copy

    def get_results(self) -> List[Dict[str, Any]]:
        """Get processing results"""
        results = []
        runtime_zip_path = 'runtime_zip'
        if os.path.exists(runtime_zip_path):
            for root, _, files in os.walk(runtime_zip_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    result = {'path': file_path}
                    
                    if file.endswith('.json'):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                                last_two = lines[-2:] if len(lines) >= 2 else lines
                                result['preview'] = [line.strip() for line in last_two]
                        except Exception as e:
                            result['preview'] = [f"Error reading file: {str(e)}"]
                    results.append(result)
        return results

    def stop_processing(self) -> None:
        """Stop current processing if running"""
        if self.status['processing']:
            self.update_status("Stopping processing by user request...")
            self.status['processing'] = False
            self.status['completed'] = True
            
            # Clean up any active connections
            if self.winrm_session:
                try:
                    self.cleanup_remote_files(self.winrm_session)
                except:
                    pass
                self.winrm_session = None
            
            self.credentials = None
            self.update_status("Processing stopped by user request")

    def clean_runtime_directory(self) -> bool:
        """Clean the runtime directory by removing all files"""
        return self.clean_all_directories(['runtime'])

    def pull_files_by_pattern(self, remote_pattern: str, local_dir: str = "./runtime") -> bool:
        """Pull files matching a pattern from remote system"""
        try:
            ps_command = f"""
            Get-ChildItem -Path '{remote_pattern}' | Select-Object -ExpandProperty FullName
            """
            result = self.execute_command(self.winrm_session, ps_command)
            
            if result['status_code'] != 0:
                self.update_status("Failed to list files matching pattern", True)
                return False
                
            files = result['stdout'].strip().split('\n')
            files = [f.strip() for f in files if f.strip()]
            
            if not files:
                self.update_status(f"No files found matching pattern: {remote_pattern}", True)
                return False
                
            ssh = self.create_ssh_client(self.credentials)
            if not ssh:
                return False
                
            try:
                sftp = ssh.open_sftp()
                
                for remote_path in files:
                    try:
                        local_filename = os.path.basename(remote_path)
                        local_path = os.path.join(local_dir, local_filename)
                        
                        self.update_status(f"Pulling file {remote_path}...")
                        sftp.get(remote_path, local_path)
                        self.update_status(f"File pulled successfully to {local_path}")
                    except Exception as e:
                        self.update_status(f"Failed to pull {remote_path}: {str(e)}", True)
                        continue
                        
                return True
                    
            finally:
                sftp.close()
                ssh.close()
                
        except Exception as e:
            self.update_status(f"Failed to pull files: {str(e)}", True)
            return False

    def cleanup_remote_files(self, session: winrm.Session) -> bool:
        """Clean up temporary files from the remote system"""
        try:
            print_info("\nCleaning up remote files...")
            logger.debug("Cleaning up remote files")
            
            # List of patterns to clean up
            patterns = [
                "C:\\Windows\\Temp\\Collector_*.exe",
                "C:\\Windows\\Temp\\Collector_*.log",
                "C:\\Windows\\Temp\\Collection-*.zip"
            ]
            
            for pattern in patterns:
                # First list files matching the pattern
                ps_command = f"""
                Get-ChildItem -Path '{pattern}' -ErrorAction SilentlyContinue | ForEach-Object {{
                    try {{
                        Remove-Item $_.FullName -Force
                        "Removed: " + $_.FullName
                    }} catch {{
                        "Failed to remove: " + $_.FullName + " - " + $_.Exception.Message
                    }}
                }}
                """
                
                result = self.execute_command(session, ps_command)
                if result['status_code'] == 0:
                    if result['stdout']:
                        print_info(f"Cleanup results for {pattern}:")
                        for line in result['stdout'].split('\n'):
                            if line.strip():
                                if line.startswith("Failed"):
                                    print_warning(line)
                                else:
                                    print_success(line)
                else:
                    print_warning(f"Cleanup command failed for {pattern}: {result['stderr']}")
            
            print_success("Remote cleanup completed")
            return True
            
        except Exception as e:
            print_error(f"Error during remote cleanup: {str(e)}")
            logger.error(f"Error during remote cleanup: {str(e)}")
            return False

    def copy_and_verify_file(self, winrm_session, credentials, local_path, remote_path):
        """
        Copy a file to the remote host using SSH/SCP and verify its presence
        """
        try:
            logger.info(f"Starting file copy operation")
            logger.debug(f"Local path: {local_path}")
            logger.debug(f"Remote path: {remote_path}")
            print_info(f"Copying file to {remote_path}...")
            
            # Create SSH client
            logger.debug("Initializing SSH client")
            ssh = self.create_ssh_client(credentials)
            if not ssh:
                logger.error("Failed to create SSH client")
                return False
                
            try:
                # Create SFTP client
                logger.debug("Creating SFTP client")
                sftp = ssh.open_sftp()
                
                # Get file size and calculate chunks for progress
                file_size = os.path.getsize(local_path)
                logger.debug(f"File size: {file_size / (1024*1024):.2f} MB")
                print_info(f"File size: {file_size / (1024*1024):.2f} MB")
                
                def progress_callback(sent, total):
                    if sent % (1024*1024) == 0:  # Log every 1MB
                        progress = (sent/total*100)
                        logger.debug(f"Transfer progress: {progress:.1f}% ({sent}/{total} bytes)")
                        print_info(f"Progress: {progress:.1f}%")
                
                # Copy the file
                logger.debug("Starting file transfer")
                sftp.put(local_path, remote_path, callback=progress_callback)
                logger.info("File transfer completed")
                
                # Verify file integrity
                logger.debug("Starting file integrity verification")
                verification_result = self.verify_file_integrity(winrm_session, local_path, remote_path)
                if verification_result:
                    logger.info("File integrity verification passed")
                else:
                    logger.error("File integrity verification failed")
                return verification_result
                    
            except Exception as e:
                logger.error(f"SFTP operation failed: {str(e)}", exc_info=True)
                print_error(f"File transfer failed: {str(e)}")
                return False
            finally:
                logger.debug("Closing SFTP and SSH connections")
                sftp.close()
                ssh.close()
                
        except Exception as e:
            logger.error(f"File transfer failed: {str(e)}", exc_info=True)
            print_error(f"File transfer failed: {str(e)}")
            return False

    def pull_file(self, session, credentials, remote_path, local_path):
        """
        Pull a single file from the remote system using SFTP
        Args:
            session: WinRM session
            credentials: Credentials dictionary
            remote_path: Path to file on remote system
            local_path: Path to save file locally
        """
        try:
            # Check if file exists on remote system
            check_file = session.run_ps(f"Test-Path '{remote_path}'")
            if check_file.std_out.decode('utf-8').strip().lower() != 'true':
                print_error(f"Remote file not found: {remote_path}")
                return False

            # Create SSH client for file transfer
            ssh = self.create_ssh_client(credentials)
            if not ssh:
                return False

            try:
                # Create SFTP client
                sftp = ssh.open_sftp()
                
                # Create local directory if it doesn't exist
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                # Download the file
                print_info(f"Pulling file {remote_path} to {local_path}...")
                sftp.get(remote_path, local_path)
                print_success(f"File pulled successfully to {local_path}")
                return True
                
            finally:
                sftp.close()
                ssh.close()
                
        except Exception as e:
            print_error(f"Failed to pull file: {str(e)}")
            return False

    def unzip_collection_file(self, zip_path: Path, runtime_zip_dir: Path) -> bool:
        """Unzip a single collection file to runtime_zip directory"""
        try:
            print_info(f"\nUnzipping: {zip_path.name}")
            
            # Set up extraction directory using the zip file stem (name without extension)
            extract_dir = runtime_zip_dir / zip_path.stem
            extract_dir.mkdir(exist_ok=True)
            
            # Extract the zip file
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                print_success(f"Successfully extracted to: {extract_dir}")
                return True
            except Exception as e:
                print_error(f"Error extracting {zip_path.name}: {str(e)}")
                return False
            
        except Exception as e:
            print_error(f"Error unzipping file: {str(e)}")
            return False

    def process_extracted_files(self, runtime_zip_dir: Path) -> bool:
        """Process all extracted files in runtime_zip directory"""
        try:
            success = True
            
            # Process each collection directory
            for collection_dir in runtime_zip_dir.iterdir():
                if not collection_dir.is_dir():
                    continue
                    
                print_info(f"\nProcessing collection directory: {collection_dir.name}")
                
                # Extract metadata from directory name
                fqdn, timestamp = self.extract_filename_info(collection_dir.name)
                if fqdn and timestamp:
                    print_info(f"FQDN: {fqdn}")
                    print_info(f"Timestamp: {timestamp}")
                
                # Recursively rename all files and directories
                print_info("Renaming files and directories...")
                self.rename_files_in_directory(collection_dir)
                
                # Process system information
                system_info = self.process_basic_information(collection_dir)
                if not system_info:
                    print_error(f"Failed to process basic information in {collection_dir.name}")
                    success = False
                    continue
                
                # Update JSON files with system info and timestamps
                self.update_json_with_system_info(collection_dir, system_info)
                self.add_timestamps_to_json_files(collection_dir)
                
                # Clean up index files
                self.delete_index_files(collection_dir)
                
                # Validate the processing
                if not self.check_process_single_zip(collection_dir.parent / f"{collection_dir.name}.zip", runtime_zip_dir):
                    success = False
            
            return success
            
        except Exception as e:
            print_error(f"Error processing extracted files: {str(e)}")
            return False

    def delete_remote_file(self, session: winrm.Session, remote_path: str) -> bool:
        """Delete a specific file from the remote system"""
        try:
            print_info(f"\nDeleting remote file: {remote_path}")
            logger.debug(f"Deleting remote file: {remote_path}")
            
            ps_command = f"""
            try {{
                if (Test-Path '{remote_path}') {{
                    Remove-Item '{remote_path}' -Force
                    "Successfully deleted {remote_path}"
                }} else {{
                    "File not found: {remote_path}"
                }}
            }} catch {{
                throw "Failed to delete {remote_path}: $_"
            }}
            """
            
            result = self.execute_command(session, ps_command)
            if result['status_code'] == 0:
                if "Successfully deleted" in result['stdout']:
                    print_success("Remote file deleted successfully")
                    return True
                else:
                    print_warning(result['stdout'])
                    return False
            else:
                print_error(f"Failed to delete remote file: {result['stderr']}")
                return False
                
        except Exception as e:
            print_error(f"Error deleting remote file: {str(e)}")
            logger.error(f"Error deleting remote file: {str(e)}")
            return False

    def create_combined_artifact_spec(self, artifacts: List[str], spec_name: str = None) -> Optional[str]:
        """Create a combined spec file for multiple artifacts"""
        logger.info(f"Creating combined spec for artifacts: {', '.join(artifacts)}")
        try:
            self.update_status(f"Creating combined spec for {len(artifacts)} artifacts")
            
            spec_generator = SpecFileGenerator(
                Config.get('ARTIFACT_TEMPLATE_PATH'),
                Config.get('ARTIFACT_LIST_FILE'),
                Config.get('ARTIFACT_SPECS_DIR')
            )
            
            logger.debug(f"Template path: {Config.get('ARTIFACT_TEMPLATE_PATH')}")
            logger.debug(f"Artifact list: {Config.get('ARTIFACT_LIST_FILE')}")
            logger.debug(f"Specs directory: {Config.get('ARTIFACT_SPECS_DIR')}")
            
            # Generate a unique spec name if not provided
            if not spec_name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                spec_name = f"profile_artifacts_{timestamp}"
            
            spec_path = spec_generator.create_combined_spec_file(artifacts, spec_name)
            if spec_path:
                logger.info(f"Successfully created combined spec file at: {spec_path}")
                self.update_status(f"Created combined spec file with {len(artifacts)} artifacts")
                return spec_path
            else:
                logger.error("Failed to create combined spec")
                self.update_status("Failed to create combined spec", True)
                return None
        except Exception as e:
            logger.error(f"Error creating combined spec: {str(e)}")
            self.update_status(f"Error creating combined spec: {str(e)}", True)
            return None

    def process_artifact_combination(self, artifacts: List[str], build_collectors: bool) -> bool:
        """Process a combination of artifacts as a single unit"""
        try:
            start_time = time.time()
            logger.info(f"Starting to process artifact combination with {len(artifacts)} artifacts")
            logger.debug(f"Artifacts to process: {', '.join(artifacts)}")
            logger.debug(f"Build collectors flag: {build_collectors}")
            print_info(f"\nStarting to process artifact combination: {', '.join(artifacts)}")
            
            # Generate a unique name for this profile
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            profile_name = f"profile_artifacts_{timestamp}"
            logger.info(f"Generated profile name: {profile_name}")
            
            # Step 1: Create combined artifact spec
            print_info("\nStep 1: Creating combined artifact spec")
            logger.info("Step 1: Creating combined artifact spec")
            spec_path = self.create_combined_artifact_spec(artifacts, profile_name)
            if not spec_path:
                logger.error("Failed to create combined artifact spec")
                self.update_artifact_statistics(profile_name, False, time.time() - start_time)
                return False
            logger.info(f"Successfully created combined spec at: {spec_path}")
            
            if build_collectors:
                # Step 2: Build collector executable
                print_info("\nStep 2: Building collector executable")
                logger.info("Step 2: Building collector executable")
                collector_path = self.build_collector_exe(profile_name, spec_path)
                if not collector_path:
                    logger.error("Failed to build collector executable")
                    self.update_artifact_statistics(profile_name, False, time.time() - start_time)
                    return False
                logger.info(f"Successfully built collector at: {collector_path}")
                
                # Step 3: Push and execute collector
                print_info("\nStep 3: Pushing and executing collector")
                logger.info("Step 3: Pushing and executing collector")
                if not self.push_and_execute_collector(collector_path, profile_name):
                    logger.error("Failed to push and execute collector")
                    self.update_artifact_statistics(profile_name, False, time.time() - start_time)
                    return False
                logger.info("Successfully pushed and executed collector")
            
            execution_time = time.time() - start_time
            self.update_artifact_statistics(profile_name, True, execution_time)
            success_msg = f"Successfully processed {profile_name} in {execution_time:.2f} seconds"
            print_success(f"\n{success_msg}")
            logger.info(success_msg)
            return True
            
        except Exception as e:
            error_msg = f"Error processing combined artifacts: {str(e)}"
            print_error(error_msg)
            logger.error(error_msg, exc_info=True)  # Include full exception traceback
            self.update_artifact_statistics("CombinedArtifacts", False, time.time() - start_time)
            return False

def main():
    """Command line interface for CollectorManager"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Velociraptor Collector Manager')
    parser.add_argument('--mode', choices=['batch', 'individual', 'windows_test', 'process_zip'],
                      default='batch', help='Operation mode')
    parser.add_argument('--artifacts', help='Comma-separated list of artifacts to process')
    parser.add_argument('--build', action='store_true', help='Build collectors for artifacts')
    parser.add_argument('--input-dir', default='runtime',
                      help='Directory containing zip files to process (for process_zip mode). Defaults to "runtime"')
    parser.add_argument('--output-dir', default='runtime_zip',
                      help='Directory to save processed files (for process_zip mode). Defaults to "runtime_zip"')
    
    args = parser.parse_args()
    
    manager = CollectorManager(mode=args.mode)
    
    if args.mode == 'process_zip':
        success = manager.process_zip_files(args.input_dir, args.output_dir)
    else:
        artifacts = args.artifacts.split(',') if args.artifacts else None
        success = manager.run(artifacts=artifacts, build_collectors=args.build)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 