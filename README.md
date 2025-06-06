# Velociraptor Collector Manager

## Project Overview

The Velociraptor Collector Manager was developed to solve critical challenges in Velociraptor artifact development and deployment workflows. It serves as a comprehensive testing and automation platform for Velociraptor artifacts, addressing several key needs in incident response and digital forensics teams:

### Key Problems Solved

1. **Artifact Testing and Validation**:
   - Test artifacts during development across different OS versions and environments
   - Catch potential issues before deployment in incident response engagements
   - Validate artifact behavior and output across different system configurations
   - Prevent deployment of broken or malfunctioning artifacts to clients

2. **Team Collaboration and Standardization**:
   - Pull artifacts directly from a central Velociraptor server used by the entire team
   - Maintain consistency in artifact versions across the team
   - Eliminate collaboration issues and version mismatches
   - Share and test artifacts in a standardized environment

3. **Golden Profile Management**:
   - Create and maintain tested, reliable artifact combinations (profiles)
   - Ensure consistent collector behavior across different deployments
   - Test profiles thoroughly before client deployment
   - Document and track successful artifact combinations

4. **Automation and Efficiency**:
   - Automate the entire artifact testing workflow
   - Streamline collector building and deployment
   - Provide a user-friendly web interface for artifact management
   - Reduce manual effort in testing and validation

### Core Features

The tool automates several critical tasks:
1. Creating and managing artifact specifications
2. Building and deploying collectors to target systems
3. Executing collections remotely
4. Processing and standardizing collected data
5. Enriching data with system information and timestamps
6. Validating and formatting results for further analysis

### Use Cases

1. **Development Testing**:
   ```
   - Test new artifacts during development
   - Validate modifications to existing artifacts
   - Debug artifact issues in controlled environments
   ```

2. **Pre-Deployment Validation**:
   ```
   - Test collectors before client deployment
   - Validate artifact behavior on specific OS versions
   - Ensure reliable data collection
   ```

3. **Profile Creation**:
   ```
   - Build and test artifact combinations
   - Create standardized collection profiles
   - Document successful configurations
   ```

4. **Team Collaboration**:
   ```
   - Share tested artifacts across the team
   - Maintain consistent artifact versions
   - Centralize artifact management
   ```

This automation significantly reduces the risk of deploying untested artifacts in critical incident response.

## Directory Structure

The project uses several directories for different purposes:

- `runtime/`: Temporary storage for incoming collection data and ZIP files
  - Used as the default input directory for raw collection files
  - Cleaned automatically before each new operation

- `runtime_zip/`: Processed and formatted collection results
  - Contains extracted and processed data in a standardized format
  - Maintains the original collection structure with added enrichments

- `collectors/`: Storage for built Velociraptor collectors
  - Houses generated collector executables
  - Named according to their artifact specifications

- `specs/`: Artifact specification files
  - Contains YAML specifications for artifacts
  - Used to generate collectors

- `binaries/`: Velociraptor binary files
  - Contains the Velociraptor executable
  - Used for building collectors

- `config/`: Configuration files
  - Server configuration
  - Environment settings
  - Artifact templates


## Usage

The collector manager can be used either through command line or web interface:

### Web Interface

To start the web interface:
```bash
python web_interface.py
```

The web interface provides:
- Easy-to-use GUI for all collector manager operations
- Real-time progress monitoring
- Drag-and-drop file upload
- Visual representation of processing results
- Interactive artifact selection
- Configurable processing options

Default web interface settings:
- URL: http://localhost:5000
- Port: 5000 (configurable)

### Command Line Interface

The collector manager supports multiple modes of operation and can be run with various options:

```bash
python collector_manager.py --mode [mode] [options]
```

### Available Modes

- `batch`: Process multiple artifacts in batch mode
- `individual`: Process artifacts one by one
- `windows_test`: Test Windows connectivity
- `process_zip`: Process collection ZIP files

### Command Options

1. Mode Selection:
```bash
--mode {batch|individual|windows_test|process_zip}
```

2. Artifact Processing:
```bash
--artifacts "artifact1,artifact2,..."  # Comma-separated list of artifacts to process
--build                               # Build collectors for artifacts
```

3. ZIP Processing (for process_zip mode):
```bash
--input-dir PATH    # Directory containing zip files to process (defaults to "runtime")
--output-dir PATH   # Directory to save processed files (defaults to "runtime_zip")
```

### Examples

1. Process ZIP files with default directories:
```bash
python collector_manager.py --mode process_zip
```
This will:
- Read ZIP files from the "runtime" directory
- Save processed files to the "runtime_zip" directory

2. Process ZIP files with custom directories:
```bash
python collector_manager.py --mode process_zip --input-dir "C:\my_zips" --output-dir "C:\processed_results"
```

3. Process specific artifacts in batch mode:
```bash
python collector_manager.py --mode batch --artifacts "Windows.System.HostsFile,Windows.Network.NetstatEnriched"
```

4. Process artifacts and build collectors:
```bash
python collector_manager.py --mode batch --artifacts "Windows.System.HostsFile" --build
```

## Requirements

### General Requirements
- Python 3.x
- Windows environment for collector operations
- Required Python packages (see requirements.txt)

### Web Interface Additional Requirements
- Flask
- Flask-SocketIO
- Werkzeug
- eventlet

## Configuration

### Web Interface Configuration
The web interface can be configured through environment variables:
```bash
WINRM_HOST_WIN10=192.168.1.1
WINRM_HOST_WIN11=192.168.1.1
WINRM_HOST_WINServer12=192.168.1.1
WINRM_HOST_WINServer16=192.168.1.1
WINRM_HOST_WINServer19=192.168.1.1
WINRM_HOST_WINServer22=192.168.1.1
WINRM_HOST_WINServer25=192.168.1.1
WINRM_USERNAME=administrator
WINRM_PASSWORD=PASSWORDHERE
SSH_PORT=22
COLLECTOR_FILE=./datastore/Collector_velociraptor-v0.72.4-windows-amd64.exe
VELO_DATASTORE=./datastore/
VELO_SERVER_CONFIG=./datastore/server.config.yaml
VELO_BINARY_PATH=./binaries/velociraptor-v0.72.4-windows-amd64.exe
ARTIFACT_TEMPLATE_PATH=./specs/test.yaml
```

### Command Line Configuration
The command line interface uses the following default directories:
- `runtime/`: Default input directory for ZIP files
- `runtime_zip/`: Default output directory for processed files
- `collectors/`: Directory for built collectors
- `specs/`: Directory for artifact specifications


## Output Format

#### When processing ZIP files, the tool will:
- Extract all ZIP files from the input directory
- Process and validate the contents
- Add system information and timestamps
- Save the processed results to the output directory
- Clean up temporary files and indices

#### Each JSON file contains:
- Original artifact data
- Added system information
- Standardized timestamps
- Source type identification
- Additional metadata

## Operating System Compatibility

⚠️ Important Notes:
- This project was developed and tested on Windows
- Limited testing on Linux and macOS
- Known compatibility issues:
  - Windows-style file paths (e.g., C:\path\to\file)
- If running on Linux/macOS, expect to modify paths and some functionality
