# Disk Space Monitor

A Windows system tray application that monitors disk space and sends alerts via Discord webhook and/or on-screen notifications.

## Features

- **System Tray Icon** - Runs quietly in the background, hover to see disk status
- **Configurable Drives** - Monitor one or multiple drives (C:, D:, etc.)
- **Configurable Threshold** - Set minimum free space in GB
- **Discord Alerts** - Sends rich embed notifications to your Discord channel
- **On-Screen Alerts** - Persistent always-on-top notification that auto-closes when space is freed
- **Configurable Check Interval** - Set how often to check disk space

## Installation

### Prerequisites
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/Space-Monitor.git
cd Space-Monitor

# Install dependencies
uv sync
```

## Usage

```bash
# Run the application
uv run python space_monitor.py
```

The app will start minimized to your system tray. Right-click the green disk icon to:
- **Check Now** - Force an immediate disk check
- **Settings** - Configure drives, thresholds, and alerts
- **Quit** - Exit the application

## Configuration

Settings are stored in `config.json` (auto-created on first run):

| Setting | Description | Default |
|---------|-------------|---------|
| `drives` | List of drives to monitor | `["C:"]` |
| `threshold_gb` | Alert when free space falls below this (GB) | `10` |
| `check_interval_minutes` | How often to check disk space | `5` |
| `alert_methods.discord` | Enable Discord webhook alerts | `true` |
| `alert_methods.onscreen` | Enable on-screen popup alerts | `true` |
| `discord_webhook_url` | Your Discord webhook URL | `""` |
| `alert_cooldown_hours` | Minimum time between repeat alerts | `0` |

### Setting up Discord Webhook

1. In Discord, go to Server Settings > Integrations > Webhooks
2. Click "New Webhook" and copy the webhook URL
3. Paste the URL in Disk Space Monitor settings

## Screenshots

### System Tray
Hover over the tray icon to see current disk status.

### On-Screen Alert
A red alert window appears when disk space is low. It cannot be closed manually and will automatically disappear when space is freed or threshold is adjusted.

### Discord Alert
Rich embed notification showing drive, free space, and threshold.

## Dependencies

- `psutil` - Disk space monitoring
- `pystray` - System tray icon
- `Pillow` - Icon generation
- `requests` - Discord webhook

## License

MIT
