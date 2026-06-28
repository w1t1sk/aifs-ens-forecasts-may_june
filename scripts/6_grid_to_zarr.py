"""Upload the static N320 model grid to MinIO as Zarr (run once)."""

import os
import sys

import s3fs
import xarray as xr

BUCKET      = "fcst-lib"
INPUT_PATH  = f"{BUCKET}/grid/master_grid_n320.nc"
OUTPUT_PATH = f"s3://{BUCKET}/zarr/grid/grid_320.zarr"
CHUNKS      = {"node": 54208}


def main():
    endpoint   = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key = os.environ.get("MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        sys.exit("error: MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set (see .env.example)")

    s3 = s3fs.S3FileSystem(key=access_key, secret=secret_key,
                           client_kwargs={"endpoint_url": endpoint})

    if s3.exists(OUTPUT_PATH):
        print("grid_320.zarr already exists — skipping.")
        return

    print(f"Converting {INPUT_PATH} → {OUTPUT_PATH}")
    with s3.open(INPUT_PATH, "rb") as f:
        ds = xr.open_dataset(f, engine="h5netcdf").chunk(CHUNKS)
    ds.to_zarr(s3.get_mapper(OUTPUT_PATH), mode="w-", consolidated=True, zarr_format=2)
    print("Done.")


if __name__ == "__main__":
    main()
