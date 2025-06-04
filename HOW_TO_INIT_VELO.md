
# Command line
.\binaries\velociraptor-v0.72.4-windows-amd64.exe collector --datastore .\datastore\ > .\specs\test.yaml

rm .\datastore\Collector_velociraptor-v0.72.4-windows-amd64.exe
.\binaries\velociraptor-v0.72.4-windows-amd64.exe collector --datastore .\datastore\ .\specs\test.yaml

# Server
#.\binaries\velociraptor-v0.72.4-windows-amd64.exe GUI --datastore .\datastore\

