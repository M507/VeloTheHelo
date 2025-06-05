import os
import sys
import shutil
from typing import Tuple, List, Optional
from config import Config, init_directories
from colors import print_success, print_error, print_info, print_warning, SUCCESS_EMOJI, ERROR_EMOJI

def clean_testing_specs():
    """Clean the testing_specs directory by removing all files"""
    specs_dir = Config.get('ARTIFACT_SPECS_DIR')
    try:
        if os.path.exists(specs_dir):
            shutil.rmtree(specs_dir)
            print_success(f"Cleaned {specs_dir} directory")
        os.makedirs(specs_dir)
        print_success(f"Created fresh {specs_dir} directory")
        return True
    except Exception as e:
        print_error(f"Error cleaning {specs_dir} directory: {e}")
        return False

class SpecFileGenerator:
    def __init__(self, template_path: str, artifacts_path: str, output_dir: str):
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
            pass

        # Then try other encodings
        for encoding in ['utf-8', 'latin1', 'ascii']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                    print_success(f"Successfully read {len(lines)} lines with {encoding}")
                    return lines, encoding
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print_error(f"Error reading file {file_path}: {e}")
        
        print_error(f"Failed to read {file_path} with any encoding")
        return None, None

    def find_section_markers(self, lines: List[str]) -> Tuple[int, int]:
        """Find the start and end markers in the template."""
        start = -1
        end = -1
        
        for i, line in enumerate(lines):
            if "The list of artifacts and their args." in line:
                start = i
            elif "Can be ZIP" in line:
                end = i
                break
        
        return start, end

    def create_spec_file(self, artifact: str, header_lines: List[str], 
                        footer_lines: List[str]) -> str:
        """Create a spec file for a single artifact."""
        try:
            # Create the new content
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
            
            print_info(f"\nCreating spec file: {spec_path}")
            print_info(f"Content length: {len(new_content)} lines")
            
            with open(spec_path, 'w', newline='', encoding=self.template_encoding) as spec_file:
                spec_file.writelines(new_content)
            
            print_success(f"Successfully created spec file for {artifact}")
            return spec_path
        except Exception as e:
            print_error(f"Error creating spec file for {artifact}: {e}")
            return ""

    def generate_all_specs(self) -> int:
        """Generate spec files for all artifacts."""
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                print_success(f"Created directory: {self.output_dir}")

            # Validate input files
            for path in [self.template_path, self.artifacts_path]:
                if not os.path.exists(path):
                    print_error(f"Error: File not found: {path}")
                    return 0

            # Read template file
            template_lines, self.template_encoding = self.try_read_file(self.template_path)
            if not template_lines:
                return 0

            # Find section markers
            start, end = self.find_section_markers(template_lines)
            if start == -1 or end == -1:
                print_error("Error: Could not find section markers in template")
                return 0

            # Split template
            header_lines = template_lines[:start + 2]  # Include the marker and "Artifacts:" line
            footer_lines = template_lines[end:]

            # Read artifacts
            artifacts_lines, _ = self.try_read_file(self.artifacts_path)
            if not artifacts_lines:
                return 0

            artifacts = [line.strip() for line in artifacts_lines if line.strip()]
            if not artifacts:
                print_error("Error: No artifacts found in the artifacts file")
                return 0

            print_info(f"\nFound {len(artifacts)} artifacts to process")

            # Create spec files
            created_files = 0
            for artifact in artifacts:
                if self.create_spec_file(artifact, header_lines, footer_lines):
                    created_files += 1

            print_info(f"\nSummary:")
            print_success(f"Total artifacts processed: {len(artifacts)}")
            print_success(f"Successfully created files: {created_files}")
            print_success(f"Files can be found in: {os.path.abspath(self.output_dir)}")
            
            return created_files

        except Exception as e:
            print_error(f"\nUnexpected error: {e}")
            import traceback
            traceback.print_exc()
            return 0

