# RegisTree
## Modern Offline School Management Application (Python + PySide6 + SQLite)

RegisTree is a secure, offline-first desktop application designed for small schools, tutoring programs, and learning pods.
It provides an intuitive interface for managing students, teachers, classes, attendance, academic calendars, exports, themes, and more.


## ✨ Features

### 🧑‍🎓 Student Management
- Full student profiles:
   - Photos
   - Notes
   - Guardian & emergency contacts
   - Attendance history
   - Enrollment history
   - Automatic grade promotion and graduation
   - Undo/redo support for edits and deletions

### 👩‍🏫 Teacher Management
- Teacher profiles with photos, contacts, emergency info, and notes
- Class assignment tracking
- Photo upload and logging

### 🏫 Class & Enrollment Management
- Create/edit/remove classes
- Assign teachers
- Enroll students (with start/end dates)
- Prevent duplicate enrollments
- Export class rosters and lists

### 📝 Attendance System
- Per-class daily attendance
- Configurable attendance statuses
- Optional auto-save mode
- Handles “No School” days automatically
- Export attendance (daily or full-range)

### 📅 Calendar System
- Monthly attendance/event calendar
- Event types:
   - No School
   - Teachers Only
   - Custom Events
- Event overlays and labels
- Exportable calendar events

### 🔍 Audit Logging (New)
- Tracks:
   - Students
   - Teachers
   - Classes
   - Enrollments
   - Attendance
   - Calendar Events
- Includes:
   - Before/After JSON snapshots
   - Password-protected viewer in Settings

### 🌓 Themes (New)
- Light Mode
- Dark Mode
- Instant switching
- Theme stored in DB and loaded on startup

### 📤 Export Tools
- Students CSV/JSON
- Classes CSV
- Enrollments CSV
- Attendance CSV
- PDF reports
- Calendar Events export
- Organized subfolders inside /exports/

### 🔐 Security
- First-time admin setup
- Password-protected login
- bcrypt password hashing
- Admin-only protected actions

### 🛠 Undo / Redo
- Global undo/redo manager
- Works across student, teacher, class, and enrollment edits


## 🛠 Tech Stack
UI            PySide6 (Qt for Python)
Database      SQLite + SQLAlchemy ORM
Security      bcrypt hashing
PDF Reports   ReportLab
Data Exports	pandas
Theme Engine	Qt Stylesheets


## 🚀 Getting Started

### 1️⃣ Clone the Repository
```
git clone https://github.com/YOURUSERNAME/RegisTree.git
cd RegisTree
```

### 2️⃣ Create a Virtual Environment
Windows:
```
python -m venv venv
.\venv\Scripts\activate
```

macOS / Linux:
```
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Install Dependencies
```
pip install -r requirements.txt
```

### 4️⃣ Run the Application
```
python app.py
```

### 5️⃣ First-Time Setup
- Create an admin password
- Login screen will appear every launch


## 📂 Project Structure

RegisTree/
│
├── app.py
├── data/
│   ├── db.py
│   ├── models.py
│   ├── security.py
│
├── ui/
│   ├── students_view.py
│   ├── teachers_view.py
│   ├── classes_view.py
│   ├── attendance_view.py
│   ├── calendar_view.py
│   ├── exports_view.py
│   ├── dashboard_view.py
│   ├── settings_view.py
│   ├── auth_dialogs.py
│   └── undo_manager.py
│
├── exports/
├── photos/
├── requirements.txt
├── README.md
└── .gitignore


## 📦 Packaging (PyInstaller)

```
pyinstaller --name RegisTree --icon assets/app.ico --noconfirm app.py
```
Executable appears in:
- dist/RegisTree/
- build/


## 🧪 Development Notes

- SQLite DB stored as: registree.db
- Settings stored in Settings table (theme, export dir, school days, etc.)
- Audit logs stored in audit_logs
- Theme applies at startup via apply_theme()


## 🙌 Credits

Designed & built by Ahmed Syed
Modern offline school management system built with Python + Qt.