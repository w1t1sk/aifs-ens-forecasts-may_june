# AIFS-ENS 40-Year May-June Hindcast Library

This repository contains the pipeline used to generate a 40-year ensemble hindcast library with the ECMWF AIFS-ENS model.

The archive covers 1986 to 2025. Forecasts are initialized once per day from 1 March to 30 June, with 30 ensemble members and a forecast horizon of 8 days at 6-hour intervals.

Initial conditions come from ERA5 reanalysis data on the N320 reduced Gaussian grid. Forecast outputs are first written as NetCDF files and can then be converted to Zarr and stored on MinIO.

## Repository structure

```text
aifs-ens-forecasts-may_june/
├── environment/
│   ├── aifs-crps-ens.def
│   └── environment.yml
├── scripts/
│   ├── 0_quickstart.py
│   ├── 1_download_ic.py
│   ├── 2_batch_inference.py
│   ├── 3_extract_surface_inputs.py
│   ├── 4_nc_to_zarr.py
│   ├── 5_surface_to_zarr.py
│   ├── 6_grid_to_zarr.py
│   └── helper.py
├── slurm/
│   └── submit_job.sh
├── notebooks/
│   └── zarr_conversion_demo.ipynb
├── .env.example
└── .gitignore
```

The numbered scripts follow the order in which the pipeline is normally run.

## Requirements

You will need:

- an ECMWF CDS API key
- Apptainer 1.1 or newer
- a CUDA-capable GPU
- Conda or Mamba
- MinIO or another S3-compatible object store

Inference has been tested on NVIDIA A100 and H100 GPUs.

## 1. Set up the CDS API

Create an account at:

https://cds.climate.copernicus.eu

Then place your CDS API credentials in:

```text
~/.cdsapirc
```

The ERA5 download script uses this automatically.

## 2. Build the Apptainer container

AIFS-ENS inference runs inside an Apptainer container.

```bash
apptainer build aifs-crps-ens.sif environment/aifs-crps-ens.def
```

The definition file expects a local Docker image called:

```text
aifs:latest
```

Before running a large batch, you can test the container with:

```bash
apptainer exec --nv aifs-crps-ens.sif \
    python3 scripts/0_quickstart.py path/to/aifs-init-hres-YYYYMMDD_0000.pkl
```

## 3. Create the Conda environment

The conversion and analysis scripts use a separate Conda environment.

```bash
conda env create -f environment/environment.yml
conda activate climt
```

## 4. Configure MinIO

Copy the example environment file:

```bash
cp .env.example .env
```

Add your MinIO credentials to `.env`, then load them:

```bash
source .env
```

The scripts expect:

```text
MINIO_ENDPOINT
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
```

The main MinIO layout is:

```text
fcst-lib/
├── forecasts/{year}/fcst_t2m_30mem_192h_{date}.nc
├── surface_inputs/{year}/sfc_input_{date}.nc
├── grid/master_grid_n320.nc
├── zarr/{year}/{date}.zarr
├── zarr/surface_inputs/{year}/{date}.zarr
└── zarr/grid/grid_320.zarr
```

## 5. Download ERA5 initial conditions

Download the default March to June period for one year:

```bash
python scripts/1_download_ic.py --year 2009
```

For a custom month range:

```bash
python scripts/1_download_ic.py \
    --year 2009 \
    --start-month 5 \
    --end-month 6
```

For a custom data directory:

```bash
python scripts/1_download_ic.py \
    --year 2009 \
    --data-dir /scratch/mydata
```

Each daily initial-condition file is saved as:

```text
<data-dir>/initial_conditions/<YEAR>/aifs-init-hres-YYYYMMDD_0000.pkl
```

The script downloads two ERA5 time steps for each initialization, T-6h and T0.

It includes:

```text
Pressure-level fields:
z, t, u, v, w, q

Single-level fields:
10u, 10v, 2d, 2t, msl, skt, sp, tcw, lsm, z, slor, sdor

Soil fields:
stl1, stl2
```

The downloader skips files that already exist, so rerunning an interrupted download is safe.

## 6. Run AIFS-ENS inference

For large batches, use the Slurm wrapper:

```bash
sbatch slurm/submit_job.sh 2009
```

Extra arguments are forwarded to the Python script:

```bash
sbatch slurm/submit_job.sh 2009 \
    --start-month 5 \
    --end-month 6
```

You can also run inference directly:

```bash
apptainer exec --nv aifs-crps-ens.sif \
    python3 scripts/2_batch_inference.py --year 2009
```

Main options:

```text
--year         required
--start-month  default 3
--end-month    default 6
--members      default 30
--lead-hours   default 192
--data-dir     default ../data
```

Each daily forecast is written to:

```text
<data-dir>/forecasts/<YEAR>/fcst_t2m_30mem_192h_YYYYMMDD.nc
```

The output contains:

```text
Variable:
t2m

Dimensions:
time   = 32
member = 30
node   = 54208
```

Temperatures are stored in Kelvin.

## 7. Extract surface inputs

Surface and soil fields from the initial-condition files can be saved separately with:

```bash
python scripts/3_extract_surface_inputs.py --year 2009
```

Output:

```text
<data-dir>/surface_inputs/<YEAR>/sfc_input_YYYYMMDD.nc
```

This step is optional if you only need the forecast output.

## 8. Convert to Zarr

Activate the Conda environment and load the MinIO credentials:

```bash
conda activate climt
source .env
```

Upload the static grid once:

```bash
python scripts/6_grid_to_zarr.py
```

Convert forecast files:

```bash
python scripts/4_nc_to_zarr.py \
    --start-year 2000 \
    --end-year 2024
```

Convert surface inputs:

```bash
python scripts/5_surface_to_zarr.py --year 2009
```

The Zarr chunk sizes are:

```text
Forecasts:
time = 32
member = 10
node = 54208

Surface inputs:
time = 2
node = 54208

Grid:
node = 54208
```

## Loading data

`scripts/helper.py` contains convenience functions for loading the archived Zarr data.

```python
from scripts.helper import load_forecast, load_surface_inputs

ds = load_forecast("20090601")
print(ds)
```

Load a regional subset:

```python
ds_region = load_forecast(
    "20090601",
    variables=["t2m"],
    lon_bounds=(60, 100),
    lat_bounds=(5, 35),
)
```

Load surface inputs:

```python
sfc = load_surface_inputs(
    "20090601",
    variables=["2t", "msl"],
)
```

## Typical workflow

For one year, the full workflow is:

```bash
python scripts/1_download_ic.py --year 2009

sbatch slurm/submit_job.sh 2009

python scripts/3_extract_surface_inputs.py --year 2009

conda activate climt
source .env

python scripts/4_nc_to_zarr.py \
    --start-year 2009 \
    --end-year 2009

python scripts/5_surface_to_zarr.py --year 2009
```

The grid upload only needs to be run once:

```bash
python scripts/6_grid_to_zarr.py
```

## Dataset summary

| Property | Value |
|---|---|
| Years | 1986 to 2025 |
| Initialization period | 1 March to 30 June |
| Model | ECMWF AIFS-ENS |
| Checkpoint | `ecmwf/aifs-ens-1.0` |
| Initial conditions | ERA5 |
| Grid | N320 reduced Gaussian |
| Grid nodes | 54,208 |
| Ensemble members | 30 |
| Forecast horizon | 192 hours |
| Output interval | 6 hours |
| Main forecast variable | 2 m temperature |
