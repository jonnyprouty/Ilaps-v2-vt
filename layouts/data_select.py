import sys
from PySide2.QtWidgets import *
from PySide2 import QtGui
from PySide2.QtCore import Qt
from widgets.tab_select import SelectTab
from widgets.peak_editor import PeakEditor

import numpy as np

from matplotlib.backends.backend_qt5agg import (
    FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure

from imgMS import MSData as msd
from imgMS import MSEval as mse
from imgMS.side_functions import *
import error_popup


class DataSelect(QWidget):

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.mainLayout.setAlignment(Qt.AlignCenter)

        self.settingsWidget = QWidget()
        self.settingsLayout = QHBoxLayout(self.settingsWidget)

        self.mainLayout.addWidget(self.settingsWidget)

        self.formGroupBox = QGroupBox("Analysis settings")
        layout = QFormLayout()

        self.blank = QLabel("")
        layout.addRow(QLabel(""), self.blank)

        self.skipBcg = QHBoxLayout()
        self.skipBcgStart = QLineEdit()
        self.skipBcgEnd = QLineEdit()
        self.skipBcg.addWidget(self.skipBcgStart)
        self.skipBcg.addWidget(self.skipBcgEnd)
        layout.addRow(QLabel("Skip background:"), self.skipBcg)

        self.skipPeak = QHBoxLayout()
        self.skipPeakStart = QLineEdit()
        self.skipPeakEnd = QLineEdit()
        self.skipPeak.addWidget(self.skipPeakStart)
        self.skipPeak.addWidget(self.skipPeakEnd)
        layout.addRow(QLabel("Skip peak:"), self.skipPeak)

        self.formGroupBox.setLayout(layout)

        self.settingsLayout.addWidget(self.formGroupBox)

        self.logaxisBox = QCheckBox('log axes')
        self.settingsLayout.addWidget(
            self.logaxisBox, alignment=Qt.AlignCenter)

        self.select = SelectTab(self)
        self.settingsLayout.addWidget(self.select)

        self.selectBtn = QPushButton('Select')
        self.settingsLayout.addWidget(self.selectBtn, alignment=Qt.AlignCenter)
        self.selectBtn.clicked.connect(self.select_data)

        self.editPeaksBtn = QPushButton('Edit peaks...')
        self.editPeaksBtn.setToolTip('Adjust the signal window of individual spots, or exclude intervals.')
        self.settingsLayout.addWidget(self.editPeaksBtn, alignment=Qt.AlignCenter)
        self.editPeaksBtn.clicked.connect(self.edit_peaks)

        self.settingsLayout.addStretch(1)

        self.fig = Figure()
        self.ax = self.fig.subplots()
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet(
            "QWidget {border: None; background-color: white; color: black}")
        self.mainLayout.addWidget(self.toolbar)
        self.mainLayout.addWidget(self.canvas)

    def get_page(self):
        """
        Returns Page for bulk analysis for main stack of gui
        Returns
        -------
        mainWidget : QWidget
            The widget that the houses the bulk analysis screen.
        """
        return self.mainWidget

    def edit_peaks(self):
        """
        Open the manual peak editor; replot and clear earlier results if anything changed.
        """
        data = self.parent.Data
        if data is None or not data.laser_on:
            error_popup.notify('Import the data and click Select before editing peaks.')
            return
        had_results = data.means is not None
        editor = PeakEditor(self.parent, data, self.parent.welcome.dataEntry1.text().strip())
        editor.exec_()
        if not editor.changed:
            return
        self.parent.bulk_analysis.clear_results()
        self.ax.clear()
        data.graph(ax=self.ax, logax=self.logaxisBox.isChecked())
        self.ax.figure.canvas.draw_idle()
        if had_results:
            QMessageBox.information(self, 'Peaks edited', 'The peak windows changed, so earlier results were '
                                    'cleared. Run Average and Quantification again.')

    def select_data(self):
        # a new selection replaces the peaks, and with them any manual edits
        data = self.parent.Data
        if data is not None and data.peak_edits:
            answer = QMessageBox.question(
                self, 'Select again', f'Selecting again discards the manual edits of {len(data.peak_edits)} '
                'spot(s). Continue?', QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return

        # get skip values if given
        if self.skipBcgStart.text().isdigit():
            bcg_s = int(self.skipBcgStart.text())
        else:
            bcg_s = 0

        if self.skipBcgEnd.text().isdigit():
            bcg_e = int(self.skipBcgEnd.text())
        else:
            bcg_e = 0

        if self.skipPeakStart.text().isdigit():
            sig_s = int(self.skipPeakStart.text())
        else:
            sig_s = 0

        if self.skipPeakEnd.text().isdigit():
            sig_e = int(self.skipPeakEnd.text())
        else:
            sig_e = 0

        # get method and values necessery for given method
        method = self.select.return_tab()
        if method == 'treshold':
            start = float(self.select.bcg.text())
            multiply = float(self.select.mltp.text())

        elif method == 'iolite':
            start = float(self.select.start.text())
            multiply = None
            if not self.parent.Iolite:
                error_dialog = QErrorMessage()
                error_dialog.showMessage('Missing Iolite file.')
                error_dialog.exec_()
                return

        # create selector
        selector = mse.Selector(ms_data=self.parent.Data, s=start, sdmul=multiply,
                                iolite=self.parent.Iolite, logger=self.parent.logger)

        selector.set_skip(bcg_s, bcg_e, sig_s, sig_e)

        # select data
        self.parent.Data.select(method=method, selector=selector)
        self.parent.bulk_analysis.clear_results()  # results of the previous selection no longer apply

        # set names from iolite if checked
        if self.select.namesCheckBox.isChecked():
            self.parent.Data.names = self.parent.Iolite.names_from_iolite()
        # set names from Param file
        elif self.parent.Data.param is not None:
            self.parent.Data.names = self.parent.Data.param .peak_names

        logax = self.logaxisBox.isChecked()

        # replot data
        self.ax.clear()
        self.ax.figure.canvas.draw_idle()
        self.parent.Data.graph(ax=self.ax, logax=logax)
        self.ax.figure.canvas.draw_idle()

    #
