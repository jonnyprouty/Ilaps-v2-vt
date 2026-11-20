"""Tests for internal_std.py (run from the Ilaps folder: ilaps/bin/python -m unittest discover tests)."""
import os
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
import internal_std as ist  # noqa: E402

SRM = pd.DataFrame({'Si': [252000.0, 307573.4], 'Ca': [50800.0, None]}, index=['BCR-2', 'SDC-1'])
PEAKS = ['BCR-2', 'SDC-1', 'VG-A1', 'VG-A1', 'VG-A2', 'BCR-2']


def table_file(df, ext):
    fd, p = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    (df.to_excel(p, index=False) if ext == '.xlsx' else df.to_csv(p, index=False))
    return p


class ReadTable(unittest.TestCase):

    def test_headers_repeats_and_formats(self):
        df = pd.DataFrame({'Sample': ['VG-A1', 'VG-A1', ' VG-A2'], 'SiO2 (wt%)': [40.0, 42.0, 38.0],
                           'Fe2O3T': [20.0, 21.0, 19.0], 'note': ['a', 'b', 'c']})
        for ext in ('.xlsx', '.csv'):
            p = table_file(df, ext)
            try:
                t, counts = ist.read_table(p)
            finally:
                os.remove(p)
            self.assertEqual(list(t.columns), ['SiO2', 'Fe2O3'])
            self.assertAlmostEqual(t.loc['VG-A1', 'SiO2'], 41.0)
            self.assertIn('VG-A2', t.index)
            self.assertEqual(counts['VG-A1'], 2)

    def test_no_oxides(self):
        p = table_file(pd.DataFrame({'name': ['a'], 'x': [1]}), '.csv')
        try:
            with self.assertRaises(ValueError):
                ist.read_table(p)
        finally:
            os.remove(p)


class BuildSheet(unittest.TestCase):

    def setUp(self):
        self.table = pd.DataFrame({'SiO2': [41.0, 38.0], 'CaO': [10.0, 12.0]}, index=['VG-A1', 'VG-A2'])

    def test_values_and_sources(self):
        sheet, src = ist.build_sheet(PEAKS, 'BCR-2', [('Si28', 'SiO2')], self.table, SRM)
        self.assertEqual(list(sheet.index), ['SDC-1', 'VG-A1', 'VG-A2'])  # calibrant left out
        self.assertEqual(sheet.loc['SDC-1', 'Si28'], 307573.4)            # from SRM.xlsx
        self.assertAlmostEqual(sheet.loc['VG-A1', 'Si28'], round(41.0 * 4674.4, 0), delta=40)
        self.assertEqual(src, {'SDC-1': 'SRM.xlsx', 'VG-A1': 'table', 'VG-A2': 'table'})

    def test_missing_value_and_calibrant_without_element(self):
        with self.assertRaises(ValueError) as cm:
            ist.build_sheet(PEAKS + ['VG-B1'], 'SDC-1', [('Ca43', 'CaO')], self.table, SRM)
        msg = str(cm.exception)
        self.assertIn('VG-B1: no CaO', msg)
        self.assertIn('Calibrant SDC-1 has no Ca value', msg)

    def test_factor(self):
        self.assertAlmostEqual(ist.ppm_per_wt_pct('SiO2'), 4674.4, places=1)
        self.assertAlmostEqual(ist.ppm_per_wt_pct('CaO'), 7147.0, places=1)

    def test_pairs_si_first(self):
        pairs = ist.candidate_pairs(['CaO', 'SiO2'], ['Ca43', 'Ca44', 'Si28', 'Na23'])
        self.assertEqual(pairs[0], ('Si28', 'SiO2'))
        self.assertEqual(len(pairs), 3)

    def test_save_to_param_keeps_other_sheets(self):
        fd, p = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        try:
            with pd.ExcelWriter(p) as xw:
                pd.DataFrame(PEAKS).to_excel(xw, sheet_name='names', header=False, index=False)
                pd.DataFrame().to_excel(xw, sheet_name='internal standard')
                pd.Series({'Si28': 46.75}).to_excel(xw, sheet_name='total sum', header=False)
            sheet, _ = ist.build_sheet(PEAKS, 'BCR-2', [('Si28', 'SiO2')], self.table, SRM)
            ist.save_to_param(p, sheet)
            x = pd.read_excel(p, sheet_name=None, header=None)
            self.assertEqual(list(x['names'][0]), PEAKS)
            self.assertEqual(x['total sum'].iloc[0].tolist(), ['Si28', 46.75])
            is_ = pd.read_excel(p, sheet_name='internal standard', index_col=0)
            self.assertEqual(list(is_.index), ['SDC-1', 'VG-A1', 'VG-A2'])
        finally:
            os.remove(p)


if __name__ == '__main__':
    unittest.main()
