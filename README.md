# VeloTheHelo

This is a development and testing platform. It makes working with Velociraptor artifacts way less painful. It helps you test, validate, and deploy artifacts without losing your mind.

Traditional methods of testing artifacts one by one through the Velociraptor GUI or command line can be time-consuming and error-prone. This platform streamlines the process by providing a one-interface environment where artifacts can be systematically tested, validated, and managed with version control.

The "Individual Testing" tab allows you to focus on single artifacts during development or troubleshooting. This is useful when you're creating new artifacts, debugging collection issues, or fine-tuning artifact parameters and editing naming conventions. The platform ensures your artifacts work reliably across different Windows versions (7, 11, Server 2012, 2022, etc.), service pack levels, and system configurations, helping you identify compatibility issues before deployment.

The "Profile Testing" tab enables you to validate groups of artifacts that you want to use together for specific investigation scenarios. For example, you can create and test profiles for IR engagements, CA engagements, etc. This helps with workflows where multiple artifacts need to work together. Testing artifacts in combination rather than individually helps identify resource conflicts, timing issues, and dependencies between artifacts that wouldn't be apparent when testing them separately. 


#### The deployment windows:
![The deployment windows ](screenshots/1.png)


#### Status  of executions + the first two lines of each output file:

![Stat windows](screenshots/2.png)


## What's the Point?

- **Test Your Artifacts**: Make sure they work across different OS versions before you deploy them
- **Team Stuff**: Pull artifacts from a central server so everyone's on the same page
- **Profile Management**: Create and test reliable artifact combinations
- **Automation FTW**: Stop doing repetitive tasks manually

## What Can It Do?

1. Build and deploy collectors
2. Run collections remotely
3. Process and standardize data
4. Add system info and timestamps for best analysis experience
5. Make sure everything is formatted nicely

## Testing Approaches

### Individual Testing vs Profiles

#### Individual Testing 

Benefits for developers:
- Allows you to find which artifacts hang forever
- Provides clearer error messages for specific artifacts
- Easier to debug and trace issues
- Lets you focus on one artifact's behavior at a time

#### Profile Testing 
Benefits for developers:
- Tests how artifacts interact with each other
- Validates resource usage when running multiple collectors
- Ensures artifacts don't conflict or interfere
- Better represents real-world deployment scenarios
- Perfect for final testing before production

## Project Structure

```
runtime/      -> Temp storage for collection data
runtime_zip/  -> Processed results
collectors/   -> Built Velociraptor collectors
specs/        -> Artifact specs (YAML)
binaries/     -> Velociraptor executables
config/       -> Config files
profiles/      -> profiles files
```

## Profiles Structure
Profiles are JSON files that define groups of artifacts to be tested together. Ideally, these profiles should match your custom "CreateCollector" server artifact on Velociraptor. Each profile contains:
- `name`: A unique identifier for the profile
- `description`: Purpose and scope of the profile
- `artifacts`: List of Velociraptor artifacts to be tested

Example of a profile:
```json
{
    "name": "IR_Profile",
    "description": "Common artifacts for Client A",
    "artifacts": [
        "Custom.HH.Windows.MFT",
        "Custom.HH.Windows.USN",
        "Custom.HH.Windows.Prefetch",
        "Custom.HH.Windows.Amcache",
        "Custom.HH.Windows.DownloadedFiles"
    ]
}
```

## Getting Started

### Web Interface
```bash
python web_interface.py --ssl
```

Visit https://localhost:5000 and you're good to go.


## Requirements

- Python 3.x
- Windows (for collector operations)
- Required Python packages (check requirements.txt)
- For web stuff: Flask, Flask-SocketIO, Werkzeug, eventlet

## Config

### Web Interface Configuration
The web interface can be configured through environment variables:
```bash
WINRM_HOST_WIN10=192.168.1.1
WINRM_HOST_WIN11=192.168.1.2
WINRM_HOST_WINServer12=192.168.1.3
WINRM_HOST_WINServer16=192.168.1.4
WINRM_HOST_WINServer19=192.168.1.5
WINRM_HOST_WINServer22=192.168.1.6
WINRM_HOST_WINServer25=192.168.1.7
WINRM_USERNAME=administrator
WINRM_PASSWORD=PASSWORDHERE
SSH_PORT=22
COLLECTOR_FILE=./datastore/Collector_velociraptor-v0.72.4-windows-amd64.exe
VELO_DATASTORE=./datastore/
VELO_SERVER_CONFIG=./datastore/server.config.yaml
VELO_BINARY_PATH=./binaries/velociraptor-v0.72.4-windows-amd64.exe
ARTIFACT_TEMPLATE_PATH=./specs/test.yaml
```

## Remote Host Requirements (WINRM_HOST_*)
The platform requires remote access to test hosts for executing, pulling, and pushing files:

- **Windows Hosts**: 
  - WinRM and SSH must be enabled and properly configured
  - Default ports (5985 for HTTP, 5986 for HTTPS, and 22) must be accessible
  - Appropriate credentials must be configured and be the same across all remote hosts. We recommend using Terraform to deploy the remote hosts with the same configuration

## OS Support

This platform primarily runs on Windows. It might work on Linux/macOS, but you'll probably need to tweak some things (especially those Windows-style paths).

