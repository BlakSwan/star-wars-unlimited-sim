#!/usr/bin/env python3
"""Star Wars Unlimited Simulator - Main Entry Point"""

import argparse
import sys
from collections import Counter

from card_analysis import analyze_card_database, format_card_analysis
from competitive_decks import COMPETITIVE_DECKS_PATH, write_hot_competitive_decks
from deck_loader import _load_card_cache, available_decks
from effect_audit import audit_deck, format_deck_audit
from effect_store import effect_key, load_effects, save_effect, save_unresolved_card
from effect_training import EffectSuggestionError, LocalEffectSuggestionProvider, get_effect_suggestion_provider
from simulator import (
    run_simulation, 
    compare_strategies, 
    run_tournament,
    analyze_strategy_performance,
    quick_test
)
from strategies import list_strategies
from swu_db_client import (
    DEFAULT_GAMEPLAY_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_SET_CODES,
    write_all_cards,
    write_gameplay_cards,
)


def _drafting_provider(args) -> LocalEffectSuggestionProvider:
    provider = get_effect_suggestion_provider(
        "local",
        local_provider=args.local_provider,
        model=args.local_model,
        host=args.local_host,
        timeout=args.local_timeout,
    )
    if not isinstance(provider, LocalEffectSuggestionProvider):
        raise RuntimeError("Local provider factory returned the wrong provider type")
    return provider


def _find_card(set_code: str, number: str) -> dict:
    index = _load_card_cache(DEFAULT_GAMEPLAY_OUTPUT_PATH)
    key = (set_code.upper(), str(number))
    if key not in index:
        raise KeyError(f"Card {set_code.upper()} {number} was not found in gameplay card data")
    return index[key]


def _save_local_draft(card: dict, record: dict, approve_safe_drafts: bool) -> str:
    triage = record.get("review", {}).get("triage", "needs_review")
    if approve_safe_drafts and triage == "safe_draft" and record.get("execution_status") == "executable":
        record["status"] = "approved"
        record.setdefault("review", {})["human_verified"] = False
        notes = record["review"].get("notes", "")
        record["review"]["notes"] = (notes + "\nApproved by conservative CLI safe-draft option; review recommended.").strip()
    save_effect(record)
    if triage == "unresolved":
        save_unresolved_card(card, record.get("review", {}).get("notes", "Local model draft unresolved"))
    return triage


def test_local_provider(args) -> int:
    try:
        provider = _drafting_provider(args)
        status = provider.test()
    except EffectSuggestionError as exc:
        print(f"{exc.title}: {exc.detail}")
        for action in exc.actions:
            print(f"  - {action}")
        return 1
    print("Local provider is ready:")
    for key, value in status.items():
        if key == "available_models":
            print(f"  {key}: {', '.join(value) if value else 'none'}")
        else:
            print(f"  {key}: {value}")
    return 0


def draft_one_local_card(args) -> int:
    set_code, number = args.draft_card
    try:
        card = _find_card(set_code, number)
        record = _drafting_provider(args).suggest_effect(card)
        triage = _save_local_draft(card, record, args.approve_safe_drafts)
    except EffectSuggestionError as exc:
        print(f"{exc.title}: {exc.detail}")
        for action in exc.actions:
            print(f"  - {action}")
        return 1
    except Exception as exc:
        print(f"Could not draft card: {exc}")
        return 1

    print(f"Drafted {card.get('Set')} {card.get('Number')} {card.get('Name')}")
    print(f"  source: {record.get('source')}")
    print(f"  triage: {triage}")
    print(f"  execution_status: {record.get('execution_status')}")
    print("  status: approved" if record.get("status") == "approved" else "  status: draft")
    return 0


