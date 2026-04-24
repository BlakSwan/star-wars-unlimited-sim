# Local LLM Drafting Boundary

The simulator now treats a local LLM as an offline draft assistant, not a live
rules judge.

## Runtime Rule

- Local models may draft structured effect records.
- The simulator only executes records that are:
  - `status: approved`
  - `execution_status: executable`
- Drafts remain review artifacts until a human approves them.

## Validation Workflow

Use the CLI to inspect the current effect corpus:

```bash
cd sw_unlimited_sim
python main.py --validate-effects
python main.py --validate-effect SOR 128
```

The validation report separates:

- schema validity
- runtime execution status
- concrete blockers such as unsupported triggers, target filters, optional
  choices, or non-instant durations
- risky card-text terms that usually require human review

## Golden Regression Cases

The test suite includes a small golden corpus in
`tests/golden_effect_cases.json`. These cases are intended to catch prompt or
normalization regressions when draft logic changes.

Run:

```bash
python -m unittest tests.test_effect_training -q
```

## Recommended Next Work

- Expand executable mechanic primitives before widening LLM usage.
- Add more reviewed effect records so prompts can be tuned against real cards.
- Keep model work offline and deterministic; do not add live in-game LLM calls.
