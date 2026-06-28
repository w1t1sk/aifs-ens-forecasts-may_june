"""Load AIFS-ENS forecast and surface-input Zarr from MinIO."""

import os

import numpy as np
import xarray as xr

BUCKET = "fcst-lib"

_storage = None
_grid    = None
_nodes   = {}


def _get_storage():
    global _storage
    if _storage is not None:
        return _storage
    endpoint   = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key = os.environ.get("MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        raise RuntimeError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set (see .env.example)")
    _storage = {
        "key": access_key,
        "secret": secret_key,
        "client_kwargs": {"endpoint_url": endpoint},
    }
    return _storage


def _open(path):
    return xr.open_zarr(path, storage_options=_get_storage(), consolidated=True)


def get_grid():
    global _grid
    if _grid is None:
        _grid = _open(f"s3://{BUCKET}/zarr/grid/grid_320.zarr")
    return _grid


def _node_indices(lon_bounds, lat_bounds):
    key = (lon_bounds, lat_bounds)
    if key in _nodes:
        return _nodes[key]

    grid = get_grid()
    lon  = np.where(grid["longitude"].values > 180,
                    grid["longitude"].values - 360,
                    grid["longitude"].values)
    lat  = grid["latitude"].values

    mask = ((lon >= lon_bounds[0]) & (lon <= lon_bounds[1]) &
            (lat >= lat_bounds[0]) & (lat <= lat_bounds[1]))
    idx  = np.where(mask)[0]

    if len(idx) == 0:
        raise ValueError(f"No grid nodes in region lon={lon_bounds} lat={lat_bounds}")

    _nodes[key] = idx
    return idx


def load_forecast(date, variables=None, lon_bounds=None, lat_bounds=None):
    """Load forecast Zarr by date string (YYYYMMDD)."""
    ds = _open(f"s3://{BUCKET}/zarr/{date[:4]}/{date}.zarr")
    if variables is not None:
        ds = ds[variables]
    if lon_bounds is not None and lat_bounds is not None:
        ds = ds.isel(node=_node_indices(lon_bounds, lat_bounds))
    return ds


def load_surface_inputs(date, variables=None, lon_bounds=None, lat_bounds=None):
    """Load surface-input Zarr by date string (YYYYMMDD)."""
    ds = _open(f"s3://{BUCKET}/zarr/surface_inputs/{date[:4]}/{date}.zarr")
    if variables is not None:
        ds = ds[variables]
    if lon_bounds is not None and lat_bounds is not None:
        ds = ds.isel(node=_node_indices(lon_bounds, lat_bounds))
    return ds
