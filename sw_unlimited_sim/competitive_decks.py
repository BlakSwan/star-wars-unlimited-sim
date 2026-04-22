"""Import competitive deck usage from SWUDB hot deck data."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from effect_store import effect_key


SWUDB_BASE_URL = "https://swudb.com"
HOT_DECKS_ENDPOINT = f"{SWUDB_BASE_URL}/api/decks/getHotDecks"
DECK_ENDPOINT = f"{SWUDB_BASE_URL}/api/deck"
COMPETITIVE_DECKS_PATH = Path(__file__).resolve().parent / "data" / "competitive_decks.json"


def _request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"User-Agent": "sw-unlimited-sim/0.1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_hot_deck_summaries(limit: int = 20) -> list[dict[str, Any]]:
    decks: list[dict[str, Any]] = []
    skip = 0
    while len(decks) < limit:
        response = _request_json(HOT_DECKS_ENDPOINT, method="POST", payload={"skip": skip, "sortby": "hot"})
        batch = response.get("decks") or []
        if not batch:
            break
        decks.extend(batch)
        if response.get("endOfResults"):
            break
        skip += len(batch)
    return decks[:limit]


def fetch_deck(deck_id: str) -> dict[str, Any]:
    return _request_json(f"{DECK_ENDPOINT}/{deck_id}")


def swudb_card_key(card: dict[str, Any]) -> str:
    return effect_key(str(card.get("defaultExpansionAbbreviation") or ""), str(card.get("defaultCardNumber") or ""))


def card_label(card: dict[str, Any]) -> str:
    title = card.get("title")
    suffix = f" - {title}" if title else ""
    return f"{card.get('cardName')}{suffix}"


def normalize_deck(deck: dict[str, Any]) -> dict[str, Any]:
    cards = []
    counts: Counter = Counter()
    sideboard_counts: Counter = Counter()

    for entry in deck.get("shuffledDeck") or []:
        card = entry.get("card") or {}
        key = swudb_card_key(card)
        count = int(entry.get("count") or 0)
        sideboard_count = int(entry.get("sideboardCount") or 0)
        if not key.strip("-"):
            continue
        if count > 0:
            counts[key] += count
        if sideboard_count > 0:
            sideboard_counts[key] += sideboard_count
        cards.append({
            "key": key,
            "set": card.get("defaultExpansionAbbreviation"),
            "number": card.get("defaultCardNumber"),
            "name": card_label(card),
            "count": count,
            "sideboard_count": sideboard_count,
        })

    leader = deck.get("leader") or {}
    base = deck.get("base") or {}
    return {
        "deck_id": deck.get("deckId"),
        "name": deck.get("deckName"),
        "author": deck.get("authorName"),
        "like_count": deck.get("likeCount"),
        "publish_date": deck.get("publishDate"),
        "leader": {
            "key": swudb_card_key(leader),
            "name": card_label(leader) if leader else "",
        },
        "base": {
            "key": swudb_card_key(base),
            "name": card_label(base) if base else "",
        },
        "cards": cards,
        "main_counts": dict(counts),
        "sideboard_counts": dict(sideboard_counts),
    }


def fetch_hot_competitive_decks(limit: int = 20) -> dict[str, Any]:
    summaries = fetch_hot_deck_summaries(limit)
    decks = []
    failed: dict[str, str] = {}
    for summary in summaries:
        deck_id = str(summary.get("deckId") or "")
        if not deck_id:
            continue
        try:
            decks.append(normalize_deck(fetch_deck(deck_id)))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            failed[deck_id] = str(exc)

    main_counts: Counter = Counter()
    sideboard_counts: Counter = Counter()
    deck_counts: Counter = Counter()
    for deck in decks:
        seen = set()
        for key, count in deck["main_counts"].items():
            main_counts[key] += count
            seen.add(key)
        for key, count in deck["sideboard_counts"].items():
            sideboard_counts[key] += count
            seen.add(key)
        for key in seen:
            deck_counts[key] += 1

    return {
        "source": "swudb_hot",
        "source_url": "https://swudb.com/decks/hot",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "requested_limit": limit,
        "deck_count": len(decks),
        "failed": failed,
        "decks": decks,
        "usage": {
            "main_counts": dict(main_counts),
            "sideboard_counts": dict(sideboard_counts),
            "deck_counts": dict(deck_counts),
        },
    }


def write_hot_competitive_decks(output_path: str | Path = COMPETITIVE_DECKS_PATH, limit: int = 20) -> dict[str, Any]:
    data = fetch_hot_competitive_decks(limit)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data


def load_competitive_decks(path: str | Path = COMPETITIVE_DECKS_PATH) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {
            "source": "swudb_hot",
            "source_url": "https://swudb.com/decks/hot",
            "deck_count": 0,
            "decks": [],
            "usage": {"main_counts": {}, "sideboard_counts": {}, "deck_counts": {}},
        }
    return json.loads(file_path.read_text(encoding="utf-8"))


def competitive_usage_counters(path: str | Path = COMPETITIVE_DECKS_PATH) -> dict[str, Counter]:
    data = load_competitive_decks(path)
    usage = data.get("usage") or {}
    return {
        "main_counts": Counter(usage.get("main_counts") or {}),
        "sideboard_counts": Counter(usage.get("sideboard_counts") or {}),
        "deck_counts": Counter(usage.get("deck_counts") or {}),
    }
