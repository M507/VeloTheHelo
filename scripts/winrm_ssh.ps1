# Enable WinRM
Write-Host "Enabling WinRM..." -ForegroundColor Cyan
Enable-PSRemoting -Force

# Allow WinRM through firewall
Write-Host "Adding WinRM firewall rules..." -ForegroundColor Cyan
Set-NetFirewallRule -Name "WINRM-HTTP-In-TCP" -Enabled True
Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True
New-NetFirewallRule -DisplayName "Allow WinRM" -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow

# Install OpenSSH Server
Write-Host "Installing OpenSSH Server..." -ForegroundColor Cyan
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start and enable SSH services
Write-Host "Starting and configuring SSH service..." -ForegroundColor Cyan
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'

# Allow SSH through firewall
Write-Host "Adding SSH firewall rule..." -ForegroundColor Cyan
New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22

Write-Host "WinRM and SSH are now configured and running." -ForegroundColor Green
