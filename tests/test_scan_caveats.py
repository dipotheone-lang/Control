from datetime import datetime

from control.discovery.outlook_scan import run_outlook_scan, scan_folder, write_overview
from tests.test_outlook import FakeFolder, FakeItem, FakeNamespace, FakeStore

INFO = "info@ubcsis.com"
CONTROL = "control@ubcsis.com"


class SortableItems:
    """Fake Items supporting Sort, to prove a capped run samples recent mail."""

    def __init__(self, items):
        self._items = list(items)
        self.sorted_desc = False

    @property
    def Count(self):
        return len(self._items)

    def Sort(self, field, descending):
        assert field == "[ReceivedTime]"
        self._items.sort(key=lambda i: i.ReceivedTime, reverse=descending)
        self.sorted_desc = descending

    def Item(self, index):
        return self._items[index - 1]


def test_capped_run_samples_the_recent_end():
    items = [
        FakeItem(entry_id="old", sender="a@x.com", received=datetime(2024, 2, 29, 9, 0)),
        FakeItem(entry_id="mid", sender="b@x.com", received=datetime(2025, 3, 1, 9, 0)),
        FakeItem(entry_id="new", sender="c@x.com", received=datetime(2026, 8, 1, 9, 0)),
    ]
    folder = FakeFolder("Inbox")
    folder.Items = SortableItems(items)

    rows, summary = scan_folder(folder, mailbox=INFO, folder_name="Inbox", limit=2)
    assert folder.Items.sorted_desc is True
    assert summary.total == 2
    senders = {r["sender"] for r in rows}
    assert senders == {"c@x.com", "b@x.com"}      # newest two, not oldest two


def test_zero_coverage_carries_the_artefact_warning(tmp_path):
    items = [
        FakeItem(entry_id="1", sender="buyer@canalsugar.com", to=INFO,
                 received=datetime(2024, 5, 1, 9, 0)),
        FakeItem(entry_id="2", sender="rep@knauf.com", to=INFO,
                 received=datetime(2025, 5, 2, 9, 0)),
    ]
    store = FakeStore(INFO, [FakeFolder("Inbox", items)])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO, ["Inbox"], tmp_path)
    text = write_overview({INFO: summaries}, tmp_path).read_text(encoding="utf-8")

    assert "observed coverage: **0.0%**" in text
    assert "Read this figure with care" in text
    assert "no historical baseline exists" in text
    assert "deciding on an artefact" in text.lower()


def test_nonzero_coverage_has_no_warning(tmp_path):
    items = [
        FakeItem(entry_id="1", sender="buyer@canalsugar.com", to=INFO, cc=CONTROL,
                 received=datetime(2026, 5, 1, 9, 0)),
        FakeItem(entry_id="2", sender="rep@knauf.com", to=INFO,
                 received=datetime(2026, 5, 2, 9, 0)),
    ]
    store = FakeStore(INFO, [FakeFolder("Inbox", items)])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO, ["Inbox"], tmp_path)
    text = write_overview({INFO: summaries}, tmp_path).read_text(encoding="utf-8")

    assert "observed coverage: **50.0%**" in text
    assert "Read this figure with care" not in text
