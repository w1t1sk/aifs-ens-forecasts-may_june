"""AIFS-ENS batch ensemble inference for any year/month range.

Run inside the Apptainer container (see slurm/submit_job.sh).
"""

import argparse
import calendar
import datetime
import os
import pickle
import random
import time

import numpy as np
import torch
import xarray as xr
from anemoi.inference.runners.simple import SimpleRunner

CHECKPOINT = {"huggingface": "ecmwf/aifs-ens-1.0"}
ENCODING   = {"t2m": {"zlib": True, "complevel": 5, "least_significant_digit": 2}}


def _seed(val):
    torch.manual_seed(val)
    torch.cuda.manual_seed_all(val)
    np.random.seed(val)


def _run_member(runner, state, lead_hours):
    steps = []
    for out in runner.run(input_state=state, lead_time=lead_hours):
        steps.append(np.array(out["fields"]["2t"]))
    return np.stack(steps)  # (n_steps, node)


def _load_state(pkl_path):
    with open(pkl_path, "rb") as f:
        state = pickle.load(f)
    # IC pickles sometimes carry a leading member dim; squeeze it
    for k, v in state["fields"].items():
        if v.ndim == 3:
            state["fields"][k] = v.squeeze(0)
    return state


def main():
    parser = argparse.ArgumentParser(description="AIFS-ENS batch ensemble inference")
    parser.add_argument("--year",        type=int, required=True)
    parser.add_argument("--start-month", type=int, default=3, metavar="M")
    parser.add_argument("--end-month",   type=int, default=6, metavar="M")
    parser.add_argument("--members",     type=int, default=30)
    parser.add_argument("--lead-hours",  type=int, default=192)
    parser.add_argument("--data-dir",    default="../data")
    args = parser.parse_args()

    year       = args.year
    n_members  = args.members
    lead_hours = args.lead_hours
    start = datetime.datetime(year, args.start_month, 1)
    end   = datetime.datetime(year, args.end_month, calendar.monthrange(year, args.end_month)[1])

    in_dir  = os.path.join(args.data_dir, "initial_conditions", str(year))
    out_dir = os.path.join(args.data_dir, "forecasts", str(year))
    os.makedirs(out_dir, exist_ok=True)

    print(f"AIFS-ENS inference: {start:%Y-%m-%d} → {end:%Y-%m-%d}  "
          f"({n_members} members, {lead_hours}h lead)")
    print(f"  IC dir:  {in_dir}")
    print(f"  Out dir: {out_dir}")

    runner = SimpleRunner(CHECKPOINT, device="cuda")

    date = start
    while date <= end:
        tag      = date.strftime("%Y%m%d")
        pkl_path = os.path.join(in_dir,  f"aifs-init-hres-{tag}_0000.pkl")
        nc_path  = os.path.join(out_dir, f"fcst_t2m_{n_members}mem_{lead_hours}h_{tag}.nc")

        if os.path.exists(nc_path):
            print(f"[{tag}] skip")
            date += datetime.timedelta(days=1)
            continue

        if not os.path.exists(pkl_path):
            print(f"[{tag}] WARNING: IC missing")
            date += datetime.timedelta(days=1)
            continue

        t0    = time.time()
        state = _load_state(pkl_path)

        members = []
        for _ in range(n_members):
            _seed(random.randrange(2**32))
            members.append(_run_member(runner, state, lead_hours))

        arr   = np.stack(members, axis=1)  # (time, member, node)
        times = [date + datetime.timedelta(hours=(i + 1) * 6) for i in range(arr.shape[0])]

        ds = xr.Dataset(
            {"t2m": (("time", "member", "node"), arr, {"units": "K"})},
            coords={"time": times, "member": np.arange(n_members)},
        )
        ds.attrs = {}
        ds.to_netcdf(nc_path, encoding=ENCODING)

        print(f"[{tag}] done  ({time.time() - t0:.0f}s)")
        date += datetime.timedelta(days=1)

    print("Batch complete.")


if __name__ == "__main__":
    main()
