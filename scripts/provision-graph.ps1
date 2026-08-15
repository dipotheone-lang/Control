<#
.SYNOPSIS
  One-time tenant provisioning for Control (charter §5.1) — Track B.

  Run as a Microsoft 365 admin, on the machine that will run Control:
    1. Registers the UBCSIS-Control Entra application (single tenant)
    2. Adds the four Graph APPLICATION permissions and grants consent
    3. Creates the certificate, uploads the public key to the app,
       exports an encrypted PFX, and stores the password in Windows
       Credential Manager via Python keyring (never in a file, §5.1)
    4. Creates the security group and the MANDATORY Application Access
       Policy restricting the app to the single control mailbox, then
       verifies both Granted and Denied
    5. Writes graph-env.ps1 with the environment values

.NOTES
  Requires: Microsoft.Graph.Authentication (Connect-MgGraph,
  Invoke-MgGraphRequest), ExchangeOnlineManagement, and the Control
  python environment on PATH (for keyring storage).

  Directory objects are read and written through Invoke-MgGraphRequest
  (raw Graph REST) rather than the typed Get-Mg* cmdlets: their -Filter
  handling varies across SDK versions and fails with BadRequest on some.

  The script is IDEMPOTENT — re-running after a failure is safe and is
  the supported way to resume.
