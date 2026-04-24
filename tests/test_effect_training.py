from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))
GOLDEN_CASES_PATH = ROOT / "tests" / "golden_effect_cases.json"

from effect_training import (  # noqa: E402
    EffectSuggestionError,
    format_validation_report,
    LocalEffectSuggestionProvider,
    LocalModelBackend,
    MLXBackend,
    OllamaBackend,
    OllamaEffectSuggestionProvider,
    execution_analysis_for_record,
    execution_status_for_record,
    get_effect_suggestion_provider,
    normalize_effect_record,
    validate_effect_record,
)


CARD = {
    "Set": "TST",
    "Number": "001",
    "Name": "Test Trooper",
    "Type": "Unit",
    "FrontText": "When Played: Deal 2 damage to an enemy unit.",
}


class FakeBackend(LocalModelBackend):
    name = "fake"

    def __init__(self, output: str):
        super().__init__(model="fake-model", host="http://local", timeout=1)
        self.output = output

    def generate_json(self, prompt):
        return self.output

    def test(self):
        return {"backend": self.name}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class EffectTrainingTests(unittest.TestCase):
    def test_provider_selection_includes_local_provider(self):
        provider = get_effect_suggestion_provider("local", local_provider="ollama", model="test-model")
        self.assertIsInstance(provider, LocalEffectSuggestionProvider)
        self.assertEqual(provider.backend.model, "test-model")

    def test_provider_selection_includes_ollama_provider(self):
        provider = get_effect_suggestion_provider("ollama", model="test-model", host="http://localhost:11434", timeout=1)
        self.assertIsInstance(provider, OllamaEffectSuggestionProvider)
        self.assertEqual(provider.backend.model, "test-model")
        self.assertEqual(provider.backend.host, "http://localhost:11434")

    def test_local_prompt_includes_swu_primer_and_mapping_guide(self):
        provider = LocalEffectSuggestionProvider(backend=FakeBackend("{}"))

        prompt = provider._build_prompt(CARD)

        self.assertIn("swu_primer", prompt)
        self.assertIn("engine_review_rules", prompt)
        self.assertIn("effect_mapping_guide", prompt)
        self.assertIn("repo_approved_examples", prompt)
        self.assertIn("'This unit' refers to the source unit itself.", prompt["swu_primer"]["core_terms"])
        self.assertEqual(prompt["effect_mapping_guide"]["phrase_to_step_type"]["draw a card"], "draw_cards")
        self.assertTrue(prompt["repo_approved_examples"])

    def test_simple_local_draft_is_safe_but_still_draft(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "deal_damage",
                            "amount": "2",
                            "duration": "instant",
                            "optional": False,
                            "target": {"controller": "enemy", "type": "unit"},
                        }
                    ],
                }
            ],
            "review": {"confidence": "high"},
        }

        record = normalize_effect_record(CARD, candidate, "local:test", raw_output=json.dumps(candidate))

        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["execution_status"], "executable")
        self.assertEqual(record["review"]["triage"], "safe_draft")
        self.assertFalse(record["review"]["human_verified"])

    def test_ambiguous_draft_routes_to_needs_review(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "deal_damage",
                            "amount": 2,
                            "duration": "instant",
                            "optional": True,
                            "target": {"controller": "enemy", "type": "unit"},
                        }
                    ],
                }
            ]
        }

        card = dict(CARD, FrontText="When Played: You may deal 2 damage to a unit.")
        record = normalize_effect_record(card, candidate, "local:test")

        self.assertEqual(record["review"]["triage"], "needs_review")
        self.assertEqual(record["execution_status"], "partial")

    def test_invalid_output_downgrades_to_unresolved_manual(self):
        provider = LocalEffectSuggestionProvider(backend=FakeBackend("not json at all"))

        record = provider.suggest_effect(CARD)

        self.assertEqual(record["review"]["triage"], "unresolved")
        self.assertEqual(record["execution_status"], "manual")
        self.assertTrue(record["review"]["parse_warnings"])

    def test_legacy_flat_trigger_output_is_coerced_for_review(self):
        candidate = {
            "triggers": [
                {
                    "type": "when_played",
                    "effect_type": "draw_cards",
                    "amount": 1,
                    "duration": "this_phase",
                    "target_controller": "self",
                    "target_type": "card",
                }
            ]
        }

        record = normalize_effect_record(CARD, candidate, "local:test")

        self.assertEqual(record["triggers"][0]["event"], "when_played")
        self.assertEqual(record["triggers"][0]["steps"][0]["type"], "draw_cards")
        self.assertEqual(record["review"]["triage"], "needs_review")
        self.assertTrue(
            any("legacy flat trigger format" in warning for warning in record["review"]["parse_warnings"])
        )

    def test_invalid_steps_are_dropped_and_downgraded(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "steps": [
                        {
                            "type": "teleport_unit",
                            "amount": "many",
                            "target": {"controller": "enemy", "type": "unit"},
                        }
                    ],
                }
            ]
        }

        record = normalize_effect_record(CARD, candidate, "local:test")

        self.assertEqual(record["review"]["triage"], "needs_review")
        self.assertEqual(record["execution_status"], "partial")
        self.assertIn("Dropped invalid effect step type", record["review"]["notes"])

    def test_create_token_output_normalizes_as_executable_draft(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "create_token",
                            "amount": "2",
                            "token": "X-Wing token",
                            "duration": "instant",
                            "target": {"controller": "friendly", "type": "player"},
                        }
                    ],
                }
            ]
        }

        record = normalize_effect_record(CARD, candidate, "local:test")

        step = record["triggers"][0]["steps"][0]
        self.assertEqual(step["amount"], 2)
        self.assertEqual(step["token_name"], "X-Wing token")
        self.assertEqual(execution_status_for_record(record), "executable")
        self.assertEqual(record["status"], "draft")
        self.assertFalse(record["review"]["human_verified"])

    def test_attached_unit_target_filter_is_executable(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "exhaust_unit",
                            "amount": 1,
                            "duration": "instant",
                            "target": {"controller": "self", "type": "unit", "filter": "attached_unit"},
                        }
                    ],
                }
            ]
        }

        card = dict(CARD, Type="Upgrade", FrontText="When Played: Exhaust attached unit.")
        record = normalize_effect_record(card, candidate, "local:test")

        self.assertEqual(record["validation"]["execution_analysis"]["status"], "executable")
        self.assertEqual(record["review"]["triage"], "safe_draft")

    def test_ground_target_filter_is_executable_for_single_target_effect(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "deal_damage",
                            "amount": 1,
                            "duration": "instant",
                            "target": {"controller": "enemy", "type": "unit", "filter": "ground"},
                        }
                    ],
                }
            ]
        }

        card = dict(CARD, FrontText="When Played: Deal 1 damage to a ground unit.")
        record = normalize_effect_record(card, candidate, "local:test")

        self.assertEqual(record["validation"]["execution_analysis"]["status"], "executable")
        self.assertEqual(record["review"]["triage"], "needs_review")

    def test_draw_cards_without_explicit_target_defaults_to_friendly_player(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "draw_cards",
                            "amount": 1,
                            "duration": "instant",
                        }
                    ],
                }
            ]
        }

        record = normalize_effect_record(CARD, candidate, "local:test")

        self.assertEqual(
            record["triggers"][0]["steps"][0]["target"],
            {"controller": "friendly", "type": "player"},
        )

    def test_create_token_without_token_name_infers_from_rules_text(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "create_token",
                            "amount": 1,
                            "duration": "instant",
                        }
                    ],
                }
            ]
        }
        card = dict(CARD, Name="Veteran Fleet Officer", FrontText="When Played: Create an X-Wing token.")

        record = normalize_effect_record(card, candidate, "local:test")

        step = record["triggers"][0]["steps"][0]
        self.assertEqual(step["token_name"], "X-Wing token")
        self.assertEqual(step["target"], {"controller": "friendly", "type": "player"})
        self.assertEqual(record["execution_status"], "partial")
        self.assertEqual(record["review"]["triage"], "needs_review")
        self.assertTrue(any("Inferred token_name" in warning for warning in record["review"]["parse_warnings"]))

    def test_ollama_generate_parses_response_field(self):
        backend = OllamaBackend(model="test-model", host="http://127.0.0.1:11434", timeout=1)
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"response": "{\"triggers\": []}"})):
            self.assertEqual(backend.generate_json({"task": "test"}), "{\"triggers\": []}")

    def test_ollama_provider_valid_json_response_creates_draft(self):
        response_record = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "deal_damage",
                            "amount": "2",
                            "duration": "instant",
                            "target": {"controller": "enemy", "type": "unit"},
                        }
                    ],
                }
            ]
        }
        provider = OllamaEffectSuggestionProvider(model="test-model", host="http://localhost:11434", timeout=1)

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"response": json.dumps(response_record)})):
            record = provider.suggest_effect(CARD)

        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["source"], "local:ollama:test-model")
        self.assertEqual(record["execution_status"], "executable")
        self.assertEqual(record["triggers"][0]["steps"][0]["amount"], 2)
        self.assertFalse(record["review"]["human_verified"])
        self.assertTrue(record["review"]["llm_suggested"])

    def test_ollama_provider_invalid_json_response_stays_manual_draft(self):
        provider = OllamaEffectSuggestionProvider(model="test-model", host="http://localhost:11434", timeout=1)

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({"response": "not json"})):
            record = provider.suggest_effect(CARD)

        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["execution_status"], "manual")
        self.assertEqual(record["review"]["triage"], "unresolved")
        self.assertIn("Could not parse local model output", record["review"]["notes"])

    def test_ollama_provider_missing_response_body_stays_manual_draft(self):
        provider = OllamaEffectSuggestionProvider(model="test-model", host="http://localhost:11434", timeout=1)

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse({})):
            record = provider.suggest_effect(CARD)

        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["execution_status"], "manual")
        self.assertEqual(record["review"]["triage"], "unresolved")
        self.assertIn("did not include generated text", record["review"]["notes"])

    def test_ollama_provider_unavailable_raises_friendly_error(self):
        provider = OllamaEffectSuggestionProvider(model="test-model", host="http://localhost:11434", timeout=1)

        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(EffectSuggestionError) as raised:
                provider.suggest_effect(CARD)

        self.assertEqual(raised.exception.title, "Ollama is not running")

    def test_ollama_timeout_is_friendly_error(self):
        backend = OllamaBackend(model="test-model", host="http://localhost:11434", timeout=1)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
            with self.assertRaises(EffectSuggestionError) as raised:
                backend.generate_json({"task": "test"})
        self.assertEqual(raised.exception.title, "Ollama request timed out")

    def test_ollama_unavailable_is_friendly_error(self):
        backend = OllamaBackend(model="test-model", host="http://127.0.0.1:11434", timeout=1)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(EffectSuggestionError) as raised:
                backend.test()
        self.assertEqual(raised.exception.title, "Ollama is not running")

    def test_mlx_import_failure_is_friendly_error(self):
        backend = MLXBackend(model="mlx/test-model", timeout=1)

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "mlx_lm":
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(EffectSuggestionError) as raised:
                backend.test()
        self.assertEqual(raised.exception.title, "MLX runtime is not installed")

    def test_validation_report_flags_runtime_choice_and_schema_problems(self):
        record = {
            "set": "TST",
            "number": "002",
            "name": "Ambiguous Card",
            "status": "draft",
            "raw_text": "When Played: You may choose a unit.",
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "deal_damage",
                            "duration": "instant",
                            "optional": True,
                            "target": {"controller": "enemy", "type": "unit", "filter": "damaged"},
                        }
                    ],
                }
            ],
        }

        report = validate_effect_record(record)

        self.assertTrue(report["valid"])
        self.assertEqual(report["execution_analysis"]["status"], "partial")
        self.assertTrue(any("optional choice" in blocker for blocker in report["execution_analysis"]["blockers"]))
        self.assertTrue(any("ambiguity term" in warning for warning in report["warnings"]))

    def test_execution_analysis_marks_unsupported_trigger_manual(self):
        record = {
            "set": "TST",
            "number": "003",
            "name": "Regroup Card",
            "status": "draft",
            "triggers": [
                {
                    "event": "regroup_start",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "draw_cards",
                            "amount": 1,
                            "duration": "instant",
                            "target": {"controller": "friendly", "type": "player"},
                        }
                    ],
                }
            ],
        }

        analysis = execution_analysis_for_record(record)

        self.assertEqual(analysis["status"], "manual")
        self.assertTrue(any("unsupported runtime event regroup_start" in blocker for blocker in analysis["blockers"]))

    def test_normalized_record_includes_validation_snapshot(self):
        candidate = {
            "triggers": [
                {
                    "event": "when_played",
                    "conditions": [],
                    "steps": [
                        {
                            "type": "deal_damage",
                            "amount": 2,
                            "duration": "instant",
                            "target": {"controller": "enemy", "type": "unit"},
                        }
                    ],
                }
            ]
        }

        record = normalize_effect_record(CARD, candidate, "local:test")

        self.assertIn("validation", record)
        self.assertTrue(record["validation"]["valid"])
        self.assertEqual(record["validation"]["execution_analysis"]["status"], "executable")

    def test_format_validation_report_includes_schema_and_runtime_sections(self):
        report = {
            "valid": False,
            "errors": ["missing required top-level field 'name'"],
            "warnings": ["rules text contains ambiguity term 'choose'"],
            "execution_analysis": {"status": "manual", "blockers": ["record has no triggers"], "metrics": {"trigger_count": 0}},
            "metrics": {"trigger_count": 0},
        }

        formatted = format_validation_report(report)

        self.assertIn("Valid: no", formatted)
        self.assertIn("Runtime blockers:", formatted)
        self.assertIn("Schema errors:", formatted)
        self.assertIn("Warnings:", formatted)

    def test_golden_effect_cases_stay_stable(self):
        cases = json.loads(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))

        for case in cases:
            with self.subTest(case=case["name"]):
                card = dict(CARD)
                if case.get("front_text"):
                    card["FrontText"] = case["front_text"]
                record = normalize_effect_record(card, case["candidate"], "local:test")
                validation = validate_effect_record(record)

                self.assertEqual(record["execution_status"], case["expected_execution_status"])
                self.assertEqual(record["review"]["triage"], case["expected_triage"])
                self.assertEqual(validation["execution_analysis"]["status"], case["expected_runtime_status"])
                self.assertEqual(validation["valid"], case["expected_valid"])


if __name__ == "__main__":
    unittest.main()
