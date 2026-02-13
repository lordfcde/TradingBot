import pandas as pd
import numpy as np
import pandas_ta as ta


class TrinityLite:
    """
    Trinity Fast & Furious — Low-latency money flow + momentum + VSA filter.
    
    Replaces the old TrinityIndicators (PineScript port) with a lean,
    vectorized engine optimised for real-time bot trading.
    
    Indicators kept:
        • EMA 50 / 144 / 233  (Trend)
        • CMF 20              (Money Flow direction)
        • Chaikin Osc (3,10)  (Money Flow acceleration)
        • RSI 14              (Price strength)
        • VSA: Vol Climax, Vol Dry, Shakeout
    
    All heavy logic (Order Block, FVG, Ichimoku, RS Rating) removed.
    """

    # ── Config ──────────────────────────────────────────────
    EMA_PERIODS   = [50, 144, 233]
    CMF_LENGTH    = 20
    RSI_LENGTH    = 14
    CHAIKIN_FAST  = 3
    CHAIKIN_SLOW  = 10
    VOL_AVG_LEN   = 20
    VOL_CLIMAX_K  = 2.0   # Volume > 2× avg → climax
    VOL_DRY_K     = 0.5   # Volume < 0.5× avg → dry
    SHAKEOUT_LOOK = 10    # Look-back for swing low

    def __init__(self):
        print("✅ TrinityLite initialized (Fast & Furious)")

    # ── Public API ──────────────────────────────────────────
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run the full TrinityLite analysis on an OHLCV DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain columns: open, high, low, close, volume

        Returns
        -------
        pd.DataFrame
            Original df with extra indicator + signal columns appended.
        """
        df = df.copy()

        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(c in df.columns for c in required):
            raise ValueError(f"Missing columns. Need {required}, got {df.columns.tolist()}")

        # ── 1. EMAs ─────────────────────────────────────────
        for p in self.EMA_PERIODS:
            df[f'ema_{p}'] = ta.ema(df['close'], length=p)

        # ── 2. Money Flow ───────────────────────────────────
        df['cmf'] = ta.cmf(
            df['high'], df['low'], df['close'], df['volume'],
            length=self.CMF_LENGTH,
        )
        df['chaikin'] = ta.adosc(
            df['high'], df['low'], df['close'], df['volume'],
            fast=self.CHAIKIN_FAST, slow=self.CHAIKIN_SLOW,
        )
        df['rsi'] = ta.rsi(df['close'], length=self.RSI_LENGTH)

        # ── 3. VSA (Volume Spread Analysis) ─────────────────
        vol_sma = df['volume'].rolling(window=self.VOL_AVG_LEN).mean()
        df['vol_avg'] = vol_sma  # Expose for analyzer

        df['vol_climax'] = df['volume'] > (self.VOL_CLIMAX_K * vol_sma)
        df['vol_dry']    = df['volume'] < (self.VOL_DRY_K * vol_sma)

        # ── 3b. MACD (Added for Breakout Strategy) ──────────
        # Returns: MACD_12_26_9, MACDh_12_26_9 (hist), MACDs_12_26_9 (signal)
        macd = ta.macd(df['close'])
        if macd is not None:
             df = pd.concat([df, macd], axis=1)

        # Shakeout: price dipped below prior 10-bar low, but closed green + low vol
        prior_swing_low = df['low'].rolling(window=self.SHAKEOUT_LOOK).min().shift(1)
        df['shakeout'] = (
            (df['low'] < prior_swing_low)
            & (df['close'] > df['open'])
            & df['vol_dry']
        )

        # ── 4. Signal Logic (vectorized) ────────────────────
        # Condition 1 — Money Flow positive & accelerating
        cond_flow = (df['cmf'] > 0) & (df['chaikin'] > df['chaikin'].shift(1))

        # Condition 2 — Trend + RSI
        cond_trend = (df['close'] > df['ema_50']) & (df['rsi'] > 50)

        # Condition 3 — Trigger (Shakeout OR bullish Vol Climax)
        bullish_climax = df['vol_climax'] & (df['close'] > df['open'])
        cond_trigger = df['shakeout'] | bullish_climax

        df['signal_buy'] = cond_flow & cond_trend & cond_trigger

        # Helper: trigger label for display
        df['trigger_type'] = np.where(
            df['shakeout'], 'SHAKEOUT',
            np.where(bullish_climax, 'VOL_CLIMAX', '')
        )

        return df

    # ── Convenience: latest-bar summary dict ────────────────
    def get_latest_summary(self, df: pd.DataFrame) -> dict | None:
        """
        Analyse `df` and return a summary dict for the most recent bar.
        Used by the monitor / stock handler for display.
        """
        try:
            analyzed = self.analyze(df)
            if analyzed.empty:
                return None

            last = analyzed.iloc[-1]
            prev = analyzed.iloc[-2] if len(analyzed) > 1 else last # For chaikin comparison

            cmf_val = last.get('cmf', 0)
            if pd.notna(cmf_val) and cmf_val > 0.1:
                cmf_status = "VÀO MẠNH 🔥"
            elif pd.notna(cmf_val) and cmf_val > 0:
                cmf_status = "VÀO NHẸ ✅"
            else:
                cmf_status = "RA NGOÀI ❌"

            close = float(last['close']) if pd.notna(last['close']) else 0.0
            ema50 = float(last.get('ema_50', 0)) if pd.notna(last.get('ema_50')) else 0.0
            ema233 = float(last.get('ema_233', 0)) if pd.notna(last.get('ema_233')) else 0.0

            if ema50 > 0 and close > ema50:
                trend = "UPTREND ✅"
            elif ema233 > 0 and close > ema233:
                trend = "SIDEWAY ⚪"
            else:
                trend = "DOWNTREND ❌"

            signal_name = None
            if last.get('signal_buy', False):
                signal_name = "MUA FAST ⚡"

            def safe_float(val, default=0.0):
                """Convert to float, replacing NaN/None with default."""
                try:
                    v = float(val)
                    return v if pd.notna(v) else default
                except (TypeError, ValueError):
                    return default

            # Attempt to get MACD Hist
            # pandas_ta default col: MACDh_12_26_9
            macd_hist = safe_float(last.get('MACDh_12_26_9', 0))
            
            return {
                'signal': signal_name,
                'cmf': safe_float(cmf_val),
                'chaikin': safe_float(last.get('chaikin', 0)),
                'prev_chaikin': safe_float(prev.get('chaikin', 0)), # Added for scoring
                'rsi': safe_float(last.get('rsi', 0)),
                'close': float(close),
                'ema50': float(ema50),
                'ema144': safe_float(last.get('ema_144', 0)),
                'ema233': float(ema233),
                'vol_climax': bool(last.get('vol_climax', False)),
                'vol_dry': bool(last.get('vol_dry', False)),
                'shakeout': bool(last.get('shakeout', False)),
                'trigger': last.get('trigger_type', ''),
                'trend': trend,
                'cmf_status': cmf_status,
                'volume': safe_float(last.get('volume', 0)),
                'vol_avg': safe_float(last.get('vol_avg', 0)), # Added
                'macd_hist': macd_hist, # Added
            }

        except Exception as e:
            print(f"❌ TrinityLite.get_latest_summary error: {e}")
            import traceback
            traceback.print_exc()
            return None


# ── Backward-compat alias (optional) ───────────────────────
TrinityIndicators = TrinityLite
