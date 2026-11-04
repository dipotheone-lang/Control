# AXION AI Team — Session Handoff & New Session Instructions
**Date:** 04-Nov-2026  
**From:** Cloud session `session_01T7L1U2JW3iQTnBTaMbPqzr`  
**To:** New local machine session on Dipo (laptop)  
**Owner:** dipotheone@gmail.com

---

## WHAT THIS FILE IS

This is the complete handoff from a cloud session that researched AXION Egypt and designed its AI team architecture. You are a **new Claude Code session running directly on the laptop** — you have access to the local files, Outlook, and the company folder. Your job is to **complete the discovery** that the cloud session could not finish.

---

## WHAT WE KNOW ABOUT AXION

### Company Identity
- **Full name:** AXION Egypt (exact legal name from commercial register)
- **Type:** Pure trading & supply chain — NOT a contractor. "One-Stop" supply partner.
- **Tagline:** "Powering Industry. Delivering Trust." / "If it exists, we can supply it."
- **HQ:** Suez, Egypt
- **Website:** www.axionegypt.com
- **Relationship to UBCSIS:** Same owner. AXION = supply only. UBCSIS = contracting + supply. Some staff shared (Ghareeb Mahmoud, Donia Ali appear in both).

### Known Mailboxes (axionegypt.com)
| Mailbox | Likely owner |
|---|---|
| info@axionegypt.com | General / Ghareeb Mahmoud |
| sales@axionegypt.com | Sales team |
| donia@axionegypt.com | Donia Ali (Proposals/Tendering) |
| gmahmoud@axionegypt.com | Ghareeb Mahmoud (GM) |
| purchase@axionegypt.com | Procurement |

### Product Divisions (from Company Profile PDF)
1. Industrial & Mechanical (valves, pumps, bearings, pipes, flanges, tools)
2. Electrical & Automation (cables, panels, instruments, motors, sensors)
3. Civil & Construction (steel, cement, insulation, waterproofing, safety)
4. IT, Office & Facility Management

### Current Clients (confirmed)
- IFFCO Egypt
- Solb Misr
- IVL Dhunseri
- Galaxy Chemicals
- Masafi Co.

### Active Pipeline (found in Gmail/Drive)
- Air Cooled Chillers — Trane brand, active quote
- PetroJet — vendor registration in progress
- Kellanova — active opportunity
- Heidelberg Materials — contact made
- Air Liquide — qualification stage

### Documents Found in Google Drive
| Document | Drive ID |
|---|---|
| Company Profile PDF | `1pBtM2LqW34IjL95G0HzkdHd7X_jDt3qa` |
| Product Portfolio PDF | `1yc0uv_MbxmlGBIhIyJ6NIdSKMgdOX-SV` |
| Commercial Register | `1KcFkuKD2rAst3Js__4p1HH4KV8BfNkXr` |
| Tax Card | `1rKDRkcKDsyNTYkW3-AQtrEGJVeqRkniO` |
| VAT Certificate | `1rmhQwe8DjHSGYlsAUmTCkxZkX2bhJzJ3` |
| Bank Details | `1M4u1GVivzprY5-XMMvKJ4zaN9DWdnZ9P` |
| RFQ Register (Google Sheet — EMPTY) | `1dY-IU2zc_TGfB93qIhuCTv5H8xU6WqiIffIwKv8srxM` |

### Previous Claude Code Sessions (read-only, may contain history)
- `session_01T7L1U1rj1biYX7apaPQihv` — labelled "AXION Outreach" (created the RFQ Register sheet)
- `session_01T7L1U2Aij97aPkki9R3E1V`
- `session_01T7L1U4nwdWuUjn6xWomAm7`

---

## LOCAL PATHS ON THIS LAPTOP (Dipo)

