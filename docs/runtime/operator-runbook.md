# Operator Runbook

## How to Start the Server

```bash
# Activate virtual environment if used
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser (first time only)
python manage.py createsuperuser

# Start development server
python manage.py runserver 127.0.0.1:8000

# Or start with Daphne (ASGI for WebSocket)
python -m daphne labsys.asgi:application --bind 127.0.0.1 --port 8000
```

## How to Configure the Lab

1. Access `/admin/` and log in as superuser
2. Create a `School`
3. Create `Classroom`(s) under the school
4. Create `Device`(s) under each classroom with:
   - Device number (1-40)
   - IP address
   - Hostname
5. Configure Veyon:
   - Set `VEYON_CLI` environment variable (default: `C:\Program Files\Veyon\veyon-cli.exe`)
   - Set `VEYON_PORT` (default: 11100)
   - Set `LAB_SIMULATE=0` for real Veyon operations

## How to Pair Devices

1. On the teacher machine, go to `/setup/`
2. The setup page will scan the network for devices
3. Devices will appear automatically when they access `/student/`
4. Assign devices to students via the admin interface or setup page

## How to Create Classrooms

1. Go to `/admin/lab/classroom/`
2. Click "Add classroom"
3. Fill in:
   - School
   - Name
   - Code (unique identifier)
   - Room number (optional)
   - Capacity (default: 40)
4. Save

## How to Assign Students

1. Go to `/admin/lab/student/`
2. Click "Add student"
3. Fill in:
   - Student ID (unique)
   - Full name
   - Preferred language (optional)
   - Assigned device (optional)
4. Save

## How to Use Screen Control

1. Select devices on the dashboard
2. Use action buttons:
   - **Lock**: Lock selected devices
   - **Unlock**: Unlock selected devices
   - **Absent**: Mark students as absent
   - **Present**: Mark students as present
3. Or use the Veyon control panel for advanced features

## How to Use Audio

1. Students open `/student/` on their devices
2. Teacher can see online students
3. Audio communication is handled via WebRTC
4. Teacher can broadcast to selected students

## How to Handle Hand Raises

1. Student clicks "Hand Raise" or "Help" on their device
2. Teacher sees the request in the assistance panel
3. Teacher can:
   - Acknowledge
   - Resolve
   - Dismiss
4. Student sees the status update

## How to Manage Media

1. Go to `/media/`
2. Create folders to organize content
3. Upload files (audio, video, image, PDF, documents)
4. Preview files inline
5. Download files
6. Rename or move files
7. Delete files

## How to Import/Export Data

1. Go to `/import-export/`
2. Select entity type (Students, Classes, Enrollments)
3. Upload CSV or XLSX file
4. Review preview and validation errors
5. Select duplicate handling mode:
   - **Reject**: Skip duplicates
   - **Update**: Modify existing records
   - **Skip**: Silently skip duplicates
6. Confirm import
7. To export: click export links for CSV or XLSX format

## How to Switch Languages

1. Click the language switcher in the header
2. Select Arabic, English, or French
3. Interface language changes immediately
4. Content language is independent (e.g., English audio with Arabic UI)

## Common Failures

| Issue | Solution |
|-------|----------|
| Device not showing online | Check IP address and network connectivity |
| Veyon command fails | Verify `VEYON_CLI` path and `LAB_SIMULATE` setting |
| WebSocket disconnects | Check network stability; reconnect is automatic |
| Upload fails | Check file size (max 500MB) and file type |
| Import validation errors | Check required fields and duplicate IDs |
| Login fails | Verify username/password; check `is_active` flag |

## Recovery Procedure

1. **Server not responding**:
   ```bash
   # Check if process is running
   tasklist | findstr python
   
   # Kill and restart
   taskkill /F /IM python.exe
   python manage.py runserver 127.0.0.1:8000
   ```

2. **Database locked**:
   ```bash
   # Stop server, delete lock file, restart
   del db.sqlite3-wal
   del db.sqlite3-shm
   python manage.py migrate
   ```

3. **Media files missing**:
   - Check `MEDIA_ROOT` in settings
   - Verify file permissions
   - Re-upload missing files

4. **Migration issues**:
   ```bash
   python manage.py showmigrations
   python manage.py migrate --run-syncdb
   ```

5. **Channel layer issues**:
   - In-memory layer is used by default (single process)
   - For multi-process, configure Redis in settings

## Implementation Status
- All stages implemented: 1-6
- 127 automated tests passing
- Final integration acceptance: 70/70 tests passing

## Runtime Status
- Server: Running (tested)
- Database: SQLite3 (tested)
- Media: Filesystem (tested)
- WebSockets: In-memory channel layer (tested)
- Veyon: Simulation mode (real hardware not available)

## Hardware Status
- Veyon: Simulation mode only (no real Veyon installation tested)
- Audio: WebRTC code present, browser testing not performed
- Devices: 95 devices in test database (40 in Language Lab A, 10 in Language Lab B)

## Known Limitations
1. No browser automation - UI tested via HTTP client only
2. Veyon real hardware not available - simulation mode only
3. WebRTC audio requires browser for full testing
4. Single-process deployment only (in-memory channel layer)
5. No Redis configured for multi-worker scaling
