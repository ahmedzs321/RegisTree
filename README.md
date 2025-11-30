# 🌳 RegisTree 
### Offline-First School Management System (Python + PySide6 + SQLite)

RegisTree is a modern, secure, offline-first desktop application built for small schools, tutoring centers, community learning pods, and homeschool groups.  
It provides a clean interface for managing students, teachers, classes, attendance, calendars, reports, exports, and more — all without requiring an internet connection.

This is the **0.1.0 Beta** release.

This README.md is for developers. Users should look for the RegisTree_User_Guide.pdf in the file directory.

---

## ✨ Features

### 🧑‍🎓 Student Management
- Full student profiles (photos, contact info, notes)
- Emergency & guardian contact support
- Grade levels, enrollment history, attendance history
- Automatic promotion & graduation tools
- Undo/redo support for edits and deletions

### 👩‍🏫 Teacher Management
- Teacher profiles with contact and emergency details
- Class assignment tracking
- Daily check-in / check-out system
- Photo upload with image caching
- Undo/redo for all modifications

### 🏫 Class & Enrollment Management
- Create, edit, and delete classes  
- Assign teachers and enroll students  
- Enrollment start/end dates  
- Prevent duplicate enrollments  
- Export class rosters (CSV)

### 📝 Attendance System
- Per-class daily attendance  
- Configurable attendance statuses  
- Auto-save mode (optional)  
- Handles “No School” calendar events  
- Daily bundle export (JSON + CSV + PDF)

### 📅 Calendar
- Monthly calendar view  
- Event types:
  - No School
  - Teachers Only
  - Custom Events  
- Built-in event export tools

### 🔍 Audit Logging (New)
RegisTree automatically logs:
- Students  
- Teachers  
- Classes  
- Enrollments  
- Attendance  
- Calendar Events  

Each entry stores:
- Timestamp  
- Actor  
- Action  
- Entity & ID  
- Before/After JSON snapshots  

Password-protected viewer included.

### 🌓 Themes
- Light & Dark mode  
- Applies instantly  
- Stored in settings and loaded at startup

### 📤 Export Tools
- Students CSV & JSON  
- Teachers CSV  
- Teacher-Class links CSV  
- Class rosters  
- Attendance (daily, range-based)  
- Monthly summaries (PDF)  
- Calendar Events (CSV)  
- Fully organized output inside `exports/`

### 🔐 Security
- First-time admin setup  
- Password-protected login  
- bcrypt hashing  
- Admin-only privileged actions  

### ↩️ Undo / Redo
- Global undo/redo engine  
- Supports student, teacher, class, and enrollment edits  
- Undo stack is in-memory (clears on restart)

---

## 🛠 Tech Stack

| Component       |        Technology         |
|-----------------|---------------------------|
| UI Framework    | PySide6 (Qt for Python)   |
| Database        | SQLite + SQLAlchemy ORM   |
| Security        | bcrypt                    |
| PDF Generator   | ReportLab                 |
| Packaging       | PyInstaller               |
| Export Helpers  | CSV, JSON, ReportLab PDFs |
| Theme Engine    | Qt Stylesheets            |

---

## 🚀 Getting Started (Developer Setup)

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/ahmedzs321/RegisTree.git
cd RegisTree
```

### 2️⃣ Create & Activate Virtual Environment
Windows
```bash
python -m venv venv
.\venv\Scripts\activate
```
macOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 4️⃣ Run RegisTree
```bash
python app.py
```

### 5️⃣ First-Time Startup
- You will be prompted to create the admin password.
- Afterwards, the login dialog appears each launch.

## 📂 Project Structure
```bash
RegisTree/
│
├── app.py
├── data/
│   ├── db.py
│   ├── models.py
│   ├── security.py
│   └── paths.py
│
├── ui/
│   ├── startup_dialog.py
│   ├── dashboard_view.py
│   ├── students_view.py
│   ├── teachers_view.py
│   ├── teacher_tracker_view.py
│   ├── classes_view.py
│   ├── attendance_view.py
│   ├── calendar_view.py
│   ├── exports_view.py
│   ├── settings_view.py
│   ├── auth_dialogs.py
│   └── undo_manager.py
│
├── exports/
├── photos/
├── logs/
├── requirements.txt
├── README.md
└── .gitignore
```

## 📦 Packaging Into an EXE (PyInstaller)
RegisTree includes a path-safe system (data/paths.py) that ensures that database + exports + logs + photos all stay beside the EXE when frozen.
Example command:
```bash
pyinstaller app.py --name RegisTree --onedir --noconfirm --clean
```
After building:
- Executable folder: dist/RegisTree/
- All user-created files appear inside the same folder:
   - registree.db
   - /exports
   - /photos
   - /logs

## 🧪 Developer Notes
 - Database file: registree.db
 - Settings stored in the Settings table
 - User-writable directories controlled by data/paths.py
 - Audit logs stored in audit_logs table
 - Undo / redo stacks do not persist after closing the app

🙌 Credits

Designed & developed by Ahmed Syed & collaborators. 

A modern offline school management system built with Python & Qt.