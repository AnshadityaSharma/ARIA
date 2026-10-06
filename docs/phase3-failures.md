# Phase 3 failure categories

This report classifies the Phase 0 failures that motivated Phase 3 and records the remaining evidence limits. It does not claim general language understanding.

## Addressed categories

| Category | Deterministic response |
| --- | --- |
| Capability wording misses | Finite synonyms and polite wrappers for measured command families |
| Indian-English phrasing | Bounded `kindly`, `once`, and measured word-order forms |
| Hinglish phrasing | Explicit small command vocabulary for launch, resize, and movement |
| Quantity and direction variants | Bounded word/digit percentages and fixed direction map |
| Stateful follow-ups | Five-minute verified recent-window state plus command-start foreground identity |
| Application spacing and one-character ASR/spelling errors | Discovery-derived compact exact and constrained unique edit-distance-one matching |
| Negation | `UnsupportedCommand`; no action proposed |
| Compound commands | `ClarificationRequired`; no partial action proposed |
| Literal command words | Payload-preserving parsing before command-clause checks |
| Missing or ambiguous context | Explicit clarification rather than target substitution |

The resolution-aware Phase 3 development set and frozen Phase 0 held-out set have no observed misses. The original Phase 0 scoring method still records one target mismatch on each split because it compares the parser's raw discovered-name query before Phase 2 resolution (`camra` / `note pad`). The resolution-aware evaluator resolves those queries against controlled discovered records and records the exact discovered application identity.

## Remaining evidence limits

- The authored corpora are small: Phase 3 development has 20 cases and 22 steps; frozen Phase 0 held-out has 23 action steps and 7 non-action steps.
- Hinglish, Indian English, and simulated ASR cohorts contain only a few examples. They show regression coverage, not population performance.
- Real human voice testing remains Phase 6/7 work. Phase 3 evaluates text and saved transcript strings only.
- The grammar intentionally abstains outside its bounded forms. Broader unsupported phrasing and user-frequency estimates remain unmeasured.
- Edit-distance recovery is restricted to a single discovered application token. Multi-token phonetic errors, two-edit errors, and ambiguous near matches clarify or abstain.
- Fresh-process startup includes Python/import cost and is not a packaged cold-start claim.
- No Phase 7 gate was run. No learned interpreter decision is justified by this authored diagnostic result alone.

Future misses must be categorized as normalization, capability selection, target resolution, parameter extraction, context, ASR, ambiguity, or unsupported scope. Improve deterministic rules using development evidence only. Preserve the frozen held-out set for decision gates.
