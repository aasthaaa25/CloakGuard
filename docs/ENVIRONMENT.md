# Environment

- Python 3.11.9 on Windows.
- Dependencies are listed in `results/requirements.txt`. This machine imported pandas 2.3.1, scikit-learn 1.9.0, and pytest.
- `results/detection/artifacts/model.joblib` and `multimodal_model.joblib` were written with scikit-learn 1.7.2. The URL ensemble does not load on 1.9.0 because `HistGradientBoostingClassifier` pickles a private `_loss` module. The metrics JSON is the readable record of that run.
- Recompute the crawl audit with `python evaluation/audit_repository.py` from the repository root.
- Recompute the local fixture with `python evaluation/demo_case.py`.
- Tests: `python -m pytest results/tests -q`.
- `PASSIVE_DNS_API_KEY` is read from the environment when a forensic lookup is enabled. No key is stored in the repository.

## November 2026 portable workflow check

The portable training and local TLS demonstration were executed with Python 3.13.9 on macOS and scikit-learn 1.7.2. Generated model cards record the versions used by each run. The Windows launcher is provided for a machine with Python and the requirements installed. Native Windows execution remains unverified.
