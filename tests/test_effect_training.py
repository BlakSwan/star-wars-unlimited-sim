from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

from effect_training import (  # noqa: E402
    EffectSuggestionError,
    LocalEffectSuggestionProvider,
    LocalModelBackend,
    MLXBackend,
    OllamaBackend,
    OllamaEffectSuggestionProvider,
    execution_status_for_record,
    get_effect_suggestion_provider,
    normalize_effect_record,
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


if __name__ == "__main__":
    unittest.main()
