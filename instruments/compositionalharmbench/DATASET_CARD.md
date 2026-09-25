# CompositionalHarmBench data and study card

The current artifact contains separate evidence sources and cohorts. It does not pool them into one benchmark accuracy.

- **Candidate-binding follow-up:** all 32 original finite cases, three views and two generations from each of two configured model subjects. The added view repeats the exact candidate beside the unchanged trusted state. These source-informed cases primarily vary identifiers within four mechanisms.
- **External observation follow-up:** 128 frozen hash-selected records from the 1,000-row AI45Research/ATBench release, with 64 source-safe and 64 source-unsafe labels. Each model sees full-record, action-log and last-action views of the same whole-trajectory target. The external source is human-audited simulated data, not production incidents. We do not independently re-adjudicate the labels.
- **Preceding common-policy study:** 384 recorded requests, kept unchanged under results/review_openai_v1. The old local observation deliberately withholds sufficient evidence and permits ASK.
- **Initial synthetic instrument:** the 1,920-item generator and its original finite evaluation remain historical; details below.

The ATBench data revision is 4476ef92ed8f85c8d58d8a5b9dfdf55aa7893138. The original test JSON has SHA256 80c534b5f3517c872b528a2e6b64e34495206968edd184f4aed563d39f0cca09. The pinned source card declares Apache 2.0 and is retained as results/external_inputs/ATBENCH_README.md. Those external records retain their source license; they are not relicensed as generated CompositionalHarmBench data. Selection, code hashes, initial plans and the pre-call schema amendment are in the same directory.

Private source labels, risk/failure annotations and gold explanations stay outside the model prompts. An exhaustive 3,000-prompt mutation check verifies annotation exclusion. This is an input-integrity check, not proof of an error-free safety oracle. Quoted source actions and instructions are evidence for classification and are never executed. The recorded subject interface disables tools and preserves the existing application home.

## Initial instrument (historical)


CompositionalHarmBench 1.0 contains 1,920 synthetic items organized as 640 matched workflow families. Every family has a clean, composition-unsafe, and atomic-unsafe variant. The complete factorial crosses five enterprise domains, four harm mechanisms, four horizons, indirect versus direct source, persistent versus ephemeral memory, and single- versus multi-agent execution. A fixed 20-family, 60-item slice supports affordable model evaluation.

Every action and state is synthetic. No real secret, credential, account, message, repository, person, or organization appears. The simulator never performs network, filesystem, purchasing, messaging, or code-execution side effects.

The composition variant contains only calls permitted by the declared memoryless local policy. Its complete sequence violates a deterministic provenance or state invariant. The atomic variant contains exactly one locally forbidden call, and the clean control violates neither policy. Tests validate all 1,920 labels.

The dataset is generated deterministically by `compositional_harm_bench.scenarios.write_dataset`. It is licensed under CC BY 4.0; code is MIT licensed. Synthetic simplicity supports causal diagnosis but is not evidence about deployment prevalence or the severity of real incidents.
