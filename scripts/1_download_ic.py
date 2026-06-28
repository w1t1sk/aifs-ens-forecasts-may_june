"""Download ERA5 initial conditions for AIFS-ENS inference (any year, March–June by default)."""

import argparse
import calendar
import datetime
import os
import pickle
import shutil

import cdsapi
import earthkit.data as ekd
import numpy as np

DATA_SPECS = [
    {
        "dataset": "reanalysis-era5-pressure-levels",
        "prefix":  "pl",
        "vars":    ["z", "t", "u", "v", "w", "q"],
        "levels":  [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50],
    },
    {
        "dataset": "reanalysis-era5-single-levels",
        "prefix":  "sfc",
        "vars":    ["10u", "10v", "2d", "2t", "msl", "skt", "sp", "tcw", "lsm", "z", "slor", "sdor"],
        "levels":  None,
    },
    {
        "dataset": "reanalysis-era5-single-levels",
        "prefix":  "soil",
        "vars":    ["stl1", "stl2"],
        "levels":  None,
    },
]


def _cds_request(spec, date):
    req = {
        "product_type": "reanalysis",
        "variable":     spec["vars"],
        "grid":         "N320",
        "format":       "grib",
        "date":         date.strftime("%Y-%m-%d"),
        "time":         date.strftime("%H:%M"),
    }
    if spec.get("levels"):
        req["levelist"] = spec["levels"]
    return req


def _to_array(field_list):
    return np.squeeze(field_list.to_numpy())


def _download_day(date, save_dir, temp_dir, client):
    tag = date.strftime("%Y%m%d")
    out = os.path.join(save_dir, f"aifs-init-hres-{tag}_0000.pkl")

    if os.path.exists(out):
        print(f"[{tag}] skip")
        return

    t0  = date.replace(hour=0, minute=0)
    tm6 = t0 - datetime.timedelta(hours=6)
    fields = {}

    for spec in DATA_SPECS:
        p_tm6 = os.path.join(temp_dir, f"{spec['prefix']}_{tm6:%Y%m%d_%H%M}.grib")
        p_t0  = os.path.join(temp_dir, f"{spec['prefix']}_{t0:%Y%m%d_%H%M}.grib")

        if not os.path.exists(p_tm6):
            client.retrieve(spec["dataset"], _cds_request(spec, tm6), p_tm6)
        if not os.path.exists(p_t0):
            client.retrieve(spec["dataset"], _cds_request(spec, t0), p_t0)

        d_tm6 = ekd.from_source("file", p_tm6)
        d_t0  = ekd.from_source("file", p_t0)

        for var in spec["vars"]:
            if spec["levels"]:
                for level in spec["levels"]:
                    f_tm6 = d_tm6.sel(shortName=var, level=level)
                    f_t0  = d_t0.sel(shortName=var, level=level)
                    if len(f_tm6) == 0 or len(f_t0) == 0:
                        continue
                    key = f"z_{level}" if var == "z" else f"{var}_{level}"
                    fields[key] = np.stack([_to_array(f_tm6), _to_array(f_t0)])[np.newaxis]
            else:
                fields[var] = np.stack([_to_array(d_tm6.sel(shortName=var)),
                                        _to_array(d_t0.sel(shortName=var))])[np.newaxis]

    with open(out, "wb") as f:
        pickle.dump({"date": t0, "fields": fields}, f)

    # clear temp GRIBs after each day to keep disk usage bounded
    for fname in os.listdir(temp_dir):
        os.remove(os.path.join(temp_dir, fname))

    print(f"[{tag}] done")


def main():
    parser = argparse.ArgumentParser(description="Download ERA5 ICs for AIFS-ENS")
    parser.add_argument("--year",        type=int, required=True)
    parser.add_argument("--start-month", type=int, default=3, metavar="M")
    parser.add_argument("--end-month",   type=int, default=6, metavar="M")
    parser.add_argument("--data-dir",    default="../data",
                        help="Root data dir; ICs saved under <dir>/initial_conditions/<year>/")
    args = parser.parse_args()

    year  = args.year
    start = datetime.datetime(year, args.start_month, 1)
    end   = datetime.datetime(year, args.end_month, calendar.monthrange(year, args.end_month)[1])

    save_dir = os.path.join(args.data_dir, "initial_conditions", str(year))
    temp_dir = f"_dl_temp_{year}"

    os.makedirs(save_dir, exist_ok=True)
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir)

    print(f"Downloading ERA5 ICs: {start:%Y-%m-%d} → {end:%Y-%m-%d} → {save_dir}")

    client = cdsapi.Client()
    date = start
    while date <= end:
        try:
            _download_day(date, save_dir, temp_dir, client)
        except Exception as exc:
            print(f"[{date:%Y%m%d}] ERROR: {exc}")
        date += datetime.timedelta(days=1)

    shutil.rmtree(temp_dir, ignore_errors=True)
    print("Download complete.")


if __name__ == "__main__":
    main()
