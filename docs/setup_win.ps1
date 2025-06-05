# --- Disable Local Password Policy ---
Write-Output "Disabling local password policy..."

# Export security settings
$cfgPath = "$env:SystemDrive\local.cfg"
secedit /export /cfg $cfgPath

# Modify settings in the file
(Get-Content $cfgPath) `
    -replace 'PasswordComplexity\s*=\s*1', 'PasswordComplexity = 0' `
    -replace 'MinimumPasswordLength\s*=\s*\d+', 'MinimumPasswordLength = 0' `
    | Set-Content $cfgPath

# Apply the changes
secedit /configure /db secedit.sdb /cfg $cfgPath /areas SECURITYPOLICY
Remove-Item $cfgPath -Force

# Set password expiration to unlimited
net accounts /maxpwage:unlimited
net accounts /minpwlen:0

# --- Enable WinRM and Configure Firewall ---
Write-Output "Enabling WinRM and adding firewall rules..."

Enable-PSRemoting -Force
Set-Service -Name WinRM -StartupType Automatic
Enable-NetFirewallRule -DisplayGroup "Windows Remote Management"

# --- Install OpenSSH Server ---
Write-Output "Installing OpenSSH Server..."

# Install OpenSSH features
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start and set OpenSSH to start automatically
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Optional: Allow SSH through firewall
New-NetFirewallRule `
  -Name "OpenSSH-In-TCP" `
  -DisplayName "OpenSSH SSH Inbound" `
  -Enabled True `
  -Direction Inbound `
  -Protocol TCP `
  -Action Allow `
  -LocalPort 22

# Confirm OpenSSH is running
Get-Service sshd
