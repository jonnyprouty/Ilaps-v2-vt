"""Prepare laser ablation data for Ilaps.

Two commands:

  combine      Same as tools/make_iolite.py on a folder: join single-spot Agilent runs into
               one file per day, with a synthetic Iolite log, a Param file and a run-order
               table. make_iolite.py itself needs no Ilaps environment.

  internal-std Write the 'internal standard' sheet of a Param file from EPMA results
               (oxide wt%) for samples and SRM.xlsx values for reference materials.
               Can also create a Param file from an Iolite log's peak names.

Run with the Ilaps environment, e.g.
  ilaps/bin/python tools/ilaps_prep.py combine "/path/to/runs" --prefix Victor
  ilaps/bin/python tools/ilaps_prep.py internal-std --param run_PARAM.xlsx \
      --calibrant BCR-2 --epma epma.xlsx --is Si28=SiO2 --is Ca43=CaO

See SOP_laser_data_reduction.md (or .html) in the Ilaps folder for the full procedure.
"""
import argparse
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ILAPS_DIR = os.path.dirname(HERE)

ATOMIC = {'O': 15.999, 'Na': 22.990, 'Mg': 24.305, 'Al': 26.982, 'Si': 28.085, 'P': 30.974,
          'K': 39.098, 'Ca': 40.078, 'Ti': 47.867, 'Cr': 51.996, 'Mn': 54.938, 'Fe': 55.845}

# Oxide formula -> (element, atoms of element, atoms of O)
OXIDES = {'Na2O': ('Na', 2, 1), 'MgO': ('Mg', 1, 1), 'Al2O3': ('Al', 2, 3), 'SiO2': ('Si', 1, 2),
          'P2O5': ('P', 2, 5), 'K2O': ('K', 2, 1), 'CaO': ('Ca', 1, 1), 'TiO2': ('Ti', 1, 2),
          'Cr2O3': ('Cr', 2, 3), 'MnO': ('Mn', 1, 1), 'FeO': ('Fe', 1, 1), 'Fe2O3': ('Fe', 2, 3)}

# Combining runs, the Iolite log and the total-sum factors live in make_iolite.py (standalone).
sys.path.insert(0, HERE)
import make_iolite  # noqa: E402

IOLITE_HEADER = ("Timestamp, Sequence Number, SubPoint Number, Vertix Number, Comment, X, Y, "
                 "Intended X, Intended Y, Scan Velocity, Laser State, Laser Rep. Rate, Spot Type, "
                 "Spot Size, Spot Angle, MFC1, MFC2, Cell Pressure, Fluence At Sample")


def oxide_to_ppm_factor(oxide):
    el, n, m = OXIDES[oxide]
    return el, 1e4 * n * ATOMIC[el] / (n * ATOMIC[el] + m * ATOMIC['O'])


def normalize_oxide(col):
    """Map common XRF/EPMA header variants to the plain formula, e.g. 'Fe2O3T', 'Fe2O3(T)',
    'FeO*', 'SiO2 (wt%)' -> 'Fe2O3', 'FeO', 'SiO2'. Unknown headers are returned unchanged."""
    c = re.sub(r'\s*\((wt\s*%|%)\)|\s*wt\s*%|\s*%', '', str(col).strip(), flags=re.I)
    c = re.sub(r'(\(t\)|\(tot\)|tot|\*|t)$', '', c, flags=re.I) if c.lower().startswith('fe') else c
    return c if c in OXIDES else col


def element_of(isotope):
    return re.match(r'[A-Z][a-z]?', isotope).group(0)


def ts_sheet():
    return pd.Series(dict(make_iolite.TS_FACTORS))


def write_param(path, names, is_sheet=None):
    """Write a Param file. Ilaps crashes on import if any of the three sheets is missing."""
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame(names).to_excel(xw, sheet_name='names', header=False, index=False)
        (is_sheet if is_sheet is not None else pd.DataFrame()).to_excel(xw, sheet_name='internal standard')
        ts_sheet().to_excel(xw, sheet_name='total sum', header=False)


# ---------------------------------------------------------------- combine
# Same as running make_iolite.py on a folder (it writes the Param files too).

def cmd_combine(a):
    files = make_iolite.collect_files([a.input_dir], a.pattern)
    out_dir = a.output_dir or a.input_dir
    prefix = a.prefix or os.path.basename(os.path.normpath(a.input_dir)).replace(' ', '_')
    try:
        make_iolite.make(files, out_dir, prefix, a.blank_seconds, a.sd_multiply, a.strip)
    except ValueError as e:
        sys.exit(str(e))


# ---------------------------------------------------------------- internal-std

