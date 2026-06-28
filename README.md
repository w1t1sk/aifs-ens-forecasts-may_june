# AIFS-ENS 40-Year May–June Hindcast Library

This repository contains the full pipeline used to generate a 40-year (1986–2025) ensemble hindcast library for the May–June season using the **ECMWF AIFS-ENS** machine-learning weather prediction model (`ecmwf/aifs-ens-1.0`).

For each day from 1 March to 30 June across all 40 years, a 30-member ensemble forecast was produced at 6-hourly intervals out to 8 days (192 h) lead time, initialised from ERA5 reanalysis data on the N320 Gaussian grid (~25 km).  Outputs are archived as compressed Zarr datasets on a MinIO object store.

---

## Repository structure

```
aifs-ens-forecasts-may_june/
├── environment/
│   ├── aifs-crps-ens.def          # Apptainer definition — builds the inference container
│   └── environment.yml            # Conda environment for zarr conversion + analysis
├── scripts/
│   ├── 0_quickstart.py            # Minimal single-run demo (verify the container works)
│   ├── 1_download_ic.py           # Step 1: Download ERA5 initial conditions via CDS API
│   ├── 2_batch_inference.py       # Step 2: Run AIFS-ENS ensemble; output NetCDF
│   ├── 3_extract_surface_inputs.py# Step 3: Extract surface fields from IC pickles
│   ├── 4_nc_to_zarr.py            # Step 4: Convert forecast NetCDFs → Zarr on MinIO
│   ├── 5_surface_to_zarr.py       # Step 5: Convert surface-input NetCDFs → Zarr on MinIO
│   ├── 6_grid_to_zarr.py          # Step 6: Upload the model grid to MinIO (run once)
│   └── helper.py                  # Utility: load forecast/surface data from MinIO
├── slurm/
│   └── submit_job.sh              # Slurm submission wrapper for 2_batch_inference.py
├── notebooks/
│   └── zarr_conversion_demo.ipynb # Interactive demo of the NetCDF → Zarr conversion
├── .env.example                   # Template for MinIO credentials
└── .gitignore
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **ECMWF CDS API key** | Register at https://cds.climate.copernicus.eu and place your key in `~/.cdsapirc` |
| **Apptainer ≥ 1.1** | Required to build and run the inference container |
| **CUDA GPU** | Required for inference (tested on a single A100/H100) |
| **MinIO** (or any S3-compatible store) | For Zarr archive storage |
| **Conda / Mamba** | For the analysis environment |

---

## Step 0 — Build the Apptainer container

The model requires specific versions of `anemoi-inference`, `anemoi-models`, and
`flash-attention` that are best installed inside a container.  Build once:

```bash
# Build from the local Docker daemon image named "aifs:latest"
# (pull from ECMWF or build your own base image first)
apptainer build aifs-crps-ens.sif environment/aifs-crps-ens.def
```

> **What the container provides:** PyTorch 2.5.0, `anemoi-inference==0.6.0`,
> `anemoi-models==0.6.0`, FlashAttention (compiled from source),
> `cartopy`, `matplotlib`.

Verify the container works before running large batches:

```bash
# Run a 12-hour test forecast from a pre-downloaded IC pickle
apptainer exec --nv aifs-crps-ens.sif \
    python3 scripts/0_quickstart.py path/to/aifs-init-hres-YYYYMMDD_0000.pkl
```

---

## Step 1 — Set up the analysis environment

```bash
conda env create -f environment/environment.yml
conda activate climt
```

This environment is used for the zarr-conversion scripts (steps 4–6) and for
loading data with `helper.py`.  Inference (step 2) runs inside the Apptainer
container, not this conda environment.

---

## Step 2 — Configure MinIO credentials

```bash
cp .env.example .env
# Edit .env with your MinIO endpoint, access key, and secret key
source .env
```

The environment variables `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, and
`MINIO_SECRET_KEY` are read by scripts 4–6 and by `helper.py`.

Expected bucket structure inside MinIO (`fcst-lib` bucket):

```
fcst-lib/
├── forecasts/{year}/fcst_t2m_30mem_192h_{date}.nc   ← written by step 2
├── surface_inputs/{year}/sfc_input_{date}.nc         ← written by step 3
├── grid/master_grid_n320.nc                          ← static grid file
├── zarr/{year}/{date}.zarr                           ← written by step 4
├── zarr/surface_inputs/{year}/{date}.zarr            ← written by step 5
└── zarr/grid/grid_320.zarr                           ← written by step 6 (once)
```

---

## Step 3 — Download ERA5 initial conditions

