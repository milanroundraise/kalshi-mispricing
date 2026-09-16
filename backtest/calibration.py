"""
Calibration and hypothesis testing against the historical backtest dataset,
validating the fair_value pricing model's forward and inverse views.
"""

import csv
import math
from models.fair_value import normal_cdf

def make_quantile_buckets(rows: list[dict], num_buckets: int = 8) -> list[list[dict]]:
    sorted_rows = sorted(rows, key=lambda r: r['model_probability'])
    bucket_size = len(sorted_rows) // num_buckets
    buckets = []
    for i in range(num_buckets):
        start = i * bucket_size
        if i == num_buckets - 1:
            end = len(sorted_rows)
        else:
            end = start + bucket_size
        buckets.append(sorted_rows[start:end])
    return buckets

def summarise_bucket(bucket: list[dict]) -> dict:
    avg_model_probability = sum(row['model_probability'] for row in bucket) / len(bucket)
    avg_actual_result = sum(row['actual_result_binary'] for row in bucket) / len(bucket)
    calibration_gap = avg_actual_result - avg_model_probability
    return {
        "count": len(bucket),
        "avg_model_probability": avg_model_probability,
        "avg_actual_result": avg_actual_result,
        "calibration_gap": calibration_gap,
    }

if __name__ == "__main__":
    with open("backtest_results.csv", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    cleaned_rows = []
    for row in rows:
        checkpoint_offset_seconds = int(row["checkpoint_offset_seconds"])
        checkpoint_ts = int(row["checkpoint_ts"])
        model_probability = float(row['model_probability'])
        kalshi_yes_bid = float(row['kalshi_yes_bid'])
        kalshi_yes_ask = float(row['kalshi_yes_ask'])
        converted_dvol = float(row['converted_dvol'])
        actual_result_binary = 1 if row['actual_result'] == "yes" else 0
        if row['kalshi_implied_vol'] == "":
            kalshi_implied_vol = None
        else:
            kalshi_implied_vol = float(row['kalshi_implied_vol'])
        cleaned_row = {
            "checkpoint_offset_seconds": checkpoint_offset_seconds,
            "checkpoint_ts": checkpoint_ts,
            "model_probability": model_probability,
            "kalshi_yes_bid": kalshi_yes_bid,
            "kalshi_yes_ask": kalshi_yes_ask,
            "kalshi_implied_vol": kalshi_implied_vol,
            "actual_result_binary": actual_result_binary,
            "converted_dvol": converted_dvol
        }
        cleaned_rows.append(cleaned_row)


    print(f"Loaded {len(rows)} rows")
    print(f"Cleaned {len(cleaned_rows)} rows")
    print(cleaned_rows[0])
    print(type(cleaned_rows[0]['model_probability']))
    print(type(cleaned_rows[0]['checkpoint_offset_seconds']))
    buckets = make_quantile_buckets(cleaned_rows, num_buckets=8)
    for i, bucket in enumerate(buckets):
        summary = summarise_bucket(bucket)
        print(f"Bucket {i}: {len(bucket)} rows")
        print(summary)
        print(f"Calibration gap: {summary['calibration_gap']}")

    for offset in [3600, 1800, 600, 120]:
        rows_for_offset = [row for row in cleaned_rows if row['checkpoint_offset_seconds'] == offset]
        print(f"Offset {offset}: {len(rows_for_offset)} rows")
        offset_buckets = make_quantile_buckets(rows_for_offset, num_buckets=5)
        for offset_bucket_index, offset_bucket in enumerate(offset_buckets):
            offset_summary = summarise_bucket(offset_bucket)
            print(f"Bucket {offset_bucket_index}: {len(offset_bucket)} rows")
            print(offset_summary)
            print(f"Calibration gap: {offset_summary['calibration_gap']}")

    filtered_gaps = []
    for row in cleaned_rows:
        if row['kalshi_implied_vol'] is None:
            continue
        midpoint = (row['kalshi_yes_bid'] + row['kalshi_yes_ask']) / 2
        if midpoint < 0.05 or midpoint > 0.95:
            continue
        if row['kalshi_implied_vol'] > 2.0:
            continue
        gap = row['kalshi_implied_vol'] - row['converted_dvol']
        filtered_gaps.append(gap)

    print(f"Filtered gaps: {len(filtered_gaps)} out of {len(cleaned_rows)} total rows")

    mean_gap = sum(filtered_gaps) / len(filtered_gaps)
    variance = sum((x- mean_gap)**2 for x in filtered_gaps) / (len(filtered_gaps) - 1)
    std_dev = math.sqrt(variance)
    print(f"Mean gap: {mean_gap}, Std Dev: {std_dev}")

    n = len(filtered_gaps)
    standard_error = std_dev / math.sqrt(n)
    z_statistic = mean_gap / standard_error
    print(f"n={n}, Standard Error: {standard_error}, Z-statistic: {z_statistic}")

    p_value = 2 * (1 - normal_cdf(abs(z_statistic)))
    print(f"P-value: {p_value}")