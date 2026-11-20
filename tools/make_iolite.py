#!/usr/bin/env python3
"""Make an Iolite laser log for single-spot laser ablation runs.

Each input file is one Agilent run (a .txt/.csv export containing a single spot: blank, then
ablation). The tool joins the runs of each day into one continuous data file and writes a
matching Iolite log that marks where every spot's ablation starts and ends, plus an Ilaps Param
file. Ilaps can then select all spots in one go (Iolite selection).

Outputs, per acquisition day (PREFIX defaults to the folder name):
  PREFIX_YYYY-MM-DD_combined.csv          the runs joined in acquisition order (counts unchanged)
  PREFIX_YYYY-MM-DD_synthetic_Iolite.csv  the Iolite log for that file (spot names = run names)
  PREFIX_YYYY-MM-DD_PARAM.xlsx            Ilaps Param file: spot names, total-sum factors, empty
                                          internal standard sheet (fill with ilaps_prep.py internal-std)
  PREFIX_YYYY-MM-DD_run_order.txt         one line per spot: name, times, source file

The log is not a real laser log: each spot's on/off times are detected from the run's own
blank, and its timestamps are midnight + time in the combined file (not the real clock), so use
the two files together, in Ilaps.

Easy use: run it with no arguments (or use the "Make Iolite log" launcher) and pick the run
files in the window.
Command line:
  python3 make_iolite.py RUN_FOLDER_OR_FILES... [--prefix NAME] [--output-dir DIR]

Needs only Python 3 (standard library; the window uses tkinter).
"""
import argparse
import glob
import os
import re
import statistics
import sys
import zipfile
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

IOLITE_HEADER = ("Timestamp, Sequence Number, SubPoint Number, Vertix Number, Comment, X, Y, "
                 "Intended X, Intended Y, Scan Velocity, Laser State, Laser Rep. Rate, Spot Type, "
                 "Spot Size, Spot Angle, MFC1, MFC2, Cell Pressure, Fluence At Sample")

DEFAULTS = dict(blank_seconds=50.0, sd_multiply=10.0, strip=["USGS-"], pattern="*.txt")

# Total-sum factors for the Param file: element wt% in its oxide, as in Ilaps' default_sum_koef.xlsx.
# Listed for every common isotope, since Ilaps matches total-sum entries by exact isotope name
# (Ilaps' own defaults have Ca44 but not Ca43).
TS_ELEMENT = {"Na": 74.186, "Mg": 60.304, "Al": 52.925, "Si": 46.75, "P": 43.64, "K": 83.01,
              "Ca": 71.469, "Ti": 59.934, "Mn": 77.44, "Fe": 69.943, "Co": 78.65, "Cu": 79.88,
              "Sn": 78.77, "Sb": 83.53, "Pb": 92.83}
TS_ISOTOPES = {"Na": [23], "Mg": [24, 25, 26], "Al": [27], "Si": [28, 29, 30], "P": [31],
               "K": [39], "Ca": [42, 43, 44], "Ti": [47, 48, 49], "Mn": [55], "Fe": [54, 56, 57],
               "Co": [59], "Cu": [63, 65], "Sn": [118, 120], "Sb": [121], "Pb": [208]}
TS_FACTORS = [(f"{el}{a}", f) for el, f in TS_ELEMENT.items() for a in TS_ISOTOPES[el]]


# ---------------------------------------------------------------- minimal .xlsx writer