def cmd_internal_std(a):
    if a.iolite:
        io = pd.read_csv(a.iolite, sep=',', engine='python')
        names = list(io[' Comment'].dropna())
        if os.path.exists(a.param):
            sys.exit(f'{a.param} already exists; drop --iolite to update it, or pick a new name.')
    else:
        names = list(pd.read_excel(a.param, sheet_name='names', header=None)[0])

    if not a.internal_standards:
        if not a.iolite:
            sys.exit('Give at least one --is ISOTOPE=OXIDE (or --iolite to create a Param file without one).')
        write_param(a.param, names)
        print(f'Wrote {a.param}: {len(names)} peak names, total-sum factors, empty internal standard sheet.')
        return

    srm = pd.read_excel(a.srm, index_col=0)
    if a.calibrant is None:
        sys.exit('--calibrant is required with --is.')
    if a.calibrant not in srm.index:
        sys.exit(f'Calibrant {a.calibrant} is not in {a.srm}.')
    if a.calibrant not in names:
        sys.exit(f'Calibrant {a.calibrant} is not among the peak names.')

    pairs = []
    for spec in a.internal_standards:
        iso, _, ox = spec.partition('=')
        if ox not in OXIDES:
            sys.exit(f'Unknown oxide {ox}. Known: {", ".join(OXIDES)}')
        el, fac = oxide_to_ppm_factor(ox)
        if element_of(iso) != el:
            sys.exit(f'{iso} is not an isotope of {el} ({ox}).')
        if pd.isna(srm.loc[a.calibrant].get(el)):
            sys.exit(f'Calibrant {a.calibrant} has no {el} value in {a.srm}; it cannot be used with IS {iso}.')
        pairs.append((iso, ox, el, fac))

    epma = None
    if a.epma:
        epma = pd.read_excel(a.epma) if a.epma.endswith(('.xlsx', '.xls')) else pd.read_csv(a.epma)
        epma = epma.rename(columns={epma.columns[0]: 'name'})
        epma = epma.rename(columns=normalize_oxide)
        epma['name'] = epma['name'].astype(str).str.strip()
        counts = epma['name'].value_counts()
        epma = epma.groupby('name').mean(numeric_only=True)

    # One row per peak, in run order, skipping calibrant peaks: Ilaps matches rows by position.
    rows, problems = [], []
    for n in names:
        if n == a.calibrant:
            continue
        vals = {}
        for iso, ox, el, fac in pairs:
            if n in srm.index and not pd.isna(srm.loc[n].get(el)):
                vals[iso] = float(srm.loc[n, el])
            elif epma is not None and n in epma.index and ox in epma.columns and not pd.isna(epma.loc[n, ox]):
                vals[iso] = round(float(epma.loc[n, ox]) * fac, 1)
            else:
                problems.append(f'{n}: no {ox} (EPMA) or {el} (SRM.xlsx) value')
        rows.append((n, vals))
    if problems:
        sys.exit('Missing internal-standard values:\n  ' + '\n  '.join(sorted(set(problems))))

    is_sheet = pd.DataFrame([v for _, v in rows], index=[n for n, _ in rows])[[p[0] for p in pairs]]
    if a.iolite:
        write_param(a.param, names, is_sheet)
    else:
        sheets = pd.read_excel(a.param, sheet_name=None, header=None)
        with pd.ExcelWriter(a.param) as xw:
            sheets['names'].to_excel(xw, sheet_name='names', header=False, index=False)
            is_sheet.to_excel(xw, sheet_name='internal standard')
            ts = sheets.get('total sum')
            (ts if ts is not None else ts_sheet().reset_index()).to_excel(
                xw, sheet_name='total sum', header=False, index=False)

    print(f'Wrote internal standard sheet to {a.param}: {len(is_sheet)} rows '
          f'({len(names) - len(is_sheet)} {a.calibrant} calibrant peaks left out).')
    for iso, ox, el, fac in pairs:
        print(f'  {iso} from {ox}: ppm = wt% x {fac:.1f}')
    if epma is not None:
        multi = counts[counts > 1]
        if len(multi):
            print('  Averaged over repeat rows: ' + ', '.join(f'{k} ({v})' for k, v in multi.items()))
    print(is_sheet.to_string())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('combine', help='join single-spot runs into one file per day')
    c.add_argument('input_dir')
    c.add_argument('--prefix', help='output file prefix (default: folder name)')
    c.add_argument('--pattern', default='*.txt', help='which files to read (default: *.txt)')
    c.add_argument('--output-dir', help='where to write (default: input_dir)')
    c.add_argument('--strip', action='append', default=['USGS-'],
                   help='text removed from file names to make peak names (default: USGS-)')
    c.add_argument('--blank-seconds', type=float, default=50,
                   help='blank length at the start of every run used to find the laser window (default 50)')
    c.add_argument('--sd-multiply', type=float, default=10)
    c.set_defaults(func=cmd_combine)

    s = sub.add_parser('internal-std', help='write internal standard sheet from EPMA data, '
                                            'or create a Param file from an Iolite log')
    s.add_argument('--param', required=True, help='Param .xlsx to update (or create, with --iolite)')
    s.add_argument('--calibrant', help='standard you will select in Ilaps, e.g. BCR-2 (needed with --is)')
    s.add_argument('--is', dest='internal_standards', action='append', default=[],
                   metavar='ISOTOPE=OXIDE', help='e.g. Si28=SiO2; repeat for more than one')
    s.add_argument('--epma', '--xrf', dest='epma',
                   help='EPMA or XRF table: first column sample name, oxide columns in wt%%')
    s.add_argument('--iolite', help='create a new Param file using peak names from this Iolite log')
    s.add_argument('--srm', default=os.path.join(ILAPS_DIR, 'SRM.xlsx'))
    s.set_defaults(func=cmd_internal_std)

    a = p.parse_args()
    a.func(a)


if __name__ == '__main__':
    main()
