
# Command line
.\binaries\velociraptor-v0.72.4-windows-amd64.exe collector --datastore .\datastore\ > .\specs\test.yaml

rm .\datastore\Collector_velociraptor-v0.72.4-windows-amd64.exe
## Option 1
.\binaries\velociraptor-v0.72.4-windows-amd64.exe collector --datastore .\datastore\ .\specs\test.yaml
## Option 2: Pull custom Artifacts from server after uploading them
### Create a web server
.\binaries\velociraptor-v0.72.4-windows-amd64.exe GUI --datastore .\datastore\
### Creater a collector
.\binaries\velociraptor-v0.72.4-windows-amd64.exe --config .\datastore\server.config.yaml collector .\specs\test.yaml


