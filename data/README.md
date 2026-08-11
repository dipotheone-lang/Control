# data/

System of record — charter §5.2. `control.db` (SQLite) is the master;
Excel in `exports/` is generated output, never the source.

- `exports/` — generated register exports
- `submissions/YYYY/MM/` — received submission files (never client-confidential ones, §12.1.2)
- `quarantine/` — attachments failing §5.4 validation; reported, never opened
- `backup/` — daily encrypted backup before first write

**Nothing in this directory is committed to git** (see `.gitignore`) — it is
runtime operational data containing mail content and personal data (§12.2).
