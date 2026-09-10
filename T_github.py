import sys
import sqlite3
import random
from pathlib import Path
from collections import defaultdict

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QSpinBox, QTimeEdit, QPushButton, QLabel, QTextEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QListWidget,
    QListWidgetItem, QCheckBox, QGroupBox, QAbstractItemView,
    QHeaderView, QFileDialog, QDialog, QDialogButtonBox
)

APP_NAME = "College Timetable Pro"
DB_FILE = Path(__file__).with_name("college_timetable.db")

DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday"
]


# ============================================================
# DATABASE
# ============================================================

class Database:
    def __init__(self, path=DB_FILE):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    def create_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK(id=1),
            college_name TEXT DEFAULT 'My College',
            start_time TEXT DEFAULT '08:00',
            period_duration INTEGER DEFAULT 40,
            period_count INTEGER DEFAULT 8,
            break_after INTEGER DEFAULT 4,
            break_duration INTEGER DEFAULT 20,
            working_days TEXT DEFAULT 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'
        );

        INSERT OR IGNORE INTO settings(id) VALUES(1);

        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS teacher_subjects (
            teacher_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            PRIMARY KEY(teacher_id, subject_id),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            year TEXT NOT NULL,
            section TEXT NOT NULL,
            UNIQUE(name, year, section)
        );

        CREATE TABLE IF NOT EXISTS program_subjects (
            program_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            periods_per_week INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(program_id, subject_id),
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS program_teacher_assignments (
            program_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            PRIMARY KEY(program_id, subject_id),
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS timetables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            slot INTEGER NOT NULL,
            subject_id INTEGER,
            teacher_id INTEGER,
            UNIQUE(program_id, day, slot),
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE SET NULL
        );
        """)
        self.conn.commit()

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()
        return cur

    def executemany(self, sql, rows):
        self.conn.executemany(sql, rows)
        self.conn.commit()

    def settings(self):
        return self.conn.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()

    def close(self):
        self.conn.close()


# ============================================================
# HELPERS
# ============================================================

def minutes_to_time(total):
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def build_slots(db):
    row = db.settings()

    start = row[2]
    duration = row[3]
    count = row[4]
    break_after = row[5]
    break_duration = row[6]

    h, m = map(int, start.split(":"))
    current = h * 60 + m

    slots = []

    for i in range(1, count + 1):
        begin = current
        end = current + duration

        slots.append({
            "number": i,
            "start": minutes_to_time(begin),
            "end": minutes_to_time(end),
            "label": f"{minutes_to_time(begin)} - {minutes_to_time(end)}",
            "break": False
        })

        current = end

        if i == break_after and i < count:
            slots.append({
                "number": 0,
                "start": minutes_to_time(current),
                "end": minutes_to_time(current + break_duration),
                "label": "BREAK",
                "break": True
            })

            current += break_duration

    return slots


def working_days(db):
    value = db.settings()[7]
    return [x.strip() for x in value.split(",") if x.strip()]


def table_item(text, bold=False):
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(Qt.AlignCenter)

    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    return item


# ============================================================
# TEACHER DIALOG
# ============================================================

class TeacherDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        self.setWindowTitle("Add Teacher")
        self.setModal(True)
        self.resize(500, 450)

        layout = QVBoxLayout(self)

        title = QLabel("Add Teacher")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)

        layout.addWidget(QLabel("Teacher Name"))

        self.name = QLineEdit()
        self.name.setPlaceholderText("Example: Mr. Ahmed")
        layout.addWidget(self.name)

        layout.addWidget(
            QLabel("Select subjects this teacher can teach:")
        )

        self.subjects = QListWidget()
        self.subjects.setSelectionMode(
            QAbstractItemView.MultiSelection
        )
        layout.addWidget(self.subjects)

        rows = self.db.conn.execute(
            "SELECT id, name FROM subjects ORDER BY name"
        ).fetchall()

        for sid, name in rows:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, sid)
            self.subjects.addItem(item)

        buttons = QHBoxLayout()

        save = QPushButton("Add Teacher")
        cancel = QPushButton("Cancel")

        buttons.addWidget(save)
        buttons.addWidget(cancel)

        layout.addLayout(buttons)

        save.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)

    def save(self):

        name = self.name.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Missing",
                "Please enter teacher name."
            )
            return

        try:
            cur = self.db.conn.cursor()

            cur.execute(
                "INSERT INTO teachers(name) VALUES(?)",
                (name,)
            )

            teacher_id = cur.lastrowid

            for i in range(self.subjects.count()):

                item = self.subjects.item(i)

                if item.isSelected():

                    subject_id = item.data(Qt.UserRole)

                    cur.execute("""
                        INSERT INTO teacher_subjects
                        (teacher_id, subject_id)
                        VALUES (?, ?)
                    """, (teacher_id, subject_id))

            self.db.conn.commit()

            self.accept()

        except sqlite3.IntegrityError:

            self.db.conn.rollback()

            QMessageBox.warning(
                self,
                "Duplicate",
                "A teacher with this name already exists."
            )

        except Exception as e:

            self.db.conn.rollback()

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )


# ============================================================
# SUBJECT DIALOG
# ============================================================

class SubjectDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        self.setWindowTitle("Add Subject")
        self.resize(400, 200)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Subject Name"))

        self.name = QLineEdit()
        self.name.setPlaceholderText("Example: Mathematics")
        layout.addWidget(self.name)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def save(self):

        name = self.name.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Missing",
                "Enter subject name."
            )
            return

        try:

            self.db.execute(
                "INSERT INTO subjects(name) VALUES(?)",
                (name,)
            )

            self.accept()

        except sqlite3.IntegrityError:

            QMessageBox.warning(
                self,
                "Duplicate",
                "This subject already exists."
            )


# ============================================================
# PROGRAM DIALOG
# ============================================================

class ProgramDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        self.setWindowTitle("Add Class / Section")
        self.setModal(True)
        self.resize(950, 650)

        layout = QVBoxLayout(self)

        title = QLabel("Add Class / Section")
        title.setFont(QFont("Segoe UI", 17, QFont.Bold))
        layout.addWidget(title)

        form = QFormLayout()

        self.program = QLineEdit()
        self.program.setPlaceholderText(
            "ICS / Pre-Engineering / Medical"
        )

        self.year = QComboBox()
        self.year.addItems([
            "11th",
            "12th",
            "1st Year",
            "2nd Year"
        ])

        self.section = QLineEdit()
        self.section.setPlaceholderText(
            "A / B / Blue / RMEB"
        )

        form.addRow("Program:", self.program)
        form.addRow("Year:", self.year)
        form.addRow("Section:", self.section)

        layout.addLayout(form)

        instruction = QLabel(
            "Select the subjects for this class and choose the teacher "
            "for each selected subject. Only teachers qualified for "
            "that subject are shown."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Subject",
            "Periods / Week",
            "Selected",
            "Teacher"
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        subjects = self.db.conn.execute("""
            SELECT id, name
            FROM subjects
            ORDER BY name
        """).fetchall()

        for sid, name in subjects:
            row = self.table.rowCount()
            self.table.insertRow(row)

            subject_item = QTableWidgetItem(name)
            subject_item.setData(Qt.UserRole, sid)
            self.table.setItem(row, 0, subject_item)

            spin = QSpinBox()
            spin.setRange(1, 20)
            spin.setValue(4)
            self.table.setCellWidget(row, 1, spin)

            checkbox = QCheckBox()
            checkbox.setChecked(False)

            wrapper = QWidget()
            box = QHBoxLayout(wrapper)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(checkbox, alignment=Qt.AlignCenter)
            self.table.setCellWidget(row, 2, wrapper)

            teacher_combo = QComboBox()
            teacher_combo.setEnabled(False)
            teacher_combo.setPlaceholderText("Select teacher")
            self.table.setCellWidget(row, 3, teacher_combo)

            self.populate_teachers(sid, teacher_combo)

            checkbox.stateChanged.connect(
                lambda state, combo=teacher_combo:
                    combo.setEnabled(state == Qt.Checked)
            )

        layout.addWidget(self.table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def populate_teachers(self, subject_id, combo):
        combo.clear()

        teachers = self.db.conn.execute("""
            SELECT t.id, t.name
            FROM teachers t
            JOIN teacher_subjects ts
              ON ts.teacher_id = t.id
            WHERE ts.subject_id = ?
            ORDER BY t.name
        """, (subject_id,)).fetchall()

        for tid, name in teachers:
            combo.addItem(name, tid)

        if not teachers:
            combo.addItem("No qualified teacher", None)
            combo.setEnabled(False)

    def save(self):
        program = self.program.text().strip()
        year = self.year.currentText()
        section = self.section.text().strip()

        if not program or not section:
            QMessageBox.warning(
                self,
                "Missing",
                "Enter program and section."
            )
            return

        selected_rows = []
        teacher_assignments = []

        # Validate the selected subjects and their teachers BEFORE
        # creating the program, so the database remains clean if the
        # user forgot a teacher.
        for row in range(self.table.rowCount()):
            wrapper = self.table.cellWidget(row, 2)
            checkbox = wrapper.findChild(QCheckBox)

            if not checkbox or not checkbox.isChecked():
                continue

            subject_item = self.table.item(row, 0)
            sid = subject_item.data(Qt.UserRole)
            subject_name = subject_item.text()

            periods = self.table.cellWidget(row, 1).value()
            teacher_combo = self.table.cellWidget(row, 3)
            tid = teacher_combo.currentData()

            if tid is None:
                QMessageBox.warning(
                    self,
                    "Teacher Missing",
                    f"Please select a qualified teacher for "
                    f"{subject_name}."
                )
                return

            # Extra database verification for safety.
            qualified = self.db.conn.execute("""
                SELECT COUNT(*)
                FROM teacher_subjects
                WHERE teacher_id = ?
                  AND subject_id = ?
            """, (tid, sid)).fetchone()[0]

            if not qualified:
                QMessageBox.warning(
                    self,
                    "Teacher Not Qualified",
                    f"{teacher_combo.currentText()} is not configured "
                    f"to teach {subject_name}."
                )
                return

            selected_rows.append(
                (sid, periods)
            )
            teacher_assignments.append(
                (sid, tid)
            )

        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Subjects",
                "Select at least one subject."
            )
            return

        try:
            cur = self.db.conn.cursor()

            cur.execute("""
                INSERT INTO programs(name, year, section)
                VALUES(?,?,?)
            """, (
                program,
                year,
                section
            ))

            pid = cur.lastrowid

            cur.executemany("""
                INSERT INTO program_subjects
                (program_id, subject_id, periods_per_week)
                VALUES(?,?,?)
            """, [
                (pid, sid, periods)
                for sid, periods in selected_rows
            ])

            cur.executemany("""
                INSERT INTO program_teacher_assignments
                (program_id, subject_id, teacher_id)
                VALUES(?,?,?)
            """, [
                (pid, sid, tid)
                for sid, tid in teacher_assignments
            ])

            self.db.conn.commit()
            self.accept()

        except sqlite3.IntegrityError:
            self.db.conn.rollback()

            QMessageBox.warning(
                self,
                "Duplicate",
                "This class/year/section already exists."
            )

        except Exception as e:
            self.db.conn.rollback()

            QMessageBox.critical(
                self,
                "Error",
                str(e)
            )


class ClassAssignmentDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        self.setWindowTitle(
            "Configure Class Timetable"
        )

        self.resize(850, 600)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Class Timetable Assignment"
        )
        title.setFont(
            QFont("Segoe UI", 17, QFont.Bold)
        )

        layout.addWidget(title)

        info = QLabel(
            "Choose a class/section and assign a teacher "
            "to each subject. You can add multiple subjects."
        )

        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.program = QComboBox()

        programs = self.db.conn.execute("""
            SELECT id, name, year, section
            FROM programs
            ORDER BY year, name, section
        """).fetchall()

        for pid, name, year, section in programs:

            self.program.addItem(
                f"{year} | {name} | Section {section}",
                pid
            )

        form.addRow(
            "Class / Section:",
            self.program
        )

        layout.addLayout(form)

        layout.addWidget(
            QLabel("Subject assignments:")
        )

        self.table = QTableWidget(0, 4)

        self.table.setHorizontalHeaderLabels([
            "Subject",
            "Teacher",
            "Periods / Week",
            "Remove"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )

        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )

        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )

        layout.addWidget(self.table)

        add_row = QPushButton(
            "+ Add Subject Assignment"
        )

        add_row.clicked.connect(
            self.add_row
        )

        layout.addWidget(add_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.save
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

        self.program.currentIndexChanged.connect(
            self.program_changed
        )

        if self.program.count():
            self.add_row()

    def program_changed(self):

        self.table.setRowCount(0)

        if self.program.count():
            self.add_row()

    def load_subjects_for_row(
        self,
        row,
        subject_combo,
        teacher_combo
    ):

        subject_combo.clear()
        teacher_combo.clear()

        pid = self.program.currentData()

        if pid is None:
            return

        subjects = self.db.conn.execute("""
            SELECT s.id, s.name, ps.periods_per_week
            FROM program_subjects ps
            JOIN subjects s
              ON s.id=ps.subject_id
            WHERE ps.program_id=?
            ORDER BY s.name
        """, (pid,)).fetchall()

        for sid, name, weekly in subjects:

            subject_combo.addItem(
                name,
                (sid, weekly)
            )

        def subject_changed():

            teacher_combo.clear()

            sid_data = subject_combo.currentData()

            if not sid_data:
                return

            sid = sid_data[0]

            teachers = self.db.conn.execute("""
                SELECT t.id, t.name
                FROM teachers t
                JOIN teacher_subjects ts
                  ON ts.teacher_id=t.id
                WHERE ts.subject_id=?
                ORDER BY t.name
            """, (sid,)).fetchall()

            for tid, name in teachers:
                teacher_combo.addItem(
                    name,
                    tid
                )

        subject_combo.currentIndexChanged.connect(
            subject_changed
        )

        subject_changed()

    def add_row(self):

        pid = self.program.currentData()

        if pid is None:
            QMessageBox.warning(
                self,
                "No class",
                "Add a class/section first."
            )
            return

        row = self.table.rowCount()

        self.table.insertRow(row)

        subject_combo = QComboBox()
        teacher_combo = QComboBox()

        self.table.setCellWidget(
            row,
            0,
            subject_combo
        )

        self.table.setCellWidget(
            row,
            1,
            teacher_combo
        )

        spin = QSpinBox()
        spin.setRange(1, 20)
        spin.setValue(4)

        self.table.setCellWidget(
            row,
            2,
            spin
        )

        remove = QPushButton("Remove")

        self.table.setCellWidget(
            row,
            3,
            remove
        )

        remove.clicked.connect(
            lambda: self.remove_row(remove)
        )

        self.load_subjects_for_row(
            row,
            subject_combo,
            teacher_combo
        )

        def update_periods():

            data = subject_combo.currentData()

            if data:
                spin.setValue(data[1])

        subject_combo.currentIndexChanged.connect(
            update_periods
        )

        update_periods()

    def remove_row(self, button):

        for row in range(self.table.rowCount()):

            if self.table.cellWidget(
                row,
                3
            ) is button:

                self.table.removeRow(row)
                return

    def save(self):

        pid = self.program.currentData()

        if pid is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Select a class."
            )
            return

        assignments = []

        for row in range(self.table.rowCount()):

            subject = self.table.cellWidget(
                row,
                0
            )

            teacher = self.table.cellWidget(
                row,
                1
            )

            periods = self.table.cellWidget(
                row,
                2
            )

            if not subject.currentData():
                continue

            sid = subject.currentData()[0]
            tid = teacher.currentData()

            if tid is None:

                QMessageBox.warning(
                    self,
                    "Teacher missing",
                    "Select a teacher for every subject."
                )

                return

            assignments.append(
                (
                    pid,
                    sid,
                    tid,
                    periods.value()
                )
            )

        if not assignments:

            QMessageBox.warning(
                self,
                "No assignments",
                "Add at least one subject assignment."
            )

            return

        # Detect duplicate subject rows.
        seen = set()

        for pid, sid, tid, periods in assignments:

            if sid in seen:

                QMessageBox.warning(
                    self,
                    "Duplicate subject",
                    "The same subject cannot be added twice "
                    "for one class in this configuration."
                )

                return

            seen.add(sid)

        self.result = assignments

        self.accept()


# ============================================================
# TEACHER ASSIGNMENT DIALOG
# ============================================================

class TeacherAssignmentDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        self.setWindowTitle(
            "Configure Teacher Timetable"
        )

        self.resize(900, 600)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Teacher Timetable Assignment"
        )

        title.setFont(
            QFont("Segoe UI", 17, QFont.Bold)
        )

        layout.addWidget(title)

        info = QLabel(
            "Choose a teacher and assign that teacher to "
            "multiple classes/sections. The generator will "
            "automatically prevent double-booking."
        )

        info.setWordWrap(True)

        layout.addWidget(info)

        form = QFormLayout()

        self.teacher = QComboBox()

        teachers = self.db.conn.execute("""
            SELECT id, name
            FROM teachers
            ORDER BY name
        """).fetchall()

        for tid, name in teachers:

            self.teacher.addItem(
                name,
                tid
            )

        form.addRow(
            "Teacher:",
            self.teacher
        )

        layout.addLayout(form)

        layout.addWidget(
            QLabel("Teacher assignments:")
        )

        self.table = QTableWidget(0, 4)

        self.table.setHorizontalHeaderLabels([
            "Class / Section",
            "Subject",
            "Periods / Week",
            "Remove"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.Stretch
        )

        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch
        )

        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents
        )

        self.table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents
        )

        layout.addWidget(self.table)

        add_row = QPushButton(
            "+ Add Class Assignment"
        )

        add_row.clicked.connect(
            self.add_row
        )

        layout.addWidget(add_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.save
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

        self.teacher.currentIndexChanged.connect(
            self.teacher_changed
        )

        if self.teacher.count():
            self.add_row()

    def teacher_changed(self):

        self.table.setRowCount(0)

        if self.teacher.count():
            self.add_row()

    def load_subjects(
        self,
        program_combo,
        subject_combo,
        spin
    ):

        subject_combo.clear()

        pid = program_combo.currentData()

        if pid is None:
            return

        subjects = self.db.conn.execute("""
            SELECT s.id, s.name, ps.periods_per_week
            FROM program_subjects ps
            JOIN subjects s
              ON s.id=ps.subject_id
            WHERE ps.program_id=?
            ORDER BY s.name
        """, (pid,)).fetchall()

        for sid, name, weekly in subjects:

            subject_combo.addItem(
                name,
                (sid, weekly)
            )

        def changed():

            data = subject_combo.currentData()

            if data:
                spin.setValue(data[1])

        subject_combo.currentIndexChanged.connect(
            changed
        )

        changed()

    def add_row(self):

        row = self.table.rowCount()

        self.table.insertRow(row)

        program_combo = QComboBox()
        subject_combo = QComboBox()

        programs = self.db.conn.execute("""
            SELECT id, name, year, section
            FROM programs
            ORDER BY year, name, section
        """).fetchall()

        for pid, name, year, section in programs:

            program_combo.addItem(
                f"{year} | {name} | Section {section}",
                pid
            )

        self.table.setCellWidget(
            row,
            0,
            program_combo
        )

        self.table.setCellWidget(
            row,
            1,
            subject_combo
        )

        spin = QSpinBox()
        spin.setRange(1, 20)
        spin.setValue(4)

        self.table.setCellWidget(
            row,
            2,
            spin
        )

        remove = QPushButton(
            "Remove"
        )

        self.table.setCellWidget(
            row,
            3,
            remove
        )

        remove.clicked.connect(
            lambda: self.remove_row(remove)
        )

        program_combo.currentIndexChanged.connect(
            lambda: self.load_subjects(
                program_combo,
                subject_combo,
                spin
            )
        )

        self.load_subjects(
            program_combo,
            subject_combo,
            spin
        )

    def remove_row(self, button):

        for row in range(self.table.rowCount()):

            if self.table.cellWidget(
                row,
                3
            ) is button:

                self.table.removeRow(row)
                return

    def save(self):

        tid = self.teacher.currentData()

        if tid is None:

            QMessageBox.warning(
                self,
                "Missing",
                "Select a teacher."
            )

            return

        assignments = []

        for row in range(self.table.rowCount()):

            program = self.table.cellWidget(
                row,
                0
            )

            subject = self.table.cellWidget(
                row,
                1
            )

            spin = self.table.cellWidget(
                row,
                2
            )

            if program.currentData() is None:
                continue

            if subject.currentData() is None:

                QMessageBox.warning(
                    self,
                    "Missing subject",
                    "Select a subject for every class."
                )

                return

            pid = program.currentData()
            sid = subject.currentData()[0]

            # Verify teacher is qualified.
            qualified = self.db.conn.execute("""
                SELECT COUNT(*)
                FROM teacher_subjects
                WHERE teacher_id=?
                  AND subject_id=?
            """, (
                tid,
                sid
            )).fetchone()[0]

            if not qualified:

                teacher_name = self.teacher.currentText()
                subject_name = subject.currentText()

                QMessageBox.warning(
                    self,
                    "Teacher not qualified",
                    f"{teacher_name} is not configured to teach "
                    f"{subject_name}."
                )

                return

            assignments.append(
                (
                    tid,
                    pid,
                    sid,
                    spin.value()
                )
            )

        if not assignments:

            QMessageBox.warning(
                self,
                "No assignments",
                "Add at least one class assignment."
            )

            return

        self.result = assignments

        self.accept()


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.db = Database()

        self.generated = False

        # ----------------------------------------------------
        # GENERATION CONFIGURATION
        # ----------------------------------------------------

        # Class configuration:
        # pid -> list of (subject_id, teacher_id, periods)
        self.class_generation_config = defaultdict(list)

        # Teacher configuration:
        # tid -> list of (program_id, subject_id, periods)
        self.teacher_generation_config = defaultdict(list)

        self.setWindowTitle(APP_NAME)
        self.resize(1800, 1000)
        self.setMinimumSize(1400, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.build_dashboard()
        self.build_settings()
        self.build_teachers()
        self.build_subjects()
        self.build_programs()
        self.build_generator()
        self.build_class_view()
        self.build_teacher_view()

        self.apply_style()

        self.refresh_all()

    # ========================================================
    # DASHBOARD
    # ========================================================

    def build_dashboard(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel(APP_NAME)
        title.setObjectName("Title")

        layout.addWidget(title)

        subtitle = QLabel(
            "Professional college timetable management and "
            "automatic conflict-free scheduling system."
        )

        subtitle.setObjectName("Subtitle")

        layout.addWidget(subtitle)

        cards = QHBoxLayout()

        self.teacher_count = QLabel("0")
        self.subject_count = QLabel("0")
        self.program_count = QLabel("0")

        for title_text, label in [
            ("Teachers", self.teacher_count),
            ("Subjects", self.subject_count),
            ("Classes / Sections", self.program_count)
        ]:

            box = QGroupBox(title_text)

            v = QVBoxLayout(box)

            label.setObjectName(
                "CardNumber"
            )

            v.addWidget(label)

            cards.addWidget(box)

        layout.addLayout(cards)

        info = QLabel(
            "WORKFLOW\n\n"
            "1. Add subjects.\n"
            "2. Add teachers and select what they can teach.\n"
            "3. Add every class / section, select its subjects, "
            "and choose a qualified teacher for each subject.\n"
            "4. Configure college timing.\n"
            "5. Click Generate All Timetables.\n"
            "7. Review class and teacher views.\n"
            "8. Export PDFs."
        )

        info.setWordWrap(True)
        info.setObjectName("Info")

        layout.addWidget(info)

        layout.addStretch()

        self.tabs.addTab(
            page,
            "Dashboard"
        )

    # ========================================================
    # SETTINGS
    # ========================================================

    def build_settings(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        group = QGroupBox(
            "College & Timetable Settings"
        )

        form = QFormLayout(group)

        self.college_name = QLineEdit()

        self.start_time = QTimeEdit()
        self.start_time.setDisplayFormat("HH:mm")

        self.period_duration = QSpinBox()
        self.period_duration.setRange(15, 180)

        self.period_count = QSpinBox()
        self.period_count.setRange(1, 20)

        self.break_after = QSpinBox()
        self.break_after.setRange(0, 20)

        self.break_duration = QSpinBox()
        self.break_duration.setRange(0, 120)

        form.addRow(
            "College name:",
            self.college_name
        )

        form.addRow(
            "College starts:",
            self.start_time
        )

        form.addRow(
            "Period duration:",
            self.period_duration
        )

        form.addRow(
            "Number of periods:",
            self.period_count
        )

        form.addRow(
            "Break after period:",
            self.break_after
        )

        form.addRow(
            "Break duration:",
            self.break_duration
        )

        layout.addWidget(group)

        days_group = QGroupBox(
            "Working Days"
        )

        days_layout = QHBoxLayout(days_group)

        self.day_checks = {}

        for day in DAYS:

            cb = QCheckBox(day)

            self.day_checks[day] = cb

            days_layout.addWidget(cb)

        layout.addWidget(days_group)

        layout.addWidget(
            QLabel("Period Preview:")
        )

        self.period_preview = QTableWidget(0, 4)

        self.period_preview.setHorizontalHeaderLabels([
            "No.",
            "Start",
            "End",
            "Type"
        ])

        self.period_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        layout.addWidget(
            self.period_preview
        )

        buttons = QHBoxLayout()

        save = QPushButton(
            "Save Settings"
        )

        preview = QPushButton(
            "Refresh Preview"
        )

        save.clicked.connect(
            self.save_settings
        )

        preview.clicked.connect(
            self.refresh_period_preview
        )

        buttons.addWidget(save)
        buttons.addWidget(preview)
        buttons.addStretch()

        layout.addLayout(buttons)

        self.tabs.addTab(
            page,
            "College Settings"
        )

    def load_settings(self):

        row = self.db.settings()

        self.college_name.setText(
            row[1]
        )

        h, m = map(
            int,
            row[2].split(":")
        )

        self.start_time.setTime(
            QTime(h, m)
        )

        self.period_duration.setValue(
            row[3]
        )

        self.period_count.setValue(
            row[4]
        )

        self.break_after.setValue(
            row[5]
        )

        self.break_duration.setValue(
            row[6]
        )

        selected = set(
            x.strip()
            for x in row[7].split(",")
        )

        for day, checkbox in self.day_checks.items():

            checkbox.setChecked(
                day in selected
            )

        self.refresh_period_preview()

    def save_settings(self):

        days = [
            d for d in DAYS
            if self.day_checks[d].isChecked()
        ]

        if not days:

            QMessageBox.warning(
                self,
                "Invalid",
                "Select at least one working day."
            )

            return

        if self.break_after.value() >= self.period_count.value():

            self.break_after.setValue(0)

        self.db.execute("""
            UPDATE settings
            SET college_name=?,
                start_time=?,
                period_duration=?,
                period_count=?,
                break_after=?,
                break_duration=?,
                working_days=?
            WHERE id=1
        """, (
            self.college_name.text().strip()
            or "My College",

            self.start_time.time().toString(
                "HH:mm"
            ),

            self.period_duration.value(),
            self.period_count.value(),
            self.break_after.value(),
            self.break_duration.value(),
            ",".join(days)
        ))

        self.refresh_period_preview()

        QMessageBox.information(
            self,
            "Saved",
            "College settings saved."
        )

    def refresh_period_preview(self):

        slots = build_slots(self.db)

        self.period_preview.setRowCount(
            len(slots)
        )

        for row, slot in enumerate(slots):

            self.period_preview.setItem(
                row,
                0,
                table_item(
                    "BREAK"
                    if slot["break"]
                    else slot["number"]
                )
            )

            self.period_preview.setItem(
                row,
                1,
                table_item(slot["start"])
            )

            self.period_preview.setItem(
                row,
                2,
                table_item(slot["end"])
            )

            self.period_preview.setItem(
                row,
                3,
                table_item(
                    "BREAK"
                    if slot["break"]
                    else "Period"
                )
            )

    # ========================================================
    # TEACHERS
    # ========================================================

    def build_teachers(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        buttons = QHBoxLayout()

        add = QPushButton(
            "+ Add Teacher"
        )

        delete = QPushButton(
            "Delete Selected"
        )

        refresh = QPushButton(
            "Refresh"
        )

        add.clicked.connect(
            self.add_teacher
        )

        delete.clicked.connect(
            self.delete_teacher
        )

        refresh.clicked.connect(
            self.refresh_teachers
        )

        buttons.addWidget(add)
        buttons.addWidget(delete)
        buttons.addWidget(refresh)
        buttons.addStretch()

        layout.addLayout(buttons)

        self.teacher_table = QTableWidget(0, 3)

        self.teacher_table.setHorizontalHeaderLabels([
            "ID",
            "Teacher",
            "Subjects They Can Teach"
        ])

        self.teacher_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        self.teacher_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents
        )

        self.teacher_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.Stretch
        )

        self.teacher_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        layout.addWidget(
            self.teacher_table
        )

        self.tabs.addTab(
            page,
            "Teachers"
        )

    def add_teacher(self):

        if self.subject_count.text() == "0":

            QMessageBox.warning(
                self,
                "Add Subjects First",
                "Please add subjects before adding teachers."
            )

            return

        dialog = TeacherDialog(
            self.db,
            self
        )

        if dialog.exec_() == QDialog.Accepted:

            self.refresh_teachers()

    def delete_teacher(self):

        rows = sorted(
            {
                item.row()
                for item in self.teacher_table.selectedItems()
            },
            reverse=True
        )

        if not rows:
            return

        if QMessageBox.question(
            self,
            "Delete",
            "Delete selected teacher(s)?"
        ) != QMessageBox.Yes:

            return

        for row in rows:

            tid = self.teacher_table.item(
                row,
                0
            ).data(Qt.UserRole)

            self.db.execute(
                "DELETE FROM teachers WHERE id=?",
                (tid,)
            )

        self.refresh_teachers()

        self.class_generation_config.clear()
        self.teacher_generation_config.clear()

        self.refresh_generation_lists()

    def refresh_teachers(self):

        data = self.db.conn.execute("""
            SELECT
                t.id,
                t.name,
                COALESCE(
                    GROUP_CONCAT(s.name, ', '),
                    ''
                )
            FROM teachers t
            LEFT JOIN teacher_subjects ts
                ON ts.teacher_id=t.id
            LEFT JOIN subjects s
                ON s.id=ts.subject_id
            GROUP BY t.id
            ORDER BY t.name
        """).fetchall()

        self.teacher_table.setRowCount(
            len(data)
        )

        for row, (
            tid,
            name,
            subjects
        ) in enumerate(data):

            self.teacher_table.setItem(
                row,
                0,
                table_item(tid)
            )

            self.teacher_table.item(
                row,
                0
            ).setData(
                Qt.UserRole,
                tid
            )

            self.teacher_table.setItem(
                row,
                1,
                QTableWidgetItem(name)
            )

            self.teacher_table.setItem(
                row,
                2,
                QTableWidgetItem(subjects)
            )

        self.teacher_count.setText(
            str(len(data))
        )

    # ========================================================
    # SUBJECTS
    # ========================================================

    def build_subjects(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        buttons = QHBoxLayout()

        add = QPushButton(
            "+ Add Subject"
        )

        bulk = QPushButton(
            "Bulk Add"
        )

        delete = QPushButton(
            "Delete Selected"
        )

        add.clicked.connect(
            self.add_subject
        )

        bulk.clicked.connect(
            self.bulk_add_subjects
        )

        delete.clicked.connect(
            self.delete_subject
        )

        buttons.addWidget(add)
        buttons.addWidget(bulk)
        buttons.addWidget(delete)
        buttons.addStretch()

        layout.addLayout(buttons)

        self.subject_table = QTableWidget(0, 2)

        self.subject_table.setHorizontalHeaderLabels([
            "ID",
            "Subject"
        ])

        self.subject_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        self.subject_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch
        )

        self.subject_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        layout.addWidget(
            self.subject_table
        )

        self.tabs.addTab(
            page,
            "Subjects"
        )

    def add_subject(self):

        dialog = SubjectDialog(
            self.db,
            self
        )

        if dialog.exec_() == QDialog.Accepted:

            self.refresh_subjects()
            self.refresh_teachers()
            self.refresh_programs()

    def bulk_add_subjects(self):

        dialog = QDialog(self)

        dialog.setWindowTitle(
            "Bulk Add Subjects"
        )

        dialog.resize(
            500,
            500
        )

        layout = QVBoxLayout(dialog)

        title = QLabel(
            "Add Multiple Subjects"
        )

        title.setFont(
            QFont(
                "Segoe UI",
                14,
                QFont.Bold
            )
        )

        layout.addWidget(title)

        layout.addWidget(
            QLabel(
                "Enter one subject per line:"
            )
        )

        text_box = QTextEdit()

        text_box.setPlaceholderText(
            "English\n"
            "Urdu\n"
            "Mathematics\n"
            "Physics\n"
            "Chemistry\n"
            "Biology\n"
            "Computer Science"
        )

        layout.addWidget(
            text_box
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel
        )

        layout.addWidget(buttons)

        buttons.rejected.connect(
            dialog.reject
        )

        def add_subjects():

            names = []

            for line in text_box.toPlainText().splitlines():

                name = line.strip()

                if name:
                    names.append(name)

            if not names:

                QMessageBox.warning(
                    dialog,
                    "No Subjects",
                    "Enter at least one subject."
                )

                return

            added = 0
            duplicates = 0

            for name in names:

                try:

                    self.db.execute(
                        "INSERT INTO subjects(name) VALUES(?)",
                        (name,)
                    )

                    added += 1

                except sqlite3.IntegrityError:

                    duplicates += 1

            dialog.accept()

            self.refresh_subjects()
            self.refresh_teachers()
            self.refresh_programs()

            QMessageBox.information(
                self,
                "Complete",
                f"Subjects added: {added}\n"
                f"Duplicates skipped: {duplicates}"
            )

        buttons.accepted.connect(
            add_subjects
        )

        dialog.exec_()

    def delete_subject(self):

        rows = sorted(
            {
                item.row()
                for item in self.subject_table.selectedItems()
            },
            reverse=True
        )

        if not rows:
            return

        if QMessageBox.question(
            self,
            "Delete",
            "Delete selected subject(s)?"
        ) != QMessageBox.Yes:

            return

        for row in rows:

            sid = self.subject_table.item(
                row,
                0
            ).data(Qt.UserRole)

            self.db.execute(
                "DELETE FROM subjects WHERE id=?",
                (sid,)
            )

        self.class_generation_config.clear()
        self.teacher_generation_config.clear()

        self.refresh_subjects()
        self.refresh_teachers()
        self.refresh_programs()
        self.refresh_generation_lists()

    def refresh_subjects(self):

        data = self.db.conn.execute("""
            SELECT id, name
            FROM subjects
            ORDER BY name
        """).fetchall()

        self.subject_table.setRowCount(
            len(data)
        )

        for row, (
            sid,
            name
        ) in enumerate(data):

            self.subject_table.setItem(
                row,
                0,
                table_item(sid)
            )

            self.subject_table.item(
                row,
                0
            ).setData(
                Qt.UserRole,
                sid
            )

            self.subject_table.setItem(
                row,
                1,
                QTableWidgetItem(name)
            )

        self.subject_count.setText(
            str(len(data))
        )

    # ========================================================
    # PROGRAMS
    # ========================================================

    def build_programs(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        buttons = QHBoxLayout()

        add = QPushButton(
            "+ Add Class / Section"
        )

        delete = QPushButton(
            "Delete Selected"
        )

        refresh = QPushButton(
            "Refresh"
        )

        add.clicked.connect(
            self.add_program
        )

        delete.clicked.connect(
            self.delete_program
        )

        refresh.clicked.connect(
            self.refresh_programs
        )

        buttons.addWidget(add)
        buttons.addWidget(delete)
        buttons.addWidget(refresh)
        buttons.addStretch()

        layout.addLayout(buttons)

        self.program_table = QTableWidget(0, 4)

        self.program_table.setHorizontalHeaderLabels([
            "ID",
            "Program",
            "Year",
            "Section"
        ])

        self.program_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        self.program_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        layout.addWidget(
            self.program_table
        )

        self.tabs.addTab(
            page,
            "Classes & Sections"
        )

    def add_program(self):

        if self.subject_count.text() == "0":

            QMessageBox.warning(
                self,
                "Add subjects first",
                "Add subjects first."
            )

            return

        dialog = ProgramDialog(
            self.db,
            self
        )

        if dialog.exec_() == QDialog.Accepted:
            self.refresh_programs()
            self.refresh_generation_lists()

    def delete_program(self):

        rows = sorted(
            {
                item.row()
                for item in self.program_table.selectedItems()
            },
            reverse=True
        )

        if not rows:
            return

        if QMessageBox.question(
            self,
            "Delete",
            "Delete selected class/section(s)?"
        ) != QMessageBox.Yes:

            return

        for row in rows:

            pid = self.program_table.item(
                row,
                0
            ).data(Qt.UserRole)

            self.db.execute(
                "DELETE FROM programs WHERE id=?",
                (pid,)
            )

            self.class_generation_config.pop(
                pid,
                None
            )

            for tid in list(
                self.teacher_generation_config
            ):

                self.teacher_generation_config[tid] = [
                    x for x in self.teacher_generation_config[tid]
                    if x[0] != pid
                ]

        self.refresh_programs()
        self.refresh_generation_lists()

    def refresh_programs(self):

        data = self.db.conn.execute("""
            SELECT id, name, year, section
            FROM programs
            ORDER BY year, name, section
        """).fetchall()

        self.program_table.setRowCount(
            len(data)
        )

        for row, values in enumerate(data):

            for col, value in enumerate(values):

                self.program_table.setItem(
                    row,
                    col,
                    table_item(value)
                )

            self.program_table.item(
                row,
                0
            ).setData(
                Qt.UserRole,
                values[0]
            )

        self.program_count.setText(
            str(len(data))
        )

        self.refresh_class_selector()

    # ========================================================
    # GENERATOR
    # ========================================================

    def build_generator(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel(
            "Professional Timetable Generator"
        )

        title.setObjectName(
            "SectionTitle"
        )

        layout.addWidget(title)

        description = QLabel(
            "Teachers selected inside each Class / Section are used "
            "automatically. Advanced class/teacher assignment tools "
            "are also available when you need manual overrides."
        )

        description.setWordWrap(True)

        layout.addWidget(
            description
        )

        # ----------------------------------------------------
        # Generation mode
        # ----------------------------------------------------

        mode_group = QGroupBox(
            "Generation Mode"
        )

        mode_layout = QFormLayout(
            mode_group
        )

        self.generate_scope = QComboBox()

        self.generate_scope.addItems([
            "Generate All Timetables",
            "Generate Class Timetables",
            "Generate Teacher Timetables"
        ])

        mode_layout.addRow(
            "Generate:",
            self.generate_scope
        )

        layout.addWidget(
            mode_group
        )

        # ----------------------------------------------------
        # Class configuration
        # ----------------------------------------------------

        class_group = QGroupBox(
            "Class Timetable Configuration"
        )

        class_layout = QVBoxLayout(
            class_group
        )

        class_buttons = QHBoxLayout()

        add_class_assignment = QPushButton(
            "+ Add Class Assignment"
        )

        clear_class_assignment = QPushButton(
            "Clear Class Assignments"
        )

        add_class_assignment.clicked.connect(
            self.add_class_assignment
        )

        clear_class_assignment.clicked.connect(
            self.clear_class_assignments
        )

        class_buttons.addWidget(
            add_class_assignment
        )

        class_buttons.addWidget(
            clear_class_assignment
        )

        class_buttons.addStretch()

        class_layout.addLayout(
            class_buttons
        )

        self.class_config_list = QListWidget()

        class_layout.addWidget(
            self.class_config_list
        )

        layout.addWidget(
            class_group
        )

        # ----------------------------------------------------
        # Teacher configuration
        # ----------------------------------------------------

        teacher_group = QGroupBox(
            "Teacher Timetable Configuration"
        )

        teacher_layout = QVBoxLayout(
            teacher_group
        )

        teacher_buttons = QHBoxLayout()

        add_teacher_assignment = QPushButton(
            "+ Add Teacher Assignment"
        )

        clear_teacher_assignment = QPushButton(
            "Clear Teacher Assignments"
        )

        add_teacher_assignment.clicked.connect(
            self.add_teacher_assignment
        )

        clear_teacher_assignment.clicked.connect(
            self.clear_teacher_assignments
        )

        teacher_buttons.addWidget(
            add_teacher_assignment
        )

        teacher_buttons.addWidget(
            clear_teacher_assignment
        )

        teacher_buttons.addStretch()

        teacher_layout.addLayout(
            teacher_buttons
        )

        self.teacher_config_list = QListWidget()

        teacher_layout.addWidget(
            self.teacher_config_list
        )

        layout.addWidget(
            teacher_group
        )

        # ----------------------------------------------------
        # Generate button
        # ----------------------------------------------------

        generate = QPushButton(
            "GENERATE ALL TIMETABLES"
        )

        generate.setObjectName(
            "GenerateButton"
        )

        generate.clicked.connect(
            self.generate_all
        )

        layout.addWidget(
            generate
        )

        self.log = QListWidget()

        layout.addWidget(
            QLabel("Generation Log:")
        )

        layout.addWidget(
            self.log
        )

        self.tabs.addTab(
            page,
            "Generate"
        )

    # ========================================================
    # ADD CLASS ASSIGNMENT
    # ========================================================

    def add_class_assignment(self):

        if self.program_count.text() == "0":

            QMessageBox.warning(
                self,
                "No classes",
                "Add classes/sections first."
            )

            return

        if self.teacher_count.text() == "0":

            QMessageBox.warning(
                self,
                "No teachers",
                "Add teachers first."
            )

            return

        dialog = ClassAssignmentDialog(
            self.db,
            self
        )

        if dialog.exec_() == QDialog.Accepted:

            for (
                pid,
                sid,
                tid,
                periods
            ) in dialog.result:

                self.class_generation_config[
                    pid
                ].append(
                    (
                        sid,
                        tid,
                        periods
                    )
                )

            self.refresh_generation_lists()

    # ========================================================
    # ADD TEACHER ASSIGNMENT
    # ========================================================

    def add_teacher_assignment(self):

        if self.teacher_count.text() == "0":

            QMessageBox.warning(
                self,
                "No teachers",
                "Add teachers first."
            )

            return

        if self.program_count.text() == "0":

            QMessageBox.warning(
                self,
                "No classes",
                "Add classes/sections first."
            )

            return

        dialog = TeacherAssignmentDialog(
            self.db,
            self
        )

        if dialog.exec_() == QDialog.Accepted:

            for (
                tid,
                pid,
                sid,
                periods
            ) in dialog.result:

                self.teacher_generation_config[
                    tid
                ].append(
                    (
                        pid,
                        sid,
                        periods
                    )
                )

            self.refresh_generation_lists()

    # ========================================================
    # CONFIGURATION LISTS
    # ========================================================

    def program_text(self, pid):

        row = self.db.conn.execute("""
            SELECT name, year, section
            FROM programs
            WHERE id=?
        """, (pid,)).fetchone()

        if not row:
            return "Unknown Class"

        return (
            f"{row[1]} | {row[0]} | Section {row[2]}"
        )

    def teacher_text(self, tid):

        row = self.db.conn.execute("""
            SELECT name
            FROM teachers
            WHERE id=?
        """, (tid,)).fetchone()

        return row[0] if row else "Unknown Teacher"

    def subject_text(self, sid):

        row = self.db.conn.execute("""
            SELECT name
            FROM subjects
            WHERE id=?
        """, (sid,)).fetchone()

        return row[0] if row else "Unknown Subject"

    def refresh_generation_lists(self):

        if not hasattr(
            self,
            "class_config_list"
        ):
            return

        self.class_config_list.clear()

        for pid, assignments in sorted(
            self.class_generation_config.items()
        ):

            class_name = self.program_text(pid)

            for sid, tid, periods in assignments:

                self.class_config_list.addItem(
                    f"{class_name}  →  "
                    f"{self.subject_text(sid)}  →  "
                    f"{self.teacher_text(tid)}  "
                    f"({periods} periods/week)"
                )

        if self.class_config_list.count() == 0:

            self.class_config_list.addItem(
                "No class assignments configured. "
                "Automatic teacher selection will be used."
            )

        self.teacher_config_list.clear()

        for tid, assignments in sorted(
            self.teacher_generation_config.items()
        ):

            teacher_name = self.teacher_text(tid)

            for pid, sid, periods in assignments:

                self.teacher_config_list.addItem(
                    f"{teacher_name}  →  "
                    f"{self.program_text(pid)}  →  "
                    f"{self.subject_text(sid)}  "
                    f"({periods} periods/week)"
                )

        if self.teacher_config_list.count() == 0:

            self.teacher_config_list.addItem(
                "No teacher assignments configured."
            )

    def clear_class_assignments(self):

        if not self.class_generation_config:
            return

        if QMessageBox.question(
            self,
            "Clear",
            "Clear all class timetable configurations?"
        ) != QMessageBox.Yes:

            return

        self.class_generation_config.clear()

        self.refresh_generation_lists()

    def clear_teacher_assignments(self):

        if not self.teacher_generation_config:
            return

        if QMessageBox.question(
            self,
            "Clear",
            "Clear all teacher timetable configurations?"
        ) != QMessageBox.Yes:

            return

        self.teacher_generation_config.clear()

        self.refresh_generation_lists()

    # ========================================================
    # QUALIFIED TEACHERS
    # ========================================================

    def qualified_teachers(self, subject_id):

        return [
            row[0]
            for row in self.db.conn.execute("""
                SELECT t.id
                FROM teachers t
                JOIN teacher_subjects ts
                    ON ts.teacher_id=t.id
                WHERE ts.subject_id=?
                ORDER BY t.name
            """, (subject_id,))
        ]

    # ========================================================
    # BUILD NORMALIZED GENERATION TASKS
    # ========================================================

    def build_generation_tasks(self):

        programs = self.db.conn.execute("""
            SELECT id, name, year, section
            FROM programs
            ORDER BY year, name, section
        """).fetchall()

        # key = (program_id, subject_id)
        fixed_teacher = {}

        requested_periods = {}

        errors = []

        # ----------------------------------------------------
        # TEACHER SELECTIONS SAVED WITH EACH CLASS / SECTION
        # ----------------------------------------------------
        # These assignments come directly from Step 3 (Add Class /
        # Section). They are persistent and therefore survive
        # application restarts.
        persistent_assignments = self.db.conn.execute("""
            SELECT program_id, subject_id, teacher_id
            FROM program_teacher_assignments
        """).fetchall()

        for pid, sid, tid in persistent_assignments:
            key = (pid, sid)
            fixed_teacher[key] = tid

        # ----------------------------------------------------
        # CLASS CONFIGURATION
        # ----------------------------------------------------

        for pid, assignments in self.class_generation_config.items():

            for sid, tid, periods in assignments:

                key = (
                    pid,
                    sid
                )

                if key in fixed_teacher:

                    old_tid = fixed_teacher[key]

                    if old_tid != tid:

                        errors.append(
                            f"Conflict: {self.program_text(pid)} "
                            f"{self.subject_text(sid)} has two different teachers."
                        )

                        continue

                fixed_teacher[key] = tid
                requested_periods[key] = periods

        # ----------------------------------------------------
        # TEACHER CONFIGURATION
        # ----------------------------------------------------

        for tid, assignments in self.teacher_generation_config.items():

            for pid, sid, periods in assignments:

                key = (
                    pid,
                    sid
                )

                if key in fixed_teacher:

                    if fixed_teacher[key] != tid:

                        errors.append(
                            f"Conflict: {self.program_text(pid)} "
                            f"{self.subject_text(sid)} is assigned to "
                            f"two different teachers."
                        )

                        continue

                fixed_teacher[key] = tid
                requested_periods[key] = periods

        # ----------------------------------------------------
        # VALIDATE TEACHERS
        # ----------------------------------------------------

        for (
            key,
            tid
        ) in fixed_teacher.items():

            pid, sid = key

            qualified = self.db.conn.execute("""
                SELECT COUNT(*)
                FROM teacher_subjects
                WHERE teacher_id=?
                  AND subject_id=?
            """, (
                tid,
                sid
            )).fetchone()[0]

            if not qualified:

                errors.append(
                    f"{self.teacher_text(tid)} cannot teach "
                    f"{self.subject_text(sid)}."
                )

        # ----------------------------------------------------
        # BUILD TASKS
        # ----------------------------------------------------

        all_tasks = []

        for pid, pname, year, section in programs:

            subject_rows = self.db.conn.execute("""
                SELECT
                    ps.subject_id,
                    s.name,
                    ps.periods_per_week
                FROM program_subjects ps
                JOIN subjects s
                    ON s.id=ps.subject_id
                WHERE ps.program_id=?
            """, (pid,)).fetchall()

            if not subject_rows:

                errors.append(
                    f"{self.program_text(pid)} has no subjects."
                )

                continue

            configured_keys = {
                key
                for key in requested_periods
                if key[0] == pid
            }

            for sid, sname, default_periods in subject_rows:

                key = (
                    pid,
                    sid
                )

                periods = requested_periods.get(
                    key,
                    default_periods
                )

                tid = fixed_teacher.get(
                    key
                )

                if tid is not None:

                    teacher_candidates = [
                        tid
                    ]

                else:

                    teacher_candidates = (
                        self.qualified_teachers(sid)
                    )

                if not teacher_candidates:

                    errors.append(
                        f"No qualified teacher available for "
                        f"{self.program_text(pid)} → {sname}."
                    )

                    continue

                for occurrence in range(periods):

                    all_tasks.append({
                        "pid": pid,
                        "sid": sid,
                        "sname": sname,
                        "teacher_fixed": tid is not None,
                        "teachers": list(teacher_candidates),
                        "occurrence": occurrence,
                        "total": periods
                    })

            # Configured subject that isn't in program_subjects
            for key in configured_keys:

                if not any(
                    row[0] == key[1]
                    for row in subject_rows
                ):

                    errors.append(
                        f"{self.subject_text(key[1])} is not "
                        f"assigned to {self.program_text(pid)} "
                        f"in Classes & Sections."
                    )

        return programs, all_tasks, errors

    # ========================================================
    # GENERATOR
    # ========================================================

    def generate_all(self):

        programs, tasks, errors = (
            self.build_generation_tasks()
        )

        if not programs:
            QMessageBox.warning(
                self,
                "No classes",
                "Add at least one class/section."
            )

            return

        days = working_days(self.db)

        slots = [
            s
            for s in build_slots(self.db)
            if not s["break"]
        ]

        if not days or not slots:
            QMessageBox.warning(
                self,
                "Settings",
                "Configure working days and periods."
            )

            return

        total_capacity = (
                len(days) *
                len(slots)
        )

        self.log.clear()

        # --------------------------------------------------------
        # DISPLAY VALIDATION ERRORS
        # --------------------------------------------------------

        for error in errors:
            self.log.addItem(
                "✗ " + error
            )

        if errors:

            answer = QMessageBox.question(
                self,
                "Configuration Problems",
                f"{len(errors)} configuration problem(s) found.\n\n"
                "Do you want to continue anyway?",
                QMessageBox.Yes |
                QMessageBox.No
            )

            if answer != QMessageBox.Yes:
                return

        # --------------------------------------------------------
        # CHECK CLASS CAPACITY
        # --------------------------------------------------------

        task_counts = defaultdict(int)

        for task in tasks:
            task_counts[
                task["pid"]
            ] += 1

        for pid, count in task_counts.items():

            if count > total_capacity:
                self.log.addItem(
                    f"✗ {self.program_text(pid)} requires "
                    f"{count} periods but only "
                    f"{total_capacity} periods are available."
                )

        # --------------------------------------------------------
        # CLEAR OLD TIMETABLE
        # --------------------------------------------------------

        self.db.execute(
            "DELETE FROM timetables"
        )

        # --------------------------------------------------------
        # GENERATE
        # --------------------------------------------------------

        success = self.solve_schedule(
            tasks,
            days,
            slots
        )

        if success:

            self.generated = True

            self.log.addItem("")
            self.log.addItem(
                "========================================"
            )
            self.log.addItem(
                "✓ TIMETABLE GENERATED SUCCESSFULLY"
            )
            self.log.addItem(
                f"✓ Classes: {len(programs)}"
            )
            self.log.addItem(
                f"✓ Scheduled periods: {len(tasks)}"
            )
            self.log.addItem(
                "✓ No teacher double-booking detected."
            )
            self.log.addItem(
                "✓ Class and teacher timetables are synchronized."
            )

            self.refresh_class_view()
            self.refresh_teacher_selector()

            # ====================================================
            # AUTOMATICALLY CREATE BOTH PDFs
            # ====================================================

            try:

                self.log.addItem("")
                self.log.addItem(
                    "Creating Class Timetables PDF..."
                )

                class_pdf, teacher_pdf = (
                    self.export_all_timetables_pdf()
                )

                self.log.addItem(
                    "✓ Class_Timetables.pdf created."
                )

                self.log.addItem(
                    "✓ Teacher_Timetables.pdf created."
                )

                self.log.addItem(
                    f"✓ PDF folder: {class_pdf.parent}"
                )

                QMessageBox.information(
                    self,
                    "Generation Complete",
                    "Timetable generated successfully.\n\n"
                    f"Classes: {len(programs)}\n"
                    f"Scheduled periods: {len(tasks)}\n\n"
                    "Two PDF files were created automatically:\n\n"
                    f"1. {class_pdf.name}\n"
                    f"2. {teacher_pdf.name}\n\n"
                    f"Location:\n{class_pdf.parent}"
                )

            except ImportError:

                QMessageBox.warning(
                    self,
                    "ReportLab Required",
                    "Timetable generated successfully, "
                    "but PDFs could not be created.\n\n"
                    "Install ReportLab with:\n\n"
                    "pip install reportlab"
                )

            except Exception as e:

                QMessageBox.warning(
                    self,
                    "PDF Error",
                    "Timetable was generated successfully, "
                    "but PDF creation failed.\n\n"
                    f"Error:\n{e}"
                )

        else:

            self.generated = False

            self.db.execute(
                "DELETE FROM timetables"
            )

            self.log.addItem("")
            self.log.addItem(
                "✗ GENERATION FAILED"
            )

            self.log.addItem(
                "The requested assignments could not fit "
                "into the available timetable."
            )

            self.log.addItem(
                "Try reducing weekly periods, adding teachers, "
                "or increasing available periods/days."
            )

            QMessageBox.warning(
                self,
                "Generation Failed",
                "A complete conflict-free timetable could not "
                "be generated.\n\n"
                "Check the Generation Log."
            )

            self.refresh_class_view()
            self.refresh_teacher_selector()

    # ========================================================
    # SCHEDULE SOLVER
    # ========================================================

    def solve_schedule(
        self,
        tasks,
        days,
        slots
    ):

        if not tasks:
            return True

        total_slots = len(days) * len(slots)

        # ----------------------------------------------------
        # Sort difficult tasks first
        # ----------------------------------------------------

        tasks = list(tasks)

        random.shuffle(tasks)

        tasks.sort(
            key=lambda task: (
                0 if task["teacher_fixed"] else 1,
                len(task["teachers"]),
                -task["total"]
            )
        )

        # ----------------------------------------------------
        # Multiple attempts
        # ----------------------------------------------------

        for attempt in range(350):

            class_used = defaultdict(set)
            teacher_used = defaultdict(set)

            assignments = []

            # Keep track of subject/day repetition.
            subject_day = defaultdict(
                lambda: defaultdict(int)
            )

            failed = False

            remaining = list(tasks)

            random.shuffle(remaining)

            # Hardest first every attempt.
            remaining.sort(
                key=lambda task: (
                    0 if task["teacher_fixed"] else 1,
                    len(task["teachers"]),
                    -task["total"]
                )
            )

            for task in remaining:

                pid = task["pid"]
                sid = task["sid"]

                candidates = []

                teacher_order = list(
                    task["teachers"]
                )

                random.shuffle(
                    teacher_order
                )

                for tid in teacher_order:

                    for day in days:

                        for slot in slots:

                            period = slot["number"]

                            class_key = (
                                day,
                                period
                            )

                            if class_key in class_used[pid]:
                                continue

                            teacher_key = (
                                day,
                                period
                            )

                            if teacher_key in teacher_used[tid]:
                                continue

                            candidates.append(
                                (
                                    day,
                                    period,
                                    tid
                                )
                            )

                if not candidates:

                    failed = True
                    break

                # ------------------------------------------------
                # Candidate scoring
                # ------------------------------------------------

                def candidate_score(candidate):

                    day, period, tid = candidate

                    same_subject_same_day = (
                        subject_day[
                            pid
                        ][
                            (sid, day)
                        ]
                    )

                    class_day_load = sum(
                        1
                        for d, p, t in assignments
                        if d == day and
                        p in class_used[pid]
                    )

                    teacher_day_load = sum(
                        1
                        for d, p, t in assignments
                        if d == day and
                        t == tid
                    )

                    # Prefer:
                    # 1. Less repetition of same subject on same day
                    # 2. Balanced class days
                    # 3. Balanced teacher workload
                    # 4. Random slight variation

                    return (
                        same_subject_same_day * 100,
                        class_day_load * 5,
                        teacher_day_load * 3,
                        random.random()
                    )

                candidates.sort(
                    key=candidate_score
                )

                chosen = candidates[0]

                day, period, tid = chosen

                assignments.append(
                    (
                        day,
                        period,
                        tid
                    )
                )

                class_used[pid].add(
                    (
                        day,
                        period
                    )
                )

                teacher_used[tid].add(
                    (
                        day,
                        period
                    )
                )

                subject_day[
                    pid
                ][
                    (sid, day)
                ] += 1

            if failed:
                continue

            # ----------------------------------------------------
            # Save complete solution
            # ----------------------------------------------------

            rows = []

            for task, assignment in zip(
                remaining,
                assignments
            ):

                day, period, tid = assignment

                rows.append(
                    (
                        task["pid"],
                        day,
                        period,
                        task["sid"],
                        tid
                    )
                )

            try:

                self.db.conn.execute(
                    "BEGIN"
                )

                self.db.conn.execute(
                    "DELETE FROM timetables"
                )

                self.db.conn.executemany("""
                    INSERT INTO timetables
                    (
                        program_id,
                        day,
                        slot,
                        subject_id,
                        teacher_id
                    )
                    VALUES (?,?,?,?,?)
                """, rows)

                self.db.conn.commit()

                return True

            except Exception:

                self.db.conn.rollback()

        return False

    # ========================================================
    # CLASS VIEW
    # ========================================================

    def build_class_view(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()

        self.class_view_selector = QComboBox()

        self.class_view_selector.currentIndexChanged.connect(
            self.refresh_class_view
        )

        top.addWidget(
            QLabel("Class / Section:")
        )

        top.addWidget(
            self.class_view_selector
        )

        top.addStretch()

        export = QPushButton(
            "Export Class PDF"
        )

        export.clicked.connect(
            self.export_class_pdf
        )

        top.addWidget(
            export
        )

        layout.addLayout(top)

        self.class_table = QTableWidget()

        self.class_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
        )

        self.class_table.cellDoubleClicked.connect(
            self.edit_class_cell
        )

        layout.addWidget(
            self.class_table
        )

        layout.addWidget(
            QLabel(
                "Double-click a cell to manually change "
                "the subject or teacher."
            )
        )

        self.tabs.addTab(
            page,
            "Class Timetable"
        )

    def refresh_class_selector(self):

        current = self.class_view_selector.currentData()

        self.class_view_selector.blockSignals(
            True
        )

        self.class_view_selector.clear()

        rows = self.db.conn.execute("""
            SELECT id, name, year, section
            FROM programs
            ORDER BY year, name, section
        """).fetchall()

        for pid, name, year, section in rows:

            self.class_view_selector.addItem(
                f"{year} | {name} | Section {section}",
                pid
            )

        if current is not None:

            index = self.class_view_selector.findData(
                current
            )

            if index >= 0:

                self.class_view_selector.setCurrentIndex(
                    index
                )

        self.class_view_selector.blockSignals(
            False
        )

    def refresh_class_view(self):

        self.refresh_class_selector()

        pid = self.class_view_selector.currentData()

        self.class_table.clear()

        if pid is None:

            self.class_table.setRowCount(
                0
            )

            return

        days = working_days(
            self.db
        )

        slots = build_slots(
            self.db
        )

        self.class_table.setColumnCount(
            len(days) + 1
        )

        self.class_table.setHorizontalHeaderLabels(
            ["Time"] + days
        )

        self.class_table.setRowCount(
            len(slots)
        )

        self.class_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        for col in range(
            1,
            len(days) + 1
        ):

            self.class_table.horizontalHeader().setSectionResizeMode(
                col,
                QHeaderView.Stretch
            )

        for row, slot in enumerate(slots):

            self.class_table.setItem(
                row,
                0,
                table_item(
                    slot["label"],
                    True
                )
            )

            if slot["break"]:

                for col in range(
                    1,
                    len(days) + 1
                ):

                    self.class_table.setItem(
                        row,
                        col,
                        table_item(
                            "BREAK",
                            True
                        )
                    )

                continue

            period_number = self.actual_slot_number(
                slots,
                row
            )

            for col, day in enumerate(
                days,
                start=1
            ):

                result = self.db.conn.execute("""
                    SELECT
                        s.name,
                        t.name,
                        t.id,
                        s.id
                    FROM timetables tt
                    LEFT JOIN subjects s
                        ON s.id=tt.subject_id
                    LEFT JOIN teachers t
                        ON t.id=tt.teacher_id
                    WHERE tt.program_id=?
                      AND tt.day=?
                      AND tt.slot=?
                """, (
                    pid,
                    day,
                    period_number
                )).fetchone()

                if result and result[0]:

                    text = (
                        f"{result[0]}\n"
                        f"{result[1] or 'No teacher'}"
                    )

                    item = table_item(
                        text
                    )

                    item.setData(
                        Qt.UserRole,
                        (
                            pid,
                            day,
                            period_number,
                            result[3],
                            result[2]
                        )
                    )

                else:

                    item = table_item(
                        "FREE"
                    )

                    item.setData(
                        Qt.UserRole,
                        (
                            pid,
                            day,
                            period_number,
                            None,
                            None
                        )
                    )

                self.class_table.setItem(
                    row,
                    col,
                    item
                )

    @staticmethod
    def actual_slot_number(
        slots,
        row
    ):

        count = 0

        for index in range(
            row + 1
        ):

            if not slots[index]["break"]:
                count += 1

        return count

    # ========================================================
    # MANUAL EDIT
    # ========================================================

    def edit_class_cell(
        self,
        row,
        col
    ):

        if col == 0:
            return

        item = self.class_table.item(
            row,
            col
        )

        if not item:
            return

        data = item.data(
            Qt.UserRole
        )

        if not data:
            return

        (
            pid,
            day,
            slot,
            old_sid,
            old_tid
        ) = data

        dialog = QDialog(
            self
        )

        dialog.setWindowTitle(
            "Edit Timetable Cell"
        )

        dialog.resize(
            500,
            220
        )

        form = QFormLayout(
            dialog
        )

        subjects = QComboBox()

        subjects.addItem(
            "FREE",
            None
        )

        subject_rows = self.db.conn.execute("""
            SELECT s.id, s.name
            FROM program_subjects ps
            JOIN subjects s
                ON s.id=ps.subject_id
            WHERE ps.program_id=?
            ORDER BY s.name
        """, (pid,)).fetchall()

        for sid, name in subject_rows:

            subjects.addItem(
                name,
                sid
            )

        if old_sid:

            index = subjects.findData(
                old_sid
            )

            if index >= 0:
                subjects.setCurrentIndex(
                    index
                )

        teachers = QComboBox()

        def load_teachers():

            teachers.clear()

            teachers.addItem(
                "No teacher",
                None
            )

            sid = subjects.currentData()

            if sid:

                rows = self.db.conn.execute("""
                    SELECT t.id, t.name
                    FROM teachers t
                    JOIN teacher_subjects ts
                        ON ts.teacher_id=t.id
                    WHERE ts.subject_id=?
                    ORDER BY t.name
                """, (sid,)).fetchall()

                for tid, name in rows:

                    teachers.addItem(
                        name,
                        tid
                    )

        subjects.currentIndexChanged.connect(
            load_teachers
        )

        load_teachers()

        if old_tid:

            index = teachers.findData(
                old_tid
            )

            if index >= 0:

                teachers.setCurrentIndex(
                    index
                )

        form.addRow(
            "Subject:",
            subjects
        )

        form.addRow(
            "Teacher:",
            teachers
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            dialog.accept
        )

        buttons.rejected.connect(
            dialog.reject
        )

        form.addRow(
            buttons
        )

        if dialog.exec_():

            sid = subjects.currentData()
            tid = teachers.currentData()

            if sid and tid:

                conflict = self.db.conn.execute("""
                    SELECT COUNT(*)
                    FROM timetables
                    WHERE day=?
                      AND slot=?
                      AND teacher_id=?
                      AND program_id<>?
                """, (
                    day,
                    slot,
                    tid,
                    pid
                )).fetchone()[0]

                if conflict:

                    QMessageBox.warning(
                        self,
                        "Teacher Conflict",
                        "This teacher is already teaching "
                        "another class at this time."
                    )

                    return

            self.db.execute("""
                DELETE FROM timetables
                WHERE program_id=?
                  AND day=?
                  AND slot=?
            """, (
                pid,
                day,
                slot
            ))

            if sid:

                self.db.execute("""
                    INSERT INTO timetables
                    (
                        program_id,
                        day,
                        slot,
                        subject_id,
                        teacher_id
                    )
                    VALUES(?,?,?,?,?)
                """, (
                    pid,
                    day,
                    slot,
                    sid,
                    tid
                ))

            self.refresh_class_view()
            self.refresh_teacher_view()

    # ========================================================
    # TEACHER VIEW
    # ========================================================

    def build_teacher_view(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()

        self.teacher_selector = QComboBox()

        self.teacher_selector.currentIndexChanged.connect(
            self.refresh_teacher_view
        )

        top.addWidget(
            QLabel("Teacher:")
        )

        top.addWidget(
            self.teacher_selector
        )

        top.addStretch()

        export = QPushButton(
            "Export Teacher PDF"
        )

        export.clicked.connect(
            self.export_teacher_pdf
        )

        top.addWidget(
            export
        )

        layout.addLayout(top)

        self.teacher_table_view = QTableWidget()

        layout.addWidget(
            self.teacher_table_view
        )

        self.tabs.addTab(
            page,
            "Teacher Timetable"
        )

    def refresh_teacher_selector(self):

        current = self.teacher_selector.currentData()

        self.teacher_selector.blockSignals(
            True
        )

        self.teacher_selector.clear()

        rows = self.db.conn.execute("""
            SELECT id, name
            FROM teachers
            ORDER BY name
        """).fetchall()

        for tid, name in rows:

            self.teacher_selector.addItem(
                name,
                tid
            )

        if current is not None:

            index = self.teacher_selector.findData(
                current
            )

            if index >= 0:

                self.teacher_selector.setCurrentIndex(
                    index
                )

        self.teacher_selector.blockSignals(
            False
        )

        self.refresh_teacher_view()

    def refresh_teacher_view(self):

        tid = self.teacher_selector.currentData()

        days = working_days(
            self.db
        )

        slots = build_slots(
            self.db
        )

        self.teacher_table_view.setColumnCount(
            len(days) + 1
        )

        self.teacher_table_view.setHorizontalHeaderLabels(
            ["Time"] + days
        )

        self.teacher_table_view.setRowCount(
            len(slots)
        )

        self.teacher_table_view.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        for col in range(
            1,
            len(days) + 1
        ):

            self.teacher_table_view.horizontalHeader().setSectionResizeMode(
                col,
                QHeaderView.Stretch
            )

        for row, slot in enumerate(slots):

            self.teacher_table_view.setItem(
                row,
                0,
                table_item(
                    slot["label"],
                    True
                )
            )

            if slot["break"]:

                for col in range(
                    1,
                    len(days) + 1
                ):

                    self.teacher_table_view.setItem(
                        row,
                        col,
                        table_item(
                            "BREAK",
                            True
                        )
                    )

                continue

            period_number = self.actual_slot_number(
                slots,
                row
            )

            for col, day in enumerate(
                days,
                start=1
            ):

                result = self.db.conn.execute("""
                    SELECT
                        p.year,
                        p.name,
                        p.section,
                        s.name
                    FROM timetables tt
                    JOIN programs p
                        ON p.id=tt.program_id
                    LEFT JOIN subjects s
                        ON s.id=tt.subject_id
                    WHERE tt.teacher_id=?
                      AND tt.day=?
                      AND tt.slot=?
                """, (
                    tid,
                    day,
                    period_number
                )).fetchone()

                if result:

                    text = (
                        f"{result[3] or ''}\n"
                        f"{result[1]} {result[2]} "
                        f"({result[0]})"
                    )

                else:

                    text = "FREE"

                self.teacher_table_view.setItem(
                    row,
                    col,
                    table_item(text)
                )

    def export_all_timetables_pdf(self):

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle
        )
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
            PageBreak
        )

        # ========================================================
        # OUTPUT FOLDER
        # ========================================================

        output_folder = Path(__file__).with_name(
            "Generated_Timetables"
        )

        output_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        class_pdf = output_folder / "Class_Timetables.pdf"
        teacher_pdf = output_folder / "Teacher_Timetables.pdf"

        college = self.db.settings()[1]

        days = working_days(
            self.db
        )

        slots = build_slots(
            self.db
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "TimetableTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=18,
            leading=22,
            spaceAfter=6
        )

        subtitle_style = ParagraphStyle(
            "TimetableSubtitle",
            parent=styles["Heading2"],
            alignment=TA_CENTER,
            fontSize=12,
            leading=15,
            spaceAfter=10
        )

        cell_style = ParagraphStyle(
            "TimetableCell",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=7.5,
            leading=9
        )

        header_style = ParagraphStyle(
            "TimetableHeader",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=8,
            leading=10
        )

        # ========================================================
        # HELPER TO CREATE TABLE
        # ========================================================

        def build_table(mode, target_id):

            data = []

            header = [
                Paragraph("Time", header_style)
            ]

            for day in days:
                header.append(
                    Paragraph(day, header_style)
                )

            data.append(header)

            for row, slot in enumerate(slots):

                # ------------------------------------------------
                # BREAK
                # ------------------------------------------------

                if slot["break"]:

                    break_row = [
                        Paragraph(
                            "BREAK",
                            cell_style
                        )
                    ]

                    for _ in days:
                        break_row.append(
                            Paragraph(
                                "BREAK",
                                cell_style
                            )
                        )

                    data.append(
                        break_row
                    )

                    continue

                period_number = self.actual_slot_number(
                    slots,
                    row
                )

                row_data = [
                    Paragraph(
                        slot["label"],
                        cell_style
                    )
                ]

                for day in days:

                    # ============================================
                    # CLASS TIMETABLE
                    # ============================================

                    if mode == "class":

                        result = self.db.conn.execute("""
                            SELECT
                                s.name,
                                t.name
                            FROM timetables tt
                            LEFT JOIN subjects s
                                ON s.id = tt.subject_id
                            LEFT JOIN teachers t
                                ON t.id = tt.teacher_id
                            WHERE tt.program_id = ?
                              AND tt.day = ?
                              AND tt.slot = ?
                        """, (
                            target_id,
                            day,
                            period_number
                        )).fetchone()

                        if result and result[0]:

                            subject_name = (
                                    result[0]
                                    or ""
                            )

                            teacher_name = (
                                    result[1]
                                    or "No teacher"
                            )

                            text = (
                                f"<b>{subject_name}</b><br/>"
                                f"{teacher_name}"
                            )

                        else:

                            text = "FREE"

                    # ============================================
                    # TEACHER TIMETABLE
                    # ============================================

                    else:

                        result = self.db.conn.execute("""
                            SELECT
                                p.year,
                                p.name,
                                p.section,
                                s.name
                            FROM timetables tt
                            JOIN programs p
                                ON p.id = tt.program_id
                            LEFT JOIN subjects s
                                ON s.id = tt.subject_id
                            WHERE tt.teacher_id = ?
                              AND tt.day = ?
                              AND tt.slot = ?
                        """, (
                            target_id,
                            day,
                            period_number
                        )).fetchone()

                        if result:

                            year = result[0]
                            program = result[1]
                            section = result[2]
                            subject = result[3] or ""

                            text = (
                                f"<b>{subject}</b><br/>"
                                f"{year} {program}<br/>"
                                f"Section {section}"
                            )

                        else:

                            text = "FREE"

                    row_data.append(
                        Paragraph(
                            text,
                            cell_style
                        )
                    )

                data.append(
                    row_data
                )

            table = Table(
                data,
                repeatRows=1
            )

            table.setStyle(
                TableStyle([
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.lightgrey
                    ),
                    (
                        "BACKGROUND",
                        (0, 1),
                        (0, -1),
                        colors.whitesmoke
                    ),
                    (
                        "ALIGN",
                        (0, 0),
                        (-1, -1),
                        "CENTER"
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE"
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold"
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        7
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        7
                    )
                ])
            )

            return table

        # ========================================================
        # CLASS PDF
        # ========================================================

        class_doc = SimpleDocTemplate(
            str(class_pdf),
            pagesize=landscape(A4),
            rightMargin=20,
            leftMargin=20,
            topMargin=20,
            bottomMargin=20
        )

        class_story = []

        programs = self.db.conn.execute("""
            SELECT id, name, year, section
            FROM programs
            ORDER BY year, name, section
        """).fetchall()

        for index, (
                pid,
                name,
                year,
                section
        ) in enumerate(programs):

            class_story.append(
                Paragraph(
                    college,
                    title_style
                )
            )

            class_story.append(
                Paragraph(
                    "Class Timetable",
                    subtitle_style
                )
            )

            class_story.append(
                Paragraph(
                    f"{year} | {name} | Section {section}",
                    subtitle_style
                )
            )

            class_story.append(
                Spacer(1, 8)
            )

            class_story.append(
                build_table(
                    "class",
                    pid
                )
            )

            if index < len(programs) - 1:
                class_story.append(
                    PageBreak()
                )

        class_doc.build(
            class_story
        )

        # ========================================================
        # TEACHER PDF
        # ========================================================

        teacher_doc = SimpleDocTemplate(
            str(teacher_pdf),
            pagesize=landscape(A4),
            rightMargin=20,
            leftMargin=20,
            topMargin=20,
            bottomMargin=20
        )

        teacher_story = []

        teachers = self.db.conn.execute("""
            SELECT id, name
            FROM teachers
            ORDER BY name
        """).fetchall()

        for index, (
                tid,
                teacher_name
        ) in enumerate(teachers):

            teacher_story.append(
                Paragraph(
                    college,
                    title_style
                )
            )

            teacher_story.append(
                Paragraph(
                    "Teacher Timetable",
                    subtitle_style
                )
            )

            teacher_story.append(
                Paragraph(
                    teacher_name,
                    subtitle_style
                )
            )

            teacher_story.append(
                Spacer(1, 8)
            )

            teacher_story.append(
                build_table(
                    "teacher",
                    tid
                )
            )

            if index < len(teachers) - 1:
                teacher_story.append(
                    PageBreak()
                )

        teacher_doc.build(
            teacher_story
        )

        return class_pdf, teacher_pdf

    # ========================================================
    # PDF EXPORT
    # ========================================================

    def export_class_pdf(self):

        pid = self.class_view_selector.currentData()

        if pid is None:

            QMessageBox.warning(
                self,
                "No class",
                "Select a class."
            )

            return

        row = self.db.conn.execute("""
            SELECT name, year, section
            FROM programs
            WHERE id=?
        """, (pid,)).fetchone()

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Class PDF",
            f"{row[1]}_{row[0]}_{row[2]}_timetable.pdf",
            "PDF Files (*.pdf)"
        )

        if not path:
            return

        try:

            self.create_pdf(
                path,
                "class",
                pid
            )

            QMessageBox.information(
                self,
                "Exported",
                f"PDF saved:\n{path}"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "PDF Error",
                f"Could not create PDF.\n\n{e}\n\n"
                "Install ReportLab with:\n"
                "pip install reportlab"
            )

    def export_teacher_pdf(self):

        tid = self.teacher_selector.currentData()

        if tid is None:

            QMessageBox.warning(
                self,
                "No teacher",
                "Select a teacher."
            )

            return

        row = self.db.conn.execute("""
            SELECT name
            FROM teachers
            WHERE id=?
        """, (tid,)).fetchone()

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Teacher PDF",
            f"{row[0]}_timetable.pdf",
            "PDF Files (*.pdf)"
        )

        if not path:
            return

        try:

            self.create_pdf(
                path,
                "teacher",
                tid
            )

            QMessageBox.information(
                self,
                "Exported",
                f"PDF saved:\n{path}"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "PDF Error",
                f"Could not create PDF.\n\n{e}\n\n"
                "Install ReportLab with:\n"
                "pip install reportlab"
            )

    def create_pdf(
        self,
        path,
        mode,
        target_id
    ):

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import (
            landscape,
            A4
        )
        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle
        )
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer
        )

        college = self.db.settings()[1]

        days = working_days(
            self.db
        )

        slots = build_slots(
            self.db
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "TitleCustom",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=18
        )

        cell_style = ParagraphStyle(
            "Cell",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=7.5,
            leading=9
        )

        doc = SimpleDocTemplate(
            path,
            pagesize=landscape(A4),
            rightMargin=20,
            leftMargin=20,
            topMargin=20,
            bottomMargin=20
        )

        story = [
            Paragraph(
                college,
                title_style
            )
        ]

        if mode == "class":

            name, year, section = self.db.conn.execute("""
                SELECT name, year, section
                FROM programs
                WHERE id=?
            """, (target_id,)).fetchone()

            story.append(
                Paragraph(
                    f"Class Timetable — "
                    f"{year} {name} — Section {section}",
                    title_style
                )
            )

        else:

            name = self.db.conn.execute("""
                SELECT name
                FROM teachers
                WHERE id=?
            """, (target_id,)).fetchone()[0]

            story.append(
                Paragraph(
                    f"Teacher Timetable — {name}",
                    title_style
                )
            )

        story.append(
            Spacer(1, 10)
        )

        data = [
            ["Time"] + days
        ]

        for row, slot in enumerate(slots):

            if slot["break"]:

                data.append(
                    [
                        slot["label"]
                    ] +
                    ["BREAK"] * len(days)
                )

                continue

            period_number = self.actual_slot_number(
                slots,
                row
            )

            cells = [
                slot["label"]
            ]

            for day in days:

                if mode == "class":

                    result = self.db.conn.execute("""
                        SELECT
                            s.name,
                            t.name
                        FROM timetables tt
                        LEFT JOIN subjects s
                            ON s.id=tt.subject_id
                        LEFT JOIN teachers t
                            ON t.id=tt.teacher_id
                        WHERE tt.program_id=?
                          AND tt.day=?
                          AND tt.slot=?
                    """, (
                        target_id,
                        day,
                        period_number
                    )).fetchone()

                    if not result or not result[0]:

                        text = "FREE"

                    else:

                        text = (
                            f"{result[0]}<br/>"
                            f"{result[1] or 'No teacher'}"
                        )

                else:

                    result = self.db.conn.execute("""
                        SELECT
                            p.year,
                            p.name,
                            p.section,
                            s.name
                        FROM timetables tt
                        JOIN programs p
                            ON p.id=tt.program_id
                        LEFT JOIN subjects s
                            ON s.id=tt.subject_id
                        WHERE tt.teacher_id=?
                          AND tt.day=?
                          AND tt.slot=?
                    """, (
                        target_id,
                        day,
                        period_number
                    )).fetchone()

                    if not result:

                        text = "FREE"

                    else:

                        text = (
                            f"{result[3] or ''}<br/>"
                            f"{result[1]} {result[2]} "
                            f"({result[0]})"
                        )

                cells.append(
                    Paragraph(
                        text,
                        cell_style
                    )
                )

            data.append(
                cells
            )

        table = Table(
            data,
            repeatRows=1
        )

        table.setStyle(
            TableStyle([
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER"
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold"
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8
                ),
                (
                    "BACKGROUND",
                    (0, 1),
                    (0, -1),
                    colors.whitesmoke
                )
            ])
        )

        story.append(
            table
        )

        doc.build(
            story
        )

    # ========================================================
    # REFRESH
    # ========================================================

    def refresh_all(self):

        self.load_settings()

        self.refresh_subjects()

        self.refresh_teachers()

        self.refresh_programs()

        self.refresh_class_view()

        self.refresh_teacher_selector()

        self.refresh_generation_lists()

    # ========================================================
    # STYLE
    # ========================================================

    def apply_style(self):

        self.setStyleSheet("""
        QMainWindow, QWidget {
            background: #121212;
            color: #eeeeee;
            font-family: Segoe UI, Arial;
            font-size: 15px;
        }

        QTabWidget::pane {
            border: 1px solid #333333;
            background: #161616;
        }

        QTabBar::tab {
            background: #242424;
            color: #eeeeee;
            padding: 14px 24px;
            margin-right: 2px;
            font-size: 15px;
            min-height: 25px;
        }

        QTabBar::tab:selected {
            background: #00a8e8;
            color: white;
        }

        QPushButton {
            background: #2d2d2d;
            border: 1px solid #444444;
            border-radius: 5px;
            padding: 10px 18px;
            min-height: 42px;
            font-size: 15px;
        }

        QPushButton:hover {
            background: #3a3a3a;
        }

        QPushButton#GenerateButton {
            background: #007acc;
            font-size: 17px;
            font-weight: bold;
            padding: 14px 20px;
            min-height: 48px;
        }

        QLineEdit,
        QComboBox,
        QSpinBox,
        QTimeEdit,
        QListWidget,
        QTableWidget,
        QTextEdit {
            background: #1e1e1e;
            border: 1px solid #3d3d3d;
            border-radius: 4px;
            padding: 7px;
            color: #eeeeee;
            font-size: 15px;
        }

        QLineEdit,
        QComboBox,
        QSpinBox,
        QTimeEdit {
            min-height: 38px;
        }

        QTableWidget {
            gridline-color: #444444;
            font-size: 15px;
        }

        QHeaderView::section {
            background: #2d2d2d;
            color: white;
            padding: 10px;
            border: 1px solid #444444;
            font-weight: bold;
            font-size: 15px;
        }

        QGroupBox {
            background: #1e1e1e;
            border: 1px solid #3d3d3d;
            border-radius: 7px;
            margin-top: 14px;
            padding: 18px;
            font-size: 16px;
            font-weight: bold;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            font-weight: bold;
            font-size: 16px;
        }

        QLabel {
            font-size: 15px;
        }

        QLabel#Title {
            font-size: 32px;
            font-weight: bold;
        }

        QLabel#Subtitle {
            color: #aaaaaa;
            font-size: 17px;
        }

        QLabel#CardNumber {
            font-size: 32px;
            font-weight: bold;
        }

        QLabel#Info {
            background: #1e1e1e;
            padding: 22px;
            border-radius: 8px;
            font-size: 16px;
        }

        QLabel#SectionTitle {
            font-size: 24px;
            font-weight: bold;
        }

        QCheckBox {
            font-size: 15px;
            spacing: 8px;
        }

        QListWidget {
            padding: 6px;
        }

        QListWidget::item {
            padding: 8px;
            min-height: 30px;
        }

        QTableWidget::item {
            padding: 7px;
        }

        QTextEdit {
            font-size: 15px;
            padding: 8px;
        }
        """)

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(self, event):

        self.db.close()

        event.accept()


# ============================================================
# START
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    app.setFont(QFont("Segoe UI", 12))

    app.setApplicationName(
        APP_NAME
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec_()
    )


if __name__ == "__main__":
    main()