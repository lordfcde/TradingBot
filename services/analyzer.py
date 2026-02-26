"""
TrinityAnalyzer v2.0 — Hybrid Shark + Technical Analysis Module.

When Shark Hunter detects a large order (>1.5B VND), this analyzer
runs TrinityLite v2.0 on 15M data to produce a BUY / WATCH rating.

v2.0 Upgrades:
  • Fixed ADX > 50 "overheated" dead code bug
  • Wyckoff-Lite scoring (SOS/SOW/Spring/Upthrust)
  • Pump & Dump Kill Switch
  • Proper field propagation (ema20, supertrend_dir, etc.)
  • Trailing stop suggestion in alerts
  • EMA alignment scoring
  • Improved scoring weights
"""

from datetime import datetime, timedelta
from services.trinity_indicators import TrinityLite


class TrinityAnalyzer:
    """
    Lightweight technical analyzer triggered by Shark orders.
    Fetches 15M candles via vnstock, runs TrinityLite v2.0, returns a rating.
    """

    def __init__(self, vnstock_service=None):
        self.vnstock_service = vnstock_service
        self.engine = TrinityLite()
        self.timeframe = "15m"
        self.lookback_days = 10
        print("✅ TrinityAnalyzer v2.0 initialized (Wyckoff + Anti-Trap)")

    # ── Public API ──────────────────────────────────────────
    def check_signal(self, symbol: str, timeframe: str = '1H') -> dict:
        """
        Fetch data and run TrinityLite v2.0 analysis.

        Returns dict with full indicator data + rating.
        """
        try:
            df = self._fetch_data(symbol, timeframe=timeframe)

            if df is None or len(df) < 50:
                print(f"⚠️ TrinityAnalyzer: Not enough data for {symbol}")
                return self._fallback_result(symbol, error="No Tech Data (insufficient bars)")

            summary = self.engine.get_latest_summary(df)

            if summary is None:
                return self._fallback_result(symbol, error="No Tech Data (calc error)")

            # ── Extract all values from v2.0 summary ──────────
            rsi        = summary.get('rsi', 0)
            vol        = summary.get('volume', 0)
            vol_avg    = summary.get('vol_avg', 0)
            cmf        = summary.get('cmf', 0)
            close      = summary.get('close', 0)
            ema50      = summary.get('ema50', 0)
            chaikin    = summary.get('chaikin', 0)
            prev_chaikin = summary.get('prev_chaikin', 0)
            macd_hist  = summary.get('macd_hist', 0)

            # ADX Fields
            adx        = summary.get('adx', 0)
            adx_status = summary.get('adx_status', '')
            is_bullish_adx = summary.get('is_bullish', False)

            # Wyckoff Fields (NEW v2.0)
            wyckoff_phase = summary.get('wyckoff_phase', 'NONE')
            pump_dump     = summary.get('pump_dump_risk', False)
            exhaustion    = summary.get('exhaustion_top', False)
            ema_aligned   = summary.get('ema_aligned', 'NONE')

            # Supertrend & EMA20
            supertrend_dir = summary.get('supertrend_dir', 1.0)
            ema20          = summary.get('ema20', 0)

            # ── SCORING SYSTEM (v2.0: max ~18 pts) ────────────
            score = 0
            reasons = []

            # 1. RSI Logic (Breakout Focus)
            if rsi > 70:
                if vol > vol_avg and not pump_dump and not exhaustion:
                    score += 3
                    reasons.append("RSI>70 + Vol (Breakout legit) ✅ (+3)")
                elif pump_dump:
                    score -= 4
                    reasons.append("RSI>70 + P&D Risk ⛔ (-4)")
                elif exhaustion:
                    score -= 3
                    reasons.append("RSI>70 + Divergence (Đỉnh cạn) ⚠️ (-3)")
                else:
                    score -= 3
                    reasons.append("RSI>70 + Low Vol (Trap) ⚠️ (-3)")
            elif 50 <= rsi <= 70:
                score += 2
                reasons.append("RSI 50-70 (Tốt) ✅ (+2)")

            # 2. Trend Criteria
            if close > ema50:
                score += 2
                reasons.append("Giá > EMA50 ✅ (+2)")

            if cmf > 0:
                score += 2
                reasons.append("CMF > 0 ✅ (+2)")

            # Chaikin (UPGRADED: +2 if climax, +1 normally)
            if chaikin > prev_chaikin:
                if summary.get('vol_climax', False):
                    score += 2
                    reasons.append("Chaikin Tăng + Vol Climax ✅ (+2)")
                else:
                    score += 1
                    reasons.append("Chaikin Tăng ✅ (+1)")

            if macd_hist > 0:
                score += 2
                reasons.append("MACD Hist > 0 ✅ (+2)")

            # 3. ADX Logic (FIXED: separate > 50 check BEFORE > 25)
            if adx > 50:
                # Overheated market — strong trend but risky
                if is_bullish_adx:
                    score += 1  # Only +1 (reduced from +2) because overheated
                    reasons.append(f"ADX Quá Nóng ({adx:.0f}) + Tăng ⚠️ (+1)")
                else:
                    score -= 5
                    reasons.append(f"ADX Quá Nóng ({adx:.0f}) + Giảm ⛔ (-5)")
            elif adx > 25:
                if is_bullish_adx:
                    score += 2
                    reasons.append(f"ADX Mạnh ({adx:.0f}) + Tăng ✅ (+2)")
                else:
                    score -= 5
                    reasons.append(f"ADX Mạnh ({adx:.0f}) + Giảm ⚠️ (-5)")

            # 4. Supertrend Direction (NEW in scoring)
            if supertrend_dir > 0:
                score += 1
                reasons.append("Supertrend Tăng ✅ (+1)")
            else:
                score -= 1
                reasons.append("Supertrend Giảm ⚠️ (-1)")

            # 5. EMA Alignment (NEW: multi-timeframe proxy)
            if ema_aligned == "BULL":
                score += 2
                reasons.append("EMA 20>50>144>233 (Sóng Tăng) ✅ (+2)")
            elif ema_aligned == "BEAR":
                score -= 2
                reasons.append("EMA Xếp Giảm ⚠️ (-2)")

            # 6. Wyckoff-Lite Scoring (NEW v2.0)
            if wyckoff_phase == "SOS":
                score += 3
                reasons.append("Wyckoff SOS (Tín hiệu Mạnh) 💎 (+3)")
            elif wyckoff_phase == "SPRING":
                score += 2
                reasons.append("Wyckoff SPRING (Rũ bỏ thành công) ✅ (+2)")
            elif wyckoff_phase == "SOW":
                score -= 3
                reasons.append("Wyckoff SOW (Tín hiệu Yếu) ⛔ (-3)")
            elif wyckoff_phase == "UPTHRUST":
                score -= 3
                reasons.append("Wyckoff UPTHRUST (Bẫy Tăng) ⛔ (-3)")

            # 7. Anti-Trap Penalties
            if pump_dump:
                score -= 3
                reasons.append("⛔ P&D Risk (RSI+Vol+Price Spike)")
            if exhaustion:
                score -= 2
                reasons.append("⚠️ Đỉnh Cạn (RSI Divergence)")

            # ── Rating Scale (Adjusted for v2.0 wider range) ──
            if score >= 10:
                rating = "MUA MẠNH 🚀"
            elif score >= 7:
                rating = "MUA THĂM DÒ 🟢"
            elif score >= 4:
                rating = "THEO DÕI 🟡"
            else:
                rating = "KHÔNG MUA ⛔"

            # FINAL GUARD: ADX Strong Downtrend → Force WATCH
            if adx > 25 and not is_bullish_adx:
                rating = "WATCH"
                reasons.append("⛔ BỎ QUA (ADX Báo Giảm Mạnh)")

            # FINAL GUARD 2: Pump & Dump → Force WATCH
            if pump_dump:
                rating = "WATCH"
                reasons.append("⛔ BỎ QUA (Nghi P&D)")

            return {
                'rating':         rating,
                'score':          score,
                'reasons':        reasons,
                'trend':          summary.get('trend', 'N/A'),
                'cmf':            cmf,
                'cmf_status':     summary.get('cmf_status', 'N/A'),
                'chaikin':        chaikin,
                'rsi':            rsi,
                'trigger':        summary.get('trigger', 'N/A'),
                'close':          close,
                'ema20':          ema20,
                'ema50':          ema50,
                'ema144':         summary.get('ema144', 0),
                'ema233':         summary.get('ema233', 0),
                'vol_climax':     summary.get('vol_climax', False),
                'vol_dry':        summary.get('vol_dry', False),
                'vol_accumulation': summary.get('vol_accumulation', False),
                'shakeout':       summary.get('shakeout', False),
                'macd_hist':      macd_hist,
                'signal':         summary.get('signal', ''),
                'signal_code':    summary.get('signal_code', ''),
                'signal_buy':     summary.get('signal', None) is not None,
                # Trinity Master Fields
                'adx':            adx,
                'adx_status':     adx_status,
                'is_bullish':     is_bullish_adx,
                'structure':      summary.get('structure', ''),
                'support':        summary.get('support', 0),
                'resistance':     summary.get('resistance', 0),
                'vol_avg':        vol_avg,
                # v2.0 New Fields
                'supertrend_dir': supertrend_dir,
                'supertrend':     summary.get('supertrend', 0),
                'wyckoff_phase':  wyckoff_phase,
                'pump_dump_risk': pump_dump,
                'exhaustion_top': exhaustion,
                'ema_aligned':    ema_aligned,
                'trailing_stop':  summary.get('trailing_stop', 0),
                'atr':            summary.get('atr', 0),
                'error':          None,
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
            df_index = self._fetch_data("VNINDEX", lookback=40)

            if df_index is None or len(df_index) < 20:
                print("⚠️ TrinityAnalyzer: VNINDEX data insufficient. Assuming SAFE (Risky!).")
                return {'status': 'SAFE', 'reason': 'No Data', 'trend': 'SIDEWAY', 'change_pts': 0.0}

            import pandas_ta as pta
            df_index['ma20'] = pta.sma(df_index['close'], length=20)

            last = df_index.iloc[-1]
            prev = df_index.iloc[-2]

            close = last['close']
            ma20 = last['ma20']
            change_pts = close - prev['close']

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

    # ── Trinity Breakout Judge Logic (v2.0) ──────────────────
    def judge_signal(self, symbol: str, shark_payload: dict) -> dict:
        """
        Master Judge v2.0 — with Wyckoff, P&D, and Trailing Stop.
        Returns:
            {
                'approved': bool,
                'reason': str,
                'message': str (ready-to-send Telegram msg),
                'analysis': dict
            }
        """
        try:
            # 1. Check Technicals (TrinityLite v2.0)
            analysis = self.check_signal(symbol)
            if not analysis or analysis.get('error'):
                return {'approved': False, 'reason': 'No Technical Data', 'message': None}

            # 2. Check Market Context (Kill Switch — VNINDEX)
            market = self.get_market_context()
            if market['status'] == 'DANGER':
                return {'approved': False, 'reason': f"MARKET DANGER ({market['reason']})", 'message': None}

            # 3. Kill Switch #1: ADX Weak (Sideway)
            adx = analysis.get('adx', 0)
            is_bullish = analysis.get('is_bullish', False)

            if adx < 20:
                return {'approved': False, 'reason': f"ADX Yếu ({adx:.1f} < 20) - Sideway", 'message': None}

            if adx > 25 and not is_bullish:
                return {'approved': False, 'reason': f"ADX Đỏ ({adx:.1f}) - Downtrend Mạnh", 'message': None}

            # 4. Kill Switch #2: RSI Extreme
            rsi = analysis.get('rsi', 0)
            if rsi > 75:
                return {'approved': False, 'reason': f"RSI Quá Mua ({rsi:.1f} > 75)", 'message': None}

            # 5. Kill Switch #3: Volume Quality
            vol_avg = analysis.get('vol_avg', 1)
            vol_cur = shark_payload.get('total_vol', 0)

            if vol_avg < 150000:
                return {'approved': False, 'reason': f"Thanh khoản thấp (MA20 Vol: {vol_avg:,.0f} < 150k)", 'message': None}

            rel_vol = vol_cur / vol_avg if vol_avg > 0 else 0
            if rel_vol < 1.5 and not analysis.get('vol_climax'):
                return {'approved': False, 'reason': f"Vol Chưa Đạt ({rel_vol:.1f}x < 1.5x)", 'message': None}

            # 6. Kill Switch #4: Trend Confirmation (FIXED: uses real fields now)
            close = analysis.get('close', 0)
            ema20 = analysis.get('ema20', 0)
            supertrend_dir = analysis.get('supertrend_dir', 1.0)
            is_above_ema20 = close > ema20 if ema20 > 0 else True
            is_st_uptrend = supertrend_dir > 0
            if not is_above_ema20 and not is_st_uptrend:
                return {'approved': False, 'reason': f"Downtrend (Dưới EMA20 & ST Giảm)", 'message': None}

            # 7. Kill Switch #5: PUMP & DUMP (NEW v2.0)
            if analysis.get('pump_dump_risk', False):
                return {'approved': False, 'reason': "⛔ Nghi Pump & Dump (RSI+Vol+Price Spike)", 'message': None}

            # 8. Kill Switch #6: Wyckoff SOW/Upthrust (NEW v2.0)
            wyckoff = analysis.get('wyckoff_phase', 'NONE')
            if wyckoff in ('SOW', 'UPTHRUST'):
                return {'approved': False, 'reason': f"⛔ Wyckoff {wyckoff} (Tín hiệu Yếu)", 'message': None}

            # 9. Kill Switch #7: Exhaustion Top (NEW v2.0)
            if analysis.get('exhaustion_top', False):
                return {'approved': False, 'reason': "⚠️ Đỉnh Cạn (RSI Divergence)", 'message': None}

            # 10. APPROVAL CRITERIA
            rating = analysis.get('rating', '')
            is_buy = "MUA" in rating
            if not is_buy:
                return {'approved': False, 'reason': f"Rating Yếu ({rating})", 'message': None}

            # ── CONSTRUCT APPROVED MESSAGE ──────────────────────
            from datetime import datetime, timedelta, timezone
            vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
            time_str = vn_now.strftime("%H:%M")
            h = vn_now.hour
            m = vn_now.minute
            hm = h * 100 + m

            # Golden Hour tier
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
            change_icon = "📈" if change >= 0 else "📉"
            score      = analysis.get('score', 0)

            # Wyckoff badge
            wyckoff_badge = ""
            if wyckoff == "SOS":
                wyckoff_badge = "💎 Wyckoff: SOS (Tín hiệu Mạnh)"
            elif wyckoff == "SPRING":
                wyckoff_badge = "🟢 Wyckoff: SPRING (Rũ bỏ thành công)"
            elif wyckoff != "NONE":
                wyckoff_badge = f"📊 Wyckoff: {wyckoff}"

            # EMA Alignment badge
            ema_badge = ""
            ema_al = analysis.get('ema_aligned', 'NONE')
            if ema_al == "BULL":
                ema_badge = "| EMA: 🟢 Sóng Tăng"

            # Trailing stop
            trailing_stop = analysis.get('trailing_stop', 0)
            atr = analysis.get('atr', 0)
            stop_line = ""
            if trailing_stop > 0:
                stop_pct = ((close - trailing_stop) / close) * 100 if close > 0 else 0
                stop_line = f"\n🛡️ Trailing Stop: <b>{trailing_stop:,.0f}</b> ({stop_pct:.1f}% dưới giá)"

            # Reasons summary (top 3)
            reasons = analysis.get('reasons', [])
            reason_lines = "\n".join([f"  • {r}" for r in reasons[:4]]) if reasons else ""

            # ── Premium v2.0 Alert ─────────────────────────────
            shock_line = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{session_icon} <b>BREAKOUT SIGNAL v2.0</b> • {session_badge}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>#{symbol}</b>   ⏰ <code>{time_str}</code>\n"
                f"💰 Lệnh cá mập: <b>{val_b:.1f} Tỷ</b>   {change_icon} <b>{change:+.2f}%</b>\n"
                f"📊 Vol nổ: <b>{rel_vol:.1f}x</b> so với TB 20 phiên\n"
                f"\n"
                f"🧠 <b>KỸ THUẬT (15M)</b>\n"
                f"• Trend: <b>{'TĂNG ✅' if is_st_uptrend else 'SIDEWAY'}</b>  |  ADX: <b>{adx:.0f}</b> {ema_badge}\n"
                f"• RSI: <b>{rsi:.0f}</b>  |  CMF: <b>{analysis.get('cmf', 0):.2f}</b>\n"
            )

            if wyckoff_badge:
                shock_line += f"• {wyckoff_badge}\n"

            shock_line += (
                f"\n"
                f"🎯 Rating: <b>{rating}</b> (Score: {score})\n"
            )

            if reason_lines:
                shock_line += f"\n📋 <b>Chi tiết:</b>\n{reason_lines}\n"

            shock_line += stop_line
            shock_line += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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
            'rating':         'WATCH',
            'score':          0,
            'reasons':        [],
            'trend':          'N/A',
            'cmf':            0.0,
            'cmf_status':     'N/A',
            'chaikin':        0.0,
            'rsi':            0.0,
            'trigger':        '',
            'close':          0.0,
            'ema20':          0.0,
            'ema50':          0.0,
            'ema144':         0.0,
            'ema233':         0.0,
            'vol_climax':     False,
            'shakeout':       False,
            'signal_buy':     False,
            'adx':            0.0,
            'adx_status':     '',
            'is_bullish':     False,
            'structure':      '',
            'support':        0.0,
            'resistance':     0.0,
            'vol_avg':        0.0,
            'supertrend_dir': 0.0,
            'supertrend':     0.0,
            'wyckoff_phase':  'NONE',
            'pump_dump_risk': False,
            'exhaustion_top': False,
            'ema_aligned':    'NONE',
            'trailing_stop':  0.0,
            'atr':            0.0,
            'error':          error,
        }