#>
param(
    [string]$Mailbox = "control@ubcsis.com",
    [string]$AppName = "UBCSIS-Control",
    [string]$OutDir  = "$PSScriptRoot\out",
    [int]$CertYears  = 2,
    [string]$DeniedProbe = "ahmed@ubcsis.com"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$GraphV1 = "https://graph.microsoft.com/v1.0"
$GraphResourceId = "00000003-0000-0000-c000-000000000000"   # Microsoft Graph
$AppRoles = [ordered]@{                                     # application permissions
    "Mail.Read"            = "810c84a8-4a9e-49e6-bf7d-12d183f40d01"
    "Mail.ReadWrite"       = "e2a3a72e-5f79-4c64-b1b1-878b674786c9"
    "Mail.Send"            = "b633e1c5-b582-4048-a93e-9f11b44c7e96"
    "MailboxSettings.Read" = "40f97065-369a-49f4-947c-6a255697ae91"
}

function Get-GraphCollection {
    param([string]$Path, [string]$Filter)
    $uri = "$GraphV1/$Path"
    if ($Filter) { $uri += "?`$filter=" + [uri]::EscapeDataString($Filter) }
    $response = Invoke-MgGraphRequest -Method GET -Uri $uri
    return @($response.value)
}

# ---- 1. App registration --------------------------------------------------
Write-Host "== Step 1: application registration ==" -ForegroundColor Cyan
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All" -NoWelcome
$tenantId = (Get-MgContext).TenantId
if (-not $tenantId) { throw "Connect-MgGraph did not establish a tenant context" }
Write-Host "Tenant: $tenantId"

$app = Get-GraphCollection -Path "applications" -Filter "displayName eq '$AppName'" |
    Select-Object -First 1

if (-not $app) {
    $body = @{
        displayName            = $AppName
        signInAudience         = "AzureADMyOrg"
        requiredResourceAccess = @(@{
            resourceAppId  = $GraphResourceId
            resourceAccess = @($AppRoles.Values | ForEach-Object { @{ id = $_; type = "Role" } })
        })
    }
    $app = Invoke-MgGraphRequest -Method POST -Uri "$GraphV1/applications" -Body $body
    Write-Host "Created application. AppId: $($app.appId)"
    Start-Sleep -Seconds 10          # directory replication
} else {
    Write-Host "Application already exists. AppId: $($app.appId)"
}
$appObjectId = $app.id
$appId       = $app.appId

$sp = Get-GraphCollection -Path "servicePrincipals" -Filter "appId eq '$appId'" |
    Select-Object -First 1
if (-not $sp) {
    $sp = Invoke-MgGraphRequest -Method POST -Uri "$GraphV1/servicePrincipals" `
        -Body @{ appId = $appId }
    Write-Host "Created service principal."
    Start-Sleep -Seconds 10
}
$spId = $sp.id

# ---- 2. Admin consent (app role assignments) ------------------------------
Write-Host "== Step 2: application permissions and consent ==" -ForegroundColor Cyan
$graphSp = Get-GraphCollection -Path "servicePrincipals" -Filter "appId eq '$GraphResourceId'" |
    Select-Object -First 1
if (-not $graphSp) { throw "Microsoft Graph service principal not found in this tenant" }

$existing = Get-GraphCollection -Path "servicePrincipals/$spId/appRoleAssignments"
foreach ($name in $AppRoles.Keys) {
    $roleId = $AppRoles[$name]
    if ($existing | Where-Object { $_.appRoleId -eq $roleId }) {
        Write-Host "  $name already granted"
        continue
    }
    Invoke-MgGraphRequest -Method POST `
        -Uri "$GraphV1/servicePrincipals/$spId/appRoleAssignments" `
        -Body @{ principalId = $spId; resourceId = $graphSp.id; appRoleId = $roleId } | Out-Null
    Write-Host "  granted $name"
}

# ---- 3. Certificate -------------------------------------------------------
# MSAL (Python) must hold the private key, so the key is exported ONCE into
# an encrypted PFX; the password goes to Windows Credential Manager, never
# to a file (§5.1). Rotate by re-running this script.
Write-Host "== Step 3: certificate ==" -ForegroundColor Cyan
$pfxPath = Join-Path $OutDir "control-graph.pfx"
if (Test-Path $pfxPath) {
    Write-Host "PFX already present at $pfxPath - keeping it (delete to rotate)."
} else {
    $cert = New-SelfSignedCertificate -Subject "CN=$AppName" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeySpec Signature -KeyLength 2048 -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears($CertYears)

    Add-Type -AssemblyName System.Web
    $pfxPassword = [System.Web.Security.Membership]::GeneratePassword(32, 8)
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath `
        -Password (ConvertTo-SecureString $pfxPassword -AsPlainText -Force) | Out-Null

    python -c "import keyring,sys; keyring.set_password('UBCSIS-Control','pfx',sys.argv[1])" $pfxPassword
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "keyring storage failed. Run before the smoke test:"
        Write-Warning "  `$env:GRAPH_PFX_PASSWORD = '<password printed below>'"
        Write-Host   "PFX password (store it in a password manager now): $pfxPassword"
    } else {
        Write-Host "PFX password stored in Windows Credential Manager (UBCSIS-Control/pfx)."
    }

    # upload the public key to the app registration
    $keyCredential = @{
        type  = "AsymmetricX509Cert"
        usage = "Verify"
        key   = [System.Convert]::ToBase64String($cert.RawData)
    }
    Invoke-MgGraphRequest -Method PATCH -Uri "$GraphV1/applications/$appObjectId" `
        -Body @{ keyCredentials = @($keyCredential) } | Out-Null
    Write-Host "Certificate uploaded. Thumbprint: $($cert.Thumbprint)"
    Write-Host "Expires $($cert.NotAfter.ToShortDateString()) - diary the rotation."

    # the PFX is now the single encrypted home of the key
    Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -Force
    Start-Sleep -Seconds 10
}

# ---- 3b. Environment file -------------------------------------------------
# Written BEFORE the Exchange stage: every value it needs is known now, and
# an Exchange failure must not cost the work already done in Entra.
$envFile = Join-Path $OutDir "graph-env.ps1"
@"
# Control §5.1 environment - dot-source before running:  . "$envFile"
`$env:GRAPH_TENANT_ID = "$tenantId"
`$env:GRAPH_CLIENT_ID = "$appId"
`$env:GRAPH_PFX_PATH  = "$pfxPath"
`$env:CONTROL_MAILBOX = "$Mailbox"
# PFX password: Windows Credential Manager, service UBCSIS-Control, user pfx
"@ | Set-Content -Path $envFile -Encoding UTF8
Write-Host "Environment file written: $envFile"

# ---- 4. Application Access Policy (MANDATORY, §5.1) -----------------------
Write-Host "== Step 4: Application Access Policy ==" -ForegroundColor Cyan
Connect-ExchangeOnline -ShowBanner:$false

$groupName = "Control-Allowed"
$group = Get-DistributionGroup -Identity $groupName -ErrorAction SilentlyContinue
if (-not $group) {
    $group = New-DistributionGroup -Name $groupName -Type Security -Members $Mailbox
    Write-Host "Created security group $groupName - waiting for provisioning..."
    Start-Sleep -Seconds 30
    $group = Get-DistributionGroup -Identity $groupName
}

$policy = Get-ApplicationAccessPolicy -ErrorAction SilentlyContinue |
    Where-Object { $_.AppId -eq $appId }
if (-not $policy) {
    New-ApplicationAccessPolicy -AppId $appId `
        -PolicyScopeGroupId $group.PrimarySmtpAddress -AccessRight RestrictAccess `
        -Description "Control: restrict to $Mailbox only" | Out-Null
    Write-Host "Application Access Policy created."
} else {
    Write-Host "Application Access Policy already present."
}

$granted = Test-ApplicationAccessPolicy -AppId $appId -Identity $Mailbox
$denied  = Test-ApplicationAccessPolicy -AppId $appId -Identity $DeniedProbe
Write-Host ""
Write-Host "Policy test  $Mailbox : $($granted.AccessCheckResult)   (must be Granted)"
Write-Host "Policy test  $DeniedProbe : $($denied.AccessCheckResult)   (must be Denied)"
if ($granted.AccessCheckResult -ne "Granted" -or $denied.AccessCheckResult -ne "Denied") {
    Write-Warning "ACCESS POLICY NOT PROVEN YET. Policies can take ~30 minutes to apply."
    Write-Warning "Re-run this script (safe) or re-test before running Control."
}

# ---- 5. Summary -----------------------------------------------------------
Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Tenant : $tenantId"
Write-Host "  AppId  : $appId"
Write-Host "  PFX    : $pfxPath"
Write-Host "  Env    : $envFile"
Write-Host ""
Write-Host "Next:  . `"$envFile`"  ;  python scripts\graph_smoketest.py"
