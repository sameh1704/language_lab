# Stage 5 Runtime Documentation

## Date
2026-10-07

## Status
STAGE 5 STATUS: PASS

## Evidence Table

| Test | Expected | Actual | Evidence | Status |
|------|----------|--------|----------|--------|
| Full test suite | Pass | Pass | `python manage.py test` = 99 OK | PASS |
| makemigrations --check | No changes | No changes | `python manage.py makemigrations --check` = No changes detected | PASS |
| migrate --plan | No pending | No pending | `python manage.py migrate --plan` = No planned operations | PASS |
| system check | No issues | No issues | `python manage.py check` = No issues | PASS |
| Runtime upload cycle | Pass | Pass | media_runtime_test.py | PASS |

## Domain

| Component | Details |
|-----------|---------|
| MediaFolder | name, parent (self-referencing FK), created_by, created_at, updated_at |
| MediaAsset | title, description, file, media_type, mime_type, size, content_language, folder, created_by, created_at, updated_at |
| Media types | audio, video, image, pdf, document |
| Migration | 0007_mediafolder_mediaasset_and_more |

## Storage

| Aspect | Details |
|--------|---------|
| Backend | Django MEDIA_ROOT (`BASE_DIR / "media"`) |
| Abstraction | `lab/media_lib.py` provides `get_media_storage_root()`, `get_safe_upload_path()` |
| Future | Clean abstraction allows replacing with object storage |

## Security

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Invalid extension (.exe) | 400 | 400 | PASS |
| Invalid MIME (application/x-msdownload for .mp3) | 400 | 400 | PASS |
| Oversized file (>500 MB) | 400 | 400 | PASS |
| Path traversal filename | Caught by validate_filename | ValueError raised | PASS |
| Unauthorized download (no login) | 302 | 302 | PASS |
| Unauthorized delete (student) | 403 | 403 | PASS |

## HTTP / UI

| Feature | Status |
|---------|--------|
| Folder browsing | PASS |
| Upload (audio, video, image, PDF) | PASS |
| Search | PASS |
| Filter by type | PASS |
| Rename asset | PASS |
| Move asset | PASS |
| Delete asset | PASS |
| Preview image | PASS |
| Preview PDF | PASS |
| Download | PASS |
| Folder create/rename/delete | PASS |

## Runtime Verification

| Step | Result |
|------|--------|
| Upload audio | 200, file stored, DB record exists |
| Upload video | 200, file stored, DB record exists |
| Upload image | 200, file stored, DB record exists |
| Upload PDF | 200, file stored, DB record exists |
| Physical file exists | Yes for all 4 files |
| Search | 200 |
| Filter by type | 200 |
| Rename | 200, title updated |
| Move | 200, folder updated |
| Download | 200, correct MIME |
| Preview image | 200 |
| Preview PDF | 200 |
| Delete | 200, DB and filesystem consistent |
| Persistence after reload | Verified |

## Database / Migration

| Check | Result |
|-------|--------|
| 0007_mediafolder_mediaasset_and_more applied | Yes |
| makemigrations --check | No changes |
| migrate --plan | No pending |
| showmigrations lab | All applied |

## Regression

| Command | Result |
|---------|--------|
| `python manage.py test` | 99 tests OK |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check` | No changes |
| `python manage.py migrate --plan` | No pending |

## Language

| Feature | Status |
|---------|--------|
| Interface language (i18n) | Arabic UI supported |
| Content language (metadata) | Independent field `content_language` |
| Mixed content | English audio/video/image/PDF with Arabic UI works |

## Limitations

- Browser automation unavailable; runtime tested via Django test client
- No user-classroom assignment for media; authorization relies on `is_staff`
- Duplicate titles in same folder are currently allowed (no unique constraint on title+folder)
