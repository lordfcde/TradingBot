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
        
        # Connect immediately
        self.connect()

    def authenticate(self):
        try:
            print(f"🔹 DEBUG: Username loaded: {self.username is not None}")
            print(f"🔹 DEBUG: Password loaded: {self.password is not None}")

            url = "https://api.dnse.com.vn/user-service/api/auth"
            payload = {"username": self.username, "password": self.password}
            
            print(f"🔹 DEBUG: Sending Auth Request to {url}...")
            response = requests.post(url, json=payload)
            # print(f"🔹 DEBUG: Auth Response Code: {response.status_code}")
            
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
            payload = json.loads(msg.payload.decode())
            
            # Identify Key: Stock uses 'symbol', Index uses 'indexName' or 'id'
            routing_key = payload.get("symbol")
            if not routing_key:
                routing_key = payload.get("indexName")
            if not routing_key:
                routing_key = payload.get("id")
            
            # Normalize
            if routing_key:
                routing_key = routing_key.upper()
            
            # Trigger callback if exists
            if routing_key and routing_key in self.callbacks:
                self.callbacks[routing_key](payload)
                # Cleanup callback after receiving one message (unless we want stream)
                # For this bot flow (Request -> Reply), deleting is fine to avoid stale callbacks.
                # BUT for multiple indices, 3 callbacks might share same name? No, dict keys are unique.
                # If we subscribe to multiple, we register routing_key for each.
                # del self.callbacks[routing_key] # Keep for stream or delete? 
                # Better to keep it if we want stream, but here we used One-Shot event in handler.
                # If we delete, subsequent updates won't be processed, which is fine for "Get Price".
                pass 
                
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
            self.callbacks[idx] = callback
            topic = f"plaintext/quotes/krx/mdds/index/{idx}"
            self.client.subscribe(topic, qos=1)
            # print(f"🔹 Subscribed to Index: {idx}")