def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path, sheets):
    """Write a plain .xlsx workbook. sheets: list of (sheet name, rows); a row is a list of str/number/None."""
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    wb_sheets, wb_rels = [], []
    files = {}
    for k, (name, rows) in enumerate(sheets, 1):
        ct.append(f'<Override PartName="/xl/worksheets/sheet{k}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        wb_sheets.append(f'<sheet name="{escape(name)}" sheetId="{k}" r:id="rId{k}"/>')
        wb_rels.append(f'<Relationship Id="rId{k}" '
                       'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                       f'Target="worksheets/sheet{k}.xml"/>')
        xr = []
        for i, row in enumerate(rows, 1):
            cells = []
            for j, v in enumerate(row):
                ref = f"{_col(j)}{i}"
                if v is None:
                    continue
                if isinstance(v, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{v!r}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
            xr.append(f'<row r="{i}">{"".join(cells)}</row>')
        files[f"xl/worksheets/sheet{k}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(xr)}</sheetData></worksheet>')
    ct.append("</Types>")
    n = len(sheets)
    files["[Content_Types].xml"] = "".join(ct)
    files["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>')
    files["xl/workbook.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(wb_sheets)}</sheets></workbook>')
    files["xl/_rels/workbook.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(wb_rels) +
        f'<Relationship Id="rId{n + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>')
    files["xl/styles.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ["[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels",
                     "xl/styles.xml"] + [f"xl/worksheets/sheet{k}.xml" for k in range(1, n + 1)]:
            z.writestr(name, files[name])


def write_param(path, names):
    """Ilaps Param file: the three sheets Ilaps needs (a missing sheet crashes its import)."""
    write_xlsx(path, [("names", [[n] for n in names]),
                      ("internal standard", []),
                      ("total sum", [[iso, f] for iso, f in TS_FACTORS])])


# ---------------------------------------------------------------- reading runs

# Month-first only: a day-first style (03/11 = 3 Nov) cannot be told apart from month-first, and a wrong
# guess would silently put runs in the wrong order or day. Unknown styles are reported, not guessed.
TIME_FORMATS = ["%b %d %Y %I:%M %p", "%b %d %Y %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]


def parse_time(text):
    """Acquisition time in any of the date styles MassHunter writes (depends on Windows locale)."""
    t = " ".join(text.split())
    for f in TIME_FORMATS:
        try:
            return datetime.strptime(t, f)
        except ValueError:
            pass
    return None


def read_agilent_run(path):
    """Return (run dict, None) or (None, reason) for one Agilent export."""
    lines = open(path, errors="replace").read().splitlines()
    if lines and lines[0].startswith("Combined from"):
        return None, "a combined file made by this tool, not a single run"
    try:
        hdr = next(i for i, l in enumerate(lines[:10]) if l.startswith("Time"))
    except StopIteration:
        return None, 'no "Time [Sec]" column row (not an Agilent export?)'
    acq_line = next((l for l in lines[:hdr] if l.startswith("Acquired")), None)
    if acq_line is None:
        return None, 'no "Acquired" line (header removed?)'
    m = re.search(r"Acquired\s*:\s*(.+?)\s+using", acq_line)
    if not m:
        return None, 'cannot read the "Acquired" time'
    acq = parse_time(m.group(1))
    if acq is None:
        return None, f"cannot read the acquisition time '{m.group(1)}'"
    data = [l for l in lines[hdr + 1:] if l and l[0].isdigit()]
    if len(data) < 10:
        return None, "too few data rows"
    return dict(acq=acq, header=lines[hdr], head3=lines[:hdr], data=data), None


def ablation_window(data_lines, bcg_s, sdmul, max_gap=5):
    """[on, off) row indices of the single ablation in one run, judged against the run's own
    blank (summed counts of all isotopes). Gaps of <= max_gap rows are merged; the longest
    region is kept, so isolated spikes are ignored. Returns (on, off, n_regions) or None."""
    t = [float(l.split(",", 1)[0]) for l in data_lines]
    tot = [sum(map(float, l.split(",")[1:])) for l in data_lines]
    nb = sum(1 for x in t if x < bcg_s)
    if nb < 2:
        return None
    thr = statistics.mean(tot[:nb]) + sdmul * statistics.stdev(tot[:nb])
    above = [i for i, v in enumerate(tot) if v > thr]
    if not above:
        return None
    regions, cur = [], [above[0], above[0]]
    for i in above[1:]:
        if i - cur[1] <= max_gap:
            cur[1] = i
        else:
            regions.append(cur)
            cur = [i, i]
    regions.append(cur)
    on, last = max(regions, key=lambda r: r[1] - r[0])
    return on, last + 1, len(regions)


def run_name(path, strip):
    """Spot name from the file name: drops the Agilent 'YYYYMMDD-HHMM-' prefix and any --strip text."""
    name = re.sub(r"^\d{8}-\d{4}-", "", os.path.splitext(os.path.basename(path))[0])
    for p in strip:
        name = name.replace(p, "")
    return name


def collect_files(inputs, pattern):
    files = []
    for x in inputs:
        if os.path.isdir(x):
            files += glob.glob(os.path.join(x, pattern))
        else:
            files.append(x)
    return sorted(dict.fromkeys(os.path.abspath(f) for f in files))


# ---------------------------------------------------------------- main work

def make(files, out_dir, prefix, blank_seconds=50.0, sd_multiply=10.0, strip=("USGS-",), say=print):
    """Combine runs per day and write combined file, Iolite log and run order.
    Returns a list of dicts, one per day: tag, runs (in order), paths, start_time."""
    runs, skipped = [], []
    for f in files:
        base = os.path.basename(f)
        if base.startswith(prefix + "_"):
            continue  # our own outputs
        r, why = read_agilent_run(f)
        if r is None:
            skipped.append((base, why))
            continue
        r.update(file=base, name=run_name(f, strip))
        w = ablation_window(r["data"], blank_seconds, sd_multiply)
        if w is None:
            skipped.append((base, "no ablation signal found"))
            continue
        r["on"], r["off"], r["nreg"] = w
        runs.append(r)
    for b, why in skipped:
        say(f"skipped {b}: {why}")
    if not runs:
        raise ValueError("No usable runs found.")
    runs.sort(key=lambda r: r["acq"])
    if len({r["header"] for r in runs}) != 1:
        raise ValueError("The runs have different isotope lists; select runs with the same method only.")
    names = [r["name"] for r in runs]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        say("note: repeated spot names (fine for standards): " + ", ".join(dup))

    results = []
    for day in sorted({r["acq"].date() for r in runs}):
        rr = [r for r in runs if r["acq"].date() == day]
        out, offset = [], 0.0
        for r in rr:
            times = [float(l.split(",", 1)[0]) for l in r["data"]]
            dt = (times[-1] - times[0]) / (len(times) - 1)
            r["t0"], r["t1"] = times[0] + offset, times[-1] + offset
            r["t_on"] = times[r["on"]] + offset
            r["t_off"] = times[r["off"] - 1] + offset  # last ablation row; Ilaps adds 1
            r["dt"] = dt
            for l, t in zip(r["data"], times):
                out.append(f"{t + offset:.3f}," + l.split(",", 1)[1])
            offset += times[-1] + dt
        # No padding row: the lab imgMS reads every row. The original imgMS (0.2.12) drops the final row,
        # which is blank after the last spot, so files still work there.
        tag = f"{prefix}_{day:%Y-%m-%d}"
        method = rr[0]["head3"][2].split("using", 1)[-1].strip() if len(rr[0]["head3"]) > 2 else ""
        head = [f"Combined from {len(rr)} single-spot runs by make_iolite.py",
                "Intensity Vs Time,Counts",
                f"Acquired      : {rr[0]['acq']:%b %d %Y  %I:%M %p} using {method}"]
        footer = ["", "", f"          Printed: {datetime.now():%a %b %d %H:%M:%S %Y}"]
        p_comb = os.path.join(out_dir, f"{tag}_combined.csv")
        with open(p_comb, "w") as fh:
            fh.write("\n".join(head + [rr[0]["header"]] + out + footer) + "\n")

        # Iolite log: timestamp = midnight + combined-file time; row 0 at the first data point, so
        # the Iolite "Start time" in Ilaps is any value between the first and second data time.
        # On/off marks sit half a sample after the intended data point so ms rounding can't shift them.
        base_t = datetime.combine(day, datetime.min.time())

        def ts(s):
            return (base_t + timedelta(milliseconds=round(s * 1000))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        def row(s, seq, nm, st):
            return (f"{ts(s)},{seq},{1 if seq else ''},,{nm},0,0,,,,{st},"
                    f"{20 if st == 'On' else 0},Spot,,0,0,0,0,")

        t_first = float(out[0].split(",", 1)[0])
        rows = []
        for i, r in enumerate(rr, 1):
            rows.append(row(t_first if i == 1 else r["t0"], i, r["name"], "Off"))
            rows.append(row(r["t_on"] + r["dt"] / 2, "", "", "On"))
            rows.append(row(r["t_off"] + r["dt"] / 2, "", "", "Off"))
        p_log = os.path.join(out_dir, f"{tag}_synthetic_Iolite.csv")
        with open(p_log, "w") as fh:
            fh.write("\n".join([IOLITE_HEADER] + rows) + "\n")

        p_par = os.path.join(out_dir, f"{tag}_PARAM.xlsx")
        write_param(p_par, [r["name"] for r in rr])

        p_ord = os.path.join(out_dir, f"{tag}_run_order.txt")
        with open(p_ord, "w") as fh:
            fh.write("peak\tname\tacquired\trun_start_s\trun_end_s\tlaser_on_s\tlaser_off_s\tsource_file\n")
            for i, r in enumerate(rr, 1):
                fh.write(f"{i}\t{r['name']}\t{r['acq']:%H:%M}\t{r['t0']:.3f}\t{r['t1']:.3f}\t"
                         f"{r['t_on']:.3f}\t{r['t_off']:.3f}\t{r['file']}\n")

        start = t_first + 0.03
        say(f"\n{tag}: {len(rr)} spots -> {os.path.basename(p_comb)}, {os.path.basename(p_log)}, "
            f"{os.path.basename(p_par)}, {os.path.basename(p_ord)}")
        say(f"  Iolite Start time to enter in Ilaps: {start:.2f}")
        durs = sorted(r["t_off"] - r["t_on"] for r in rr)
        typical = durs[len(durs) // 2]
        for i, r in enumerate(rr, 1):
            dur, on_rel = r["t_off"] - r["t_on"], r["t_on"] - r["t0"]
            note = []
            if r["nreg"] > 1:
                note.append(f"{r['nreg']} signal regions, kept the longest")
            if abs(dur - typical) > 8:
                note.append("unusual ablation length")
            say(f"  {i:3d} {r['name']:14s} on at {on_rel:6.1f} s, {dur:5.1f} s long"
                + (f"   <-- check: {'; '.join(note)}" if note else ""))
        results.append(dict(tag=tag, runs=rr, combined=p_comb, iolite=p_log, param=p_par, run_order=p_ord,
                            start_time=start))
    return results


# ---------------------------------------------------------------- window (no arguments)

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, simpledialog

    root = tk.Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(
        title="Select the single-spot runs (one Agilent export per spot)",
        filetypes=[("Agilent exports", "*.txt *.csv"), ("All files", "*")])
    if not files:
        print("make_iolite: no files selected, nothing written.")
        return
    out_dir = os.path.dirname(files[0])
    prefix = simpledialog.askstring(
        "Output name", "Prefix for the output files:", initialvalue=os.path.basename(out_dir).replace(" ", "_"))
    if not prefix:
        print("make_iolite: no output name given, nothing written.")
        return
    lines = []
    try:
        make(collect_files(files, "*"), out_dir, prefix.strip(), say=lines.append, **{
            k: DEFAULTS[k] for k in ("blank_seconds", "sd_multiply", "strip")})
        title = f"Done: files written to {out_dir}"
    except Exception as e:  # show any problem in the window rather than a console
        lines.append(f"\nERROR: {e}")
        title = "Problem"
    with open(os.path.join(out_dir, f"{prefix.strip()}_make_iolite_log.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    win = tk.Toplevel(root)
    win.title("make_iolite")
    tk.Label(win, text=title, anchor="w", font=("TkDefaultFont", 11, "bold")).pack(fill="x", padx=10, pady=(10, 4))
    box = scrolledtext.ScrolledText(win, width=100, height=30, font=("TkFixedFont", 9))
    box.insert("1.0", "\n".join(lines))
    box.configure(state="disabled")
    box.pack(fill="both", expand=True, padx=10)
    tk.Button(win, text="Close", command=root.destroy).pack(pady=8)
    win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="*", help="run files, or folders containing them")
    p.add_argument("--prefix", help="output file prefix (default: name of the first input's folder)")
    p.add_argument("--output-dir", help="where to write (default: the folder of the runs)")
    p.add_argument("--pattern", default=DEFAULTS["pattern"], help="files to read inside folders (default: *.txt)")
    p.add_argument("--strip", action="append", default=None,
                   help="extra text removed from file names to make spot names (USGS- is always removed); repeat for more")
    p.add_argument("--blank-seconds", type=float, default=DEFAULTS["blank_seconds"],
                   help="length of the blank at the start of every run (default 50)")
    p.add_argument("--sd-multiply", type=float, default=DEFAULTS["sd_multiply"],
                   help="signal threshold = blank mean + this many SD (default 10)")
    a = p.parse_args(argv)
    if not a.inputs:
        return gui()
    files = collect_files(a.inputs, a.pattern)
    first_dir = a.inputs[0] if os.path.isdir(a.inputs[0]) else os.path.dirname(os.path.abspath(a.inputs[0]))
    out_dir = a.output_dir or first_dir
    prefix = a.prefix or os.path.basename(os.path.normpath(first_dir)).replace(" ", "_")
    try:
        make(files, out_dir, prefix, a.blank_seconds, a.sd_multiply,
             DEFAULTS["strip"] + (a.strip or []))
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
