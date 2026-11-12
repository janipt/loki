#!/usr/bin/env python3
"""Loki 0.3: read-only journal browser for KDE / CachyOS.

Qt table model keeps data in Python instead of allocating a widget item for
all four columns of every row. Both journal queries and boot enumeration run
outside the UI thread. Timing labels help diagnose unexpected stalls.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QTableView, QTextEdit, QVBoxLayout, QWidget,
)

PRIORITIES = ["Hätätila", "Hälytys", "Kriittinen", "Virhe", "Varoitus", "Huomautus", "Tiedote", "Debug"]
COLOR_ERROR = QColor("#e35b64")
COLOR_WARNING = QColor("#e4a54d")


def run_journal(args, timeout=25):
    return subprocess.run(
        ["journalctl", "--no-pager", *args],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )


class JournalWorker(QThread):
    # records, error, subprocess duration (s), JSON processing duration (s)
    loaded = Signal(object, str, float, float)

    def __init__(self, boot, max_priority, kernel_only, count, parent=None):
        super().__init__(parent)
        self.boot = boot
        self.max_priority = max_priority
        self.kernel_only = kernel_only
        self.count = count

    def run(self):
        args = ["--boot", self.boot, "--output=json", "--reverse", "--lines", str(self.count)]
        if self.max_priority is not None:
            args += ["--priority", str(self.max_priority)]
        if self.kernel_only:
            args.append("--dmesg")

        start = perf_counter()
        try:
            result = run_journal(args)
            read_seconds = perf_counter() - start
            parse_start = perf_counter()
            records = []
            for line in result.stdout.splitlines():
                try:
                    item = json.loads(line)
                    microseconds = int(item.get("__REALTIME_TIMESTAMP", 0))
                    timestamp = (
                        datetime.fromtimestamp(microseconds / 1_000_000).strftime("%Y-%m-%d %H:%M:%S")
                        if microseconds else "?"
                    )
                    priority = int(item.get("PRIORITY", 6))
                    source = str(item.get("_SYSTEMD_UNIT") or item.get("SYSLOG_IDENTIFIER")
                                 or item.get("_COMM") or "kernel")
                    message = str(item.get("MESSAGE", ""))
                    records.append({
                        "time": timestamp,
                        "priority": priority,
                        "source": source,
                        "message": message,
                        "searchable": (timestamp + " " + source + " " + message).casefold(),
                        "raw": item,
                    })
                except (ValueError, TypeError, OverflowError, OSError):
                    continue
            error = result.stderr.strip() if result.returncode else ""
            if result.returncode and not error:
                error = f"journalctl päättyi virhekoodiin {result.returncode}"
            self.loaded.emit(records, error, read_seconds, perf_counter() - parse_start)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.loaded.emit([], str(exc), perf_counter() - start, 0.0)


class BootsWorker(QThread):
    ready = Signal(object)

    def run(self):
        try:
            result = run_journal(["--list-boots", "--no-legend"], timeout=10)
            boots = []
            seen = {"0", "-1"}
            for line in reversed(result.stdout.splitlines()):
                parts = line.strip().split(maxsplit=2)
                if len(parts) < 3:
                    continue
                offset = parts[0]
                if offset in seen or not (offset.startswith("-") and offset[1:].isdigit()):
                    continue
                boots.append((f"Käynnistys {offset}: {parts[2][:22]}", offset))
                seen.add(offset)
            self.ready.emit(boots)
        except (OSError, subprocess.TimeoutExpired):
            self.ready.emit([])


class JournalModel(QAbstractTableModel):
    HEADERS = ["Aika", "Taso", "Lähde", "Viesti"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        if role == Qt.DisplayRole:
            c = index.column()
            if c == 0:
                return record["time"]
            if c == 1:
                p = record["priority"]
                return PRIORITIES[p] if 0 <= p < len(PRIORITIES) else "?"
            if c == 2:
                return record["source"]
            if c == 3:
                return record["message"].replace("\n", " ⏎ ")
        if role == Qt.ForegroundRole:
            p = record["priority"]
            return COLOR_ERROR if p <= 3 else COLOR_WARNING if p == 4 else None
        return None

    def set_records(self, records):
        self.beginResetModel()
        self.records = records
        self.endResetModel()


class SearchProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.term = ""

    def set_term(self, value):
        normalized = value.strip().casefold()
        if normalized != self.term:
            self.term = normalized
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.term:
            return True
        return self.term in self.sourceModel().records[source_row]["searchable"]


class Loki(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loki 0.3 | systemd-lokiselain")
        icon_path = Path(__file__).resolve().parent / "loki-journal.svg"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1250, 760)
        self.worker = None
        self.boot_worker = None
        self._refresh_pending = False
        self._closing = False
        self._last_pulse = perf_counter()
        self._max_stall = 0.0
        self._load_started = 0.0

        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.boot = QComboBox()
        self.boot.setMinimumWidth(240)
        self.boot.addItem("Nykyinen käynnistys", "0")
        self.boot.addItem("Edellinen käynnistys", "-1")
        top.addWidget(QLabel("Käynnistys:"))
        top.addWidget(self.boot)

        self.level = QComboBox()
        self.level.addItem("Kaikki tasot", None)
        self.level.addItem("Vain virheet ja vakavammat", 3)
        self.level.addItem("Varoitukset ja vakavammat", 4)
        self.level.setCurrentIndex(1)
        top.addWidget(QLabel("Vakavuus:"))
        top.addWidget(self.level)

        self.scope = QComboBox()
        self.scope.addItems(["Kaikki lähteet", "Vain kernel"])
        top.addWidget(self.scope)
        self.limit = QSpinBox()
        self.limit.setRange(100, 20000)
        self.limit.setSingleStep(500)
        self.limit.setValue(2000)
        self.limit.setSuffix(" riviä")
        top.addWidget(self.limit)
        self.refresh_button = QPushButton("Päivitä")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)

        filterbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hae näkyvistä riveistä: amdgpu, nvme, timeout, ...")
        self.search.setClearButtonEnabled(True)
        filterbar.addWidget(self.search)
        export = QPushButton("Vie näkyvät TXT-tiedostoon")
        export.clicked.connect(self.export)
        filterbar.addWidget(export)
        layout.addLayout(filterbar)

        splitter = QSplitter(Qt.Vertical)
        self.model = JournalModel(self)
        self.proxy = SearchProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 145)
        self.table.setColumnWidth(1, 85)
        self.table.setColumnWidth(2, 180)
        self.table.selectionModel().currentChanged.connect(self.show_detail)
        splitter.addWidget(self.table)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Valitse lokirivi. Tarkat tiedot näkyvät tässä.")
        self.detail.setFont(QFont("monospace", 10))
        splitter.addWidget(self.detail)
        splitter.setSizes([540, 170])
        layout.addWidget(splitter)

        bottom = QHBoxLayout()
        self.status = QLabel("Valmis")
        bottom.addWidget(self.status, 1)
        self.metrics = QLabel("")
        bottom.addWidget(self.metrics)
        self.stall = QLabel("UI: ok")
        self.stall.setToolTip("Sovelluksen käyttöliittymän pisin havaittu viive (ajastimen ylitys)")
        bottom.addWidget(self.stall)
        layout.addLayout(bottom)
        self.setCentralWidget(root)

        self.boot.currentIndexChanged.connect(self.refresh)
        self.level.currentIndexChanged.connect(self.refresh)
        self.scope.currentIndexChanged.connect(self.refresh)
        self.limit.valueChanged.connect(self.refresh)
        self.search.textChanged.connect(self.filter_rows)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)

        self.pulse = QTimer(self)
        self.pulse.setInterval(100)
        self.pulse.timeout.connect(self.heartbeat)
        self.pulse.start()
        self.refresh()
        self.load_boots_async()

    def load_boots_async(self):
        self.boot_worker = BootsWorker(self)
        self.boot_worker.ready.connect(self.receive_boots)
        self.boot_worker.finished.connect(self.maybe_close)
        self.boot_worker.start()

    def receive_boots(self, boots):
        self.boot.blockSignals(True)
        try:
            for title, offset in boots:
                self.boot.addItem(title, offset)
        finally:
            self.boot.blockSignals(False)

    def heartbeat(self):
        current = perf_counter()
        delay = max(0.0, current - self._last_pulse - 0.1)
        self._last_pulse = current
        if delay > self._max_stall:
            self._max_stall = delay
            if delay >= 0.3:
                self.stall.setText(f"UI-viive: {delay:.1f} s")
                self.stall.setToolTip("Qt:n tapahtumasilmukka ei ehtinyt käsitellä ajastinta normaalisti")

    def refresh(self, *_):
        if self._closing:
            return
        if self.worker is not None and self.worker.isRunning():
            self._refresh_pending = True
            self.status.setText("Asetukset muuttuivat: päivitetään haun valmistuttua...")
            return
        self._refresh_pending = False
        self._max_stall = 0.0
        self._last_pulse = perf_counter()
        self.stall.setText("UI: ok")
        self.metrics.setText("")
        self.status.setText("Luetaan journalia...")
        self.refresh_button.setEnabled(False)
        self._load_started = perf_counter()
        self.worker = JournalWorker(
            self.boot.currentData(), self.level.currentData(),
            self.scope.currentIndex() == 1, self.limit.value(), self,
        )
        self.worker.loaded.connect(self.display)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def display(self, records, error, read_seconds, parse_seconds):
        start = perf_counter()
        self.detail.clear()
        self.model.set_records(records)
        # Keep existing search filter. Qt only paints the visible rows.
        self.proxy.set_term(self.search.text())
        display_seconds = perf_counter() - start
        self.refresh_button.setEnabled(True)
        self.status.setText(f"Luettu {len(records)} riviä, näkyvissä {self.proxy.rowCount()}. Uusimmat ensin.")
        self.metrics.setText(
            f"Haku {read_seconds * 1000:.0f} ms | JSON {parse_seconds * 1000:.0f} ms | "
            f"UI {display_seconds * 1000:.0f} ms | yhteensä {(perf_counter()-self._load_started)*1000:.0f} ms"
        )
        if error:
            if not records:
                QMessageBox.warning(self, "Lokin lukeminen epäonnistui", error)
            else:
                self.status.setText(self.status.text() + " | journalctl: " + error)

    def worker_finished(self):
        if self._refresh_pending and not self._closing:
            QTimer.singleShot(0, self.refresh)
        self.maybe_close()

    def filter_rows(self, *_):
        self.proxy.set_term(self.search.text())
        self.status.setText(
            f"Näkyvissä {self.proxy.rowCount()} / {len(self.model.records)} riviä. "
            "Haku koskee ladattuja rivejä."
        )

    def show_detail(self, current, _previous):
        if not current.isValid():
            self.detail.clear()
            return
        source_index = self.proxy.mapToSource(current)
        if not source_index.isValid():
            self.detail.clear()
            return
        raw = self.model.records[source_index.row()]["raw"]
        key_order = ["MESSAGE", "_SYSTEMD_UNIT", "_COMM", "_EXE", "_PID", "_BOOT_ID", "PRIORITY", "__CURSOR"]
        keys = [key for key in key_order if key in raw] + sorted(set(raw) - set(key_order))
        self.detail.setPlainText("\n\n".join(f"{key}: {raw[key]}" for key in keys))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Tallenna näkyvät lokirivit", str(Path.home() / "loki.txt"), "Text (*.txt)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                for i in range(self.proxy.rowCount()):
                    source = self.proxy.mapToSource(self.proxy.index(i, 0))
                    entry = self.model.records[source.row()]
                    file.write(f'{entry["time"]} [{entry["priority"]}] {entry["source"]}: {entry["message"]}\n')
            self.status.setText(f"Tallennettu: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Tallennus epäonnistui", str(exc))

    def maybe_close(self):
        if self._closing and not any(t is not None and t.isRunning() for t in (self.worker, self.boot_worker)):
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if any(t is not None and t.isRunning() for t in (self.worker, self.boot_worker)):
            self._closing = True
            self.status.setText("Odotetaan käynnissä olevan journal-haun päättymistä ennen sulkemista...")
            event.ignore()
            return
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Loki")
    app.setDesktopFileName("loki-journal")
    window = Loki()
    window.show()
    sys.exit(app.exec())
