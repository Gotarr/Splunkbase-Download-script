####################################
#### Splunkbase Download Script
#### Erstellung: 10.11.2025
#### letzte Änderung: 10.11.2025
#### Creator: Gotarr
####################################

"""02 - Splunkbase Download Script (robust)

Improvements over 01-splunkbase-download.py:
- Streamed download (stream=True) to avoid loading whole file into memory
- Defensive get_latest_version() with checks
- Atomic write for Your_apps.json (write temp file then os.replace)
- Parse Last-Modified header to ISO8601 UTC when present

Run: python 02-splunkbase-download.py
"""

import requests
import json
import os
import datetime
import tempfile
from email.utils import parsedate_to_datetime


def download_stream(app_id, app_version, cookies, downloaded_apps, skipped_apps, out_dir="."):
    """Stream-download the TGZ and return updated_time in ISO8601 UTC or None.
    Returns updated_time (str) or None on failure.
    """
    file_name = f"{app_id}_{app_version}.tgz"
    file_path = os.path.join(out_dir, file_name)
    updated_time = None

    if os.path.exists(file_path):
        skipped_apps.append(file_name)
        return None

    download_url = (
        f"https://api.splunkbase.splunk.com/api/v2/apps/{app_id}/releases/{app_version}/download/?origin=sb&lead=false"
    )

    try:
        with requests.get(download_url, cookies=cookies, stream=True, timeout=60) as r:
            if r.status_code != 200:
                print(f"Failed to download {file_name}. Status code: {r.status_code}")
                return None

            # Stream to disk
            with open(file_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)

            downloaded_apps.append(file_name)

            # Parse Last-Modified header if present
            lm = r.headers.get("Last-Modified")
            if lm:
                try:
                    dt = parsedate_to_datetime(lm)
                    # Ensure UTC and produce ISO8601
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    updated_time = dt.astimezone(datetime.timezone.utc).isoformat()
                except Exception:
                    updated_time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
            else:
                updated_time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

            return updated_time

    except requests.RequestException as e:
        print(f"Network error while downloading {file_name}: {e}")
        # Clean up possibly partial file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        return None


def update_Your_apps_file_atomic(apps_data, uid, new_version, updated_time, file_path="Your_apps.json"):
    """Atomically update Your_apps.json by writing to a temp file and replacing the original.
    Modifies apps_data in-memory as well.
    """
    found = False
    for app in apps_data:
        if app.get("uid") == uid:
            app["version"] = new_version
            app["updated_time"] = updated_time
            found = True
            break

    if not found:
        # If app not present, append a new entry
        apps_data.append({"uid": uid, "version": new_version, "updated_time": updated_time})

    dir_name = os.path.dirname(os.path.abspath(file_path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="your_apps_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            json.dump(apps_data, tmpf, indent=4, ensure_ascii=False)
            tmpf.flush()
            os.fsync(tmpf.fileno())
        os.replace(tmp_path, file_path)
    except Exception as e:
        print(f"Failed to write updated apps file: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def authenticate():
    if not os.path.exists("login.json"):
        raise FileNotFoundError("login.json not found")

    with open("login.json", "r", encoding="utf-8") as f:
        login_data = json.load(f)

    login_url = "https://splunkbase.splunk.com/api/account:login/"
    payload = {"username": login_data.get("username"), "password": login_data.get("password")}
    try:
        resp = requests.post(login_url, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.cookies.get_dict()
    except requests.RequestException as e:
        raise RuntimeError(f"Authentication failed: {e}")


def get_latest_version_safe(uid, cookies):
    url = f"https://splunkbase.splunk.com/api/v1/app/{uid}/release/"
    try:
        resp = requests.get(url, cookies=cookies, timeout=30)
        if resp.status_code != 200:
            print(f"Error retrieving app version for {uid}: Status code {resp.status_code}")
            return None
        data = resp.json()
        if not data or not isinstance(data, list):
            print(f"Unexpected version response for {uid}: {type(data)}")
            return None
        first = data[0]
        if not isinstance(first, dict) or "name" not in first:
            print(f"Missing 'name' in version response for {uid}")
            return None
        return first["name"]
    except (ValueError, json.JSONDecodeError):
        print(f"Invalid JSON when retrieving version for {uid}")
        return None
    except requests.RequestException as e:
        print(f"Network error when retrieving version for {uid}: {e}")
        return None


if __name__ == "__main__":
    try:
        cookies = authenticate()

        if not os.path.exists("Your_apps.json"):
            raise FileNotFoundError("Your_apps.json not found")

        with open("Your_apps.json", "r", encoding="utf-8") as f:
            apps_data_from_file = json.load(f)

        downloaded_apps = []
        skipped_apps = []

        for app in apps_data_from_file:
            uid = app.get("uid")
            if uid is None:
                print(f"Skipping entry without uid: {app}")
                continue

            latest_version = get_latest_version_safe(uid, cookies)
            if latest_version and latest_version != app.get("version"):
                updated_time = download_stream(uid, latest_version, cookies, downloaded_apps, skipped_apps)
                if updated_time:
                    # Update file atomically
                    update_Your_apps_file_atomic(apps_data_from_file, uid, latest_version, updated_time)
            else:
                skipped_apps.append(f"{uid}_{app.get('version')}")

        print(f"Downloaded apps: {downloaded_apps}")
        print(f"Skipped apps: {skipped_apps}")

    except Exception as e:
        print(f"An error occurred: {e}")
