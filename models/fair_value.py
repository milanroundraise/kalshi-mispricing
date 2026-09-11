"""
Black-Scholes-style digital option pricing.
Computes the fair probability that an underlying asset finishes ABOVE a given
strike at expiry, given spot price, volatility, time to expiry, and risk-free rate.
"""

import math
from datetime import datetime
from data.deribit_client import get_tradingview_chart_data, get_option_chain 

def normal_cdf(x: float) -> float:
    normal_function = (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
    return normal_function

def inverse_normal_cdf(p: float) -> float:
    if p <= 0 or p >= 1:
        raise ValueError("p must be strictly between 0 and 1")

    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]

    p_low = 0.02425
    p_high = 1 - p_low

    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        numerator = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
        denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
        return numerator / denominator
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        numerator = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        denominator = (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        return numerator / denominator
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        numerator = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
        denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
        return -(numerator / denominator)


def probability_above_strike(
    spot: float,
    strike: float,
    time_to_expiry_seconds: float,
    volatility: float,
    risk_free_rate: float = 0.0,
) -> float:
    if time_to_expiry_seconds <= 0:
        raise ValueError("time_to_expiry_seconds must be positive")
    if volatility <= 0: 
        raise ValueError("volatility must be positive")
    T_years = time_to_expiry_seconds / (365 * 24 * 60 *60)
    d2 = (math.log(spot / strike) + (risk_free_rate - 0.5 * volatility ** 2) * T_years) / (volatility * math.sqrt(T_years))
    probability = normal_cdf(d2)
    return probability

def get_nearest_atm_option(option_chain: list[dict], spot_price: float, target_expiry_ts: int) -> dict:
    nearest = min(option_chain, key=lambda instrument: abs(
        datetime.strptime(instrument['underlying_index'].split('-')[1], "%d%b%y").timestamp() - target_expiry_ts))

    same_expiry_options = []
    for instrument in option_chain:
        if instrument['underlying_index'] == nearest['underlying_index']:
            same_expiry_options.append(instrument)

    nearest_strike_option = min(same_expiry_options, key=lambda instrument: abs(
        float(instrument['instrument_name'].split('-')[2]) - spot_price))

    target_strike = float(nearest_strike_option['instrument_name'].split('-')[2])
    same_strike_options = []
    for instrument in same_expiry_options:
        instrument_strike = float(instrument['instrument_name'].split('-')[2])
        if instrument_strike == target_strike:
            same_strike_options.append(instrument)

    option_a = same_strike_options[0]
    option_b = same_strike_options[1]

    a_has_quotes = option_a['bid_price'] is not None and option_a['ask_price'] is not None
    b_has_quotes = option_b['bid_price'] is not None and option_b['ask_price'] is not None

    if a_has_quotes and not b_has_quotes:
        chosen_option = option_a
    elif b_has_quotes and not a_has_quotes:
        chosen_option = option_b
    elif a_has_quotes and b_has_quotes:
        if option_a['volume'] > option_b['volume']:
            chosen_option = option_a
        elif option_a['volume'] == option_b['volume']:
            chosen_option = option_a if option_a['open_interest'] > option_b['open_interest'] else option_b
        else:
            chosen_option = option_b
    else:
        raise ValueError(f"Neither option has valid quotes at strike {target_strike}")


    return chosen_option

def implied_volatility(
    spot: float,
    strike: float,
    time_to_expiry_seconds: float,
    market_probability: float,
    risk_free_rate: float = 0.0,
) -> float:
    if time_to_expiry_seconds <= 0:
        raise ValueError("time_to_expiry_seconds must be positive")
    T_years = time_to_expiry_seconds / (365 * 24 * 60 * 60)
    d2 = inverse_normal_cdf(market_probability)
    A = 0.5 * T_years
    B = d2 * math.sqrt(T_years)
    C = -math.log(spot/strike) - risk_free_rate * T_years
    discriminant = B**2 - 4*A*C
    if discriminant < 0:
        raise ValueError("Discriminant is negative, cannot compute implied volatility")
    sigma = (-B + math.sqrt(discriminant)) / (2*A)
    return sigma

if __name__ == "__main__":
    spot = 100
    strike = 100
    time_to_expiry_seconds = 60 * 60 * 24 * 30
    volatility = 0.3
    risk_free_rate = 0.01

    market_probability = probability_above_strike(
        spot=spot,
        strike=strike,
        time_to_expiry_seconds=time_to_expiry_seconds,
        volatility=volatility,
        risk_free_rate=risk_free_rate,
    )
    recovered_volatility = implied_volatility(
        spot=spot,
        strike=strike,
        time_to_expiry_seconds=time_to_expiry_seconds,
        market_probability=market_probability,
        risk_free_rate=risk_free_rate,
    )

    print(f"Market probability: {market_probability:.12f}")
    print(f"Recovered volatility: {recovered_volatility:.12f}")
    assert math.isclose(recovered_volatility, volatility, rel_tol=1e-9, abs_tol=1e-9)