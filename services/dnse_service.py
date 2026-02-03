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
        
        # Connect immediately
        self.connect()

    def authenticate(self):
        # ... (authentication logic remains same)
        try:
            print(f"🔹 DEBUG: Username loaded: {self.username is not None}")
            print(f"🔹 DEBUG: Password loaded: {self.password is not None}")

            url = "https://api.dnse.com.vn/user-service/api/auth"
            payload = {"username": self.username, "password": self.password}
            
            print(f"🔹 DEBUG: Sending Auth Request to {url}...")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            self.token = response.json().get("token")
            print("✅ Auth Successful! Token received.")
            
            # Get Investor ID
            url_me = "https://api.dnse.com.vn/user-service/api/me"
            headers = {"authorization": f"Bearer {self.token}"}
            print("🔹 DEBUG: Getting Investor ID...")
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
        else:
            print(f"❌ Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            # 1. Stream Dispatch (Priority for Shark Hunter)
            if "ohlc/stock/1D" in topic and self.ohlc_global_handler:
                self.ohlc_global_handler(payload)
                # Don't return, allow specific callbacks (if any) to also fire?
                # For now, continue.

            if "stockinfo/v1/roundlot" in topic and self.tick_global_handler:
                self.tick_global_handler(payload)
            
            # 2. Specific Callbacks (Legacy /stock command)
            # Identify Key: Stock uses 'symbol', Index uses 'indexName' or 'id'
            routing_key = payload.get("symbol")
            if not routing_key:
                routing_key = payload.get("indexName")
            if not routing_key:
                routing_key = payload.get("id")
            if not routing_key:
                routing_key = payload.get("indexId") # Fallback
            
            # Normalize
            if routing_key:
                routing_key = routing_key.upper()
            
            # Trigger callback if exists
            if routing_key and routing_key in self.callbacks:
                # print(f"🔹 Dispatching {routing_key}")
                self.callbacks[routing_key](payload)
                pass 
            elif "index" in topic:
                 # Debug: If index topic but no callback found?
                 # Extract index id from topic? topic: .../index/VNINDEX
                 try:
                     parts = topic.split('/')
                     idx_from_topic = parts[-1].upper()
                     if idx_from_topic in self.callbacks:
                         # print(f"🔹 topic-dispatch: {idx_from_topic}")
                         self.callbacks[idx_from_topic](payload)
                 except: pass 
                
        except Exception as e:
            print(f"Message Error: {e}")

    def connect(self):
        if not self.authenticate():
            return
            
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
        
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()

    def get_realtime_price(self, symbol, callback):
        """
        Subscribe to symbol and trigger callback when data arrives.
        """
        if not self.client or not self.client.is_connected():
            print("Client disconneted. Reconnecting...")
            self.connect()

        # Normalize symbol
        symbol = symbol.upper()
        
        # Register callback
        self.callbacks[symbol] = callback
        
        # Subscribe path
        # Updated based on User provided "Stock Info" topic
        topic = f"plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/{symbol}"
        
        self.client.subscribe(topic, qos=1)
        print(f"🔹 Subscribed to: {topic}")


    def get_market_index(self, index_id, callback):
        """
        Subscribe to Market Index data (VN-INDEX, VN30, etc.)
        Topic: plaintext/quotes/krx/mdds/index/{indexName}
        """
        if not self.client or not self.client.is_connected():
            print("Client disconneted. Reconnecting...")
            self.connect()

        # Normalize ID
        index_id = index_id.upper()
        
        # Register callback
        self.callbacks[index_id] = callback
        
        # Subscribe
        topic = f"plaintext/quotes/krx/mdds/index/{index_id}"
        self.client.subscribe(topic, qos=1)

    def get_multiple_indices(self, indices, callback):
        """
        Subscribe to multiple indices at once.
        indices: list of strings ['VNINDEX', 'VN30', 'HNX']
        """
        if not self.client or not self.client.is_connected():
            self.connect()
            
        for idx in indices:
            idx = idx.upper()
            # Register same callback for all
            # Register same callback for all
            self.callbacks[idx] = callback
            
            # Subscribe
            topic = f"plaintext/quotes/krx/mdds/index/{idx}"
            self.client.subscribe(topic, qos=1)
            # print(f"🔹 Subscribed to Index: {topic}")

    def register_shark_streams(self, ohlc_cb, tick_cb):
        """
        Register global handlers for the Shark Hunter engine.
        """
        self.ohlc_global_handler = ohlc_cb
        self.tick_global_handler = tick_cb
        print("🦈 Shark Hunter Streams Registered.")

    def subscribe_all_markets(self):
        """
        FIREHOSE SUBSCRIPTION: Use with caution.
        Subscribes to ALL stocks OHLC and TICK data.
        """
        if not self.client or not self.client.is_connected():
            self.connect()
            
        # Topic 1: OHLC Daily wildcard
        # Assuming the topic format allows wildcard at the end
        # OHLC topic removed as per user request (Only 1-day realtime API)
        # topic_ohlc = "plaintext/quotes/krx/mdds/v2/ohlc/stock/1D/+"
        # self.client.subscribe(topic_ohlc, qos=0)
        
        # Topic 2: Real-time Stock Info wildcard
        # Using wildcard for symbol
        topic_tick = "plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/+"
        self.client.subscribe(topic_tick, qos=0)
        print(f"🦈 Subscribed to Real-time Stream: {topic_tick}")

