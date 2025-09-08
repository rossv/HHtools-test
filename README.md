# H-H-tools

Utilities for hydrology and hydraulics modeling support. Each tool is
available from the command line and as a PyQt GUI so they can be bundled
as standalone executables.

## Installation

```bash
pip install .
```

## Command line tools

All command line interfaces show default values in their `--help` text and
support `-v/--verbose` to increase logging or `-q/--quiet` to suppress
informational messages.

### Extract Timeseries

Extract time-series data from SWMM `.out` files:

```bash
extract-timeseries example.out --ids ALL --out-format tsf
```

To discover element IDs without extracting data use `--list-ids`:

```bash
extract-timeseries example.out --list-ids node
```

Multiple types may be listed with commas.

Specify a custom directory for the extracted files with `--output-dir`.
Use `--out-format dat` or `--out-format csv` to write DAT or CSV files.

Use `--pptx results.pptx` to create a PowerPoint presentation populated
with plots for each extracted series.

When working with multiple `.out` files that cover different time periods,
use `--combine across` to merge matching element IDs into a single
chronologically ordered series.

Run `extract-timeseries --help` for the full list of options.

### Compare Out Files

Generate a report highlighting differences between two SWMM `.out` files:

```bash
compare-outfiles run1.out run2.out --type node --ids ALL --params Flow_rate
```

Use `--detailed-table details.csv` to also write a CSV with the full time-series
values and their differences:

```bash
compare-outfiles run1.out run2.out --type node --ids ALL --params Flow_rate \
    --detailed-table differences.csv
```

Create PNG plots for each compared series by specifying a directory:

```bash
compare-outfiles run1.out run2.out --type node --ids ALL --params Flow_rate \
    --plot-dir plots/
```

The plots will be named using the element ID and parameter (e.g.,
`plots/N1_Flow_rate.png`).

Run `compare-outfiles --help` for available options.

### Review Flow Data

Inspect and clean flow, depth, and velocity time series:

```bash
review-flow-data measurements.csv --time-col Date --flow-col Flow --output cleaned.tsf
```

Run `review-flow-data --help` for more options.

In the GUI, choosing an input file automatically fills drop-down lists with
the file's column headers for quick selection.

### Design Storm Generator

Create synthetic design storms from manual inputs or NOAA Atlas 14 data:

```bash
design-storm --duration 6 --depth 2.5 --time-step 5 --distribution scs_type_ii --out-csv storm.csv --out-dat storm.dat
```

Run `design-storm --help` for the available options.
Use `--out-dat` to create a PCSWMM-compatible `.dat` rain gage file.

To enable automatic depth lookup from NOAA's Atlas 14 service install the
optional dependency set:

```bash
pip install hh-tools[noaa]
```

### Calibrate Model

Optimise SWMM parameters to match observed data:

```bash
calibrate-model base.inp --bounds bounds.json --observed flow.csv --metric nse --output params.json
```

The bounds file maps parameter names to low/high values.  The observed data
file should contain a numeric column used for comparison.  Results are written
as JSON and a calibrated INP can optionally be produced with `--calibrated-inp`.

### Summarize Out Files

Summarize SWMM `.out` files with basic statistics:

```bash
summarize-outfiles run1.out run2.out --type node --ids ALL --params Flow_rate --output summary_report.csv
```

### Download Rainfall

Fetch rainfall data from NOAA's API and write it in multiple formats:

```bash
download-rainfall --station 012345 --start 2020-01-01 --end 2020-01-31 --api-key TOKEN --output rain.csv
```

### Download Streamflow

Retrieve streamflow series from the USGS NWIS service:

```bash
download-streamflow --station 01234567 --start 2020-01-01 --end 2020-01-31 --output flow.csv
```

### Resample Timeseries

Change the timestep of a time series and export the results:

```bash
resample-timeseries data.csv --freq 30min --format tsf --output resampled.tsf
```

Use `--plot` to preview the original and resampled series.

### Batch Runner

Run multiple SWMM scenarios described in a config file or list of `.inp` files:

```bash
batch-runner config.yml
```

### Validate INP

