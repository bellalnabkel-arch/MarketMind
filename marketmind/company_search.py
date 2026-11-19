"""Cached SEC company search, using only downloaded official company metadata."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from rapidfuzz.distance import DamerauLevenshtein

DIRECTORY_URL = "https://www.sec.gov/files/company_tickers.json"
EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
ROOT = Path(__file__).resolve().parents[1]
_lock = threading.Lock()
_legal = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc"}

def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower().replace("&", " and ")).strip()

def normalize_directory(raw: dict, exchange_raw: dict | None = None) -> list[dict]:
    exchanges = {}
    if exchange_raw and {"fields", "data"} <= exchange_raw.keys():
        fields = exchange_raw["fields"]
        for row in exchange_raw["data"]:
            record = dict(zip(fields, row))
            if record.get("exchange"):
                exchanges[(str(record["cik"]).zfill(10), record["ticker"])] = record["exchange"]
    result, seen = [], set()
    for rank, row in enumerate(raw.values()):
        if not isinstance(row, dict) or not str(row.get("cik_str", "")).isdigit() or not row.get("ticker") or not row.get("title"):
            continue
        cik, ticker = str(row["cik_str"]).zfill(10), row["ticker"].upper().replace(".", "-")
        if (cik, ticker) in seen or len(cik) != 10:
            continue
        seen.add((cik, ticker))
        result.append({"name": row["title"], "ticker": ticker, "cik": cik, "exchange": exchanges.get((cik, ticker)), "source_rank": rank})
    if not result:
        raise ValueError("SEC returned an empty or unrecognized directory.")
    return result

@dataclass
class CompanyIndex:
    companies: list[dict]

    def __post_init__(self):
        self.tickers = {c["ticker"]: c for c in self.companies}
        self.records = [(c, normalize(c["name"]), [w for w in normalize(c["name"]).split() if w not in _legal]) for c in self.companies]

    def search(self, query: str, limit: int = 12) -> list[dict]:
        q = normalize(query)
        if not q:
            return []
        if q.isdigit():
            return [c for c in self.companies if c["cik"] == q.zfill(10)][:limit]
        ticker = query.strip().upper().replace(".", "-")
        qw = [w for w in q.split() if w not in _legal]
        ranked = []
        for c, name, words in self.records:
            score = None
            if c["ticker"] == ticker:
                score = 0
            elif name == q or words == qw:
                score = 1
            elif c["ticker"].startswith(ticker):
                score = 2
            elif name.startswith(q):
                score = 3
            elif qw and all(any(w.startswith(part) for w in words) for part in qw):
                score = 4
            elif len(q) >= 3 and q in name:
                score = 5
            elif len(q) >= 3 and qw and all(any(DamerauLevenshtein.distance(part, word) <= (2 if len(part) > 6 else 1) for word in words) for part in qw):
                score = 7
            if score is not None:
                ranked.append((score, len(name), c.get("source_rank", 100000), c["ticker"], c))
        return [r[-1] for r in sorted(ranked, key=lambda r: r[:4])[:limit]]

class CompanyDirectory:
    """Disk cache with a 24-hour refresh and official snapshot outage fallback."""
    def __init__(self, cache_path: Path | None = None):
        self.cache_path = cache_path or ROOT / ".cache" / "company-directory.json"
        self.snapshot_path = ROOT / "data" / "sec-directory-cache.json"

    def load(self, user_agent: str = "", force: bool = False) -> dict:
        with _lock:
            cached = None
            for path in (self.cache_path, self.snapshot_path):
                try:
                    value = json.loads(path.read_text())
                    if value.get("companies") and (not cached or value["fetched_at"] > cached["fetched_at"]):
                        cached = value
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            fresh = cached and (datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"].replace("Z", "+00:00"))).total_seconds() < 86400
            if fresh and not force:
                return {**cached, "warning": None}
            if not user_agent:
                if cached:
                    return {**cached, "warning": "Using the official cached directory. Add your SEC contact to refresh it."}
                raise ValueError("Configure an SEC request identity to download the directory.")
            try:
                response = requests.get(DIRECTORY_URL, headers={"User-Agent": user_agent}, timeout=20)
                response.raise_for_status()
                exchanges = None
                try:
                    ex = requests.get(EXCHANGE_URL, headers={"User-Agent": user_agent}, timeout=15)
                    ex.raise_for_status()
                    exchanges = ex.json()
                except (requests.RequestException, ValueError):
                    pass
                result = {"companies": normalize_directory(response.json(), exchanges), "source_url": DIRECTORY_URL, "fetched_at": datetime.now(timezone.utc).isoformat()}
            except (requests.RequestException, ValueError, TypeError):
                if cached:
                    return {**cached, "warning": "SEC refresh failed; using the last official downloaded directory."}
                raise ValueError("SEC directory is unavailable. Try again later.") from None
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", dir=self.cache_path.parent, delete=False) as temp:
                    json.dump(result, temp)
                os.replace(temp.name, self.cache_path)
            except OSError:
                result["warning"] = "Directory loaded; disk caching is unavailable on this host."
            return result