```bash
# Download March–June for a single year (runs on CPU, outside the container)
python scripts/1_download_ic.py --year 2009

# Custom date range
python scripts/1_download_ic.py --year 2009 --start-month 5 --end-month 6

# Custom data directory
python scripts/1_download_ic.py --year 2009 --data-dir /scratch/mydata
```

Each daily IC is saved as `<data-dir>/initial_conditions/<YEAR>/aifs-init-hres-YYYYMMDD_0000.pkl`.

The script downloads two ERA5 time steps (T-6h and T0) per day, covering:
- **Pressure levels:** z, t, u, v, w, q at 13 levels (1000–50 hPa)
- **Single levels:** 10u, 10v, 2d, 2t, msl, skt, sp, tcw, lsm, z, slor, sdor
- **Soil levels:** stl1, stl2

---

## Step 4 — Run batch ensemble inference

Inference runs inside the Apptainer container and requires a CUDA GPU.

**Via Slurm (recommended for large batches):**

```bash
sbatch slurm/submit_job.sh 2009
# Extra flags are forwarded to 2_batch_inference.py:
sbatch slurm/submit_job.sh 2009 --start-month 5 --end-month 6
```

**Directly (inside the container):**

```bash
apptainer exec --nv aifs-crps-ens.sif \
    python3 scripts/2_batch_inference.py --year 2009

# All available flags:
python3 scripts/2_batch_inference.py --help
# --year         (required)  Year to process
# --start-month  (default 3) First month
# --end-month    (default 6) Last month
# --members      (default 30) Ensemble size
# --lead-hours   (default 192) Forecast horizon in hours
# --data-dir     (default ../data) Root data directory
```

**Output format** (per day):
```
<data-dir>/forecasts/<YEAR>/fcst_t2m_30mem_192h_YYYYMMDD.nc
  Variables: t2m (K)
  Dimensions: time (32 × 6-hourly steps), member (30), node (54208)
  Compression: zlib level 5, 2-digit precision
```

---

## Step 5 — Extract surface inputs (optional)

Surface and soil fields needed for contextual analysis are extracted from the
same IC pickles used for inference:

```bash
python scripts/3_extract_surface_inputs.py --year 2009
```

Output: `<data-dir>/surface_inputs/<YEAR>/sfc_input_YYYYMMDD.nc`

---

## Step 6 — Convert to Zarr and upload to MinIO

These steps are run inside the `climt` conda environment after sourcing `.env`.

```bash
source .env

# Upload the static model grid (run once)
python scripts/6_grid_to_zarr.py

# Convert forecast NetCDFs for a range of years
python scripts/4_nc_to_zarr.py --start-year 2000 --end-year 2024

# Convert surface inputs for a single year
python scripts/5_surface_to_zarr.py --year 2009
```

**Zarr chunking strategy:**
- Forecasts: `{time: 32, member: 10, node: 54208}`
- Surface inputs: `{time: 2, node: 54208}`
- Grid: `{node: 54208}`

---

## Loading data for analysis

```python
from scripts.helper import load_forecast, load_surface_inputs

# Full global forecast for a single date
ds = load_forecast("20090601")
print(ds)  # t2m: (time=32, member=30, node=54208)

# Regional subset (South Asia)
ds_region = load_forecast(
    "20090601",
    variables=["t2m"],
    lon_bounds=(60, 100),
    lat_bounds=(5, 35),
)

# Surface inputs
sfc = load_surface_inputs("20090601", variables=["2t", "msl"])
```

---

## Model reference

| Property | Value |
|---|---|
| Model | ECMWF AIFS-ENS |
| Checkpoint | `ecmwf/aifs-ens-1.0` (HuggingFace) |
| Grid | N320 reduced Gaussian (~25 km, 54208 nodes) |
| Ensemble | 30 members, independent random seeds per member |
| Lead time | 192 h (8 days) at 6-hourly intervals |
| Variable | 2m temperature (`2t`) |
| IC source | ERA5 reanalysis (ECMWF CDS) |

**Citation:** Bouallegue, Z. B., et al. (2024). *The rise of data-driven weather forecasting: A first statistical assessment of machine learning-based weather forecasts in an operational-like context.* Bulletin of the American Meteorological Society. https://doi.org/10.1175/BAMS-D-23-0162.1

---

## Troubleshooting

**`MINIO_ACCESS_KEY` not set** — Run `source .env` before executing zarr-conversion scripts.

**CDS API timeout** — The CDS queue can be slow for historical reanalysis requests.  The downloader skips already-downloaded files, so rerunning is safe.

**OOM on GPU** — Reduce `--members` or run one year at a time.

**FlashAttention build fails** — The container definition compiles FlashAttention from source; ensure the base Docker image (`aifs:latest`) contains a compatible CUDA toolkit.
