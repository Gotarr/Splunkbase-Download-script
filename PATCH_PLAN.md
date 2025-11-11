# Patch- und Phasen-Plan (Roadmap)

Ziel: Nachvollziehbares, schrittweises Patch-Management für `splunkbase-download.py` mit klaren Zielen, Abnahmekriterien, Tests und Rollback-Strategie.

Diese Datei dient als Arbeitsgrundlage und Checkliste für jede Phase. Haken ( [ ] / [x] ) werden gesetzt, sobald ein Punkt erledigt ist.

---

## Versionierung & Releases
- Schema: SemVer (MAJOR.MINOR.PATCH)
- Branching: `main` stabil, Feature-Branches je Phase (`feature/phase-<nr>-<kurzname>`)
- Tags/Release: `vX.Y.Z` nach Abschluss einer Phase oder eines logischen Bündels
- Changelog: `CHANGELOG.md` (kann später ergänzt werden)

Release-Checkliste:
- [ ] Tests grün
- [ ] Lint/Format (optional)
- [ ] README/PATCH_PLAN aktualisiert
- [ ] Version im Release-Tag notiert

---

## Phase 1 – Validierung (`--validate`)
Ziel: Konsistenzfehler in `Your_apps.json` früh erkennen.

Umfang:
- [x] Neues Flag `--validate` (nur prüfen, keine Downloads)
- [x] Prüfungen:
  - Pflichtfelder: `uid`, `version`, `name`, `appid`, `updated_time`
  - Typen: `uid` (int), `version` (str), `updated_time` (ISO8601 mit TZ)
  - Doppelte `uid` erkennen
  - JSON-Parsing-Fehler sauber melden
- [x] Exit-Code ≠ 0 bei Fehlern
- [x] Optional: Ausgabe in Report via `--report-file`

Abnahmekriterien:
- `py ./splunkbase-download.py --validate` liefert klare Meldungen und Exit-Code 1 bei Fehlern
- Keine Dateiänderungen

Tests (Beispiele):
- [x] Gültige Datei → Exit 0
- [x] Fehlendes Feld → Exit 1
- [x] Doppelte `uid` → Exit 1
- [x] Falscher `updated_time`-String → Warnung oder Fehler gemäß Definition

Rollback:
- Nur Code-Änderungen, keine Datenmutation → Rollback nicht kritisch

---

## Phase 2 – Mismatch-Erkennung (Datei vs. JSON)
Ziel: Abgleich zwischen deklarierten Versionen und vorhandenen `.tgz`-Dateien.

Umfang:
- [x] Erwarteter Dateiname: `<uid>_<version>.tgz`
- [x] Feld `file_present` pro App (Report + Log)
- [x] Zusammenfassung `missing_files`
- [x] Wirksam in normalem Lauf und in `--validate`

Abnahmekriterien:
- Fehlende Dateien werden geloggt und im Report ausgewiesen

Tests:
- [x] Datei vorhanden → `file_present=true`
- [x] Datei fehlt → `file_present=false` + Warnung

Rollback:
- Nur Logik/Report, keine Datenmutation

---

## Phase 3 – Reparatur fehlender Dateien (`--fix-missing`) ✅
Ziel: Konsistenz automatisch wiederherstellen.

Umfang:
- [x] Neues Flag `--fix-missing`
- [x] Wenn Datei fehlt und JSON-Version == `latest` → Datei erneut laden
- [x] Wenn JSON-Version != `latest`:
  - Standard: Nur warnen (kein automatisches Upgrade)
  - Optionales Flag `--fix-missing-upgrade`: lade `latest` und aktualisiere Eintrag
- [x] Report: `action` = `redownload-missing` oder `plan-upgrade`

Abnahmekriterien:
- Fehlende aktuelle Version wird automatisch nachgeladen ✅
- Kein stilles Upgrade ohne Flag ✅

Tests:
- [x] Fehlende Datei bei aktueller Version → Download + `file_present=true`
- [x] Fehlende Datei bei veralteter Version → Warnung, mit `--fix-missing-upgrade` → Upgrade
- [x] Dry-run zeigt `plan-redownload` für fehlende Dateien
- [x] Report enthält `file_present`, `action: redownloaded/plan-redownload`

Rollback:
- Nutzt bestehendes atomares Update der JSON; Backup-Phase (siehe Phase 6) reduziert Risiko zusätzlich

