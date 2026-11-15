"""Compute accuracy metrics against eval/ground_truth.csv (docs/evaluation.md).

Usage:
    python eval/run_eval.py --results /path/to/results.csv --truth eval/ground_truth.csv --out eval/reports/report_YYYYMMDD.md
"""
import argparse
import csv
import statistics
from collections import Counter
from pathlib import Path


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(value: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_report(results: list[dict], truth: list[dict], config_note: str) -> str:
    results_by_name = {r["image_name"]: r for r in results}
    truth_by_name = {t["image_name"]: t for t in truth}
    missing = [name for name in truth_by_name if name not in results_by_name]

    rows = []
    for name, t in truth_by_name.items():
        r = results_by_name.get(name)
        if r is None:
            continue
        rows.append((name, t, r))

    def split_rows(split_value: str | None):
        if split_value is None:
            return rows
        return [row for row in rows if row[1].get("split", "tune") == split_value]

    def metrics_for(subset: list) -> dict:
        n = len(subset)
        truth_ok = [row for row in subset if row[1]["truth_status"] == "OK"]
        pred_ok = [row for row in subset if row[2]["status"] == "OK"]
        wrong_extractions = [row for row in pred_ok if row[2]["awb"] != row[1]["truth_awb"]]
        correct_ok_awb = [row for row in pred_ok if row[1]["truth_status"] == "OK" and row[2]["awb"] == row[1]["truth_awb"]]
        silent_misses = [row for row in subset if row[1]["truth_status"] == "FLAGGED" and row[2]["status"] == "OK"]

        flag_confusion = Counter()
        for name, t, r in subset:
            truth_label = t["truth_flag"] if t["truth_status"] == "FLAGGED" else "OK"
            pred_label = r["primary_flag"] if r["status"] in ("FLAGGED", "ERROR") else "OK"
            flag_confusion[(truth_label, pred_label or "OK")] += 1

        weight_checks = [row for row in subset if _num(row[1].get("truth_weight_kg")) is not None]
        weight_correct = [row for row in weight_checks if _num(row[2].get("weight_kg")) is not None and abs(_num(row[2]["weight_kg"]) - _num(row[1]["truth_weight_kg"])) <= 0.01]
        weight_wrong_nonempty = [
            row for row in weight_checks
            if _num(row[2].get("weight_kg")) is not None and abs(_num(row[2]["weight_kg"]) - _num(row[1]["truth_weight_kg"])) > 0.01
        ]

        dim_checks = [row for row in subset if _num(row[1].get("truth_length_cm")) is not None]
        def dim_match(row) -> bool:
            t, r = row[1], row[2]
            pred_vals = (_num(r.get("length_cm")), _num(r.get("width_cm")), _num(r.get("height_cm")))
            truth_vals = (_num(t.get("truth_length_cm")), _num(t.get("truth_width_cm")), _num(t.get("truth_height_cm")))
            if any(v is None for v in pred_vals):
                return False
            return all(abs(p - tv) <= 0.5 for p, tv in zip(pred_vals, truth_vals, strict=False))
        dim_correct = [row for row in dim_checks if dim_match(row)]
        dim_wrong_nonempty = [row for row in dim_checks if _num(row[2].get("length_cm")) is not None and not dim_match(row)]

        return {
            "n": n,
            "wrong_extraction_rate": len(wrong_extractions) / len(pred_ok) if pred_ok else 0.0,
            "wrong_extractions": wrong_extractions,
            "awb_recall": len(correct_ok_awb) / len(truth_ok) if truth_ok else 0.0,
            "truth_ok_count": len(truth_ok),
            "silent_miss_rate": len(silent_misses) / sum(1 for row in subset if row[1]["truth_status"] == "FLAGGED") if any(row[1]["truth_status"] == "FLAGGED" for row in subset) else 0.0,
            "silent_misses": silent_misses,
            "flag_confusion": flag_confusion,
            "weight_checks_n": len(weight_checks),
            "weight_correct_n": len(weight_correct),
            "weight_wrong_nonempty": weight_wrong_nonempty,
            "dim_checks_n": len(dim_checks),
            "dim_correct_n": len(dim_correct),
            "dim_wrong_nonempty": dim_wrong_nonempty,
        }

    overall = metrics_for(rows)
    holdout_rows = split_rows("holdout")
    holdout = metrics_for(holdout_rows) if holdout_rows else None

    times_ms = [_num(r.get("processing_ms")) for _, _, r in rows]
    times_ms = [t for t in times_ms if t is not None]

    def fmt_pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    lines = []
    lines.append(f"# Evaluation report\n\nConfig: {config_note}\n")
    lines.append(f"Ground truth images: {len(truth_by_name)}; matched to results: {len(rows)}; missing from results: {len(missing)}\n")
    if missing:
        lines.append(f"Missing (not in results.csv): {', '.join(missing)}\n")

    for label, m in (("Overall", overall), ("Held-out split", holdout)):
        if m is None:
            continue
        lines.append(f"\n## {label} (n={m['n']})\n")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Wrong-extraction rate (target 0%) | {fmt_pct(m['wrong_extraction_rate'])} ({len(m['wrong_extractions'])} / predicted-OK rows) |")
        lines.append(f"| AWB recall on readable set | {fmt_pct(m['awb_recall'])} ({m['truth_ok_count']} truth-OK images) |")
        lines.append(f"| Silent-miss rate (truth FLAGGED, predicted OK) | {fmt_pct(m['silent_miss_rate'])} |")
        if m["weight_checks_n"]:
            lines.append(f"| Weight accuracy (within 0.01kg) | {m['weight_correct_n']}/{m['weight_checks_n']} |")
        if m["dim_checks_n"]:
            lines.append(f"| Dimension accuracy (within 0.5cm) | {m['dim_correct_n']}/{m['dim_checks_n']} |")

        lines.append("\nFlag confusion (truth, predicted) -> count:\n")
        for (t_label, p_label), count in sorted(m["flag_confusion"].items()):
            marker = "" if t_label == p_label else "  <-- mismatch"
            lines.append(f"- ({t_label}, {p_label}): {count}{marker}")

    lines.append("\n## Every wrong or silently-missed case\n")
    wrong_cases = list({name: (name, t, r) for name, t, r in overall["wrong_extractions"] + overall["silent_misses"]}.values())
    if not wrong_cases:
        lines.append("None.\n")
    else:
        for name, t, r in wrong_cases:
            lines.append(
                f"- `{name}`: truth_status={t['truth_status']} truth_flag={t.get('truth_flag')} "
                f"truth_awb={t.get('truth_awb')!r} | predicted status={r['status']} flag={r.get('primary_flag')} "
                f"awb={r.get('awb')!r} reason={r.get('flag_reason')!r}"
            )

    if overall["weight_wrong_nonempty"] or overall["dim_wrong_nonempty"]:
        lines.append("\n## Non-empty but wrong weight/dimension values\n")
        for name, t, r in overall["weight_wrong_nonempty"]:
            lines.append(f"- `{name}`: weight truth={t.get('truth_weight_kg')} predicted={r.get('weight_kg')}")
        for name, t, r in overall["dim_wrong_nonempty"]:
            lines.append(f"- `{name}`: dims truth=({t.get('truth_length_cm')},{t.get('truth_width_cm')},{t.get('truth_height_cm')}) predicted=({r.get('length_cm')},{r.get('width_cm')},{r.get('height_cm')})")

    if times_ms:
        times_ms.sort()
        mean_ms = statistics.mean(times_ms)
        p95_ms = times_ms[int(len(times_ms) * 0.95) - 1]
        lines.append("\n## Throughput\n")
        lines.append(f"- mean: {mean_ms:.0f} ms/image, p95: {p95_ms:.0f} ms/image (n={len(times_ms)})")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--truth", type=Path, default=Path("eval/ground_truth.csv"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config-note", type=str, default="heuristic scene provider, rapidocr, zxing-cpp")
    args = parser.parse_args()

    results = load_csv(args.results)
    truth = load_csv(args.truth)
    report = build_report(results, truth, args.config_note)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
