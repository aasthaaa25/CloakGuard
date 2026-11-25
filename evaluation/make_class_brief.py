"""Build the classroom PDF and its figures from current evaluation artifacts."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve

ROOT = Path(__file__).resolve().parents[1]
INK = "#10243A"
MUTED = "#485F73"
BLUE = "#154D8D"
TEAL = "#087D77"
ORANGE = "#BA531F"
BACKGROUND = "#F6F8FB"


def page(number, section, title, subtitle):
    fig = plt.figure(figsize=(11.7, 8.3), facecolor=BACKGROUND)
    fig.text(.07, .935, f"CLOAKGUARD   /   {section.upper()}", color=TEAL, size=11, weight="bold")
    fig.text(.07, .857, title, color=INK, size=30, weight="bold")
    fig.text(.07, .806, subtitle, color=MUTED, size=11)
    fig.text(.07, .035, "Aastha Tyagi  |  Defensive security and machine learning", color=MUTED, size=9)
    fig.text(.93, .035, f"{number:02}", ha="right", color=MUTED, size=9)
    return fig


def styled_axes(fig, bounds, title):
    ax = fig.add_axes(bounds)
    ax.set_title(title, loc="left", color=INK, fontsize=14, weight="bold", pad=12)
    ax.grid(axis="y", color="#DDE5ED", linewidth=.8)
    ax.set_axisbelow(True)
    for edge in ("top", "right"):
        ax.spines[edge].set_visible(False)
    return ax


def note(fig, y, heading, text):
    fig.text(.07, y, heading, weight="bold", color=INK, size=12)
    fig.text(.07, y - .033, text, color=MUTED, size=10.5, linespacing=1.5, va="top")


def architecture(demo):
    fig = page(1, "Architecture & live demo", "Review suspicious split views",
               "A site-owner workflow with a forward-only traffic path and a separate evidence path.")
    ax = fig.add_axes([.07, .32, .86, .42])
    ax.axis("off")
    rows = [
        (.82, "HTTP traffic", ("Client / HTTPS ingress", "CloakGuard proxy", "Authorized site origin")),
        (.46, "Detection & evidence", ("Paired HTTP capture", "Drift + promotional signals", "Review score + evidence")),
        (.10, "Isolated policy checks", ("Designated test subject", "Fingerprint policy + rate limit", "Static decoy + rollback")),
    ]
    for y, label, nodes in rows:
        ax.text(.0, y + .12, label, transform=ax.transAxes, color=MUTED, size=10, weight="bold")
        for x, name in zip((.14, .50, .86), nodes):
            ax.text(x, y, name, transform=ax.transAxes, ha="center", va="center", size=11,
                    color=INK, bbox={"boxstyle": "round,pad=0.65", "fc": "white", "ec": "#AFC4D5"})
        for x in (.32, .68):
            ax.annotate("", xy=(x + .038, y), xytext=(x - .038, y), xycoords=ax.transAxes,
                        arrowprops={"arrowstyle": "->", "lw": 1.5, "color": BLUE})
    clean = demo["cases"]["clean"]
    changed = demo["cases"]["bot_substantial"]
    note(fig, .22, "Verified on real loopback HTTP",
         f"Clean pair scored {clean['score']:.3f}. The scripted bot-only change scored {changed['score']:.3f} and generated evidence "
         f"at the {changed['threshold']:.2f} cutoff.\nThe HTTPS ingress is a deployment topology. The verified demo uses local HTTP.")
    return fig


def url_results(report, predictions):
    fig = page(2, "URL-lexical experiment", "Five domain-disjoint folds",
               f"{report['rows']:,} archived URL rows  |  {report['registrable_domain_groups']:,} domain groups  |  "
               f"{report['positive']:,} class 1 and {report['negative']:,} class 0")
    ax = styled_axes(fig, [.08, .27, .39, .43], "Pooled out-of-fold ROC")
    colors = {"logistic": BLUE, "hist_gradient_boosting": TEAL}
    names = {"logistic": "Logistic regression", "hist_gradient_boosting": "Hist. gradient boosting"}
    for name, color in colors.items():
        fpr, tpr, _ = roc_curve(predictions["label"], predictions[name])
        ax.plot(fpr, tpr, color=color, lw=2, label=names[name])
    ax.plot([0, 1], [0, 1], "--", color="#899CAD")
    ax.set(xlabel="False-positive rate", ylabel="True-positive rate", xlim=(0, 1), ylim=(0, 1.03))
    ax.legend(loc="lower right", frameon=False, fontsize=8)

    ax = styled_axes(fig, [.57, .27, .35, .43], "Mean fold ROC-AUC")
    ids = ["prior", "logistic", "hist_gradient_boosting"]
    bars = ax.bar(["Prior", "Logistic", "Boosting"],
                  [report["models"][i]["mean_fold_roc_auc"] for i in ids], color=["#AFC4D5", BLUE, TEAL])
    ax.set_ylim(0, 1.12)
    ax.bar_label(bars, fmt="%.3f", padding=4, color=INK)
    note(fig, .15, "Interpretation",
         "These scores measure prediction of the archived proxy labels. The full 160,000-row CSV and independent\n"
         "label provenance were unavailable. Source-specific differences may still explain part of the signal.")
    return fig


def paired_results(report, curves):
    fig = page(3, "Paired HTTP experiment", "Separating ranking from alerts",
               f"{report['rows']} scripted pairs  |  {report['positive']} positives  |  "
               "Training excludes the test template and scenario group")
    ax = styled_axes(fig, [.08, .27, .36, .43], "Precision–recall")
    selections = [("tfidf_with_control", "TF-IDF + control", "#8296A6"),
                  ("paired_without_jargon", "Paired without jargon", ORANGE),
                  ("paired_features", "Full paired / fixed heuristic", TEAL)]
    for name, label, color in selections:
        rows = curves.loc[curves["method"].eq(name)]
        ax.step(rows["recall"], rows["precision"], where="pre", label=label, color=color, lw=2)
    ax.set(xlim=(0, 1), ylim=(0, 1.04), xlabel="Recall", ylabel="Precision")
    ax.legend(loc="center right", bbox_to_anchor=(1, .34), frameon=False, fontsize=8)

    ax = styled_axes(fig, [.57, .27, .35, .43], "Outcomes at cutoff 0.50")
    ids = ["raw_score", "paired_without_jargon", "paired_features"]
    positions = np.arange(len(ids))
    for offset, key, label, color in ((-.16, "tp", "Detected positives", TEAL), (.16, "fp", "False alerts", ORANGE)):
        bars = ax.bar(positions + offset, [report["models"][i][key] for i in ids], .3, color=color, label=label)
        ax.bar_label(bars, padding=3, color=INK)
    ax.set_xticks(positions, ["Fixed\nheuristic", "Without\njargon", "Full\npaired"])
    ax.set_ylim(0, 15.5)
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    note(fig, .15, "Interpretation",
         "The fixed heuristic and full model had the same precision–recall ranking here. At 0.50, the full model alerted\n"
         "on 12 of 12 positives and the heuristic on 2 of 12. The fixtures share vocabulary, limiting field inference.")
    return fig


def error_matrices(url, paired):
    fig = page(4, "Error analysis", "Where the models make mistakes",
               "Confusion matrices from saved predictions at the preset 0.50 cutoff.")
    panels = (
        (.095, "URL proxy labels | boosting", url["models"]["hist_gradient_boosting"]),
        (.57, "Scripted pairs | full paired model", paired["models"]["paired_features"]),
    )
    for x, title, model in panels:
        ax = fig.add_axes([x, .27, .34, .43])
        ax.set_title(title, loc="left", color=INK, fontweight="bold", fontsize=13, pad=12)
        matrix = np.array([[model["tn"], model["fp"]], [model["fn"], model["tp"]]])
        ax.imshow(matrix, cmap="Blues", aspect="auto")
        for row, column in np.ndindex(matrix.shape):
            count = matrix[row, column]
            ax.text(column, row, f"{count:,}", ha="center", va="center", weight="bold", size=18,
                    color="white" if count > matrix.max() * .56 else INK)
        ax.set_xticks([0, 1], ["Class 0", "Class 1"])
        ax.set_yticks([0, 1], ["Class 0", "Class 1"])
        ax.set(xlabel="Predicted", ylabel="Recorded label")
    note(fig, .15, "How to read these panels",
         "The left panel uses historical URL proxy labels. The right uses scenario labels from controlled fixtures.\n"
         "Each chart uses its own color scale. The two experiments measure different tasks.")
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, default=ROOT / "evaluation" / "outputs")
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = args.evaluation_dir
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    figures = (
        ("architecture", architecture(load(args.demo))),
        ("url_proxy", url_results(load(data / "url_proxy_metrics.json"), pd.read_csv(data / "url_proxy_predictions.csv"))),
        ("paired_review", paired_results(load(data / "stress_metrics.json"), pd.read_csv(data / "stress_pr_curves.csv"))),
        ("error_matrices", error_matrices(load(data / "url_proxy_metrics.json"), load(data / "stress_metrics.json"))),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with PdfPages(args.output_dir / "CloakGuard_class_brief.pdf", metadata={"Title": "CloakGuard class brief"}) as pdf:
        for name, fig in figures:
            pdf.savefig(fig, facecolor=fig.get_facecolor())
            fig.savefig(args.output_dir / f"CloakGuard_{name}.png", dpi=165)
            plt.close(fig)


if __name__ == "__main__":
    main()
