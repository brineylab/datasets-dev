---
name: hello2-6a463bf0
description: "300 synthetic antibody pairs of random amino acids in three splits: the repository's smoke dataset. Reach for it to check that reading a dataset works from where you are, never to train."
metadata:
  version: 1.0.0
  tools: datascience@1.0.0
  license: mit
---
# hello2-6a463bf0

Hub: `brineylab/hello2-6a463bf0`, tag `v1.0.0`

## Files

`train.parquet`, `eval.parquet`, `test.parquet`: 240, 30, and 30 rows, one per pair, columns `pair_id` (`hello-0000` to `hello-0299`), `sequence_heavy` (110 to 130 amino acids), `sequence_light` (105 to 115). The letters are uniform draws from the twenty amino acids: no sequence is an antibody.

## Reading it

```python
from huggingface_hub import snapshot_download
import polars as pl
path = snapshot_download("brineylab/hello2-6a463bf0", repo_type="dataset", revision="v1.0.0")
train = pl.read_parquet(f"{path}/train.parquet")
```

## Recipe

No source: `recipe/build` draws `pairs = 300` pairs from `random.Random(seed = 1)`, shuffles them, and splits them `[0.8, 0.1, 0.1]` in that order. It runs in `datascience@1.0.0`. The test checks the three files, their columns, their row counts, and that no `pair_id` is in two splits.

## Compute

Seconds on a laptop, one CPU, kilobytes of disk.

## Gotchas

- It exists to exercise filing, checking, promoting, and reading; its sequences mean nothing.
