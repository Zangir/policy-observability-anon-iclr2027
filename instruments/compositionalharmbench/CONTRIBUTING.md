# How we work together

Each project has a code repository, a manuscript repository, and one tracking issue in the central hub. The original research question remains the research objective; completing a small component experiment does not settle it.

1. The supervisor assigns a student to the project tracking issue. Each task names an owner, a concrete deliverable, and the evidence needed to accept it.
2. Before changing code, open an issue and create a branch such as `q01/retrieval-baseline`. Submit a pull request that links the task. Request review from `Anonymous`; do not merge your own research conclusions without review.
3. For a new experiment, commit the hypothesis, task split, seeds, endpoints, model/configuration, budget and stopping rule before collection. Store new runs under a new ID. Preserve failed calls, original scores and negative results.
4. A weekly update goes in the central tracking issue: completed work; commit/PR and result links; numerical result and interpretation; blockers; next deliverable and target date. Status labels are `status:ready`, `status:in-progress`, `status:blocked`, `status:review`, and `status:done`.
5. Mark a milestone complete only when the linked output is reviewable and accepted. A passing smoke check validates software, not novelty or scientific adequacy. Refer to the paper-specific remaining gaps.

## Manuscript editing and Overleaf

The manuscript repository is the shared version history. If using Overleaf, the project owner links their GitHub account, then creates a NEW Overleaf project by importing the `-paper` repository. Use pdfLaTeX and `main.tex`. GitHub synchronization requires a supported premium/institutional plan and is manual. Do not import the code repository into Overleaf.

Choose a writing window: push existing Overleaf edits to GitHub before an external LaTeX change, pause editing, review/merge the GitHub change, then pull it into Overleaf. Resolve tracked changes/comments before pulling external edits; Overleaf warns that synchronization can displace them. Student code can continue independently during a writing window.

Overleaf synchronization attributes GitHub commits to the connected account, so commit counts are not a reliable measure of individual writing contributions. Use assigned tasks and weekly evidence updates, and inspect Overleaf history for writing work.

Without GitHub sync, upload the verified source ZIP to create an Overleaf project. After a writing session, download its source and submit the changes to the manuscript repository in a reviewed PR. ZIP upload is an initial copy, not ongoing synchronization.

The assistant can work on accessible GitHub issues, branches, code and paper source during a session. It does not independently watch private Overleaf sessions or send students messages in the background. Student access still needs their actual usernames; direct Overleaf work needs an authenticated integration or project Git access. Do not paste passwords or tokens in chat.

## Access and checkpoints

All repositories start private. Students receive access to the hub and their assigned repositories. The supervisor keeps ownership. Use a tagged baseline and reviewed milestones so a paper revision can be tied to a code commit and a recorded run. CODEOWNERS requests review; enforcement depends on the repository plan and branch rules and is not claimed merely because the file exists.

The existing license files apply to their stated code or source data only. Restricted market records, feature caches, credentials and local execution environments are not part of this collaboration export. Provider calls are not run by CI; students arrange their own authorized model access for new collections.

References: [Overleaf synchronization](https://docs.overleaf.com/integrations-and-add-ons/git-integration-and-github-synchronization/github-synchronization), [Overleaf limits](https://docs.overleaf.com/getting-started/free-and-premium-plans/plan-limits), [GitHub Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects).