def bulk_draft_local_cards(args) -> int:
    try:
        provider = _drafting_provider(args)
        index = _load_card_cache(DEFAULT_GAMEPLAY_OUTPUT_PATH)
        effects = load_effects()
    except Exception as exc:
        print(f"Could not prepare local drafting: {exc}")
        return 1

    selected_sets = {set_code.upper() for set_code in (args.sets or [])}
    summary: Counter = Counter()
    errors: list[str] = []

    cards = sorted(index.values(), key=lambda card: (str(card.get("Set") or ""), str(card.get("Number") or "")))
    for card in cards:
        if selected_sets and str(card.get("Set") or "").upper() not in selected_sets:
            continue
        if args.limit and summary["scanned"] >= args.limit:
            break

        summary["scanned"] += 1
        key = effect_key(str(card.get("Set") or ""), str(card.get("Number") or ""))
        existing = effects.get(key)
        if existing:
            if args.only_missing or existing.get("status") == "approved":
                summary["skipped_existing"] += 1
                continue
            if existing.get("status") == "draft" and not args.overwrite_drafts:
                summary["skipped_existing"] += 1
                continue

        try:
            record = provider.suggest_effect(card)
            triage = _save_local_draft(card, record, args.approve_safe_drafts)
            effects[key] = record
            summary["drafts_created"] += 1
            summary[triage] += 1
        except EffectSuggestionError as exc:
            summary["provider_errors"] += 1
            errors.append(f"{key}: {exc.title} - {exc.detail}")
            break
        except Exception as exc:
            summary["errors"] += 1
            errors.append(f"{key}: {exc}")

    print("Local drafting summary:")
    for key in ("scanned", "drafts_created", "safe_draft", "needs_review", "unresolved", "skipped_existing", "provider_errors", "errors"):
        print(f"  {key}: {summary[key]}")
    if errors:
        print("Errors:")
        for error in errors[:10]:
            print(f"  - {error}")
    return 1 if summary["provider_errors"] else 0


