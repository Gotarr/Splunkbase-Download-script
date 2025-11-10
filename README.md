

# Splunkbase-Download-script

Python script for automated, robust downloading of Splunk Apps from Splunkbase. Cross-platform (Windows/Linux), with secure credential handling and atomic updates.

## Features

- Download Splunkbase apps listed in `Your_apps.json`
- **Interactive onboarding**: Add apps by UID or from existing TGZ filenames (`--onboard`)
- Secure authentication via `login.json` or interactive prompt (`--prompt-login`)
- Validation mode: Check `Your_apps.json` schema and consistency (`--validate`)
- File mismatch detection: Verify downloaded files match declared versions
- Streamed downloads (no memory overflow)
- Atomic updates to `Your_apps.json` (safe against crashes)
- Cross-platform: works on Windows and Linux
- Logging and verbose mode (`--verbose`)
- Retry/backoff for network errors
- Summary reports and JSON export (`--summary`, `--report-file`)
- Test suite included (pytest)

## Requirements

All dependencies are listed in `requirements.txt`. Install them with:

```bash
python -m pip install -r requirements.txt
```

Minimum required packages:
- requests
- urllib3
- pytest (for running tests)

## Setup

You need two files:

- `login.json`: Stores your Splunkbase credentials
- `Your_apps.json`: Lists the apps to download (fields: `uid`, `version`, etc.)

### Option 1: Manual Setup

Example `login.json`:
```json
{
    "username": "your_splunkbase_username_or_email",
    "password": "your_splunkbase_password"
}
```

Example `Your_apps.json`:
```json
[
  {
      "name": "Splunk Add-on for Microsoft Windows",
      "uid": 742,
      "appid": "Splunk_TA_windows",
      "updated_time": "2025-11-03T07:40:11+00:00",
      "version": "9.1.0"
  }
]
```

### Option 2: Interactive Onboarding (Recommended)

Instead of manually creating `Your_apps.json`, use the **`--onboard`** feature to add apps interactively:

#### Add apps by UID (Interactive)
```powershell
# Windows
python .\splunkbase-download.py --onboard

# Linux/macOS
python3 ./splunkbase-download.py --onboard
```

You'll be prompted to enter Splunkbase app UIDs:
```
App UID(s): 742, 833, 1621
  ✓ Queued UID 742
  ✓ Queued UID 833
  ✓ Queued UID 1621
App UID(s): 

Fetching details for 3 app(s) from Splunkbase...
  ✓ Splunk Add-on for Microsoft Windows (UID 742, v9.1.0)
  ✓ Splunk Add-on for Unix and Linux (UID 833, v10.2.0)
  ✓ Splunk Common Information Model (CIM) (UID 1621, v6.2.0)

✓ Successfully added 3 app(s) to Your_apps.json
```

**Common Splunkbase UIDs:**
- 742 - Splunk Add-on for Microsoft Windows
- 833 - Splunk Add-on for Unix and Linux
- 1621 - Splunk Common Information Model (CIM)
- 1724 - Splunk App for Lookup File Editing
- 1467 - Add-on for Cisco Network Data

#### Add apps from existing TGZ files
If you already downloaded apps manually and have TGZ files (format: `app-name_version.tgz`), use:

```powershell
# From a text file listing filenames
python .\splunkbase-download.py --onboard --from-files .\apps.txt

# From a directory containing TGZ files
python .\splunkbase-download.py --onboard --from-files .\downloads\
```

Example `apps.txt`:
```
splunk-add-on-for-microsoft-windows_910.tgz
splunk-add-on-for-unix-and-linux_1020.tgz
splunk-common-information-model-cim_620.tgz
```

The script will:
1. Parse app names from filenames
2. Look up UIDs using `app_name_mapping.conf` (customizable)
3. Fetch current metadata from Splunkbase
4. Create or update `Your_apps.json` with latest versions

**Customizing App Name Mapping:**
Edit `app_name_mapping.conf` to add your own app name → UID mappings:
```conf
# Format: app-name=UID
splunk-add-on-for-microsoft-windows=742
my-custom-app=1234
```

## Usage

### Basic Download

Download all apps listed in `Your_apps.json`:

