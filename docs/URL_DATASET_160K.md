# CloakGuard 160k URL dataset

The CSV is a balanced, deduplicated adaptation of **PhiUSIIL Phishing URL (Website)** by Arvind Prasad and Shalini Chandra (2024). UCI licenses the source under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The adaptation selects and shuffles 80,000 examples per class, remaps the label convention, and adds domain groups and split assignments. [UCI dataset 967](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+website+dataset)

| Column | Meaning |
| --- | --- |
| `url` | Trimmed source string for offline lexical analysis |
| `label` | 0 for legitimate, 1 for phishing |
| `domain_group` | Registrable domain using the bundled Public Suffix List, or hostname fallback |
| `split` | Fixed train or test partition. Domain groups occur in one partition only |

Read the file as data. Some strings point to phishing infrastructure. Neither the builder nor the benchmark visits the URLs. The builder filters malformed records, explicit URL credentials, common credential-like query fields, and conflicting records and collapses exact or normalized URL duplicates before sampling. The manifest records the selection seed, counts, and checksums.

This source labels phishing and legitimate URLs. It provides no paired-view cloaking adjudication, and class balance does not reflect prevalence in deployment. Every legitimate sample uses HTTPS with a www. hostname and an empty path and query. The benchmark includes a rule using only that shape and reports a matched-shape test slice. This exposes a source-specific shortcut that domain grouping alone cannot remove. Grouping domains leaves possible sharing of campaign or collection characteristics across partitions.

## Rebuild and evaluate

Install the dependencies in `results/requirements.txt`. Download UCI's original ZIP and run from the repository root:

```text
python results/detection/train_model.py path/to/phiusiil.zip --output-dir path/to/output
```

You can also pass the extracted `CloakGuard_160k.csv` as the first argument to evaluate the delivered split directly. Add `--prepare-only` to skip training. The benchmark uses only the 41 features computed from the URL string and the saved split. It does not use any source-derived page or aggregate features. Use the existing dataset file and the included manifest checksum for the exact delivered snapshot. The original study's metrics remain historical.


## Evaluation findings

On 41,152 held-out rows, the URL-shape rule reached 99.69% accuracy, compared with 99.59% for histogram gradient boosting. All 19,969 legitimate test URLs and only 127 phishing test URLs shared the matched URL shape. On that slice, boosting detected 38 of 127 phishing URLs at 0.50, and logistic regression detected 10 of 127. Boosting's ROC-AUC fell from 0.999 on all held-out rows to 0.776 on the matched slice. These numbers quantify the collection shortcut. Use them as a dataset-bias analysis in the paper.
