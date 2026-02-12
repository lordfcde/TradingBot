"""
Manual cache clearing script
Run this to immediately clear all alert caches and stop spam
"""
import json
import os

def clear_all_caches():
    print("🧹 Clearing all alert caches...")
    
    # Clear shark stats file
    stats_file = "shark_stats.json"
    if os.path.exists(stats_file):
        try:
            with open(stats_file, 'r') as f:
                data = json.load(f)
            
            # Keep structure but clear alert history
            if 'alert_history' in data:
                data['alert_history'] = {}
            if 'stats' in data:
                data['stats'] = {}
            
            with open(stats_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"✅ Cleared {stats_file}")
        except Exception as e:
            print(f"⚠️ Error clearing {stats_file}: {e}")
    
    # Clear watchlist (keep structure but reset timestamps)
    watchlist_file = "watchlist.json"
    if os.path.exists(watchlist_file):
        try:
            # Backup first
            with open(watchlist_file, 'r') as f:
                data = json.load(f)
            
            with open('watchlist_backup.json', 'w') as f:
                json.dump(data, f, indent=2)
            
            # Clear watchlist
            with open(watchlist_file, 'w') as f:
                json.dump({}, f)
            
            print(f"✅ Cleared {watchlist_file} (backup saved)")
        except Exception as e:
            print(f"⚠️ Error clearing {watchlist_file}: {e}")
    
    print("\n🎯 Cache cleared! Bot will resume with fresh state.")
    print("💡 Restart bot to apply: ./bot.sh restart")

if __name__ == "__main__":
    clear_all_caches()
