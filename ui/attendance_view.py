from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class AttendanceView(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Attendance tab coming soon"))
        self.setLayout(layout)
