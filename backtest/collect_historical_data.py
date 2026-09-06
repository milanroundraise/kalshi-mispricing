"""
Collects historical Kalshi KXBTCD markets with matched Deribit checkpoints,
for calibration/backtesting against the fair_value pricing model.
"""

from datetime import datetime, timedelta, timezone
from data.kalshi_client import get_candlesticks, get_markets
from data.deribit_client import get_index_price, get_dvol, get_tradingview_chart_data
from models.fair_value import probability_above_strike
import csv

if __name__ == "__main__":
    now_ts = int(datetime.now(timezone.utc).timestamp())
    one_day_ago_ts = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())

    settled_markets, success = get_markets(
        "KXBTCD",
        status="settled",
        min_close_ts=one_day_ago_ts,
        max_close_ts=now_ts,
    )
    print(f"Fetched {len(settled_markets)} settled markets, success={success}")

    grouped_by_hour = {}
    for market in settled_markets:
        key = market['event_ticker']
        if key not in grouped_by_hour:
            grouped_by_hour[key] = []
        grouped_by_hour[key].append(market)

    print(f"Number of distinct hours: {len(grouped_by_hour)}")

    checkpoint_offsets_seconds = [60 * 60, 30 * 60, 10 * 60, 2 * 60]
    all_results = []

    for event_ticker, markets_in_hour in list(grouped_by_hour.items())[:2]:
        close_dt = datetime.fromisoformat(markets_in_hour[0]['close_time'])
        close_ts_ms = int(close_dt.timestamp() * 1000)
        chart_data = get_tradingview_chart_data(
            instrument_name="BTC-PERPETUAL",
            start_timestamp = close_ts_ms - (60 * 60 * 1000),
            end_timestamp = close_ts_ms + (60 * 60 * 1000),
            resolution = "60",
        )
        nearest_index = min(range(len(chart_data['ticks'])), key=lambda i: abs(chart_data['ticks'][i] - close_ts_ms))
        historical_spot_price = chart_data['close'][nearest_index]
        print(f"Event: {event_ticker}, Close Time: {close_dt}, Historical Spot: {historical_spot_price}")

        nearest_atm_market = min(markets_in_hour, key=lambda market: abs(market['floor_strike'] - historical_spot_price))
        print(f"nearest atm: {nearest_atm_market['ticker']}, strike: {nearest_atm_market['floor_strike']}, spot={historical_spot_price}")

        checkpoint_offsets_seconds = [60 * 60, 30 * 60, 10 * 60, 2 * 60]
        close_ts_seconds = int(close_dt.timestamp())
        for offset in checkpoint_offsets_seconds:
            checkpoint_ts_seconds = close_ts_seconds - offset #migos
            print(f" checkpoint: {offset}s before close -> {checkpoint_ts_seconds}")
            window_seconds = 5 * 60
            candlesticks = get_candlesticks(
                series_ticker="KXBTCD",
                market_ticker=nearest_atm_market['ticker'],
                start_ts=checkpoint_ts_seconds - window_seconds,
                end_ts=checkpoint_ts_seconds + window_seconds,
                period_interval=1,
            )
            print(candlesticks)
            nearest_candle = min(candlesticks, key=lambda c: abs(c['end_period_ts'] - checkpoint_ts_seconds))
            print(f" nearest candle: {nearest_candle['end_period_ts']}, yes_bid={nearest_candle['yes_bid']['close_dollars']}, yes_ask={nearest_candle['yes_ask']['close_dollars']}")
            dvol_data = get_dvol(
                currency="BTC",
                start_timestamp=(checkpoint_ts_seconds - 300) * 1000,
                end_timestamp=(checkpoint_ts_seconds + 300) *1000,
                resolution="60",)
            print(f" dvol: {dvol_data}")
            nearest_dvol_row = min(dvol_data, key=lambda row: abs(row[0] - (checkpoint_ts_seconds * 1000)))
            implied_dvol_percent = nearest_dvol_row[4]
            converted_dvol = implied_dvol_percent / 100
            print(f" nearest dvol: {nearest_dvol_row}, implied_dvol_percent: {implied_dvol_percent}, converted_dvol: {converted_dvol}")
            checkpoint_ts_ms = checkpoint_ts_seconds * 1000
            spot_chart_data = get_tradingview_chart_data(
                instrument_name="BTC-PERPETUAL",
                start_timestamp=checkpoint_ts_ms - (5 * 60 * 1000),
                end_timestamp=checkpoint_ts_ms + (5 * 60 * 1000),
                resolution="1",
            )
            spot_nearest_index = min(range(len(spot_chart_data['ticks'])), key=lambda i: abs(spot_chart_data['ticks'][i] - checkpoint_ts_ms))
            checkpoint_spot_price = spot_chart_data['close'][spot_nearest_index]
            time_to_expiry_seconds = close_ts_seconds - checkpoint_ts_seconds
            model_probability = probability_above_strike(
                spot=checkpoint_spot_price,
                strike=nearest_atm_market['floor_strike'],
                time_to_expiry_seconds=time_to_expiry_seconds,
                volatility=converted_dvol,)
            print(f"model probability: {model_probability}")
            result_row = {
                "event_ticker": event_ticker,
                "market_ticker": nearest_atm_market['ticker'],
                "checkpoint_offset_seconds": offset,
                "checkpoint_ts": checkpoint_ts_seconds,
                "model_probability": model_probability,
                "kalshi_yes_bid": float(nearest_candle['yes_bid']['close_dollars']),
                "kalshi_yes_ask": float(nearest_candle['yes_ask']['close_dollars']),
                "actual_result": nearest_atm_market['result'],
            }
            all_results.append(result_row)
            print(f"Total results collected: {len(all_results)}")
            print(all_results[0])

    with open ("backtest_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
        writer.writeheader()
        writer.writerows(all_results)

    print(f"saved {len(all_results)} results to backtest_results.csv")