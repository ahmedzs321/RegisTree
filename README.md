# 🌳 RegisTree

**RegisTree** is an offline desktop application (built with Python, PySide6, and SQLite) designed for schools to manage students, classes, and attendance.  
The long-term vision is to provide both an **offline executable** for small schools and a **cloud-based version** for multi-user access.

---

## 🚀 Features (Phase 1 MVP)
- Student registration & management
- Class creation & enrollment
- Attendance tracking (daily, per class)
- Data export to CSV/JSON/PDF

---

## 🌟 Planned Features (Phase 2)
- User authentication (Admin/Teacher roles)
- Audit logs for data changes
- Automated backups & restore
- Windows executable packaging for distribution

---

## 📦 Getting Started

### 1. Clone the repository
    git clone https://github.com/YOURUSERNAME/RegisTree.git
    cd RegisTree

### 2. Create a virtual environment
**Windows (PowerShell):**
    python -m venv venv
    .\venv\Scripts\Activate

**macOS/Linux:**
    python3 -m venv venv
    source venv/bin/activate

### 3. Install dependencies
    pip install -r requirements.txt

### 4. Run the app
    python app.py

You should see the **RegisTree** window with tabs for Students, Classes, Attendance, and Exports.

---

## 📊 Project Roadmap

### Phase 1 — Offline MVP
1. Add Student model (SQLAlchemy)
2. Build StudentsView table (UI)
3. Add Class model
4. Create Enrollment model (student-class link)
5. Add Attendance model and AttendanceView
6. Export data (CSV/JSON/PDF)

### Phase 2 — Extras & Improvements
7. User authentication (Admin/Teacher roles)
8. Audit log for data changes
9. Backup & restore system
10. Package RegisTree as Windows executable

---

## 🔧 Tech Stack
- Python 3.12+
- PySide6 — desktop UI
- SQLAlchemy — ORM & database
- SQLite — local database
- ReportLab — PDF generation
- bcrypt — password hashing
- PyInstaller — executable packaging (later)

---

## 👥 Contributing
1. Fork the repo
2. Create a feature branch (`git checkout -b feature-name`)
3. Commit changes (`git commit -m "Add feature"`)
4. Push to branch (`git push origin feature-name`)
5. Open a Pull Request 🎉
