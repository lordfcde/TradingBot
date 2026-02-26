import pandas as pd
import numpy as np
import pandas_ta as ta


class TrinityLite:
    """
    Trinity Master v2.0 — Upgraded Engine with Wyckoff-Lite + Anti-Trap.

    Indicators:
        • EMA 20 / 50 / 144 / 233       (Trend)
        • CMF 20                          (Money Flow direction)
        • Chaikin Osc (3,10)             (Money Flow acceleration)
        • RSI 14                          (Price strength)
        • ADX 14 + DI+/DI-              (Trend strength & direction)
        • Supertrend (10,3)              (Trend direction filter)
        • MACD (12,26,9)                 (Momentum confirmation)
        • VSA: Vol Climax, Vol Dry, Shakeout (Volume analysis)

    NEW in v2.0:
        • Wyckoff-Lite: SOS/SOW detection (Spring, Upthrust, Breakout)
        • Pump & Dump detection           (RSI spike + Vol spike + spread)
        • Improved Shakeout logic          (Volume + spread + recovery)
        • Multi-timeframe trend helper     (EMA alignment check)
        • ATR for trailing stop suggestion
    """

    # ── Config ──────────────────────────────────────────────
    EMA_PERIODS   = [20, 50, 144, 233]
    CMF_LENGTH    = 20
    RSI_LENGTH    = 14
    ADX_LENGTH    = 14
    CHAIKIN_FAST  = 3
    CHAIKIN_SLOW  = 10
    VOL_AVG_LEN   = 20
    VOL_CLIMAX_K  = 1.5
    VOL_DRY_K     = 0.5
    SHAKEOUT_LOOK = 10
    SR_LOOKBACK   = 20
    ATR_LENGTH    = 14

    # Wyckoff-Lite Config
    WYCKOFF_CONSOL_LEN = 20   # Bars to define consolidation range
    WYCKOFF_BREAK_K    = 1.02  # 2% above resistance = breakout
    WYCKOFF_SPRING_K   = 0.98  # 2% below support = spring

    # Pump & Dump Config
    PD_RSI_THRESHOLD   = 80
    PD_PRICE_SPIKE_PCT = 5.0   # 5% price spike in recent bars
    PD_VOL_SPIKE_K     = 3.0   # Volume 3x average = suspicious

    def __init__(self):
        print("✅ TrinityLite v2.0 initialized (Wyckoff-Lite + Anti-Trap)")

    # ── Public API ──────────────────────────────────────────
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run the full TrinityLite v2.0 analysis on an OHLCV DataFrame.
        Includes ADX, Supertrend, Wyckoff-Lite, P&D detection, and ATR.
        """
        df = df.copy()

        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(c in df.columns for c in required):
            raise ValueError(f"Missing columns. Need {required}, got {df.columns.tolist()}")

        # ── 1. EMAs ─────────────────────────────────────────
        for p in self.EMA_PERIODS:
            df[f'ema_{p}'] = ta.ema(df['close'], length=p)

        # ── 2. Money Flow & Momentum ────────────────────────
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=self.CMF_LENGTH)
        df['chaikin'] = ta.adosc(df['high'], df['low'], df['close'], df['volume'], fast=self.CHAIKIN_FAST, slow=self.CHAIKIN_SLOW)
        df['rsi'] = ta.rsi(df['close'], length=self.RSI_LENGTH)

        # ADX (Returns ADX_14, DMP_14, DMN_14)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=self.ADX_LENGTH)
        if adx_df is not None:
            df = pd.concat([df, adx_df], axis=1)
            df['adx'] = df[f'ADX_{self.ADX_LENGTH}']
            df['dmp'] = df[f'DMP_{self.ADX_LENGTH}']
            df['dmn'] = df[f'DMN_{self.ADX_LENGTH}']

        # ── 2b. Supertrend ──────────────────────────────────
        try:
            st_df = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
            if st_df is not None and not st_df.empty:
                df = pd.concat([df, st_df], axis=1)
                for col in st_df.columns:
                    if col.startswith('SUPERTd_'):
                        df['supertrend_dir'] = st_df[col]
                    elif col.startswith('SUPERT_'):
                        df['supertrend'] = st_df[col]
        except Exception:
            pass

        # ── 2c. ATR (for trailing stop) ─────────────────────
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.ATR_LENGTH)

        # ── 3. VSA (Volume Spread Analysis) ─────────────────
        vol_sma = df['volume'].rolling(window=self.VOL_AVG_LEN).mean()
        vol_sma_safe = vol_sma.fillna(1)  # Safe version for comparisons
        df['vol_avg'] = vol_sma
        df['vol_climax'] = df['volume'] > (self.VOL_CLIMAX_K * vol_sma_safe)
        df['vol_dry']    = df['volume'] < (self.VOL_DRY_K * vol_sma_safe)
        # VSA Accumulation: moderate volume increase with bullish candle
        df['vol_accumulation'] = (
            (df['volume'] > vol_sma_safe * 1.2)
            & (df['volume'] <= vol_sma_safe * self.VOL_CLIMAX_K)
            & (df['close'] > df['open'])
        )

        # ── 3b. MACD ────────────────────────────────────────
        macd = ta.macd(df['close'])
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        # ── 4. Support / Resistance (Donchian) ──────────────
        df['support_zone'] = df['low'].rolling(window=self.SR_LOOKBACK).min()
        df['resistance_zone'] = df['high'].rolling(window=self.SR_LOOKBACK).max()

        # ── 4b. Improved Shakeout (VSA v2) ──────────────────
        # Shakeout = price dips below recent swing low BUT:
        #   - Closes above open (bullish candle)
        #   - Volume NOT extremely high (low vol = weak selling = trap for bears)
        #   - Close recovers above previous close
        prior_swing_low = df['low'].rolling(window=self.SHAKEOUT_LOOK).min().shift(1).fillna(0)
        spread = (df['high'] - df['low'])
        body = abs(df['close'] - df['open'])
        # Improved: require bullish close + weak volume + body > 40% of spread (strong recovery)
        df['shakeout'] = (
            (df['low'] < prior_swing_low)
            & (df['close'] > df['open'])
            & (df['volume'] < vol_sma_safe * 1.5)  # Not massive selling volume
            & (body > spread * 0.3)            # Body recovery (relaxed from 0.4)
            & (prior_swing_low > 0)
        )

        # ── 5. WYCKOFF-LITE DETECTION ───────────────────────
        # Consolidation range (20-bar range)
        consol_high = df['high'].rolling(window=self.WYCKOFF_CONSOL_LEN).max()
        consol_low  = df['low'].rolling(window=self.WYCKOFF_CONSOL_LEN).min()
        consol_range = consol_high - consol_low

        # Use fillna to prevent NaN comparison errors on early bars
        consol_high_s = consol_high.shift(1).fillna(0)
        consol_low_s  = consol_low.shift(1).fillna(0)
        cmf_safe = df['cmf'].fillna(0)

        # SOS (Sign of Strength): Breakout above consolidation resistance with volume
        df['wyckoff_sos'] = (
            (df['close'] > consol_high_s * self.WYCKOFF_BREAK_K) &  # Price breaks above range
            (df['close'] > df['open']) &                              # Bullish candle
            (df['volume'] > vol_sma_safe * 1.5) &                    # Above-average volume
            (cmf_safe > 0) &                                          # Money flowing in
            (consol_high_s > 0)                                       # Ensure data exists
        )

        # SOW (Sign of Weakness): Breakdown below consolidation support
        df['wyckoff_sow'] = (
            (df['close'] < consol_low_s * self.WYCKOFF_SPRING_K) &  # Price breaks below range
            (df['close'] < df['open']) &                              # Bearish candle
            (df['volume'] > vol_sma_safe * 1.5) &                    # High volume selling
            (cmf_safe < 0) &                                          # Money flowing out
            (consol_low_s > 0)
        )

        # Spring: False breakdown (dips below support then recovers = bullish)
        df['wyckoff_spring'] = (
            (df['low'] < consol_low_s) &                             # Wick below support
            (df['close'] > consol_low_s) &                           # But closes above support
            (df['close'] > df['open']) &                              # Bullish close
            (df['volume'] < vol_sma_safe) &                           # Low volume = weak selling
            (consol_low_s > 0)
        )

        # Upthrust: False breakout (spikes above resistance then fails = bearish)
        df['wyckoff_upthrust'] = (
            (df['high'] > consol_high_s) &                           # Wick above resistance
            (df['close'] < consol_high_s) &                          # But closes below resistance
            (df['close'] < df['open']) &                              # Bearish close
            (df['volume'] > vol_sma_safe * 1.5) &                    # High volume = distribution
            (consol_high_s > 0)
        )

        # ── 6. PUMP & DUMP DETECTION ────────────────────────
        # Price change over last 5 bars
        price_change_5 = ((df['close'] / df['close'].shift(5)) - 1) * 100
        price_change_5 = price_change_5.fillna(0)
        df['price_spike_5'] = price_change_5

        # P&D flag: RSI extreme + huge volume + big price spike
        rsi_safe = df['rsi'].fillna(0)
        vol_sma_safe = vol_sma.fillna(1)  # Avoid NaN comparison
        df['pump_dump_risk'] = (
            (rsi_safe > self.PD_RSI_THRESHOLD) &
            (df['volume'] > vol_sma_safe * self.PD_VOL_SPIKE_K) &
            (price_change_5 > self.PD_PRICE_SPIKE_PCT)
        )

        # Exhaustion top: RSI > 75 + volume climax + bearish divergence proxy
        # (price makes new high but RSI doesn't)
        rsi_prev_5_max = rsi_safe.rolling(window=5).max().shift(1).fillna(0)
        price_prev_5_max = df['high'].rolling(window=5).max().shift(1).fillna(0)
        df['exhaustion_top'] = (
            (rsi_safe > 75) &
            (df['high'] > price_prev_5_max) &  # New price high
            (rsi_safe < rsi_prev_5_max) &       # But RSI doesn't confirm = divergence
            (df['volume'] > vol_sma_safe * 1.5)
        )

        # ── 7. EMA ALIGNMENT (Multi-Timeframe Proxy) ───────
        # Perfect alignment: EMA20 > EMA50 > EMA144 > EMA233 (Strong uptrend)
        # Use fillna(0) to avoid NaN comparison errors on early bars
        e20 = df['ema_20'].fillna(0)
        e50 = df['ema_50'].fillna(0)
        e144 = df['ema_144'].fillna(0)
        e233 = df['ema_233'].fillna(0)
        df['ema_aligned_bull'] = (
            (e20 > e50) &
            (e50 > e144) &
            (e144 > e233) &
            (e233 > 0)  # Ensure all EMAs are computed (not zero)
        )
        df['ema_aligned_bear'] = (
            (e20 < e50) &
            (e50 < e144) &
            (e144 < e233) &
            (e233 > 0)
        )

        # ── 8. Trinity Master Signal Logic (v2.0) ──────────
        # Trend
        is_uptrend = (df['close'] > df['ema_50'].fillna(0))
        is_adx_strong = (df['adx'].fillna(0) > 25)
        is_bullish_adx = (df['dmp'].fillna(0) > df['dmn'].fillna(0))

        # 💎 DIAMOND: Strong Uptrend + Vol Climax + CMF + Anti-Trap
        sig_diamond = (
            is_uptrend & is_adx_strong & is_bullish_adx &
            (cmf_safe > 0) &
            (df['vol_climax'].fillna(False) | (df['volume'] > vol_sma_safe * 1.5)) &
            ~df['pump_dump_risk'].fillna(False) &
            ~df['exhaustion_top'].fillna(False)
        )

        # ✅ MÚC (Safe Buy): Uptrend + ADX > 20 + RSI Check
        sig_muc = (
            is_uptrend & (df['adx'].fillna(0) > 20) & is_bullish_adx &
            (rsi_safe > 50) & (rsi_safe < 70) &
            ~df['pump_dump_risk'].fillna(False)
        )

        # ⚠️ SỚM (Early/Risky): Oversold + Vol or Spring
        sig_som = (
            ((rsi_safe < 30) & (df['volume'] > vol_sma_safe) & (df['close'] > df['open'])) |
            df['wyckoff_spring'].fillna(False)
        )

        # 🚨 SELL: Breakdown or Extreme Overbought or SOW
        sig_sell = (
            ((df['close'] < df['ema_50'].fillna(0)) & (rsi_safe < 50)) |
            (rsi_safe > 80) |
            df['wyckoff_sow'].fillna(False) |
            df['wyckoff_upthrust'].fillna(False)
        )

        # Assign Signals (Priority: Diamond > Muc > Som > Sell)
        df['signal_type'] = np.where(sig_diamond, 'DIAMOND',
                            np.where(sig_muc, 'MUC',
                            np.where(sig_som, 'SOM',
                            np.where(sig_sell, 'SELL', 'NONE'))))

        return df

    # ── Convenience: latest-bar summary dict ────────────────
    def get_latest_summary(self, df: pd.DataFrame) -> dict | None:
        """
        Analyse `df` and return a summary dict for the most recent bar.
        v2.0: Includes Wyckoff, P&D, EMA alignment, ATR, trailing stop.
        """
        try:
            analyzed = self.analyze(df)
            if analyzed.empty:
                return None

            last = analyzed.iloc[-1]
            prev = analyzed.iloc[-2] if len(analyzed) > 1 else last

            # Helper
            def safe_float(val, default=0.0):
                try:
                    v = float(val)
                    return v if pd.notna(v) else default
                except: return default

            # 1. ADX Status (Dashboard)
            adx_val = last.get('adx', 0)
            dmp = last.get('dmp', 0)
            dmn = last.get('dmn', 0)

            if adx_val > 50:
                adx_status = "QUÁ NÓNG 🟠"
            elif adx_val > 25:
                if dmp > dmn: adx_status = "MẠNH TĂNG 🟢"
                else: adx_status = "MẠNH GIẢM 🔴"
            else:
                adx_status = "YẾU/SIDEWAY ⚪"

            # 2. Structure (S/R + Wyckoff)
            close = float(last['close'])
            sup = float(last.get('support_zone', 0))
            res = float(last.get('resistance_zone', 0))

            structure = "Bình thường"
            if bool(last.get('wyckoff_sos', False)):
                structure = "🟢 SOS (Tín hiệu Mạnh - Wyckoff)"
            elif bool(last.get('wyckoff_spring', False)):
                structure = "🟢 SPRING (Rũ bỏ - Wyckoff)"
            elif bool(last.get('wyckoff_sow', False)):
                structure = "🔴 SOW (Yếu - Wyckoff)"
            elif bool(last.get('wyckoff_upthrust', False)):
                structure = "🔴 UPTHRUST (Bẫy tăng - Wyckoff)"
            elif close <= sup * 1.02:
                structure = "Chạm Hỗ trợ (Hộp Xanh)"
            elif close >= res * 0.98:
                structure = "Chạm Kháng cự (Hộp Đỏ)"
            elif close > float(last.get('ema_50', 0)):
                structure = "Trên EMA50 (Tăng)"

            # 3. Signal
            sig_type = last.get('signal_type', 'NONE')
            signal_emoji = ""
            if sig_type == 'DIAMOND': signal_emoji = "💎 SUPER BUY"
            elif sig_type == 'MUC': signal_emoji = "✅ MÚC (An toàn)"
            elif sig_type == 'SOM': signal_emoji = "⚠️ SỚM (Rủi ro)"
            elif sig_type == 'SELL': signal_emoji = "🚨 BÁN"

            # 4. Wyckoff Phase (aggregate)
            wyckoff_phase = "NONE"
            if bool(last.get('wyckoff_sos', False)):
                wyckoff_phase = "SOS"
            elif bool(last.get('wyckoff_spring', False)):
                wyckoff_phase = "SPRING"
            elif bool(last.get('wyckoff_sow', False)):
                wyckoff_phase = "SOW"
            elif bool(last.get('wyckoff_upthrust', False)):
                wyckoff_phase = "UPTHRUST"

            # 5. Trailing Stop Suggestion (ATR-based)
            atr = safe_float(last.get('atr', 0))
            supertrend_val = safe_float(last.get('supertrend', 0))
            # Trailing stop = max(Supertrend, Close - 2*ATR)
            atr_stop = close - (2 * atr) if atr > 0 else 0
            trailing_stop = max(supertrend_val, atr_stop) if supertrend_val > 0 else atr_stop

            # 6. MACD Histogram
            macd_hist_col = [c for c in analyzed.columns if c.startswith('MACDh_')]
            macd_hist = safe_float(last.get(macd_hist_col[0], 0)) if macd_hist_col else 0
            prev_macd_hist = safe_float(prev.get(macd_hist_col[0], 0)) if macd_hist_col else 0

            # 7. Chaikin comparison
            chaikin_val = safe_float(last.get('chaikin', 0))
            prev_chaikin = safe_float(prev.get('chaikin', 0))

            # 8. EMA Alignment
            ema_aligned = "NONE"
            if bool(last.get('ema_aligned_bull', False)):
                ema_aligned = "BULL"
            elif bool(last.get('ema_aligned_bear', False)):
                ema_aligned = "BEAR"

            return {
                # Core Signals
                'signal': signal_emoji,
                'signal_code': sig_type,

                # ADX
                'adx': safe_float(adx_val),
                'adx_status': adx_status,
                'is_bullish': bool(dmp > dmn),

                # Structure & Wyckoff
                'structure': structure,
                'wyckoff_phase': wyckoff_phase,
                'support': sup,
                'resistance': res,

                # Momentum
                'rsi': safe_float(last.get('rsi', 0)),
                'cmf': safe_float(last.get('cmf', 0)),
                'chaikin': chaikin_val,
                'prev_chaikin': prev_chaikin,
                'macd_hist': macd_hist,
                'prev_macd_hist': prev_macd_hist,

                # Volume
                'vol_climax': bool(last.get('vol_climax', False)),
                'vol_dry': bool(last.get('vol_dry', False)),
                'vol_accumulation': bool(last.get('vol_accumulation', False)),
                'shakeout': bool(last.get('shakeout', False)),
                'close': close,
                'volume': safe_float(last.get('volume', 0)),
                'vol_avg': safe_float(last.get('vol_avg', 0)),

                # Trend
                'ema20': safe_float(last.get('ema_20', 0)),
                'ema50': safe_float(last.get('ema_50', 0)),
                'ema144': safe_float(last.get('ema_144', 0)),
                'ema233': safe_float(last.get('ema_233', 0)),
                'supertrend': supertrend_val,
                'supertrend_dir': safe_float(last.get('supertrend_dir', 1.0)),
                'ema_aligned': ema_aligned,
                'trend': "UPTREND" if close > safe_float(last.get('ema_50', 0)) else "DOWNTREND",

                # Anti-Trap
                'pump_dump_risk': bool(last.get('pump_dump_risk', False)),
                'exhaustion_top': bool(last.get('exhaustion_top', False)),

                # Risk Management
                'atr': atr,
                'trailing_stop': trailing_stop,
            }

        except Exception as e:
            print(f"❌ TrinityLite error: {e}")
            import traceback
            traceback.print_exc()
            return None


# ── Backward-compat alias (optional) ───────────────────────
TrinityIndicators = TrinityLite
