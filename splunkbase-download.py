#!/usr/bin/env python3
####################################
#### Splunkbase Download Script
#### Erstellung: 10.11.2025
#### letzte Änderung: 11.11.2025
#### Creator: Gotarr
####################################


import argparse
import json
import tempfile
import datetime
import os
import hashlib
import shutil
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from email.utils import parsedate_to_datetime
import logging
import getpass
from typing import List, Dict, Any, Tuple, Optional
import re
import sys


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


def update_Your_apps_file_atomic(apps_data, uid, new_version, updated_time, file_path="Your_apps.json", backup_keep: Optional[int] = 5):
    """Atomically update Your_apps.json by writing to a temp file and replacing the original.
    Modifies apps_data in-memory as well.
    
    Args:
        apps_data: List of app dictionaries
        uid: App UID to update
        new_version: New version string
        updated_time: New timestamp
        file_path: Path to Your_apps.json
        backup_keep: Number of backups to keep (None=use default 5, 0=no backups)
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
    
    # Create backup before updating
    if backup_keep is None:
        backup_keep = 5  # Default
    if backup_keep != 0:
        create_backup(file_path_obj, backup_keep)
    
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


def create_backup(file_path: Path, backup_keep: int = 5) -> Optional[Path]:
    """Create a timestamped backup of file_path and rotate old backups.
    
    Args:
        file_path: Path to the file to backup
        backup_keep: Number of backups to keep (0 = no backups, None = keep all)
        
    Returns:
        Path to created backup file, or None if backup was skipped/failed
    """
    if backup_keep == 0:
        logging.debug("Backups disabled (backup_keep=0)")
        return None
    
    if not file_path.exists():
        logging.debug("No file to backup: %s", file_path)
        return None
    
    # Create backup with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = file_path.parent / f"{file_path.name}.bak-{timestamp}"
    
    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        logging.info("Created backup: %s", backup_path)
        
        # Rotate old backups
        if backup_keep is not None and backup_keep > 0:
            rotate_backups(file_path, backup_keep)
        
        return backup_path
    except Exception as e:
        logging.warning("Failed to create backup: %s", e)
        return None


def rotate_backups(file_path: Path, keep_count: int) -> None:
    """Delete old backup files, keeping only the N most recent.
    
    Args:
        file_path: Original file path (backups are named file_path.bak-TIMESTAMP)
        keep_count: Number of most recent backups to keep
    """
    if keep_count <= 0:
        return
    
    # Find all backup files
    backup_pattern = f"{file_path.name}.bak-*"
    backup_files = sorted(
        file_path.parent.glob(backup_pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Newest first
    )
    
    # Delete old backups beyond keep_count
    for old_backup in backup_files[keep_count:]:
        try:
            old_backup.unlink()
            logging.debug("Deleted old backup: %s", old_backup)
        except Exception as e:
            logging.warning("Failed to delete old backup %s: %s", old_backup, e)


def atomic_write_json(file_path: Path, data: Any, backup_keep: Optional[int] = 5) -> None:
    """Atomically write JSON to file_path with UTF-8 encoding.
    
    Args:
        file_path: Path to write JSON to
        data: Data to serialize to JSON
        backup_keep: Number of backups to keep (None=use default 5, 0=no backups)
    """
    file_path = Path(file_path)
    
    # Create backup before writing
    if backup_keep is None:
        backup_keep = 5  # Default
    if backup_keep != 0:
        create_backup(file_path, backup_keep)
    
    dir_name = str(file_path.parent) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="your_apps_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            json.dump(data, tmpf, indent=4, ensure_ascii=False)
            tmpf.write("\n")
            tmpf.flush()
            os.fsync(tmpf.fileno())
        Path(tmp_path).replace(file_path)
        if os.name != "nt":
            try:
                file_path.chmod(0o644)
            except Exception:
                pass
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass
        raise


def _normalize_iso8601(ts: str) -> Tuple[bool, str]:
    """Try to normalize timestamp to ISO8601 with timezone. Returns (ok, normalized_or_original)."""
    try:
        s = ts.strip()
        # Accept trailing 'Z' by translating to +00:00 for fromisoformat
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return False, ts
        return True, dt.isoformat()
    except Exception:
        return False, ts


def _is_iso8601_with_tz(ts: str) -> bool:
    ok, _ = _normalize_iso8601(ts)
    return ok


def expected_file_path(out_dir: Path, uid: int, version: str) -> Path:
    return Path(out_dir) / f"{uid}_{version}.tgz"


def check_file_present(out_dir: Path, uid: int, version: str) -> Tuple[bool, Path]:
    p = expected_file_path(out_dir, uid, version)
    return p.exists(), p


def calculate_sha256(file_path: Path) -> Optional[str]:
    """Calculate SHA256 hash of a file.
    
    Args:
        file_path: Path to the file to hash
        
    Returns:
        Hex string of SHA256 hash, or None if file doesn't exist or error occurs
    """
    if not file_path.exists():
        return None
    
    try:
        sha256_hash = hashlib.sha256()
        with file_path.open("rb") as f:
            # Read in 64KB chunks for memory efficiency
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        logging.warning("Failed to calculate hash for %s: %s", file_path, e)
        return None


def add_hash_if_enabled(result_dict: Dict[str, Any], file_path: Path, calculate_hash: bool) -> Dict[str, Any]:
    """Add SHA256 hash to result dictionary if hash calculation is enabled and file exists.
    
    Args:
        result_dict: The result dictionary to potentially add hash to
        file_path: Path to the file to hash
        calculate_hash: Whether hash calculation is enabled (from args.hash)
        
    Returns:
        The same dictionary with 'sha256' field added if applicable
    """
    if calculate_hash:
        hash_value = calculate_sha256(file_path)
        result_dict["sha256"] = hash_value
    return result_dict


def create_eval_result(uid, current, latest, action, reason, file_present, file_path_str, file_hash=None, include_hash=False):
    """Helper to create eval result dict with optional hash field.
    
    Args:
        uid: App UID
        current: Current version
        latest: Latest version
        action: Action to take
        reason: Reason for action
        file_present: Whether file exists
        file_path_str: File path as string
        file_hash: Optional SHA256 hash
        include_hash: Whether to include hash field (from args.hash)
        
    Returns:
        Dictionary for eval_results
    """
    result = {
        "uid": uid,
        "current": current,
        "latest": latest,
        "action": action,
        "reason": reason,
        "file_present": file_present,
        "file_path": file_path_str,
    }
    if include_hash:
        result["sha256"] = file_hash
    return result


def validate_apps_data(apps_data: Any) -> Tuple[List[Dict[str, Any]], int, int]:
    """Validate structure and basic content of Your_apps.json.
    Returns (results, error_count, warning_count).
    Each result has: index, uid, issues (list of strings), status (valid|invalid|warning).
    """
    results: List[Dict[str, Any]] = []
    errors = 0
    warnings = 0

    if not isinstance(apps_data, list):
        results.append({
            "index": None,
            "uid": None,
            "issues": ["Top-level JSON must be a list"],
            "status": "invalid",
        })
        return results, 1, 0

    seen_uids: Dict[int, int] = {}
    version_re = re.compile(r"^\d+\.\d+(?:\.\d+)?(?:[.-][A-Za-z0-9]+)?$")

    for idx, app in enumerate(apps_data):
        issues: List[str] = []
        status = "valid"
        err_count_local = 0
        warn_count_local = 0
        uid = app.get("uid") if isinstance(app, dict) else None

        if not isinstance(app, dict):
            issues.append("Entry is not an object/dict")
        else:
            # Required fields
            required = ["uid", "version", "name", "appid", "updated_time"]
            missing = [k for k in required if k not in app]
            if missing:
                issues.append(f"ERR: Missing required fields: {', '.join(missing)}")
                err_count_local += 1

            # Types and content
            if "uid" in app and not isinstance(app["uid"], int):
                issues.append("ERR: uid must be an integer")
                err_count_local += 1
            if "version" in app and not isinstance(app["version"], str):
                issues.append("ERR: version must be a string")
                err_count_local += 1
            if "name" in app and not isinstance(app["name"], str):
                issues.append("ERR: name must be a string")
                err_count_local += 1
            if "appid" in app and not isinstance(app["appid"], str):
                issues.append("ERR: appid must be a string")
                err_count_local += 1
            if "updated_time" in app:
                ut = app.get("updated_time")
                if not isinstance(ut, str) or not _is_iso8601_with_tz(ut):
                    issues.append("ERR: updated_time must be ISO8601 with timezone, e.g. 2025-11-03T07:40:11+00:00")
                    err_count_local += 1

            # Content validation (empties, version shape)
            if isinstance(app.get("version"), str):
                v = app["version"].strip()
                if not v:
                    issues.append("ERR: version must not be empty")
                    err_count_local += 1
                elif not version_re.match(v):
                    issues.append("WARN: version format is unusual; expected like 1.2 or 1.2.3 or 1.2.3-rc1")
                    warn_count_local += 1
            if isinstance(app.get("name"), str) and not app["name"].strip():
                issues.append("WARN: name is empty")
                warn_count_local += 1
            if isinstance(app.get("appid"), str) and not app["appid"].strip():
                issues.append("WARN: appid is empty")
                warn_count_local += 1

            # Duplicate UID
            if isinstance(app.get("uid"), int):
                uid_val = app["uid"]
                if uid_val in seen_uids:
                    issues.append(f"ERR: duplicate uid (also in index {seen_uids[uid_val]})")
                    err_count_local += 1
                else:
                    seen_uids[uid_val] = idx

        if issues:
            if err_count_local > 0:
                status = "invalid"
                errors += err_count_local
            elif warn_count_local > 0:
                status = "warning"
                warnings += warn_count_local
        results.append({
            "index": idx,
            "uid": uid,
            "issues": issues,
            "status": status,
        })

    return results, errors, warnings


def format_apps_for_readability(apps_data: List[Dict[str, Any]], sort_by: str = "name") -> List[Dict[str, Any]]:
    """Normalize and reorder entries for readability, and return a new sorted list.
    - Key order: name, uid, appid, updated_time, version, (extras...)
    - Trim string fields
    - Normalize updated_time to ISO8601 with timezone if possible
    - Sort by name (case-insensitive) or uid
    """
    ordered: List[Dict[str, Any]] = []
    key_order = ["name", "uid", "appid", "updated_time", "version"]
    for app in apps_data:
        if not isinstance(app, dict):
            ordered.append(app)
            continue
        normalized: Dict[str, Any] = {}
        for k in app.keys():
            val = app[k]
            if isinstance(val, str):
                val = val.strip()
            normalized[k] = val
        # normalize timestamp
        if isinstance(normalized.get("updated_time"), str):
            ok, norm = _normalize_iso8601(normalized["updated_time"])
            if ok:
                normalized["updated_time"] = norm
        base = {k: normalized.get(k) for k in key_order if k in normalized}
        extras = {k: normalized[k] for k in normalized.keys() if k not in key_order}
        for k in sorted(extras.keys()):
            base[k] = extras[k]
        ordered.append(base)

    if sort_by == "uid":
        try:
            ordered.sort(key=lambda x: (int(x.get("uid", 0)), str(x.get("name", "")).lower()))
        except Exception:
            ordered.sort(key=lambda x: str(x.get("name", "")).lower())
    else:  # name
        ordered.sort(key=lambda x: (str(x.get("name", "")).lower(), int(x.get("uid", 0)) if isinstance(x.get("uid"), int) else 0))
    return ordered


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


def fetch_splunkbase_catalog(cookies, session=None, cache_file="splunkbase_catalog.json", max_age_hours=24):
    """Fetch complete Splunkbase app catalog and cache it locally.
    Returns dict: {normalized_name: {"uid": int, "title": str, "appid": str}, ...}
    Uses cache if younger than max_age_hours.
    """
    cache_path = Path(cache_file)
    sess = session or requests
    
    # Check cache freshness
    if cache_path.exists():
        try:
            stat = cache_path.stat()
            age_hours = (datetime.datetime.now().timestamp() - stat.st_mtime) / 3600
            if age_hours < max_age_hours:
                with cache_path.open("r", encoding="utf-8") as f:
                    catalog = json.load(f)
                logging.info("Using cached Splunkbase catalog (%.1f hours old, %d apps)", age_hours, len(catalog))
                return catalog
        except Exception as e:
            logging.warning("Could not read catalog cache: %s", e)
    
    # Fetch from API
    logging.info("Fetching Splunkbase app catalog (this may take a moment)...")
    url = "https://splunkbase.splunk.com/api/v1/app/"
    catalog = {}
    
    try:
        # Try without pagination first - get all available
        resp = sess.get(url, cookies=cookies, timeout=60)
        
        if resp.status_code != 200:
            logging.error("Failed to fetch catalog: HTTP %s", resp.status_code)
            return {}
        
        data = resp.json()
        
        # Handle both list response and paginated response
        apps_list = []
        if isinstance(data, dict) and "results" in data:
            apps_list = data.get("results", [])
        elif isinstance(data, list):
            apps_list = data
        
        if not apps_list:
            logging.warning("Empty catalog response from Splunkbase API")
            return {}
        
        for app in apps_list:
            if not isinstance(app, dict):
                continue
            
            uid = app.get("uid")
            title = app.get("title", "").strip()
            appid = app.get("appid", "").strip()
            
            if uid and title:
                # Normalize name for fuzzy matching
                normalized = title.lower().replace("-", "").replace("_", "").replace(" ", "")
                catalog[normalized] = {
                    "uid": int(uid),
                    "title": title,
                    "appid": appid,
                }
        
        logging.info("Fetched %d apps from Splunkbase", len(catalog))
        
        # Write cache
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2, ensure_ascii=False)
            logging.info("Saved catalog cache to %s", cache_file)
        except Exception as e:
            logging.warning("Could not write catalog cache: %s", e)
        
        return catalog
        
    except Exception as e:
        logging.error("Error fetching Splunkbase catalog: %s", e)
        return {}


def get_app_details(uid, cookies, session=None):
    """Retrieve app metadata from Splunkbase API.
    Returns dict with name, appid, uid, version (latest), updated_time or None on error.
    """
    url = f"https://splunkbase.splunk.com/api/v1/app/{uid}/"
    sess = session or requests
    try:
        resp = sess.get(url, cookies=cookies, timeout=30)
        if resp.status_code != 200:
            logging.error("Failed to retrieve app details for uid=%s: HTTP %s", uid, resp.status_code)
            return None
        app_data = resp.json()
        if not isinstance(app_data, dict):
            logging.error("Invalid app details response for uid=%s", uid)
            return None
        
        name = app_data.get("title", "").strip()
        appid = app_data.get("appid", "").strip()
        if not name or not appid:
            logging.error("App uid=%s missing required fields (name/appid)", uid)
            return None
        
        # Get latest version
        latest_version = get_latest_version_safe(uid, cookies, session=sess)
        if not latest_version:
            logging.error("Could not retrieve latest version for uid=%s", uid)
            return None
        
        # Use current UTC as updated_time
        updated_time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        
        return {
            "name": name,
            "uid": int(uid),
            "appid": appid,
            "updated_time": updated_time,
            "version": latest_version,
        }
    except Exception as e:
        logging.error("Error retrieving app details for uid=%s: %s", uid, e)
        return None


def load_app_name_mapping():
    """Load app name to UID mapping from config file.
    Returns dict with normalized app names as keys and UIDs as values.
    """
    mapping_file = Path("app_name_mapping.conf")
    mapping = {}
    
    if not mapping_file.exists():
        return mapping
    
    try:
        with mapping_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    name, uid_str = line.split("=", 1)
                    name = name.strip().lower().replace("-", "").replace("_", "")
                    try:
                        mapping[name] = int(uid_str.strip())
                    except ValueError:
                        continue
    except Exception as e:
        logging.warning("Could not load app_name_mapping.conf: %s", e)
    
    return mapping


def search_app_by_name(app_name, cookies, session=None, catalog=None):
    """Search Splunkbase for an app by name and return UID if found.
    Returns dict with uid, name, appid, version or None if not found.
    Uses catalog cache if provided for fast lookup.
    """
    # First try local mapping file
    mapping = load_app_name_mapping()
    normalized = app_name.lower().replace("-", "").replace("_", "").replace(" ", "")
    
    if normalized in mapping:
        uid = mapping[normalized]
        logging.info("Found UID %s for '%s' in local mapping", uid, app_name)
        details = get_app_details(uid, cookies, session=session)
        if details:
            return details
    
    # Second: try catalog cache
    if catalog:
        # Try exact normalized match
        if normalized in catalog:
            entry = catalog[normalized]
            uid = entry["uid"]
            logging.info("Found UID %s for '%s' in catalog cache", uid, app_name)
            details = get_app_details(uid, cookies, session=session)
            if details:
                return details
        
        # Try fuzzy match (substring search)
        for cat_name, entry in catalog.items():
            if normalized in cat_name or cat_name in normalized:
                uid = entry["uid"]
                logging.info("Found UID %s for '%s' via fuzzy match in catalog ('%s')", uid, app_name, entry["title"])
                details = get_app_details(uid, cookies, session=session)
                if details:
                    return details
    
    # Fallback: Try direct API search (may not work for all Splunkbase instances)
    url = "https://splunkbase.splunk.com/api/v1/app/"
    sess = session or requests
    
    try:
        # Search with query parameter
        params = {"search": app_name, "limit": 10}
        resp = sess.get(url, params=params, cookies=cookies, timeout=30)
        if resp.status_code != 200:
            logging.warning("Search failed for '%s': HTTP %s", app_name, resp.status_code)
            return None
        
        results = resp.json()
        if not isinstance(results, list) or len(results) == 0:
            logging.warning("No results found for '%s'", app_name)
            return None
        
        # Normalize app_name for comparison (lowercase, replace spaces/dashes)
        normalized_query = app_name.lower().replace("-", " ").replace("_", " ")
        
        # Try to find exact or close match
        for app in results:
            if not isinstance(app, dict):
                continue
            
            title = app.get("title", "").lower().replace("-", " ").replace("_", " ")
            appid = app.get("appid", "").lower().replace("-", " ").replace("_", " ")
            
            # Check if query matches title or appid closely
            if normalized_query in title or title in normalized_query or normalized_query in appid:
                uid = app.get("uid")
                if uid:
                    # Get latest version
                    latest_version = get_latest_version_safe(uid, cookies, session=sess)
                    return {
                        "uid": int(uid),
                        "name": app.get("title", "").strip(),
                        "appid": app.get("appid", "").strip(),
                        "version": latest_version if latest_version else "unknown",
                    }
        
        # If no close match, return first result
        first = results[0]
        uid = first.get("uid")
        if uid:
            latest_version = get_latest_version_safe(uid, cookies, session=sess)
            return {
                "uid": int(uid),
                "name": first.get("title", "").strip(),
                "appid": first.get("appid", "").strip(),
                "version": latest_version if latest_version else "unknown",
            }
        
        return None
        
    except Exception as e:
        logging.error("Error searching for '%s': %s", app_name, e)
        return None


def extract_app_info_from_filename(filename):
    """Extract app name and version from Splunkbase TGZ filename.
    Expected formats:
    - app-name_version.tgz
    - app-name_version_something.tgz
    Returns (app_name, version) tuple or (None, None) if invalid.
    """
    if not filename.endswith(".tgz"):
        return None, None
    
    # Remove .tgz extension
    base = filename[:-4]
    
    # Split by underscore - last part before .tgz should be version or part of it
    parts = base.rsplit("_", 1)
    if len(parts) == 2:
        app_name = parts[0]
        version = parts[1]
        return app_name, version
    
    return None, None


def extract_uids_from_filenames(filenames):
    """Extract UIDs from Splunkbase TGZ filenames.
    Expected format: app-name_UID.tgz or appname_UID.tgz
    Returns set of unique UIDs.
    """
    uids = set()
    pattern = re.compile(r'_(\d+)\.tgz$')
    for fname in filenames:
        match = pattern.search(fname)
        if match:
            uids.add(int(match.group(1)))
    return uids


def onboard_apps_from_files(file_source, session=None):
    """Read filenames from a file or directory and search Splunkbase by app name to populate Your_apps.json.
    file_source can be:
    - Path to a text file with one filename per line
    - Path to a directory containing .tgz files
    """
    source_path = Path(file_source)
    filenames = []
    
    if source_path.is_file():
        # Read filenames from text file
        try:
            with source_path.open("r", encoding="utf-8") as f:
                filenames = [line.strip() for line in f if line.strip()]
            print(f"[OK] Read {len(filenames)} filename(s) from {source_path}")
        except Exception as e:
            logging.error("Failed to read file %s: %s", source_path, e)
            print(f"[X] Error reading {source_path}: {e}")
            return
    elif source_path.is_dir():
        # Scan directory for .tgz files
        try:
            filenames = [f.name for f in source_path.glob("*.tgz")]
            print(f"[OK] Found {len(filenames)} .tgz file(s) in {source_path}")
        except Exception as e:
            logging.error("Failed to scan directory %s: %s", source_path, e)
            print(f"[X] Error scanning {source_path}: {e}")
            return
    else:
        print(f"[X] {source_path} is neither a file nor a directory")
        return
    
    if not filenames:
        print("No filenames to process.")
        return
    
    # Parse filenames to extract app names
    apps_to_search = []
    for fname in filenames:
        app_name, version = extract_app_info_from_filename(fname)
        if app_name:
            apps_to_search.append((fname, app_name, version))
        else:
            print(f"[!] Could not parse filename: {fname}")
    
    if not apps_to_search:
        print("[X] No valid filenames to process (expected format: app-name_version.tgz)")
        return
    
    print(f"[OK] Parsed {len(apps_to_search)} app filename(s)")
    
    # Check against existing
    apps_file = Path("Your_apps.json")
    existing_apps = []
    if apps_file.exists():
        try:
            with apps_file.open("r", encoding="utf-8") as f:
                existing_apps = json.load(f)
            if not isinstance(existing_apps, list):
                existing_apps = []
        except Exception:
            existing_apps = []
    
    existing_uids = {app.get("uid") for app in existing_apps if isinstance(app, dict) and "uid" in app}
    existing_names = {app.get("name", "").lower() for app in existing_apps if isinstance(app, dict)}
    
    # Authenticate and search
    cookies = authenticate(session=session, prompt=False)
    
    # Fetch catalog for name → UID lookups
    catalog = fetch_splunkbase_catalog(cookies, session=session)
    
    print(f"\nSearching Splunkbase for {len(apps_to_search)} app(s)...\n")
    
    new_apps = []
    added_uids = set()  # Track UIDs added in this session to avoid duplicates
    for fname, app_name, version in apps_to_search:
        print(f"  '{app_name}' (from {fname})... ", end="", flush=True)
        
        result = search_app_by_name(app_name, cookies, session=session, catalog=catalog)
        if result:
            uid = result.get("uid")
            name = result.get("name")
            
            if uid in existing_uids:
                print(f"[!] Already exists (UID {uid})")
                continue
            
            if uid in added_uids:
                print(f"[!] Duplicate in this batch (UID {uid})")
                continue
            
            # Get latest version and metadata
            latest_version = get_latest_version_safe(uid, cookies, session=session)
            if not latest_version:
                print(f"[X] Found UID {uid} but no version available")
                continue
            
            updated_time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
            
            new_apps.append({
                "name": name,
                "uid": uid,
                "appid": result.get("appid"),
                "updated_time": updated_time,
                "version": latest_version,
            })
            added_uids.add(uid)
            print(f"[OK] {name} (UID {uid}, v{latest_version})")
        else:
            print("[X] Not found")
    
    if not new_apps:
        print("\n[X] No new apps to add. Your_apps.json not modified.")
        return
    
    # Merge and write
    combined = existing_apps + new_apps
    formatted = format_apps_for_readability(combined, sort_by="name")
    
    try:
        atomic_write_json(apps_file, formatted, backup_keep=args.backup_keep)
        print(f"\n[OK] Successfully added {len(new_apps)} app(s) to Your_apps.json")
        print("\nAdded apps:")
        for app in new_apps:
            print(f"  - {app['name']} (UID {app['uid']}, v{app['version']})")
    except Exception as e:
        logging.error("Failed to write Your_apps.json: %s", e)
        print(f"\n[X] Error writing Your_apps.json: {e}")



def onboard_apps_interactive(session=None):
    """Interactive wizard to add apps to Your_apps.json by UID.
    Prompts user for UIDs, fetches metadata from Splunkbase, and updates Your_apps.json atomically.
    """
    apps_file = Path("Your_apps.json")
    existing_apps = []
    if apps_file.exists():
        try:
            with apps_file.open("r", encoding="utf-8") as f:
                existing_apps = json.load(f)
            if not isinstance(existing_apps, list):
                logging.error("Your_apps.json is not a list; creating new file")
                existing_apps = []
        except Exception as e:
            logging.warning("Could not read existing Your_apps.json: %s; starting fresh", e)
            existing_apps = []
    
    existing_uids = {app.get("uid") for app in existing_apps if isinstance(app, dict) and "uid" in app}
    
    print("\n=== Splunkbase App Onboarding ===")
    print("Enter Splunkbase app UIDs (comma-separated or one per line).")
    print("Example UIDs: 742 (Windows TA), 1621 (CIM), 833 (Unix/Linux TA)")
    print("Press Ctrl+C or enter an empty line to finish.\n")
    
    cookies = authenticate(session=session, prompt=False)
    
    uids_to_add = []
    while True:
        try:
            line = input("App UID(s): ").strip()
            if not line:
                break
            # Parse comma-separated or space-separated UIDs
            parts = re.split(r'[,\s]+', line)
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                try:
                    uid = int(p)
                    if uid in existing_uids:
                        print(f"  [!] UID {uid} already exists in Your_apps.json, skipping.")
                    elif uid in uids_to_add:
                        print(f"  [!] UID {uid} already queued, skipping duplicate.")
                    else:
                        uids_to_add.append(uid)
                        print(f"  [OK] Queued UID {uid}")
                except ValueError:
                    print(f"  [X] Invalid UID: {p}")
        except (EOFError, KeyboardInterrupt):
            print("\nOnboarding cancelled.")
            return
    
    if not uids_to_add:
        print("No new apps to add.")
        return
    
    print(f"\nFetching details for {len(uids_to_add)} app(s) from Splunkbase...")
    new_apps = []
    for uid in uids_to_add:
        print(f"  Retrieving uid={uid}...", end=" ")
        details = get_app_details(uid, cookies, session=session)
        if details:
            new_apps.append(details)
            print(f"[OK] {details['name']} v{details['version']}")
        else:
            print("[X] Failed")
    
    if not new_apps:
        print("No valid apps retrieved. Your_apps.json not modified.")
        return
    
    # Merge with existing and format
    combined = existing_apps + new_apps
    formatted = format_apps_for_readability(combined, sort_by="name")
    
    # Atomic write
    try:
        atomic_write_json(apps_file, formatted, backup_keep=args.backup_keep)
        print(f"\n[OK] Successfully added {len(new_apps)} app(s) to Your_apps.json")
        print("Added apps:")
        for app in new_apps:
            print(f"  - {app['name']} (UID {app['uid']}, v{app['version']})")
    except Exception as e:
        logging.error("Failed to write Your_apps.json: %s", e)
        print(f"[X] Error writing Your_apps.json: {e}")


def parse_uid_list(uid_string: str) -> set:
    """Parse a comma-separated string of UIDs into a set of integers.
    
    Args:
        uid_string: Comma-separated UID string (e.g., "742,833,1621")
        
    Returns:
        Set of integer UIDs
        
    Raises:
        ValueError: If any UID is not a valid integer
    """
    if not uid_string or not uid_string.strip():
        return set()
    
    uids = set()
    for part in uid_string.split(','):
        part = part.strip()
        if part:
            try:
                uids.add(int(part))
            except ValueError:
                raise ValueError(f"Invalid UID '{part}' - must be an integer")
    return uids


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Download Splunkbase apps listed in Your_apps.json")
        parser.add_argument("--outdir", "-o", default=".", help="Output directory for downloaded apps")
        parser.add_argument("--dry-run", action="store_true", help="Do not download, only check for updates")
        parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
        parser.add_argument("--prompt-login", action="store_true", help="Prompt for Splunkbase login credentials interactively")
        parser.add_argument("--summary", action="store_true", help="Print a concise summary table of update decisions")
        parser.add_argument("--report-file", help="Write a JSON report with per-app decisions (uid, current, latest, action, reason)")
        parser.add_argument("--validate", action="store_true", help="Validate Your_apps.json (schema, types, duplicates); no downloads")
        parser.add_argument("--format-json", action="store_true", help="Rewrite Your_apps.json with consistent formatting (pretty, key order)")
        parser.add_argument("--fix-missing", action="store_true", help="If an app is up-to-date but its declared file is missing, re-download it (or plan it in dry-run)")
        parser.add_argument("--fix-missing-upgrade", action="store_true", help="Reserved for future: no effect now; upgrades already occur when newer versions exist")
        parser.add_argument("--only", metavar="UIDS", help="Process only the specified UIDs (comma-separated, e.g., --only 742,833,1621)")
        parser.add_argument("--exclude", metavar="UIDS", help="Exclude the specified UIDs from processing (comma-separated, e.g., --exclude 1809)")
        parser.add_argument("--hash", action="store_true", help="Calculate SHA256 hash for existing .tgz files and include in report")
        parser.add_argument("--backup-keep", type=int, metavar="N", help="Number of backup files to retain (default: 5); set to 0 to disable backups")
        parser.add_argument("--fail-on-errors", action="store_true", help="Exit with non-zero status if errors or inconsistencies are found (useful for CI/CD)")
        parser.add_argument("--onboard", action="store_true", help="Interactive mode: add new apps to Your_apps.json by UID; fetches metadata from Splunkbase")
        parser.add_argument("--from-files", metavar="PATH", help="With --onboard: extract UIDs from .tgz filenames in a directory or text file (one filename per line)")
        args = parser.parse_args()

        # Set default for backup_keep if not specified
        if args.backup_keep is None:
            args.backup_keep = 5  # Default: keep 5 backups

        # Configure logging
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                            format="%(asctime)s %(levelname)s: %(message)s")

        # Onboarding mode: interactive wizard to add apps
        if args.onboard:
            session = requests.Session()
            retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
            adapter = HTTPAdapter(max_retries=retries)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            
            if args.from_files:
                onboard_apps_from_files(args.from_files, session=session)
            else:
                onboard_apps_interactive(session=session)
            sys.exit(0)

        apps_file = Path("Your_apps.json")
        if not apps_file.exists():
            raise FileNotFoundError("Your_apps.json not found")

        with apps_file.open("r", encoding="utf-8") as f:
            apps_data_from_file = json.load(f)

        # Phase 1 + Phase 2 (validate + file mismatch in validate mode)
        if args.validate:
            # Parse UID filters (same as normal mode)
            only_uids = parse_uid_list(args.only) if args.only else None
            exclude_uids = parse_uid_list(args.exclude) if args.exclude else None
            
            if only_uids:
                logging.info("Validating only UIDs: %s", sorted(only_uids))
            if exclude_uids:
                logging.info("Excluding UIDs from validation: %s", sorted(exclude_uids))
            
            results, error_count, warning_count = validate_apps_data(apps_data_from_file)
            out_dir = Path(args.outdir)
            eval_results: List[Dict[str, Any]] = []
            missing_files = 0
            for r in results:
                uid_val = r.get("uid")
                
                # Apply UID filters in validate mode
                if only_uids is not None and uid_val not in only_uids:
                    continue
                if exclude_uids is not None and uid_val in exclude_uids:
                    continue
                
                file_present = None
                file_path_str = None
                declared_version = None
                idx = r.get("index")
                if isinstance(idx, int) and 0 <= idx < len(apps_data_from_file):
                    declared_version = apps_data_from_file[idx].get("version")
                if isinstance(uid_val, int) and isinstance(declared_version, str):
                    fp, p = check_file_present(out_dir, uid_val, declared_version)
                    file_present = fp
                    file_path_str = str(p)
                    if not fp:
                        missing_files += 1
                eval_results.append({
                    "uid": uid_val,
                    "index": r.get("index"),
                    "action": "valid" if r.get("status") == "valid" else ("warning" if r.get("status") == "warning" else "invalid"),
                    "reason": "; ".join(r.get("issues", [])) if r.get("issues") else "",
                    "file_present": file_present,
                    "file_path": file_path_str,
                    "declared_version": declared_version,
                })

            if args.summary:
                def _fmt(s, w):
                    s = "" if s is None else str(s)
                    return s[:w].ljust(w)
                headers = [("IDX", 5), ("UID", 8), ("Status", 8), ("File", 6), ("Version", 12), ("Issues", 45)]
                line = " ".join(_fmt(h, w) for h, w in headers)
                sep = "-" * len(line)
                print(sep)
                print(line)
                print(sep)
                for row in eval_results:
                    print(" ".join([
                        _fmt(row.get("index"), 5),
                        _fmt(row.get("uid"), 8),
                        _fmt(row.get("action"), 8),
                        _fmt("yes" if row.get("file_present") else "no", 6),
                        _fmt(row.get("declared_version"), 12),
                        _fmt(row.get("reason"), 45),
                    ]))
                print(sep)
                print(f"Errors: {error_count} | Warnings: {warning_count} | Missing files: {missing_files} | Total: {len(eval_results)}")

            if args.report_file:
                try:
                    report_path = Path(args.report_file)
                    json_report = {
                        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                        "mode": "validate",
                        "summary": {"errors": error_count, "warnings": warning_count, "missing_files": missing_files, "total": len(eval_results)},
                        "results": eval_results,
                    }
                    with report_path.open("w", encoding="utf-8") as rf:
                        json.dump(json_report, rf, indent=2, ensure_ascii=False)
                    logging.info("Wrote validation report to %s", report_path)
                except Exception as e:
                    logging.error("Failed to write validation report: %s", e)

            if args.format_json:
                try:
                    formatted = format_apps_for_readability(apps_data_from_file)
                    atomic_write_json(apps_file, formatted, backup_keep=args.backup_keep)
                    logging.info("Reformatted Your_apps.json for readability")
                except Exception as e:
                    logging.error("Failed to format Your_apps.json: %s", e)

            if error_count > 0:
                sys.exit(1)
            else:
                sys.exit(0)

        # Normal/Download flow starts here
        out_dir = Path(args.outdir)

        # Create a requests Session with retries
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        cookies = authenticate(session=session, prompt=args.prompt_login)

        # Parse UID filters
        only_uids = parse_uid_list(args.only) if args.only else None
        exclude_uids = parse_uid_list(args.exclude) if args.exclude else None
        
        if only_uids:
            logging.info("Processing only UIDs: %s", sorted(only_uids))
        if exclude_uids:
            logging.info("Excluding UIDs: %s", sorted(exclude_uids))

        downloaded_apps: List[str] = []
        skipped_apps: List[str] = []
        eval_results: List[Dict[str, Any]] = []
        total_apps = 0
        to_update = 0
        up_to_date = 0
        errors = 0
        missing_files = 0

        for app in apps_data_from_file:
            uid = app.get("uid")
            if uid is None:
                logging.warning("Skipping entry without uid: %s", app)
                continue

            # Apply UID filters
            if only_uids is not None and uid not in only_uids:
                logging.debug("Skipping uid=%s (not in --only list)", uid)
                continue
            if exclude_uids is not None and uid in exclude_uids:
                logging.debug("Skipping uid=%s (in --exclude list)", uid)
                continue

            total_apps += 1
            current_version = app.get("version")
            # Phase 2: check for existing file of declared current version
            file_present = None
            file_path_str = None
            file_hash = None
            if isinstance(uid, int) and isinstance(current_version, str):
                fp, p = check_file_present(Path(args.outdir), uid, current_version)
                file_present = fp
                file_path_str = str(p)
                if not fp:
                    missing_files += 1
                    logging.warning("Declared file missing: uid=%s version=%s expected=%s", uid, current_version, p)
                elif args.hash:
                    # Calculate hash only if file exists and --hash is enabled
                    file_hash = calculate_sha256(p)

            latest_version = get_latest_version_safe(uid, cookies, session=session)
            if not latest_version:
                logging.warning("Could not retrieve latest version for uid=%s (current=%s)", uid, current_version)
                eval_results.append(create_eval_result(
                    uid, current_version, None, "error", "latest version not available",
                    file_present, file_path_str, file_hash, args.hash
                ))
                errors += 1
                skipped_apps.append(f"{uid}_{current_version}")
                continue

            if latest_version != current_version:
                logging.info("Update available: uid=%s %s -> %s", uid, current_version, latest_version)
                to_update += 1
                if args.dry_run:
                    logging.info("Dry-run: would download uid=%s version %s", uid, latest_version)
                    skipped_apps.append(f"{uid}_{current_version}")
                    eval_results.append(create_eval_result(
                        uid, current_version, latest_version, "plan-update", "dry-run",
                        file_present, file_path_str, file_hash, args.hash
                    ))
                    continue

                updated_time = download_stream(uid, latest_version, cookies, downloaded_apps, skipped_apps, out_dir=out_dir, session=session)
                if updated_time:
                    # Update file atomically
                    update_Your_apps_file_atomic(apps_data_from_file, uid, latest_version, updated_time, file_path=str(apps_file), backup_keep=args.backup_keep)
                    # After download, calculate hash of new file if --hash enabled
                    new_file_path = expected_file_path(Path(args.outdir), uid, latest_version)
                    new_file_hash = calculate_sha256(new_file_path) if args.hash else None
                    eval_results.append(create_eval_result(
                        uid, current_version, latest_version, "updated", "downloaded and file updated",
                        True, str(new_file_path), new_file_hash, args.hash
                    ))
                else:
                    logging.error("Failed to download/update uid=%s to version %s", uid, latest_version)
                    errors += 1
                    eval_results.append(create_eval_result(
                        uid, current_version, latest_version, "error", "download failed",
                        file_present, file_path_str, file_hash, args.hash
                    ))
            else:
                # Up-to-date relative to Splunkbase
                if (file_present is False) and args.fix_missing:
                    # Declared version is latest, but file is missing: re-download
                    if args.dry_run:
                        logging.info("Dry-run: would re-download missing file for uid=%s version=%s", uid, current_version)
                        skipped_apps.append(f"{uid}_{current_version}")
                        eval_results.append(create_eval_result(
                            uid, current_version, latest_version, "plan-redownload", "missing file",
                            False, file_path_str, None, args.hash
                        ))
                    else:
                        updated_time = download_stream(uid, current_version, cookies, downloaded_apps, skipped_apps, out_dir=out_dir, session=session)
                        if updated_time:
                            # Touch updated_time for the same version to reflect fresh download
                            update_Your_apps_file_atomic(apps_data_from_file, uid, current_version, updated_time, file_path=str(apps_file), backup_keep=args.backup_keep)
                            redownload_path = expected_file_path(Path(args.outdir), uid, current_version)
                            redownload_hash = calculate_sha256(redownload_path) if args.hash else None
                            eval_results.append(create_eval_result(
                                uid, current_version, latest_version, "redownloaded", "declared file was missing",
                                True, str(redownload_path), redownload_hash, args.hash
                            ))
                        else:
                            logging.error("Failed to re-download missing file for uid=%s version=%s", uid, current_version)
                            errors += 1
                            eval_results.append(create_eval_result(
                                uid, current_version, latest_version, "error", "redownload failed",
                                False, file_path_str, None, args.hash
                            ))
                else:
                    logging.info("Up-to-date: uid=%s version=%s", uid, current_version)
                    up_to_date += 1
                    skipped_apps.append(f"{uid}_{current_version}")
                    eval_results.append(create_eval_result(
                        uid, current_version, latest_version, "skip", "already up-to-date",
                        file_present, file_path_str, file_hash, args.hash
                    ))

        # Summary logging
        logging.info("Summary: total=%d, to_update=%d, up_to_date=%d, errors=%d", total_apps, to_update, up_to_date, errors)
        logging.info("Downloaded apps: %s", downloaded_apps)
        logging.info("Skipped apps: %s", skipped_apps)
        # Mismatch info (Phase 2) already collected per entry; could aggregate here later

        # Optional summary table
        if args.summary:
            def _fmt(s, w):
                s = "" if s is None else str(s)
                return s[:w].ljust(w)
            headers = [
                ("UID", 8),
                ("Current", 12),
                ("Latest", 12),
                ("Action", 12),
                ("Reason", 30),
                ("File", 6),
            ]
            line = " ".join(_fmt(h, w) for h, w in headers)
            sep = "-" * len(line)
            print(sep)
            print(line)
            print(sep)
            for row in eval_results:
                print(" ".join([
                    _fmt(row.get("uid"), 8),
                    _fmt(row.get("current"), 12),
                    _fmt(row.get("latest"), 12),
                    _fmt(row.get("action"), 12),
                    _fmt(row.get("reason"), 30),
                    _fmt("yes" if row.get("file_present") else "no", 6),
                ]))
            print(sep)
            print(f"Total: {total_apps} | To update: {to_update} | Up-to-date: {up_to_date} | Errors: {errors} | Missing files: {missing_files}")

        # Optional JSON report
        if args.report_file:
            try:
                report_path = Path(args.report_file)
                with report_path.open("w", encoding="utf-8") as rf:
                    json.dump({
                        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                        "summary": {
                            "total": total_apps,
                            "to_update": to_update,
                            "up_to_date": up_to_date,
                            "errors": errors,
                            "missing_files": missing_files,
                        },
                        "results": eval_results,
                    }, rf, indent=2, ensure_ascii=False)
                logging.info("Wrote report to %s", report_path)
            except Exception as e:
                logging.error("Failed to write report file: %s", e)

        # Exit with error code if --fail-on-errors is set and errors occurred
        if args.fail_on_errors and errors > 0:
            logging.error(f"Exiting with error code 1 due to {errors} error(s)")
            sys.exit(1)

    except Exception as e:
        logging.exception("An error occurred: %s", e)
        # Exit with error code if --fail-on-errors is set
        if hasattr(args, 'fail_on_errors') and args.fail_on_errors:
            sys.exit(1)
