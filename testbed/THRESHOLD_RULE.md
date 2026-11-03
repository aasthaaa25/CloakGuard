# Threshold rule for heuristic version 2

This rule was written before the calibration scores were computed. `north_market` and `harbor_books` are heuristic version 1 development examples. They are not used to choose this threshold. The version 1 threshold remains 0.50 and its no-alert results stay in `testbed/results/predictions.csv`.

## Scope

The detector being calibrated is bot-directed promotional cloaking. A positive case is a cross-profile pair in which the bot view contains in-list promotional keywords that the human view does not. Human-only injection, identical defacement, access challenges, and benign page changes are not positives for this detector.

The decision is a review alert. It does not authorize a block by itself.

## Data

Calibration families: `cedar_clinic`, `maple_archive`.

Reserved families, not used to pick the threshold: `quartz_supply`, `linen_press`.

One row per scenario is used: H1 versus B1. The other three captures are repeats, not extra examples.

## Selection

Let P be the H1–B1 scores of calibration scenarios whose role is `positive` or `positive_substantial`.
Let N be the H1–B1 scores of calibration scenarios whose role is `negative`.

If the lowest P is greater than the highest N, the review threshold is the midpoint `(min(P) + max(N)) / 2`.

If they overlap, narrow P to scenarios whose role is `positive_substantial` and apply the same midpoint rule. Few-term and hidden-link cases then stay reported, but they do not set the threshold.

If the narrowed sets still overlap, do not publish a threshold. Record the overlap.

Do not set the threshold to 0.47 because a previous example scored about 0.48.

## Operational review

The service rounds the controlled threshold to 0.270 on the fixed-weight scoring path. Set `REVIEW_THRESHOLD` to override it. The URL-model-assisted path retains the 0.50 alert for review because the 0.270 rule was selected without the URL model. Neither alert authorizes blocking. Human-only injection is outside this rule. Owner-approved static artifacts can be checked independently with `detection.pipeline.integrity`.
