# Splunkbase-Download-script
Python Script for downloading Splunk Apps from Splunkbase
Important:
You need both files: 1) login.json for your credentials 2) Your_apps.json to dertermine wich apps should be downloaded. 
The "uid" and "version" fields are the most important ones !


login.json
```
  {
      "username": "Dein Splunk.com Loginname Oder Mail-Adresse",
      "password": "Dein Splunk.com Passwort"
  }
```

Your_apps.json
```
[
  {
      "name": "Splunk Add-on for Microsoft Windows",
      "uid": 742,
      "appid": "Splunk_TA_windows",
      "updated_time": "Tue, 26 Sep 2023 06:23:01 GMT",
      "version": "8.8.0"
  },
  {
      "name": "Splunk Common Information Model (CIM)",
      "uid": 1621,
      "appid": "Splunk_SA_CIM",
      "updated_time": "Wed, 08 Nov 2023 21:06:39 GMT",
      "version": "5.1.2"
  },
  {
      "name": "Splunk Add-on for Unix and Linux",
      "uid": 833,
      "appid": "Splunk_TA_nix",
      "updated_time": "Wed, 08 Nov 2023 19:23:49 GMT",
      "version": "9.0.0"
  }
]
```

## New: robust downloader (02-splunkbase-download.py)

I added a new, more robust script: `02-splunkbase-download.py`.

What it improves:
- Streamed downloads (doesn't load entire file into memory).
- Defensive API parsing for versions (avoids IndexError/KeyError).
- Atomic writes for `Your_apps.json` (write to temp file then replace).
- Normalizes `Last-Modified` header to ISO8601 UTC if present.

Quick usage (Windows PowerShell):

```powershell
python .\02-splunkbase-download.py
```

Dependencies:
- requests (pip install requests)

Files required (same as before):
- `login.json` (username/password)
- `Your_apps.json` (list of apps with `uid` and `version`)
If you want, I can make the script overwrite the header `letzte Änderung` automatically or add retries/backoff. Tell me which additional features you'd like.

## Current version changes (02-splunkbase-download.py) — 10.11.2025

This repository now includes an improved downloader script `02-splunkbase-download.py`. Key changes in this version:

- Streamed downloads: files are downloaded with `stream=True` and written in chunks to avoid loading entire archives into memory.
- Defensive API handling: version API responses are validated before use (avoids IndexError/KeyError and invalid JSON crashes).
- Atomic updates: `Your_apps.json` is written atomically (temporary file + replace) to prevent corruption on crash.
- Cross-platform paths: replaced string paths with `pathlib.Path` to work consistently on Windows and Linux.
- CLI args: added `--outdir` (`-o`) to choose output folder, `--dry-run` for checks without downloading, and `--verbose` for more output.
- Logging: replaced ad-hoc prints with the `logging` module (honors `--verbose`).
- Retries and session: network calls use a `requests.Session` with an exponential/backoff retry policy for transient errors.
- POSIX file permissions: downloaded files and updated JSON get sensible permissions on non-Windows systems.
- Tests: basic `pytest` tests added to validate atomic writes and download cleanup/skip behavior.

These changes make the downloader more robust and suitable for running on both Windows and Linux systems.

## Requirements

All Python dependencies are listed in `requirements.txt`. Install them with:

```bash
python -m pip install -r requirements.txt
```

Minimum required packages (also present in `requirements.txt`):
- requests
- urllib3
- pytest (for running tests)

## Running the script

PowerShell (Windows):

```powershell
python .\02-splunkbase-download.py --outdir .\downloads
```

Bash (Linux/macOS):

```bash
python3 ./02-splunkbase-download.py -o ./downloads
# or after making executable:
# chmod +x ./02-splunkbase-download.py
# ./02-splunkbase-download.py -o ./downloads
```

## Running tests

Install dependencies and run the test suite with pytest (recommended inside a virtualenv):

```bash
python -m pip install -r requirements.txt
pytest -q
```

