"""
Collects historical Kalshi KXBTCD markets with matched Deribit checkpoints,
for calibration/backtesting against the fair_value pricing model.
"""

from datetime import datetime, timedelta, timezone
from data.kalshi_client import get_markets
from data.deribit_client import get_index_price, get_dvol, get_tradingview_chart_data

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

    for event_ticker, markets_in_hour in grouped_by_hour.items():
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
