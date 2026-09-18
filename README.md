# Kalshi-Mispricing

Testing whether Kalshi's hourly Bitcoin threshold markets (`KXBTCD`) are mispriced relative to the volatility Deribit's options market is pricing in. Kalshi runs an hourly ladder of "will BTC be above $X at the top of the hour" contracts, which is structurally just a binary digital option — so I built a Black-Scholes pricer from scratch, fed it an independent volatility estimate from Deribit, and compared the fair value against what Kalshi's own market actually charges.

Everything here — the normal CDF, its inverse, the implied-vol solver, the hypothesis test — is hand-derived and hand-implemented. No `scipy.stats`. Partly because I wanted to actually understand the mechanics well enough to reuse them, partly because building it myself caught a bunch of bugs I'd never have noticed just importing a library.

Full writeup with the derivations and charts is in [`kalshi_mispricing_report.pdf`](./kalshi_mispricing_report.pdf).

## What it actually found

Short version: the pricing model has real, monotonic discriminative power, and there's a statistically significant gap between Kalshi-implied and Deribit-implied volatility (p ≈ 5.6×10⁻⁹, n=162). But the model isn't perfectly calibrated — it shows a structured, S-shaped bias I can mostly attribute to using a 30-day vol index to price contracts that expire in minutes. And my first attempt at trading the signal was closer to gambling than to a real edge: 24% win rate, top 5 trades carrying 58% of the profit. A disciplined, capped version of the same rule held up a lot better.

## Structure

```
data/
  kalshi_client.py      # Kalshi public API — markets, candlesticks, pagination + backoff
  deribit_client.py     # Deribit public API — index price, DVOL, option chain, TradingView chart data

models/
  fair_value.py         # the actual maths — normal CDF, inverse normal CDF, digital option
                         # pricer, implied-vol solver, ATM option selector

backtest/
  collect_historical_data.py   # pulls a week of settled KXBTCD markets, matches 4 checkpoints
                                # per market against Deribit spot/vol, saves to CSV
  calibration.py               # quantile bucketing, calibration gap, the hand-rolled t-test
  trading_book.py              # simulates a paper trading rule against the collected data
```

Nothing here needs auth or an API key — both Kalshi and Deribit's public market-data endpoints are open. `backtest_results.csv` is the actual dataset from the run described in the writeup (7 days, 655 checkpoints, 164 hourly markets).

## Running it

```bash
pip install requests

# pull a fresh week of data (this hits both APIs a lot, expect 15-30+ min)
python -m backtest.collect_historical_data

# calibration + hypothesis test against backtest_results.csv
python -m backtest.calibration

# simulate the trading book
python -m backtest.trading_book
```

Run everything with `-m` from the project root, not as bare scripts — the modules import across `data/`, `models/`, and `backtest/`, so Python needs to see this as a package.

## The maths, briefly

A `KXBTCD` contract pays $1 if BTC finishes above the strike, $0 otherwise. Assuming lognormal returns, the fair probability is `N(d2)` where `d2` is the usual Black-Scholes term. Going backwards — given a real market price, what vol explains it — means inverting `N(·)` first (I used Acklam's rational approximation, since there's no closed form) to get `d2`, then solving a genuine quadratic in `σ`. Both directions are round-trip verified: forward → inverse → forward recovers the original input to 9+ decimal places, checked on every single row of the dataset via an assertion, not just once and trusted.

The vol gap test is a plain one-sample t-test, hand-rolled, using the same normal CDF as a large-sample stand-in for the Student's-t CDF (fine once n's in the hundreds).

## Known limitations

- **DVOL is the wrong horizon.** It's a 30-day constant-maturity index, standing in for contracts that expire in minutes. The better fix — nearest-expiry Deribit option IV — isn't feasible for backtesting, since Deribit's option chain is live-only with no historical equivalent.
- One asset, one series, one week. Solid within that scope, not something I'd generalise further without more data.
- The 4 checkpoints per hour aren't fully independent — they share an outcome. Ran a version with one checkpoint per hour as a sanity check and it pointed the same direction, but it's not the headline number.
- No trading fees modelled, just the bid-ask spread.

## What's next

Scanner/alerting layer is deliberately last on the list — wanted to prove there's actually something worth alerting on first, rather than build alerting infrastructure around a signal I hadn't validated. Given the trading book results, next real step is probably swapping DVOL for a proper short-horizon vol input before trying to extend this to more assets or longer windows.
