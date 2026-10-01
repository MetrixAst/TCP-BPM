"""Filename sanitization shared by every place that builds a downloads-dir
path from an externally-supplied invoice id.

Deliberately dependency-free (only stdlib) so it can be imported from
odata_1c_client.py, nova_buh_1c_client.py, and invoice_access.py without risk
of circular imports through integration_1c.py.
"""
from __future__ import annotations

import re

# Invoice ids we actually see are either 1C GUIDs or Nova's own compound keys —
# neither ever legitimately contains "/", "\", or "..". Anything outside this
# set is dropped rather than passed through, so a crafted invoice_id can't
# escape the downloads directory via path traversal (see audit from
# 2026-08-25: several places built `downloads / f"invoice_{invoice_id}.pdf"`
# with no validation at all).
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_.\-]")


def safe_filename_component(value: str) -> str:
    return _UNSAFE_CHARS.sub("_", (value or "").strip())
