# Deployment Guide

This directory contains systemd service templates for automating the pro_botti trading system.

## Files

- **pro_botti.service** - Main live trading service
- **pro_botti-retrain.service** - One-shot retrain pipeline service
- **pro_botti-retrain.timer** - Timer for scheduled retraining

## Installation

### Prerequisites

1. Pro botti installed at `/root/pro_botti` (or update paths in service files)
2. Python virtual environment at `/root/pro_botti/venv`
3. Configuration file at `/root/pro_botti/config.yaml`
4. Environment variables in `/root/pro_botti/botti.env`

### Install Services

```bash
# Copy service files to systemd directory
sudo cp pro_botti.service /etc/systemd/system/
sudo cp pro_botti-retrain.service /etc/systemd/system/
sudo cp pro_botti-retrain.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload
```

### Enable and Start Live Trading

```bash
# Enable service to start on boot
sudo systemctl enable pro_botti.service

# Start the service now
sudo systemctl start pro_botti.service

# Check status
sudo systemctl status pro_botti.service

# View logs
sudo journalctl -u pro_botti.service -f
```

### Enable Automated Retraining

```bash
# Enable timer (runs daily at 2 AM UTC)
sudo systemctl enable pro_botti-retrain.timer

# Start timer
sudo systemctl start pro_botti-retrain.timer

# Check timer status
sudo systemctl status pro_botti-retrain.timer

# List scheduled times
sudo systemctl list-timers pro_botti-retrain.timer

# View retrain logs
sudo journalctl -u pro_botti-retrain.service -f
```

## Service Management

### Live Trading Service

```bash
# Start
sudo systemctl start pro_botti.service

# Stop
sudo systemctl stop pro_botti.service

# Restart
sudo systemctl restart pro_botti.service

# Check status
sudo systemctl status pro_botti.service

# View real-time logs
sudo journalctl -u pro_botti.service -f

# View last 100 lines
sudo journalctl -u pro_botti.service -n 100
```

### Retrain Timer

```bash
# Start timer
sudo systemctl start pro_botti-retrain.timer

# Stop timer
sudo systemctl stop pro_botti-retrain.timer

# Check when next run is scheduled
sudo systemctl list-timers pro_botti-retrain.timer

# Trigger retrain manually (without waiting for timer)
sudo systemctl start pro_botti-retrain.service

# View retrain logs
sudo journalctl -u pro_botti-retrain.service -n 200
```

## Customization

### Change Retrain Schedule

Edit `pro_botti-retrain.timer` and modify the `OnCalendar` directive:

```ini
[Timer]
# Daily at 2 AM UTC
OnCalendar=*-*-* 02:00:00

# Or use shortcuts:
# OnCalendar=daily          # Midnight
# OnCalendar=weekly         # Monday midnight
# OnCalendar=monthly        # 1st of month midnight

# Multiple schedules:
OnCalendar=*-*-* 02:00:00
OnCalendar=*-*-* 14:00:00  # Also run at 2 PM
```

After changes:
```bash
sudo systemctl daemon-reload
sudo systemctl restart pro_botti-retrain.timer
```

### Change Installation Path

If pro_botti is installed elsewhere, update these in service files:

- `WorkingDirectory=/root/pro_botti`
- `Environment="ROOT=/root/pro_botti"`
- `ExecStart=/root/pro_botti/...`
- `EnvironmentFile=/root/pro_botti/botti.env`

### Adjust Resource Limits

Edit service files to change:

```ini
[Service]
# Memory limit (increase if needed)
MemoryMax=4G

# CPU limit (200% = 2 cores)
CPUQuota=200%
```

## Monitoring

### Check Service Health

```bash
# Overall status
sudo systemctl status pro_botti.service

# Process info
ps aux | grep pro_botti

# Resource usage
systemctl show pro_botti.service | grep -E "Memory|CPU"
```

### View Logs

```bash
# Live trading logs
tail -f /root/pro_botti/logs/live.log
tail -f /root/pro_botti/logs/live.err

# Retrain logs
tail -f /root/pro_botti/logs/retrain.log
tail -f /root/pro_botti/logs/retrain.err

# Loop logs
tail -f /root/pro_botti/logs/loop.log
```

### Check Active Symbols

```bash
cd /root/pro_botti
python3 -m cli show-active
```

## Troubleshooting

### Service Won't Start

```bash
# Check for errors
sudo journalctl -u pro_botti.service -n 50

# Verify files exist
ls -la /root/pro_botti/venv/bin/python3
ls -la /root/pro_botti/config.yaml
ls -la /root/pro_botti/botti.env

# Test manually
cd /root/pro_botti
source venv/bin/activate
python3 -m cli live --config config.yaml
```

### Timer Not Running

```bash
# Check timer is active
sudo systemctl is-active pro_botti-retrain.timer

# Check timer list
sudo systemctl list-timers --all | grep retrain

# Enable if needed
sudo systemctl enable pro_botti-retrain.timer
```

### Retrain Failing

```bash
# Check retrain logs
sudo journalctl -u pro_botti-retrain.service -n 100

# Run manually to debug
cd /root/pro_botti
./scripts/auto_retrain.sh
```

### Permission Issues

```bash
# Check file ownership
ls -la /root/pro_botti/

# Fix ownership if needed
sudo chown -R root:root /root/pro_botti/

# Make scripts executable
chmod +x /root/pro_botti/scripts/*.sh
```

## Uninstallation

```bash
# Stop and disable services
sudo systemctl stop pro_botti.service
sudo systemctl stop pro_botti-retrain.timer
sudo systemctl disable pro_botti.service
sudo systemctl disable pro_botti-retrain.timer

# Remove service files
sudo rm /etc/systemd/system/pro_botti.service
sudo rm /etc/systemd/system/pro_botti-retrain.service
sudo rm /etc/systemd/system/pro_botti-retrain.timer

# Reload systemd
sudo systemctl daemon-reload
```

## Best Practices

1. **Monitor Initially**: Watch logs closely for the first few days
2. **Test Manually First**: Run `auto_retrain.sh` manually before enabling timer
3. **Backup Models**: Keep backups of working models before retraining
4. **Resource Limits**: Set appropriate MemoryMax and CPUQuota
5. **Log Rotation**: Setup logrotate for `/root/pro_botti/logs/`
6. **Alert Integration**: Consider adding alerts for service failures

## Example Logrotate Config

Create `/etc/logrotate.d/pro_botti`:

```
/root/pro_botti/logs/*.log /root/pro_botti/logs/*.err {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 root root
}
```

Test:
```bash
sudo logrotate -d /etc/logrotate.d/pro_botti
```
