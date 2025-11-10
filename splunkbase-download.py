#!/usr/bin/env python3
####################################
#### Splunkbase Download Script
#### Erstellung: 10.11.2025
#### letzte Änderung: 10.11.2025
#### Creator: Gotarr
####################################


import argparse
import json
import tempfile
import datetime
import os
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from email.utils import parsedate_to_datetime
import logging
import getpass


def download_stream(app_id, app_version, cookies, downloaded_apps, skipped_apps, out_dir=Path("."), session=None):
    """Stream-download the TGZ and return updated_time in ISO8601 UTC or None.
    Returns updated_time (str) or None on failure.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{app_id}_{app_version}.tgz"
    file_path = out_dir / file_name
    updated_time = None

    if file_path.exists():
        skipped_apps.append(file_name)
        return None

    download_url = (
        f"https://api.splunkbase.splunk.com/api/v2/apps/{app_id}/releases/{app_version}/download/?origin=sb&lead=false"
    )

    if session is None:
        session = requests

    try:
        with session.get(download_url, cookies=cookies, stream=True, timeout=60) as r:
            if r.status_code != 200:
                logging.error("Failed to download %s. Status code: %s", file_name, r.status_code)
                return None

            # Stream to disk
            with file_path.open("wb") as fh:
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

            # Ensure reasonable file permissions on POSIX
            try:
                if os.name != "nt":
                    file_path.chmod(0o644)
            except Exception:
                pass

            return updated_time

    except requests.RequestException as e:
        logging.error("Network error while downloading %s: %s", file_name, e)
        # Clean up possibly partial file
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            logging.debug("Failed to remove partial file %s", file_path, exc_info=True)
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

    file_path_obj = Path(file_path)
    dir_name = str(file_path_obj.parent) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="your_apps_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            json.dump(apps_data, tmpf, indent=4, ensure_ascii=False)
            tmpf.flush()
            os.fsync(tmpf.fileno())
        # Atomic replace
        Path(tmp_path).replace(file_path_obj)
        # Set permissions on POSIX
        try:
            if os.name != "nt":
                file_path_obj.chmod(0o644)
        except Exception:
            pass
    except Exception as e:
        logging.error("Failed to write updated apps file: %s", e)
        try:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except Exception:
            logging.debug("Failed to remove temp file %s", tmp_path, exc_info=True)
        raise


def authenticate(session=None, prompt=False):
    """Authenticate against Splunkbase. If `prompt` is True or login.json is missing/invalid,
    interactively prompt for username/password. Optionally save credentials when prompted.
    Returns cookies dict.
    """

    login_file = Path("login.json")
    creds = {}
    if login_file.exists():
        try:
            creds = json.loads(login_file.read_text(encoding="utf-8"))
        except Exception:
            creds = {}

    if not creds.get("username") or not creds.get("password"):
        logging.error("No valid credentials found in login.json. Please provide username and password.")
        prompt = True

    while True:
        if prompt or not creds.get("username") or not creds.get("password"):
            username = input("Splunkbase username: ")
            password = getpass.getpass("Splunkbase password: ")
            creds = {"username": username, "password": password}
            save = input("Save credentials to login.json? [y/N]: ").strip().lower()
            if save == "y":
                try:
                    login_file.write_text(json.dumps(creds, indent=4), encoding="utf-8")
                    if os.name != "nt":
                        try:
                            login_file.chmod(0o600)
                        except Exception:
                            pass
                except Exception as e:
                    logging.warning("Could not save credentials to login.json: %s", e)

        login_url = "https://splunkbase.splunk.com/api/account:login/"
        payload = {"username": creds.get("username"), "password": creds.get("password")}
        sess = session or requests
        try:
            resp = sess.post(login_url, data=payload, timeout=30)
            if resp.status_code == 403:
                logging.error("Authentication failed with 403 Forbidden. Please try again.")
                prompt = True
                continue
            resp.raise_for_status()
            return resp.cookies.get_dict()
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            prompt = True
            continue


def get_latest_version_safe(uid, cookies, session=None):
    url = f"https://splunkbase.splunk.com/api/v1/app/{uid}/release/"
    sess = session or requests
    try:
        resp = sess.get(url, cookies=cookies, timeout=30)
        if resp.status_code != 200:
            logging.warning("Error retrieving app version for %s: Status code %s", uid, resp.status_code)
            return None
        data = resp.json()
        if not data or not isinstance(data, list):
            logging.warning("Unexpected version response for %s: %s", uid, type(data))
            return None
        first = data[0]
        if not isinstance(first, dict) or "name" not in first:
            logging.warning("Missing 'name' in version response for %s", uid)
            return None
        return first["name"]
    except (ValueError, json.JSONDecodeError):
        logging.warning("Invalid JSON when retrieving version for %s", uid)
        return None
    except Exception as e:
        logging.error("Network error when retrieving version for %s: %s", uid, e)
        return None
if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Download Splunkbase apps listed in Your_apps.json")
        parser.add_argument("--outdir", "-o", default=".", help="Output directory for downloaded apps")
        parser.add_argument("--dry-run", action="store_true", help="Do not download, only check for updates")
        parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
        parser.add_argument("--prompt-login", action="store_true", help="Prompt for Splunkbase login credentials interactively")
        args = parser.parse_args()

        # Configure logging
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                            format="%(asctime)s %(levelname)s: %(message)s")

        out_dir = Path(args.outdir)

        # Create a requests Session with retries
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        cookies = authenticate(session=session, prompt=args.prompt_login)

        apps_file = Path("Your_apps.json")
        if not apps_file.exists():
            raise FileNotFoundError("Your_apps.json not found")

        with apps_file.open("r", encoding="utf-8") as f:
            apps_data_from_file = json.load(f)

        downloaded_apps = []
        skipped_apps = []

        for app in apps_data_from_file:
            uid = app.get("uid")
            if uid is None:
                logging.warning("Skipping entry without uid: %s", app)
                continue

            latest_version = get_latest_version_safe(uid, cookies, session=session)
            if latest_version and latest_version != app.get("version"):
                if args.dry_run:
                    logging.info("Would download %s -> %s", uid, latest_version)
                    skipped_apps.append(f"{uid}_{app.get('version')}")
                    continue

                updated_time = download_stream(uid, latest_version, cookies, downloaded_apps, skipped_apps, out_dir=out_dir, session=session)
                if updated_time:
                    # Update file atomically
                    update_Your_apps_file_atomic(apps_data_from_file, uid, latest_version, updated_time, file_path=str(apps_file))
            else:
                skipped_apps.append(f"{uid}_{app.get('version')}")

        logging.info("Downloaded apps: %s", downloaded_apps)
        logging.info("Skipped apps: %s", skipped_apps)

    except Exception as e:
        logging.exception("An error occurred: %s", e)
