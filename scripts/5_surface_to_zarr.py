"""Convert surface-input NetCDFs on MinIO to Zarr for a given year."""

import argparse
import os
import sys

import s3fs
import xarray as xr

BUCKET = "fcst-lib"
CHUNKS = {"time": 2, "node": 54208}


def _s3():
    endpoint   = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key = os.environ.get("MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        sys.exit("error: MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set (see .env.example)")
    return s3fs.S3FileSystem(key=access_key, secret=secret_key,
                             client_kwargs={"endpoint_url": endpoint})


def convert_year(s3, year):
    files = sorted(s3.glob(f"{BUCKET}/surface_inputs/{year}/*.nc"))
    print(f"Surface inputs {year}: {len(files)} files")

    for i, nc_path in enumerate(files, 1):
        fname    = nc_path.split("/")[-1]
        date_str = fname.replace("sfc_input_", "").replace(".nc", "")
        zarr_out = f"s3://{BUCKET}/zarr/surface_inputs/{year}/{date_str}.zarr"

        if s3.exists(zarr_out):
            print(f"  [{i}/{len(files)}] {date_str} skip")
            continue

        try:
            with s3.open(nc_path, "rb") as f:
                ds = xr.open_dataset(f, engine="h5netcdf").chunk(CHUNKS)
            ds.to_zarr(s3.get_mapper(zarr_out), mode="w-", consolidated=True, zarr_format=2)
            print(f"  [{i}/{len(files)}] {date_str} done")
        except Exception as exc:
            print(f"  [{i}/{len(files)}] {date_str} ERROR: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Convert surface input NetCDFs to Zarr on MinIO")
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()

    s3 = _s3()
    convert_year(s3, args.year)


if __name__ == "__main__":
    main()
