# Stage 6 Runtime Documentation

## Date
2026-10-07

## Status
STAGE 6 STATUS: PASS

## Evidence Table

| Test | Expected | Actual | Evidence | Status |
|------|----------|--------|----------|--------|
| Full test suite | Pass | Pass | `python manage.py test` = 127 OK | PASS |
| makemigrations --check | No changes | No changes | `python manage.py makemigrations --check` = No changes detected | PASS |
| migrate --plan | No pending | No pending | `python manage.py migrate --plan` = No planned operations | PASS |
| system check | No issues | No issues | `python manage.py check` = No issues | PASS |
| Runtime import/export cycle | Pass | Pass | stage6_runtime_test.py | PASS |

## Supported Data

| Entity | Fields |
|--------|--------|
| Students | student_id, full_name, active, preferred_language, device_number, classroom_code |
| Classes | code, name, grade, section, learning_language, academic_year, active |
| Enrollments | student_id, class_code, status |

## Import Workflow

| Step | Status |
|------|--------|
| Upload CSV/XLSX | PASS |
| Parse with UTF-8 detection | PASS |
| Validate required fields | PASS |
| Deep validation (duplicates, foreign keys) | PASS |
| Preview with errors | PASS |
| User confirmation | PASS |
| Transactional import | PASS |
| Import report | PASS |

## Validation

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Missing required fields | Rejected | Rejected | PASS |
| Duplicate student IDs | Rejected | Rejected | PASS |
| Duplicate enrollments | Rejected | Rejected | PASS |
| Invalid classroom code | Rejected | Rejected | PASS |
| Invalid device number | Rejected | Rejected | PASS |
| Invalid language code | Rejected | Rejected | PASS |
| Malformed rows | Rejected | Rejected | PASS |
| Encoding errors (non-UTF8) | Rejected | Rejected | PASS |

## UTF-8 Support

| Language | Test | Status |
|----------|------|--------|
| Arabic | محمد أحمد, فاطمة الزهراء | PASS |
| French | Jean Dupont, Marie Curie | PASS |
| English | John Smith, Emma Wilson | PASS |

## Transactions

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Rollback on error | DB unchanged | DB unchanged | PASS |
| Partial import prevention | No partial data | No partial data | PASS |

## Duplicates

| Mode | Behavior | Status |
|------|----------|--------|
| Reject | Skip and report | PASS |
| Update | Modify existing | PASS |
| Skip | Silently skip | PASS |

## Export

| Format | Status |
|--------|--------|
| CSV (UTF-8 BOM) | PASS |
| XLSX (openpyxl) | PASS |
| Arabic preservation | PASS |
| French preservation | PASS |
| English preservation | PASS |

## Authorization

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Unauthorized import | 403 | 403 | PASS |
| Unauthorized export | 403 | 403 | PASS |
| Staff access | Allowed | Allowed | PASS |

## Runtime Verification

| Step | Result |
|------|--------|
| Upload 11 students (Arabic/French/English) | 200 OK |
| Preview validation | 11 valid, 0 errors |
| Confirm import | 11 created |
| Database records | 11 students with correct names |
| Export CSV | 382 bytes, all names present |
| Export XLSX | 5522 bytes, 12 rows |
| Duplicate rejection | 1 error reported |
| Transaction rollback | DB unchanged after simulated error |
| Authorization | 403 for non-staff |

## Database / Migration

| Check | Result |
|-------|--------|
| New migrations | None |
| makemigrations --check | No changes |
| migrate --plan | No pending |

## Regression

| Command | Result |
|---------|--------|
| `python manage.py test` | 127 tests OK |
| `python manage.py check` | No issues |

## Limitations

- Browser automation unavailable; runtime tested via Django test client
- Large file preview limited to 100 rows in JSON response
- XLSX export requires openpyxl (installed)
- No chunked import for very large files
