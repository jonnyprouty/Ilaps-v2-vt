# SOP: LA-ICP-MS spot data reduction in Ilaps

**Scope:** bulk (spot) analyses from our Agilent ICP-MS, reduced to concentrations (µg/g, ppm) in Ilaps-v2. Imaging and line scans are not covered.
**Applies to:** everyone reducing laser data in the lab.
**Written:** 2026-11-04, tested on the October 2026 Victor sample set (USGS reference materials plus VG samples, all as lithium borate fused beads). Fused-bead section added 2026-11-04. Section 4 updated 2026-11-20 for the Make Iolite log tool.

---

## 1. Which procedure do I follow?

| How the data was collected | Procedure |
|---|---|
| **One file per spot**: each spot was acquired as its own Agilent run (e.g. `20261028-1407-USGS-BCR-2.txt`). No laser log. | **Case A**: combine the runs first (section 4), then process (section 6). |
| **Many spots in one stream**: one long Agilent acquisition covering the whole sequence, plus the laser's Iolite log (`*.Iolite.csv`). | **Case B**: prepare the Iolite and Param files (section 5), then process (section 6). |

Both cases end in the same Ilaps workflow: calibrate on a reference material, correct with an internal standard (XRF or EPMA) or total sum, then export.

**Fused glass beads** (samples and standards fused with lithium borate flux, e.g. XRF beads): also follow section 8. It changes which elements can be reported, which internal standard to use, and how to compare standards.

---

## 2. One-time setup

1. **Python environment.** Ilaps runs in the `ilaps` virtual environment in the Ilaps folder (Python 3.10):
   ```bash
   cd ~/Tools/Ilaps-v2
   source ilaps/bin/activate
   python GUI.py
   ```
2. **Lab version of imgMS.** Ilaps does its calculations with the `imgMS` package. We use the lab fork (`jonnyprouty/imgMS-vt`), which matches the internal standard sheet by name (7.5), keeps the last data row of Agilent files, and works with pandas 2. `ilaps/bin/pip install -r requirements.txt` installs it. To work on imgMS itself, clone it to `~/Tools/imgMS-vt` and install that copy instead (edits then take effect immediately):
   ```bash
   ilaps/bin/pip install --no-deps -e ~/Tools/imgMS-vt
   ```
   Check: `ilaps/bin/python -c "import imgMS; print(imgMS.__file__)"` should point into `imgMS-vt`. With the original imgMS (0.2.12), pandas must be older than 2.0 (`ilaps/bin/pip install "pandas<2"`), or **Report** and **Export stats** crash without showing an error.
3. **Reference materials (`SRM.xlsx`).** Ilaps reads `SRM.xlsx` in the Ilaps folder (not the copy in `test_data/`). Before a new reference material can be used:
   - Add one row per material. Column A is the name, spelled exactly as the peaks will be named (e.g. `BCR-2`, `AGV-2a`, `W-2b`).
   - Element columns (`Si`, `Ca`, `Fe`, …) are in **µg/g (ppm) of the element**, not oxide wt%. Convert oxides with the factors in section 7.4.
   - Leave unknown values **blank, never 0**. A 0 makes that element read 0 in every sample.
   - Back up the file before editing. Close it in Excel/LibreOffice before running Ilaps.

   Currently in `SRM.xlsx`: NIST610, NIST612, NIST614, AGV-2a, BCR-2, BHVO-2, BIR-1a, RGM-2, SBC-1, SDC-1, W-2b.

---

## 3. Data requirements (plan these at the instrument)

- **Gas blank before every spot.** At least about 30 s with the laser off; our method uses about 60 s. Ilaps measures each spot's background from the readings just before and just after it.
- **Calibrant.** At least 2 spots of the reference material you will calibrate on, ideally at the **start, middle and end** of the session.
- **Secondary standards.** At least one other reference material treated as an unknown, to check accuracy (section 9).
- **Same session.** Calibrate samples only against standards from the same day and session. Process each day separately.
- **Names.** Peak names must match exactly. Use the same spelling for repeats of a sample (`VG-A1` three times, not `VG-A1`, `VG A1`, `vg-a1`). Standards must match their `SRM.xlsx` row name.
- **Case A file names:** `YYYYMMDD-HHMM-NAME.txt`, e.g. `20261028-1407-USGS-BCR-2.txt`. The peak name is taken from everything after the date and time, with `USGS-` removed.
- **Keep the Agilent header.** Export with the 3 header lines and the "Printed:" footer intact. Files with the header removed are skipped.
- **One isotope per element** for major elements, if you intend to use total sum correction (section 7.6).

