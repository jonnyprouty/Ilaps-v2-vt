"""Internal standard values for Ilaps from an XRF or EPMA table.

The table has the sample name in its first column and oxide wt% in the others (SiO2, CaO, ...;
headers such as 'SiO2 (wt%)' or 'Fe2O3T' are recognised). Repeat rows of a sample are averaged.
Reference materials take their values from SRM.xlsx (element ppm, as for the calibration), so they
need no row in the table. The result has one row per sample name, which imgMS matches to the peaks
by name.
"""
import re

import pandas as pd

ATOMIC = {'O': 15.999, 'Na': 22.990, 'Mg': 24.305, 'Al': 26.982, 'Si': 28.085, 'P': 30.974,
          'K': 39.098, 'Ca': 40.078, 'Ti': 47.867, 'Cr': 51.996, 'Mn': 54.938, 'Fe': 55.845}

# oxide -> (element, atoms of element, atoms of O)
OXIDES = {'Na2O': ('Na', 2, 1), 'MgO': ('Mg', 1, 1), 'Al2O3': ('Al', 2, 3), 'SiO2': ('Si', 1, 2),
          'P2O5': ('P', 2, 5), 'K2O': ('K', 2, 1), 'CaO': ('Ca', 1, 1), 'TiO2': ('Ti', 1, 2),
          'Cr2O3': ('Cr', 2, 3), 'MnO': ('Mn', 1, 1), 'FeO': ('Fe', 1, 1), 'Fe2O3': ('Fe', 2, 3)}


def ppm_per_wt_pct(oxide):
    """Element ppm per 1 wt% of the oxide, e.g. SiO2 -> 4674.4."""
    el, n, m = OXIDES[oxide]
    return 1e4 * n * ATOMIC[el] / (n * ATOMIC[el] + m * ATOMIC['O'])


def element_of(isotope):
    return re.match(r'[A-Z][a-z]?', isotope).group(0)


def normalize_oxide(col):
    """'SiO2 (wt%)', 'Fe2O3T', 'FeO*' -> 'SiO2', 'Fe2O3', 'FeO'; other headers unchanged."""
    c = re.sub(r'\s*\((wt\s*%|%)\)|\s*wt\s*%|\s*%', '', str(col).strip(), flags=re.I)
    c = re.sub(r'(\(t\)|\(tot\)|tot|\*|t)$', '', c, flags=re.I) if c.lower().startswith('fe') else c
    return c if c in OXIDES else col


def read_table(path):
    """Read an XRF/EPMA table (.xlsx, .xls, .csv). Returns (oxide wt% per sample, rows per sample)."""
    t = pd.read_excel(path) if str(path).lower().endswith(('.xlsx', '.xls')) else pd.read_csv(path)
    t = t.rename(columns={t.columns[0]: 'name'}).rename(columns=normalize_oxide)
    t = t[t['name'].notna()]
    t['name'] = t['name'].astype(str).str.strip()
    oxides = [c for c in t.columns if c in OXIDES]
    if not oxides:
        raise ValueError(f'No oxide columns found in {path}. Expected headers such as SiO2, CaO, Fe2O3 (wt%).')
    t[oxides] = t[oxides].apply(pd.to_numeric, errors='coerce')
    counts = t['name'].value_counts()
    return t.groupby('name', sort=False)[oxides].mean(), counts


def candidate_pairs(oxides, isotopes):
    """(isotope, oxide) pairs possible with this table and these measured isotopes, Si first."""
    pairs = [(iso, ox) for ox in oxides for iso in isotopes if element_of(iso) == OXIDES[ox][0]]
    return sorted(pairs, key=lambda p: (p[0][:2] != 'Si', p[1], p[0]))


def build_sheet(peak_names, calibrant, pairs, table, srm):
    """
    Internal standard sheet: one row per sample name (calibrant left out), one column per isotope,
    element ppm. Returns (sheet, source) where source[name] is 'SRM.xlsx' or 'table'.
    Raises ValueError listing every problem (missing values, calibrant without the element).
    """
    problems = []
    for iso, ox in pairs:
        el = OXIDES[ox][0]
        if calibrant not in srm.index:
            problems.append(f'Calibrant {calibrant} is not in SRM.xlsx.')
        elif pd.isna(srm.loc[calibrant].get(el)):
            problems.append(f'Calibrant {calibrant} has no {el} value in SRM.xlsx, so {iso} cannot be '
                            f'the internal standard with this calibrant.')
    rows, source = {}, {}
    for name in dict.fromkeys(str(n).strip() for n in peak_names):
        if name == calibrant:
            continue
        vals = {}
        for iso, ox in pairs:
            el = OXIDES[ox][0]
            if name in srm.index and not pd.isna(srm.loc[name].get(el)):
                vals[iso] = float(srm.loc[name, el])
                source[name] = 'SRM.xlsx'
            elif name in table.index and not pd.isna(table.loc[name, ox]):
                vals[iso] = round(float(table.loc[name, ox]) * ppm_per_wt_pct(ox), 1)
                source.setdefault(name, 'table')
            else:
                problems.append(f'{name}: no {ox} in the table and no {el} in SRM.xlsx')
        rows[name] = vals
    if problems:
        raise ValueError('Internal standard not loaded:\n' + '\n'.join(dict.fromkeys(problems)))
    sheet = pd.DataFrame.from_dict(rows, orient='index')[[iso for iso, _ in pairs]]
    return sheet, source


def save_to_param(path, sheet):
    """Write the sheet into the 'internal standard' sheet of a Param file, keeping its other sheets."""
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    with pd.ExcelWriter(path) as xw:
        for name, df in sheets.items():
            if name == 'internal standard':
                continue
            df.to_excel(xw, sheet_name=name, header=False, index=False)
        sheet.to_excel(xw, sheet_name='internal standard')
