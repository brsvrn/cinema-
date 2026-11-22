"""Persistence: JSON document store + file storage.

Backends
  * LocalStore    - JSON files under STUDIO_DATA_DIR (default, used by tests/CI)
  * SupabaseStore - Postgres tables (via PostgREST) + Supabase Storage bucket
  * R2 (optional) - large media to Cloudflare R2 (S3 API) when configured

The same interface is used by the pipeline so a render can run anywhere.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

import requests

from . import config

COLLECTIONS = ("series", "characters", "locations", "episodes", "jobs", "cost_ledger", "settings")


class LocalStore:
    kind = "local"

    def __init__(self, root: Path | None = None):
        self.root = Path(root or config.DATA_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, coll: str, id_: str) -> Path:
        d = self.root / coll
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{id_}.json"

    def get(self, coll: str, id_: str) -> dict | None:
        p = self._p(coll, id_)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, coll: str, id_: str, data: dict) -> dict:
        data = {**data, "id": id_, "updated_at": time.time()}
        p = self._p(coll, id_)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(p)
        return data

    def list(self, coll: str, **flt) -> list[dict]:
        d = self.root / coll
        if not d.exists():
            return []
        out = []
        for p in sorted(d.glob("*.json")):
            doc = json.loads(p.read_text())
            if all(doc.get(k) == v for k, v in flt.items()):
                out.append(doc)
        return out

    def delete(self, coll: str, id_: str):
        self._p(coll, id_).unlink(missing_ok=True)

    # files
    def upload(self, local: Path, key: str) -> str:
        dst = self.root / "files" / key
        dst.parent.mkdir(parents=True, exist_ok=True)
        if Path(local).resolve() != dst.resolve():
            dst.write_bytes(Path(local).read_bytes())
        return f"file://{dst}"

    def download(self, key: str, local: Path) -> bool:
        src = self.root / "files" / key
        if not src.exists():
            return False
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(src.read_bytes())
        return True

    def exists(self, key: str) -> bool:
        return (self.root / "files" / key).exists()


class SupabaseStore:
    """Documents live in tables with columns (id text pk, data jsonb, + indexed columns)."""
    kind = "supabase"
    INDEX_COLS = {
        "episodes": ("series_id", "status", "episode_number"),
        "jobs": ("status", "kind", "episode_id"),
        "characters": ("series_id",),
        "locations": ("series_id",),
        "cost_ledger": ("job_id",),
    }

    def __init__(self):
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_SERVICE_KEY
        # New-style secret keys (sb_secret_...) go only in `apikey`; legacy JWT keys also as Bearer.
        self.auth = {"apikey": self.key}
        if self.key.startswith("eyJ"):
            self.auth["Authorization"] = f"Bearer {self.key}"
        self.h = {**self.auth, "Content-Type": "application/json"}
        self.bucket = config.SUPABASE_BUCKET
        self.owner_id = config.__dict__.get("OWNER_ID") or None

    def _rest(self, method: str, path: str, **kw):
        r = requests.request(method, f"{self.url}/rest/v1/{path}", headers={**self.h, **kw.pop("headers", {})},
                             timeout=60, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"supabase {method} {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.text else None

    def get(self, coll: str, id_: str) -> dict | None:
        rows = self._rest("GET", f"{coll}?id=eq.{id_}&select=*")
        if not rows:
            return None
        row = rows[0]
        return {**(row.get("data") or {}), "id": row["id"], **{k: row.get(k) for k in self.INDEX_COLS.get(coll, ())
                                                              if row.get(k) is not None}}

    def put(self, coll: str, id_: str, data: dict) -> dict:
        row: dict[str, Any] = {"id": id_, "data": data}
        for k in self.INDEX_COLS.get(coll, ()):
            if k in data:
                row[k] = data[k]
        if data.get("owner_id"):
            row["owner_id"] = data["owner_id"]
        self._rest("POST", f"{coll}?on_conflict=id", json=row,
                   headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        return {**data, "id": id_}

    def list(self, coll: str, **flt) -> list[dict]:
        q = "&".join(f"{k}=eq.{v}" for k, v in flt.items() if k in self.INDEX_COLS.get(coll, ()))
        rows = self._rest("GET", f"{coll}?select=*{'&' + q if q else ''}&order=id")
        docs = [{**(r.get("data") or {}), "id": r["id"]} for r in rows]
        return [d for d in docs if all(d.get(k) == v for k, v in flt.items())]

    def delete(self, coll: str, id_: str):
        self._rest("DELETE", f"{coll}?id=eq.{id_}")

    def upload(self, local: Path, key: str) -> str:
        if config.r2_enabled() and Path(local).stat().st_size > 5_000_000:
            return R2.upload(local, key)
        ctype = mimetypes.guess_type(str(local))[0] or "application/octet-stream"
        with open(local, "rb") as f:
            r = requests.post(f"{self.url}/storage/v1/object/{self.bucket}/{key}",
                              headers={**self.auth, "Content-Type": ctype, "x-upsert": "true"}, data=f, timeout=600)
        if r.status_code >= 400:
            raise RuntimeError(f"storage upload {key}: {r.status_code} {r.text[:200]}")
        return f"supabase://{self.bucket}/{key}"

    def download(self, key: str, local: Path) -> bool:
        r = requests.get(f"{self.url}/storage/v1/object/{self.bucket}/{key}",
                         headers=self.auth, timeout=600)
        if r.status_code != 200:
            return False
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(r.content)
        return True

    def exists(self, key: str) -> bool:
        folder, _, name = key.rpartition("/")
        r = requests.post(f"{self.url}/storage/v1/object/list/{self.bucket}",
                          headers=self.h, json={"prefix": folder, "search": name, "limit": 5}, timeout=60)
        return r.status_code == 200 and any(o.get("name") == name for o in r.json())

    # queue helpers (Postgres functions defined in supabase/migrations)
    def rpc(self, fn: str, args: dict) -> Any:
        return self._rest("POST", f"rpc/{fn}", json=args)


class R2:
    @staticmethod
    def _client():
        import boto3  # optional dependency
        return boto3.client("s3", endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                            aws_access_key_id=config.R2_ACCESS_KEY_ID,
                            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY, region_name="auto")

    @staticmethod
    def upload(local: Path, key: str) -> str:
        R2._client().upload_file(str(local), config.R2_BUCKET, key)
        return f"r2://{config.R2_BUCKET}/{key}"


def get_store():
    return SupabaseStore() if config.supabase_enabled() else LocalStore()
