"""Manual editing of peak windows, one spot at a time.

Drag the blue lines to move the start or end of the signal. With "Exclude interval" on, drag across
readings to leave them out; right-click an excluded interval to restore it. Readings removed from a
peak are used neither as signal nor as background (see imgMS MSData.background_windows).
"""
import os

import numpy as np
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QVBoxLayout)
from matplotlib.backends.backend_qt5agg import FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

SUM_LABEL = 'Sum of all isotopes'
GRAB_PIXELS = 7


class PeakEditor(QDialog):

    def __init__(self, parent, data, data_path=''):
        super().__init__(parent)
        self.data = data
        self.data_path = data_path
        self.time = np.asarray(data.time, dtype=float)
        self.changed = False
        self.peak = 0
        self._drag = None       # 'start' or 'end' while a line is dragged
        self._span_from = None  # first reading of an exclusion being dragged
        self._rubber = None

        self.setWindowTitle('Edit peaks')
        self.resize(1150, 760)
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.prevBtn = QPushButton('< Previous')
        self.prevBtn.clicked.connect(lambda: self.peakCombo.setCurrentIndex(max(self.peak - 1, 0)))
        self.peakCombo = QComboBox()
        self.nextBtn = QPushButton('Next >')
        self.nextBtn.clicked.connect(
            lambda: self.peakCombo.setCurrentIndex(min(self.peak + 1, len(self.data.laser_on) - 1)))
        self.isotopeCombo = QComboBox()
        self.isotopeCombo.addItems([SUM_LABEL] + [str(i) for i in data.isotope_names])
        self.logBox = QCheckBox('log axis')
        self.logBox.setChecked(True)
        for w in (QLabel('Spot:'), self.prevBtn, self.peakCombo, self.nextBtn, QLabel('Show:'), self.isotopeCombo,
                  self.logBox):
            row.addWidget(w)
        row.addStretch(1)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.startBox, self.endBox = self._time_box(), self._time_box()
        self.excludeBtn = QPushButton('Exclude interval')
        self.excludeBtn.setCheckable(True)
        self.excludeBtn.setToolTip('On: drag across the plot to leave those readings out. '
                                   'Right-click an excluded interval to restore it.')
        self.clearExcludeBtn = QPushButton('Clear exclusions')
        self.resetBtn = QPushButton('Reset spot')
        self.resetAllBtn = QPushButton('Reset all')
        self.saveBtn = QPushButton('Save edits...')
        self.loadBtn = QPushButton('Load edits...')
        self.closeBtn = QPushButton('Close')
        for w in (QLabel('Signal start (s):'), self.startBox, QLabel('end (s):'), self.endBox, self.excludeBtn,
                  self.clearExcludeBtn, self.resetBtn, self.resetAllBtn, self.saveBtn, self.loadBtn):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(self.closeBtn)
        layout.addLayout(row)

        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.fig = Figure()
        self.ax = self.fig.subplots()
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet('QWidget {border: None; background-color: white; color: black}')
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

        self.peakCombo.currentIndexChanged.connect(self.show_peak)
        self.isotopeCombo.currentIndexChanged.connect(lambda _: self.redraw())
        self.logBox.toggled.connect(lambda _: self.redraw())
        self.startBox.editingFinished.connect(self._boxes_edited)
        self.endBox.editingFinished.connect(self._boxes_edited)
        self.clearExcludeBtn.clicked.connect(lambda: self.apply(exclude=[]))
        self.resetBtn.clicked.connect(self.reset_peak)
        self.resetAllBtn.clicked.connect(self.reset_all)
        self.saveBtn.clicked.connect(self.save_edits)
        self.loadBtn.clicked.connect(self.load_edits)
        self.closeBtn.clicked.connect(self.accept)
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_release_event', self.on_release)

        self.refresh_labels()
        self.show_peak(0)

    # ------------------------------------------------------------------ helpers

    def _time_box(self):
        box = QDoubleSpinBox()
        box.setDecimals(3)
        box.setRange(float(self.time[0]), float(self.time[-1]))
        box.setKeyboardTracking(False)
        box.setMinimumWidth(100)
        return box

    def _nearest(self, t):
        return int(np.abs(self.time - t).argmin())

    def _label(self, peak):
        names = self.data.names
        name = str(names[peak]) if names is not None and peak < len(names) else ''
        return f"{peak + 1}: {name}{' *' if peak in self.data.peak_edits else ''}"

    def refresh_labels(self):
        self.peakCombo.blockSignals(True)
        current = self.peak
        self.peakCombo.clear()
        self.peakCombo.addItems([self._label(i) for i in range(len(self.data.laser_on))])
        self.peakCombo.setCurrentIndex(current)
        self.peakCombo.blockSignals(False)

    def _describe(self):
        d, p = self.data, self.peak
        used = sum(b - a for a, b in d.signal_segments(p))
        a, b = d.laser_on[p]
        text = f'Spot {p + 1}: {used} readings used of {b - a} in the automatic window. '
        text += f'{len(d.peak_edits)} spot(s) edited (marked *).' if d.peak_edits else 'No spots edited.'
        return text

    # ------------------------------------------------------------------ display

    def show_peak(self, peak):
        if peak < 0:
            return
        self.peak = peak
        self.redraw(reset_view=True)

    def _signal(self):
        name = self.isotopeCombo.currentText()
        if name == SUM_LABEL:
            return self.data.data.values.sum(axis=1)
        return self.data.data[name].values

    def redraw(self, reset_view=False):
        d, p = self.data, self.peak
        xlim = None if reset_view or not self.ax.has_data() else self.ax.get_xlim()
        ylim = None if reset_view or not self.ax.has_data() else self.ax.get_ylim()
        log = self.logBox.isChecked()
        was_log = self.ax.get_yscale() == 'log'

        start, end = d.peak_window(p)
        outer = d.background_windows()[0][p]
        width = max(outer[1] - outer[0], 20)
        lo, hi = max(outer[0] - width // 2, 0), min(outer[1] + width // 2, len(self.time) - 1)

        self.ax.clear()
        y = self._signal()[lo:hi + 1].astype(float)
        self.ax.plot(self.time[lo:hi + 1], np.maximum(y, 0.5) if log else y, color='black', lw=1)
        if log:
            self.ax.set_yscale('log')
        # each reading is drawn as a band centred on its time, so single readings stay visible
        step = float(np.median(np.diff(self.time)))
        edges = np.append(self.time - step / 2, self.time[-1] + step / 2)
        for a, b in d.signal_segments(p):
            self.ax.axvspan(edges[a], edges[b], color='green', alpha=0.2, lw=0)
        cursor = outer[0]
        for a, b in d.signal_segments(p) + [(outer[1], outer[1])]:
            if a > cursor:
                self.ax.axvspan(edges[cursor], edges[a], color='grey', alpha=0.4, lw=0)
            cursor = max(cursor, b)
        self.startLine = self.ax.axvline(self.time[start], color='tab:blue', lw=2)
        self.endLine = self.ax.axvline(self.time[end - 1], color='tab:blue', lw=2)
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel(f'{self.isotopeCombo.currentText()} (counts)')
        self.ax.set_title(f'{self._label(p)}   green: signal, grey: removed, blue: drag to move', fontsize=10)
        if xlim is not None:
            self.ax.set_xlim(xlim)
            if was_log == log:
                self.ax.set_ylim(ylim)
        else:
            self.ax.set_xlim(self.time[lo], self.time[hi])
        self.canvas.draw_idle()

        for box, value in ((self.startBox, self.time[start]), (self.endBox, self.time[end - 1])):
            box.blockSignals(True)
            box.setValue(float(value))
            box.blockSignals(False)
        self.status.setText(self._describe())

    # ------------------------------------------------------------------ edits

    def apply(self, **edit):
        try:
            changed = self.data.set_peak_edit(self.peak, **edit)
        except ValueError as e:
            self.redraw()
            self.status.setText(f'Not applied. {e}')
            return False
        if changed:
            self.changed = True
            self.refresh_labels()
        self.redraw()
        return changed

    def _boxes_edited(self):
        self.apply(start=self._nearest(self.startBox.value()), end=self._nearest(self.endBox.value()) + 1)

    def reset_peak(self):
        if self.data.clear_peak_edits(self.peak):
            self.changed = True
            self.refresh_labels()
        self.redraw(reset_view=True)

    def reset_all(self):
        if not self.data.peak_edits:
            return
        answer = QMessageBox.question(self, 'Reset all', f'Remove the edits of all {len(self.data.peak_edits)} '
                                      'edited spots?', QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes and self.data.clear_peak_edits():
            self.changed = True
            self.refresh_labels()
            self.redraw(reset_view=True)

    def _default_path(self):
        return os.path.splitext(self.data_path)[0] + '_peak_edits.json' if self.data_path else ''

    def save_edits(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save peak edits', self._default_path(), 'Peak edits (*.json)')
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        self.data.save_peak_edits(path)
        self.status.setText(f'Saved {len(self.data.peak_edits)} edited spot(s) to {path}.')

    def load_edits(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load peak edits', self._default_path(),
                                              'Peak edits (*.json);;All files (*)')
        if not path:
            return
        before = dict(self.data.peak_edits)
        try:
            n = self.data.load_peak_edits(path)
        except (ValueError, OSError) as e:
            self.status.setText(str(e))
            return
        self.changed = self.changed or self.data.peak_edits != before
        self.refresh_labels()
        self.redraw(reset_view=True)
        self.status.setText(f'Loaded edits for {n} spot(s) from {path}.')

    # ------------------------------------------------------------------ mouse

    def _toolbar_busy(self):
        return bool(str(self.toolbar.mode))

    def _near(self, line, event):
        x = self.ax.transData.transform((line.get_xdata()[0], 1))[0]
        return abs(x - event.x) <= GRAB_PIXELS

    def on_press(self, event):
        if event.inaxes is not self.ax or event.xdata is None or self._toolbar_busy():
            return
        reading = self._nearest(event.xdata)
        if event.button == 3:  # restore an excluded interval
            edit = self.data.peak_edits.get(self.peak)
            if edit:
                remaining = [(a, b) for a, b in edit['exclude'] if not a <= reading < b]
                if len(remaining) != len(edit['exclude']):
                    self.apply(exclude=remaining)
            return
        if event.button != 1:
            return
        if self.excludeBtn.isChecked():
            self._span_from = reading
            self._rubber = self.ax.axvspan(self.time[reading], self.time[reading], color='grey', alpha=0.4, lw=0)
        elif self._near(self.startLine, event) and (not self._near(self.endLine, event) or
                                                    event.xdata < self.endLine.get_xdata()[0]):
            self._drag = 'start'
        elif self._near(self.endLine, event):
            self._drag = 'end'

    def on_motion(self, event):
        if event.xdata is None or event.inaxes is not self.ax:
            return
        if self._drag:
            line = self.startLine if self._drag == 'start' else self.endLine
            t = float(self.time[self._nearest(event.xdata)])
            line.set_xdata([t, t])
            self.canvas.draw_idle()
        elif self._span_from is not None:
            a, b = sorted((float(self.time[self._span_from]), float(self.time[self._nearest(event.xdata)])))
            self._rubber.remove()
            self._rubber = self.ax.axvspan(a, b, color='grey', alpha=0.4, lw=0)
            self.canvas.draw_idle()

    def on_release(self, event):
        x = event.xdata if event.inaxes is self.ax else None
        if self._drag:
            which, self._drag = self._drag, None
            line = self.startLine if which == 'start' else self.endLine
            reading = self._nearest(x if x is not None else line.get_xdata()[0])
            self.apply(**({'start': reading} if which == 'start' else {'end': reading + 1}))
        elif self._span_from is not None:
            first, self._span_from = self._span_from, None
            self._rubber = None
            if x is None:
                self.redraw()
                return
            a, b = sorted((first, self._nearest(x)))
            current = self.data.peak_edits.get(self.peak, {}).get('exclude', [])
            self.apply(exclude=list(current) + [(a, b + 1)])