def main():
    parser = argparse.ArgumentParser(
        description="Star Wars Unlimited Card Game Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --test                          # Quick test (10 games)
  python main.py --sim aggressive control 100    # Simulate aggressive vs control
  python main.py --compare                       # Compare all strategies
  python main.py --tournament                    # Run tournament
  python main.py --analyze aggressive            # Analyze aggressive strategy
        """
    )
    
    parser.add_argument("--test", action="store_true", 
                        help="Run quick test with 10 games")
    parser.add_argument("--sim", nargs=3, metavar=("STRAT1", "STRAT2", "GAMES"),
                        help="Run simulation: strat1 vs strat2 for N games")
    parser.add_argument("--compare", action="store_true",
                        help="Compare all strategies against each other")
    parser.add_argument("--tournament", action="store_true",
                        help="Run round-robin tournament")
    parser.add_argument("--analyze", metavar="STRATEGY",
                        help="Analyze a strategy against all opponents")
    parser.add_argument("--list", action="store_true",
                        help="List available strategies")
    parser.add_argument("--list-decks", action="store_true",
                        help="List bundled deck names")
    parser.add_argument("--deck1",
                        help="Deck name or JSON path for player 1")
    parser.add_argument("--deck2",
                        help="Deck name or JSON path for player 2")
    parser.add_argument("--audit-deck",
                        help="Audit a deck for unsupported simulator effects")
    parser.add_argument("--show-supported", action="store_true",
                        help="Include supported cards in --audit-deck output")
    parser.add_argument("--fetch-cards", nargs="?", const=str(DEFAULT_OUTPUT_PATH),
                        metavar="OUTPUT",
                        help="Fetch all known SWU DB card data to JSON")
    parser.add_argument("--sets", nargs="+", metavar="SET",
                        help="Set codes to fetch or draft, e.g. SOR SHD TWI")
    parser.add_argument("--filter-gameplay-cards", nargs="?", const=str(DEFAULT_GAMEPLAY_OUTPUT_PATH),
                        metavar="OUTPUT",
                        help="Collapse cosmetic variants from fetched card data")
    parser.add_argument("--card-input", default=str(DEFAULT_OUTPUT_PATH),
                        help="Input JSON for --filter-gameplay-cards")
    parser.add_argument("--analyze-cards", action="store_true",
                        help="Analyze card database mechanics and simulator support")
    parser.add_argument("--fetch-competitive-decks", nargs="?", const=str(COMPETITIVE_DECKS_PATH),
                        metavar="OUTPUT",
                        help="Fetch hot SWUDB deck usage JSON for training queue priority")
    parser.add_argument("--competitive-limit", type=int, default=20,
                        help="Deck count for --fetch-competitive-decks")
    parser.add_argument("--ui", action="store_true",
                        help="Start the local web UI")
    parser.add_argument("--ui-port", type=int, default=8765,
                        help="Port for --ui")
    parser.add_argument("--test-local-provider", action="store_true",
                        help="Check local LLM provider setup without drafting cards")
    parser.add_argument("--draft-card", nargs=2, metavar=("SET", "NUMBER"),
                        help="Draft one card effect with the configured local LLM provider")
    parser.add_argument("--draft-local-effects", action="store_true",
                        help="Bulk draft card effects with the configured local LLM provider")
    parser.add_argument("--draft-missing-cards", action="store_true",
                        help="Bulk draft only cards without an existing effect record")
    parser.add_argument("--local-provider", choices=["ollama", "mlx"], default=None,
                        help="Local provider backend for card-effect drafting")
    parser.add_argument("--local-model",
                        help="Local model name or path for card-effect drafting")
    parser.add_argument("--local-host",
                        help="Local provider host, used by Ollama")
    parser.add_argument("--local-timeout", type=int,
                        help="Local provider timeout in seconds")
    parser.add_argument("--only-missing", action="store_true",
                        help="Skip cards that already have effect records during bulk local drafting")
    parser.add_argument("--limit", type=int,
                        help="Maximum card count for bulk local drafting")
    parser.add_argument("--overwrite-drafts", action="store_true",
                        help="Replace existing draft records during bulk local drafting")
    parser.add_argument("--approve-safe-drafts", action="store_true",
                        help="Conservatively approve structurally simple local drafts; off by default")
    
    args = parser.parse_args()
    
    strategies = list_strategies()

    if args.draft_missing_cards:
        args.draft_local_effects = True
        args.only_missing = True

    if args.test_local_provider:
        sys.exit(test_local_provider(args))

    if args.draft_card:
        sys.exit(draft_one_local_card(args))

    if args.draft_local_effects:
        sys.exit(bulk_draft_local_cards(args))
    
    # List strategies
    if args.list:
        print("Available strategies:")
        for s in strategies:
            print(f"  - {s}")
        return

    if args.list_decks:
        print("Available decks:")
        for deck in available_decks():
            print(f"  - {deck}")
        return

    if args.audit_deck:
        audit = audit_deck(args.audit_deck)
        print(format_deck_audit(audit, show_supported=args.show_supported))
        return

    if args.analyze_cards:
        analysis = analyze_card_database(DEFAULT_GAMEPLAY_OUTPUT_PATH)
        print(format_card_analysis(analysis))
        return

    if args.fetch_competitive_decks:
        print(f"Fetching top {args.competitive_limit} hot SWUDB decks...")
        data = write_hot_competitive_decks(args.fetch_competitive_decks, limit=args.competitive_limit)
        print(f"Wrote {data['deck_count']} decks to {args.fetch_competitive_decks}")
        if data["failed"]:
            print("Failed decks:")
            for deck_id, error in data["failed"].items():
                print(f"  - {deck_id}: {error}")
        return

    if args.ui:
        from ui_server import run_ui
        run_ui(port=args.ui_port)
        return

    # Fetch card data from SWU DB
    if args.fetch_cards:
        set_codes = args.sets or DEFAULT_SET_CODES
        print(f"Fetching SWU DB card data for {len(set_codes)} set codes...")
        data = write_all_cards(args.fetch_cards, set_codes=set_codes)
        print(f"Wrote {data['total_cards']} cards to {args.fetch_cards}")
        if data["failed_sets"]:
            print("Failed sets:")
            for set_code, error in data["failed_sets"].items():
                print(f"  - {set_code}: {error}")
        return

    # Build gameplay-only card data
    if args.filter_gameplay_cards:
        data = write_gameplay_cards(args.card_input, args.filter_gameplay_cards)
        print(f"Read {data['total_source_cards']} source card records")
        print(f"Wrote {data['total_cards']} gameplay cards to {args.filter_gameplay_cards}")
        print(f"Removed {data['removed_variants']} cosmetic variants")
        return
    
    # Quick test
    if args.test:
        quick_test()
        return
    
    # Run simulation
    if args.sim:
        strat1, strat2, games = args.sim
        if strat1 not in strategies or strat2 not in strategies:
            print(f"Error: Unknown strategy. Available: {strategies}")
            sys.exit(1)
        if bool(args.deck1) != bool(args.deck2):
            print("Error: Provide both --deck1 and --deck2, or neither.")
            sys.exit(1)
        try:
            num_games = int(games)
        except ValueError:
            print(f"Error: Invalid number of games '{games}'")
            sys.exit(1)
        
        run_simulation(strat1, strat2, num_games, deck1_ref=args.deck1, deck2_ref=args.deck2)
        return
    
    # Compare strategies
    if args.compare:
        compare_strategies(strategies, num_games=50)
        return
    
    # Tournament
    if args.tournament:
        run_tournament(strategies, games_per_match=30)
        return
    
    # Analyze strategy
    if args.analyze:
        strat = args.analyze
        if strat not in strategies:
            print(f"Error: Unknown strategy '{strat}'. Available: {strategies}")
            sys.exit(1)
        
        opponents = [s for s in strategies if s != strat]
        analyze_strategy_performance(strat, opponents, num_games=50)
        return
    
    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
