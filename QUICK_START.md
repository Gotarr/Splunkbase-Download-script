# Splunkbase Download Script - Quick Start Guide

## For New Users

### Step 1: Download the Script
```bash
git clone <repository-url>
cd Splunkbase-Download-script
```

### Step 2: Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### Step 3: Set Up Your Configuration

#### Option A: Copy Example Files (Manual)
```bash
# Windows
copy login.json.example login.json
copy Your_apps.json.example Your_apps.json

# Linux/Mac
cp login.json.example login.json
cp Your_apps.json.example Your_apps.json
```

Then edit `login.json` with your Splunkbase credentials.

#### Option B: Use Interactive Onboarding (Recommended)
```bash
python splunkbase-download.py --onboard
```

This will:
- Prompt for your Splunkbase credentials
- Let you add apps by entering their UID (e.g., 742 for Windows TA)
- Automatically create `Your_apps.json`

### Step 4: Download Your Apps
```bash
# See what would be downloaded (dry-run)
python splunkbase-download.py --dry-run --summary

# Actually download the apps
python splunkbase-download.py
```

## Common UIDs

- 1621 - Splunk Common Information Model (CIM)
- 742 - Splunk Add-on for Microsoft Windows
- 833 - Splunk Add-on for Unix and Linux
- 1724 - Splunk App for Lookup File Editing
- 1809 - Splunk App for Stream

Find more at: https://splunkbase.splunk.com/

## Need Help?

```bash
# See all available options
python splunkbase-download.py --help

# Validate your configuration
python splunkbase-download.py --validate

# Check for updates without downloading
python splunkbase-download.py --dry-run --summary
```
