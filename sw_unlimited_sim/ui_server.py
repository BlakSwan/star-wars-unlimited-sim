"""Local web UI for non-coder simulator workflows."""

from __future__ import annotations

import html
import json
import re
from copy import deepcopy
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from urllib.parse import parse_qs, urlparse

from card_analysis import analyze_card_database
from competitive_decks import competitive_usage_counters, load_competitive_decks
from deck_loader import _load_card_cache, available_decks, resolve_deck_path
from effect_audit import _audit_card, audit_deck, format_deck_audit
from effect_store import effect_key, get_effect, load_effects, save_draft_artifact, save_effect
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
    validate_effect_record,
)
from llm_queue import (
    SIMPLE_LLM_BLOCKED_KEYWORDS,
    SIMPLE_LLM_BLOCKED_PHRASES,
    simple_llm_candidates,
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
.table-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
  margin-bottom: 12px;
}
.table-toolbar .grow {
  flex: 1 1 280px;
}
.table-toolbar label {
  margin-top: 0;
}
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
      <a href="/batch">Batch Review</a>
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


def option_with_all(values: list[str], selected: str, all_label: str = "all") -> str:
    return f'<option value="all" {"selected" if selected == "all" else ""}>{esc(all_label)}</option>' + options(values, selected)


def card_sort_key(card: dict) -> tuple[str, int | str]:
    number = str(card.get("Number") or "")
    return (str(card.get("Set") or ""), int(number) if number.isdigit() else number)


def card_display(card: dict) -> str:
    return f"{card.get('Set')} {card.get('Number')} {card.get('Name')}"


