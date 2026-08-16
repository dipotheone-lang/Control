> **Superseded for day-to-day use by `docs/RUNBOOK.md`**, which carries the current commands end to end. This file is kept for the background it records.

# Phase 0 Runbook — connecting the mailbox and folders

This is the step-by-step to take Control from repository to a live
Phase 0 discovery run. It has two tracks:

- **Track A — folders and archives (no tenant work, start today):**
  run Stages A–B against `UB_ROOT` on a machine that can see the
  company files.
- **Track B — the mailbox (Graph):** provision the Entra app so
  Control can read `control@ubcsis.com` live. Required for the
  operational phases; useful in Phase 0 for mailbox-side history.

> **Where to run this.** On a company-controlled machine that can see
> `UB_ROOT` — the charter assumes company hardware (§5.1, §12.2).
> Company mail archives contain personal data (PDPL 151/2020) and
> NDA-covered client material (§12.1): do **not** upload archives to
> third-party services or cloud sessions to "run discovery there."
> The engine comes to the data; the data does not go to the engine.

---

## Track A — folders and archives

### A1. Install (once)

On the machine (Windows is fine; Python 3.11+):

```bash
git clone https://github.com/dipotheone-lang/Control
cd Control
python -m pip install -e ".[dev]"
python -m pytest          # should report all tests passing
```

### A2. Choose the roots

- `UB_ROOT` = the top of the United Brothers folder tree (O-09 — this
  run is how you confirm it).
- `CONTROL_ROOT` = `<UB_ROOT>/CONTROL`. Create it and copy this repo's
  `config/` into it (or point `--control-root` at a checkout).
- The engine writes **only** inside `CONTROL_ROOT` (§1.13). Everything
  else is read-only by construction.

```powershell
$env:UB_ROOT      = "D:\UnitedBrothers"
$env:CONTROL_ROOT = "D:\UnitedBrothers\CONTROL"
```

### A3. Stage the mail archives

Stage A parses `.eml` and `.mbox` natively and indexes `.pst`/`.ost`/`.msg`.

- **Close Outlook**, then export mailboxes to `.pst`
  (Outlook → File → Open & Export → Import/Export → Export to a file).
  Put exports anywhere under `UB_ROOT`.
- An `.ost` is locked while Outlook runs and is skipped with a note —
  export to `.pst` instead.
- To fully parse `.pst` content install `libpff`/`pypff`; without it
  the archives are indexed and listed in `DISCOVERY-LIMITATIONS.md`
  (an honest gap, not a failure).
- For the **Stage H numbers** (the O-05 decision), export `sales@` and
  `procure@` as well — this needs a one-time, CEO-authorised admin
  export (§6 Stage H fallback).

### A4. Run discovery

```bash
python -m control startup    --control-root %CONTROL_ROOT% --ub-root %UB_ROOT%
python -m control discovery  --control-root %CONTROL_ROOT% --ub-root %UB_ROOT%
python -m control verify     --control-root %CONTROL_ROOT%
```

Outputs land in `CONTROL_ROOT/discovery/`:
`mail-archive-index.csv`, `mail-messages.jsonl`, `file-inventory.csv`,
`DISCOVERY-LIMITATIONS.md`.

**What is automated today: Stages A and B.** Stages C–J (forms and
contract extraction, obligation inference, baselines, the eleven
deliverables) are the next tooling increment and partly human work —
raise them as the next build step once A–B output exists.

---

## Track B — the mailbox (Microsoft Graph)

Needs a Microsoft 365 admin. ~30 minutes.

### The scripted path (recommended)

`scripts/provision-graph.ps1` performs B1–B5 in one run — app
registration, application permissions with admin consent, certificate
creation and upload, encrypted PFX export with the password stored in
Windows Credential Manager, the mandatory Application Access Policy
with both Granted and Denied verification, and a `graph-env.ps1`
environment file. Then:

```powershell
. .\scripts\out\graph-env.ps1
python .\scripts\graph_smoketest.py     # read-only: prints counts, sends nothing
```

**Key handling, stated honestly:** MSAL for Python must hold the
private key material, so a Windows-store *non-exportable* key cannot
be used directly. The §5.1-compliant compromise the script implements:
the key exists only inside an encrypted PFX; the password lives in
Windows Credential Manager (service `UBCSIS-Control`, user `pfx`),
never in a file; and the temporary store copy of the key is deleted
after export. Rotation is a re-run of the script.

The manual steps below are the same operations for auditability.

### B1. Register the Entra app

Portal → Entra ID → App registrations → **New registration**
- Name: `UBCSIS-Control`
- Supported account types: single tenant
- Note the **Application (client) ID** and **Directory (tenant) ID**

### B2. API permissions (Application, not Delegated)

Add → Microsoft Graph → **Application permissions**:
`Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `MailboxSettings.Read`
→ **Grant admin consent**.

### B3. Certificate — never a client secret (§5.1)

On the machine that will run Control (PowerShell as the run user):

```powershell
$cert = New-SelfSignedCertificate -Subject "CN=UBCSIS-Control" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -KeyExportPolicy NonExportable -KeySpec Signature `
  -KeyLength 2048 -NotAfter (Get-Date).AddYears(2)
Export-Certificate -Cert $cert -FilePath control-public.cer
$cert.Thumbprint
```

Portal → the app → Certificates & secrets → **Upload certificate**
(`control-public.cer`). Diary the 2-year rotation.

### B4. Application Access Policy — mandatory (§5.1)

Scope the app to the single mailbox (Exchange Online PowerShell):

```powershell
Connect-ExchangeOnline
New-DistributionGroup -Name "Control-Allowed" -Type Security `
  -Members control@ubcsis.com
New-ApplicationAccessPolicy -AppId <client-id> `
  -PolicyScopeGroupId Control-Allowed-group-address -AccessRight RestrictAccess `
  -Description "Control: restrict to control@ mailbox only"
Test-ApplicationAccessPolicy -AppId <client-id> -Identity control@ubcsis.com   # Granted
Test-ApplicationAccessPolicy -AppId <client-id> -Identity ahmed@ubcsis.com     # Denied
```

Both test results matter: the second proves the blast radius is one
mailbox.

### B5. Environment (§5.1)

```powershell
$env:GRAPH_TENANT_ID       = "<tenant-id>"
$env:GRAPH_CLIENT_ID       = "<client-id>"
$env:GRAPH_CERT_THUMBPRINT = "<thumbprint>"
$env:CONTROL_MAILBOX       = "control@ubcsis.com"
```

`GraphTransport` (in `src/control/transport.py`) authenticates by
certificate, honours `Retry-After`, and treats any incomplete sweep as
a **FAILED cycle** — it will not record absences from a partial view.

### B6. Verify the connection

A read-only smoke test (fetches unread, sends nothing):

```python
from control.transport import GraphTransport
# private key stays in the certificate store; export a PEM only if your
# MSAL setup requires it, and keep it out of the repository
t = GraphTransport("control@ubcsis.com", tenant_id=..., client_id=...,
                   certificate_pem=..., certificate_thumbprint=...)
print(len(t.fetch_unprocessed()), "unread messages visible")
```

---

## The gates you are walking toward

Phase 0 ends when (§6): the CEO approves the obligation register,
confirms the confidential scope (`config/confidential.yaml`, O-04),
and takes the shared-mailbox decision (O-05, on Stage H numbers).
Also on the Phase 0 gate: reporting lines (O-01), authority matrix
(O-02), and the statutory calendar verified with the tax advisor
(O-03). The full list is charter Appendix B.

Until every gate closes, `RUN_MODE=DISCOVERY` and the engine sends
nothing — by design.
