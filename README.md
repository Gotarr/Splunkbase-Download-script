

# Splunkbase-Download-script

Python script for automated, robust downloading of Splunk Apps from Splunkbase. Cross-platform (Windows/Linux), with secure credential handling and atomic updates.

---

**🚀 New User?** See [QUICK_START.md](QUICK_START.md) for a step-by-step guide!

---

## Quick Start

### 1. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 2. Create Configuration Files

```bash
# Copy example files
cp login.json.example login.json
cp Your_apps.json.example Your_apps.json

# Edit login.json with your Splunkbase credentials
# Edit Your_apps.json with the apps you want to manage
```

**Or use interactive onboarding** (recommended for first-time users):

```bash
# Add apps interactively
python splunkbase-download.py --onboard

# Import from existing .tgz files
python splunkbase-download.py --onboard --from-files /path/to/apps/

# Or from a text file listing filenames
python splunkbase-download.py --onboard --from-files apps.txt
```

### 3. Download Apps

```bash
# Download/update all apps
python splunkbase-download.py

# Dry-run to see what would be updated
python splunkbase-download.py --dry-run --summary
```

## Features

- Download Splunkbase apps listed in `Your_apps.json`
- **Interactive onboarding**: Add apps by UID or from existing TGZ filenames (`--onboard`)
- **Automatic backup rotation**: Configurable retention of `Your_apps.json` backups (`--backup-keep`)
- **CI/CD integration**: Exit codes for automated pipelines (`--fail-on-errors`)
- **Smart filtering**: Process only specific apps or exclude certain ones (`--only`, `--exclude`)
- **File integrity**: SHA256 hash calculation for verification (`--hash`)
- **Missing file repair**: Automatically re-download missing files (`--fix-missing`)
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
- `requests` - HTTP library for downloads
- `urllib3` - HTTP connection pooling
- `pytest` - (optional) For running tests

## Configuration Files

The script uses two configuration files:

### `login.json` - Splunkbase Credentials

**Template available:** `login.json.example`

```json
{
    "username": "your-splunkbase-username",
    "password": "your-splunkbase-password"
}
```

**Security note:** This file is in `.gitignore` and should never be committed to version control.

**Alternative:** Use `--prompt-login` to enter credentials interactively each time.

### `Your_apps.json` - App List

**Template available:** `Your_apps.json.example`

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
```bash
# Process only specific UIDs
python splunkbase-download.py --only 742,833 --dry-run --summary
```

#### Exclude specific apps
```bash
# Skip specific UIDs from processing
python splunkbase-download.py --exclude 1621 --outdir ./downloads
```

#### Calculate file hashes
```bash
# Include SHA256 hashes in reports (useful for verification)
python splunkbase-download.py --dry-run --hash --report-file report.json
```

#### Fix missing files
```bash
# Re-download files that are declared but missing locally
python splunkbase-download.py --fix-missing

# Dry-run to see what would be re-downloaded
python splunkbase-download.py --fix-missing --dry-run --summary
```

#### Filter and validate
```bash
# Validate only specific apps
python splunkbase-download.py --validate --only 742,1621 --summary

# Exclude apps from validation
python splunkbase-download.py --validate --exclude 1809
```

#### Backup management
```bash
# Keep only 3 backups (default is 5)
python splunkbase-download.py --validate --format-json --backup-keep 3

# Disable backups completely
python splunkbase-download.py --validate --format-json --backup-keep 0

# View existing backups
ls Your_apps.json.bak-*
```

#### CI/CD Integration
```bash
# Exit with code 1 if validation fails (for CI pipelines)
python splunkbase-download.py --validate --fail-on-errors

# Combined: validate, create backup, fail on errors
python splunkbase-download.py --validate --backup-keep 10 --fail-on-errors
```

## Command-Line Flags

### Core Options
- `--outdir PATH` / `-o PATH` - Output directory for downloaded apps (default: current directory)
- `--dry-run` - Check for updates without downloading
- `--verbose` / `-v` - Enable detailed logging
- `--prompt-login` - Prompt for credentials instead of using `login.json`
- `--summary` - Print concise summary table
- `--report-file PATH` - Write JSON report with detailed results

### Validation & Quality
- `--validate` - Validate `Your_apps.json` schema and consistency
- `--format-json` - Reformat `Your_apps.json` with consistent formatting
- `--hash` - Calculate SHA256 hashes for files (includes in reports)

