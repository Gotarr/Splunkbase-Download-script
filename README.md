

# Splunkbase-Download-script

Python script for automated, robust downloading of Splunk Apps from Splunkbase. Cross-platform (Windows/Linux), with secure credential handling and atomic updates.

## Features

- Download Splunkbase apps listed in `Your_apps.json`
- Secure authentication via `login.json` or interactive prompt (`--prompt-login`)
- Streamed downloads (no memory overflow)
- Atomic updates to `Your_apps.json` (safe against crashes)
- Cross-platform: works on Windows and Linux
- Logging and verbose mode (`--verbose`)
- Retry/backoff for network errors
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
      "updated_time": "Tue, 26 Sep 2023 06:23:01 GMT",
      "version": "8.8.0"
  }
]
```

## Usage

### Windows (PowerShell)
```powershell
python .\splunkbase-download.py --outdir .\downloads
```

### Linux/macOS (Bash)
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
python3 ./splunkbase-download.py --dry-run
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

