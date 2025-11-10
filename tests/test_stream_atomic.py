import importlib.util
import json
from pathlib import Path
import requests


def load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "02-splunkbase-download.py"
    spec = importlib.util.spec_from_file_location("sb_downloader", str(script_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_atomic_write(tmp_path):
    mod = load_module()
    apps = [{"uid": 123, "version": "1.0"}]
    file_path = tmp_path / "Your_apps.json"
    # Write initial
    mod.update_Your_apps_file_atomic(apps, 123, "1.1", "2025-11-10T00:00:00Z", file_path=str(file_path))
    assert file_path.exists()
    data = json.loads(file_path.read_text(encoding="utf-8"))
    assert any(item.get("uid") == 123 and item.get("version") == "1.1" for item in data)


def test_download_stream_cleanup_on_exception(tmp_path):
    mod = load_module()

    class BadSession:
        def get(self, *args, **kwargs):
            raise requests.RequestException("simulated failure")

    downloaded = []
    skipped = []
    res = mod.download_stream("999", "0.0.1", cookies={}, downloaded_apps=downloaded, skipped_apps=skipped, out_dir=tmp_path, session=BadSession())
    assert res is None
    assert not (tmp_path / "999_0.0.1.tgz").exists()


def test_download_stream_skip_existing(tmp_path):
    mod = load_module()
    target = tmp_path / "888_1.0.tgz"
    target.write_bytes(b"data")
    downloaded = []
    skipped = []
    res = mod.download_stream("888", "1.0", cookies={}, downloaded_apps=downloaded, skipped_apps=skipped, out_dir=tmp_path, session=None)
    assert res is None
    assert "888_1.0.tgz" in skipped
