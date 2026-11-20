import os
import sys
from PySide2.QtWidgets import *
from PySide2 import QtGui
from PySide2.QtCore import Qt

from widgets.pandas_model import PandasModel
import error_popup

from xlrd import XLRDError

from imgMS import MSData as msd
from imgMS import MSEval as mse
from imgMS.side_functions import *

# Make Iolite log (tools/make_iolite.py): combines single-spot runs, writes Iolite log and Param file
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import make_iolite  # noqa: E402


class Welcome(QWidget):
    """
    Starting screen of Ilaps GUI, allowing importing analysis data

    """

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.mainLayout.setAlignment(Qt.AlignCenter)

        self.importAnalysis = QGroupBox('Import Data')
        self.mainLayout.addWidget(self.importAnalysis)
        self.analysisLayout = QGridLayout()

        self.lbl = QLabel('Import Analysis')
        self.analysisLayout.addWidget(self.lbl, 0, 0)

        self.loadData1 = QPushButton('')
        self.loadData1.setIcon(QtGui.QIcon('./imgs/load.jpg'))
        self.analysisLayout.addWidget(
            self.loadData1, 1, 0, alignment=Qt.AlignLeft)
        self.loadData1.clicked.connect(lambda: self.get_file(self.dataEntry1))

        self.dataEntry1 = QLineEdit()
        self.analysisLayout.addWidget(
            self.dataEntry1, 1, 1, alignment=Qt.AlignLeft)

        self.lbl = QLabel('File type:')
        self.analysisLayout.addWidget(self.lbl, 2, 0)

        self.fileType = QComboBox()
        self.fileType.addItems(['csv', 'xlsx', 'asc'])
        self.analysisLayout.addWidget(self.fileType, 2, 1)

        self.lbl = QLabel('Instrument type:')
        self.analysisLayout.addWidget(self.lbl, 3, 0)

        self.instrument = QComboBox()
        self.instrument.addItems(['raw', 'Agilent', 'Element', 'MC Nu-Sapphire'])
        self.analysisLayout.addWidget(self.instrument, 3, 1)

        self.lbl = QLabel('Import Parameters')
        self.analysisLayout.addWidget(self.lbl, 4, 0)

        self.loadData2 = QPushButton('')
        self.loadData2.setIcon(QtGui.QIcon('./imgs/load.jpg'))
        self.analysisLayout.addWidget(
            self.loadData2, 5, 0, alignment=Qt.AlignLeft)
        self.loadData2.clicked.connect(lambda: self.get_file(self.dataEntry2))

        self.dataEntry2 = QLineEdit()
        self.analysisLayout.addWidget(
            self.dataEntry2, 5, 1, alignment=Qt.AlignLeft)

        self.lbl = QLabel('Import Iolite')
        self.analysisLayout.addWidget(self.lbl, 6, 0)

        self.loadIolite = QPushButton('')
        self.loadIolite.setIcon(QtGui.QIcon('./imgs/load.jpg'))
        self.analysisLayout.addWidget(
            self.loadIolite, 7, 0, alignment=Qt.AlignLeft)
        self.loadIolite.clicked.connect(lambda: self.get_file(self.dataEntry3))

        self.dataEntry3 = QLineEdit()
        self.analysisLayout.addWidget(
            self.dataEntry3, 7, 1, alignment=Qt.AlignLeft)

        self.importAnalysis.setLayout(self.analysisLayout)

        self.importBtn = QPushButton('Import')
        self.mainLayout.addWidget(self.importBtn)
        self.importBtn.clicked.connect(self.import_data)

        self.singleSpotBtn = QPushButton('Import single-spot runs...')
        self.singleSpotBtn.setToolTip(
            'Select Agilent runs with one spot each: they are joined into one file per day, with an '
            'Iolite log and Param file (Make Iolite log), and the day is imported.')
        self.mainLayout.addWidget(self.singleSpotBtn)
        self.singleSpotBtn.clicked.connect(self.import_single_spot)

    def get_page(self):
        """
        Returns Page for bulk analysis for main stack of gui
        Returns
        -------
        mainWidget : QWidget
            The widget that the houses the bulk analysis screen.
        """
        return self.mainWidget

    def get_file(self, entry):
        """
        Fill lineEdit with path to file from user
        """
        filename, filters = QFileDialog.getOpenFileName(self, caption='Open file', dir='',
                                                        filter='All Files(*.*);; Excel Files(*.xlsx)')
        if filename:
            entry.setText(filename)

    def import_single_spot(self):
        """
        Combine single-spot Agilent runs with Make Iolite log, fill in the import fields and import.
        """
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Select the single-spot runs (one Agilent export per spot)', '',
            'Agilent exports (*.txt *.csv);;All files (*)')
        if not files:
            return
        out_dir = os.path.dirname(files[0])
        prefix, ok = QInputDialog.getText(self, 'Output name', 'Prefix for the output files:',
                                          text=os.path.basename(out_dir).replace(' ', '_'))
        prefix = prefix.strip()
        if not ok or not prefix:
            return

        lines = []
        try:
            days = make_iolite.make(make_iolite.collect_files(files, '*'), out_dir, prefix, say=lines.append)
        except ValueError as e:
            error_popup.notify(e)
            return
        with open(os.path.join(out_dir, f'{prefix}_make_iolite_log.txt'), 'w') as fh:
            fh.write('\n'.join(lines) + '\n')

        day = days[0]
        if len(days) > 1:
            labels = [f"{d['tag']} ({len(d['runs'])} spots)" for d in days]
            choice, ok = QInputDialog.getItem(self, 'Which day?', 'The runs are from several days; '
                                              'each has its own files. Import:', labels, 0, False)
            if not ok:
                return
            day = days[labels.index(choice)]

        self.dataEntry1.setText(day['combined'])
        self.dataEntry2.setText(day['param'])
        self.dataEntry3.setText(day['iolite'])
        self.fileType.setCurrentText('csv')
        self.instrument.setCurrentText('Agilent')
        select = self.parent.data_select.select
        select.tabs.setCurrentIndex(1)  # Iolite selection
        select.start.setText(f"{day['start_time']:.2f}")

        checks = sum('<-- check' in l for l in lines)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle('Single-spot runs combined')
        box.setText(f"{len(day['runs'])} spots from {day['tag']} combined; files written to {out_dir}.\n"
                    f"Iolite Start time set to {day['start_time']:.2f}."
                    + (f"\n{checks} spot(s) marked to check: see the details." if checks else ''))
        box.setDetailedText('\n'.join(lines))
        box.exec_()
        self.import_data()

    def import_data(self):
        """
        Create MSData object from files holding all analysis data
        """
        if self.parent.Data is not None:
            self.parent.Data = None

        # create logger
        self.parent.logger = get_logger('./log.txt')
        error_popup.attach(self.parent.logger)
        self.parent.logger.info('Starting new session.')

        # create reader
        reader = msd.DataReader(filename=self.dataEntry1.text(), filetype=str(
            self.fileType.currentText()), instrument=str(self.instrument.currentText()))

        # create MSData
        self.parent.Data = msd.MSData(reader, self.parent.logger)
        self.parent.Data.read_srms()

        # read Param if given
        if self.dataEntry2.text():
            self.parent.Data.param = mse.Param(
                path=str(self.dataEntry2.text()), logger=self.parent.logger)

        # read iolite
        if self.dataEntry3.text():
            self.parent.Iolite = mse.Iolite(path=str(self.dataEntry3.text()))

        # set srms to bulk analysis window combo box
        stds = self.parent.Data.srms.index.values
        self.parent.bulk_analysis.standard.clear()
        self.parent.bulk_analysis.standard.addItems(stds)

        # set elements to imaging window combobox
        elems = self.parent.Data.isotope_names
        self.parent.imaging.element.clear()
        self.parent.imaging.element.addItems(elems)

        # set elements to show data window combobox
        self.parent.show_data.elem.clear()
        self.parent.show_data.elem.addItems(elems)

        # plot data to graph in data select window
        self.parent.Data.graph(ax=self.parent.data_select.ax)
        self.parent.data_select.canvas.draw()

        # show spreadsheet table of raw data in bulk analysis window
        model = PandasModel(self.parent.Data.data)
        self.parent.bulk_analysis.table.table['Raw'].setModel(model)

        # change to second tab - data selection
        self.parent.change_layout(1)
