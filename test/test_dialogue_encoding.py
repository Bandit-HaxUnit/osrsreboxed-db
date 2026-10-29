"""UTF-8 cache and audit fingerprints must not depend on the host locale."""

from pathlib import Path

from scripts.dialogues import fetch
from scripts.dialogues.corrections import fingerprint


def test_utf8_cache_round_trip_preserves_fingerprint_on_cp1252_host(monkeypatch, tmp_path):
    original_read = Path.read_text

    def windows_default(path, encoding=None, errors=None):
        return original_read(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", windows_default)
    path = tmp_path / "source.json"
    source = {"npc": "Café — déjà vu"}
    fetch.save(path, source)
    loaded = fetch.read_cache(path)
    assert loaded == source
    assert fingerprint(loaded) == fingerprint(source)


def test_missing_cache_still_returns_empty_without_creating_a_file(tmp_path):
    path = tmp_path / "missing.json"
    assert fetch.read_cache(path) == {}
    assert not path.exists()
