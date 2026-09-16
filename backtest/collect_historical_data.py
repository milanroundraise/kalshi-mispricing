"""
Collects historical Kalshi KXBTCD markets with matched Deribit checkpoints,
for calibration/backtesting against the fair_value pricing model.
"""

from datetime import datetime, timedelta, timezone
from data.kalshi_client import get_candlesticks, get_markets
from data.deribit_client import get_index_price, get_dvol, get_tradingview_chart_data
from models.fair_value import implied_volatility, probability_above_strike
import csv

if __name__ == "__main__":
    now_ts = int(datetime.now(timezone.utc).timestamp())
    one_week_ago_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())

    settled_markets, success = get_markets(
        "KXBTCD",
        status="settled",
        min_close_ts=one_week_ago_ts,
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
    fieldnames = [
        "event_ticker", "market_ticker", "checkpoint_offset_seconds", "checkpoint_ts",
        "model_probability", "kalshi_yes_bid", "kalshi_yes_ask", "actual_result",
        "kalshi_implied_vol", "converted_dvol",
    ]

    with open("backtest_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for event_ticker, markets_in_hour in grouped_by_hour.items():
            close_dt = datetime.fromisoformat(markets_in_hour[0]['close_time'])
            close_ts_ms = int(close_dt.timestamp() * 1000)
            chart_data = get_tradingview_chart_data(
                instrument_name="BTC-PERPETUAL",
                start_timestamp=close_ts_ms - (60 * 60 * 1000),
                end_timestamp=close_ts_ms + (60 * 60 * 1000),
                resolution="60",
            )
            nearest_index = min(range(len(chart_data['ticks'])), key=lambda i: abs(chart_data['ticks'][i] - close_ts_ms))
            historical_spot_price = chart_data['close'][nearest_index]
            print(f"Event: {event_ticker}, Close Time: {close_dt}, Historical Spot: {historical_spot_price}")

            nearest_atm_market = min(markets_in_hour, key=lambda market: abs(market['floor_strike'] - historical_spot_price))
            print(f"nearest atm: {nearest_atm_market['ticker']}, strike: {nearest_atm_market['floor_strike']}, spot={historical_spot_price}")

            close_ts_seconds = int(close_dt.timestamp())
            for offset in checkpoint_offsets_seconds:
                checkpoint_ts_seconds = close_ts_seconds - offset
            
                window_seconds = 5 * 60
                candlesticks = get_candlesticks(
                    series_ticker="KXBTCD",
                    market_ticker=nearest_atm_market['ticker'],
                    start_ts=checkpoint_ts_seconds - window_seconds,
                    end_ts=checkpoint_ts_seconds + window_seconds,
                    period_interval=1,
                )


                if not candlesticks:
                    print(f"No candlesticks found for market {nearest_atm_market['ticker']} around checkpoint {checkpoint_ts_seconds}")
                    continue
                nearest_candle = min(candlesticks, key=lambda c: abs(c['end_period_ts'] - checkpoint_ts_seconds))
           
                dvol_data = get_dvol(
                    currency="BTC",
                    start_timestamp=(checkpoint_ts_seconds - 300) * 1000,
                    end_timestamp=(checkpoint_ts_seconds + 300) * 1000,
                    resolution="60",
                )

                if not dvol_data:
                    print(f"No dvol data found for market {nearest_atm_market['ticker']} around checkpoint {checkpoint_ts_seconds}")
                    continue
            
                nearest_dvol_row = min(dvol_data, key=lambda row: abs(row[0] - (checkpoint_ts_seconds * 1000)))
                implied_dvol_percent = nearest_dvol_row[4]
                converted_dvol = implied_dvol_percent / 100
          
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
                    volatility=converted_dvol,
                )
            
                kalshi_yes_bid = float(nearest_candle['yes_bid']['close_dollars'])
                kalshi_yes_ask = float(nearest_candle['yes_ask']['close_dollars'])
                kalshi_midpoint_probability = (kalshi_yes_bid + kalshi_yes_ask) / 2
            
                try:
                    kalshi_implied_vol = implied_volatility(
                        spot=checkpoint_spot_price,
                        strike=nearest_atm_market['floor_strike'],
                        time_to_expiry_seconds=time_to_expiry_seconds,
                        market_probability=kalshi_midpoint_probability,
                    )
                except ValueError as e:
                    print(f"cant compute implied vol for this checkpoint {e}")
                    kalshi_implied_vol = None
                if kalshi_implied_vol is not None:
                    check_probability = probability_above_strike(
                        spot=checkpoint_spot_price,
                        strike=nearest_atm_market['floor_strike'],
                        time_to_expiry_seconds=time_to_expiry_seconds,
                        volatility=kalshi_implied_vol,
                    )
                    assert abs(check_probability - kalshi_midpoint_probability) < 1e-6, \
                        f"Round-trip mismatch: {check_probability} vs {kalshi_midpoint_probability}"
                result_row = {
                    "event_ticker": event_ticker,
                    "market_ticker": nearest_atm_market['ticker'],
                    "checkpoint_offset_seconds": offset,
                    "checkpoint_ts": checkpoint_ts_seconds,
                    "model_probability": model_probability,
                    "kalshi_yes_bid": kalshi_yes_bid,
                    "kalshi_yes_ask": kalshi_yes_ask,
                    "actual_result": nearest_atm_market['result'],
                    "kalshi_implied_vol": kalshi_implied_vol,
                    "converted_dvol": converted_dvol,
                }
                writer.writerow(result_row)
                f.flush()
                print(f" checkpoint {offset}s: model={model_probability:.3f}, kalshi_mid={kalshi_midpoint_probability:.3f}, actual={nearest_atm_market['result']}")

    print("Done collecting historical data, results written to backtest_results.csv")