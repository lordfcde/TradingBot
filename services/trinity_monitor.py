import time
import threading
from datetime import datetime, timedelta
from services.trinity_indicators import TrinityLite


class TrinitySignalMonitor:
    """
    Monitor stocks for Trinity Fast & Furious signals.
    Uses TrinityLite (pandas_ta) for low-latency indicator calculation.
    """

    def __init__(self, bot, vnstock_service, watchlist_service):
        """
        Initialize Trinity Signal Monitor

        Args:
            bot: Telegram bot instance
            vnstock_service: Vnstock service for historical data
            watchlist_service: Watchlist service for monitored symbols
        """
        self.bot = bot
        self.vnstock_service = vnstock_service
        self.watchlist_service = watchlist_service
        self.engine = TrinityLite()

        # Config
        self.timeframe = "30m"
        self.alert_cooldown = 1800   # 30 minutes
        self.check_interval = 300    # 5 minutes

        # State
        self.alert_history = {}      # {symbol: last_alert_time}
        self.chat_id = None
        self.is_monitoring = False
        self.monitor_thread = None

        print("✅ Trinity Signal Monitor initialized (Fast & Furious, 30m)")

    # ───────────────────────────────────────────────────────
    # PUBLIC: get_analysis  (used by stock_handler + shark_hunter)
    # ───────────────────────────────────────────────────────
    def get_analysis(self, symbol, timeframe=None):
        """
        Run TrinityLite analysis for a symbol and return a summary dict.

        Returns:
            dict with keys: signal, cmf, chaikin, rsi, trend, cmf_status,
                            trigger, vol_climax, shakeout, ema50, close …
            or None on error / insufficient data.
        """
        timeframe = timeframe or self.timeframe
        try:
            df = self._fetch_data(symbol, timeframe)
            if df is None or len(df) < 50:
                print(f"⚠️ Not enough data for {symbol} ({timeframe})")
                return None

            return self.engine.get_latest_summary(df)

        except Exception as e:
            print(f"❌ get_analysis error for {symbol}: {e}")
            return None

    # ───────────────────────────────────────────────────────
    # MONITORING LOOP
    # ───────────────────────────────────────────────────────
    def set_chat_id(self, chat_id):
        """Set Telegram chat ID for alerts"""
        self.chat_id = chat_id
        print(f"📱 Trinity alerts will be sent to chat: {chat_id}")

    def check_signal(self, symbol, timeframe='30m'):
        """
        Check for Trinity signals for a given symbol.
        Returns:
            dict: Signal details or None if no signal
        """
        analysis = self.get_analysis(symbol, timeframe)
        if analysis and analysis.get('signal'):
            analysis['symbol'] = symbol
            analysis['signal_type'] = analysis['signal']
            return analysis
        return None

    def check_symbol(self, symbol):
        """Check a single symbol for signals and send alert if found"""
        print(f"🔍 Checking {symbol} for Trinity signals...")

        # Cooldown check
        if symbol in self.alert_history:
            last_alert_time = self.alert_history[symbol]
            if time.time() - last_alert_time < self.alert_cooldown:
                remaining = self.alert_cooldown - (time.time() - last_alert_time)
                print(f"⏳ {symbol} cooldown: {remaining/60:.1f} min remaining")
                return

        try:
            signal_data = self.check_signal(symbol)

            if signal_data:
                print(f"🎯 SIGNAL DETECTED: {symbol} - {signal_data['signal_type']}")
                self.send_alert(signal_data)
            else:
                print(f"  ✓ {symbol} checked - no signal")

        except Exception as e:
            print(f"❌ Error checking {symbol}: {e}")
            import traceback
            traceback.print_exc()

    def check_cooldown(self, symbol):
        """Check if alert cooldown has passed"""
        if symbol not in self.alert_history:
            return True
        return (time.time() - self.alert_history[symbol]) >= self.alert_cooldown

    # ───────────────────────────────────────────────────────
    # ALERT FORMATTING
    # ───────────────────────────────────────────────────────
    def format_alert_message(self, signal_details):
        """Format Telegram alert message for TrinityLite signals."""
        symbol      = signal_details['symbol']
        signal_type = signal_details.get('signal_type', signal_details.get('signal', ''))
        cmf         = signal_details.get('cmf', 0)
        chaikin     = signal_details.get('chaikin', 0)
        rsi         = signal_details.get('rsi', 0)
        close       = signal_details.get('close', 0)
        trend       = signal_details.get('trend', 'N/A')
        cmf_status  = signal_details.get('cmf_status', '')
        trigger     = signal_details.get('trigger', '')

        # Trigger icon
        if trigger == 'SHAKEOUT':
            trigger_label = "🔄 RŨ BỎ thành công"
        elif trigger == 'VOL_CLIMAX':
            trigger_label = "💥 TIỀN VÀO ĐỘT BIẾN"
        else:
            trigger_label = "⚡ Trigger"

        # RSI status
        if rsi > 70:
            rsi_label = f"🔴 {rsi:.1f} QUÁ MUA"
        elif rsi > 50:
            rsi_label = f"🟢 {rsi:.1f} MẠNH"
        else:
            rsi_label = f"⚪ {rsi:.1f} YẾU"

        msg = (
            f"⚡ **TÍN HIỆU {signal_type} - {symbol} (30m)**\n\n"
            f"📊 **Dashboard:**\n"
            f"• Xu hướng: {trend}\n"
            f"• Dòng tiền: {cmf_status} (CMF: {cmf:.2f})\n"
            f"• Chaikin Osc: {chaikin:+,.0f}\n"
            f"• RSI(14): {rsi_label}\n"
            f"• Kích nổ: {trigger_label}\n\n"
            f"⏰ **Thời gian:** {datetime.now().strftime('%H:%M %d/%m/%Y')}\n"
            f"💰 **Giá:** {close:,.0f}\n\n"
            f"✅ **GỢI Ý:** {signal_type}"
        )
        return msg

    def send_alert(self, signal_details):
        """Send Telegram alert"""
        try:
            if not self.chat_id:
                print("⚠️ No chat ID set for Trinity alerts")
                return

            symbol = signal_details['symbol']

            if not self.check_cooldown(symbol):
                remaining = self.alert_cooldown - (time.time() - self.alert_history[symbol])
                print(f"⏳ {symbol} cooldown: {remaining/60:.1f} min remaining")
                return

            message = self.format_alert_message(signal_details)
            self.bot.send_message(self.chat_id, message, parse_mode='Markdown')

            self.alert_history[symbol] = time.time()
            print(f"📢 Trinity alert sent: {symbol} - {signal_details.get('signal_type')}")

        except Exception as e:
            print(f"❌ Error sending alert for {signal_details.get('symbol', '?')}: {e}")

    # ───────────────────────────────────────────────────────
    # MONITORING LIFECYCLE
    # ───────────────────────────────────────────────────────
    def monitor_loop(self):
        """Main monitoring loop"""
        print(f"🔄 Trinity monitor loop started (checking every {self.check_interval/60:.0f} min)")

        while self.is_monitoring:
            try:
                if not self._is_trading_hours():
                    print(f"💤 Market Closed. Trinity sleeping... (Time: {datetime.now().strftime('%H:%M')})")
                    time.sleep(300)
                    continue

                watchlist_items = self.watchlist_service.get_active_watchlist()

                if watchlist_items:
                    symbols = [item['symbol'] for item in watchlist_items]
                    print(f"\n📊 Trinity scan: {len(symbols)} symbols in watchlist")

                    for symbol in symbols:
                        if not self.is_monitoring:
                            break
                        self.check_symbol(symbol)
                        time.sleep(2)  # Rate limit
                else:
                    print("📭 Trinity: Watchlist is empty")

                print(f"⏸️ Trinity: Waiting {self.check_interval/60:.0f} min until next scan...")
                time.sleep(self.check_interval)

            except Exception as e:
                print(f"❌ Trinity monitor loop error: {e}")
                time.sleep(60)

    def start_monitoring(self, chat_id):
        """Start Trinity signal monitoring"""
        if self.is_monitoring:
            print("⚠️ Trinity monitor already running")
            return False

        self.set_chat_id(chat_id)
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        print("✅ Trinity Signal Monitor started")
        return True

    def stop_monitoring(self):
        """Stop Trinity signal monitoring"""
        if not self.is_monitoring:
            print("⚠️ Trinity monitor not running")
            return False

        self.is_monitoring = False
        print("🛑 Trinity Signal Monitor stopped")
        return True

    def send_test_alert(self, symbol="TEST"):
        """Send a fake Trinity alert for testing UI"""
        if not self.chat_id:
            print("⚠️ No Chat ID for test alert")
            return False

        print(f"🧪 Sending TEST Trinity alert for {symbol}...")

        fake_details = {
            'symbol': symbol,
            'signal_type': "MUA FAST ⚡ (TEST)",
            'signal': "MUA FAST ⚡ (TEST)",
            'cmf': 0.18,
            'chaikin': 125000,
            'rsi': 62.5,
            'close': 28500,
            'ema50': 27000,
            'ema144': 26000,
            'ema233': 25000,
            'trend': "UPTREND ✅",
            'cmf_status': "VÀO MẠNH 🔥",
            'trigger': "VOL_CLIMAX",
            'vol_climax': True,
            'vol_dry': False,
            'shakeout': False,
            'volume': 5000000,
        }

        self.send_alert(fake_details)
        return True

    # ───────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ───────────────────────────────────────────────────────
    def _fetch_data(self, symbol, timeframe='30m'):
        """Fetch OHLCV data for analysis."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)

            from vnstock import Vnstock
            stock = Vnstock().stock(symbol=symbol, source='VCI')

            df = stock.quote.history(
                symbol=symbol,
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                interval=timeframe,
            )

            if df is None or df.empty:
                return None

            # Normalize column names (vnstock may vary)
            col_map = {}
            for col in df.columns:
                lower = col.lower()
                if lower in ('open', 'high', 'low', 'close', 'volume', 'time'):
                    col_map[col] = lower
            if col_map:
                df = df.rename(columns=col_map)

            return df

        except Exception as e:
            print(f"❌ Error fetching data for {symbol}: {e}")
            return None

    def _is_trading_hours(self):
        """Check if current time is within 09:00 - 15:15"""
        now = datetime.now()
        current_hm = now.strftime("%H:%M")
        return "09:00" <= current_hm <= "15:15" and now.weekday() < 5
