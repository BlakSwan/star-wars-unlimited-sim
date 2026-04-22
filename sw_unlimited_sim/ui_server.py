"""Local web UI for non-coder simulator workflows."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from urllib.parse import parse_qs, urlparse

from card_analysis import analyze_card_database
from competitive_decks import competitive_usage_counters, load_competitive_decks
from deck_loader import _load_card_cache, available_decks, resolve_deck_path
from effect_audit import _audit_card, audit_deck, format_deck_audit
from effect_store import effect_key, get_effect, load_effects, save_effect
from effect_training import (
    CONDITION_TYPES,
    DURATIONS,
    EFFECT_TYPES,
    EXECUTION_STATUSES,
    EffectSuggestionError,
    TARGET_CONTROLLERS,
    TARGET_FILTERS,
    TARGET_TYPES,
    TRIGGERS,
    blank_effect_record,
    build_condition,
    build_step,
    execution_status_for_record,
    get_effect_suggestion_provider,
    rules_text,
    should_execute_record,
)
from simulator import SimulationResult, run_single_game
from strategies import get_strategy, list_strategies
from swu_db_client import DEFAULT_GAMEPLAY_OUTPUT_PATH


HOST = "127.0.0.1"
PORT = 8765


CSS = """
:root {
  color-scheme: light;
  --bg: #f4f2ee;
  --text: #1f252b;
  --muted: #69717a;
  --line: #d8d4cc;
  --panel: #ffffff;
  --accent: #a4212b;
  --accent-2: #205b88;
  --ok: #246b43;
  --warn: #9a5a00;
  --bad: #9b1c1c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
}
header {
  background: #171b20;
  color: white;
  padding: 18px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
header h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
nav a {
  color: #f4f2ee;
  text-decoration: none;
  margin-left: 18px;
  font-size: 14px;
}
main { max-width: 1180px; margin: 0 auto; padding: 28px; }
section { margin-bottom: 28px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
}
h2 { margin: 0 0 14px; font-size: 22px; }
h3 { margin: 0 0 10px; font-size: 17px; }
p { color: var(--muted); line-height: 1.5; }
label { display: block; font-weight: 650; margin: 12px 0 6px; }
select, input, textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  font: inherit;
  background: white;
}
textarea { min-height: 130px; resize: vertical; }
.inline-field {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.split {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(320px, 1fr);
  gap: 16px;
}
button, .button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: var(--accent);
  color: white;
  padding: 10px 14px;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  margin-top: 14px;
}
.button.secondary, button.secondary { background: var(--accent-2); }
pre {
  white-space: pre-wrap;
  background: #11161c;
  color: #eef3f8;
  border-radius: 8px;
  padding: 16px;
  overflow: auto;
}
table { width: 100%; border-collapse: collapse; background: var(--panel); }
th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 10px; vertical-align: top; }
th { color: var(--muted); font-size: 13px; text-transform: uppercase; }
.status-supported { color: var(--ok); font-weight: 800; }
.status-partial { color: var(--warn); font-weight: 800; }
.status-unsupported { color: var(--bad); font-weight: 800; }
.metric { font-size: 30px; font-weight: 800; }
.muted { color: var(--muted); }
details {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin-bottom: 12px;
}
summary {
  cursor: pointer;
  font-weight: 800;
  padding: 12px 16px;
}
details pre {
  border-radius: 0 0 8px 8px;
  margin: 0;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.stat-tile {
  background: #fbfaf7;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.stat-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.stat-value {
  font-size: 24px;
  font-weight: 850;
  margin-top: 6px;
}
@media (max-width: 760px) {
  header { display: block; }
  nav { margin-top: 10px; }
  nav a { display: inline-block; margin: 0 14px 8px 0; }
  .split { grid-template-columns: 1fr; }
}
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <header>
    <h1>SWU Simulator Lab</h1>
    <nav>
      <a href="/">Dashboard</a>
      <a href="/audit">Audit</a>
      <a href="/simulate">Simulate</a>
      <a href="/cards">Cards</a>
      <a href="/queue">Training Queue</a>
      <a href="/train">Train Effects</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>""".encode("utf-8")


def options(values: list[str], selected: str | None = None) -> str:
    return "\n".join(
        f'<option value="{esc(value)}" {"selected" if value == selected else ""}>{esc(value)}</option>'
        for value in values
    )


def card_sort_key(card: dict) -> tuple[str, int | str]:
    number = str(card.get("Number") or "")
    return (str(card.get("Set") or ""), int(number) if number.isdigit() else number)


def card_display(card: dict) -> str:
    return f"{card.get('Set')} {card.get('Number')} {card.get('Name')}"


def build_effect_record(
    card: dict,
    status: str,
    trigger: str,
    steps: list[dict],
    notes: str,
    confidence: str = "medium",
    condition_type: str = "none",
    condition_value: str = "",
    execution_status: str = "",
) -> dict:
    condition = build_condition(condition_type, condition_value)
    record = blank_effect_record(card)
    record.update({
        "status": status,
        "source": "human_guided_ui",
        "triggers": [
            {
                "event": trigger,
                "conditions": [condition] if condition else [],
                "steps": steps,
            }
        ],
    })
    record["review"]["confidence"] = confidence
    record["review"]["notes"] = notes.strip()
    record["review"]["human_verified"] = status == "approved"
    record["execution_status"] = execution_status or execution_status_for_record(record)
    if notes.strip():
        record["notes"] = notes.strip()
    return record


def dashboard() -> bytes:
    decks = available_decks()
    strategies = list_strategies()
    effects = load_effects()
    analysis = analyze_card_database(DEFAULT_GAMEPLAY_OUTPUT_PATH)
    supported = analysis["support_counts"].get("supported", 0)
    total = analysis["total_cards"]
    body = f"""
<section>
  <h2>Simulator Dashboard</h2>
  <p>Use this local interface to audit decks, run simulations, analyze card coverage, and train structured card effects.</p>
</section>
<section class="grid">
  <div class="card"><h3>Decks</h3><div class="metric">{len(decks)}</div><p>Bundled decklists available.</p></div>
  <div class="card"><h3>Strategies</h3><div class="metric">{len(strategies)}</div><p>Playable strategy presets.</p></div>
  <div class="card"><h3>Approved Effects</h3><div class="metric">{len(effects)}</div><p>Human-approved structured effect records.</p></div>
  <div class="card"><h3>Card Support</h3><div class="metric">{supported}/{total}</div><p>{supported / max(1, total):.1%} of gameplay cards currently supported by audit.</p></div>
</section>
"""
    return page("Dashboard", body)


def audit_page(query: dict[str, list[str]]) -> bytes:
    decks = available_decks()
    deck = query.get("deck", [decks[0] if decks else ""])[0]
    show_supported = query.get("show_supported", [""])[0] == "1"
    result = ""
    if deck:
        result = f"<pre>{esc(format_deck_audit(audit_deck(deck), show_supported=show_supported))}</pre>"
    checked = "checked" if show_supported else ""
    body = f"""
<section><h2>Deck Audit</h2><p>Check whether a deck has valid tournament shape and supported card effects.</p></section>
<section class="card">
  <form method="get" action="/audit">
    <label>Deck</label>
    <select name="deck">{options(decks, deck)}</select>
    <label><input type="checkbox" name="show_supported" value="1" {checked} style="width:auto"> Show supported cards</label>
    <button type="submit">Run Audit</button>
  </form>
</section>
<section>{result}</section>
"""
    return page("Deck Audit", body)


def parse_positive_int(value: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def pct(numerator: int, denominator: int) -> str:
    return f"{numerator / max(1, denominator):.1%}"


def card_count_from_draw_text(value: str) -> int:
    if value.strip() == "none":
        return 0
    return len([part for part in value.split(", ") if part.strip()])


def empty_sim_stats() -> dict:
    return {
        "games": 0,
        "errors": 0,
        "turns": [],
        "wins": Counter(),
        "drawn": Counter(),
        "played": Counter(),
        "attacks": Counter(),
        "base_attacks": Counter(),
        "resources": Counter(),
        "passes": Counter(),
        "initiative_rolls": Counter(),
        "initiative_wins": Counter(),
        "base_damage_taken": Counter(),
        "top_played": Counter(),
    }


def update_stats_from_game(stats: dict, winner: int | None, turns: int, log: list[str]):
    stats["games"] += 1
    stats["turns"].append(turns)
    if winner:
        stats["wins"][winner] += 1
    else:
        stats["wins"]["draw"] += 1

    initiative_player = None
    for line in log:
        initiative_match = re.search(r"Setup: Player ([12]) wins initiative roll", line)
        if initiative_match:
            initiative_player = int(initiative_match.group(1))
            stats["initiative_rolls"][initiative_player] += 1

        draw_match = re.search(r"Player ([12]) draws (.+?) \(", line)
        if draw_match:
            stats["drawn"][int(draw_match.group(1))] += card_count_from_draw_text(draw_match.group(2))

        resource_match = re.search(r"Player ([12]) resources ", line)
        if resource_match:
            stats["resources"][int(resource_match.group(1))] += 1

        play_match = re.search(r"Player ([12]) plays (.+?)(?: exhausted| ready| on | but|$)", line)
        if play_match:
            player_id = int(play_match.group(1))
            card_name = play_match.group(2).strip()
            stats["played"][player_id] += 1
            stats["top_played"][card_name] += 1

        attack_match = re.search(r"Player ([12])'s .+ attacks ", line)
        if attack_match:
            stats["attacks"][int(attack_match.group(1))] += 1

        base_attack_match = re.search(r"Player ([12])'s .+ attacks Player ([12])'s base for (\d+) damage", line)
        if base_attack_match:
            attacker = int(base_attack_match.group(1))
            defender = int(base_attack_match.group(2))
            damage = int(base_attack_match.group(3))
            stats["base_attacks"][attacker] += 1
            stats["base_damage_taken"][defender] += damage

        base_damage_match = re.search(r"deals (\d+) damage to Player ([12])'s base", line)
        if base_damage_match:
            damage = int(base_damage_match.group(1))
            defender = int(base_damage_match.group(2))
            stats["base_damage_taken"][defender] += damage

        pass_match = re.search(r"Player ([12]) passes", line)
        if pass_match:
            stats["passes"][int(pass_match.group(1))] += 1

    if initiative_player and winner == initiative_player:
        stats["initiative_wins"][initiative_player] += 1


def avg_counter(stats: dict, key: str, player_id: int) -> float:
    return stats[key][player_id] / max(1, stats["games"])


def metric(label: str, value: str) -> str:
    return f"<div class='stat-tile'><div class='stat-label'>{esc(label)}</div><div class='stat-value'>{esc(value)}</div></div>"


def simulation_stats_html(stats: dict) -> str:
    games = max(1, stats["games"])
    turns = stats["turns"] or [0]
    initiative_games = stats["initiative_rolls"][1] + stats["initiative_rolls"][2]
    initiative_wins = stats["initiative_wins"][1] + stats["initiative_wins"][2]
    top_played_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{count}</td></tr>"
        for name, count in stats["top_played"].most_common(10)
    ) or "<tr><td colspan='2'>No cards played</td></tr>"

    tiles = "".join([
        metric("P1 Win Rate", pct(stats["wins"][1], stats["games"])),
        metric("P2 Win Rate", pct(stats["wins"][2], stats["games"])),
        metric("Avg Turns", f"{sum(turns) / len(turns):.1f}"),
        metric("Median Turns", f"{median(turns):.1f}"),
        metric("Fastest Game", str(min(turns))),
        metric("Longest Game", str(max(turns))),
        metric("Initiative Win Rate", pct(initiative_wins, initiative_games)),
        metric("Errors", str(stats["errors"])),
    ])

    player_rows = "".join(
        f"<tr><td>Player {player_id}</td>"
        f"<td>{avg_counter(stats, 'drawn', player_id):.1f}</td>"
        f"<td>{avg_counter(stats, 'played', player_id):.1f}</td>"
        f"<td>{avg_counter(stats, 'attacks', player_id):.1f}</td>"
        f"<td>{avg_counter(stats, 'base_attacks', player_id):.1f}</td>"
        f"<td>{avg_counter(stats, 'resources', player_id):.1f}</td>"
        f"<td>{avg_counter(stats, 'base_damage_taken', player_id):.1f}</td></tr>"
        for player_id in (1, 2)
    )

    return f"""
<section class="card">
  <h2>Stats Window</h2>
  <div class="stats-grid">{tiles}</div>
  <h3>Per Game Averages</h3>
  <table>
    <thead><tr><th>Player</th><th>Cards Drawn</th><th>Cards Played</th><th>Attacks</th><th>Base Attacks</th><th>Resources</th><th>Base Damage Taken</th></tr></thead>
    <tbody>{player_rows}</tbody>
  </table>
  <h3>Most Played Cards</h3>
  <table><thead><tr><th>Card</th><th>Plays</th></tr></thead><tbody>{top_played_rows}</tbody></table>
</section>
"""


def run_ui_simulation_html(
    strategy1_name: str,
    strategy2_name: str,
    games: int,
    deck1_ref: str,
    deck2_ref: str,
    show_logs: bool,
) -> str:
    strategy1 = get_strategy(strategy1_name)
    strategy2 = get_strategy(strategy2_name)
    result = SimulationResult()
    result.strategy1_name = strategy1_name
    result.strategy2_name = strategy2_name
    stats = empty_sim_stats()
    game_sections = []
    log_limit = min(games, 50)

    for game_number in range(1, games + 1):
        winner, turns, log = run_single_game(
            strategy1,
            strategy2,
            verbose=False,
            deck1_ref=deck1_ref,
            deck2_ref=deck2_ref,
        )
        if winner is None and turns == 0:
            result.add_error(f"Game {game_number} had an error: {log[0] if log else 'Unknown'}")
            stats["errors"] += 1
        else:
            result.add_game(winner, turns)
            update_stats_from_game(stats, winner, turns, log)

        if show_logs and game_number <= log_limit:
            winner_label = f"Player {winner}" if winner else "Draw"
            game_log = "\n".join(log) if log else "No logged actions."
            game_sections.append(
                "<details>"
                f"<summary>Game {game_number}: {esc(winner_label)} in {turns} turns</summary>"
                f"<pre>{esc(game_log)}</pre>"
                "</details>"
            )

    cap_note = ""
    if show_logs and games > log_limit:
        cap_note = "<p class='muted'>Detailed logs are capped at 50 games so the browser page stays responsive. Stats include every game in the run.</p>"
    return f"<pre>{esc(result.summary())}</pre>{simulation_stats_html(stats)}{cap_note}{''.join(game_sections)}"


def simulate_page(query: dict[str, list[str]]) -> bytes:
    decks = available_decks()
    strategies = list_strategies()
    deck1 = query.get("deck1", ["rebel_heroism_50" if "rebel_heroism_50" in decks else (decks[0] if decks else "")])[0]
    deck2 = query.get("deck2", ["imperial_villainy_50" if "imperial_villainy_50" in decks else (decks[-1] if decks else "")])[0]
    strat1 = query.get("strategy1", ["aggressive"])[0]
    strat2 = query.get("strategy2", ["aggressive"])[0]
    games = parse_positive_int(query.get("games", ["20"])[0], 20, 5000)
    show_logs = query.get("show_logs", [""])[0] == "1"
    result = ""

    if query.get("run", [""])[0] == "1":
        result = run_ui_simulation_html(strat1, strat2, games, deck1, deck2, show_logs)

    checked = "checked" if show_logs else ""
    body = f"""
<section><h2>Run Simulation</h2><p>Compare two strategies and decklists. Start small, then scale up once audits are clean.</p></section>
<section class="card">
  <form method="get" action="/simulate">
    <input type="hidden" name="run" value="1">
    <div class="grid">
      <div>
        <label>Player 1 Deck</label>
        <select name="deck1">{options(decks, deck1)}</select>
      </div>
      <div>
        <label>Player 1 Strategy</label>
        <select name="strategy1">{options(strategies, strat1)}</select>
      </div>
      <div>
        <label>Player 2 Deck</label>
        <select name="deck2">{options(decks, deck2)}</select>
      </div>
      <div>
        <label>Player 2 Strategy</label>
        <select name="strategy2">{options(strategies, strat2)}</select>
      </div>
      <div>
        <label>Games</label>
        <input name="games" type="number" min="1" max="5000" value="{esc(games)}">
      </div>
    </div>
    <label><input type="checkbox" name="show_logs" value="1" {checked} style="width:auto"> Show moves and cards drawn for each game</label>
    <button type="submit">Run Simulation</button>
  </form>
</section>
<section>{result}</section>
"""
    return page("Simulation", body)


def cards_page() -> bytes:
    analysis = analyze_card_database(DEFAULT_GAMEPLAY_OUTPUT_PATH)
    support = analysis["support_counts"]
    keyword_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{count}</td></tr>"
        for name, count in list(analysis["keyword_counts"].items())[:20]
    )
    unsupported_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{count}</td><td>{esc('; '.join(analysis['unsupported_examples'].get(name, [])))}</td></tr>"
        for name, count in list(analysis["unsupported_patterns"].items())[:20]
    )
    body = f"""
<section><h2>Card Database Analysis</h2><p>Use this to decide which mechanics to implement next.</p></section>
<section class="grid">
  <div class="card"><h3>Total Cards</h3><div class="metric">{analysis['total_cards']}</div></div>
  <div class="card"><h3>Supported</h3><div class="metric">{support.get('supported', 0)}</div></div>
  <div class="card"><h3>Partial</h3><div class="metric">{support.get('partial', 0)}</div></div>
  <div class="card"><h3>Unsupported</h3><div class="metric">{support.get('unsupported', 0)}</div></div>
</section>
<section class="grid">
  <div class="card">
    <h3>Top Keywords</h3>
    <table><thead><tr><th>Keyword</th><th>Count</th></tr></thead><tbody>{keyword_rows}</tbody></table>
  </div>
  <div class="card">
    <h3>Top Unsupported Patterns</h3>
    <table><thead><tr><th>Pattern</th><th>Count</th><th>Examples</th></tr></thead><tbody>{unsupported_rows}</tbody></table>
  </div>
</section>
"""
    return page("Cards", body)


QUEUE_PATTERNS = [
    "when played",
    "on attack",
    "when defeated",
    "action",
    "damage",
    "draw",
    "discard",
    "exhaust",
    "ready",
    "defeat",
    "upgrade",
    "capture",
    "search",
    "shield",
    "experience",
    "heal",
    "exploit",
    "coordinate",
    "smuggle",
    "bounty",
]


def card_key_from_data(card: dict) -> str:
    return effect_key(str(card.get("Set") or ""), str(card.get("Number") or ""))


def card_training_status(card: dict, effects: dict) -> str:
    record = effects.get(card_key_from_data(card))
    if not record:
        return "missing"
    status = str(record.get("status") or "draft")
    execution_status = str(record.get("execution_status") or "manual")
    if should_execute_record(record):
        return "approved/executable"
    if status == "approved":
        return f"approved/{execution_status}"
    return status


def card_patterns(card: dict) -> list[str]:
    text = rules_text(card).lower()
    return [pattern for pattern in QUEUE_PATTERNS if pattern in text]


def deck_usage_counts() -> Counter:
    counts: Counter = Counter()
    for deck_name in available_decks():
        deck_path = resolve_deck_path(deck_name)
        data = json.loads(Path(deck_path).read_text(encoding="utf-8"))
        leader = data.get("leader") or {}
        if leader:
            counts[effect_key(str(leader.get("set") or leader.get("Set") or ""), str(leader.get("number") or leader.get("Number") or ""))] += 1
        for entry in data.get("cards", []):
            key = effect_key(str(entry.get("set") or entry.get("Set") or ""), str(entry.get("number") or entry.get("Number") or ""))
            counts[key] += int(entry.get("count") or 1)
    return counts


def queue_priority(
    audit_status: str,
    training_status: str,
    deck_count: int,
    competitive_main_count: int,
    competitive_deck_count: int,
    patterns: list[str],
) -> tuple[int, int, int, int, int]:
    status_score = {"unsupported": 3, "partial": 2}.get(audit_status, 1)
    training_score = 2 if training_status == "missing" else 1
    pattern_score = len(patterns)
    return (competitive_deck_count, competitive_main_count, deck_count, status_score + training_score, pattern_score)


def training_queue_items(scope: str, status_filter: str, limit: int) -> list[dict]:
    index = _load_card_index()
    effects = load_effects()
    usage = deck_usage_counts()
    competitive_usage = competitive_usage_counters()
    competitive_main_counts = competitive_usage["main_counts"]
    competitive_sideboard_counts = competitive_usage["sideboard_counts"]
    competitive_deck_counts = competitive_usage["deck_counts"]
    items = []

    for card in index.values():
        key = card_key_from_data(card)
        deck_count = usage.get(key, 0)
        competitive_main_count = competitive_main_counts.get(key, 0)
        competitive_sideboard_count = competitive_sideboard_counts.get(key, 0)
        competitive_deck_count = competitive_deck_counts.get(key, 0)
        if scope == "decks" and deck_count == 0:
            continue
        if scope == "competitive" and competitive_deck_count == 0:
            continue

        audit = _audit_card(card, count=1, trained_effects=effects)
        training_status = card_training_status(card, effects)
        if status_filter != "all":
            if status_filter == "needs_work" and audit.status == "supported":
                continue
            if status_filter in {"unsupported", "partial", "supported"} and audit.status != status_filter:
                continue
            if status_filter == "missing" and training_status != "missing":
                continue

        patterns = card_patterns(card)
        if status_filter == "all" and audit.status == "supported" and training_status == "approved/executable":
            continue

        items.append({
            "key": key,
            "card": card,
            "audit": audit,
            "training_status": training_status,
            "deck_count": deck_count,
            "competitive_main_count": competitive_main_count,
            "competitive_sideboard_count": competitive_sideboard_count,
            "competitive_deck_count": competitive_deck_count,
            "patterns": patterns,
            "priority": queue_priority(
                audit.status,
                training_status,
                deck_count,
                competitive_main_count,
                competitive_deck_count,
                patterns,
            ),
        })

    return sorted(items, key=lambda item: item["priority"], reverse=True)[:limit]


def training_queue_page(query: dict[str, list[str]]) -> bytes:
    scope = query.get("scope", ["all"])[0]
    status_filter = query.get("status", ["needs_work"])[0]
    limit = parse_positive_int(query.get("limit", ["100"])[0], 100, 500)
    items = training_queue_items(scope, status_filter, limit)
    competitive_data = load_competitive_decks()
    competitive_note = (
        f"{competitive_data.get('deck_count', 0)} SWUDB hot decks cached"
        if competitive_data.get("deck_count")
        else "No SWUDB hot deck cache yet. Run `python main.py --fetch-competitive-decks`."
    )
    rows = []
    for item in items:
        card = item["card"]
        selected = f"{card.get('Set')}-{card.get('Number')}"
        train_href = f"/train?card={esc(selected)}"
        draft_href = f"/train/suggest?card={esc(selected)}"
        ollama_draft_href = f"/train/suggest?card={esc(selected)}&provider=ollama"
        local_draft_href = f"/train/suggest?card={esc(selected)}&provider=local"
        rows.append(
            "<tr>"
            f"<td>{esc(card.get('Set'))} {esc(card.get('Number'))}</td>"
            f"<td>{esc(card.get('Name'))}<br><span class='muted'>{esc(card.get('Type'))}</span></td>"
            f"<td>{item['deck_count']}</td>"
            f"<td>{item['competitive_main_count']}</td>"
            f"<td>{item['competitive_deck_count']}</td>"
            f"<td class='status-{esc(item['audit'].status)}'>{esc(item['audit'].status)}</td>"
            f"<td>{esc(item['training_status'])}</td>"
            f"<td>{esc(', '.join(item['patterns']) or 'none')}</td>"
            f"<td>{esc('; '.join(item['audit'].reasons))}</td>"
            f"<td><a class='button secondary' href='{train_href}'>Train</a> <a class='button' href='{draft_href}'>Draft</a> <a class='button' href='{ollama_draft_href}'>Ollama Draft</a> <a class='button' href='{local_draft_href}'>Local Draft</a></td>"
            "</tr>"
        )
    queue_rows = "\n".join(rows) or "<tr><td colspan='10'>No cards match this queue filter.</td></tr>"
    body = f"""
<section><h2>Unsupported Card Training Queue</h2><p>Prioritize unsupported and partially supported cards, especially cards used by cached competitive decks.</p><p class="muted">{esc(competitive_note)}</p></section>
<section class="card">
  <form method="get" action="/queue">
    <div class="inline-field">
      <div>
        <label>Scope</label>
        <select name="scope">{options(["all", "competitive", "decks"], scope)}</select>
      </div>
      <div>
        <label>Status</label>
        <select name="status">{options(["needs_work", "unsupported", "partial", "missing", "all"], status_filter)}</select>
      </div>
      <div>
        <label>Limit</label>
        <input name="limit" type="number" min="1" max="500" value="{esc(limit)}">
      </div>
    </div>
    <button type="submit">Refresh Queue</button>
  </form>
</section>
<section>
  <table>
    <thead>
      <tr><th>Card</th><th>Name</th><th>Bundled Copies</th><th>Hot Copies</th><th>Hot Decks</th><th>Audit</th><th>Training</th><th>Patterns</th><th>Reason</th><th>Actions</th></tr>
    </thead>
    <tbody>{queue_rows}</tbody>
  </table>
</section>
"""
    return page("Training Queue", body)


def _load_card_index():
    return _load_card_cache(DEFAULT_GAMEPLAY_OUTPUT_PATH)


def effect_step_fields(index: int) -> str:
    return f"""
<div class="card">
  <h3>Step {index}</h3>
  <label>Effect</label>
  <select name="effect_type_{index}">
    <option value="">No step</option>
    {options(EFFECT_TYPES)}
  </select>
  <div class="inline-field">
    <div>
      <label>Amount</label>
      <input name="amount_{index}" type="number" min="0">
    </div>
    <div>
      <label>Duration</label>
      <select name="duration_{index}">{options(DURATIONS, "instant")}</select>
    </div>
  </div>
  <div class="inline-field">
    <div>
      <label>Target Side</label>
      <select name="target_controller_{index}">{options(TARGET_CONTROLLERS, "enemy")}</select>
    </div>
    <div>
      <label>Target Type</label>
      <select name="target_type_{index}">{options(TARGET_TYPES, "unit")}</select>
    </div>
  </div>
  <div class="inline-field">
    <div>
      <label>Target Filter</label>
      <select name="target_filter_{index}">{options(TARGET_FILTERS, "none")}</select>
    </div>
    <div>
      <label>Filter Value</label>
      <input name="filter_value_{index}" placeholder="Trait, aspect, number, etc.">
    </div>
  </div>
  <div class="inline-field">
    <div>
      <label>Choice Group</label>
      <input name="choice_group_{index}" placeholder="mode_1">
    </div>
    <div>
      <label><input type="checkbox" name="optional_{index}" value="1" style="width:auto"> Optional / may</label>
    </div>
  </div>
</div>
"""


def train_page(query: dict[str, list[str]]) -> bytes:
    index = _load_card_index()
    cards = sorted(index.values(), key=card_sort_key)
    selected = query.get("card", [""])[0]
    selected_card = None
    if selected:
        set_code, number = selected.split("-", 1)
        selected_card = index.get((set_code, number))
    if not selected_card:
        selected_card = cards[0] if cards else None
        selected = f"{selected_card.get('Set')}-{selected_card.get('Number')}" if selected_card else ""

    current_effect = get_effect(str(selected_card.get("Set")), str(selected_card.get("Number"))) if selected_card else None
    card_options = []
    for card in cards:
        value = f"{card.get('Set')}-{card.get('Number')}"
        selected_attr = "selected" if value == selected else ""
        card_options.append(f'<option value="{esc(value)}" {selected_attr}>{esc(card_display(card))}</option>')
    card_options_html = "\n".join(card_options)
    text = rules_text(selected_card) if selected_card else ""
    default_effect = blank_effect_record(selected_card) if selected_card else {"status": "draft", "triggers": []}
    effect_json = json.dumps(current_effect or default_effect, indent=2)
    execution_status = (current_effect or default_effect).get("execution_status", "manual")
    review = (current_effect or default_effect).get("review", {})
    triage = review.get("triage", "")
    parse_warnings = review.get("parse_warnings") or []
    source = (current_effect or default_effect).get("source", "")
    triage_html = f"<p><strong>Triage:</strong> {esc(triage)}</p>" if triage else ""
    source_html = f"<p><strong>Source:</strong> {esc(source)}</p>" if source else ""
    warnings_html = ""
    if parse_warnings:
        warnings_html = "<p><strong>Parse warnings:</strong></p><ul>" + "".join(
            f"<li>{esc(warning)}</li>" for warning in parse_warnings
        ) + "</ul>"
    draft_href = f"/train/suggest?card={esc(selected)}"
    llm_href = f"/train/suggest?card={esc(selected)}&provider=openai"
    ollama_llm_href = f"/train/suggest?card={esc(selected)}&provider=ollama"
    local_llm_href = f"/train/suggest?card={esc(selected)}&provider=local"
    body = f"""
<section><h2>Train Structured Effects</h2><p>Turn card text into reviewed simulator actions. Approved executable effects are loaded by the simulator during games.</p></section>
<section class="grid">
  <div class="card">
    <form method="get" action="/train">
      <label>Card</label>
      <select name="card">{card_options_html}</select>
      <button type="submit">Load Card</button>
    </form>
  </div>
  <div class="card">
    <h3>{esc(selected_card.get('Name') if selected_card else '')}</h3>
    <p class="muted">{esc(selected)}</p>
    <p><strong>Execution status:</strong> {esc(execution_status)}</p>
    {source_html}
    {triage_html}
    {warnings_html}
    <pre>{esc(text or 'No rules text')}</pre>
    <a class="button secondary" href="{draft_href}">Draft From Card Text</a>
    <a class="button" href="{llm_href}">Draft With LLM</a>
    <a class="button" href="{ollama_llm_href}">Draft With Ollama</a>
    <a class="button" href="{local_llm_href}">Draft With Local Model</a>
  </div>
</section>
<section>
  <h3>Complex Effect Builder</h3>
  <form method="post" action="/train/guided-save">
    <input type="hidden" name="card" value="{esc(selected)}">
    <div class="inline-field">
      <div>
        <label>Status</label>
        <select name="status">{options(["draft", "approved"], "draft")}</select>
      </div>
      <div>
        <label>Engine Execution</label>
        <select name="execution_status">{options(EXECUTION_STATUSES, "manual")}</select>
      </div>
      <div>
        <label>Reviewer Confidence</label>
        <select name="confidence">{options(["low", "medium", "high"], "medium")}</select>
      </div>
      <div>
        <label>Trigger</label>
        <select name="trigger">{options(TRIGGERS, "when_played")}</select>
      </div>
    </div>
    <div class="inline-field">
      <div>
        <label>Condition</label>
        <select name="condition_type">{options(CONDITION_TYPES, "none")}</select>
      </div>
      <div>
        <label>Condition Value</label>
        <input name="condition_value" placeholder="Trait, aspect, threshold, etc.">
      </div>
    </div>
    <h3>Effect Steps</h3>
    <div class="grid">
      {effect_step_fields(1)}
      {effect_step_fields(2)}
      {effect_step_fields(3)}
    </div>
    <label>Reviewer Notes</label>
    <textarea name="notes" placeholder="Ruling notes, unresolved choices, or why this should not execute yet."></textarea>
    <button type="submit">Save Structured Effect</button>
  </form>
</section>
<section class="grid">
  <div class="card">
    <h3>Simple One-Step Shortcut</h3>
    <form method="post" action="/train/guided-save">
      <input type="hidden" name="card" value="{esc(selected)}">
      <input type="hidden" name="execution_status" value="executable">
      <input type="hidden" name="confidence" value="medium">
      <input type="hidden" name="condition_type" value="none">
      <div class="inline-field">
        <div>
          <label>Status</label>
          <select name="status">{options(["draft", "approved"], "draft")}</select>
        </div>
        <div>
          <label>Trigger</label>
          <select name="trigger">{options(["when_played", "on_attack", "when_defeated", "action"], "when_played")}</select>
        </div>
      </div>
      <label>Effect</label>
      <select name="effect_type_1">{options(["deal_damage", "heal_damage", "draw_cards", "discard_cards", "exhaust_unit", "ready_unit", "defeat_unit", "give_shield", "give_experience"], "deal_damage")}</select>
      <div class="inline-field">
        <div>
          <label>Amount</label>
          <input name="amount_1" type="number" min="0" value="1">
        </div>
        <div>
          <label>Target Side</label>
          <select name="target_controller_1">{options(["enemy", "friendly", "self", "any"], "enemy")}</select>
        </div>
        <div>
          <label>Target Type</label>
          <select name="target_type_1">{options(["unit", "base", "player"], "unit")}</select>
        </div>
      </div>
      <label>Reviewer Notes</label>
      <textarea name="notes" placeholder="Optional ruling notes or uncertainty."></textarea>
      <button type="submit">Save Guided Effect</button>
    </form>
  </div>
  <div class="card">
    <h3>Advanced JSON Editor</h3>
    <form method="post" action="/train/save">
      <label>Structured Effect JSON</label>
      <textarea name="effect_json">{esc(effect_json)}</textarea>
      <button type="submit">Save JSON Effect</button>
    </form>
  </div>
</section>
"""
    return page("Train Effects", body)


def save_train(post_body: str) -> bytes:
    fields = parse_qs(post_body)
    raw = fields.get("effect_json", ["{}"])[0]
    try:
        data = json.loads(raw)
        save_effect(data)
        message = f"<section class='card'><h2>Effect Saved</h2><pre>{esc(json.dumps(data, indent=2))}</pre><a class='button secondary' href='/train'>Back</a></section>"
    except Exception as exc:
        message = f"<section class='card'><h2>Could Not Save</h2><p>{esc(exc)}</p><a class='button secondary' href='/train'>Back</a></section>"
    return page("Save Effect", message)


def save_guided_train(post_body: str) -> bytes:
    fields = parse_qs(post_body)
    selected = fields.get("card", [""])[0]
    try:
        set_code, number = selected.split("-", 1)
        card = _load_card_index()[(set_code, number)]
        steps = []
        for index in range(1, 4):
            step = build_step(
                effect_type=fields.get(f"effect_type_{index}", [""])[0],
                amount=fields.get(f"amount_{index}", [""])[0],
                target_controller=fields.get(f"target_controller_{index}", ["enemy"])[0],
                target_type=fields.get(f"target_type_{index}", ["unit"])[0],
                target_filter=fields.get(f"target_filter_{index}", ["none"])[0],
                filter_value=fields.get(f"filter_value_{index}", [""])[0],
                duration=fields.get(f"duration_{index}", ["instant"])[0],
                optional=fields.get(f"optional_{index}", [""])[0] == "1",
                choice_group=fields.get(f"choice_group_{index}", [""])[0],
            )
            if step:
                steps.append(step)
        if not steps:
            raise ValueError("At least one effect step is required")
        data = build_effect_record(
            card=card,
            status=fields.get("status", ["draft"])[0],
            trigger=fields.get("trigger", ["when_played"])[0],
            steps=steps,
            notes=fields.get("notes", [""])[0],
            confidence=fields.get("confidence", ["medium"])[0],
            condition_type=fields.get("condition_type", ["none"])[0],
            condition_value=fields.get("condition_value", [""])[0],
            execution_status=fields.get("execution_status", [""])[0],
        )
        save_effect(data)
        message = (
            "<section class='card'><h2>Guided Effect Saved</h2>"
            f"<pre>{esc(json.dumps(data, indent=2))}</pre>"
            f"<a class='button secondary' href='/train?card={esc(selected)}'>Back</a></section>"
        )
    except Exception as exc:
        message = f"<section class='card'><h2>Could Not Save</h2><p>{esc(exc)}</p><a class='button secondary' href='/train'>Back</a></section>"
    return page("Save Guided Effect", message)


def suggest_train_effect(query: dict[str, list[str]]) -> bytes:
    selected = query.get("card", [""])[0]
    try:
        set_code, number = selected.split("-", 1)
        card = _load_card_index()[(set_code, number)]
        provider = get_effect_suggestion_provider(query.get("provider", ["heuristic"])[0])
        data = provider.suggest_effect(card)
        save_effect(data)
        review = data.get("review", {})
        triage = review.get("triage", "not classified")
        warnings = review.get("parse_warnings") or []
        warning_block = ""
        if warnings:
            warning_block = "<p><strong>Parse warnings:</strong></p><ul>" + "".join(
                f"<li>{esc(warning)}</li>" for warning in warnings
            ) + "</ul>"
        message = (
            "<section class='card'><h2>Draft Saved</h2>"
            "<p class='muted'>The draft is stored for human review. Drafts will not execute in simulations until approved, even when the structure looks executable.</p>"
            f"<p><strong>Source:</strong> {esc(data.get('source', 'unknown'))}</p>"
            f"<p><strong>Triage:</strong> {esc(triage)}</p>"
            f"{warning_block}"
            f"<pre>{esc(json.dumps(data, indent=2))}</pre>"
            f"<a class='button secondary' href='/train?card={esc(selected)}'>Review Draft</a></section>"
        )
    except EffectSuggestionError as exc:
        actions = "".join(f"<li>{esc(action)}</li>" for action in exc.actions)
        action_block = f"<ul>{actions}</ul>" if actions else ""
        message = (
            f"<section class='card'><h2>{esc(exc.title)}</h2>"
            f"<p>{esc(exc.detail)}</p>"
            f"{action_block}"
            f"<a class='button secondary' href='/train?card={esc(selected)}'>Back</a></section>"
        )
    except Exception as exc:
        message = f"<section class='card'><h2>Could Not Draft Effect</h2><p>{esc(exc)}</p><a class='button secondary' href='/train'>Back</a></section>"
    return page("Draft Effect", message)


class UIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        routes = {
            "/": lambda: dashboard(),
            "/audit": lambda: audit_page(query),
            "/simulate": lambda: simulate_page(query),
            "/cards": lambda: cards_page(),
            "/queue": lambda: training_queue_page(query),
            "/train": lambda: train_page(query),
            "/train/suggest": lambda: suggest_train_effect(query),
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self.send_error(404)
            return
        self._send(handler())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        if self.path == "/train/save":
            self._send(save_train(body))
            return
        if self.path == "/train/guided-save":
            self._send(save_guided_train(body))
            return
        self.send_error(404)

    def _send(self, payload: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def run_ui(host: str = HOST, port: int = PORT):
    server = ThreadingHTTPServer((host, port), UIHandler)
    print(f"SWU Simulator UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run_ui()