```
E:\AXION Co Date 01.02.2026\     ← Main company folder
E:\Outlook Files\                ← Outlook archive files (.pst / .ost / .msg)
E:\UBCSIS Co Date Jan 2026\      ← UBCSIS folder (related company)
E:\Donia Handover\               ← Donia Ali handover files
C:\Users\Lape Top Suez\My Drive\ ← Google Drive local sync
```

---

## YOUR DISCOVERY MISSION

You are running on the laptop. Work through these stages in order. Write your findings to `E:\AXION Co Date 01.02.2026\AI-Discovery\` (create it if it doesn't exist).

### STAGE 1 — Company Folder Survey
Walk `E:\AXION Co Date 01.02.2026\` completely:
- List every file and folder with dates
- Find: quotations, RFQs, POs, supplier lists, client lists, price lists, contracts
- Find: any existing trackers (Excel, Word, PDF)
- Note: duplicates, competing versions, gaps
- **Output:** `AI-Discovery\01-folder-inventory.md`

### STAGE 2 — Outlook Email Analysis
Read the files in `E:\Outlook Files\`:
- Identify all .pst, .ost, .msg, .eml files
- For each mailbox archive found:
  - Count emails by sender/recipient domain
  - Find all emails from/to: clients (IFFCO, Solb Misr, IVL, Galaxy, Masafi, Air Liquide, PetroJet, Kellanova, Heidelberg)
  - Find all RFQs received (subject contains: RFQ, طلب عرض, quotation, offer, سعر, تورد)
  - Find all quotations sent
  - Find unanswered threads (email received, no reply within 48h)
  - Find supplier communications (purchase@, moredars, suppliers)
- **Output:** `AI-Discovery\02-email-analysis.md`

### STAGE 3 — Pipeline Reconstruction
From the emails and folder files, reconstruct the full commercial pipeline:
- Every RFQ received in the last 12 months — client, item, date received, quoted? won/lost?
- Every quotation sent — value (EGP), client, status
- Every active opportunity — stage, next action, owner
- Every supplier used — name, products, contact
- **Output:** `AI-Discovery\03-pipeline-register.md`

### STAGE 4 — Online Presence Research
Search and document:
- LinkedIn page: search "AXION Egypt" or "axionegypt" on LinkedIn
- Facebook page: search "AXION Egypt" on Facebook
- Website: www.axionegypt.com — capture: products listed, contact info, any blog/news
- Google Business profile if any
- Any other platform presence
- **For each:** followers/connections count, last post date, engagement level, content type
- **Output:** `AI-Discovery\04-online-presence.md`

### STAGE 5 — People & Org Chart
From emails and files, confirm:
- Full list of AXION staff (name, role, email, phone if found)
- Who handles what (sales vs procurement vs admin vs technical)
- Which staff are shared with UBCSIS
- Reporting lines
- **Output:** `AI-Discovery\05-people-org.md`

### STAGE 6 — Gap Analysis
Based on everything found, identify:
- What processes exist vs what should exist
- What's tracked vs what's falling through the cracks
- Estimated volume: RFQs/month, quotations/month, orders/month, EGP value
- Biggest revenue risks right now (unanswered RFQs, expiring quotes, lapsed clients)
- **Output:** `AI-Discovery\06-gap-analysis.md`

---

## AI TEAM TO BUILD (from cloud session design)

After completing discovery, build and deploy this team:

### Agent 1 — GM Daily Briefing (gmahmoud@)
**Schedule:** Every day 07:30  
**Delivers:** New RFQs overnight, pipeline status, decisions needed today, quotes expiring this week  
**Tools needed:** Outlook/Graph API access, Google Sheets (RFQ Register)

### Agent 2 — Inbox Sentinel (info@ + sales@)
**Schedule:** Every 30 min  
**Job:** Classify inbound mail → route RFQs to Sourcing Agent, complaints to GM, invoices to Finance  
**Tools needed:** Graph API for info@ and sales@

### Agent 3 — Sourcing Agent (purchase@)
**Trigger:** New RFQ classified by Sentinel  
**Job:** Read specs → query supplier database → request 3 competitive quotes → pass best to Quotation Agent  
**Tools needed:** purchase@ access, Supplier DB (Google Sheet)

### Agent 4 — Quotation Agent (donia@)
**Trigger:** Sourcing Agent delivers prices  
**Job:** Apply margin → generate bilingual PDF quote on company letterhead → send to client → log in RFQ Register  
**Tools needed:** donia@ access, Google Drive (templates), Google Sheets

### Agent 5 — Pipeline Manager
**Schedule:** Daily + on any update  
**Job:** Keep RFQ Register current, track quote validity, alert on expiring quotes, weekly pipeline report  
**Tools needed:** Google Sheets ✓ (ready now)

### Agent 6 — Sales & BD Agent
**Schedule:** Daily + weekly outreach campaigns  
**Job:** Vendor registrations (PetroJet, Heidelberg, etc.), reactivate silent clients, send company profile to new prospects  
**Tools needed:** Gmail (dipotheone@gmail.com for now), Google Drive (Company Profile)

### Agent 7 — Finance Agent
**Schedule:** Daily  
**Job:** Receivables ageing, payment reminders before due date, PO-to-invoice matching, VAT reminders  
**Tools needed:** Google Sheets, Outlook (accounts mailbox)

### Agent 8 — Marketing Agent
**Schedule:** Weekly  
**Job:** LinkedIn posts, Facebook updates, email campaigns to prospect list, company profile updates  
**Tools needed:** Gmail, Google Drive, LinkedIn API (optional)

---

## WHAT THE CLOUD SESSION COULD NOT DO (your advantages)

| Task | Cloud session | Your session (local) |
|---|---|---|
| Read E:\AXION folder | ❌ No access | ✅ Direct access |
| Read Outlook .pst files | ❌ No access | ✅ Direct access |
| Read Outlook Classic live | ❌ No access | ✅ Can use COM or export |
| Run PowerShell/scripts | ❌ No access | ✅ Full shell |
| Access LinkedIn/Facebook | Via web search only | ✅ Browser automation |
| Read previous CCR sessions | ❌ Trusted device only | ✅ Can read locally |

---

## IMMEDIATE PRIORITIES (do first)

1. **Run Stage 1 & 2** — folder survey + email analysis. This is the most valuable output.
2. **Populate the RFQ Register** in Google Sheets with every open opportunity found
3. **Start Pipeline Manager agent** — it can run today with just Google Sheets
4. **Document the supplier list** — even a basic list of 10-20 known suppliers unblocks the Sourcing Agent

---

## KEY CONSTRAINT: Microsoft Graph API

To automate email monitoring for axionegypt.com mailboxes, you need:
1. Azure/Microsoft 365 account for axionegypt.com domain
2. App Registration in Azure Entra ID (like UBCSIS Control does for control@ubcsis.com)
3. Permissions: `Mail.Read`, `Mail.Send`, `Mail.ReadWrite` on the AXION mailboxes
4. If AXION uses a different mail provider (not Microsoft 365), identify it and use the appropriate API

**Check this in Stage 2:** what email system does axionegypt.com use? (look at mail headers in .pst files or DNS MX records for axionegypt.com)

---

## OUTPUT EXPECTED FROM YOUR SESSION

When discovery is complete, produce:
1. `AI-Discovery\AXION-DISCOVERY-REPORT.md` — the 10 things the owner most needs to know
2. `AI-Discovery\COMMERCIAL-EXPOSURE.md` — every open opportunity with EGP value and urgency
3. `AI-Discovery\TEAM-DEPLOYMENT-PLAN.md` — which agents to deploy first and how
4. Populated RFQ Register in Google Sheets
5. CLAUDE.md files for each agent (in their respective session folders)

---

*Handoff written by Cloud Session session_01T7L1U2JW3iQTnBTaMbPqzr — 04-Nov-2026*  
*Owner: Ahmed Diab / dipotheone@gmail.com*
