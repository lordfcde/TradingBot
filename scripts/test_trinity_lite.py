"""
Test script for TrinityLite indicator engine.
Generates synthetic OHLCV data and validates the analyze() output.
"""
import pandas as pd
import numpy as np

# Ensure project root is importable
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.trinity_indicators import TrinityLite


def make_synthetic_ohlcv(n=250):
    """Generate n bars of realistic-ish OHLCV data."""
    np.random.seed(42)
    close = 25_000 + np.cumsum(np.random.randn(n) * 200)
    high  = close + np.abs(np.random.randn(n) * 300)
    low   = close - np.abs(np.random.randn(n) * 300)
    opn   = close + np.random.randn(n) * 100
    vol   = np.random.randint(100_000, 5_000_000, size=n).astype(float)

    df = pd.DataFrame({
        'open': opn,
        'high': high,
        'low': low,
        'close': close,
        'volume': vol,
    })
    return df


def test_analyze():
    print("=" * 60)
    print("TEST 1: TrinityLite.analyze() — column validation")
    print("=" * 60)

    engine = TrinityLite()
    df = make_synthetic_ohlcv()

    result = engine.analyze(df)

    expected_cols = [
        'ema_50', 'ema_144', 'ema_233',
        'cmf', 'chaikin', 'rsi',
        'vol_climax', 'vol_dry', 'shakeout',
        'signal_buy', 'trigger_type',
    ]

    missing = [c for c in expected_cols if c not in result.columns]
    if missing:
        print(f"❌ FAIL — Missing columns: {missing}")
        return False
    else:
        print(f"✅ PASS — All {len(expected_cols)} expected columns present")

    # signal_buy should be boolean
    assert result['signal_buy'].dtype == bool, "signal_buy should be bool"
    print(f"✅ PASS — signal_buy dtype is bool")

    # Print last 5 rows summary
    cols_show = ['close', 'ema_50', 'cmf', 'chaikin', 'rsi', 'vol_climax', 'shakeout', 'signal_buy']
    print(f"\nLast 5 rows:\n{result[cols_show].tail()}")

    buy_count = result['signal_buy'].sum()
    print(f"\n📊 Total signal_buy = True bars: {buy_count} / {len(result)}")

    return True


def test_get_latest_summary():
    print("\n" + "=" * 60)
    print("TEST 2: TrinityLite.get_latest_summary()")
    print("=" * 60)

    engine = TrinityLite()
    df = make_synthetic_ohlcv()

    summary = engine.get_latest_summary(df)

    if summary is None:
        print("❌ FAIL — summary is None")
        return False

    required_keys = ['signal', 'cmf', 'chaikin', 'rsi', 'trend', 'cmf_status', 'trigger']
    missing = [k for k in required_keys if k not in summary]
    if missing:
        print(f"❌ FAIL — Missing keys: {missing}")
        return False

    print(f"✅ PASS — Summary dict has all required keys")
    for k, v in summary.items():
        print(f"  {k:15s}: {v}")

    return True


if __name__ == '__main__':
    ok1 = test_analyze()
    ok2 = test_get_latest_summary()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("🎉 ALL TESTS PASSED")
    else:
        print("💥 SOME TESTS FAILED")
    print("=" * 60)
