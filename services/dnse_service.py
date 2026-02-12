import os
import json
import ssl
import time
import threading
import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

class DNSEService:
    def __init__(self):
        # Load environment variables from MaterialsDnse/.env
        # Load environment variables from MaterialsDnse/.env (Relative to this file: ../MaterialsDnse/.env)
        # __file__ is inside services/, so we go up one level
        project_root = os.path.dirname(os.path.dirname(__file__))
        env_path = os.path.join(project_root, 'MaterialsDnse', '.env')
        # print(f"🔹 DEBUG: Loading env from {env_path}")
        load_dotenv(env_path)
        
        self.username = os.getenv("usernameEntrade")
        self.password = os.getenv("password")
        self.token = None
        self.investor_id = None
        
        self.broker_host = "datafeed-lts-krx.dnse.com.vn"
        self.broker_port = 443
        self.client = None
        
        # Callback storage: symbol -> function
        self.callbacks = {}
        
        # New: Generic Stream Handlers (for Shark Hunter)
        self.ohlc_global_handler = None
        self.tick_global_handler = None
        
        self.is_shark_active = False
        
        # MQTT Stability: Track active subscriptions for auto-restore
        self.active_subscriptions = set()
        
        # Connect immediately
        # self.connect() # Removed auto-connect in init to control explicitly or keep?
        # Keeping it compatible with existing code usage
        self.connect()

    def authenticate(self):
        # ... (Same)
        try:
             # Shortened for brevity in thought, keeping actual logic same
            print(f"🔹 DEBUG: Username loaded: {self.username is not None}")
            print(f"🔹 DEBUG: Password loaded: {self.password is not None}")

            url = "https://api.dnse.com.vn/user-service/api/auth"
            payload = {"username": self.username, "password": self.password}
            
            # print(f"🔹 DEBUG: Sending Auth Request to {url}...")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            self.token = response.json().get("token")
            print("✅ Auth Successful! Token received.")
            
            # Get Investor ID
            url_me = "https://api.dnse.com.vn/user-service/api/me"
            headers = {"authorization": f"Bearer {self.token}"}
            # print("🔹 DEBUG: Getting Investor ID...")
            res_me = requests.get(url_me, headers=headers)
            res_me.raise_for_status()
            self.investor_id = str(res_me.json()["investorId"])
            print(f"✅ Investor ID: {self.investor_id}")
            return True
        except Exception as e:
            print(f"❌ AUTH ERROR: {e}")
            if hasattr(e, 'response') and e.response is not None:
                 print(f"❌ Server Response: {e.response.text}")
            return False

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("✅ Connected to DNSE MQTT Broker!")
            # Auto-Subscribe to Shark Stream if active
            if self.is_shark_active:
                self.subscribe_all_markets()
                
            # Re-subscribe specific callbacks
            for symbol in self.callbacks:
                if len(symbol) == 3: # Stock
                    topic = f"plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/{symbol}"
                    client.subscribe(topic, qos=1)
                elif "INDEX" in symbol:
                    topic = f"plaintext/quotes/krx/mdds/index/{symbol}"
                    client.subscribe(topic, qos=1)
        else:
            print(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            # 1. Stream Dispatch (Priority for Shark Hunter)
            if "ohlc/stock/1D" in topic and self.ohlc_global_handler:
                self.ohlc_global_handler(payload)

            # Route Stock Info messages (original  configuration)
            if "stockinfo/v1/roundlot" in topic and self.tick_global_handler:
                self.tick_global_handler(payload)
            
            # 2. Specific Callbacks (Legacy routes)
            routing_key = payload.get("symbol") or payload.get("indexName") or payload.get("id") or payload.get("indexId")
            
            if routing_key:
                routing_key = routing_key.upper()
                if routing_key in self.callbacks:
                    self.callbacks[routing_key](payload)
                
        except Exception as e:
            # print(f"Message Error: {e}")
            pass

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        """Handle MQTT disconnection with auto-reconnect"""
        print(f"⚠️ MQTT Disconnected: {reason_code}")
        if reason_code != 0:
            print("🔄 Unexpected disconnect. Attempting reconnect in 5s...")
            try:
                time.sleep(5)
                self.connect()
                self._restore_subscriptions()
            except Exception as e:
                print(f"❌ Reconnect failed: {e}")


    def connect(self):
        print("🔹 DEBUG: Attempting to connect to DNSE...")
        if not self.authenticate():
            print("❌ connect() aborted due to Auth failure.")
            return False
            
        try:
            client_id = f"dnse-bot-{int(time.time())}"
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id,
                protocol=mqtt.MQTTv5,
                transport="websockets"
            )
            
            self.client.username_pw_set(self.investor_id, self.token)
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
            self.client.ws_set_options(path="/wss")
            
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect
            
            # Increased keepalive from 60 to 300 seconds for better stability
            self.client.connect(self.broker_host, self.broker_port, keepalive=300)
            self.client.loop_start()
            print("✅ MQTT Loop started.")
            return True
        except Exception as e:
            print(f"❌ MQTT Client Init Error: {e}")
            return False

    def get_realtime_price(self, symbol, callback):
        if not self.client or not self.client.is_connected():
            print("Client disconnected. Reconnecting...")
            if not self.connect():
                print("❌ Could not reconnect in get_realtime_price")
                return

        symbol = symbol.upper()
        self.callbacks[symbol] = callback
        topic = f"plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/{symbol}"
        if self.client:
            self.client.subscribe(topic, qos=1)
            print(f"🔹 Subscribed to: {topic}")

    def get_market_index(self, index_id, callback):
        if not self.client or not self.client.is_connected():
            if not self.connect():
                return
        index_id = index_id.upper()
        self.callbacks[index_id] = callback
        topic = f"plaintext/quotes/krx/mdds/index/{index_id}"
        if self.client:
            self.client.subscribe(topic, qos=1)

    def get_multiple_indices(self, indices, callback):
        if not self.client or not self.client.is_connected():
            print("🔹 Connecting for indices...")
            if not self.connect():
                print("❌ Connection failed in get_multiple_indices")
                return

        for idx in indices:
            idx = idx.upper()
            self.callbacks[idx] = callback
            topic = f"plaintext/quotes/krx/mdds/index/{idx}"
            if self.client:
                self.client.subscribe(topic, qos=1)

    def register_shark_streams(self, ohlc_cb, tick_cb):
        self.ohlc_global_handler = ohlc_cb
        self.tick_global_handler = tick_cb
        self.is_shark_active = True
        print("🦈 Shark Hunter Streams Registered.")
        # Try subscribing immediately if connected
        if self.client and self.client.is_connected():
             self.subscribe_all_markets()

    def subscribe_all_markets(self):
        """Subscribe to Stock Info topic for shark detection."""
        if not self.client:
            print("⚠️ Cannot subscribe: MQTT client not initialized")
            return
            
        # Subscribe to Stock Info Topic (original configuration)
        topic_stock = "plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/+"
        self.client.subscribe(topic_stock, qos=0)
        self.active_subscriptions.add(topic_stock)
        
        # DEBUG: Explicitly subscribe to FOX for user test
        topic_fox = "plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/FOX"
        self.client.subscribe(topic_fox, qos=0)
        self.active_subscriptions.add(topic_fox)
        print(f"🦈 Subscribed to Stock Info topic (original config).")

    def _restore_subscriptions(self):
        """Re-subscribe to all topics after reconnection"""
        if not self.active_subscriptions:
            print("   No subscriptions to restore.")
            return
            
        print(f"🔄 Restoring {len(self.active_subscriptions)} subscriptions...")
        for topic in self.active_subscriptions:
            self.client.subscribe(topic, qos=1)
            print(f"   ✅ Re-subscribed: {topic}")
