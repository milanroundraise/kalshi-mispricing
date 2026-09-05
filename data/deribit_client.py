import requests
from data.kalshi_client import fetch_with_backoff
from datetime import datetime, timedelta, timezone

DERIBIT_BASE_URL = "https://www.deribit.com/api/v2"

def get_index_price(index_name: str = "btc_usd") -> float:
    url = f"{DERIBIT_BASE_URL}/public/get_index_price?index_name={index_name}"
    response = fetch_with_backoff(url)
    if response.status_code != 200:
        print("Error fetching index price:", response.status_code)
        return None
    return response.json()['result']['index_price']



def get_dvol(currency: str = "BTC", start_timestamp: int = None, end_timestamp: int = None, resolution: str = "60") -> list[dict]:
    params = {
        "currency": currency,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "resolution": resolution,
    }
    url = f"{DERIBIT_BASE_URL}/public/get_volatility_index_data"
    response = fetch_with_backoff(url, params)
    if response.status_code != 200:
        print("Error fetching DVOL:", response.status_code)
        return None
    #print(response.json())
    return response.json()['result']['data']


def get_option_chain(currency: str = "BTC") -> list[dict]:
    params = {
        "currency": currency,
        "kind": "option",
    }
    url = f"{DERIBIT_BASE_URL}/public/get_book_summary_by_currency"
    response = fetch_with_backoff(url, params)
    if response.status_code != 200:
        print("Error fetching option chain:", response.status_code)
        return None
    return response.json()['result']

def get_tradingview_chart_data(instrument_name: str, start_timestamp: int, end_timestamp: int, resolution: str = "60") -> dict:
    """
    Get historical OHLCV candle data for an instrument (index, future, or option)
    from Deribit's TradingView-compatible endpoint.

    Endpoint: public/get_tradingview_chart_data
    Params: instrument_name, start_timestamp, end_timestamp (ms), resolution

    The raw response is printed before accessing its result so the endpoint
    shape can be inspected empirically.
    """
    params = {
        "instrument_name": instrument_name,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "resolution": resolution,
    }
    url = f"{DERIBIT_BASE_URL}/public/get_tradingview_chart_data"
    response = fetch_with_backoff(url, params)
    if response.status_code != 200:
        print("Error fetching TradingView chart data:", response.status_code)
        return None

    raw_response = response.json()
    print(raw_response)
    return raw_response["result"]


if __name__ == "__main__":
    index_price = get_index_price()
    print(index_price)
    
    dvol_end_dt = datetime.now()
    dvol_start_dt = dvol_end_dt - timedelta(hours=6)
    dvol_start_ts = int(dvol_start_dt.timestamp() * 1000)
    dvol_end_ts = int(dvol_end_dt.timestamp() * 1000)
    dvol = get_dvol(currency="BTC", start_timestamp=(dvol_start_ts), end_timestamp=(dvol_end_ts), resolution="60")
    print(dvol)

    option_chain = get_option_chain(currency="BTC")
    print(option_chain)

    chart_end_dt = datetime.now(timezone.utc)
    chart_start_dt = chart_end_dt - timedelta(hours=6)
    chart_start_ts = int(chart_start_dt.timestamp() * 1000)
    chart_end_ts = int(chart_end_dt.timestamp() * 1000)
    chart_data = get_tradingview_chart_data(
        instrument_name="BTC-PERPETUAL",
        start_timestamp=chart_start_ts,
        end_timestamp=chart_end_ts,
        resolution="60",
    )
    print(chart_data)

    print()