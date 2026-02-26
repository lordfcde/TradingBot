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
        self.timeframe = "15m"      # 15-minute candles for fast T+2.5 breakout detection
        self.lookback_days = 10     # ~450 bars of 15M data — more than enough for indicators
        print("✅ TrinityAnalyzer initialized (15M Breakout Mode for T+2.5)")

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
                'trend':      summary.get('trend', 'N/A'),
                'cmf':        summary.get('cmf', 0),
                'cmf_status': summary.get('cmf_status', 'N/A'),
                'chaikin':    summary.get('chaikin', 0),
                'rsi':        summary.get('rsi', 0),
                'trigger':    summary.get('trigger', 'N/A'),
                'close':      summary.get('close', 0),
                'ema50':      summary.get('ema50', 0),
                'ema144':     summary.get('ema144', 0),
                'ema233':     summary.get('ema233', 0),
                'vol_climax': summary.get('vol_climax', False),
                'shakeout':   summary.get('shakeout', False),
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

            # 5. Kill Switch 4: Volume Quality — Nổ khối lượng đột biến?
            # [USER REQUESTED DANGEROUS OVERRIDE]: Bỏ hoàn toàn ràng buộc khối lượng
            vol_avg = analysis.get('vol_avg', 1)
            vol_cur = shark_payload.get('total_vol', 0)
            rel_vol = vol_cur / vol_avg if vol_avg > 0 else 0

            # 5b. Kill Switch 5: Trend Confirmation (Anti-Trap)
            close = analysis.get('close', 0)
            ema20 = analysis.get('ema20', 0)
            supertrend_dir = analysis.get('supertrend_dir', 1.0)
            is_above_ema20 = close > ema20 if ema20 > 0 else True
            is_st_uptrend = supertrend_dir > 0
            if not is_above_ema20 and not is_st_uptrend:
                return {'approved': False, 'reason': f"Downtrend (Dưới EMA20 & ST Giảm)", 'message': None}

            # 6. APPROVAL CRITERIA
            rating = analysis.get('rating', '')
            is_buy = "MUA" in rating
            if not is_buy:
                return {'approved': False, 'reason': f"Rating Yếu ({rating})", 'message': None}

            # ── CONSTRUCT APPROVED MESSAGE ──────────────────────────────────
            from datetime import datetime, timedelta, timezone
            vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
            time_str = vn_now.strftime("%H:%M")
            h = vn_now.hour
            m = vn_now.minute
            hm = h * 100 + m  # e.g. 09:25 → 925

            # Golden Hour tier (C)
            if (915 <= hm <= 1030):
                session_badge = "🏆 PRIME (Sáng Vàng)"
                session_icon  = "🔥"
            elif (1400 <= hm <= 1430):
                session_badge = "🏆 PRIME (Chiều ATC)"
                session_icon  = "🔥"
            elif (1130 <= hm <= 1300):
                session_badge = "⚠️ GIỜ TRƯA (Ít tin cậy)"
                session_icon  = "🟡"
            else:
                session_badge = "🟢 PHIÊN THƯỜNG"
                session_icon  = "🟢"

            price      = shark_payload.get('price', 0)
            change     = shark_payload.get('change_pc', 0)
            order_val  = shark_payload.get('order_value', 0)
            val_b      = order_val / 1_000_000_000
            rel_vol    = vol_cur / vol_avg if vol_avg > 0 else 0
            is_strong  = any(w in rating.upper() for w in ['MẠNH', 'DIAMOND', 'NỔ'])
            change_icon = "📈" if change >= 0 else "📉"

            # ── Premium One-Block Alert ─────────────────────────────────────
            shock_line = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{session_icon} <b>BREAKOUT SIGNAL</b> • {session_badge}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>#{symbol}</b>   ⏰ <code>{time_str}</code>\n"
                f"💰 Lệnh cá mập: <b>{val_b:.1f} Tỷ</b>   {change_icon} <b>{change:+.2f}%</b>\n"
                f"📊 Vol nổ: <b>{rel_vol:.1f}x</b> so với TB 20 phiên\n"
                f"\n"
                f"🧠 <b>KỸ THUẬT (15M)</b>\n"
                f"• Trend: <b>{'TĂNG ✅' if is_st_uptrend else 'SIDEWAY'}</b>  |  ADX: <b>{adx:.0f}</b>\n"
                f"• RSI: <b>{rsi:.0f}</b>  |  CMF: <b>{analysis.get('cmf', 0):.2f}</b>\n"
                f"\n"
                f"🎯 Rating: <b>{rating}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            msg = shock_line

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
    def _fetch_data(self, symbol, timeframe='1D', lookback=None):
        """Fetch data from Vnstock (Helper) with dynamic timeframe"""
        from datetime import datetime, timedelta
        try:
            if not self.vnstock_service:
                return None

            end_date = datetime.now()
            # If lookback is provided use it, otherwise use 100 days
            days_to_lookback = lookback if lookback else 100
            start_date = end_date - timedelta(days=days_to_lookback)

            df = self.vnstock_service.get_history(
                    symbol=symbol,
                    start=start_date.strftime('%Y-%m-%d'),
                    end=end_date.strftime('%Y-%m-%d'),
                    interval=timeframe,
                    source='KBS'
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
