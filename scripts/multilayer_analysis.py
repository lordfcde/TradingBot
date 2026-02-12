"""
Multi-Layer Stock Analysis Tool
Combines Real-time data + Trinity Technical Analysis for watchlist evaluation
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.analyzer import TrinityAnalyzer
from services.vnstock_service import VnstockService
from datetime import datetime

def analyze_stock_multilayer(symbol):
    """
    Perform multi-layer analysis: Real-time + Trinity
    Returns comprehensive report for watchlist decision
    """
    print("=" * 70)
    print(f"🔍 PHÂN TÍCH ĐA TẦNG: {symbol}")
    print("=" * 70)
    
    # Layer 1: Real-time Data
    print("\n📊 LAYER 1: DỮ LIỆU REAL-TIME")
    print("-" * 70)
    
    vnstock = VnstockService()
    realtime = vnstock.get_stock_info(symbol)
    
    if not realtime:
        print("❌ Không lấy được dữ liệu real-time")
        return None
    
    price = realtime['matchPrice']
    change_pc = realtime['changedRatio']
    volume = realtime['totalVolumeTraded']
    avg_vol_5d = realtime.get('avg_vol_5d', 0)
    
    print(f"   Giá hiện tại:    {price:,.0f} VNĐ ({change_pc:+.2f}%)")
    print(f"   Khối lượng:      {volume:,.0f} cp")
    print(f"   KL TB 5 ngày:    {avg_vol_5d:,.0f} cp")
    
    vol_ratio = (volume / avg_vol_5d * 100) if avg_vol_5d > 0 else 0
    print(f"   Tỷ lệ KL:        {vol_ratio:.0f}% so với TB")
    
    # Layer 2: Trinity Technical Analysis (15m)
    print("\n🧠 LAYER 2: TRINITY ANALYSIS (15M)")
    print("-" * 70)
    
    analyzer = TrinityAnalyzer()
    trinity = analyzer.check_signal(symbol)
    
    if trinity['error']:
        print(f"   ⚠️ Lỗi kỹ thuật: {trinity['error']}")
        rating = "UNKNOWN"
    else:
        print(f"   Trend:           {trinity['trend']}")
        print(f"   RSI (14):        {trinity['rsi']:.1f}")
        print(f"   CMF (20):        {trinity['cmf']:.3f} ({trinity['cmf_status']})")
        print(f"   Chaikin Osc:     {trinity['chaikin']:+,.0f}")
        print(f"   EMA50:           {trinity['ema50']:.2f}")
        print(f"   Close:           {trinity['close']:.2f}")
        if trinity['trigger']:
            print(f"   Trigger:         {trinity['trigger']}")
        
        rating = trinity['rating']
    
    # Decision Logic
    print("\n🎯 KẾT LUẬN VÀ GỢI Ý")
    print("-" * 70)
    
    # Scoring system
    score = 0
    reasons = []
    
    # Real-time signals
    if change_pc > 2:
        score += 2
        reasons.append("✅ Tăng giá mạnh >2%")
    elif change_pc > 0:
        score += 1
        reasons.append("✅ Tăng giá nhẹ")
    elif change_pc < -2:
        score -= 1
        reasons.append("⚠️ Giảm giá >2%")
    
    if vol_ratio > 150:
        score += 2
        reasons.append("✅ Khối lượng đột biến (>150% TB)")
    elif vol_ratio > 100:
        score += 1
        reasons.append("✅ Khối lượng tăng")
    elif vol_ratio < 50:
        score -= 1
        reasons.append("⚠️ Khối lượng thấp")
    
    # Trinity signals
    if rating == "BUY":
        score += 3
        reasons.append("✅ Trinity Rating: BUY")
    elif rating == "WATCH":
        score += 1
        reasons.append("⚪ Trinity Rating: WATCH")
    
    if not trinity['error']:
        if trinity['rsi'] > 70:
            score -= 1
            reasons.append("⚠️ RSI quá mua (>70)")
        elif trinity['rsi'] > 50:
            score += 1
            reasons.append("✅ RSI mạnh (>50)")
        
        if trinity['cmf'] > 0.1:
            score += 2
            reasons.append("✅ Dòng tiền vào mạnh")
        elif trinity['cmf'] > 0:
            score += 1
            reasons.append("✅ Dòng tiền vào nhẹ")
        elif trinity['cmf'] < -0.1:
            score -= 1
            reasons.append("⚠️ Dòng tiền ra mạnh")
    
    # Final recommendation
    print("\n   📋 Điểm số:")
    for r in reasons:
        print(f"      {r}")
    
    print(f"\n   🔢 Tổng điểm: {score}/10")
    
    if score >= 6:
        recommendation = "🟢 THÊM VÀO WATCHLIST - Tín hiệu mạnh"
    elif score >= 3:
        recommendation = "🟡 THEO DÕI - Tín hiệu trung bình"
    else:
        recommendation = "🔴 BỎ QUA - Tín hiệu yếu"
    
    print(f"\n   💡 Gợi ý: {recommendation}")
    
    print("\n" + "=" * 70)
    
    return {
        'symbol': symbol,
        'price': price,
        'change_pc': change_pc,
        'volume': volume,
        'trinity': trinity,
        'score': score,
        'recommendation': recommendation
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Multi-layer stock analysis')
    parser.add_argument('symbol', nargs='?', default='HPG', help='Stock symbol (default: HPG)')
    args = parser.parse_args()
    
    analyze_stock_multilayer(args.symbol.upper())