---

## 4. Case A: one file per spot → build combined files

Ilaps calibrates within one loaded file, so single-spot runs must first be joined into one file per day, with an Iolite log that tells Ilaps where each spot is and a Param file. The **Make Iolite log** tool (`tools/make_iolite.py`) makes all three. It needs only Python 3, not the Ilaps environment.

### 4.1 Run Make Iolite log

1. Start it: choose **Make Iolite log** in the application menu, or run
   ```bash
   cd ~/Tools/Ilaps-v2
   python3 tools/make_iolite.py
   ```
2. In the file window, go to the run folder and select the runs (Ctrl+A selects them all; files that are not Agilent runs, and earlier combined files, are skipped). Runs from several days are split into one set per day.
3. Enter the output name (`PROJECT`; the default is the folder name) and click OK.
4. A report window opens (section 4.4). The outputs are written next to the runs; the original files are never modified. If you cancel either window, nothing is written and the terminal says so.

From the command line instead (same result, report printed in the terminal):

```bash
python3 tools/make_iolite.py "/path/to/run folder" --prefix PROJECT
```

Options: `--output-dir DIR` to write elsewhere; `--pattern "*.csv"` if the runs are .csv (default `*.txt`; only used when a folder is given); `--strip TEXT` to remove more text from names (`USGS-` is always removed); `--blank-seconds 50` (how much of each run's start is blank); `--sd-multiply 10` (signal threshold above the blank). Run `python3 tools/make_iolite.py --help` for details.

On another Linux computer: copy `tools/make_iolite.py`, and for the menu entry copy `tools/make_iolite.desktop` to `~/.local/share/applications/` and fix the path in its `Exec=` line.

### 4.2 Outputs (one set per day)

| File | What it is | Used in Ilaps as |
|---|---|---|
| `PROJECT_YYYY-MM-DD_combined.csv` | All runs of that day joined in acquisition order (sorted by the instrument's *Acquired* time, not the file name). Counts are copied unchanged; only the time column is made continuous. | Import Analysis |
| `PROJECT_YYYY-MM-DD_synthetic_Iolite.csv` | A laser log made by the tool, giving each spot's ablation start/end, detected from that run's own blank. **Not a real laser log**: its times refer to the combined file, so always use the two together. | Import Iolite |
| `PROJECT_YYYY-MM-DD_PARAM.xlsx` | Peak names, total-sum factors for our isotopes (including Ca43, which Ilaps' defaults lack), and an empty internal standard sheet (filled in section 7.5). | Import Parameters |
| `PROJECT_YYYY-MM-DD_run_order.txt` | Table of peak number, name, source file and ablation window. | Your reference for QC |
| `PROJECT_make_iolite_log.txt` | The report (section 4.4), saved when the tool is run with its windows (menu or no arguments). | Your record |

### 4.3 Internal standard

The Param file is ready for total-sum correction. For internal standard correction, fill its internal standard sheet once the XRF or EPMA data are available (section 7.5); this step needs the Ilaps environment.

`ilaps/bin/python tools/ilaps_prep.py combine "/path/to/run folder" --prefix PROJECT` does the same as the tool on a whole folder, from the Ilaps environment.

### 4.4 Check the tool's report

The report lists every run with its ablation start and length, and the **Iolite Start time** to enter in Ilaps (normally `0.60`). Some runs are marked `<-- check`:

- **"2 signal regions, kept the longest"**: there was a separate short signal (a spike or stray particle) besides the ablation. Open the run and confirm the kept window is the ablation (in Oct 2026, a 1 s spike 20 s after the ablation in a VG-A3 run).
- **"unusual ablation length"**: the spot was ablated noticeably longer or shorter than the rest. Normal if intended (e.g. a longer acquisition); otherwise check the run.

Skipped files are listed at the top with the reason. A run is skipped if it has no Agilent header, no signal above its blank, or an acquisition date the tool cannot read (it reads `Oct 28 2026 2:07 PM` and `10/28/2026 2:07:00 PM`; day-first dates such as `28/10/2026` are refused rather than guessed). All runs must have the same isotope list; split different methods into separate selections.

Then continue with section 6, using **Iolite** selection with the Start time from the report.

> Why not threshold selection? Ilaps' Threshold method computes one cut-off from the first blank of the file. On a full day this splits spots into fragments (we saw 36 "peaks" from 5 spots). The synthetic Iolite log avoids that.

---

## 5. Case B: many spots in one stream (real Iolite log)

### 5.1 Files needed

- The Agilent export of the whole acquisition (`.csv`, header intact).
- The laser's Iolite log for the same sequence (`.Iolite.csv`). Each spot's **Comment** is its peak name, so name spots in the laser software exactly as in section 3.

### 5.2 Param file

A Param file is needed for internal standard correction and for correct total-sum factors (Ilaps' built-in defaults include Ca44 but not Ca43, so Ca would be dropped from the total). Create one from the Iolite log:

```bash
ilaps/bin/python tools/ilaps_prep.py internal-std --param "/path/RUN_PARAM.xlsx" --iolite "/path/RUN.Iolite.csv"
```

This writes names, total-sum factors and an empty internal standard sheet. To fill in XRF or EPMA internal standards at the same time, add `--calibrant`, `--epma` and `--is` (section 7).

### 5.3 Start time

On the Iolite tab in Ilaps, **Start time** tells Ilaps where the Iolite log starts on the ICP-MS time axis. Set it to the time (s) of the **first reading where the first spot's signal rises** above the blank:

1. Import the data (section 6.1) and look at the plot on the *Data analysis* screen. Zoom (magnifier icon) onto the first peak.
2. Read the time of the first point clearly above background. Enter that value.
3. After **Select**, check that the start and end lines sit on the edges of the peaks across the **whole** run, including the last spots. If every window is shifted, adjust Start time by one reading and select again.

Example (`test_data/sample_data_Agilent.csv`): first rise at 126.16 s gives windows that sit on the peaks; 120 s shifts every window early by one reading.

---

## 6. Processing in Ilaps (both cases)

The toolbar at the top switches screens: **Home** (import), **Data analysis** (Ctrl+D), **Bulk analysis** (Ctrl+A), **Show data**, **Show error log** (Ctrl+E).

> If a button seems to do nothing, open **Show error log**: Ilaps reports most errors there and not in a pop-up.

### 6.1 Import (Home screen)

| Field | Case A | Case B |
|---|---|---|
| Import Analysis | `..._combined.csv` | the Agilent `.csv` |
| File type | `csv` | `csv` |
| Instrument type | `Agilent` | `Agilent` |
| Import Parameters | `..._PARAM.xlsx` | your `RUN_PARAM.xlsx` |
| Import Iolite | `..._synthetic_Iolite.csv` | the laser's `.Iolite.csv` |

Click **Import**. Ilaps switches to *Data analysis* and plots the signal. Use a Param file made by the tools (4.2 or 5.2). A Param file missing any of its three sheets (`names`, `internal standard`, `total sum`) crashes the import.

### 6.2 Peak selection (Data analysis screen)

1. Choose the **Iolite** tab.
2. **Start time:** Case A: the value in the tool's report (`0.60`). Case B: see 5.3.
3. Leave **Set names from iolite** unchecked; names then come from the Param file. (Checking it uses the Iolite comments instead; for Case A both are identical.)
4. Leave **Skip background** and **Skip peak** empty. A non-zero *Skip peak* halved our averages in testing: the peak edges get treated as background.
5. Click **Select**. Check the plot: one start/end pair per spot, on the edges of each peak. Tick **log axes** to see the blanks.

### 6.3 Averaging and calibration (Bulk analysis screen)

Set the **Settings** box exactly like this:

| Setting | Use | Why |
|---|---|---|
| Detection limit | **`all`** | This box also sets how background is subtracted. `all` uses each spot's own neighbouring blank. The default `beginning` subtracts the first blank of the file from every spot. |
| Despiking | `True` | Removes single-reading spikes. (Choosing `False` currently has no effect: Ilaps despikes either way.) |
| Method | **`intensity`** | Mean count rate. `integral` sums over time, so spots ablated longer read higher. |
| Peak ablation time | leave blank | Only used with `integral`. |
| Standard | your calibrant, e.g. `BCR-2` | Must be one of the peak names and a row in `SRM.xlsx`. |
| Drift Correction | **unchecked**, unless the calibrant was run at the start, middle and end | Ilaps fits a line through the calibrant spots by position and extends it to every spot. With only back-to-back calibrant spots, this extrapolates over the whole day; in our test, late samples came out 30–50% low and 111 values went negative. |

Then click, in order:

1. **Average**: background-corrected mean counts per spot (*Average* tab).
2. **Quantification**: concentrations calibrated on the standard (*Quantified* tab). Calibrant spots are removed from this table. These values are **not yet corrected** for differences in ablation yield between materials, so they are typically biased by 10–30%. Always apply a correction (section 7).

### 6.4 Correction

- **With XRF or EPMA data (preferred):** click **Internal Std Correction** (section 7).
- **Without:** click **TS settings**, check the settings (section 7.6), then **Total Sum Correction**.

You can run both and export both for comparison.

### 6.5 Export

Do these in this order. **Report** changes the tables in place, so run *Export stats* before it.

1. **Export**: one Excel workbook with sheets:
   - `raw`: the counts
   - `average`: mean background-corrected counts per spot (cps)
   - `quantified`: calibrated, uncorrected ppm
   - one sheet per internal standard isotope, e.g. `Si28`, `Ca43`: IS-corrected ppm
   - `corrected_TS`: total-sum-corrected ppm

   Keep this file as the full record of the reduction.
2. **Export stats**: choose *Quantified*, *Corrected – Total sum* or *Corrected – Internal standard*, click **Apply**, then pick a file name. The workbook has:
   - `Outliers`: all spots; for samples with 3 or more spots, outlier spots are in red.
   - `Stats`: per sample: `mean`, `2*std`, `max`, `min`, `median`.

   The internal-standard option writes one file per IS isotope, named `yourfile_Si28.xlsx` etc.
3. **Report**: values below the detection limit become `< LoD`, the rest are rounded, and a detection-limit row is added to each table.
4. **Export** again to a new file name. This is the version for tables and reports.

> `< LoD` in *Export stats* also appears for elements that have **no value for the calibrant in `SRM.xlsx`**. These are not calibrated at all and are not below detection. Example: Be with BCR-2 as calibrant.

---

## 7. Internal standard correction (EPMA or XRF data)

### 7.1 What it does

Spots ablate different amounts of material, and samples ablate differently from the calibrant. An internal standard is an element whose concentration in each sample you already know (from EPMA or XRF). Ilaps scales every element in a spot so that the internal standard element matches its known value:

`corrected = quantified × (known IS concentration ÷ quantified IS concentration)`

### 7.2 Choosing the internal standard

- An element **measured by EPMA on the same phase or glass** that the laser spot sampled, ideally at the same spot location.
- High concentration, homogeneous, and with a precise EPMA value: usually **Si** (SiO2) or **Ca** (CaO); Al or Mg can also work.
- **Measured by ICP-MS** in your method (we measure Si28 and Ca43) and **present in `SRM.xlsx` for your calibrant**. The tool refuses a calibrant without a value for the IS element.
- Using two (e.g. Si28 and Ca43) gives two independent results; agreement between them is a useful check.

### 7.3 Prepare the EPMA or XRF table

One `.csv` or `.xlsx` file (the same layout works for EPMA and XRF results):

- **First column:** sample name, spelled exactly like the peak names (`VG-A1`).
- **Other columns:** oxides in **wt%**, with these headers: `SiO2`, `CaO`, `Al2O3`, `MgO`, `TiO2`, `FeO`, `Fe2O3`, `Na2O`, `K2O`, `MnO`, `P2O5`, `Cr2O3`. Common variants are understood too: `Fe2O3T`, `Fe2O3(T)`, `FeO*`, `SiO2 (wt%)`. Other columns (e.g. `LOI`, `Total`) are ignored.
- Several rows with the same name (repeat EPMA points or XRF replicates) are **averaged** by the tool.
- Reference materials do not need EPMA rows: their values come from `SRM.xlsx`.

Example:

| Sample | SiO2 | CaO |
|---|---|---|
| VG-A1 | 52.31 | 9.12 |
| VG-A1 | 52.87 | 9.05 |
| VG-A2 | 61.40 | 4.33 |

### 7.4 Oxide → element conversion

The tool converts automatically. For reference, element ppm = oxide wt% × factor:

| Oxide | Element | Factor |
|---|---|---|
| SiO2 | Si | 4674 |
| CaO | Ca | 7147 |
| Al2O3 | Al | 5293 |
| MgO | Mg | 6030 |
| TiO2 | Ti | 5995 |
| FeO | Fe | 7773 |
| Fe2O3 | Fe | 6994 |
| Na2O | Na | 7419 |
| K2O | K | 8301 |
| MnO | Mn | 7745 |
| P2O5 | P | 4364 |

Example: 52.6 wt% SiO2 → 52.6 × 4674 = 245,900 ppm Si.

### 7.5 Write the internal standard sheet

```bash
ilaps/bin/python tools/ilaps_prep.py internal-std \
    --param "/path/PROJECT_2026-10-28_PARAM.xlsx" \
    --calibrant BCR-2 \
    --epma "/path/epma.xlsx" \
    --is Si28=SiO2 --is Ca43=CaO
```

- `--calibrant` must be the same standard you will pick in Ilaps.
- `--epma` and `--xrf` are the same option; use whichever describes your table.
- `--is ISOTOPE=OXIDE`: the isotope exactly as in the data's column names (`Si28`, not `Si`), and the EPMA oxide it comes from.
- The tool stops and lists any peak that has no EPMA value and no `SRM.xlsx` value. Fix the EPMA table (usually a spelling difference) and rerun.
- Rerunning replaces the internal standard sheet; names and total-sum sheets are kept.
- Ilaps reads the Param file at import: after updating it, **import again** in Ilaps.

**How Ilaps matches the sheet to the spots** (lab version of Ilaps, with our imgMS fork): the tool writes one row per peak in run order, with every calibrant peak left out, and Ilaps uses those rows in order. A sheet typed by hand can instead have **one row per sample name**, in any order; Ilaps then matches rows by name, and extra rows (such as the calibrant) are ignored:

| | Si28 | Ca43 |
|---|---|---|
| SDC-1 | 307573.4 | 10005.7 |
| VG-B1 | 247741.5 | 65752.0 |
| … | | |

(header row = isotopes; values in element ppm; secondary standards use their `SRM.xlsx` values.)

Different values for repeat spots of one sample (e.g. EPMA of each spot) only work in the one-row-per-peak, run-order form. If the sheet fits neither form (a sample missing, a blank value, rows out of order), **Internal Std Correction** stops with a message saying what does not match, rather than applying values to the wrong spots. The original Ilaps (upstream imgMS 0.2.12) uses rows by position only and gives no warning; with it, use the tool.

### 7.6 Total sum correction (when there is no EPMA or XRF)

Assumes the major-element oxides of each spot add up to 100%. Good for anhydrous silicates and glasses; poor for hydrous, carbonate-, sulfide- or halogen-rich material. For fused beads, see 8.3 and 8.4 first.

In **TS settings**:

- **Total sum [ppm]:** `1000000` for 100%. If samples contain volatiles not measured (H2O, CO2), enter 100% minus their amount (e.g. `980000` for 2 wt% LOI).
- **Isotope checkboxes:** a ticked isotope is **left out** of the sum. If you measured several isotopes of one major element (e.g. Si28 and Si29), tick all but one, or that element is counted twice.
- **keep oxide form:** reports oxide values instead of element ppm.

Iron is counted as Fe2O3, manganese as MnO.

### 7.7 Check the correction

- In the internal-standard sheet of the export, the IS element in each sample must equal its EPMA value (e.g. Si28 for VG-B1 = 247,741.5 ppm). If not, the sheet holds the wrong value for that sample.
- Secondary standards should agree with `SRM.xlsx` (section 9; for fused beads see 8.5).

---

## 8. Fused glass beads (lithium borate flux)

Our XRF beads are samples (and standards) fused with lithium borate flux and a lithium bromide release agent, then polished. A spot on a bead samples **mostly flux**: the rock is diluted, typically 5–10× depending on the sample-to-flux ratio. This section covers what that changes. Everything in sections 4–7 still applies.

### 8.1 What changes on a bead

| Effect | Consequence |
|---|---|
| Flux is lithium borate | **Li comes from the flux**, not the rock: its signal is about the same in every bead (seen in Oct 2026: 330,000–1,035,000 cps in all materials, whatever their reference Li). **Never report Li.** B is also flux-derived (not in our method). |
| Lithium bromide release agent | Br is mostly lost during fusion; not reportable. |
| Rock diluted 5–10× by flux | Count rates are 5–10× lower than on the rock. In Oct 2026 many trace elements gave under 10 cps (most heavy REE, Hf, Ta, W, U, Rb, Cs). Expect poor precision and high detection limits for low-level trace elements. |
| Fusion at about 1000–1100 °C | Volatile elements can be partly lost: As, Cu, Zn, Sn, Cs, Pb, S, halogens. They may read low against powder reference values. |
| Flux impurities | Trace amounts of Na and other elements in the flux add to every bead. Matters most for elements that are low in the rock (Oct 2026: Na in SBC-1, only 0.15% Na2O, read 1.5× high). |
| Volatiles (H2O, CO2, organic C) driven off | The bead holds the rock's **volatile-free** (ignited) composition. Reference values in `SRM.xlsx` are for the **as-received** powder. See 8.5. |
| All beads are mostly the same flux glass | Matrix differences between rock types largely disappear, so the choice of calibrant matters less than for natural glasses. Choose it for accuracy, count rate and element coverage. |

### 8.2 Elements to report

- **Do not report:** Li, B, Br.
- **Treat with caution:** volatile elements (As, Cu, Zn, Sn, Cs, Pb); any element with fewer than about 20 cps above background in your samples (check the `average` sheet of the export); Ca43 in Al-rich, Ca-poor samples (²⁷Al¹⁶O⁺ overlaps mass 43; in Oct 2026 Ca read 1.40× in SDC-1 and 1.17× in SBC-1). Measure Ca44 in future methods.
- **Reliable** (Oct 2026, BCR-2 calibrant, Si internal standard, recovery of SDC-1, SBC-1 and AGV-2a):
  - within 5% in all three: Mg, Al, Si, K, Ti, Mn, Sr, Ba, Rb (Rb gave under 10 cps in the VG samples, so it is reliable in standards only);
  - within 10% in all three: Fe, Co, V, Ce, Zr, Th, U, Yb;
  - within about 12%: La, Nd, Y;
  - Na within 2%, except in low-Na SBC-1 (flux impurity, 8.1).

### 8.3 Choose the internal standard source

The flux dilution cancels in the internal standard correction, as long as the internal standard element is diluted the same way as the others (it is, in a homogeneous bead). What the source of the internal standard values decides is **what the results mean**:

| Internal standard values from | Results come out as | Notes |
|---|---|---|
| **XRF of the same bead (recommended)** | Rock concentrations, on the same basis as the XRF report | Use the XRF table directly with `--xrf` (7.5). Check whether your XRF report is volatile-free (ignited) or as-received, and state that basis with the results. |
| **EPMA on the bead glass** | Concentrations **in the bead** (diluted) | Convert the EPMA values to rock values **before** making the table (8.4), so every result is a rock value. |
| **Total sum** (no XRF/EPMA) | Rock concentrations, **volatile-free** basis | All majors must be measured (we measure Si, Ti, Al, Fe, Mn, Mg, Ca, Na, K, P). In **TS settings**, tick **Li7** so flux Li is left out of the sum. |

Use **Si28** as the internal standard on beads. Ca43 is affected by AlO⁺ in Al-rich samples (8.2).

### 8.4 Converting bead values to rock values (EPMA on beads only)

Multiply each EPMA oxide value by the dilution factor before building the table:

`rock wt% = bead wt% × DF`, with `DF = bead mass ÷ sample mass`

- Use the masses from the fusion record for **that** bead.
- **Bead mass:** weigh the finished bead. If it was not weighed, use sample mass after ignition + flux mass. Do not count the LiBr release agent; it mostly volatilizes.
- **Sample mass:** the ignited mass gives volatile-free rock values; the as-received mass gives as-received values. Use the same basis for every sample in a project.
- Example: 1.000 g ignited sample + 9.000 g flux, bead 10.00 g → DF = 10.0. EPMA SiO2 5.26 wt% in the bead → 52.6 wt% SiO2 in the rock.
- An EPMA total far below 100% on a bead is expected: Li and B are not measured by EPMA.

### 8.5 Checking standards on the right basis

The tool fills the standards' internal standard values from `SRM.xlsx` (as-received powder), so **IS-corrected standards come out as-received** and compare directly with `SRM.xlsx`.

**Total-sum-corrected standards come out volatile-free.** Before comparing, convert the reference value:

`volatile-free reference = SRM.xlsx value × 100 ÷ (sum of the standard's major oxides, wt%)`

Oct 2026 example: SBC-1 (a shale) has major oxides summing to about 89%. Its total-sum result read 1.10× the `SRM.xlsx` values, as expected for a factor of 100 ÷ 89 = 1.12. With the Si internal standard it read 0.97×. AGV-2a and BCR-2 (sums 98–100%) agree either way.

### 8.6 Session design for beads

- **Fuse standards and samples the same way:** same flux, ratio and fusion program.
- **Run a flux blank bead** (flux and release agent only, fused like the samples) at least once per session, and name it e.g. `FLUX-BLANK`. Compare its counts with the samples' in the `average` sheet. Treat any element where the flux blank reaches more than about 10% of a sample's counts as unreliable for that sample. The flux blank has no Si, so it cannot be IS- or total-sum-corrected; it is only for this comparison. (The tool needs an internal standard value for every peak, so add a `FLUX-BLANK` row with SiO2 `0.001` to the table; ignore its corrected results.)
- **Clean the surface:** run a few pre-ablation (cleaning) pulses over each spot to remove polishing residue, and avoid bubbles, cracks, unmelted grains and the bead edge.
- **Standards:** spread calibrant spots through the session (start, middle, end); include a basaltic check standard (BHVO-2 is in `SRM.xlsx`) and one more secondary standard.

---

## 9. Quality control

For each session, before using sample results:

1. **Peak count:** number of peaks on the plot = number of names. If they differ, *Average* fails and the error appears under *Show error log*.
2. **Windows:** start/end lines sit on every peak (spot-check the first, a middle and the last spots).
3. **Secondary standards:** compare the mean of each secondary standard to `SRM.xlsx`. Suggested lab criteria (adjust as the lab decides): major elements within ±5%, most trace elements within ±10%. Report the recoveries with the data.
   Reference result (Oct 28 2026, BCR-2 calibrant, Si28 internal standard): AGV-2a median recovery 1.01; Si 1.00, Ca 1.03, Fe 1.00, Sr 1.03, La 1.01.
4. **Repeats:** use the `2*std` rows in the *Export stats* `Stats` sheet; investigate spots shown in red in `Outliers`.
5. **Keep for the record:** the raw runs, the combined/Param/Iolite files, the EPMA table, both exports, and a note of the settings used (calibrant, IS isotope, TS settings).

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **Select** does nothing | Empty Start time (Iolite) or empty boxes (Threshold) | Fill them in; see 6.2 |
| Import does nothing / app shows no data | Param file missing a sheet, or wrong Instrument type | Use the tool-made Param file; Instrument `Agilent` |
| Make Iolite log writes nothing | A window was cancelled, or every file was skipped | Check the terminal or report for the reason (4.4) |
| *Average* does nothing; error log shows "Length mismatch" | Selection found more or fewer peaks than there are names | Case A: use Iolite selection with the synthetic log. Case B: check Start time and the Iolite log covers the same run |
| "X not in peak names" | Standard dropdown name does not match any peak | Make names match `SRM.xlsx` exactly (case, hyphens) |
| Internal Std Correction does nothing | Internal standard sheet empty | Run the tool (7.5) and re-import |
| Internal Std Correction shows "Internal standard sheet does not match the peaks" | A sample has no row, a value is blank, or per-spot rows are out of run order | Follow the message; regenerate with the tool (7.5) and re-import |
| IS-corrected IS element ≠ EPMA value | Wrong value in the internal standard sheet (or rows misaligned, with the original Ilaps) | Regenerate with the tool (7.5) |
| Report / Export stats do nothing | Original imgMS with pandas 2.x | Install the lab imgMS (section 2), or `ilaps/bin/pip install "pandas<2"` |
| Export stats fails after Report | Report replaced numbers with `< LoD` text | Re-import, process again, run Export stats before Report |
| Element shows `< LoD` everywhere | Calibrant has no value for that element in `SRM.xlsx` | Add the value, or calibrate on a standard that has it |
| Values negative or drifting through the day | Drift Correction checked with poor calibrant spacing | Uncheck it (6.3) |
| Results ~10–30% off for all elements | No correction applied | Apply IS or total sum correction |
| Li about the same in every sample and standard | Fused beads: Li is from the flux | Don't report Li (8.1) |
| Volatile-rich standard (e.g. SBC-1) ~10% high after total sum | Total sum gives volatile-free values; `SRM.xlsx` is as-received | Compare on the same basis (8.5) |
| `internal-std` tool: "no SiO2 … value" for an EPMA/XRF sample | Name in the table differs from the peak name, or header not recognised | Match spelling exactly; use oxide headers as in 7.3 |

---

## Appendix A: Worked example (Victor samples, 28 Oct 2026)

```bash
cd ~/Tools/Ilaps-v2
python3 tools/make_iolite.py "/run/media/jprouty/VT EPMA/Victor Samples" --prefix Victor   # or use the menu
# when XRF (or EPMA) data is available; use --epma for EPMA tables:
ilaps/bin/python tools/ilaps_prep.py internal-std \
    --param "/run/media/jprouty/VT EPMA/Victor Samples/Victor_2026-10-28_PARAM.xlsx" \
    --calibrant BCR-2 --xrf "/path/to/Victor_XRF.xlsx" --is Si28=SiO2
python GUI.py
```

- Import: `Victor_2026-10-28_combined.csv`, csv, Agilent, `Victor_2026-10-28_PARAM.xlsx`, `Victor_2026-10-28_synthetic_Iolite.csv`.
- Data analysis: Iolite tab, Start time `0.60`, Select. Expect 54 peaks.
- Bulk analysis: Detection limit `all`, Despiking `True`, Method `intensity`, Standard `BCR-2`, Drift Correction off. Then Average, Quantification, then Internal Std Correction (or TS settings, then Total Sum Correction).
- These are fused beads: never report Li; for total sum, tick Li7 in TS settings (section 8).
- Export, then Export stats, then Report, then Export to a second file.
- Oct 27 data: same steps with the `2026-10-27` files and `W-2b` as calibrant (no secondary standard that day).

## Appendix B: Files and tools

- `tools/make_iolite.py` (menu: **Make Iolite log**): combines single-spot runs and writes the synthetic Iolite log and Param file (section 4). Python 3 standard library only, so it can be copied to any computer. Menu launcher: `tools/make_iolite.desktop`.
- `tools/ilaps_prep.py`: `internal-std` (sections 5.2, 7.5, 8.3), and `combine` (same as `make_iolite.py` on a folder, section 4.3). Run `ilaps/bin/python tools/ilaps_prep.py internal-std --help` for all options.
- `SRM.xlsx`: reference material values (section 2).
- `default_sum_koef.xlsx`: Ilaps' built-in total-sum factors, used only when no Param file is loaded.
- `log.txt`: Ilaps' processing log (settings used, warnings).
