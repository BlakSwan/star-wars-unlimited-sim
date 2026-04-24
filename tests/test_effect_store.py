from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sw_unlimited_sim"))

import effect_store  # noqa: E402


class EffectStoreTests(unittest.TestCase):
    def test_save_get_and_delete_draft_artifact(self):
        record = {
            "set": "TWI",
            "number": "107",
            "name": "Patrolling V-Wing",
            "status": "draft",
            "triggers": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "draft_artifacts.json"
            with mock.patch.object(effect_store, "DRAFT_ARTIFACTS_PATH", artifact_path):
                effect_store.save_draft_artifact(record, reason="test archive")

                artifact = effect_store.get_draft_artifact("TWI", "107")
                self.assertIsNotNone(artifact)
                self.assertEqual(artifact["name"], "Patrolling V-Wing")
                self.assertEqual(len(artifact["artifacts"]), 1)
                self.assertEqual(artifact["artifacts"][0]["reason"], "test archive")

                self.assertTrue(effect_store.delete_draft_artifact("TWI", "107"))
                self.assertIsNone(effect_store.get_draft_artifact("TWI", "107"))


if __name__ == "__main__":
    unittest.main()
