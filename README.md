# mlops-04-mlflow-production

Production-oriented MLflow setup: moving past a local `mlruns/` directory to a
tracking server backed by a real database and artifact store, with a model
registry driving promotion between stages.

Fourth project in the `mlops-projects` series, following
`mlops-03-mlflow-basic-install`.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## Usage

```bash
uv run main.py
```

## Project layout

```
.
├── main.py           # entry point
├── pyproject.toml    # project metadata and dependencies
└── .python-version   # pinned Python version
```