#### Windows (PowerShell)
```powershell
python .\splunkbase-download.py --outdir .\downloads
```

#### Linux/macOS (Bash)
```bash
python3 ./splunkbase-download.py -o ./downloads
# Or make executable:
chmod +x ./splunkbase-download.py
./splunkbase-download.py -o ./downloads
```

### Interactive Login
If you don't want to store credentials in `login.json`, use:
```powershell
python .\splunkbase-download.py --prompt-login
```
or
```bash
python3 ./splunkbase-download.py --prompt-login
```
You will be prompted for username and password. Optionally, you can save them to `login.json` (on Linux, permissions will be set to `0o600`).

### Dry Run
Check for updates without downloading:
```bash
python3 ./splunkbase-download.py --dry-run --summary
```

### Validation and Maintenance

#### Validate Your_apps.json
Check schema, types, duplicates, and file presence:
```powershell
python .\splunkbase-download.py --validate --summary
```

Example output:
```
-----------------------------------------------------------------------------------------
IDX   UID      Status   File   Version      Issues
-----------------------------------------------------------------------------------------
0     742      valid    yes    9.1.0
1     833      valid    no     10.2.0        
2     1621     valid    yes    6.2.0
-----------------------------------------------------------------------------------------
Errors: 0 | Warnings: 0 | Missing files: 1 | Total: 3
```

#### Format Your_apps.json
Rewrite with consistent formatting (pretty print, sorted):
```powershell
python .\splunkbase-download.py --validate --format-json
```

#### Re-download Missing Files
If files are missing but declared in `Your_apps.json`:
```powershell
python .\splunkbase-download.py --fix-missing --outdir .\downloads
```

### Summary Reports

#### Terminal Summary
```powershell
python .\splunkbase-download.py --dry-run --summary
```

#### JSON Report
```powershell
python .\splunkbase-download.py --summary --report-file .\update-report.json
```

Example report structure:
```json
{
  "generated_at": "2025-11-10T14:30:00Z",
  "summary": {
    "total": 3,
    "to_update": 1,
    "up_to_date": 2,
    "errors": 0,
    "missing_files": 1
  },
  "results": [
    {
      "uid": 742,
      "current": "9.0.0",
      "latest": "9.1.0",
      "action": "updated",
      "reason": "downloaded and file updated",
      "file_present": true,
      "file_path": "downloads\\742_9.1.0.tgz"
    }
  ]
}
```

### Advanced Usage

#### Process specific apps only
```powershell
# Coming soon: --only flag
python .\splunkbase-download.py --only 742,833 --outdir .\downloads
```

#### Exclude specific apps
```powershell
# Coming soon: --exclude flag
python .\splunkbase-download.py --exclude 1621 --outdir .\downloads
```

## Running Tests

Install dependencies and run the test suite with pytest:
```bash
python -m pip install -r requirements.txt
pytest -q
```

## Security Notes

- Only save credentials on trusted machines
- For encrypted credential storage, consider using an OS keyring (not included)
- The `login.json` file contains your Splunkbase credentials in plain text
- On Linux, the script automatically sets file permissions to `0o600` for `login.json`
- Never commit `login.json` to version control (already in `.gitignore`)
- This script is provided "as-is" without any warranty

## Compliance

**Important**: By using this script, you agree to comply with the [Splunkbase Terms of Service](https://www.splunk.com/en_us/legal/splunk-general-terms.html).

This script:
- Uses official Splunkbase APIs
- Requires valid Splunkbase credentials
- Downloads only apps you have access to
- Is intended for personal/organizational use to automate app management

**Users are responsible for**:
- Ensuring they have the right to download and use the apps
- Complying with individual app licenses
- Following Splunkbase usage policies
- Protecting their credentials

## Third-Party Dependencies

This project uses the following open-source libraries:
- [requests](https://github.com/psf/requests) - Apache License 2.0
- [urllib3](https://github.com/urllib3/urllib3) - MIT License
- [pytest](https://github.com/pytest-dev/pytest) - MIT License (dev dependency)

See LICENSE file for full details.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add/update tests as needed
5. Submit a pull request

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing issues before creating new ones

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for full details.

**Disclaimer**: This software is provided "as-is" without warranty. The authors are not responsible for any damages or issues arising from its use.

