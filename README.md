# datasets

The lab's datasets, built once and read everywhere. Each dataset is a recipe in this repository (fetch, curate, split, annotate) and a versioned set of files on the Hugging Face Hub; a skill, in prose, says what the dataset is, what its files hold, and the one line that loads them, and both people and their agents read it.

Why it exists and what it is not: [docs/VISION.md](docs/VISION.md). How it works: [docs/DESIGN.md](docs/DESIGN.md). Adding a dataset: [CONTRIBUTING.md](CONTRIBUTING.md).

## Finding a dataset

`ls datasets`. Each `datasets/<name>/SKILL.md` starts with a `description` that says what the dataset is and when to reach for it, then its files and their columns, the line that reads it, the recipe that made it, and what the build took.

## Reading a dataset from anywhere

```python
from huggingface_hub import snapshot_download
path = snapshot_download("brineylab/<name>", repo_type="dataset", revision="v<version>")
```

`path` is a local directory holding the version's parquet files; read them with polars, pandas, or pyarrow. `datasets.load_dataset("brineylab/<name>", revision="v<version>")` works the same. Always name a version; `main` is not a version.

## On bcr

```bash
export HF_HUB_CACHE=/mnt/data/datasets/hf_hub
```

before the line above, in a notebook or a job, shares the cluster's cache: a version anyone on the cluster has pulled, a flyloft campaign included, is read from disk at once.

## Giving your coding agent the skills

```bash
git clone https://github.com/brineylab/datasets && cd datasets
mkdir -p ~/.claude/skills && for d in datasets/*; do ln -sfn "$PWD/$d" ~/.claude/skills/; done
```

For Codex and OpenCode, link into `~/.agents/skills/` instead. `git pull` updates the linked skills; run the loop again after a pull that adds a dataset.

## Versions

A dataset's version is a tag, `v<version>`, on its Hub repository, and a published tag is never moved. A version changes when the source is re-pulled, a parameter moves, or a tool moves; a variant (another species, another threshold) is another dataset.

CI checks every pull request: the dataset's rules, an unpublished version, the recipe's tools in the toolshed, and a record of the candidate's passing test whose files are exactly the Hub's. After the merge, whoever merged tags the record's commit with `scripts/promote`. CI checks records and never pulls a dataset; whoever builds a dataset tests it and files it.
