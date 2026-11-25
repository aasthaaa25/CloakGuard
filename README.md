# CloakGuard

CloakGuard is Aastha Tyagi’s defensive research prototype for identifying bot-directed promotional changes on owner-controlled websites. It compares paired HTTP captures, records review evidence, and provides a separate forward-only reverse proxy.

Download the [balanced 160,000-URL dataset](data/CloakGuard_160k_dataset.zip) and read the [dataset guide](docs/URL_DATASET_160K.md) for attribution, the fixed domain split, and the source-bias analysis.

Run `python evaluation/run_live_demo.py` for the local HTTP-to-evidence demonstration or `python results/run_all.py` for the full verification suite.

- [Corrected paper](paper/CloakGuard_corrected.md) and [claim audit](docs/CLAIM_AUDIT.md)
- [Controlled validation protocol](docs/CONTROLLED_VALIDATION.md) and [ML benchmark](evaluation/benchmark_controlled_ml.py)
- [Deployment and live demo](results/deploy/README.md)

The historical PDF and archived model metrics are retained for traceability. The 160,000-URL source dataset is missing. The historical paired-view training table contains zero-filled modalities and labels derived from the detector’s score. The new controlled benchmark uses scenario labels and separates fit and reserved examples by template family.

The research software lives in `results/detection/` and `testbed/`. Evidence processing and owner-side policy components live in `results/app/`. The default web service forwards traffic to one configured origin. The offline lab exercises fingerprint policy, rate-limit decisions, decoy rollback, and forensic packaging.
