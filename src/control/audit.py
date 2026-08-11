"""Hash-chained audit log — charter §1.9, §5.3, §13.3.

One JSONL file per day (YYYY-MM-DD.jsonl) in logs/, but the chain is
continuous across files: each entry's hash covers the previous entry's
hash, so truncation or edit anywhere breaks verification. A break is a
critical incident (§13.3). Unlogged means it didn't happen.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _canonical(entry: dict) -> bytes:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _entry_hash(prev_hash: str, entry_without_hash: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(_canonical(entry_without_hash))
    return h.hexdigest()


class AuditLog:
    def __init__(self, logs_dir: Path):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._seq, self._prev_hash = self._tail()

    def _files(self) -> list[Path]:
        return sorted(self.logs_dir.glob("????-??-??.jsonl"))

    def _tail(self) -> tuple[int, str]:
        """Sequence and hash of the last entry across all daily files."""
        files = self._files()
        if not files:
            return 0, GENESIS
        last_line = None
        with files[-1].open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if last_line is None:
            # An empty latest file: fall back to full scan of prior files.
            for path in reversed(files[:-1]):
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            last_line = line
                if last_line:
                    break
        if last_line is None:
            return 0, GENESIS
        entry = json.loads(last_line)
        return entry["seq"], entry["hash"]

    def append(self, event: str, data: dict) -> dict:
        """Append one entry; returns it. Timestamps are UTC — display
        timezone (Africa/Cairo) is a rendering concern, not a record one."""
        now = datetime.now(timezone.utc)
        entry = {
            "seq": self._seq + 1,
            "ts": now.isoformat(),
            "event": event,
            "data": data,
            "prev_hash": self._prev_hash,
        }
        entry["hash"] = _entry_hash(self._prev_hash, {k: v for k, v in entry.items() if k != "prev_hash"})
        path = self.logs_dir / f"{now.date().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        self._seq, self._prev_hash = entry["seq"], entry["hash"]
        return entry

    def verify(self) -> tuple[bool, str]:
        """Walk the whole chain. Returns (ok, detail). A break is a
        critical incident (§13.3) — the caller halts and alerts."""
        prev_hash, seq = GENESIS, 0
        for path in self._files():
            with path.open("r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry["seq"] != seq + 1:
                        return False, f"{path.name}:{lineno}: seq {entry['seq']} after {seq}"
                    if entry["prev_hash"] != prev_hash:
                        return False, f"{path.name}:{lineno}: prev_hash mismatch"
                    expected = _entry_hash(
                        prev_hash, {k: v for k, v in entry.items() if k not in ("prev_hash", "hash")}
                    )
                    if entry["hash"] != expected:
                        return False, f"{path.name}:{lineno}: hash mismatch (entry edited?)"
                    prev_hash, seq = entry["hash"], entry["seq"]
        return True, f"chain intact: {seq} entries"