class CollectorManager:
    def __init__(self, velociraptor_path: str, remote_host: str):
        self.velociraptor_path = velociraptor_path
        self.remote_host = remote_host

    def create_collector(self, spec_path: str) -> str:
        """
        Create a collector executable from a spec file.
        Returns the path to the created collector executable.
        """
        try:
            # Get the filename without extension
            spec_name = os.path.splitext(os.path.basename(spec_path))[0]
            
            # Create output directory for collectors if it doesn't exist
            collectors_dir = Config.get('ARTIFACT_COLLECTORS_DIR')
            if not os.path.exists(collectors_dir):
                os.makedirs(collectors_dir)
            
            # The collector will be created in the collectors directory
            collector_path = os.path.join(collectors_dir, f"{spec_name}_collector.exe")
            
            # Get server config path from environment
            server_config = Config.get('VELO_SERVER_CONFIG')
            datastore = Config.get('VELO_DATASTORE')
            
            # Build the command
            cmd = f"{self.velociraptor_path} --config {server_config} collector --datastore {datastore} {spec_path}"
            
            print(f"\nCreating collector for {spec_path}")
            print(f"Command: {cmd}")
            
            # Execute the command
            result = os.system(cmd)
            
            if result == 0:
                print(f"Successfully created collector: {collector_path}")
                return collector_path
            else:
                print(f"Failed to create collector. Exit code: {result}")
                return ""
                
        except Exception as e:
            print(f"Error creating collector: {e}")
            return ""

    def deploy_and_run(self, collector_path: str) -> bool:
        """
        Deploy and run the collector on the remote host.
        Returns True if successful.
        """
        # TODO: Implement remote deployment and execution
        pass

    def collect_logs(self, remote_output_path: str) -> str:
        """
        Collect logs from the remote host.
        Returns the path to the collected logs.
        """
        # TODO: Implement log collection
        pass

    def analyze_results(self, logs_path: str) -> bool:
        """
        Analyze the collected logs to verify if the artifact collection worked.
        Returns True if the collection was successful.
        """
        # TODO: Implement results analysis
        pass

def print_usage():
    print("\nUsage:")
    print("  Generate all specs:")
    print("    python test_one_by_one.py --generate-all")
    print("\n  Test single or multiple artifacts:")
    print("    python test_one_by_one.py --test-artifact <artifact1,artifact2,...> [--build]")
    print("\n  Show current configuration:")
    print("    python test_one_by_one.py --show-config")
    print("\nExamples:")
    print("    # Create and build collector for one artifact:")
    print("    python test_one_by_one.py --test-artifact Windows.System.PowerShell --build")
    print("    # Create specs only for multiple artifacts:")
    print("    python test_one_by_one.py --test-artifact Windows.Sys.AllUsers,Windows.Sys.Users")
    print("    # Create and build collectors for multiple artifacts:")
    print("    python test_one_by_one.py --test-artifact Windows.Sys.AllUsers,Windows.Sys.Users --build")

def create_artifact_spec(artifact_name: str, spec_generator: SpecFileGenerator) -> str:
    """Create a spec file for a single artifact."""
    try:
        print_info(f"\n{SUCCESS_EMOJI} Creating spec file for artifact: {artifact_name}")
        
        # Read template and create spec
        template_lines, encoding = spec_generator.try_read_file(spec_generator.template_path)
        if not template_lines:
            print_error("Failed to read template file")
            return ""

        start, end = spec_generator.find_section_markers(template_lines)
        if start == -1 or end == -1:
            print_error("Error: Could not find section markers in template")
            return ""

        header_lines = template_lines[:start + 2]
        footer_lines = template_lines[end:]

        # Create spec file
        spec_path = spec_generator.create_spec_file(artifact_name, header_lines, footer_lines)
        if not spec_path:
            print_error(f"Failed to create spec file for {artifact_name}")
            return ""

        print_success(f"Successfully created spec file: {spec_path}")
        return spec_path

    except Exception as e:
        print_error(f"Error creating spec for artifact {artifact_name}: {e}")
        return ""

