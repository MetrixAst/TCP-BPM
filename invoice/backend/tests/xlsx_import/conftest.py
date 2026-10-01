"""save_upload() writes to disk via tenant_stamp._tenant_assets_root(), which
defaults to the real repo-relative uploads/tenants/ dir — that dir IS
committed to git in this repo (real tenant stamps/signatures), so without
this override, running these tests once accidentally leaves synthetic test
files sitting in a directory `git add -A` would happily pick up (exactly
what happened 2026-08-26 — 3 leftover test .xlsx landed in a commit).
Redirect every test in this package to a throwaway tmp dir instead."""
import pytest


@pytest.fixture(autouse=True)
def _isolate_upload_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TENANT_UPLOADS_DIR", str(tmp_path))
