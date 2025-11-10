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

