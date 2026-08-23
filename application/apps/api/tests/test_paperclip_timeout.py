from __future__ import annotations

import time

from app.adapters import paperclip_client


class _HangClient:
    def search(self, query: str, **kwargs):
        time.sleep(30)
        return type("Result", (), {"raw": [], "output": ""})()


def test_search_drug_literature_does_not_block_on_hung_client(monkeypatch):
    monkeypatch.setattr(paperclip_client, "SEARCH_TIMEOUT_SECONDS", 0.15)
    start = time.monotonic()
    results = paperclip_client.search_drug_literature(_HangClient(), "paclitaxel", ["TUBB"])
    elapsed = time.monotonic() - start
    assert elapsed < 4
    assert len(results) == 4
    assert all(family.result_count == 0 for family in results)