Check SWMM input files for structural and cross-reference issues:

```bash
validate-inp model.inp
```

### Sensitivity Analyzer

Sweep parameter ranges and compute metrics for each SWMM run:

```bash
sensitivity-analyzer base.inp --params ranges.json --metrics peak_flow --output results.csv
```

### Compare Hydrographs

Compare modeled results against observed data with overlay plots:

```bash
compare-hydrographs model.out observed.csv J1 plot.png
```

### Event Extractor

Identify rainfall or flow events that exceed a threshold for a minimum duration:

```bash
event-extractor data.csv --column Rain --threshold 0.1 --min-duration 30
```

### INP Diff

Report differences between two SWMM input files:

```bash
inp-diff before.inp after.inp --output diff.csv
```

### Flow Decomposition

Decompose sanitary sewer flow into groundwater infiltration (GWI), base
wastewater flow (BWWF) and wet-weather flow (WWF):

```bash
flow-decomp --flow flow.csv --rain rain.csv --out results/
```

The command writes a CSV timeseries and a JSON file with derived patterns and
RTK parameters when rainfall is supplied.
For an interactive interface with live plots use `flow-decomp-gui`.

## GUI tools

Each command line tool has a corresponding PyQt5 GUI using a dark theme.
Launch a tool directly or start the master launcher:

- `hh-tools-launcher` — master window to pick a tool (`hh-tools-launcher`)
- `extract-timeseries-gui` — GUI for time-series extraction (`extract-timeseries-gui`)
- `compare-outfiles-gui` — compare `.out` files (`compare-outfiles-gui`)
- `review-flow-data-gui` — review flow data (`review-flow-data-gui`)
- `design-storm-gui` — generate design storms (`design-storm-gui`)
- `summarize-outfiles-gui` — summarize `.out` files (`summarize-outfiles-gui`)
- `download-rainfall-gui` — fetch rainfall data (`download-rainfall-gui`)
- `download-streamflow-gui` — download streamflow data (`download-streamflow-gui`)
- `batch-runner-gui` — run multiple scenarios (`batch-runner-gui`)
- `validate-inp-gui` — validate INP files (`validate-inp-gui`)
- `sensitivity-analyzer-gui` — parameter sweeps (`sensitivity-analyzer-gui`)
- `compare-hydrographs-gui` — compare modeled and observed hydrographs (`compare-hydrographs-gui`)
- `event-extractor-gui` — extract rainfall or flow events (`event-extractor-gui`)
- `inp-diff-gui` — diff INP files (`inp-diff-gui`)
- `calibrate-model-gui` — calibrate parameters (`calibrate-model-gui`)
- `plot-digitizer-gui` — digitize points from plot images (`plot-digitizer-gui`)
- `flow-decomp-gui` — decompose sanitary flow (`flow-decomp-gui`)

To view plots or tables in the `compare-outfiles-gui`, run a comparison and
use the **Export** menu to save the current table or plot for review.

## Packaging to an executable

PyInstaller can create distributable executables. Example for the
extractor GUI:

```bash
pyinstaller --onefile -w -n extract-timeseries-gui \
    src/hh_tools/gui/extract_timeseries_gui.py
```

Use the generated binary in the `dist/` directory and repeat for other
GUIs or for `hh_tools/gui/master_launcher.py` to bundle the launcher.

## Repository layout

```
src/hh_tools/
    extract_timeseries.py       # Core CLI implementation
    compare_outfiles.py         # Compare two SWMM output files
    design_storm.py             # Generate rainfall design storms
    review_flow_data.py         # Inspect and clean flow data
    gui/
        extract_timeseries_gui.py  # PyQt GUI wrapper
        compare_outfiles_gui.py    # GUI for compare-outfiles
        design_storm_gui.py        # GUI for design storms
        review_flow_data_gui.py    # GUI for flow data review
        plot_digitizer_gui.py      # GUI for digitizing plot images
        master_launcher.py         # GUI to launch tools
```

Add new tools under `hh_tools/` and expose them in `pyproject.toml`.
Update `master_launcher.py` with buttons for any new GUIs.