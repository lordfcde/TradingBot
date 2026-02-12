"""
TrinityAnalyzer — Hybrid Shark + Technical Analysis Module.

When Shark Hunter detects a large order (>1B VND), this analyzer
runs TrinityLite on 1H (Hourly) data to produce a BUY / WATCH rating.

Designed for low-latency, fault-tolerant operation:
  • Uses pandas_ta (vectorized, no for-loops)
  • Full try-except: vnstock failure → rating='WATCH' + error='No Tech Data'
"""

from datetime import datetime, timedelta
from services.trinity_indicators import TrinityLite


class TrinityAnalyzer:
    """
    Lightweight technical analyzer triggered by Shark orders.
    Fetches 1H candles via vnstock, runs TrinityLite, returns a rating.
    """

    def __init__(self):
        self.engine = TrinityLite()
        self.timeframe = "1H"       # Hourly timeframe for T+2.5 strategy
        self.lookback_days = 30     # Need ~50 bars. 5 bars/day * 30 days = 150 bars. Safe.
        print("✅ TrinityAnalyzer initialized (1H hybrid mode)")

    # ── Public API ──────────────────────────────────────────
    def check_signal(self, symbol: str) -> dict:
        """
        Fetch 1H data and run TrinityLite analysis.

        Returns
        -------
        dict with keys:
            rating      : 'BUY' | 'WATCH'
            trend       : str   e.g. 'UPTREND ✅'
            cmf         : float
            cmf_status  : str
            chaikin     : float
            rsi         : float
            trigger     : str   'SHAKEOUT' | 'VOL_CLIMAX' | ''
            close       : float
            ema50       : float
            error       : None | str  (set to 'No Tech Data' on failure)
        """
        try:
            df = self._fetch_data(symbol)

            if df is None or len(df) < 50:
                print(f"⚠️ TrinityAnalyzer: Not enough data for {symbol}")
                return self._fallback_result(symbol, error="No Tech Data (insufficient bars)")

            summary = self.engine.get_latest_summary(df)

            if summary is None:
                return self._fallback_result(symbol, error="No Tech Data (calc error)")

            # ── Rating Logic ────────────────────────────────
            trend_ok = summary['close'] > summary['ema50']       # Giá > EMA50
            flow_ok  = summary['cmf'] > 0                        # Dòng tiền dương
            rsi_ok   = summary['rsi'] > 50                       # Phe mua kiểm soát

            if trend_ok and flow_ok and rsi_ok:
                rating = "BUY"
            else:
                rating = "WATCH"

            return {
                'rating':     rating,
                'trend':      summary['trend'],
                'cmf':        summary['cmf'],
                'cmf_status': summary['cmf_status'],
                'chaikin':    summary['chaikin'],
                'rsi':        summary['rsi'],
                'trigger':    summary['trigger'],
                'close':      summary['close'],
                'ema50':      summary['ema50'],
                'ema144':     summary['ema144'],
                'ema233':     summary['ema233'],
                'vol_climax': summary['vol_climax'],
                'shakeout':   summary['shakeout'],
                'signal_buy': summary.get('signal', None) is not None,
                'error':      None,
            }

        except Exception as e:
            print(f"❌ TrinityAnalyzer.check_signal error for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_result(symbol, error="No Tech Data")

    # ── Internal ────────────────────────────────────────────
    def _fetch_data(self, symbol: str):
        """Fetch 15m OHLCV via vnstock."""
        try:
            from vnstock import Vnstock
            stock = Vnstock().stock(symbol=symbol, source='KBS')  # KBS has better 15m data quality

            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)

            df = stock.quote.history(
                symbol=symbol,
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                interval=self.timeframe,
            )

            if df is None or df.empty:
                return None

            # Normalize column names
            col_map = {}
            for col in df.columns:
                lower = col.lower()
                if lower in ('open', 'high', 'low', 'close', 'volume', 'time'):
                    col_map[col] = lower
            if col_map:
                df = df.rename(columns=col_map)

            return df

        except Exception as e:
            print(f"❌ TrinityAnalyzer._fetch_data error for {symbol}: {e}")
            return None

    @staticmethod
    def _fallback_result(symbol: str, error: str = "No Tech Data") -> dict:
        """Return a safe default when technical data is unavailable."""
        return {
            'rating':     'WATCH',
            'trend':      'N/A',
            'cmf':        0.0,
            'cmf_status': 'N/A',
            'chaikin':    0.0,
            'rsi':        0.0,
            'trigger':    '',
            'close':      0.0,
            'ema50':      0.0,
            'ema144':     0.0,
            'ema233':     0.0,
            'vol_climax': False,
            'shakeout':   False,
            'signal_buy': False,
            'error':      error,
        }
