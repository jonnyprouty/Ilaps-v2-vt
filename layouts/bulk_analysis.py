import sys
from PySide2.QtWidgets import *
from PySide2 import QtGui
from PySide2.QtCore import Qt
from PySide2.QtCore import QEventLoop
from widgets.tab_table import TabTable
from widgets.pandas_model import PandasModel
import error_popup
import internal_std
from widgets.drop_elems_window import ElemWindow
from widgets.stat_export_select import DataTableWindow

from imgMS import MSData as msd
from imgMS import MSEval as mse
from imgMS.side_functions import *


class BulkAnalysis(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.suma = 1000000
        self.skip_isotopes = []
        self.oxide_form = False

        self.stat_export_table = None

        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.mainLayout.setAlignment(Qt.AlignCenter)

        self.settingsGroup = QGroupBox('Settings')
        layout = QGridLayout()

        self.lodLbl = QLabel('Detection limit')
        layout.addWidget(self.lodLbl, 0, 0)
        self.lodCombo = QComboBox()
        self.lodCombo.addItems(['beginning', 'end', 'all'])
        layout.addWidget(self.lodCombo, 1, 0)

        self.despikingLbl = QLabel('Despiking')
        layout.addWidget(self.despikingLbl, 0, 1)
        self.despikingCombo = QComboBox()
        self.despikingCombo.addItems(['True', 'False'])
        layout.addWidget(self.despikingCombo, 1, 1)

        self.methodLbl = QLabel('Method')
        layout.addWidget(self.methodLbl, 0, 2)
        self.method = QComboBox()
        self.method.addItems(['integral', 'intensity'])
        layout.addWidget(self.method, 1, 2)

        self.abltimeLbl = QLabel('Peak ablation time:')
        layout.addWidget(self.abltimeLbl, 0, 3)
        self.ablation = QLineEdit()
        layout.addWidget(self.ablation, 1, 3)

        self.standardLbl = QLabel('Standard')
        layout.addWidget(self.standardLbl, 0, 4)
        self.standard = QComboBox()
        self.standard.addItems(['Select standard'])
        layout.addWidget(self.standard, 1, 4)

        self.signaldriftBox = QCheckBox('Drift Correction')
        layout.addWidget(self.signaldriftBox, 1, 5)

        self.averageBtn = QPushButton('Average')
        layout.addWidget(self.averageBtn, 0, 6)
        self.averageBtn.clicked.connect(self.average)

        self.quantifyBtn = QPushButton('Quantification')
        layout.addWidget(self.quantifyBtn, 1, 6)
        self.quantifyBtn.clicked.connect(self.quantify)

        self.intStdCor = QPushButton('Internal Std Correction')
        layout.addWidget(self.intStdCor, 0, 7)
        self.intStdCor.clicked.connect(self.correctionIS)

        self.totSumCor = QPushButton('Total Sum Correction')
        layout.addWidget(self.totSumCor, 1, 7)
        self.totSumCor.clicked.connect(self.correctionTS)

        self.loadISBtn = QPushButton('Load internal standard...')
        self.loadISBtn.setToolTip('Read XRF or EPMA results (sample name + oxide wt%) and use one oxide, '
                                  'e.g. SiO2 for Si28, as the internal standard. Reference materials '
                                  'take their values from SRM.xlsx.')
        layout.addWidget(self.loadISBtn, 0, 8)
        self.loadISBtn.clicked.connect(self.load_internal_std)

        self.tssettingsBtn = QPushButton('TS settings')
        layout.addWidget(self.tssettingsBtn, 1, 8)
        self.tssettingsBtn.clicked.connect(self.elem_window)

        self.reportBtn = QPushButton('Report')
        layout.addWidget(self.reportBtn, 0, 9)
        self.reportBtn.clicked.connect(self.report)

        self.exportBtn = QPushButton('Export')
        layout.addWidget(self.exportBtn, 1, 9)
        self.exportBtn.clicked.connect(self.export)

        self.exportstatsBtn = QPushButton('Export stats')
        layout.addWidget(self.exportstatsBtn, 1, 10)
        self.exportstatsBtn.clicked.connect(self.export_stats)

        layout.setAlignment(Qt.AlignLeft)
        layout.setSizeConstraint(QLayout.SetFixedSize)
        self.settingsGroup.setLayout(layout)

        self.mainLayout.addWidget(self.settingsGroup)

        self.table = TabTable(self)
        self.mainLayout.addWidget(self.table)

    def get_page(self):
        """
        Returns Page for bulk analysis for main stack of gui
        Returns
        -------
        mainWidget : QWidget
            The widget that the houses the bulk analysis screen.
        """
        return self.mainWidget

    def average(self):
        """
        Calculate average of peaks for MSData
        """
        # get values from GUI
        method = self.method.currentText()
        scale = self.lodCombo.currentText()
        despiking = self.despikingCombo.currentText() == 'True'  # text 'False' would count as true

        # calculate average
        self.parent.Data.average_isotopes(
            despiked=despiking, bcgcor_method=scale, method=method)

        # check length of names vs peaks
        if len(self.parent.Data.names) != len(self.parent.Data.means.index):
            error_dialog = QErrorMessage()
            error_dialog.showMessage(
                f'Number of peaks({len(self.parent.Data.means.index)}) doesnt\
                    match number of given names({len(self.parent.Data.names)}).')
            error_dialog.exec_()
            return

        # show average data
        model = PandasModel(self.parent.Data.means)
        self.table.table['Average'].setModel(model)
        self.table.show_tab(1)

    def quantify(self):
        """
        Calculate quantified values of peaks for MSData
        """

        # get values
        std = self.standard.currentText()
        abltime = self.ablation.text()
        method = self.method.currentText()
        scale = self.lodCombo.currentText()

        # check if abltime not missing
        if abltime == '' and method == 'integral':
            error_dialog = QErrorMessage()
            error_dialog.showMessage(
                'Missing ablation time while method is integral.')
            error_dialog.exec_()
            return

        # check if abltime was endered and convert to mumber
        if abltime != '':
            abltime = float(abltime)
        else:
            abltime = None

        # check if selected standard was measured
        if std not in self.parent.Data.names:
            error_dialog = QErrorMessage()
            error_dialog.showMessage('{} not in peak names.'.format(std))
            error_dialog.exec_()
            return

        # check if using signal drift correction
        drift = self.signaldriftBox.isChecked()
        print(drift)

        # quantify data
        self.parent.Data.quantify_isotopes(
            srm_name=std, drift_correction=drift)

        # calculate detection limit
        self.parent.Data.detection_limit(
            method=method, scale=scale, ablation_time=abltime)

        # show quantified data
        model = PandasModel(self.parent.Data.quantified)
        self.table.table['Quantified'].setModel(model)

        self.table.show_tab(2)

    def clear_results(self):
        """
        Empty the result tables after the peak windows change.
        """
        for name in ('Average', 'Quantified', 'Internal Std', 'Total Sum'):
            self.table.table[name].setModel(None)

    def load_internal_std(self):
        """
        Build the internal standard sheet from an XRF/EPMA table and SRM.xlsx and attach it to the data.
        """
        data = self.parent.Data
        if data is None or not data.names:
            error_popup.notify('Import the data and select the peaks before loading the internal standard.')
            return
        calibrant = self.standard.currentText()
        if calibrant not in data.srms.index:
            error_popup.notify('Choose the calibrant standard (Standard box) first: it decides which '
                               'elements can be internal standards.')
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'XRF or EPMA results (first column sample name, oxide wt% columns)', '',
            'Tables (*.xlsx *.xls *.csv);;All files (*)')
        if not path:
            return
        try:
            table, counts = internal_std.read_table(path)
        except Exception as e:
            error_popup.notify(f'Could not read {path}: {e}')
            return
        pairs = internal_std.candidate_pairs(list(table.columns), list(data.isotope_names))
        if not pairs:
            error_popup.notify('None of the oxides in the table belongs to a measured isotope.')
            return

        # choose the internal standard(s)
        dlg = QDialog(self)
        dlg.setWindowTitle('Internal standard')
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel('Use as internal standard (the first ticked one is shown in the table):'))
        boxes = []
        for i, (iso, ox) in enumerate(pairs):
            cb = QCheckBox(f'{iso} from {ox}  (ppm = wt% x {internal_std.ppm_per_wt_pct(ox):.1f})')
            cb.setChecked(i == 0)
            lay.addWidget(cb)
            boxes.append(cb)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if not dlg.exec_():
            return
        chosen = [p for p, cb in zip(pairs, boxes) if cb.isChecked()]
        if not chosen:
            return

        try:
            sheet, source = internal_std.build_sheet(data.names, calibrant, chosen, table, data.srms)
        except ValueError as e:
            error_popup.notify(e)
            return

        if data.param is None:
            data.param = mse.Param.__new__(mse.Param)
            data.param.path, data.param.logger = None, data.logger
            data.param.peak_names, data.param.ts_coef = list(data.names), {}
        data.param.is_coef = sheet
        if data.logger is not None:
            data.logger.info(f'Internal standard loaded from {path}: '
                             + ', '.join(f'{i} from {o}' for i, o in chosen))

        n_srm = sum(v == 'SRM.xlsx' for v in source.values())
        repeats = [f'{k} ({v})' for k, v in counts.items() if v > 1 and k in sheet.index]
        msg = (f"Internal standard loaded: {', '.join(f'{i} from {o}' for i, o in chosen)} for "
               f"{len(sheet)} samples ({n_srm} reference materials from SRM.xlsx, "
               f"{len(sheet) - n_srm} from the table).")
        if repeats:
            msg += '\nAveraged over repeat rows: ' + ', '.join(repeats) + '.'
        param_path = self.parent.welcome.dataEntry2.text().strip()
        box = QMessageBox(self)
        box.setWindowTitle('Internal standard')
        box.setText(msg + '\n\nNext: Internal Std Correction.')
        box.setDetailedText(sheet.to_string())
        save = None
        if param_path:
            save = box.addButton('Also save to the Param file', QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Ok)
        box.exec_()
        if save is not None and box.clickedButton() is save:
            try:
                internal_std.save_to_param(param_path, sheet)
            except Exception as e:
                error_popup.notify(f'Could not save to {param_path}: {e}')

    def correctionIS(self):
        """
        Correct quantified values of MSData using internal standard correction
        """
        # check if parameters were imported and contain coef for IS
        if self.parent.Data.param is None:
            error_dialog = QErrorMessage()
            error_dialog.showMessage(
                'Missing data for internal standard correction.')
            error_dialog.exec_()
            return
        elif self.parent.Data.param.is_coef is None:
            error_dialog = QErrorMessage()
            error_dialog.showMessage(
                'Missing data for internal standard correction.')
            error_dialog.exec_()
            return

        # correct data; imgMS raises ValueError when the internal standard sheet does not match the peaks
        try:
            self.parent.Data.IS_correction()
        except ValueError as e:
            error_popup.notify(e)
            return

        # show data corrected by internal standard
        model = PandasModel(
            self.parent.Data.corrected_IS[self.parent.Data.param.is_coef.columns[0]])
        self.table.table['Internal Std'].setModel(model)
        self.table.show_tab(3)

    def correctionTS(self):
        """
        Correct quantified values of MSData using total sum correction
        """
        # correct data
        self.parent.Data.TS_correction(
            suma=self.suma, skip_isotopes=self.skip_isotopes, return_oxides=self.oxide_form)

        # show data corrected by total sum
        model = PandasModel(self.parent.Data.corrected_TS)
        self.table.table['Total Sum'].setModel(model)
        self.table.show_tab(4)

    def report(self):
        # round all data
        self.parent.Data.report()

        # show all data
        if self.parent.Data.quantified is not None:
            model = PandasModel(self.parent.Data.quantified)
            self.table.table['Quantified'].setModel(model)
        if self.parent.Data.corrected_IS is not None:
            model = PandasModel(
                self.parent.Data.corrected_IS[self.parent.Data.param.is_coef.columns[0]])
            self.table.table['Internal Std'].setModel(model)
        if self.parent.Data.corrected_TS is not None:
            model = PandasModel(self.parent.Data.corrected_TS)
            self.table.table['Total Sum'].setModel(model)

    def export(self):
        # get filename
        filename, filters = QFileDialog.getSaveFileName(
            self, 'Save file', '', 'Excel (*.xlsx);;All files (*)')

        # save data
        if filename:
            self.parent.Data.export(filename)

    def export_stats(self):
        # export data into excel in a formated style, containing means, sd, max and min for repeated samples

        # get data table to export
        self.stat_export_table = None
        window_to_open = DataTableWindow(self)
        window_to_open.setAttribute(Qt.WA_DeleteOnClose)
        window_to_open.show()

        loop = QEventLoop()
        window_to_open.destroyed.connect(loop.quit)
        loop.exec_()
        if not self.stat_export_table:  # table window closed without Apply
            return

        # get filename
        filename, filters = QFileDialog.getSaveFileName(
            self, 'Save file', '', 'Excel (*.xlsx);;All files (*)')
        if not filename:  # save dialog cancelled
            return

        # export data (imgMS adds .xlsx when the name has no or another extension)
        self.parent.Data.formated_export(
            filename, table=self.stat_export_table)

    def elem_window(self):
        window_to_open = ElemWindow(self)
        window_to_open.setAttribute(Qt.WA_DeleteOnClose)
        window_to_open.show()