def unique_card_values(cards: list[dict], field: str) -> list[str]:
    values = set()
    for card in cards:
        value = card.get(field)
        if isinstance(value, list):
            values.update(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            values.add(str(value))
    return sorted(values)


def card_has_value(card: dict, field: str, selected: str) -> bool:
    if selected == "all":
        return True
    value = card.get(field)
    if isinstance(value, list):
        return selected.lower() in {str(item).lower() for item in value}
    return str(value or "").lower() == selected.lower()


def card_matches_official_filters(card: dict, filters: dict[str, str]) -> bool:
    if filters.get("set", "all") != "all" and str(card.get("Set") or "") != filters["set"]:
        return False
    if not card_has_value(card, "Type", filters.get("type", "all")):
        return False
    if not card_has_value(card, "Aspects", filters.get("aspect", "all")):
        return False
    if not card_has_value(card, "Keywords", filters.get("keyword", "all")):
        return False
    if not card_has_value(card, "Traits", filters.get("trait", "all")):
        return False
    if not card_has_value(card, "Arenas", filters.get("arena", "all")):
        return False
    if not card_has_value(card, "Rarity", filters.get("rarity", "all")):
        return False
    search = filters.get("search", "").strip().lower()
    if search:
        haystack = " ".join(
            str(card.get(field) or "")
            for field in ("Set", "Number", "Name", "Subtitle", "Type", "FrontText", "BackText", "EpicAction")
        ).lower()
        if search not in haystack:
            return False
    return True


def official_filter_values(cards: list[dict]) -> dict[str, list[str]]:
    return {
        "sets": unique_card_values(cards, "Set"),
        "types": unique_card_values(cards, "Type"),
        "aspects": unique_card_values(cards, "Aspects"),
        "keywords": unique_card_values(cards, "Keywords"),
        "traits": unique_card_values(cards, "Traits"),
        "arenas": unique_card_values(cards, "Arenas"),
        "rarities": unique_card_values(cards, "Rarity"),
    }


def official_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {
        "set": query.get("set", ["all"])[0],
        "type": query.get("type", ["all"])[0],
        "aspect": query.get("aspect", ["all"])[0],
        "keyword": query.get("keyword", ["all"])[0],
        "trait": query.get("trait", ["all"])[0],
        "arena": query.get("arena", ["all"])[0],
        "rarity": query.get("rarity", ["all"])[0],
        "search": query.get("search", [""])[0],
    }


def official_filter_controls(values: dict[str, list[str]], filters: dict[str, str]) -> str:
    return f"""
<div>
  <label>Search</label>
  <input name="search" value="{esc(filters.get('search', ''))}" placeholder="Name, text, trait, etc.">
</div>
<div>
  <label>Set</label>
  <select name="set">{option_with_all(values['sets'], filters.get('set', 'all'))}</select>
</div>
<div>
  <label>Type</label>
  <select name="type">{option_with_all(values['types'], filters.get('type', 'all'))}</select>
</div>
<div>
  <label>Keyword</label>
  <select name="keyword">{option_with_all(values['keywords'], filters.get('keyword', 'all'))}</select>
</div>
<div>
  <label>Trait</label>
  <select name="trait">{option_with_all(values['traits'], filters.get('trait', 'all'))}</select>
</div>
<div>
  <label>Arena</label>
  <select name="arena">{option_with_all(values['arenas'], filters.get('arena', 'all'))}</select>
</div>
<div>
  <label>Aspect</label>
  <select name="aspect">{option_with_all(values['aspects'], filters.get('aspect', 'all'))}</select>
</div>
<div>
  <label>Rarity</label>
  <select name="rarity">{option_with_all(values['rarities'], filters.get('rarity', 'all'))}</select>
</div>
"""


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


def _semantic_review_blockers(record: dict) -> list[str]:
    blockers: list[str] = []
    raw_text = str(record.get("raw_text") or "").lower()
    triggers = record.get("triggers") or []
    steps = [step for trigger in triggers if isinstance(trigger, dict) for step in (trigger.get("steps") or []) if isinstance(step, dict)]

    draw_steps = [step for step in steps if step.get("type") == "draw_cards"]
    if "draw a card" in raw_text:
        if not draw_steps:
            blockers.append("rules text says 'draw a card' but no draw_cards step is present")
        for step in draw_steps:
            if int(step.get("amount") or 0) != 1:
                blockers.append("rules text says 'draw a card' but draw amount is not 1")
            target = step.get("target") or {}
            if target.get("type") != "player" or target.get("controller") not in {"self", "friendly"}:
                blockers.append("draw_cards step should target the acting player")

    self_damage_match = re.search(r"deal\s+(\d+)\s+damage\s+to\s+this unit\b", raw_text)
    if self_damage_match:
        expected = int(self_damage_match.group(1))
        matching_steps = [step for step in steps if step.get("type") == "deal_damage"]
        if not matching_steps:
            blockers.append("rules text says this unit takes damage but no deal_damage step is present")
        for step in matching_steps:
            if int(step.get("amount") or 0) != expected:
                blockers.append(f"rules text says deal {expected} damage to this unit, but saved amount differs")
            target = step.get("target") or {}
            if target.get("controller") != "self" or target.get("type") != "unit":
                blockers.append("rules text says 'this unit' but saved target is not self unit")

    if "attached unit" in raw_text:
        attached_steps = [step for step in steps if (step.get("target") or {}).get("type") == "unit"]
        if not attached_steps:
            blockers.append("rules text says 'attached unit' but no unit-targeting step is present")
        for step in attached_steps:
            target = step.get("target") or {}
            if target.get("filter") != "attached_unit":
                blockers.append("rules text says 'attached unit' but saved target is not using attached_unit")

    if "all ground units" in raw_text or "all space units" in raw_text:
        for step in steps:
            target = step.get("target") or {}
            if target.get("filter") in {"ground", "space"}:
                blockers.append("rules text affects all units in an arena, but the saved record still targets only one unit")
                break

    token_match = re.search(r"create\s+(?:an?|one|two|\d+)?\s*([a-z0-9' -]+?)\s+token\b", raw_text)
    if token_match:
        expected = " ".join(token_match.group(1).split()).strip()
        create_steps = [step for step in steps if step.get("type") == "create_token"]
        if not create_steps:
            blockers.append("rules text creates a token but no create_token step is present")
        for step in create_steps:
            token_name = str(step.get("token_name") or "").lower()
            if expected and expected not in token_name:
                blockers.append(f"rules text creates a {expected} token, but token_name does not match")

    return blockers


def approval_blockers(record: dict) -> list[str]:
    report = validate_effect_record(record)
    blockers: list[str] = []
    if not report.get("valid", False):
        blockers.extend(report.get("errors") or [])
    if report.get("execution_analysis", {}).get("status") != "executable":
        blockers.extend(report.get("execution_analysis", {}).get("blockers") or [])
    blockers.extend(_semantic_review_blockers(record))
    return blockers


def validation_summary_html(record: dict) -> str:
    report = validate_effect_record(record)
    runtime = report.get("execution_analysis", {})
    parts = [
        f"<p><strong>Schema valid:</strong> {'yes' if report.get('valid') else 'no'}</p>",
        f"<p><strong>Runtime status:</strong> {esc(runtime.get('status', 'manual'))}</p>",
    ]
    errors = report.get("errors") or []
    blockers = runtime.get("blockers") or []
    warnings = report.get("warnings") or []
    if errors:
        parts.append("<p><strong>Schema errors:</strong></p><ul>" + "".join(f"<li>{esc(error)}</li>" for error in errors) + "</ul>")
    if blockers:
        parts.append("<p><strong>Runtime blockers:</strong></p><ul>" + "".join(f"<li>{esc(blocker)}</li>" for blocker in blockers) + "</ul>")
    if warnings:
        parts.append("<p><strong>Warnings:</strong></p><ul>" + "".join(f"<li>{esc(warning)}</li>" for warning in warnings) + "</ul>")
    return "".join(parts)


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


def cards_page(query: dict[str, list[str]]) -> bytes:
    analysis = analyze_card_database(DEFAULT_GAMEPLAY_OUTPUT_PATH)
    support = analysis["support_counts"]
    cards = sorted(_load_card_index().values(), key=card_sort_key)
    filter_values = official_filter_values(cards)
    filters = official_filters_from_query(query)
    support_filter = query.get("support", ["all"])[0]
    limit = parse_positive_int(query.get("limit", ["100"])[0], 100, 500)
    effects = load_effects()
    filtered_cards = []
    for card in cards:
        if not card_matches_official_filters(card, filters):
            continue
        audit = _audit_card(card, count=1, trained_effects=effects)
        if support_filter != "all" and audit.status != support_filter:
            continue
        filtered_cards.append((card, audit))

    filtered_rows = "".join(
        "<tr>"
        f"<td>{esc(card.get('Set'))} {esc(card.get('Number'))}</td>"
        f"<td>{esc(card.get('Name'))}<br><span class='muted'>{esc(card.get('Type'))}</span></td>"
        f"<td>{esc(', '.join(card.get('Keywords') or []) or 'none')}</td>"
        f"<td>{esc(', '.join(card.get('Traits') or []) or 'none')}</td>"
        f"<td>{esc(', '.join(card.get('Arenas') or []) or 'none')}</td>"
        f"<td class='status-{esc(audit.status)}'>{esc(audit.status)}</td>"
        f"<td><a class='button secondary' href='/train?card={esc(card.get('Set'))}-{esc(card.get('Number'))}'>Train</a></td>"
        "</tr>"
        for card, audit in filtered_cards[:limit]
    ) or "<tr><td colspan='7'>No cards match these filters.</td></tr>"
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
<section class="card">
  <h3>Official-Style Card Filters</h3>
  <form method="get" action="/cards">
    <div class="inline-field">
      {official_filter_controls(filter_values, filters)}
      <div>
        <label>Support</label>
        <select name="support">{option_with_all(["supported", "partial", "unsupported"], support_filter)}</select>
      </div>
      <div>
        <label>Limit</label>
        <input name="limit" type="number" min="1" max="500" value="{esc(limit)}">
      </div>
    </div>
    <button type="submit">Apply Filters</button>
    <a class="button secondary" href="/cards">Clear</a>
  </form>
</section>
<section class="grid">
  <div class="card"><h3>Total Cards</h3><div class="metric">{analysis['total_cards']}</div></div>
  <div class="card"><h3>Supported</h3><div class="metric">{support.get('supported', 0)}</div></div>
  <div class="card"><h3>Partial</h3><div class="metric">{support.get('partial', 0)}</div></div>
  <div class="card"><h3>Unsupported</h3><div class="metric">{support.get('unsupported', 0)}</div></div>
  <div class="card"><h3>Filtered</h3><div class="metric">{len(filtered_cards)}</div><p>Showing up to {limit} cards.</p></div>
</section>
<section class="card">
  <h3>Filtered Cards</h3>
  <table>
    <thead><tr><th>Card</th><th>Name</th><th>Keywords</th><th>Traits</th><th>Arenas</th><th>Support</th><th>Action</th></tr></thead>
    <tbody>{filtered_rows}</tbody>
  </table>
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


def draft_review_bucket(record: dict) -> str:
    triggers = record.get("triggers") or []
    if triggers and isinstance(triggers[0], dict):
        steps = triggers[0].get("steps") or []
        if steps and isinstance(steps[0], dict) and steps[0].get("type"):
            return str(steps[0]["type"])
        if triggers[0].get("event"):
            return str(triggers[0]["event"])
    return "unclassified"


def batch_review_records(
    triage_filter: str,
    runtime_filter: str,
    bucket_filter: str,
    approval_filter: str,
    limit: int,
    card_filters: dict[str, str],
) -> tuple[list[dict], dict[str, int], list[tuple[str, int, int]]]:
    effects = load_effects()
    card_index = _load_card_index()
    items: list[dict] = []
    summary: Counter = Counter()

    for key, record in sorted(effects.items()):
        if str(record.get("status") or "draft") != "draft":
            continue
        set_code = str(record.get("set") or "").upper()
        number = str(record.get("number") or "")
        card = card_index.get((set_code, number))
        if card and card_filters and not card_matches_official_filters(card, card_filters):
            continue

        triage = str(record.get("review", {}).get("triage") or "unclassified")
        runtime = str(record.get("execution_status") or execution_status_for_record(record) or "manual")
        bucket = draft_review_bucket(record)
        blockers = approval_blockers(record)
        approval_state = "approvable" if not blockers else "blocked"
        parse_warnings = record.get("review", {}).get("parse_warnings") or []
        display_name = str(record.get("name") or (card.get("Name") if card else key))
        display_type = str(record.get("type") or (card.get("Type") if card else "Unknown"))

        if triage_filter != "all" and triage != triage_filter:
            continue
        if runtime_filter != "all" and runtime != runtime_filter:
            continue
        if bucket_filter != "all" and bucket != bucket_filter:
            continue
        if approval_filter != "all" and approval_state != approval_filter:
            continue

        item = {
            "key": key,
            "name": display_name,
            "type": display_type,
            "card": card,
            "record": record,
            "triage": triage,
            "runtime": runtime,
            "bucket": bucket,
            "blockers": blockers,
            "approval_state": approval_state,
            "parse_warning_count": len(parse_warnings),
            "updated_at": str(record.get("updated_at") or ""),
        }
        items.append(item)
        summary["total"] += 1
        summary[approval_state] += 1
        summary[f"triage:{triage}"] += 1
        summary[f"runtime:{runtime}"] += 1
        summary[f"bucket:{bucket}"] += 1

    items.sort(
        key=lambda item: (
            0 if item["approval_state"] == "approvable" else 1,
            0 if item["triage"] == "safe_draft" else 1,
            item["bucket"],
            item["key"],
        )
    )
    items = items[:limit]

    bucket_rows = []
    bucket_names = sorted({item["bucket"] for item in items})
    for bucket in bucket_names:
        bucket_items = [item for item in items if item["bucket"] == bucket]
        approvable = sum(1 for item in bucket_items if item["approval_state"] == "approvable")
        bucket_rows.append((bucket, len(bucket_items), approvable))

    return items, dict(summary), bucket_rows


def safe_list_items(
    max_words: int,
    limit: int,
    card_filters: dict[str, str],
    only_missing: bool = True,
) -> list[dict]:
    effects = load_effects()
    items = []
    for entry in simple_llm_candidates(max_words=max_words, limit=None):
        card = entry["card"]
        if card_filters and not card_matches_official_filters(card, card_filters):
            continue
        training_status = card_training_status(card, effects)
        if only_missing and training_status != "missing":
            continue
        items.append({
            **entry,
            "training_status": training_status,
            "audit": _audit_card(card, count=1, trained_effects=effects),
        })
        if len(items) >= limit:
            break
    return items


def _archive_superseded_draft(existing: dict | None, record: dict, reason: str) -> None:
    if not existing or existing.get("status") != "draft":
        return
    existing_json = json.dumps(existing, sort_keys=True)
    new_json = json.dumps(record, sort_keys=True)
    if existing_json != new_json:
        save_draft_artifact(existing, reason=reason)


def approve_batch_records(selected_keys: list[str]) -> dict[str, object]:
    effects = load_effects()
    results: dict[str, object] = {
        "approved": [],
        "blocked": {},
        "missing": [],
    }

    for key in selected_keys:
        record = effects.get(key)
        if not record:
            results["missing"].append(key)
            continue

        blockers = approval_blockers(record)
        if blockers:
            results["blocked"][key] = blockers
            continue

        save_draft_artifact(record, reason="Approved via batch review UI")
        updated = deepcopy(record)
        updated["status"] = "approved"
        updated.setdefault("review", {})
        updated["review"]["human_verified"] = True
        notes = str(updated["review"].get("notes") or "").strip()
        approval_note = "Approved via batch review UI."
        if approval_note not in notes:
            updated["review"]["notes"] = f"{notes}\n{approval_note}".strip()
        save_effect(updated)
        results["approved"].append(key)

    return results


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
    return training_queue_items_filtered(scope, status_filter, "all", limit, {})


def training_queue_items_filtered(
    scope: str,
    status_filter: str,
    training_filter: str,
    limit: int,
    card_filters: dict[str, str],
) -> list[dict]:
    index = _load_card_index()
    effects = load_effects()
    usage = deck_usage_counts()
    competitive_usage = competitive_usage_counters()
    competitive_main_counts = competitive_usage["main_counts"]
    competitive_sideboard_counts = competitive_usage["sideboard_counts"]
    competitive_deck_counts = competitive_usage["deck_counts"]
    items = []

    for card in index.values():
        if card_filters and not card_matches_official_filters(card, card_filters):
            continue
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
        if training_filter != "all":
            if training_filter == "missing" and training_status != "missing":
                continue
            if training_filter == "draft" and training_status != "draft":
                continue
            if training_filter == "approved" and not training_status.startswith("approved/"):
                continue
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
    training_filter = query.get("training", ["missing"])[0]
    limit = parse_positive_int(query.get("limit", ["100"])[0], 100, 500)
    card_filters = official_filters_from_query(query)
    filter_values = official_filter_values(list(_load_card_index().values()))
    items = training_queue_items_filtered(scope, status_filter, training_filter, limit, card_filters)
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
            f"<td><a class='button secondary' href='{train_href}'>Review</a> <a class='button' href='{draft_href}'>Heuristic Draft</a> <a class='button' href='{ollama_draft_href}'>Ollama Draft</a> <a class='button' href='{local_draft_href}'>Configured Local Draft</a></td>"
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
        <label>Audit</label>
        <select name="status">{options(["needs_work", "unsupported", "partial", "missing", "all"], status_filter)}</select>
      </div>
      <div>
        <label>Training</label>
        <select name="training">{options(["missing", "draft", "approved", "all"], training_filter)}</select>
      </div>
      <div>
        <label>Limit</label>
        <input name="limit" type="number" min="1" max="500" value="{esc(limit)}">
      </div>
      {official_filter_controls(filter_values, card_filters)}
    </div>
    <button type="submit">Refresh Queue</button>
    <a class="button secondary" href="/queue">Clear</a>
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


def batch_review_page(query: dict[str, list[str]]) -> bytes:
    triage_filter = query.get("triage", ["all"])[0]
    runtime_filter = query.get("runtime", ["executable"])[0]
    approval_filter = query.get("approval", ["approvable"])[0]
    bucket_filter = query.get("bucket", ["all"])[0]
    limit = parse_positive_int(query.get("limit", ["100"])[0], 100, 500)
    safe_limit = parse_positive_int(query.get("safe_limit", ["20"])[0], 20, 200)
    safe_max_words = parse_positive_int(query.get("safe_max_words", ["10"])[0], 10, 50)
    safe_only_missing = query.get("safe_only_missing", ["1"])[0] == "1"
    card_filters = official_filters_from_query(query)
    cards = list(_load_card_index().values())
    filter_values = official_filter_values(cards)
    items, summary, bucket_rows = batch_review_records(
        triage_filter=triage_filter,
        runtime_filter=runtime_filter,
        bucket_filter=bucket_filter,
        approval_filter=approval_filter,
        limit=limit,
        card_filters=card_filters,
    )
    safe_items = safe_list_items(
        max_words=safe_max_words,
        limit=safe_limit,
        card_filters=card_filters,
        only_missing=safe_only_missing,
    )
    bucket_options = sorted({row[0] for row in bucket_rows})
    summary_rows = "".join(
        f"<tr><td>{esc(bucket)}</td><td>{count}</td><td>{approvable}</td><td>{pct(approvable, count)}</td></tr>"
        for bucket, count, approvable in bucket_rows
    ) or "<tr><td colspan='4'>No draft buckets match the current filter.</td></tr>"

    item_rows = []
    for item in items:
        card = item["card"] or {}
        card_ref = f"{card.get('Set') or item['record'].get('set')} {card.get('Number') or item['record'].get('number')}"
        train_href = f"/train?card={esc(item['key'])}"
        blocker_html = (
            "<ul>" + "".join(f"<li>{esc(blocker)}</li>" for blocker in item["blockers"][:3]) + "</ul>"
            if item["blockers"]
            else "<span class='status-supported'>ready</span>"
        )
        search_text = " ".join(
            [
                str(card_ref),
                str(item["name"]),
                str(item["type"]),
                str(item["bucket"]),
                str(item["triage"]),
                str(item["runtime"]),
                str(item["approval_state"]),
                " ".join(item["blockers"]),
            ]
        )
        row_html = (
            "<tr>"
            f"<td><input type='checkbox' name='cards' value='{esc(item['key'])}' {'disabled' if item['approval_state'] != 'approvable' else ''} style='width:auto'></td>"
            f"<td>{esc(card_ref)}</td>"
            f"<td>{esc(item['name'])}<br><span class='muted'>{esc(item['type'])}</span></td>"
            f"<td>{esc(item['bucket'])}</td>"
            f"<td>{esc(item['triage'])}</td>"
            f"<td>{esc(item['runtime'])}</td>"
            f"<td>{esc(item['approval_state'])}</td>"
            f"<td>{item['parse_warning_count']}</td>"
            f"<td>{blocker_html}</td>"
            f"<td><a class='button secondary' href='{train_href}'>Review</a></td>"
            "</tr>"
        ).replace(
            "<tr>",
            f"<tr class='batch-review-row' data-search='{esc(search_text)}'>",
            1,
        )
        item_rows.append(row_html)
    review_rows = "\n".join(item_rows) or "<tr><td colspan='10'>No drafts match this batch review filter.</td></tr>"
    safe_rows = []
    for item in safe_items:
        card = item["card"]
        selected = f"{card.get('Set')}-{card.get('Number')}"
        train_href = f"/train?card={esc(selected)}"
        local_draft_href = f"/train/suggest?card={esc(selected)}&provider=local"
        safe_rows.append(
            "<tr>"
            f"<td>{esc(item['key'])}</td>"
            f"<td>{esc(item['title'])}<br><span class='muted'>{esc(item['type'])}</span></td>"
            f"<td>{esc(item['bucket'])}</td>"
            f"<td>{item['words']}</td>"
            f"<td>{esc(item['training_status'])}</td>"
            f"<td>{esc(item['text'])}</td>"
            f"<td><a class='button' href='{local_draft_href}'>Configured Local Draft</a> <a class='button secondary' href='{train_href}'>Review</a></td>"
            "</tr>"
        )
    safe_table_rows = "\n".join(safe_rows) or "<tr><td colspan='7'>No safe-list cards match the current filters.</td></tr>"

    hidden_filter_fields = "".join(
        f"<input type='hidden' name='{esc(name)}' value='{esc(value)}'>"
        for name, value in {
            "triage": triage_filter,
            "runtime": runtime_filter,
            "approval": approval_filter,
            "bucket": bucket_filter,
            "limit": str(limit),
            "safe_limit": str(safe_limit),
            "safe_max_words": str(safe_max_words),
            "safe_only_missing": "1" if safe_only_missing else "0",
            **card_filters,
        }.items()
    )

    body = f"""
<section><h2>Batch Review And Approval</h2><p>Review local-model drafts in grouped batches, then approve only the drafts that clear the same validation and semantic blockers used by the single-card workflow.</p></section>
<section class="card">
  <form method="get" action="/batch">
    <div class="inline-field">
      <div>
        <label>Triage</label>
        <select name="triage">{option_with_all(["safe_draft", "needs_review", "unresolved", "unclassified"], triage_filter)}</select>
      </div>
      <div>
        <label>Runtime</label>
        <select name="runtime">{option_with_all(["executable", "partial", "manual"], runtime_filter)}</select>
      </div>
      <div>
        <label>Approval</label>
        <select name="approval">{option_with_all(["approvable", "blocked"], approval_filter)}</select>
      </div>
      <div>
        <label>Bucket</label>
        <select name="bucket">{option_with_all(bucket_options, bucket_filter)}</select>
      </div>
      <div>
        <label>Limit</label>
        <input name="limit" type="number" min="1" max="500" value="{esc(limit)}">
      </div>
      {official_filter_controls(filter_values, card_filters)}
    </div>
    <button type="submit">Refresh Batch View</button>
    <a class="button secondary" href="/batch">Clear</a>
  </form>
</section>
<section class="card">
  <h3>Safe List Generation</h3>
  <p class="muted">Generate the next low-risk unsupported cards for local drafting using the same simple queue rules as the CLI. Excluded keywords: {esc(', '.join(sorted(SIMPLE_LLM_BLOCKED_KEYWORDS)))}. Excluded phrases: {esc(', '.join(SIMPLE_LLM_BLOCKED_PHRASES))}.</p>
  <form method="get" action="/batch">
    <div class="inline-field">
      <div>
        <label>Safe List Limit</label>
        <input name="safe_limit" type="number" min="1" max="200" value="{esc(safe_limit)}">
      </div>
      <div>
        <label>Max Words</label>
        <input name="safe_max_words" type="number" min="1" max="50" value="{esc(safe_max_words)}">
      </div>
      <div>
        <label>Existing Records</label>
        <select name="safe_only_missing">{options(["1", "0"], "1" if safe_only_missing else "0")}</select>
      </div>
      {official_filter_controls(filter_values, card_filters)}
    </div>
    <input type="hidden" name="triage" value="{esc(triage_filter)}">
    <input type="hidden" name="runtime" value="{esc(runtime_filter)}">
    <input type="hidden" name="approval" value="{esc(approval_filter)}">
    <input type="hidden" name="bucket" value="{esc(bucket_filter)}">
    <input type="hidden" name="limit" value="{esc(limit)}">
    <button type="submit">Generate Safe List</button>
  </form>
  <form method="post" action="/batch/draft-safe">
    <input type="hidden" name="safe_limit" value="{esc(safe_limit)}">
    <input type="hidden" name="safe_max_words" value="{esc(safe_max_words)}">
    <input type="hidden" name="safe_only_missing" value="{'1' if safe_only_missing else '0'}">
    <input type="hidden" name="triage" value="{esc(triage_filter)}">
    <input type="hidden" name="runtime" value="{esc(runtime_filter)}">
    <input type="hidden" name="approval" value="{esc(approval_filter)}">
    <input type="hidden" name="bucket" value="{esc(bucket_filter)}">
    <input type="hidden" name="limit" value="{esc(limit)}">
    {''.join(f"<input type='hidden' name='{esc(name)}' value='{esc(value)}'>" for name, value in card_filters.items())}
    <button type="submit">Process Safe List With Configured Local LLM</button>
  </form>
  <table>
    <thead><tr><th>Card</th><th>Name</th><th>Bucket</th><th>Words</th><th>Training</th><th>Rules Text</th><th>Actions</th></tr></thead>
    <tbody>{safe_table_rows}</tbody>
  </table>
</section>
<section class="grid">
  <div class="card"><h3>Filtered Drafts</h3><div class="metric">{summary.get('total', 0)}</div></div>
  <div class="card"><h3>Approvable</h3><div class="metric">{summary.get('approvable', 0)}</div></div>
  <div class="card"><h3>Blocked</h3><div class="metric">{summary.get('blocked', 0)}</div></div>
  <div class="card"><h3>Safe Draft</h3><div class="metric">{summary.get('triage:safe_draft', 0)}</div></div>
  <div class="card"><h3>Executable</h3><div class="metric">{summary.get('runtime:executable', 0)}</div></div>
  <div class="card"><h3>Safe List</h3><div class="metric">{len(safe_items)}</div></div>
</section>
<section class="card">
  <h3>Bucket Summary</h3>
  <table>
    <thead><tr><th>Bucket</th><th>Drafts</th><th>Approvable</th><th>Approvable %</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>
</section>
<section class="card">
  <form method="post" action="/batch/approve">
    {hidden_filter_fields}
    <button type="submit">Approve Selected Drafts</button>
    <p class="muted">Only rows without blockers can be selected. Each approved card archives the prior draft snapshot before promotion.</p>
    <div class="table-toolbar">
      <div class="grow">
        <label for="batch-row-filter">Filter Visible Rows</label>
        <input id="batch-row-filter" type="search" placeholder="Filter by card, name, bucket, triage, runtime, blockers">
      </div>
      <div>
        <label><input id="batch-select-visible" type="checkbox" style="width:auto"> Select all shown</label>
      </div>
    </div>
    <table>
      <thead><tr><th>Select</th><th>Card</th><th>Name</th><th>Bucket</th><th>Triage</th><th>Runtime</th><th>Approval</th><th>Warnings</th><th>Blockers</th><th>Action</th></tr></thead>
      <tbody id="batch-review-rows">{review_rows}</tbody>
    </table>
  </form>
</section>
<script>
(() => {{
  const filterInput = document.getElementById("batch-row-filter");
  const selectVisible = document.getElementById("batch-select-visible");
  const rows = Array.from(document.querySelectorAll("#batch-review-rows .batch-review-row"));

  function visibleRows() {{
    return rows.filter((row) => !row.hidden);
  }}

  function syncSelectVisible() {{
    const candidates = visibleRows()
      .map((row) => row.querySelector("input[name='cards']"))
      .filter((input) => input && !input.disabled);
    if (!candidates.length) {{
      selectVisible.checked = false;
      selectVisible.indeterminate = false;
      return;
    }}
    const checkedCount = candidates.filter((input) => input.checked).length;
    selectVisible.checked = checkedCount === candidates.length;
    selectVisible.indeterminate = checkedCount > 0 && checkedCount < candidates.length;
  }}

  function applyFilter() {{
    const query = (filterInput.value || "").trim().toLowerCase();
    rows.forEach((row) => {{
      const haystack = (row.dataset.search || "").toLowerCase();
      row.hidden = query !== "" && !haystack.includes(query);
    }});
    syncSelectVisible();
  }}

  filterInput?.addEventListener("input", applyFilter);
  selectVisible?.addEventListener("change", () => {{
    visibleRows().forEach((row) => {{
      const input = row.querySelector("input[name='cards']");
      if (input && !input.disabled) {{
        input.checked = selectVisible.checked;
      }}
    }});
    syncSelectVisible();
  }});
  rows.forEach((row) => {{
    const input = row.querySelector("input[name='cards']");
    input?.addEventListener("change", syncSelectVisible);
  }});
  applyFilter();
}})();
</script>
"""
    return page("Batch Review", body)


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
    current_record = current_effect or default_effect
    execution_status = current_record.get("execution_status", "manual")
    review = current_record.get("review", {})
    triage = review.get("triage", "")
    parse_warnings = review.get("parse_warnings") or []
    source = (current_effect or default_effect).get("source", "")
    validation_html = validation_summary_html(current_record) if selected_card else ""
    current_status = current_record.get("status", "draft")
    current_confidence = review.get("confidence", "medium")
    current_trigger = ((current_record.get("triggers") or [{}])[0]).get("event", "when_played")
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
    <p><strong>Saved status:</strong> {esc(current_status)}</p>
    <p><strong>Execution status:</strong> {esc(execution_status)}</p>
    {source_html}
    {triage_html}
    {warnings_html}
    {validation_html}
    <pre>{esc(text or 'No rules text')}</pre>
    <p class="muted">Draft sources: heuristic rules-text parser, OpenAI, forced Ollama, or the provider configured in your local settings.</p>
    <a class="button secondary" href="{draft_href}">Heuristic Draft</a>
    <a class="button" href="{llm_href}">OpenAI Draft</a>
    <a class="button" href="{ollama_llm_href}">Ollama Draft</a>
    <a class="button" href="{local_llm_href}">Configured Local Draft</a>
  </div>
</section>
<section>
  <h3>Complex Effect Builder</h3>
  <form method="post" action="/train/guided-save">
    <input type="hidden" name="card" value="{esc(selected)}">
    <div class="inline-field">
      <div>
        <label>Status</label>
        <select name="status">{options(["draft", "approved"], current_status)}</select>
      </div>
      <div>
        <label>Engine Execution</label>
        <select name="execution_status">{options(EXECUTION_STATUSES, execution_status)}</select>
      </div>
      <div>
        <label>Reviewer Confidence</label>
        <select name="confidence">{options(["low", "medium", "high"], current_confidence)}</select>
      </div>
      <div>
        <label>Trigger</label>
        <select name="trigger">{options(TRIGGERS, current_trigger)}</select>
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
          <select name="status">{options(["draft", "approved"], current_status)}</select>
        </div>
        <div>
          <label>Trigger</label>
          <select name="trigger">{options(["when_played", "on_attack", "when_defeated", "action"], current_trigger if current_trigger in {"when_played", "on_attack", "when_defeated", "action"} else "when_played")}</select>
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
        if data.get("status") == "approved":
            blockers = approval_blockers(data)
            if blockers:
                raise ValueError("Cannot approve this effect until blockers are fixed:\n- " + "\n- ".join(blockers))
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
        if data.get("status") == "approved":
            blockers = approval_blockers(data)
            if blockers:
                raise ValueError("Cannot approve this effect until blockers are fixed:\n- " + "\n- ".join(blockers))
        save_effect(data)
        message = (
            "<section class='card'><h2>Guided Effect Saved</h2>"
            f"<pre>{esc(json.dumps(data, indent=2))}</pre>"
            f"<a class='button secondary' href='/train?card={esc(selected)}'>Back</a></section>"
        )
    except Exception as exc:
        message = f"<section class='card'><h2>Could Not Save</h2><p>{esc(exc)}</p><a class='button secondary' href='/train'>Back</a></section>"
    return page("Save Guided Effect", message)


def batch_approve(post_body: str) -> bytes:
    fields = parse_qs(post_body)
    selected_keys = fields.get("cards", [])
    try:
        if not selected_keys:
            raise ValueError("Select at least one approvable draft to batch approve.")
        results = approve_batch_records(selected_keys)
        approved = results["approved"]
        blocked = results["blocked"]
        missing = results["missing"]
        blocked_html = ""
        if blocked:
            blocked_html = "<h3>Blocked</h3><ul>" + "".join(
                f"<li>{esc(key)}: {esc('; '.join(reasons))}</li>"
                for key, reasons in blocked.items()
            ) + "</ul>"
        missing_html = ""
        if missing:
            missing_html = "<h3>Missing</h3><ul>" + "".join(f"<li>{esc(key)}</li>" for key in missing) + "</ul>"
        message = (
            "<section class='card'><h2>Batch Approval Complete</h2>"
            f"<p><strong>Approved:</strong> {len(approved)}</p>"
            f"<p><strong>Blocked:</strong> {len(blocked)}</p>"
            f"<p><strong>Missing:</strong> {len(missing)}</p>"
            + ("<h3>Approved Keys</h3><ul>" + "".join(f"<li>{esc(key)}</li>" for key in approved) + "</ul>" if approved else "")
            + blocked_html
            + missing_html
            + "<a class='button secondary' href='/batch'>Back To Batch Review</a></section>"
        )
    except Exception as exc:
        message = f"<section class='card'><h2>Could Not Batch Approve</h2><p>{esc(exc)}</p><a class='button secondary' href='/batch'>Back</a></section>"
    return page("Batch Approval", message)


def batch_draft_safe(post_body: str) -> bytes:
    fields = parse_qs(post_body)
    safe_limit = parse_positive_int(fields.get("safe_limit", ["20"])[0], 20, 200)
    safe_max_words = parse_positive_int(fields.get("safe_max_words", ["10"])[0], 10, 50)
    safe_only_missing = fields.get("safe_only_missing", ["1"])[0] == "1"
    card_filters = official_filters_from_query(fields)
    try:
        items = safe_list_items(
            max_words=safe_max_words,
            limit=safe_limit,
            card_filters=card_filters,
            only_missing=safe_only_missing,
        )
        if not items:
            raise ValueError("No safe-list cards match the current filters.")
        provider = get_effect_suggestion_provider("local")
        drafted: list[tuple[str, str, str]] = []
        failed: list[tuple[str, str]] = []
        for item in items:
            card = item["card"]
            key = item["key"]
            try:
                record = provider.suggest_effect(card)
                existing = get_effect(card.get("Set"), card.get("Number"))
                _archive_superseded_draft(existing, record, "Superseded by Batch Review safe-list local draft")
                save_effect(record)
                drafted.append(
                    (
                        key,
                        record.get("review", {}).get("triage", "needs_review"),
                        record.get("execution_status", ""),
                    )
                )
            except EffectSuggestionError as exc:
                failed.append((key, f"{exc.title}: {exc.detail}"))
            except Exception as exc:
                failed.append((key, str(exc)))
        drafted_html = ""
        if drafted:
            drafted_html = (
                "<h3>Drafted</h3><ul>"
                + "".join(
                    f"<li>{esc(key)}: triage={esc(triage)}, runtime={esc(runtime or 'unknown')}</li>"
                    for key, triage, runtime in drafted
                )
                + "</ul>"
            )
        failed_html = ""
        if failed:
            failed_html = (
                "<h3>Failures</h3><ul>"
                + "".join(f"<li>{esc(key)}: {esc(detail)}</li>" for key, detail in failed)
                + "</ul>"
            )
        message = (
            "<section class='card'><h2>Safe List Drafting Complete</h2>"
            f"<p><strong>Processed:</strong> {len(items)}</p>"
            f"<p><strong>Drafted:</strong> {len(drafted)}</p>"
            f"<p><strong>Failures:</strong> {len(failed)}</p>"
            f"{drafted_html}"
            f"{failed_html}"
            "<a class='button secondary' href='/batch'>Back To Batch Review</a></section>"
        )
    except EffectSuggestionError as exc:
        actions = "".join(f"<li>{esc(action)}</li>" for action in exc.actions)
        action_block = f"<ul>{actions}</ul>" if actions else ""
        message = (
            f"<section class='card'><h2>{esc(exc.title)}</h2>"
            f"<p>{esc(exc.detail)}</p>"
            f"{action_block}"
            f"<a class='button secondary' href='/batch'>Back</a></section>"
        )
    except Exception as exc:
        message = f"<section class='card'><h2>Could Not Draft Safe List</h2><p>{esc(exc)}</p><a class='button secondary' href='/batch'>Back</a></section>"
    return page("Safe List Drafting", message)


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
            "/cards": lambda: cards_page(query),
            "/queue": lambda: training_queue_page(query),
            "/batch": lambda: batch_review_page(query),
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
        if self.path == "/batch/approve":
            self._send(batch_approve(body))
            return
        if self.path == "/batch/draft-safe":
            self._send(batch_draft_safe(body))
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
