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

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QLocale, QSettings, QSortFilterProxyModel, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QTableView, QTextEdit, QVBoxLayout, QWidget,
)

TEXT = {
    "fi": {
        "priorities": ["Hätätila", "Hälytys", "Kriittinen", "Virhe", "Varoitus", "Huomautus", "Tiedote", "Debug"],
        "headers": ["Aika", "Taso", "Lähde", "Viesti"],
        "title": "Loki 0.4.1 | systemd-lokiselain",
        "language": "Kieli:", "finnish": "Suomi", "english": "English",
        "current_boot": "Nykyinen käynnistys", "previous_boot": "Edellinen käynnistys",
        "boot": "Käynnistys {offset}: {date}", "boot_label": "Käynnistys:", "severity": "Vakavuus:",
        "all_levels": "Kaikki tasot", "errors": "Vain virheet ja vakavammat",
        "warnings": "Varoitukset ja vakavammat", "all_sources": "Kaikki lähteet", "kernel": "Vain kernel",
        "rows_suffix": " riviä", "refresh": "Päivitä",
        "search_hint": "Hae näkyvistä riveistä: amdgpu, nvme, timeout, ...",
        "export": "Vie näkyvät TXT-tiedostoon", "detail_hint": "Valitse lokirivi. Tarkat tiedot näkyvät tässä.",
        "ready": "Valmis", "ui_ok": "UI: ok", "stall_tip": "Sovelluksen käyttöliittymän pisin havaittu viive (ajastimen ylitys)",
        "stall_detected": "Qt:n tapahtumasilmukka ei ehtinyt käsitellä ajastinta normaalisti",
        "refresh_pending": "Asetukset muuttuivat: päivitetään haun valmistuttua...",
        "loading": "Luetaan journalia...", "read": "Luettu {count} riviä, näkyvissä {visible}. Uusimmat ensin.",
        "timing": "Haku {read:.0f} ms | JSON {parse:.0f} ms | UI {ui:.0f} ms | yhteensä {total:.0f} ms",
        "journal_error": "journalctl päättyi virhekoodiin {code}", "read_failed": "Lokin lukeminen epäonnistui",
        "read_error": "Luettu {count} riviä, näkyvissä {visible}. Uusimmat ensin. | journalctl: {error}",
        "filter_status": "Näkyvissä {visible} / {total} riviä. Haku koskee ladattuja rivejä.",
        "save_dialog": "Tallenna näkyvät lokirivit", "text_files": "Tekstitiedostot (*.txt)",
        "save_failed": "Tallennus epäonnistui", "saved": "Tallennettu: {path}",
        "waiting_close": "Odotetaan käynnissä olevan journal-haun päättymistä ennen sulkemista...",
    },
    "en": {
        "priorities": ["Emergency", "Alert", "Critical", "Error", "Warning", "Notice", "Informational", "Debug"],
        "headers": ["Time", "Level", "Source", "Message"],
        "title": "Loki 0.4.1 | systemd journal browser",
        "language": "Language:", "finnish": "Suomi", "english": "English",
        "current_boot": "Current boot", "previous_boot": "Previous boot",
        "boot": "Boot {offset}: {date}", "boot_label": "Boot:", "severity": "Severity:",
        "all_levels": "All levels", "errors": "Errors and above", "warnings": "Warnings and above",
        "all_sources": "All sources", "kernel": "Kernel only", "rows_suffix": " rows", "refresh": "Refresh",
        "search_hint": "Search visible rows: amdgpu, nvme, timeout, ...",
        "export": "Export visible rows to TXT", "detail_hint": "Select a log row to see its details here.",
        "ready": "Ready", "ui_ok": "UI: OK", "stall_tip": "Longest observed UI delay (timer overrun)",
        "stall_detected": "The Qt event loop could not process the timer on time",
        "refresh_pending": "Settings changed: refreshing when the current query finishes...",
        "loading": "Reading journal...", "read": "Read {count} rows, {visible} visible. Newest first.",
        "timing": "Query {read:.0f} ms | JSON {parse:.0f} ms | UI {ui:.0f} ms | total {total:.0f} ms",
        "journal_error": "journalctl exited with code {code}", "read_failed": "Failed to read the journal",
        "read_error": "Read {count} rows, {visible} visible. Newest first. | journalctl: {error}",
        "filter_status": "Showing {visible} / {total} rows. Search covers loaded rows.",
        "save_dialog": "Save visible log rows", "text_files": "Text files (*.txt)",
        "save_failed": "Save failed", "saved": "Saved: {path}",
        "waiting_close": "Waiting for the running journal query to finish before closing...",
    },
}
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
                error = f"journalctl-exit:{result.returncode}"
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
                boots.append((offset, parts[2][:22]))
                seen.add(offset)
            self.ready.emit(boots)
        except (OSError, subprocess.TimeoutExpired):
            self.ready.emit([])


class JournalModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.language = "fi"

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(TEXT[self.language]["headers"]):
                return TEXT[self.language]["headers"][section]
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
                priorities = TEXT[self.language]["priorities"]
                return priorities[p] if 0 <= p < len(priorities) else "?"
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
        self.settings = QSettings("Loki", "Loki")
        saved_language = self.settings.value("language", "")
        system_language = "fi" if QLocale.system().language() == QLocale.Finnish else "en"
        self.language_code = saved_language if saved_language in TEXT else system_language
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
        self._metric_values = None
        self._stall_delay = 0.0
        self._status_key = "ready"
        self._status_args = {}

        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.boot = QComboBox()
        self.boot.setMinimumWidth(240)
        self.boot.addItem("", "0")
        self.boot.addItem("", "-1")
        self.boot_label = QLabel()
        top.addWidget(self.boot_label)
        top.addWidget(self.boot)

        self.level = QComboBox()
        self.level.addItem("", None)
        self.level.addItem("", 3)
        self.level.addItem("", 4)
        self.level.setCurrentIndex(1)
        self.level_label = QLabel()
        top.addWidget(self.level_label)
        top.addWidget(self.level)

        self.scope = QComboBox()
        self.scope.addItems(["", ""])
        top.addWidget(self.scope)
        self.limit = QSpinBox()
        self.limit.setRange(100, 20000)
        self.limit.setSingleStep(500)
        self.limit.setValue(2000)
        self.limit.setSuffix("")
        top.addWidget(self.limit)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        self.language_label = QLabel()
        top.addWidget(self.language_label)
        self.language = QComboBox()
        self.language.addItem("", "fi")
        self.language.addItem("", "en")
        top.addWidget(self.language)
        layout.addLayout(top)

        filterbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("")
        self.search.setClearButtonEnabled(True)
        filterbar.addWidget(self.search)
        self.export_button = QPushButton()
        self.export_button.clicked.connect(self.export)
        filterbar.addWidget(self.export_button)
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
        self.detail.setPlaceholderText("")
        self.detail.setFont(QFont("monospace", 10))
        splitter.addWidget(self.detail)
        splitter.setSizes([540, 170])
        layout.addWidget(splitter)

        bottom = QHBoxLayout()
        self.status = QLabel()
        bottom.addWidget(self.status, 1)
        self.metrics = QLabel("")
        bottom.addWidget(self.metrics)
        self.stall = QLabel()
        bottom.addWidget(self.stall)
        layout.addLayout(bottom)
        self.setCentralWidget(root)

        self.boot.currentIndexChanged.connect(self.refresh)
        self.level.currentIndexChanged.connect(self.refresh)
        self.scope.currentIndexChanged.connect(self.refresh)
        self.limit.valueChanged.connect(self.refresh)
        self.search.textChanged.connect(self.filter_rows)
        self.language.currentIndexChanged.connect(self.change_language)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)

        self.pulse = QTimer(self)
        self.pulse.setInterval(100)
        self.pulse.timeout.connect(self.heartbeat)
        self.pulse.start()
        self.language.setCurrentIndex(self.language.findData(self.language_code))
        self.retranslate_ui()
        self.refresh()
        self.load_boots_async()

    def tr(self, key):
        return TEXT[self.language_code][key]

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("title"))
        self.boot_label.setText(self.tr("boot_label"))
        self.boot.setItemText(0, self.tr("current_boot"))
        self.boot.setItemText(1, self.tr("previous_boot"))
        for index in range(2, self.boot.count()):
            offset, date = self.boot.itemData(index)
            self.boot.setItemText(index, self.tr("boot").format(offset=offset, date=date))
        self.level_label.setText(self.tr("severity"))
        for index, key in enumerate(("all_levels", "errors", "warnings")):
            self.level.setItemText(index, self.tr(key))
        self.scope.setItemText(0, self.tr("all_sources"))
        self.scope.setItemText(1, self.tr("kernel"))
        self.limit.setSuffix(self.tr("rows_suffix"))
        self.refresh_button.setText(self.tr("refresh"))
        self.language_label.setText(self.tr("language"))
        self.language.setItemText(0, self.tr("finnish"))
        self.language.setItemText(1, self.tr("english"))
        self.search.setPlaceholderText(self.tr("search_hint"))
        self.export_button.setText(self.tr("export"))
        self.detail.setPlaceholderText(self.tr("detail_hint"))
        self.stall.setToolTip(self.tr("stall_detected") if self._stall_delay >= 0.3 else self.tr("stall_tip"))
        self._render_stall()
        self._render_metrics()
        self.model.language = self.language_code
        self.model.headerDataChanged.emit(Qt.Horizontal, 0, 3)
        if self.model.records:
            self.model.dataChanged.emit(
                self.model.index(0, 1),
                self.model.index(len(self.model.records) - 1, 1),
                [Qt.DisplayRole],
            )
        self._render_status()

    def set_status(self, key, **args):
        self._status_key = key
        self._status_args = args
        self._render_status()

    def _render_status(self):
        args = self._status_args.copy()
        if "journal_code" in args:
            args["error"] = self.tr("journal_error").format(code=args.pop("journal_code"))
        self.status.setText(self.tr(self._status_key).format(**args))

    def _render_metrics(self):
        if self._metric_values is None:
            self.metrics.setText("")
            return
        self.metrics.setText(self.tr("timing").format(**self._metric_values))

    def _render_stall(self):
        if self._stall_delay >= 0.3:
            label = "UI delay" if self.language_code == "en" else "UI-viive"
            self.stall.setText(f"{label}: {self._stall_delay:.1f} s")
        else:
            self.stall.setText(self.tr("ui_ok"))

    def change_language(self, *_):
        language = self.language.currentData()
        if language not in TEXT or language == self.language_code:
            return
        self.language_code = language
        self.settings.setValue("language", language)
        self.retranslate_ui()

    def load_boots_async(self):
        self.boot_worker = BootsWorker(self)
        self.boot_worker.ready.connect(self.receive_boots)
        self.boot_worker.finished.connect(self.maybe_close)
        self.boot_worker.start()

    def receive_boots(self, boots):
        self.boot.blockSignals(True)
        try:
            for offset, date in boots:
                self.boot.addItem(self.tr("boot").format(offset=offset, date=date), (offset, date))
        finally:
            self.boot.blockSignals(False)

    def heartbeat(self):
        current = perf_counter()
        delay = max(0.0, current - self._last_pulse - 0.1)
        self._last_pulse = current
        if delay > self._max_stall:
            self._max_stall = delay
            if delay >= 0.3:
                self._stall_delay = delay
                self._render_stall()
                self.stall.setToolTip(self.tr("stall_detected"))

    def refresh(self, *_):
        if self._closing:
            return
        if self.worker is not None and self.worker.isRunning():
            self._refresh_pending = True
            self.set_status("refresh_pending")
            return
        self._refresh_pending = False
        self._max_stall = 0.0
        self._stall_delay = 0.0
        self._last_pulse = perf_counter()
        self._render_stall()
        self._metric_values = None
        self._render_metrics()
        self.set_status("loading")
        self.refresh_button.setEnabled(False)
        self._load_started = perf_counter()
        selected_boot = self.boot.currentData()
        boot_offset = selected_boot[0] if isinstance(selected_boot, tuple) else selected_boot
        self.worker = JournalWorker(
            boot_offset, self.level.currentData(),
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
        self._metric_values = {
            "read": read_seconds * 1000, "parse": parse_seconds * 1000,
            "ui": display_seconds * 1000, "total": (perf_counter()-self._load_started) * 1000,
        }
        status_args = {"count": len(records), "visible": self.proxy.rowCount()}
        self.set_status("read", **status_args)
        self._render_metrics()
        if error:
            journal_code = None
            if error.startswith("journalctl-exit:"):
                journal_code = error.partition(":")[2]
                error = self.tr("journal_error").format(code=journal_code)
            if not records:
                QMessageBox.warning(self, self.tr("read_failed"), error)
            else:
                if journal_code is not None:
                    self.set_status("read_error", **status_args, journal_code=journal_code)
                else:
                    self.set_status("read_error", **status_args, error=error)

    def worker_finished(self):
        if self._refresh_pending and not self._closing:
            QTimer.singleShot(0, self.refresh)
        self.maybe_close()

    def filter_rows(self, *_):
        self.proxy.set_term(self.search.text())
        self.set_status("filter_status", visible=self.proxy.rowCount(), total=len(self.model.records))

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
            self, self.tr("save_dialog"), str(Path.home() / "loki.txt"), self.tr("text_files"),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                for i in range(self.proxy.rowCount()):
                    source = self.proxy.mapToSource(self.proxy.index(i, 0))
                    entry = self.model.records[source.row()]
                    file.write(f'{entry["time"]} [{entry["priority"]}] {entry["source"]}: {entry["message"]}\n')
            self.set_status("saved", path=path)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("save_failed"), str(exc))

    def maybe_close(self):
        if self._closing and not any(t is not None and t.isRunning() for t in (self.worker, self.boot_worker)):
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if any(t is not None and t.isRunning() for t in (self.worker, self.boot_worker)):
            self._closing = True
            self.set_status("waiting_close")
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
