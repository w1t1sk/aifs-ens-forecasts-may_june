"""Extract surface and soil fields from IC pickles into per-date NetCDF files."""

import argparse
import calendar
import datetime
import os
import pickle

import xarray as xr

SURFACE_VARS = [
    "10u", "10v", "2d", "2t", "msl", "skt", "sp", "tcw",
    "lsm", "z", "slor", "sdor", "stl1", "stl2",
]


def main():
    parser = argparse.ArgumentParser(description="Extract surface inputs from IC pickles")
    parser.add_argument("--year",        type=int, required=True)
    parser.add_argument("--start-month", type=int, default=3, metavar="M")
    parser.add_argument("--end-month",   type=int, default=6, metavar="M")
    parser.add_argument("--data-dir",    default="../data")
    args = parser.parse_args()

    year  = args.year
    start = datetime.datetime(year, args.start_month, 1)
    end   = datetime.datetime(year, args.end_month, calendar.monthrange(year, args.end_month)[1])

    in_dir  = os.path.join(args.data_dir, "initial_conditions", str(year))
    out_dir = os.path.join(args.data_dir, "surface_inputs",     str(year))
    os.makedirs(out_dir, exist_ok=True)

    print(f"Surface extraction: {start:%Y-%m-%d} → {end:%Y-%m-%d}")
    print(f"  IC dir:  {in_dir}")
    print(f"  Out dir: {out_dir}")

    date = start
    while date <= end:
        tag      = date.strftime("%Y%m%d")
        pkl_path = os.path.join(in_dir,  f"aifs-init-hres-{tag}_0000.pkl")
        nc_path  = os.path.join(out_dir, f"sfc_input_{tag}.nc")

        if os.path.exists(nc_path):
            date += datetime.timedelta(days=1)
            continue

        if not os.path.exists(pkl_path):
            print(f"[{tag}] WARNING: IC missing")
            date += datetime.timedelta(days=1)
            continue

        with open(pkl_path, "rb") as f:
            fields = pickle.load(f)["fields"]

        # IC shape: (1_member, 2_timesteps, node) → squeeze member → (2, node)
        data_vars = {v: (("time", "node"), fields[v].squeeze(0))
                     for v in SURFACE_VARS if v in fields}

        times = [date - datetime.timedelta(hours=6), date]
        ds    = xr.Dataset(data_vars, coords={"time": times})
        ds.attrs = {}
        ds.to_netcdf(nc_path, encoding={v: {"zlib": True, "complevel": 5} for v in data_vars})

        print(f"[{tag}] done")
        date += datetime.timedelta(days=1)

    print("Done.")


if __name__ == "__main__":
    main()
