from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class ClassesView(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Classes tab coming soon"))
        self.setLayout(layout)
