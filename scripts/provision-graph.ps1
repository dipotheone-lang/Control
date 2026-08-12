<#
.SYNOPSIS
  One-time tenant provisioning for Control (charter §5.1) — Track B.

  Run as a Microsoft 365 admin, on the machine that will run Control:
    1. Registers the UBCSIS-Control Entra application (single tenant)
    2. Adds the four Graph APPLICATION permissions and grants consent
    3. Creates the certificate, uploads the public key to the app,
       exports an encrypted PFX, and stores the password in Windows
       Credential Manager via Python keyring (never in a file, §5.1)
    4. Creates the mail-enabled security group and the MANDATORY
       Application Access Policy restricting the app to the single
       control mailbox, then verifies both Granted and Denied
    5. Writes graph-env.ps1 with the environment values

.NOTES
  Requires: Microsoft.Graph.Applications, ExchangeOnlineManagement,
  and the Control python environment on PATH (for keyring storage).
  Verify the permission GUIDs against the portal if Microsoft ever
  rotates them — they are the well-known Graph application role IDs.
#>
param(
    [string]$Mailbox = "control@ubcsis.com",
    [string]$AppName = "UBCSIS-Control",
    [string]$OutDir  = "$PSScriptRoot\out",
    [int]$CertYears  = 2
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# ---- 1. App registration --------------------------------------------------
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All" -NoWelcome

$graphResourceId = "00000003-0000-0000-c000-000000000000"   # Microsoft Graph
$appRoles = @{                                              # application permissions
    "Mail.Read"            = "810c84a8-4a9e-49e6-bf7d-12d183f40d01"
    "Mail.ReadWrite"       = "e2a3a72e-5f79-4c64-b1b1-878b674786c9"
    "Mail.Send"            = "b633e1c5-b582-4048-a93e-9f11b44c7e96"
    "MailboxSettings.Read" = "40f97065-369a-49f4-947c-6a255697ae91"
}

$requiredAccess = @{
    ResourceAppId  = $graphResourceId
    ResourceAccess = @($appRoles.Values | ForEach-Object { @{ Id = $_; Type = "Role" } })
}

$app = Get-MgApplication -Filter "displayName eq '$AppName'" | Select-Object -First 1
if (-not $app) {
    $app = New-MgApplication -DisplayName $AppName -SignInAudience "AzureADMyOrg" `
        -RequiredResourceAccess @($requiredAccess)
    Write-Host "Created application $($app.AppId)"
} else {
    Write-Host "Application already exists: $($app.AppId)"
}

$sp = Get-MgServicePrincipal -Filter "appId eq '$($app.AppId)'" | Select-Object -First 1
if (-not $sp) { $sp = New-MgServicePrincipal -AppId $app.AppId }

# ---- 2. Admin consent (app role assignments) ------------------------------
$graphSp = Get-MgServicePrincipal -Filter "appId eq '$graphResourceId'" | Select-Object -First 1
$existing = Get-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id
foreach ($name in $appRoles.Keys) {
    $roleId = $appRoles[$name]
    if ($existing | Where-Object { $_.AppRoleId -eq $roleId }) { continue }
    New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id `
        -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $roleId | Out-Null
    Write-Host "Granted $name"
}

# ---- 3. Certificate -------------------------------------------------------
# MSAL (Python) must hold the private key, so the key is exported ONCE into
# an encrypted PFX; the password goes to Windows Credential Manager, never
# to a file (§5.1). Delete no files from $OutDir by hand — rotate instead.
$cert = New-SelfSignedCertificate -Subject "CN=$AppName" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeySpec Signature -KeyLength 2048 -KeyExportPolicy Exportable `
    -NotAfter (Get-Date).AddYears($CertYears)

Add-Type -AssemblyName System.Web
$pfxPassword = [System.Web.Security.Membership]::GeneratePassword(32, 8)
$pfxPath = Join-Path $OutDir "control-graph.pfx"
Export-PfxCertificate -Cert $cert -FilePath $pfxPath `
    -Password (ConvertTo-SecureString $pfxPassword -AsPlainText -Force) | Out-Null

# store password in Credential Manager via the engine's python + keyring
python -c "import keyring; keyring.set_password('UBCSIS-Control','pfx','$pfxPassword')"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "keyring storage failed - set GRAPH_PFX_PASSWORD manually and do NOT commit it anywhere."
}

# upload public key to the app
$keyCredential = @{
    Type  = "AsymmetricX509Cert"
    Usage = "Verify"
    Key   = $cert.RawData
}
Update-MgApplication -ApplicationId $app.Id -KeyCredentials @($keyCredential)
Write-Host "Certificate uploaded. Thumbprint: $($cert.Thumbprint) (expires $($cert.NotAfter.ToShortDateString()) - diary the rotation)"

# remove the exportable private key from the store: the PFX is now the
# single, encrypted home of the key
Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)"

# ---- 4. Application Access Policy (MANDATORY, §5.1) -----------------------
Connect-ExchangeOnline -ShowBanner:$false
$groupName = "Control-Allowed"
$group = Get-DistributionGroup -Identity $groupName -ErrorAction SilentlyContinue
if (-not $group) {
    $group = New-DistributionGroup -Name $groupName -Type Security -Members $Mailbox
    Write-Host "Created security group $groupName"
}
$policy = Get-ApplicationAccessPolicy | Where-Object { $_.AppId -eq $app.AppId }
if (-not $policy) {
    New-ApplicationAccessPolicy -AppId $app.AppId `
        -PolicyScopeGroupId $group.PrimarySmtpAddress -AccessRight RestrictAccess `
        -Description "Control: restrict to $Mailbox only" | Out-Null
    Write-Host "Application Access Policy created"
}

$granted = Test-ApplicationAccessPolicy -AppId $app.AppId -Identity $Mailbox
$denied  = Test-ApplicationAccessPolicy -AppId $app.AppId -Identity "ahmed@ubcsis.com"
Write-Host "Policy test for ${Mailbox}: $($granted.AccessCheckResult)   (must be Granted)"
Write-Host "Policy test for ahmed@:    $($denied.AccessCheckResult)   (must be Denied)"
if ($granted.AccessCheckResult -ne "Granted" -or $denied.AccessCheckResult -ne "Denied") {
    Write-Warning "ACCESS POLICY NOT PROVEN - do not run Control until both tests pass. Policies can take ~30 minutes to apply."
}

# ---- 5. Environment file --------------------------------------------------
$tenantId = (Get-MgContext).TenantId
$envFile = Join-Path $OutDir "graph-env.ps1"
@"
# Control §5.1 environment - dot-source before running: . $envFile
`$env:GRAPH_TENANT_ID = "$tenantId"
`$env:GRAPH_CLIENT_ID = "$($app.AppId)"
`$env:GRAPH_PFX_PATH  = "$pfxPath"
`$env:CONTROL_MAILBOX = "$Mailbox"
# PFX password: Windows Credential Manager, service UBCSIS-Control, user pfx
"@ | Set-Content -Path $envFile -Encoding UTF8

Write-Host ""
Write-Host "Done. Next: . $envFile ; python scripts/graph_smoketest.py"
