""" Simulates trading book against historical backtest dataset using fair value model's edge over Kalshi price as a trade signal."""

import csv
from backtest.calibration import make_quantile_buckets, summarise_bucket

base_size = 1


def print_trade_report(trades: list[dict], checkpoint_count: int, threshold: float) -> None:
    total_pnl = sum(trade["pnl"] for trade in trades)
    total_size = sum(trade["size"] for trade in trades)
    average_pnl = total_pnl / len(trades) if trades else 0
    wins = sum(1 for trade in trades if trade["payout"] == 1)
    win_rate = wins / len(trades) if trades else 0
    sorted_by_pnl = sorted(trades, key=lambda trade: trade["pnl"], reverse=True)
    top_5_pnl = sum(trade["pnl"] for trade in sorted_by_pnl[:5])
    top_5_share = top_5_pnl / total_pnl if total_pnl != 0 else 0

    print("\n" + "=" * 90)
    print("--- trading book backtest ---")
    print("=" * 90)
    print(f"Trigger threshold: {threshold:.4f} | Trades: {len(trades)} / {checkpoint_count} checkpoints")
    print("-" * 90)
    print(
        f"{'#':>3}  {'Side':<4} {'Entry':>8} {'Edge':>8} "
        f"{'Size':>8} {'Result':>8} {'PnL':>10} {'Running PnL':>13}"
    )
    print("-" * 90)

    running_pnl = 0
    for index, trade in enumerate(trades, start=1):
        running_pnl += trade["pnl"]
        result = "WIN" if trade["payout"] else "LOSS"
        print(
            f"{index:>3}  {trade['direction']:<4} "
            f"{trade['entry_price']:>8.4f} {trade['edge']:>+8.4f} "
            f"{trade['size']:>8.4f} {result:>8} "
            f"{trade['pnl']:>+10.4f} {running_pnl:>+13.4f}"
        )

    print("-" * 90)
    print(
        f"Total PnL: {total_pnl:+.4f} | Average PnL/trade: {average_pnl:+.4f} "
        f"| Win rate: {win_rate:.1%} ({wins}/{len(trades)}) | Total size: {total_size:.4f}"
    )
    print(f"Top 5 trades' share of total PnL: {top_5_share:.1%}")
    print("=" * 90)

    """ above function was made because i was going cross eyed trying to read the output of the trades in a non ordered format without columns/headers - it's a mess. """

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

    buckets = make_quantile_buckets(cleaned_rows, num_buckets=8)
    bucket_gaps = [abs(summarise_bucket(bucket)['calibration_gap']) for bucket in buckets]
    threshold = sum(bucket_gaps) / len(bucket_gaps)

    simulated_trades = []
    for row in cleaned_rows:
        kalshi_midpoint = (row['kalshi_yes_bid'] + row['kalshi_yes_ask']) / 2
        edge = row['model_probability'] - kalshi_midpoint
        if abs(edge) < threshold:
            continue
        if edge > 0:
            direction = "YES"
            entry_price = row['kalshi_yes_ask']
        else:
            direction = "NO"
            entry_price = 1 - row['kalshi_yes_bid']
        size = base_size * (abs(edge) / threshold)
        if (direction == "YES" and row['actual_result_binary'] == 1) or (direction == "NO" and row['actual_result_binary'] == 0):
            payout = 1
        else:
            payout = 0
        pnl = (payout - entry_price) * size
        trade = {
            "direction": direction,
            "entry_price": entry_price,
            "edge": edge, 
            "actual_result" : row['actual_result_binary'],
            "size": size,
            "payout": payout,
            "pnl": pnl
        }
        simulated_trades.append(trade)

    print_trade_report(simulated_trades, len(cleaned_rows), threshold)