import difflib
import json
import logging
import re
import threading
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Same catalog as the frontend's IconPicker.tsx/StackIcon.tsx use for search/render.
METADATA_URL = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons@main/metadata.json"
FUZZY_CUTOFF = 0.8
MIN_CANDIDATE_LEN = 3


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class IconService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._catalog: dict[str, str] | None = None  # normalized alias/slug -> canonical slug
        self._fetch_in_progress = False

    def _start_fetch(self) -> None:
        # Fetches on a background thread so callers (in particular
        # stack_service.scan(), which runs synchronously in main.py's
        # startup lifespan) never block on this network call. Only caches
        # the catalog on success - a failed fetch just clears the in-progress
        # flag, so the next guess() call retries instead of the catalog
        # staying permanently empty for the rest of the process's life.
        with self._lock:
            if self._catalog is not None or self._fetch_in_progress:
                return
            self._fetch_in_progress = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        catalog: dict[str, str] = {}
        try:
            with urllib.request.urlopen(METADATA_URL, timeout=10) as resp:
                data: dict[str, Any] = json.load(resp)
            for slug, meta in data.items():
                catalog[_normalize(slug)] = slug
                for alias in meta.get("aliases") or []:
                    catalog.setdefault(_normalize(alias), slug)
        except Exception:
            logger.exception("Failed to fetch icon catalog")
            catalog = {}
        with self._lock:
            self._fetch_in_progress = False
            if catalog:
                self._catalog = catalog

    def guess(self, candidates: list[str]) -> str | None:
        with self._lock:
            catalog = self._catalog
        if catalog is None:
            self._start_fetch()
            return None
        normalized = [_normalize(c) for c in candidates]
        normalized = [c for c in normalized if len(c) >= MIN_CANDIDATE_LEN]
        for cand in normalized:
            if cand in catalog:
                return catalog[cand]
        for cand in normalized:
            match = difflib.get_close_matches(cand, catalog.keys(), n=1, cutoff=FUZZY_CUTOFF)
            if match:
                return catalog[match[0]]
        return None


icon_service = IconService()
