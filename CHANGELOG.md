# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] - 2025-11-11

### Added
- Automatic download directory detection: when `--outdir` is not specified, the script reads the last "Output Directory" from `download.log` and uses it automatically. A clear info message is shown: `[INFO] Using last download directory from log: C:\...\downloads`.
- Download session logging: each run appends to `download.log` with a timestamped session header, the resolved output directory, and all downloaded files with full paths.

### Changed
- Catalog fetching now paginates (limit=100, offset loop) to retrieve the full Splunkbase catalog instead of the first page only.
- Catalog cache duration increased from 24 hours to 96 hours.
- Startup output clarifies the active configuration, including absolute output directory and path to `download.log`.
- Improved messaging when an app is up-to-date but the file is missing: now reports `up-to-date but file missing (use --fix-missing)` with a warning.

### Fixed
- Validation and checks previously failed to find already-downloaded files when they were in a prior downloads directory and `--outdir` was omitted; resolved by automatic directory detection.
- `Your_apps.json` is now auto-created as an empty array when missing, preventing `FileNotFoundError` during first run or onboarding.
- Clearer guidance for `UnicodeDecodeError` when files were created as UTF-16 (e.g., via PowerShell `echo`), including suggestions to recreate with UTF-8.

---

## [2.0.0] - 2025-11-11

### Added

#### Phase 3 - File Repair
- `--fix-missing` flag to automatically re-download missing files
- Intelligent detection of missing files vs outdated versions
- Dry-run support for missing file detection
- Report includes `action: redownloaded` for repaired files

#### Phase 4 - Filtering
- `--only UIDS` flag to process only specific UIDs (comma-separated)
- `--exclude UIDS` flag to skip specific UIDs from processing
- Filter support across all modes (normal, dry-run, validate, fix-missing)
- Robust UID parsing with error handling for invalid input

#### Phase 5 - Enhanced Reports
- `--hash` flag to calculate SHA256 checksums for downloaded files
- Memory-efficient hash calculation (64KB chunks)
- Extended report fields: `file_present`, `file_path`, `declared_version`, `latest_version`
- SHA256 hash included in reports (null for missing files)
- Improved report summaries with error/warning/missing file counts

#### Phase 6 - Backup & CI/CD Integration
- `--backup-keep N` flag for automatic backup rotation (default: 5)
- Timestamped backups: `Your_apps.json.bak-YYYYMMDD-HHMMSS`
- Automatic deletion of old backups (keeps only N most recent)
- Option to disable backups: `--backup-keep 0`
- `--fail-on-errors` flag for CI/CD pipeline integration
- Proper exit codes: 0 for success, 1 for errors
- Backups created before every `Your_apps.json` modification

#### Phase 7 - Documentation
- Comprehensive troubleshooting section in README
- Examples for all new features
- Updated feature list with Phase 3-6 additions
- Backup management documentation
- CI/CD integration examples

### Changed
- Improved error handling and validation
- Better logging for all operations
- Enhanced report structure with more detailed information
- Atomic file updates now include automatic backup creation

### Fixed
- File presence detection now works correctly in all modes
- Proper handling of missing files during validation
- Correct exit codes in validation mode

---

## [1.0.0] - Initial Release

### Added
- Basic download functionality for Splunkbase apps
- Interactive onboarding (`--onboard`)
- Credential management via `login.json`
- Schema validation (`--validate`)
- File mismatch detection
- Atomic updates to `Your_apps.json`
- Cross-platform support (Windows/Linux)
- Retry logic with backoff
- Summary reports and JSON export
- Test suite with pytest

---

## Migration Guide (1.x → 2.0)

### Breaking Changes
None - all changes are backward compatible.

### New Recommended Workflow

1. **Validation with backups:**
   ```bash
   python splunkbase-download.py --validate --backup-keep 5
   ```

2. **CI/CD Integration:**
   ```bash
   python splunkbase-download.py --validate --fail-on-errors
   ```

3. **Targeted updates:**
   ```bash
   python splunkbase-download.py --only 742,833 --hash
   ```

4. **Missing file repair:**
   ```bash
   python splunkbase-download.py --fix-missing --dry-run
   ```

### Configuration Changes
- Backups are now enabled by default (5 most recent)
- Use `--backup-keep 0` to disable if needed
- All backup files are automatically ignored in `.gitignore`

