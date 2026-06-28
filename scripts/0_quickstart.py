"""Minimal AIFS-ENS test run — loads an IC pickle, runs a 12-hour forecast, plots 100m wind."""

import argparse
import pickle
import sys

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import matplotlib.tri as tri
import numpy as np
from anemoi.inference.runners.simple import SimpleRunner
from anemoi.inference.outputs.printer import print_state

CHECKPOINT = {"huggingface": "ecmwf/aifs-ens-1.0"}


def main():
    parser = argparse.ArgumentParser(description="AIFS-ENS quickstart: 12-hour test forecast")
    parser.add_argument("ic_pickle", help="Initial-condition pickle (from 1_download_ic.py)")
    parser.add_argument("--out", default="quickstart_100u.png")
    args = parser.parse_args()

    print(f"Loading {args.ic_pickle}...")
    with open(args.ic_pickle, "rb") as f:
        state = pickle.load(f)
    print(f"  date: {state['date']}")

    runner = SimpleRunner(CHECKPOINT, device="cuda")
    last = None
    for step in runner.run(input_state=state, lead_time=12):
        print_state(step)
        last = step

    if last is None:
        sys.exit("error: model produced no output")

    lats = last["latitudes"]
    lons = np.where(last["longitudes"] > 180, last["longitudes"] - 360, last["longitudes"])
    u100 = last["fields"]["100u"]

    fig, ax = plt.subplots(figsize=(11, 6), subplot_kw={"projection": ccrs.PlateCarree()})
    ax.coastlines()
    ax.add_feature(cfeature.BORDERS, linestyle=":")
    cf = ax.tricontourf(tri.Triangulation(lons, lats), u100, levels=20,
                        transform=ccrs.PlateCarree(), cmap="RdBu")
    fig.colorbar(cf, ax=ax, shrink=0.7, label="100u (m/s)")
    ax.set_title(f"100m wind at {last['date']}")
    plt.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