def build_collector(artifact_name: str, spec_path: str, collector_manager: CollectorManager) -> bool:
    """Build a collector executable for a single artifact and run it."""
    try:
        print_info(f"\n{SUCCESS_EMOJI} Building collector executable for {artifact_name}")
        collector_path = collector_manager.create_collector(spec_path)
        if not collector_path:
            print_error(f"Failed to create collector executable for {artifact_name}")
            return False

        print_success(f"Successfully created collector: {collector_path}")

        # Import and run the collector workflow
        print_info(f"\n{SUCCESS_EMOJI} Running collector workflow")
        try:
            from run_collector import main as run_collector_main
            run_collector_main()
            print_success(f"Successfully ran collector workflow for {artifact_name}")
            return True
        except Exception as e:
            print_error(f"Failed to run collector workflow: {e}")
            return False

    except Exception as e:
        print_error(f"Error building and running collector for {artifact_name}: {e}")
        return False

def process_artifacts(artifacts: List[str], spec_generator: SpecFileGenerator, 
                     collector_manager: Optional[CollectorManager] = None) -> bool:
    """Process a list of artifacts - create specs and optionally build collectors."""
    success_count = 0
    total_artifacts = len(artifacts)

    for artifact_name in artifacts:
        artifact_name = artifact_name.strip()
        print_info(f"\nProcessing artifact ({artifacts.index(artifact_name) + 1}/{total_artifacts}): {artifact_name}")
        
        # Create spec file
        spec_path = create_artifact_spec(artifact_name, spec_generator)
        if not spec_path:
            continue

        # Build collector if requested
        if collector_manager:
            if build_collector(artifact_name, spec_path, collector_manager):
                success_count += 1
        else:
            success_count += 1

    # Print summary
    print_info(f"\n{SUCCESS_EMOJI} Summary:")
    print_info(f"Total artifacts processed: {total_artifacts}")
    print_info(f"Successful: {success_count}")
    print_info(f"Failed: {total_artifacts - success_count}")

    return success_count == total_artifacts

def main():
    # Clean testing_specs directory at start
    if not clean_testing_specs():
        print_error("Failed to clean testing_specs directory. Exiting.")
        return

    # Initialize required directories
    init_directories()
    
    # Process command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--show-config':
            Config.print_config()
            return
            
        if sys.argv[1] == '--generate-all':
            spec_generator = SpecFileGenerator(
                Config.get('ARTIFACT_TEMPLATE_PATH'),
                Config.get('ARTIFACT_LIST_FILE'),
                Config.get('ARTIFACT_SPECS_DIR')
            )
            spec_generator.generate_all_specs()
            
        elif sys.argv[1] == '--test-artifact' and len(sys.argv) > 2:
            # Get the list of artifacts
            artifacts = sys.argv[2].split(',')
            
            # Check if we should build collectors
            should_build = '--build' in sys.argv
            
            print_info(f"\nStarting artifact processing:")
            print_info(f"Artifacts to process: {', '.join(artifacts)}")
            print_info(f"Build collectors: {'Yes' if should_build else 'No'}")
            
            spec_generator = SpecFileGenerator(
                Config.get('ARTIFACT_TEMPLATE_PATH'),
                Config.get('ARTIFACT_LIST_FILE'),
                Config.get('ARTIFACT_SPECS_DIR')
            )
            
            # Only create collector manager if building is requested
            collector_manager = None
            if should_build:
                collector_manager = CollectorManager(
                    Config.get('VELO_BINARY_PATH'),
                    Config.get('WINRM_HOST')
                )
            
            if process_artifacts(artifacts, spec_generator, collector_manager):
                print_success(f"\nSuccessfully completed processing all artifacts")
            else:
                print_error(f"\nFailed to process some artifacts")
        else:
            print_error("Invalid command")
            print_usage()
    else:
        print_usage()

if __name__ == '__main__':
    main()
