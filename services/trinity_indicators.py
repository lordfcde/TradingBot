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
    EMA_PERIODS   = [20, 50, 144, 233]
    CMF_LENGTH    = 20
    RSI_LENGTH    = 14
    ADX_LENGTH    = 14    # Added for Trend Strength
    CHAIKIN_FAST  = 3
    CHAIKIN_SLOW  = 10
    VOL_AVG_LEN   = 20
    VOL_CLIMAX_K  = 2.0   
    VOL_DRY_K     = 0.5   
    SHAKEOUT_LOOK = 10    
    SR_LOOKBACK   = 20    # Support/Resistance Lookback (Donchian)

    def __init__(self):
        print("✅ TrinityLite initialized (Trinity Master AI Mode)")

    # ── Public API ──────────────────────────────────────────
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run the full TrinityLite analysis on an OHLCV DataFrame.
        Now includes ADX and Support/Resistance logic.
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
             # Rename for clarity if needed, but pandas_ta uses ADX_14
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
         except Exception as e:
             pass
        # ── 3. VSA (Volume Spread Analysis) ─────────────────
        vol_sma = df['volume'].rolling(window=self.VOL_AVG_LEN).mean()
        df['vol_avg'] = vol_sma
        df['vol_climax'] = df['volume'] > (self.VOL_CLIMAX_K * vol_sma)
        df['vol_dry']    = df['volume'] < (self.VOL_DRY_K * vol_sma)

        # ── 3b. MACD ────────────────────────────────────────
        macd = ta.macd(df['close'])
        if macd is not None:
             df = pd.concat([df, macd], axis=1)

        # ── 4. Support / Resistance (Donchian / Order Block Proxy) ──
        # Simple Proxy: Rolling Min/Max
        df['support_zone'] = df['low'].rolling(window=self.SR_LOOKBACK).min()
        df['resistance_zone'] = df['high'].rolling(window=self.SR_LOOKBACK).max()
        
        # Shakeout
        prior_swing_low = df['low'].rolling(window=self.SHAKEOUT_LOOK).min().shift(1)
        df['shakeout'] = (
            (df['low'] < prior_swing_low)
            & (df['close'] > df['open'])
            & df['vol_dry']
        )

        # ── 5. Trinity Master Signal Logic ──────────────────
        # Define Conditions
        
        # Trend
        is_uptrend = (df['close'] > df['ema_50'])
        is_adx_strong = (df['adx'] > 25)
        is_bullish_adx = (df['dmp'] > df['dmn'])
        
        # Signals
        # 💎 SUPER BUY (Diamond): Strong Uptrend + Vol Climax + CMF Positive
        sig_diamond = (
            is_uptrend & is_adx_strong & is_bullish_adx &
            (df['cmf'] > 0) &
            (df['vol_climax'] | (df['volume'] > df['vol_avg'] * 1.5))
        )
        
        # MÚC (Safe Buy): Uptrend + ADX > 20 + RSI Check
        sig_muc = (
            is_uptrend & (df['adx'] > 20) & is_bullish_adx &
            (df['rsi'] > 50) & (df['rsi'] < 70)
        )
        
        # SỚM (Early/Risky): Oversold + Vol or Divergence proxy
        sig_som = (
            (df['rsi'] < 30) & (df['volume'] > df['vol_avg']) & 
            (df['close'] > df['open']) # Closing Green
        )
        
        # SELL: Breakdown or Extreme Overbought
        sig_sell = (
            (df['close'] < df['ema_50']) & (df['rsi'] < 50)
        ) | (df['rsi'] > 80)

        # Assign Signals (Priority: Diamond > Muc > Som)
        df['signal_type'] = np.where(sig_diamond, 'DIAMOND',
                            np.where(sig_muc, 'MUC',
                            np.where(sig_som, 'SOM', 
                            np.where(sig_sell, 'SELL', 'NONE'))))

        return df

    # ── Convenience: latest-bar summary dict ────────────────
    def get_latest_summary(self, df: pd.DataFrame) -> dict | None:
        """
        Analyse `df` and return a summary dict for the most recent bar.
        Only exposes Trinity Master AI fields.
        """
        try:
            analyzed = self.analyze(df)
            if analyzed.empty:
                return None

            last = analyzed.iloc[-1]
            prev = analyzed.iloc[-2] if len(analyzed) > 1 else last

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

            # 2. Structure (S/R)
            close = float(last['close'])
            sup = float(last.get('support_zone', 0))
            res = float(last.get('resistance_zone', 0))
            
            structure = "Bình thường"
            if close <= sup * 1.02:
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
            
            # Helper stuff
            def safe_float(val, default=0.0):
                try:
                    v = float(val)
                    return v if pd.notna(v) else default
                except: return default

            return {
                'signal': signal_emoji,
                'signal_code': sig_type, # For logic checks
                'adx': safe_float(adx_val),
                'adx_status': adx_status,
                'is_bullish': (dmp > dmn),
                'structure': structure,
                'support': sup,
                'resistance': res,
                'rsi': safe_float(last.get('rsi', 0)),
                'cmf': safe_float(last.get('cmf', 0)),
                'vol_climax': bool(last.get('vol_climax', False)),
                'close': close,
                'volume': safe_float(last.get('volume', 0)),
                'vol_avg': safe_float(last.get('vol_avg', 0)),
                'ema20': safe_float(last.get('ema_20', 0)),
                'supertrend': safe_float(last.get('supertrend', 0)),
                'supertrend_dir': safe_float(last.get('supertrend_dir', 1.0)),
                'trend': "UPTREND" if close > last.get('ema_50', 0) else "DOWNTREND"
            }

        except Exception as e:
            print(f"❌ TrinityLite error: {e}")
            import traceback
            traceback.print_exc()
            return None


# ── Backward-compat alias (optional) ───────────────────────
TrinityIndicators = TrinityLite
