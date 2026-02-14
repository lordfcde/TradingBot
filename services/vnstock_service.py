import os
import pandas as pd
from vnstock import Trading, Vnstock
from datetime import datetime, timedelta

class VnstockService:
    def __init__(self):
        """Initialize vnstock service."""
        self.trading = Trading()
        self.stock_source = Vnstock()  # Initialize once to avoid reloading mappings
        print("✅ vnstock Service initialized")
    
    def get_stock_info(self, symbol):
        """
        Get real-time stock information for a given symbol using vnstock API.
        
        Args:
            symbol (str): Stock symbol (e.g., 'HPG', 'VCB')
            
        Returns:
            dict: Stock information or None if error
        """
        try:
            symbol = symbol.upper().strip()
            
            # Get stock price using vnstock Trading().price_board()
            price_data = self.trading.price_board(symbols_list=[symbol])
            
            if price_data is None or price_data.empty:
                print(f"⚠️ No data returned for {symbol}")
                return None
            
            # Extract data from DataFrame (first row)
            stock_data = price_data.iloc[0].to_dict()
            
            # Get industry/sector info
            industry = "N/A"
            avg_vol_5d = 0
            ma20_val = 0
            rsi_val = None
            
            try:
                # Use pre-initialized source
                stock_obj = self.stock_source.stock(symbol=symbol, source='VCI')
                
                # Try to get company profile for industry
                try:
                    profile = stock_obj.company.profile()
                    if profile is not None and not profile.empty:
                        industry = profile.iloc[0].get('industryName', 'N/A') if hasattr(profile.iloc[0], 'get') else 'N/A'
                        if industry == 'N/A' or not industry:
                            # Try alternative field names
                            industry = profile.iloc[0].get('industry', 'N/A') if hasattr(profile.iloc[0], 'get') else 'N/A'
                except Exception as e:
                    print(f"⚠️ Could not get industry for {symbol}: {e}")
                
                # Get 5-day avg volume from historical data
                try:
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=60)  # Get 60 days for RSI
                    
                    hist = stock_obj.quote.history(
                        symbol=symbol,
                        start=start_date.strftime('%Y-%m-%d'),
                        end=end_date.strftime('%Y-%m-%d'),
                        interval='1D'
                    )
                    
                    if hist is not None and not hist.empty and 'volume' in hist.columns:
                        avg_vol_5d = int(hist['volume'].tail(5).mean())
                        
                    # Calculate MA20 (Price) and MA20 (Volume) and RSI
                    ma20_val = 0
                    ma20_vol = 0
                    
                    if hist is not None and not hist.empty:
                        if 'close' in hist.columns and len(hist) > 20:
                             ma20_val = hist['close'].tail(20).mean()
                        
                        if 'volume' in hist.columns and len(hist) > 20:
                             ma20_vol = int(hist['volume'].tail(20).mean())
                        
                        if 'close' in hist.columns and len(hist) > 14:
                            rsi_val = self._calculate_rsi(hist['close'])
                except Exception as e:
                    print(f"⚠️ Could not get avg volume for {symbol}: {e}")
                    
            except Exception as e:
                print(f"⚠️ Extended data fetch warning for {symbol}: {e}")
            
            # Format response to match expected format
            return {
                'source': 'VNSTOCK',
                'symbol': symbol,
                'matchPrice': float(stock_data.get('close_price', 0)),
                'changedRatio': float(stock_data.get('percent_change', 0)),
                'referencePrice': float(stock_data.get('reference_price', 0)),
                'highestPrice': float(stock_data.get('high_price', 0)),
                'lowestPrice': float(stock_data.get('low_price', 0)),
                'avgPrice': float(stock_data.get('average_price', 0)),
                'totalVolumeTraded': int(stock_data.get('total_trades', 0)),
                'matchQuantity': 0,  # Not available in price_board
                'openPrice': float(stock_data.get('open_price', 0)),
                'ceilingPrice': float(stock_data.get('ceiling_price', 0)),
                'floorPrice': float(stock_data.get('floor_price', 0)),
                'time': stock_data.get('time', ''),
                'exchange': stock_data.get('exchange', ''),
                # Additional data for display
                'total_value': float(stock_data.get('total_value', 0)),
                'foreign_buy': int(stock_data.get('foreign_buy_volume', 0)),
                'foreign_sell': int(stock_data.get('foreign_sell_volume', 0)),
                'bid_price_1': float(stock_data.get('bid_price_1', 0)),
                'ask_price_1': float(stock_data.get('ask_price_1', 0)),
                # New fields
                'industry': industry,
                'industry': industry,
                'avg_vol_5d': avg_vol_5d,
                'ma20': ma20_val,
                'ma20_vol': ma20_vol,
                'rsi': rsi_val,
                'raw_data': stock_data  # Keep raw data for debugging
            }

        except Exception as e:
            print(f"❌ vnstock Error for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI using Wilder's smoothing method"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]  # Return latest RSI

    def get_history(self, symbol, start, end, interval='1D', source='VCI'):
        """
        Get historical data for a given symbol.
        
        Args:
            symbol (str): Stock symbol (e.g., 'HPG', 'VCB')
            start (str): Start date in 'YYYY-MM-DD' format
            end (str): End date in 'YYYY-MM-DD' format
            interval (str): Data interval (e.g., '1D', '1H', '1M')
            source (str): Data source (default: 'VCI')
            
        Returns:
            pd.DataFrame: Historical data or None if error
        """
        try:
            # Use pre-initialized source
            stock_obj = self.stock_source.stock(symbol=symbol, source=source)
            df = stock_obj.quote.history(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval
            )
            return df
        except Exception as e:
            print(f"❌ VnstockService.get_history error for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_intraday_stats(self, symbol):
        """
        Get Active Buy/Sell Stats from Intraday Data.
        Returns:
            {
                'buy_vol': int,
                'sell_vol': int,
                'buy_ratio': float, # 0.0 - 1.0
                'sell_ratio': float
            }
        """
        try:
            # Use pre-initialized source
            stock_obj = self.stock_source.stock(symbol=symbol, source='VCI')
            
            # Fetch intraday data (max 100 pages * 10 or just fetch enough)
            # Default page_size might be small. Let's try page_size=1000 if supported, 
            # or just default. vnstock document implies simple usage.
            # We want TODAY's data. 
            # Warning: This might be slow if we fetch too much.
            # Let's fetch page_size=100 to get "Reflect Short Term Sentiment"
            # User likely wants "Session Total".
            # Try fetching 500 records.
            df = stock_obj.quote.intraday(symbol=symbol, page_size=500)
            
            if df is None or df.empty:
                return None
                
            if 'match_type' not in df.columns:
                return None
                
            # Filter
            buy_df = df[df['match_type'].str.contains('Buy', case=False, na=False)]
            sell_df = df[df['match_type'].str.contains('Sell', case=False, na=False)]
            
            buy_vol = buy_df['volume'].sum() if not buy_df.empty else 0
            sell_vol = sell_df['volume'].sum() if not sell_df.empty else 0
            
            total = buy_vol + sell_vol
            
            return {
                'buy_vol': int(buy_vol),
                'sell_vol': int(sell_vol),
                'total_analyzed': int(total),
                'buy_ratio': buy_vol / total if total > 0 else 0,
                'sell_ratio': sell_vol / total if total > 0 else 0
            }
            
        except Exception as e:
            print(f"⚠️ Intraday Stats Error for {symbol}: {e}")
            return None
