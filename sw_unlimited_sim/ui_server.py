"""Local web UI for non-coder simulator workflows."""

from __future__ import annotations

import html
import io
import json
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from card_analysis import analyze_card_database
from deck_loader import _load_card_cache, available_decks
from effect_audit import audit_deck, format_deck_audit
from effect_store import get_effect, load_effects, save_effect
from simulator import run_simulation
from strategies import list_strategies
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
    effect_type: str,
    amount: str,
    target_controller: str,
    target_type: str,
    notes: str,
) -> dict:
    step = {
        "type": effect_type,
        "target": {
            "controller": target_controller,
            "type": target_type,
        },
    }
    if amount:
        step["amount"] = int(amount)
    record = {
        "set": card.get("Set"),
        "number": card.get("Number"),
        "name": card.get("Name"),
        "status": status,
        "source": "human_guided_ui",
        "triggers": [
            {
                "event": trigger,
                "steps": [step],
            }
        ],
    }
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


def simulate_page(query: dict[str, list[str]]) -> bytes:
    decks = available_decks()
    strategies = list_strategies()
    deck1 = query.get("deck1", ["rebel_heroism_50" if "rebel_heroism_50" in decks else (decks[0] if decks else "")])[0]
    deck2 = query.get("deck2", ["imperial_villainy_50" if "imperial_villainy_50" in decks else (decks[-1] if decks else "")])[0]
    strat1 = query.get("strategy1", ["aggressive"])[0]
    strat2 = query.get("strategy2", ["aggressive"])[0]
    games = int(query.get("games", ["20"])[0] or 20)
    result = ""

    if query.get("run", [""])[0] == "1":
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            run_simulation(strat1, strat2, games, deck1_ref=deck1, deck2_ref=deck2)
        result = f"<pre>{esc(buffer.getvalue())}</pre>"

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


def _load_card_index():
    return _load_card_cache(DEFAULT_GAMEPLAY_OUTPUT_PATH)


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
    text = "\n".join(str(selected_card.get(field) or "") for field in ("FrontText", "BackText", "EpicAction") if selected_card and selected_card.get(field))
    effect_json = json.dumps(current_effect or {
        "set": selected_card.get("Set") if selected_card else "",
        "number": selected_card.get("Number") if selected_card else "",
        "name": selected_card.get("Name") if selected_card else "",
        "status": "draft",
        "triggers": []
    }, indent=2)
    body = f"""
<section><h2>Train Structured Effects</h2><p>Turn card text into reviewed simulator actions. Use the guided form for common effects, or edit the JSON directly for more complex cards.</p></section>
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
    <pre>{esc(text or 'No rules text')}</pre>
  </div>
</section>
<section class="split">
  <div class="card">
    <h3>Guided Effect Builder</h3>
    <form method="post" action="/train/guided-save">
      <input type="hidden" name="card" value="{esc(selected)}">
      <div class="inline-field">
        <div>
          <label>Status</label>
          <select name="status">{options(["draft", "approved"], "draft")}</select>
        </div>
        <div>
          <label>Trigger</label>
          <select name="trigger">{options(["when_played", "on_attack", "when_defeated", "action", "constant"], "when_played")}</select>
        </div>
      </div>
      <label>Effect</label>
      <select name="effect_type">{options(["deal_damage", "heal_damage", "draw_cards", "discard_cards", "exhaust_unit", "ready_unit", "defeat_unit", "give_shield", "give_experience", "capture_unit"], "deal_damage")}</select>
      <div class="inline-field">
        <div>
          <label>Amount</label>
          <input name="amount" type="number" min="0" value="1">
        </div>
        <div>
          <label>Target Side</label>
          <select name="target_controller">{options(["enemy", "friendly", "self", "any"], "enemy")}</select>
        </div>
        <div>
          <label>Target Type</label>
          <select name="target_type">{options(["unit", "base", "player", "card", "upgrade"], "unit")}</select>
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
        data = build_effect_record(
            card=card,
            status=fields.get("status", ["draft"])[0],
            trigger=fields.get("trigger", ["when_played"])[0],
            effect_type=fields.get("effect_type", ["deal_damage"])[0],
            amount=fields.get("amount", [""])[0],
            target_controller=fields.get("target_controller", ["enemy"])[0],
            target_type=fields.get("target_type", ["unit"])[0],
            notes=fields.get("notes", [""])[0],
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


class UIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        routes = {
            "/": lambda: dashboard(),
            "/audit": lambda: audit_page(query),
            "/simulate": lambda: simulate_page(query),
            "/cards": lambda: cards_page(),
            "/train": lambda: train_page(query),
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
