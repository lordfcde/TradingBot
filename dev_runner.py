import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RestartHandler(FileSystemEventHandler):
    def __init__(self, command):
        self.command = command
        self.process = None
        self.start_process()

    def start_process(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        
        print(f"🚀 Starting bot: {' '.join(self.command)}")
        self.process = subprocess.Popen(self.command)

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print(f"\n🔄 File changed: {event.src_path}")
            print("To stop the runner, press Ctrl+C")
            self.start_process()

if __name__ == "__main__":
    # Command to run the bot
    command = [sys.executable, "main.py"]
    
    event_handler = RestartHandler(command)
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=False)
    observer.start()

    print("👀 Watching for file changes... (Press Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        if event_handler.process:
            event_handler.process.terminate()
    observer.join()