**Status:** ✅ Vollständig implementiert und getestet (11.11.2025)

---

## Phase 4 – Selektion (`--only`/`--exclude`) ✅
Ziel: Fokussierte Verarbeitung.

Umfang:
- [x] `--only 742,833` → nur diese UIDs verarbeiten
- [x] `--exclude 1621` → diese UIDs auslassen
- [x] Gilt für alle Modi (validate, dry-run, normal, fix-missing)

Abnahmekriterien:
- Nur ausgewählte UIDs werden gelistet/verarbeitet ✅
- Filter funktionieren in allen Modi ✅

Tests:
- [x] `--only` filtert korrekt (single: 742, multiple: 742,833)
- [x] `--exclude` filtert korrekt (single: 742, multiple: 742,833,1621)
- [x] Nicht-existierende UIDs (--only 9999 → keine Verarbeitung)
- [x] Filter in --validate Modus
- [x] Filter in --fix-missing Modus
- [x] Ungültige Eingabe (abc) → ValueError mit klarer Meldung

Rollback: Nur CLI/Filter-Logik

**Status:** ✅ Vollständig implementiert und getestet (11.11.2025)

---

## Phase 5 – Report erweitern ✅
Ziel: Bessere Nachvollziehbarkeit.

Umfang:
- [x] Report-Felder: `declared_version`, `latest_version`, `action`, `reason`, `file_present`, `file_path`
- [x] Optional `--hash`: SHA256 bei vorhandener Datei berechnen
- [x] Zusammenfassung: `missing_files`, `to_update`, `up_to_date`, `errors`

Abnahmekriterien:
- Report enthält alle Felder ✅
- SHA256-Hash wird nur bei --hash berechnet ✅
- Hash ist null für fehlende Dateien ✅

Tests:
- [x] JSON-Report valide, enthält neue Felder
- [x] --hash mit fehlender Datei → sha256: null
- [x] --hash mit existierender Datei → gültiger SHA256-Hash (64 Zeichen hex)
- [x] Ohne --hash → kein sha256 Feld im Report
- [x] Hash-Berechnung in 64KB chunks (speichereffizient)

Rollback: rein additive Felder

**Status:** ✅ Vollständig implementiert und getestet (11.11.2025)

---

## Phase 6 – Backups & Exit-Codes
Ziel: Sichere Updates und CI-Integration.

Umfang:
- [ ] Backup-Rotation vor JSON-Update: `Your_apps.json.bak-YYYYMMDD-HHMMSS` (retention via `--backup-keep N`)
- [ ] `--fail-on-errors`: Exit-Code ≠ 0, wenn `errors > 0` oder Inkonsistenzen gefunden

Abnahmekriterien:
- Backups werden erzeugt und rotiert
- CI kann auf Fehler reagieren

Tests:
- [ ] Backup-Datei existiert
- [ ] `--fail-on-errors` setzt Exit-Code ≠ 0 bei Fehlern

Rollback: Backups ermöglichen Wiederherstellung

---

## Phase 7 – README & Dokumentation
Ziel: Gute Bedienbarkeit.

Umfang:
- [ ] README ergänzt um neue Flags + Beispiele
- [ ] Kurze Troubleshooting-Hinweise

Abnahmekriterien:
- README verständlich, Beispiele funktionieren

Rollback: Nur Doku

---

## Optionale Erweiterungen (später)
- [ ] CSV-Report (`--format csv`)
- [ ] Parallele Abfragen/Downloads (`--max-parallel N`) – API-Limits beachten
- [ ] Benachrichtigungen (Slack/E-Mail) bei Updates
- [ ] Quarantäne/Staging-Ordner vor produktivem Einsatz

---

## Patch-Template (für jede Phase)
- Ziel(e): …
- Änderungen: …
- Flags/CLI: …
- Datenänderungen: …
- Abnahmekriterien: …
- Tests: …
- Risiken/Edge Cases: …
- Rollback: …
- Doku/README: …
- Release/Tag: …

---

## Hinweise / Governance
- Code-Review empfohlen (4-Augen-Prinzip)
- Kleine, isolierte Commits pro Teilaufgabe
- Automatisierte Tests wenn möglich (pytest)
- Keine Secrets einchecken (siehe `.gitignore`)

