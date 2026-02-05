#!/bin/bash

# Bot Manager Script
BOT_DIR="/Users/vinhh/Documents/Bot"
VENV_PATH="$BOT_DIR/.venv"
MAIN_SCRIPT="main.py"
LOG_FILE="$BOT_DIR/bot.log"
PID_FILE="$BOT_DIR/bot.pid"

start() {
    echo "🚀 Starting bot..."
    cd "$BOT_DIR"
    
    # Check if already running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  Bot is already running (PID: $PID)"
            return 1
        fi
    fi
    
    # Activate venv and start bot
    source "$VENV_PATH/bin/activate"
    nohup python3 "$MAIN_SCRIPT" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    
    echo "✅ Bot started successfully (PID: $!)"
    echo "📝 Log file: $LOG_FILE"
}

stop() {
    echo "🛑 Stopping bot..."
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID
            rm "$PID_FILE"
            echo "✅ Bot stopped (PID: $PID)"
        else
            echo "⚠️  Bot is not running"
            rm "$PID_FILE"
        fi
    else
        # Fallback: kill by process name
        pkill -f "python3 $MAIN_SCRIPT"
        echo "✅ Bot stopped (fallback method)"
    fi
}

restart() {
    echo "🔄 Restarting bot..."
    stop
    sleep 2
    start
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "✅ Bot is running (PID: $PID)"
            echo "📊 Memory usage:"
            ps -p $PID -o pid,vsz,rss,comm
            return 0
        fi
    fi
    
    echo "❌ Bot is not running"
    return 1
}

logs() {
    echo "📝 Showing bot logs (Ctrl+C to exit)..."
    tail -f "$LOG_FILE"
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "🤖 Bot Manager"
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the bot"
        echo "  stop    - Stop the bot"
        echo "  restart - Restart the bot"
        echo "  status  - Check bot status"
        echo "  logs    - View bot logs (real-time)"
        exit 1
        ;;
esac

exit 0
