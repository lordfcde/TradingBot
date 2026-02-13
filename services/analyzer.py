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

    def __init__(self, vnstock_service=None):
        self.vnstock_service = vnstock_service
        self.engine = TrinityLite()
        self.timeframe = "1H"       # Hourly timeframe for T+2.5 strategy
        self.lookback_days = 30     # Need ~50 bars. 5 bars/day * 30 days = 150 bars. Safe.
        print("✅ TrinityAnalyzer initialized (1H hybrid mode)")

    # ── Public API ──────────────────────────────────────────
    def check_signal(self, symbol: str, timeframe: str = '1H') -> dict:
        """
        Fetch data and run TrinityLite analysis.

        Args:
            symbol (str): Stock symbol.
            timeframe (str): '1H' or '1D'.

        Returns
        -------
        dict with keys:
            rating      : 'BUY' | 'WATCH'
            trend       : str   e.g. 'UPTREND ✅'
            ...
        """
        try:
            df = self._fetch_data(symbol, timeframe=timeframe)

            if df is None or len(df) < 50:
                print(f"⚠️ TrinityAnalyzer: Not enough data for {symbol}")
                return self._fallback_result(symbol, error="No Tech Data (insufficient bars)")

            summary = self.engine.get_latest_summary(df)

            if summary is None:
                return self._fallback_result(symbol, error="No Tech Data (calc error)")

            # ── Rating Logic ────────────────────────────────
            # ── Rating Logic (Updated for Breakout/T+2.5) ──
            
            # Extract values
            rsi = summary.get('rsi', 0)
            vol = summary.get('volume', 0)
            vol_avg = summary.get('vol_avg', 0)
            cmf = summary.get('cmf', 0)
            close = summary.get('close', 0)
            ema50 = summary.get('ema50', 0)
            chaikin = summary.get('chaikin', 0)
            prev_chaikin = summary.get('prev_chaikin', 0)
            macd_hist = summary.get('macd_hist', 0)
            
            # ADX Fields (New)
            adx = summary.get('adx', 0)
            adx_status = summary.get('adx_status', '')
            is_bullish_adx = summary.get('is_bullish', False)

            score = 0
            reasons = []

            # 1. RSI Logic (Breakout Focus)
            if rsi > 70:
                if vol > vol_avg:
                    score += 3
                    reasons.append("RSI>70 + Vol (Breakout) ✅ (+3)")
                else:
                    score -= 3
                    reasons.append("RSI>70 + Low Vol (Trap) ⚠️ (-3)")
            elif 50 <= rsi <= 70:
                score += 2
                reasons.append("RSI 50-70 (Tốt) ✅ (+2)")

            # 2. Other Criteria
            if close > ema50:
                score += 2
                reasons.append("Giá > EMA50 ✅ (+2)")
            
            if cmf > 0:
                score += 2
                reasons.append("CMF > 0 ✅ (+2)")

            if chaikin > prev_chaikin:
                score += 1
                reasons.append("Chaikin Tăng ✅ (+1)")

            if macd_hist > 0:
                score += 2
                reasons.append("MACD Hist > 0 ✅ (+2)")
                
            # 3. ADX Logic (Trinity Master)
            if adx > 25:
                if is_bullish_adx:
                    score += 2
                    reasons.append(f"ADX Mạnh ({adx:.0f}) + Tăng ✅ (+2)")
                else:
                    score -= 5 # Heavy penalty for Strong Downtrend
                    reasons.append(f"ADX Mạnh ({adx:.0f}) + Giảm ⚠️ (-5)")
            elif adx > 50:
                 # Overheated?
                 reasons.append(f"ADX Quá Nóng ({adx:.0f}) ⚠️")

            # 4. Rating Scale
            if score >= 8:
                rating = "MUA MẠNH 🚀"
            elif score >= 6:
                rating = "MUA THĂM DÒ 🟢"
            else:
                rating = "THEO DÕI 🟡"
            
            # FINAL GUARD: If ADX indicates Strong Downtrend, Force WATCH
            if adx > 25 and not is_bullish_adx:
                rating = "WATCH"
                reasons.append("⛔ BỎ QUA (ADX Báo Giảm Mạnh)")

            return {
                'rating':     rating,
                'score':      score,
                'reasons':    reasons,
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
                # Trinity Master Fields
                'adx':        adx,
                'adx_status': adx_status,
                'is_bullish': is_bullish_adx,
                'structure':  summary.get('structure', ''),
                'support':    summary.get('support', 0),
                'resistance': summary.get('resistance', 0),
                'vol_avg':    vol_avg,
                'error':      None,
            }

        except Exception as e:
            print(f"❌ TrinityAnalyzer.check_signal error for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_result(symbol, error="No Tech Data")

    # ── Market Context (Kill Switch 2 & 4) ──────────────────
    def get_market_context(self) -> dict:
        """
        Check VN-INDEX health.
        Returns:
            dict: {
                'status': 'SAFE' | 'DANGER',
                'reason': str,
                'trend': 'UP' | 'DOWN' | 'SIDEWAY',
                'change_pts': float
            }
        """
        try:
            # Fetch VNINDEX history (30 days) to calc MA20
            # Symbol for VNINDEX often "VNINDEX" or "VNIndex" depending on source
            df_index = self._fetch_data("VNINDEX", lookback=40) 
            
            if df_index is None or len(df_index) < 20:
                print("⚠️ TrinityAnalyzer: VNINDEX data insufficient. Assuming SAFE (Risky!).")
                return {'status': 'SAFE', 'reason': 'No Data', 'trend': 'SIDEWAY', 'change_pts': 0.0}
            
            # Calc MA20
            import pandas_ta as ta
            df_index['ma20'] = ta.sma(df_index['close'], length=20)
            
            last = df_index.iloc[-1]
            prev = df_index.iloc[-2]
            
            close = last['close']
            ma20 = last['ma20']
            change_pts = close - prev['close']
            
            # Rule 1: Index < MA20 (Downtrend Warning)
            # Rule 2: Index Drop > 10 pts (Panic Selling)
            
            status = 'SAFE'
            reason = 'Market OK'
            trend = 'SIDEWAY'
            
            if close > ma20:
                trend = 'UP'
            else:
                trend = 'DOWN'
            
            is_ma20_broken = close < ma20
            is_panic_drop = change_pts < -10.0
            
            if is_panic_drop:
                status = 'DANGER'
                reason = f"VNINDEX Sập {change_pts:.1f} điểm"
            elif is_ma20_broken:
                # If broken but not panic, maybe just warning. 
                # User said: "Gãy MA20 -> Loại"
                status = 'DANGER'
                reason = f"VNINDEX Gãy MA20 ({close:.1f} < {ma20:.1f})"
                
            return {
                'status': status,
                'reason': reason,
                'trend': trend,
                'change_pts': change_pts,
                'current': close,
                'ma20': ma20
            }

        except Exception as e:
            print(f"❌ Market Context Error: {e}")
            return {'status': 'SAFE', 'reason': 'Error checking Index', 'trend': 'SIDEWAY', 'change_pts': 0.0}

    # ── Trinity Breakout Judge Logic ────────────────────────
    def judge_signal(self, symbol: str, shark_payload: dict) -> dict:
        """
        Master Judge function.
        Returns:
            {
                'approved': bool,
                'reason': str,
                'message': str (ready-to-send Telegram msg),
                'analysis': dict
            }
        """
        try:
            # 1. Check Technicals (TrinityLite)
            analysis = self.check_signal(symbol)
            if not analysis or analysis.get('error'):
                return {'approved': False, 'reason': 'No Technical Data', 'message': None}

            # 2. Check Market Context (Kill Switch #2)
            market = self.get_market_context()
            if market['status'] == 'DANGER':
                return {'approved': False, 'reason': f"MARKET DANGER ({market['reason']})", 'message': None}

            # 3. Kill Switch #1: Trend & ADX
            adx = analysis.get('adx', 0)
            is_bullish = analysis.get('is_bullish', False)
            
            if adx < 20:
                return {'approved': False, 'reason': f"ADX Yếu ({adx:.1f} < 20) - Sideway", 'message': None}
            
            if adx > 25 and not is_bullish:
                return {'approved': False, 'reason': f"ADX Đỏ ({adx:.1f}) - Downtrend Mạnh", 'message': None}

            # 4. Kill Switch #3: Room (RSI Limit)
            rsi = analysis.get('rsi', 0)
            if rsi > 75:
                 return {'approved': False, 'reason': f"RSI Quá Mua ({rsi:.1f} > 75)", 'message': None}

            # 5. Kill Switch #4: Volume Quality
            # Expected Vol = Current Vol / Avg Vol * (Time Ratio? No, just raw ratio > 1.0)
            vol_avg = analysis.get('vol_avg', 1)
            vol_cur = shark_payload.get('total_vol', 0)
            # If current vol < avg vol (at end of day), it might be weak. 
            # But during day, we check if it's "Active".
            # User Rule: "If Volume dự kiến < 1.0 (Yếu hơn trung bình): Loại."
            # We approximate this: If vol_cur < 50% of avg during session, warn.
            # But let's stick to TrinityLite's 'vol_dry'.
            
            # Better check:
            vol_ratio = vol_cur / vol_avg if vol_avg > 0 else 0
            # If ratio is too low (e.g. < 0.5), it means very low liquidity today?
            # Or user means "Volume Prediction". 
            # Simple Proxy: Check if 'vol_dry' is True -> REJECT
            if analysis.get('vol_dry'):
                 return {'approved': False, 'reason': "Volume Cạn Kiệt (Dry)", 'message': None}

            # 6. APPROVAL CRITERIA (Breakout)
            # Must have BUY rating OR specific Trigger
            rating = analysis.get('rating', '')
            is_buy = "MUA" in rating
            
            if not is_buy:
                 return {'approved': False, 'reason': f"Rating Weak ({rating})", 'message': None}


            # ── CONSTRUCT APPROVED MESSAGE ──────────────────
            from datetime import datetime, timedelta, timezone
            vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
            time_str = vn_now.strftime("%H:%M:%S")
            
            price = shark_payload.get('price', 0)
            change = shark_payload.get('change_pc', 0)
            change_icon = "📈" if change >= 0 else "📉"
            
            # Format
            msg = (
                f"🚀 **PHÁT HIỆN ĐIỂM NỔ: #{symbol}**\n"
                f"⏰ {time_str}\n\n"
                f"✅ **LÝ DO KÍCH HOẠT:**\n"
                f"• Giá: `{price:,.0f}` ({change:+.2f}%)\n"
                f"• Vol: Đột biến `{vol_ratio:.1f}x` trung bình.\n"
                f"• Trend: ADX `{adx:.1f}` ({'MẠNH TĂNG 🔥' if is_bullish else 'YẾU 🟡'})\n\n"
                f"🛡️ **CHECK T+2.5:**\n"
                f"• VN-INDEX: {market['status']} ({market['current']:.1f})\n"
                f"• Dư địa: RSI `{rsi:.1f}` (An toàn)\n\n"
                f"👉 **KHUYẾN NGHỊ:**\n"
                f"**{rating}**"
            )

            return {
                'approved': True,
                'reason': 'Passed All Checks',
                'message': msg,
                'analysis': analysis
            }

        except Exception as e:
            print(f"❌ Judge Error: {e}")
            import traceback
            traceback.print_exc()
            return {'approved': False, 'reason': 'Judge Exception', 'message': None}
    def _fetch_data(self, symbol: str, lookback: int = None):
        """Fetch OHLCV via vnstock."""
        lookback_days = lookback if lookback else self.lookback_days
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)


            # Use Shared Service if available (Optimization)
            if self.vnstock_service:
                df = self.vnstock_service.get_history(
                    symbol=symbol,
                    start=start_date.strftime('%Y-%m-%d'),
                    end=end_date.strftime('%Y-%m-%d'),
                    interval='15m',
                    source='KBS'
                )
            else:
                # Fallback (Slow, for testing isolation)
                from vnstock import Vnstock
                stock = Vnstock().stock(symbol=symbol, source='KBS')
                df = stock.quote.history(
                    symbol=symbol,
                    start=start_date.strftime('%Y-%m-%d'),
                    end=end_date.strftime('%Y-%m-%d'),
                    interval='15m'
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
