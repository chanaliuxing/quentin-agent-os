from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests


class QdrantError(RuntimeError):
    pass


@dataclass(frozen=True)
class QdrantPoint:
    id: str
    score: float
    payload: Dict[str, Any]


class QdrantRestClient:
    """
    Minimal Qdrant REST client (no extra deps).

    We keep this intentionally small:
    - create collection if missing
    - upsert points
    - search (vector)
    - delete points
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 10.0,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        if not self.base_url:
            raise ValueError("QdrantRestClient requires base_url")
        self.timeout_s = float(timeout_s)
        self._session = requests.Session()
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["api-key"] = str(api_key)

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _raise(self, r: requests.Response, *, what: str) -> None:
        try:
            body = r.text[:2000]
        except Exception:
            body = "<unreadable>"
        raise QdrantError(f"Qdrant {what} failed: HTTP {r.status_code}: {body}")

    def ready(self) -> bool:
        try:
            r = self._session.get(self._url("/readyz"), headers=self._headers, timeout=self.timeout_s)
            return r.status_code == 200
        except Exception:
            return False

    def wait_ready(self, *, timeout_s: float = 30.0) -> bool:
        deadline = time.time() + float(timeout_s)
        while time.time() < deadline:
            if self.ready():
                return True
            time.sleep(0.25)
        return False

    def collection_exists(self, name: str) -> bool:
        r = self._session.get(
            self._url(f"/collections/{name}"),
            headers=self._headers,
            timeout=self.timeout_s,
        )
        return r.status_code == 200

    def list_collections(self) -> List[str]:
        r = self._session.get(self._url("/collections"), headers=self._headers, timeout=self.timeout_s)
        if r.status_code != 200:
            self._raise(r, what="list_collections")
        data = r.json() or {}
        cols = (data.get("result") or {}).get("collections") or []
        out: List[str] = []
        for c in cols:
            name = str((c or {}).get("name") or "").strip()
            if name:
                out.append(name)
        return out

    def collection_info(self, name: str) -> Dict[str, Any]:
        r = self._session.get(self._url(f"/collections/{name}"), headers=self._headers, timeout=self.timeout_s)
        if r.status_code != 200:
            self._raise(r, what="collection_info")
        return r.json() or {}

    def delete_collection(self, name: str, *, timeout_s: Optional[float] = None) -> None:
        if not str(name or "").strip():
            return
        r = self._session.delete(
            self._url(f"/collections/{name}"),
            headers=self._headers,
            timeout=float(timeout_s or self.timeout_s),
        )
        if r.status_code not in (200, 202):
            self._raise(r, what="delete_collection")

    def ensure_collection(
        self,
        *,
        name: str,
        dim: int,
        distance: str = "Cosine",
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 100,
        on_disk_payload: bool = True,
    ) -> None:
        if self.collection_exists(name):
            return
        payload: Dict[str, Any] = {
            "vectors": {"size": int(dim), "distance": str(distance)},
            "hnsw_config": {"m": int(hnsw_m), "ef_construct": int(hnsw_ef_construct)},
            "optimizers_config": {"indexing_threshold": 20_000},
        }
        if on_disk_payload:
            payload["on_disk_payload"] = True

        r = self._session.put(
            self._url(f"/collections/{name}"),
            headers=self._headers,
            timeout=self.timeout_s,
            data=json.dumps(payload),
        )
        if r.status_code not in (200, 201):
            self._raise(r, what="ensure_collection")

    def upsert(
        self,
        *,
        collection: str,
        points: Iterable[Dict[str, Any]],
        wait: bool = False,
    ) -> None:
        pts = list(points)
        if not pts:
            return
        r = self._session.put(
            self._url(f"/collections/{collection}/points?wait={'true' if wait else 'false'}"),
            headers=self._headers,
            timeout=self.timeout_s,
            data=json.dumps({"points": pts}),
        )
        if r.status_code not in (200, 201):
            self._raise(r, what="upsert")

    def delete_points(self, *, collection: str, ids: List[str], wait: bool = False) -> None:
        ids = [str(x) for x in (ids or []) if str(x or "").strip()]
        if not ids:
            return
        r = self._session.post(
            self._url(f"/collections/{collection}/points/delete?wait={'true' if wait else 'false'}"),
            headers=self._headers,
            timeout=self.timeout_s,
            data=json.dumps({"points": ids}),
        )
        if r.status_code not in (200, 201):
            self._raise(r, what="delete_points")

    def search(
        self,
        *,
        collection: str,
        vector: List[float],
        limit: int,
        qfilter: Optional[Dict[str, Any]] = None,
        with_payload: bool = True,
        hnsw_ef: Optional[int] = None,
    ) -> List[QdrantPoint]:
        params: Dict[str, Any] = {"vector": vector, "limit": int(limit), "with_payload": bool(with_payload)}
        if qfilter:
            params["filter"] = qfilter
        if hnsw_ef is not None:
            params["params"] = {"hnsw_ef": int(hnsw_ef)}

        r = self._session.post(
            self._url(f"/collections/{collection}/points/search"),
            headers=self._headers,
            timeout=self.timeout_s,
            data=json.dumps(params),
        )
        if r.status_code != 200:
            self._raise(r, what="search")
        data = r.json() or {}
        result = data.get("result") or []
        out: List[QdrantPoint] = []
        for item in result:
            pid = str(item.get("id"))
            score = float(item.get("score") or 0.0)
            payload = item.get("payload") or {}
            out.append(QdrantPoint(id=pid, score=score, payload=dict(payload)))
        return out
