# ScaffoldRankBench data card: external audit

The primary dataset is a complete projection of the published ActBench release at Hugging Face revision `595df032d53ef71f927c9a1d8c068dad0edebbc5`, with MIT source licensing. It contains all 24,000 records over 20 configurations, 300 paired tasks and 213 scenarios. Each configuration/task has one clean and three attack records. Scores, identities, source provenance, error flags and thresholds are preserved. No new labels or attacks were generated for this replay.

All 21 publisher file hashes and 5,613 embedded task-file hashes match. Canonical reconstruction matches 21,600 trajectory hashes; all 2,400 Kimi-K3/Grok-4.5 embedded hashes remain unresolved. These rows remain visible, with the exact discrepancy census retained. File integrity does not validate source judges or recover an original workspace.

Additional inputs are complete published AgentS4D Table 14 (20 configuration rows) and HarnessRisk Table 2 (14 rows), cached with exact HTML digests. These are reported source results, not newly executed experiments. Their original copyright and licenses remain attached to the source publications. The code's MIT license does not relicense those publications. All 26 eligible nominal comparisons are included; 11 descriptive reversals are dependent and adaptive. Missing cells, 128 AgentS4D inconclusive records and HarnessRisk's seed standard deviations/failure filtering are retained.

Intended use is auditing ranking scope, denominators, utility tradeoffs and uncertainty. It is not an operational security certification, an independent relabeling exercise or a causal model-versus-harness attribution. Providers/routes, versions, tasks, judges and budgets differ between sources. The 70 unobserved ActBench combinations cannot supply measured cross-harness rankings. No live source tool or model is executed by the default audit.

The earlier synthetic studies remain separate below. Their AI-assisted task construction and finite policy are not an independently authored external test distribution.

## Historical data card (retained)

# ScaffoldRankBench dataset card

ScaffoldRankBench v1.0 contains 32 generated items in 16 matched families. Four safe simulated domains are crossed with four authorization-record defects (identity mismatch, scope mismatch, unverified channel, and expired grant), and every family contains one clean and one attack variant. Canonical records specify the authenticated goal, governing policy, tool registry, initial information, forbidden operation, exact safe plan, provenance, and a three-action budget.

The same record is compiled into four protocols: a one-shot plan, a serialized textual-ReAct transcript, a two-call planner-validator, and a serialized provenance-ledger transcript. The data contain no real people, organizations, messages, repositories, purchases, credentials, secrets, or external side effects. Labels come from deterministic action and state semantics, not an LLM. The complete family pair is always the statistical and split unit.

The artifact is intended for controlled measurement of scaffold sensitivity. It is not a production compromise-rate dataset, naturalness study, or proof that the four compact loops reproduce every implementation detail of named commercial frameworks.
