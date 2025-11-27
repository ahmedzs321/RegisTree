# 🌳 RegisTree

**RegisTree** is an offline, password-protected desktop application (Python + PySide6 + SQLite) for small schools and independent programs to manage:

- Students  
- Classes  
- Enrollments  
- Daily class attendance  
- Data exports and backups  

Long-term, RegisTree is intended to have both:

- A **local executable** for offline schools  
- A **cloud-backed version** for multi-device, multi-teacher access  

---

## ✨ Current Features

### Core Data

- Student registration & management  
  - Name, DOB, grade, status (Active/Inactive/Graduated)  
  - Guardian name & phone  
  - Contact email  
- Class management  
  - Name, subject, teacher, term, room  
- Enrollment system  
  - Assign students to classes  
  - Track enrollment start/end dates  

### Attendance

- Per-class, per-day attendance view  
- Status per student (e.g. Present/Absent/…)  
- Data stored in SQLite for reporting later  

### Dashboard

- Total students / active students  
- Total classes  
- Today’s attendance count  
- Breakdown by status for today (Present/Absent/etc.)  
- Auto-refresh when you switch to the Dashboard tab  

### Security

- Admin account stored in the database (`admin_users` table)  
- First run: prompt to **set admin password**  
- Later runs: **login dialog** before app opens  
- Passwords hashed with **bcrypt** (no plain-text storage)  

### Backup & Restore

- **Backup Database…**  
  - One-click copy of `registree.db` to a chosen location  
- **Restore Database…**  
  - Import an existing `.db` file, overwriting the local one  
  - “Restart now?” prompt that fully restarts the app  
- All data (including the admin password) travels with the DB file, so you can move RegisTree between devices.  

### Exports

- CSV exports:
  - Students (`students.csv`)
  - Classes (`classes.csv`)
  - Enrollments (`enrollments.csv`)
  - Attendance for a chosen date (`attendance_YYYY-MM-DD.csv`)
- JSON:
  - `students.json` snapshot of all students
- PDF:
  - Daily summary PDF for a date (total students, classes, attendance counts, status breakdown)
- Daily bundle:
  - For a selected date, generates a folder `exports/YYYY-MM-DD/` containing  
    - `students.json`  
    - `attendance_YYYY-MM-DD.csv`  
    - `summary_YYYY-MM-DD.pdf`  

---

## 🧭 Roadmap (Summary)

RegisTree’s upcoming development is focused on expanding functionality, improving usability, and preparing for long-term scalability. Planned features include:

- **Settings Menu** – Global configuration for school info, academic year, custom attendance statuses, export defaults, and auto-save behavior.  [COMPLETED]
- **Student Lifecycle Tools** – Graduation workflows and automatic grade-level promotion each academic year.  [COMPLETED]
- **Student Profiles** – A detailed profile window showing photos, attendance history, class list, guardian info, and notes.  
- **Class View Enhancements** – Enrollment counts, attendance summaries, roster exports, and quick-action views for each class.  
- **Attendance Reports** – Student/class reports, monthly summaries, and absence analytics in CSV/PDF form.  
- **Undo/Redo System** – Ability to revert recent changes such as deletions, edits, and enrollments.  
- **Calendar View** – A visual attendance calendar with color-coded days and per-day breakdowns.  
- **UI/UX Improvements** – Dark mode, better spacing and fonts, modern dialogs, icons, and color-coded attendance statuses.  

---

## 🛠 Tech Stack

- **Python** 3.12+  
- **PySide6** — desktop UI (Qt)  
- **SQLite** — local database  
- **SQLAlchemy** — ORM  
- **bcrypt** — password hashing  
- **ReportLab** — PDF generation  

---

## 🚀 Getting Started (Developers / Collaborators)

### 1. Clone the repository

```bash
git clone https://github.com/YOURUSERNAME/RegisTree.git
cd RegisTree
```

### 2. Create and activate a virtual environment

Windows (PowerShell):
```PowerShell
python -m venv venv
.\venv\Scripts\Activate
```

macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
````

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
python app.py
```

On first run, you will be prompted to:

	1. Set an admin password.

	2. After that, the main window opens with tabs for Dashboard, Students, Classes, Attendance, and Exports.

On later runs, you’ll see an Admin Login dialog before the main window opens.

---

## 🧑‍💻 Project Structure (high-level)
RegisTree/
  app.py                  # Application entry point (login + main window + tab wiring)
  requirements.txt        # Python dependencies
  README.md               # Project overview & setup instructions
  .gitignore              # Files/directories excluded from version control
  registree.db            # Local SQLite database (auto-created, ignored by git)
  data/
    __init__.py
    db.py                 # SQLAlchemy engine, SessionLocal, init_db()
    models.py             # ORM models: Student, Class, Enrollment, Attendance, AdminUser, Settings
    security.py           # Password hashing & verification (bcrypt)
  ui/
    __init__.py
    dashboard_view.py     # Dashboard tab (key metrics + today’s attendance)
    students_view.py      # Students tab (CRUD, search/filter, promotion logic)
    classes_view.py       # Classes tab (CRUD, term filter, manage enrollments)
    attendance_view.py    # Attendance tab (roster loading, marking, auto-save)
    exports_view.py       # Exports tab (CSV/JSON/PDF export, backup/restore)
    settings_view.py      # Settings tab (school info, statuses, grade range, promote-all)
    auth_dialogs.py       # SetupAdminDialog & LoginDialog (first-run + login UI)

  exports/                # Generated export files (CSV/JSON/PDF) — (ignored by git)
  venv/                   # Local virtual environment (ignored by git)
  build/                  # PyInstaller build artifacts (ignored by git)
  dist/                   # PyInstaller distribution folder (ignored by git)