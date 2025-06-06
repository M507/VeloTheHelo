# Velociraptor Collector Manager

A tool for managing and processing Velociraptor collectors and their outputs.

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

## Output Structure

When processing ZIP files, the tool will:
1. Extract all ZIP files from the input directory
2. Process and validate the contents
3. Add system information and timestamps
4. Save the processed results to the output directory
5. Clean up temporary files and indices

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
PORT=8080              # Change the web server port (default: 5000)
HOST=0.0.0.0          # Change the host binding (default: localhost)
DEBUG=True            # Enable debug mode (default: False)
UPLOAD_FOLDER=uploads # Change upload directory (default: runtime)
```

You can also create a `.env` file in the project root with these settings.

### Command Line Configuration
The command line interface uses the following default directories:
- `runtime/`: Default input directory for ZIP files
- `runtime_zip/`: Default output directory for processed files
- `collectors/`: Directory for built collectors
- `specs/`: Directory for artifact specifications

## Processing Features

The tool provides the following processing features:
1. ZIP File Processing:
   - Extraction and validation
   - System information enrichment
   - Timestamp standardization
   - Index file cleanup

2. Artifact Collection:
   - Multiple artifact support
   - Collector building
   - Remote execution
   - Result gathering

3. Data Enhancement:
   - Automatic timestamp conversion
   - System information integration
   - Source type identification
   - JSON validation and formatting

## Output Format

Processed files maintain the following structure:
```
output_directory/
├── Collection--hostname--timestamp/
│   ├── results/
│   │   ├── artifact1.json
│   │   ├── artifact2.json
│   │   └── ...
│   └── logs/
└── ...
```

Each JSON file contains:
- Original artifact data
- Added system information
- Standardized timestamps
- Source type identification
- Additional metadata

## Running Modes

### 1. Web Interface Mode
The web interface provides a user-friendly way to:
- Upload and process ZIP files
- Monitor processing progress in real-time
- View and download processed results
- Configure processing options visually
- Handle multiple files simultaneously

### 2. Command Line Mode
```bash
python collector_manager.py --mode [mode] [options]
```