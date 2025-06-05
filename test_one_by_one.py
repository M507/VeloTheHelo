import os
import sys
import shutil
from typing import Tuple, List, Optional
from config import Config, init_directories

def clean_testing_specs():
    """Clean the testing_specs directory by removing all files"""
    specs_dir = Config.get('ARTIFACT_SPECS_DIR')
    try:
        if os.path.exists(specs_dir):
            shutil.rmtree(specs_dir)
            print(f"\nCleaned {specs_dir} directory")
        os.makedirs(specs_dir)
        print(f"Created fresh {specs_dir} directory")
        return True
    except Exception as e:
        print(f"Error cleaning {specs_dir} directory: {e}")
        return False

class SpecFileGenerator:
    def __init__(self, template_path: str, artifacts_path: str, output_dir: str):
        self.template_path = template_path
        self.artifacts_path = artifacts_path
        self.output_dir = output_dir
        self.template_encoding = None

    def try_read_file(self, file_path: str) -> Tuple[Optional[List[str]], Optional[str]]:
        """Try to read a file with different encodings."""
        print(f"\nAttempting to read {file_path}")
        
        # First try UTF-16
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                lines = f.readlines()
                print(f"Successfully read {len(lines)} lines with UTF-16")
                return lines, 'utf-16'
        except UnicodeError:
            pass

        # Then try other encodings
        for encoding in ['utf-8', 'latin1', 'ascii']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                    print(f"Successfully read {len(lines)} lines with {encoding}")
                    return lines, encoding
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
        
        print(f"Failed to read {file_path} with any encoding")
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
            
            print(f"\nCreating spec file: {spec_path}")
            print(f"Content length: {len(new_content)} lines")
            
            with open(spec_path, 'w', newline='', encoding=self.template_encoding) as spec_file:
                spec_file.writelines(new_content)
            
            print(f"Successfully created spec file for {artifact}")
            return spec_path
        except Exception as e:
            print(f"Error creating spec file for {artifact}: {e}")
            return ""

    def generate_all_specs(self) -> int:
        """Generate spec files for all artifacts."""
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                print(f"Created directory: {self.output_dir}")

            # Validate input files
            for path in [self.template_path, self.artifacts_path]:
                if not os.path.exists(path):
                    print(f"Error: File not found: {path}")
                    return 0

            # Read template file
            template_lines, self.template_encoding = self.try_read_file(self.template_path)
            if not template_lines:
                return 0

            # Find section markers
            start, end = self.find_section_markers(template_lines)
            if start == -1 or end == -1:
                print("Error: Could not find section markers in template")
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
                print("Error: No artifacts found in the artifacts file")
                return 0

            print(f"\nFound {len(artifacts)} artifacts to process")

            # Create spec files
            created_files = 0
            for artifact in artifacts:
                if self.create_spec_file(artifact, header_lines, footer_lines):
                    created_files += 1

            print(f"\nSummary:")
            print(f"Total artifacts processed: {len(artifacts)}")
            print(f"Successfully created files: {created_files}")
            print(f"Files can be found in: {os.path.abspath(self.output_dir)}")
            
            return created_files

        except Exception as e:
            print(f"\nUnexpected error: {e}")
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
            
            # Build the command
            cmd = f"{self.velociraptor_path} --config {server_config} collector {spec_path}"
            
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

def test_single_artifact(artifact_name: str, spec_generator: SpecFileGenerator, 
                        collector_manager: CollectorManager) -> bool:
    """
    Test a single artifact by:
    1. Creating its spec file
    2. Building a collector
    3. Running it on the remote host
    4. Collecting and analyzing the results
    """
    try:
        # Create spec file for the artifact
        print(f"\nTesting artifact: {artifact_name}")
        
        # Read template and create spec
        template_lines, encoding = spec_generator.try_read_file(spec_generator.template_path)
        if not template_lines:
            return False

        start, end = spec_generator.find_section_markers(template_lines)
        if start == -1 or end == -1:
            print("Error: Could not find section markers in template")
            return False

        header_lines = template_lines[:start + 2]
        footer_lines = template_lines[end:]

        # Create spec file
        spec_path = spec_generator.create_spec_file(artifact_name, header_lines, footer_lines)
        if not spec_path:
            return False

        print(f"Created spec file: {spec_path}")

        # Create collector executable
        collector_path = collector_manager.create_collector(spec_path)
        if not collector_path:
            return False

        return True

    except Exception as e:
        print(f"Error testing artifact {artifact_name}: {e}")
        return False

def print_usage():
    print("\nUsage:")
    print("  Generate all specs:")
    print("    python test_one_by_one.py --generate-all")
    print("\n  Test single artifact:")
    print("    python test_one_by_one.py --test-artifact <artifact_name>")
    print("\n  Show current configuration:")
    print("    python test_one_by_one.py --show-config")
    print("\nExample:")
    print("    python test_one_by_one.py --test-artifact Windows.System.PowerShell")

def main():
    # Clean testing_specs directory at start
    if not clean_testing_specs():
        print("Failed to clean testing_specs directory. Exiting.")
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
            artifact_name = sys.argv[2]
            spec_generator = SpecFileGenerator(
                Config.get('ARTIFACT_TEMPLATE_PATH'),
                Config.get('ARTIFACT_LIST_FILE'),
                Config.get('ARTIFACT_SPECS_DIR')
            )
            collector_manager = CollectorManager(
                Config.get('VELO_BINARY_PATH'),
                Config.get('WINRM_HOST')
            )
            test_single_artifact(artifact_name, spec_generator, collector_manager)
        else:
            print("Invalid command")
            print_usage()
    else:
        print_usage()

if __name__ == '__main__':
    main()
