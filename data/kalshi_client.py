from time import sleep
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"  
series_ticker = "KXBTCD"

def fetch_with_backoff(url, params=None):
    for attempt in range (10):
        base_delay = 1
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response
        if response.status_code == 429:
            print("Rate limited. Retrying")
            wait_time = base_delay * (2 ** attempt)
            sleep(wait_time)
        else:
            return response
    return response
            

def get_markets(
    series_ticker: str,
    status: str = "open",
    min_close_ts: int | None = None,
    max_close_ts: int | None = None,
) -> tuple[list[dict], bool]:
    all_markets = []
    cursor = None
    success_flag = False
    while True:
        url = f"{BASE_URL}/markets?series_ticker={series_ticker}&limit=100&status={status}"
        if min_close_ts is not None:
            url += f"&min_close_ts={min_close_ts}"
        if max_close_ts is not None:
            url += f"&max_close_ts={max_close_ts}"
        if cursor:
            url += f"&cursor={cursor}"
        response = fetch_with_backoff(url)
        if response.status_code != 200:
            print("Error fetching markets:", response.status_code)
            break
        data = response.json()
        all_markets.extend(data['markets'])
        cursor = data.get('cursor')
        if not cursor:
            success_flag = True
            break
        print(f"Fetched {len(data['markets'])} markets, total: {len(all_markets)}")
    return all_markets, success_flag



def get_candlesticks(series_ticker: str, market_ticker: str, start_ts: int, end_ts: int, period_interval: int = 1) -> list[dict]:
    params = {
        "start_ts": start_ts, 
        "end_ts": end_ts,
        "period_interval": period_interval,
    }
    url = f"{BASE_URL}/series/{series_ticker}/markets/{market_ticker}/candlesticks"
    response = fetch_with_backoff(url, params)
    if response.status_code != 200:
        print("Error fetching candlesticks:", response.status_code)
        return []
    data = response.json()
    return data['candlesticks']

def get_tradingview_chart_data(instrument_name: str, start_timestamp: int, end_timestamp: int, resolution: str = "60") -> dict:
    """
    Get historical OHLCV candle data for an instrument (index, future, or option)
    from Deribit's TradingView-compatible endpoint.

    Endpoint: public/get_tradingview_chart_data
    Params: instrument_name, start_timestamp, end_timestamp (ms), resolution

    TODO:
    - build URL/params, same pattern as get_dvol
    - fetch_with_backoff, check status
    - print the raw response once and inspect the shape before assuming keys —
      this response format is likely DIFFERENT from get_dvol's OHLC-candle-list
      shape (recall it's described as "TradingView-compatible," which often means
      separate parallel arrays: one list of timestamps ('ticks'), one list of
      opens, one of highs/lows/closes, etc. — rather than one list of [ts, o, h, l, c]
      tuples like get_dvol returns. Don't assume — check.)
    - return whatever raw structure comes back; don't parse/filter here (same
      single-responsibility principle as your other data-layer functions)

    Also worth testing empirically: what instrument_name actually works for
    plain BTC spot/index price — "btc_usd"? "BTC-PERPETUAL"? something else?
    Try a couple and see what returns real data vs an error.
    """
    pass

if __name__ == "__main__":
    markets, success = get_markets(series_ticker)
    if not success or not markets:
        print("Failed to fetch markets")
        raise SystemExit(1)

    print(f"Total markets fetched: {len(markets)}")
    market = markets[0]
    print(market)

    start_dt = datetime.fromisoformat(market['open_time'])
    start_ts = int(start_dt.timestamp())

    close_dt = datetime.fromisoformat(market['close_time'])
    close_ts = int(close_dt.timestamp())

    candlesticks = get_candlesticks(series_ticker, market['ticker'], start_ts, close_ts)
    print(candlesticks)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    four_days_ago_ts = int((datetime.now(timezone.utc) - timedelta(days=4)).timestamp())
    settled_markets, success = get_markets(
        "KXBTCD",
        status="settled",
        min_close_ts=four_days_ago_ts,
        max_close_ts=now_ts,
    )
    print(f"Fetched {len(settled_markets)} settled markets, success={success}")
    if settled_markets:
        print(settled_markets[0])