### App Management
- `--onboard` - Interactive mode to add apps by UID
- `--from-files PATH` - With `--onboard`: import apps from TGZ filenames or directory
- `--fix-missing` - Re-download files that are declared but missing
- `--fix-missing-upgrade` - (Reserved for future use)

### Filtering
- `--only UIDS` - Process only specified UIDs (comma-separated, e.g., `742,833,1621`)
- `--exclude UIDS` - Exclude specified UIDs from processing (comma-separated)

**Note:** Filters (`--only`/`--exclude`) work in all modes: normal, dry-run, validate, fix-missing

### Backup & CI/CD Integration
- `--backup-keep N` - Number of backup files to keep before updating `Your_apps.json` (default: 5, 0 to disable)
- `--fail-on-errors` - Exit with non-zero status if errors or inconsistencies are detected (for CI pipelines)

**Backup behavior:**
- Backups are created automatically before any `Your_apps.json` modification
- Format: `Your_apps.json.bak-YYYYMMDD-HHMMSS`
- Rotation: Only the N most recent backups are kept
- Set to `0` to disable backups completely

## Running Tests

Install dependencies and run the test suite with pytest:
```bash
python -m pip install -r requirements.txt
pytest -q
```

## Troubleshooting

### Authentication Issues

**Problem:** "Login failed" or "401 Unauthorized"
- Verify credentials in `login.json` are correct
- Check if your Splunkbase account is active
- Try `--prompt-login` to enter credentials manually
- Ensure no trailing spaces in username/password

**Problem:** `login.json` not found
- Use `--prompt-login` to enter credentials interactively
- Copy `login.json.example` to `login.json` and edit with your credentials

### Validation Errors

**Problem:** `--validate` reports schema errors
- Check that all required fields exist: `uid`, `version`, `name`, `appid`, `updated_time`
- Ensure `uid` is an integer (not a string)
- Use `--format-json` to reformat and fix common formatting issues
- Restore from backup if needed: `cp Your_apps.json.bak-<timestamp> Your_apps.json`

**Problem:** Duplicate UIDs detected
- Remove duplicate entries manually or restore from backup
- Each app should appear only once in `Your_apps.json`

### Download Issues

**Problem:** Downloads fail with network errors
- Script automatically retries (3 attempts with backoff)
- Check internet connection
- Verify Splunkbase is accessible: https://splunkbase.splunk.com
- Try again later if Splunkbase is experiencing issues

**Problem:** Downloaded file is corrupted
- Use `--hash` to verify file integrity with SHA256
- Re-download with `--fix-missing` after removing the corrupted file
- Check available disk space

### Missing Files

**Problem:** `file_present: false` in reports
- Use `--fix-missing` to automatically re-download missing files
- Run `--validate --summary` to see which files are missing
- Ensure `--outdir` points to the correct directory

### Backup & Recovery

**Problem:** `Your_apps.json` was corrupted/overwritten
- List available backups: `ls Your_apps.json.bak-*` (Linux) or `dir Your_apps.json.bak-*` (Windows)
- Restore from most recent backup: `cp Your_apps.json.bak-<timestamp> Your_apps.json`
- Backups are timestamped: `YYYYMMDD-HHMMSS`

**Problem:** Too many backup files
- Adjust retention: `--backup-keep 3` (keeps only 3 most recent)
- Disable backups: `--backup-keep 0` (not recommended)
- Manually delete old backups: `rm Your_apps.json.bak-*` (be careful!)

### CI/CD Integration

**Problem:** Pipeline doesn't fail on errors
- Use `--fail-on-errors` flag to ensure non-zero exit code on errors
- Example: `python splunkbase-download.py --validate --fail-on-errors`
- Check exit code: `echo $?` (Linux) or `echo $LASTEXITCODE` (PowerShell)

**Problem:** Want to test without downloading
- Use `--dry-run --summary` to see what would be updated
- Combine with `--report-file` to save results: `--dry-run --report-file check.json`

### Performance

**Problem:** Script is slow
- Downloads are sequential (API rate limiting consideration)
- Network speed affects download time
- Use `--only` to process specific apps: `--only 742,833`
- Large apps take longer to download

### General Tips

- Run `--validate --summary` regularly to check for issues
- Use `--dry-run` before actual updates to preview changes
- Keep backups enabled (default: 5 most recent)
- Check logs with `--verbose` for detailed information
- Use filters (`--only`/`--exclude`) for targeted operations

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
