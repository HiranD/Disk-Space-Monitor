"""
Disk Disk Space Monitor - Disk space monitoring with Discord alerts
A Windows system tray application that monitors disk space and sends alerts.
"""

import json
import queue
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import requests
from PIL import Image, ImageDraw
import pystray

# Try to import tkinter for on-screen alerts
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# Configuration file path (same directory as script)
CONFIG_PATH = Path(__file__).parent / "config.json"

# Default configuration
DEFAULT_CONFIG = {
    "drives": ["C:"],
    "threshold_gb": 50,
    "check_interval_minutes": 5,
    "alert_methods": {
        "discord": True,
        "onscreen": True
    },
    "discord_webhook_url": "",
    "alert_cooldown_hours": 0
}


class Config:
    """Manages loading and saving configuration."""

    def __init__(self):
        self.data = self.load()

    def load(self):
        """Load config from file or create default."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                # Merge with defaults for any missing keys
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
            except (json.JSONDecodeError, IOError):
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def save(self):
        """Save current config to file."""
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.data, f, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()


class TkManager:
    """Manages all tkinter windows in a thread-safe way."""

    def __init__(self):
        self.root = None
        self.settings_window = None
        self.alert_window = None
        self.command_queue = queue.Queue()
        self.running = True
        self.thread = None

    def start(self):
        """Start the tkinter thread."""
        self.thread = threading.Thread(target=self._run_tk, daemon=True)
        self.thread.start()

    def _run_tk(self):
        """Run tkinter mainloop in dedicated thread."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide root window
        self._process_queue()
        self.root.mainloop()

    def _process_queue(self):
        """Process commands from queue."""
        try:
            while True:
                cmd, args = self.command_queue.get_nowait()
                cmd(*args)
        except queue.Empty:
            pass
        if self.running:
            self.root.after(100, self._process_queue)

    def run_in_tk_thread(self, func, *args):
        """Schedule a function to run in the tkinter thread."""
        self.command_queue.put((func, args))

    def show_settings(self, config, on_save_callback):
        """Show settings window."""
        self.run_in_tk_thread(self._create_settings_window, config, on_save_callback)

    def _create_settings_window(self, config, on_save_callback):
        """Create settings window (runs in tk thread)."""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        # Reload config from file
        config.data = config.load()

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Disk Disk Space Monitor Settings")
        self.settings_window.geometry("450x500")
        self.settings_window.resizable(False, False)

        # Main frame with padding
        main_frame = ttk.Frame(self.settings_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Drives section
        ttk.Label(main_frame, text="Drives to Monitor:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        drives_var = tk.StringVar(value=", ".join(config.get("drives", ["C:"])))
        drives_entry = ttk.Entry(main_frame, textvariable=drives_var, width=50)
        drives_entry.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(main_frame, text="Comma-separated (e.g., C:, D:, E:)", font=("Arial", 8)).pack(anchor=tk.W, pady=(0, 15))

        # Threshold section
        ttk.Label(main_frame, text="Alert Threshold (GB):", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        threshold_var = tk.StringVar(value=str(config.get("threshold_gb", 50)))
        threshold_entry = ttk.Entry(main_frame, textvariable=threshold_var, width=20)
        threshold_entry.pack(anchor=tk.W, pady=(0, 15))

        # Check interval section
        ttk.Label(main_frame, text="Check Interval (minutes):", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        interval_var = tk.StringVar(value=str(config.get("check_interval_minutes", 5)))
        interval_entry = ttk.Entry(main_frame, textvariable=interval_var, width=20)
        interval_entry.pack(anchor=tk.W, pady=(0, 15))

        # Alert methods section
        ttk.Label(main_frame, text="Alert Methods:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        alert_methods = config.get("alert_methods", {"discord": True, "onscreen": True})

        discord_var = tk.BooleanVar(value=alert_methods.get("discord", True))
        discord_check = ttk.Checkbutton(main_frame, text="Discord Webhook", variable=discord_var)
        discord_check.pack(anchor=tk.W)

        onscreen_var = tk.BooleanVar(value=alert_methods.get("onscreen", True))
        onscreen_check = ttk.Checkbutton(main_frame, text="On-Screen Alert", variable=onscreen_var)
        onscreen_check.pack(anchor=tk.W, pady=(0, 15))

        # Discord webhook URL section
        ttk.Label(main_frame, text="Discord Webhook URL:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        webhook_var = tk.StringVar(value=config.get("discord_webhook_url", ""))
        webhook_entry = ttk.Entry(main_frame, textvariable=webhook_var, width=50)
        webhook_entry.pack(fill=tk.X, pady=(0, 15))

        # Cooldown section
        ttk.Label(main_frame, text="Alert Cooldown (hours):", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        cooldown_var = tk.StringVar(value=str(config.get("alert_cooldown_hours", 1)))
        cooldown_entry = ttk.Entry(main_frame, textvariable=cooldown_var, width=20)
        cooldown_entry.pack(anchor=tk.W, pady=(0, 20))

        def save_settings():
            try:
                # Parse drives
                drives = [d.strip() for d in drives_var.get().split(",") if d.strip()]
                if not drives:
                    drives = ["C:"]

                # Validate numeric values
                threshold = int(threshold_var.get())
                interval = int(interval_var.get())
                cooldown = float(cooldown_var.get())

                # Update config
                config.set("drives", drives)
                config.set("threshold_gb", threshold)
                config.set("check_interval_minutes", interval)
                config.set("alert_methods", {
                    "discord": discord_var.get(),
                    "onscreen": onscreen_var.get()
                })
                config.set("discord_webhook_url", webhook_var.get())
                config.set("alert_cooldown_hours", cooldown)

                self.settings_window.destroy()
                self.settings_window = None

                # Run check after settings window is closed
                if on_save_callback:
                    self.root.after(100, on_save_callback)

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}", parent=self.settings_window)

        def close_settings():
            self.settings_window.destroy()
            self.settings_window = None

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        save_btn = ttk.Button(button_frame, text="Save", command=save_settings)
        save_btn.pack(side=tk.RIGHT, padx=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=close_settings)
        cancel_btn.pack(side=tk.RIGHT)

        self.settings_window.protocol("WM_DELETE_WINDOW", close_settings)

    def show_alert(self, low_drives, threshold_gb):
        """Show on-screen alert."""
        self.run_in_tk_thread(self._create_alert_window, low_drives, threshold_gb)

    def _create_alert_window(self, low_drives, threshold_gb):
        """Create alert window (runs in tk thread)."""
        # Close existing alert if any
        if self.alert_window and self.alert_window.winfo_exists():
            self.alert_window.destroy()

        self.alert_window = tk.Toplevel(self.root)
        self.alert_window.title("Disk Space Alert")
        self.alert_window.attributes('-topmost', True)
        self.alert_window.overrideredirect(True)  # Remove window decorations
        self.alert_window.configure(bg='#ff4444')

        # Center the window
        width = 350
        height = 150 + (len(low_drives) * 30)
        screen_width = self.alert_window.winfo_screenwidth()
        screen_height = self.alert_window.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.alert_window.geometry(f"{width}x{height}+{x}+{y}")

        # Title
        title_label = tk.Label(
            self.alert_window,
            text="LOW DISK SPACE",
            font=("Arial", 16, "bold"),
            fg="white",
            bg="#ff4444"
        )
        title_label.pack(pady=10)

        # Drive info
        for drive_info in low_drives:
            drive_text = f"{drive_info['drive']} - {drive_info['free_gb']:.1f} GB free ({drive_info['percent_free']:.1f}%)"
            drive_label = tk.Label(
                self.alert_window,
                text=drive_text,
                font=("Arial", 11),
                fg="white",
                bg="#ff4444"
            )
            drive_label.pack(pady=5)

        # Threshold info
        threshold_label = tk.Label(
            self.alert_window,
            text=f"Threshold: {threshold_gb} GB",
            font=("Arial", 10),
            fg="white",
            bg="#ff4444"
        )
        threshold_label.pack(pady=5)

        # Info text
        info_label = tk.Label(
            self.alert_window,
            text="This alert will close when space is freed",
            font=("Arial", 9, "italic"),
            fg="white",
            bg="#ff4444"
        )
        info_label.pack(pady=10)

    def close_alert(self):
        """Close the alert window."""
        self.run_in_tk_thread(self._close_alert_window)

    def _close_alert_window(self):
        """Close alert window (runs in tk thread)."""
        if self.alert_window and self.alert_window.winfo_exists():
            self.alert_window.destroy()
            self.alert_window = None

    def stop(self):
        """Stop the tkinter manager."""
        self.running = False
        if self.root:
            self.root.after(0, self.root.quit)


class DiskMonitor:
    """Monitors disk space and triggers alerts."""

    def __init__(self, config, tk_manager):
        self.config = config
        self.tk_manager = tk_manager
        self.last_alerts = {}  # Track last alert time per drive
        self.running = True

    def get_disk_usage(self, drive):
        """Get disk usage for a specific drive."""
        try:
            usage = psutil.disk_usage(drive + "\\")
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent
            }
        except (FileNotFoundError, PermissionError):
            return None

    def bytes_to_gb(self, bytes_val):
        """Convert bytes to GB."""
        return bytes_val / (1024 ** 3)

    def check_drives(self):
        """Check all configured drives and return those below threshold."""
        drives = self.config.get("drives", ["C:"])
        threshold_gb = self.config.get("threshold_gb", 50)
        low_drives = []

        for drive in drives:
            usage = self.get_disk_usage(drive)
            if usage:
                free_gb = self.bytes_to_gb(usage["free"])
                if free_gb < threshold_gb:
                    low_drives.append({
                        "drive": drive,
                        "free_gb": free_gb,
                        "total_gb": self.bytes_to_gb(usage["total"]),
                        "percent_free": 100 - usage["percent"]
                    })

        return low_drives

    def can_send_alert(self, drive):
        """Check if enough time has passed since last alert for this drive."""
        cooldown_hours = self.config.get("alert_cooldown_hours", 1)
        last_alert = self.last_alerts.get(drive)

        if last_alert is None:
            return True

        return datetime.now() - last_alert > timedelta(hours=cooldown_hours)

    def send_discord_alert(self, drive_info):
        """Send alert to Discord webhook."""
        webhook_url = self.config.get("discord_webhook_url", "")

        if not webhook_url:
            return False

        message = {
            "embeds": [{
                "title": "Disk Space Alert!",
                "description": f"**Drive {drive_info['drive']}** is running low on space",
                "color": 16711680,  # Red
                "fields": [
                    {
                        "name": "Free Space",
                        "value": f"{drive_info['free_gb']:.1f} GB / {drive_info['total_gb']:.1f} GB ({drive_info['percent_free']:.1f}%)",
                        "inline": True
                    },
                    {
                        "name": "Threshold",
                        "value": f"{self.config.get('threshold_gb', 50)} GB",
                        "inline": True
                    }
                ],
                "timestamp": datetime.utcnow().isoformat()
            }]
        }

        try:
            response = requests.post(webhook_url, json=message, timeout=10)
            return response.status_code == 204
        except requests.RequestException:
            return False

    def trigger_alert(self, low_drives):
        """Trigger alerts based on configuration."""
        alert_methods = self.config.get("alert_methods", {"discord": True, "onscreen": True})
        threshold_gb = self.config.get("threshold_gb", 50)

        for drive_info in low_drives:
            # Try Discord if enabled
            if alert_methods.get("discord", True):
                discord_success = self.send_discord_alert(drive_info)
                # If Discord fails and on-screen not enabled, show on-screen anyway
                if not discord_success and not alert_methods.get("onscreen", True):
                    self.tk_manager.show_alert(low_drives, threshold_gb)

            # Record alert time
            self.last_alerts[drive_info["drive"]] = datetime.now()

        # Show on-screen if enabled
        if alert_methods.get("onscreen", True):
            self.tk_manager.show_alert(low_drives, threshold_gb)

    def run_check(self):
        """Run a single check cycle."""
        low_drives = self.check_drives()
        alert_methods = self.config.get("alert_methods", {"discord": True, "onscreen": True})
        onscreen_enabled = alert_methods.get("onscreen", True)

        # Filter to only drives that can receive alerts (cooldown passed)
        alertable_drives = [d for d in low_drives if self.can_send_alert(d["drive"])]

        if alertable_drives:
            self.trigger_alert(alertable_drives)

        # Close on-screen alert if no low drives OR on-screen is disabled
        if not low_drives or not onscreen_enabled:
            self.tk_manager.close_alert()

    def monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            self.run_check()
            interval = self.config.get("check_interval_minutes", 5) * 60

            # Sleep in small chunks to allow quick shutdown
            for _ in range(int(interval)):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        """Stop the monitor."""
        self.running = False
        self.tk_manager.close_alert()


class SpaceMonitorApp:
    """Main application class."""

    def __init__(self):
        self.config = Config()
        self.tk_manager = TkManager()
        self.monitor = DiskMonitor(self.config, self.tk_manager)
        self.monitor_thread = None
        self.icon = None

    def create_icon_image(self):
        """Create a simple icon for the system tray."""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw a simple disk shape
        draw.ellipse([8, 16, 56, 48], fill='#4CAF50', outline='#2E7D32', width=2)
        draw.ellipse([8, 8, 56, 40], fill='#4CAF50', outline='#2E7D32', width=2)

        # Draw center hole
        draw.ellipse([26, 18, 38, 30], fill='#2E7D32')

        return image

    def get_status_text(self):
        """Get current disk status for tooltip."""
        drives = self.config.get("drives", ["C:"])
        threshold = self.config.get("threshold_gb", 50)

        lines = ["Disk Disk Space Monitor"]
        for drive in drives:
            usage = self.monitor.get_disk_usage(drive)
            if usage:
                free_gb = self.monitor.bytes_to_gb(usage["free"])
                status = "OK" if free_gb >= threshold else "LOW"
                lines.append(f"{drive} {free_gb:.1f}GB free [{status}]")

        return "\n".join(lines)

    def open_settings(self, icon=None, item=None):
        """Open settings window."""
        self.tk_manager.show_settings(self.config, self.on_settings_save)

    def on_settings_save(self):
        """Called when settings are saved."""
        # Reload config in monitor
        self.monitor.config = self.config
        # Re-check drives
        self.monitor.run_check()

    def check_now(self, icon=None, item=None):
        """Force an immediate check."""
        self.monitor.run_check()

    def quit_app(self, icon=None, item=None):
        """Quit the application."""
        self.monitor.stop()
        self.tk_manager.stop()
        if self.icon:
            self.icon.stop()

    def run(self):
        """Run the application."""
        # Start tkinter manager
        self.tk_manager.start()

        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor.monitor_loop, daemon=True)
        self.monitor_thread.start()

        # Create system tray icon
        menu = pystray.Menu(
            pystray.MenuItem("Check Now", self.check_now),
            pystray.MenuItem("Settings", self.open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app)
        )

        self.icon = pystray.Icon(
            "space_monitor",
            self.create_icon_image(),
            "Disk Space Monitor",
            menu
        )

        # Update tooltip periodically
        def update_tooltip():
            while self.monitor.running:
                if self.icon:
                    self.icon.title = self.get_status_text()
                time.sleep(30)

        tooltip_thread = threading.Thread(target=update_tooltip, daemon=True)
        tooltip_thread.start()

        # Run the icon (this blocks)
        self.icon.run()


def main():
    """Main entry point."""
    if not HAS_TKINTER:
        print("Warning: tkinter not available, on-screen alerts will be disabled")

    app = SpaceMonitorApp()
    app.run()


if __name__ == "__main__":
    main()
