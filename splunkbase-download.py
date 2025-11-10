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
from typing import List, Dict, Any, Tuple
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


def atomic_write_json(file_path: Path, data: Any) -> None:
    """Atomically write JSON to file_path with UTF-8 encoding."""
    file_path = Path(file_path)
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
        args = parser.parse_args()

        # Configure logging
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                            format="%(asctime)s %(levelname)s: %(message)s")

        apps_file = Path("Your_apps.json")
        if not apps_file.exists():
            raise FileNotFoundError("Your_apps.json not found")

        with apps_file.open("r", encoding="utf-8") as f:
            apps_data_from_file = json.load(f)

        # Phase 1 + Phase 2 (validate + file mismatch in validate mode)
        if args.validate:
            results, error_count, warning_count = validate_apps_data(apps_data_from_file)
            out_dir = Path(args.outdir)
            eval_results: List[Dict[str, Any]] = []
            missing_files = 0
            for r in results:
                uid_val = r.get("uid")
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
                    atomic_write_json(apps_file, formatted)
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

            total_apps += 1
            current_version = app.get("version")
            # Phase 2: check for existing file of declared current version
            file_present = None
            file_path_str = None
            if isinstance(uid, int) and isinstance(current_version, str):
                fp, p = check_file_present(Path(args.outdir), uid, current_version)
                file_present = fp
                file_path_str = str(p)
                if not fp:
                    missing_files += 1
                    logging.warning("Declared file missing: uid=%s version=%s expected=%s", uid, current_version, p)

            latest_version = get_latest_version_safe(uid, cookies, session=session)
            if not latest_version:
                logging.warning("Could not retrieve latest version for uid=%s (current=%s)", uid, current_version)
                eval_results.append({
                    "uid": uid,
                    "current": current_version,
                    "latest": None,
                    "action": "error",
                    "reason": "latest version not available",
                    "file_present": file_present,
                    "file_path": file_path_str,
                })
                errors += 1
                skipped_apps.append(f"{uid}_{current_version}")
                continue

            if latest_version != current_version:
                logging.info("Update available: uid=%s %s -> %s", uid, current_version, latest_version)
                to_update += 1
                if args.dry_run:
                    logging.info("Dry-run: would download uid=%s version %s", uid, latest_version)
                    skipped_apps.append(f"{uid}_{current_version}")
                    eval_results.append({
                        "uid": uid,
                        "current": current_version,
                        "latest": latest_version,
                        "action": "plan-update",
                        "reason": "dry-run",
                        "file_present": file_present,
                        "file_path": file_path_str,
                    })
                    continue

                updated_time = download_stream(uid, latest_version, cookies, downloaded_apps, skipped_apps, out_dir=out_dir, session=session)
                if updated_time:
                    # Update file atomically
                    update_Your_apps_file_atomic(apps_data_from_file, uid, latest_version, updated_time, file_path=str(apps_file))
                    eval_results.append({
                        "uid": uid,
                        "current": current_version,
                        "latest": latest_version,
                        "action": "updated",
                        "reason": "downloaded and file updated",
                        "file_present": True,
                        "file_path": str(expected_file_path(Path(args.outdir), uid, latest_version)),
                    })
                else:
                    logging.error("Failed to download/update uid=%s to version %s", uid, latest_version)
                    errors += 1
                    eval_results.append({
                        "uid": uid,
                        "current": current_version,
                        "latest": latest_version,
                        "action": "error",
                        "reason": "download failed",
                        "file_present": file_present,
                        "file_path": file_path_str,
                    })
            else:
                # Up-to-date relative to Splunkbase
                if (file_present is False) and args.fix_missing:
                    # Declared version is latest, but file is missing: re-download
                    if args.dry_run:
                        logging.info("Dry-run: would re-download missing file for uid=%s version=%s", uid, current_version)
                        skipped_apps.append(f"{uid}_{current_version}")
                        eval_results.append({
                            "uid": uid,
                            "current": current_version,
                            "latest": latest_version,
                            "action": "plan-redownload",
                            "reason": "missing file",
                            "file_present": False,
                            "file_path": file_path_str,
                        })
                    else:
                        updated_time = download_stream(uid, current_version, cookies, downloaded_apps, skipped_apps, out_dir=out_dir, session=session)
                        if updated_time:
                            # Touch updated_time for the same version to reflect fresh download
                            update_Your_apps_file_atomic(apps_data_from_file, uid, current_version, updated_time, file_path=str(apps_file))
                            eval_results.append({
                                "uid": uid,
                                "current": current_version,
                                "latest": latest_version,
                                "action": "redownloaded",
                                "reason": "declared file was missing",
                                "file_present": True,
                                "file_path": str(expected_file_path(Path(args.outdir), uid, current_version)),
                            })
                        else:
                            logging.error("Failed to re-download missing file for uid=%s version=%s", uid, current_version)
                            errors += 1
                            eval_results.append({
                                "uid": uid,
                                "current": current_version,
                                "latest": latest_version,
                                "action": "error",
                                "reason": "redownload failed",
                                "file_present": False,
                                "file_path": file_path_str,
                            })
                else:
                    logging.info("Up-to-date: uid=%s version=%s", uid, current_version)
                    up_to_date += 1
                    skipped_apps.append(f"{uid}_{current_version}")
                    eval_results.append({
                        "uid": uid,
                        "current": current_version,
                        "latest": latest_version,
                        "action": "skip",
                        "reason": "already up-to-date",
                        "file_present": file_present,
                        "file_path": file_path_str,
                    })

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

    except Exception as e:
        logging.exception("An error occurred: %s", e)
