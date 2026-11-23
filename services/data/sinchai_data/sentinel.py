"""Sentinel-2 crop-calendar map for the pilot site.

Imagery (REAL): Sentinel-2 L2A surface reflectance from the public Earth Search STAC catalogue
(collection ``sentinel-2-c1-l2a``, the consistently reprocessed Collection 1 archive, as
Cloud-Optimised GeoTIFFs on public S3, no key). Only a 2.5 x 2.5 km
window around the site is read, through HTTP range requests, for bands B02, B03, B04, B08 and the
scene classification layer (SCL). Pixels flagged as cloud, cloud shadow, cirrus, saturated, dark
or unclassified in SCL are masked out.

Classes (DERIVED): a transparent phenology rule set on the per-pixel 10 m NDVI time series over
one agricultural year (June 2024 to May 2025). The rules follow the standard crop calendar for
the north Bihar plains, as written up in FAO crop calendars and in ISRO/MNCFC crop-mapping
practice, which separate seasons by when the green-up peak falls rather than by spectral
signature:

* kharif crop (in this area mostly transplanted paddy): canopy builds after transplanting in
  July and peaks in late August to early October, then the field is bare after harvest in
  late October / November. Rule: high NDVI peak in Aug-Oct, low peak in Dec-Mar.
* rabi crop (wheat, with maize, mustard, lentil and potato): sown November to mid December,
  peak green in late January to February, harvested March-April. Rule: high peak in Dec-Mar,
  low peak in Aug-Oct.
* double cropped: both peaks, separated by a post-kharif trough in Nov-Dec.
* orchard / trees (mango, litchi, bamboo groves, homestead trees): stays green all year, so the
  low end of the NDVI series stays high and there is no harvest trough.
* water: open water has negative NDVI and positive NDWI (green vs NIR) for most of the year.
* fallow / built-up: never gets green (NDVI peak below the crop threshold). NDVI alone cannot
  separate roofs, roads and permanently fallow soil, so they are one class.

What NDVI phenology cannot do: tell paddy from kharif maize, or wheat from rabi maize, mustard
or potato. Classes are season classes, not crop species. There are no ground-truth labels
offline; see ``validation`` in the snapshot JSON.

Run: ``env -u VIRTUAL_ENV uv run python -m sinchai_data.sentinel`` (needs internet). Offline use
reads ``services/data/snapshots/s2_ndvi_stack.npz`` and ``s2_crop_shares.json``.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import numpy as np

SNAP_DIR = Path(__file__).resolve().parents[1] / "snapshots"
REPO_ROOT = Path(__file__).resolve().parents[3]
BASEMAP_DIR = REPO_ROOT / "apps" / "web" / "public" / "basemap"
STACK_PATH = SNAP_DIR / "s2_ndvi_stack.npz"
SHARES_PATH = SNAP_DIR / "s2_crop_shares.json"

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
# Collection 1 is used rather than the older ``sentinel-2-l2a`` collection: in the older one the
# stored digital numbers for this tile already had the +1000 radiometric offset removed while the
# metadata still declared offset -0.1, which produced negative red reflectance and NDVI near 1
# over town and water. Collection 1 stores DN = 1000 + 10000 * reflectance, matching its metadata.
COLLECTION = "sentinel-2-c1-l2a"
MGRS_TILE = "MGRS-45RUJ"  # the tile that covers the site; keeps every scene on one pixel grid
UTM_EPSG = 32645
YEAR_START = "2024-06-01"
YEAR_END = "2025-05-31"
AOI_HALF_M = 1250.0  # 2.5 x 2.5 km
PIXEL_M = 10.0

# SCL: 4 vegetation, 5 not vegetated, 6 water are kept. 0 no data, 1 saturated, 2 dark/shadow,
# 3 cloud shadow, 7 unclassified, 8/9 cloud, 10 cirrus, 11 snow are masked.
SCL_CLEAR = (4, 5, 6)
MIN_CLEAR_FRACTION = 0.6  # scene is used only if this share of the AOI is clear
RABI_BIN_DAYS = 10  # dry season has many clear scenes; keep the clearest one per 10 days

NODATA_I16 = -32768
SCALE_I16 = 10000.0

# Phenology windows (month-day, inclusive) and thresholds.
KHARIF_WINDOW = ((8, 1), (10, 31))  # paddy peak
RABI_WINDOW = ((12, 15), (3, 15))  # wheat / mustard peak (Jan-Feb centred)
TROUGH_WINDOW = ((11, 1), (12, 20))  # bare or freshly sown between seasons
CROP_PEAK = 0.60  # NDVI peak of a closed crop canopy (paddy and wheat reach 0.7-0.85)
NO_CROP_PEAK = 0.40  # below this the season is treated as not cropped
GREEN_MAX = 0.35  # whole-year NDVI max below this: never green (fallow / built-up)
TREE_LOW = 0.35  # whole-year 10th-percentile NDVI above this (deciduous trees dip in Feb-Mar) ...
TREE_MEDIAN = 0.55  # ... and a whole-year median above this: green all year
WATER_NDWI = 0.05  # median NDWI above this (and NDVI below 0.1): open water

CLASSES: dict[str, dict] = {
    "kharif_paddy": {"code": 1, "label": "Kharif crop only (mostly paddy)", "color": "#2f9e44"},
    "rabi_wheat_mustard": {
        "code": 2,
        "label": "Rabi crop only (wheat, maize, mustard)",
        "color": "#f2b705",
    },
    "double_cropped": {"code": 3, "label": "Double cropped (kharif + rabi)", "color": "#1971c2"},
    "orchard_trees": {"code": 4, "label": "Orchard / trees (green all year)", "color": "#0b5d1e"},
    "fallow_builtup": {"code": 5, "label": "Fallow / built-up (never green)", "color": "#c2a383"},
    "water": {"code": 6, "label": "Water", "color": "#4dabf7"},
    "other_mixed": {"code": 7, "label": "Other / mixed (weak or partial signal)", "color": "#ced4da"},
}
NO_DATA_CODE = 0
CODE_TO_CLASS = {v["code"]: k for k, v in CLASSES.items()}


# --------------------------------------------------------------------------------------------
# Classifier (pure numpy, offline)
# --------------------------------------------------------------------------------------------


def _in_window(d: date, window: tuple[tuple[int, int], tuple[int, int]]) -> bool:
    (m0, d0), (m1, d1) = window
    key = (d.month, d.day)
    if (m0, d0) <= (m1, d1):
        return (m0, d0) <= key <= (m1, d1)
    return key >= (m0, d0) or key <= (m1, d1)  # window wraps the new year


def _nan_reduce(fn, x: np.ndarray, sel: np.ndarray) -> np.ndarray:
    """Apply a nan-aware reducer over the time axis for the selected dates; NaN if none valid."""
    sub = x[sel]
    out = np.full(x.shape[1:], np.nan, dtype=np.float32)
    if sub.shape[0] == 0:
        return out
    ok = np.isfinite(sub).any(axis=0)
    if ok.any():
        out[ok] = fn(sub[:, ok], axis=0)
    return out


def classify(
    ndvi: np.ndarray, dates: list[date], ndwi: np.ndarray | None = None
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Classify a (T, ...) NDVI stack (NaN = masked) into class codes.

    Returns (codes, features). Works on any trailing shape, so a (T, N) array of synthetic
    series is fine. ``ndwi`` is an optional stack of the same shape used for water.
    """
    ndvi = np.asarray(ndvi, dtype=np.float32)
    dates = list(dates)
    if ndvi.shape[0] != len(dates):
        raise ValueError("ndvi time axis and dates differ in length")
    kh = np.array([_in_window(d, KHARIF_WINDOW) for d in dates])
    rb = np.array([_in_window(d, RABI_WINDOW) for d in dates])
    tr = np.array([_in_window(d, TROUGH_WINDOW) for d in dates])
    every = np.ones(len(dates), dtype=bool)

    k_peak = _nan_reduce(np.nanmax, ndvi, kh)
    r_peak = _nan_reduce(np.nanmax, ndvi, rb)
    trough = _nan_reduce(np.nanmin, ndvi, tr)
    y_max = _nan_reduce(np.nanmax, ndvi, every)
    y_p10 = _nan_reduce(lambda a, axis: np.nanpercentile(a, 10, axis=axis), ndvi, every)
    y_med = _nan_reduce(np.nanmedian, ndvi, every)
    if ndwi is not None:
        w_med = _nan_reduce(np.nanmedian, np.asarray(ndwi, dtype=np.float32), every)
    else:
        w_med = np.where(np.isfinite(y_med), -y_med, np.nan).astype(np.float32)
    n_valid = np.isfinite(ndvi).sum(axis=0)

    codes = np.full(ndvi.shape[1:], CLASSES["other_mixed"]["code"], dtype=np.uint8)
    c = {k: v["code"] for k, v in CLASSES.items()}
    has_k = np.isfinite(k_peak)
    has_r = np.isfinite(r_peak)
    kp = np.where(has_k, k_peak, -1.0)
    rp = np.where(has_r, r_peak, -1.0)
    tro = np.where(np.isfinite(trough), trough, np.nan)

    k_crop = has_k & (kp >= CROP_PEAK)
    r_crop = has_r & (rp >= CROP_PEAK)
    k_none = has_k & (kp < NO_CROP_PEAK)
    r_none = has_r & (rp < NO_CROP_PEAK)
    # A real two-season pattern has a bare/young-crop trough between the peaks; without a
    # trough observation the two peaks are still accepted (cannot be checked).
    trough_ok = ~np.isfinite(tro) | (tro <= np.minimum(kp, rp) - 0.15)

    # Order matters: later assignments override earlier ones.
    codes[k_crop & r_none] = c["kharif_paddy"]
    codes[r_crop & k_none] = c["rabi_wheat_mustard"]
    codes[k_crop & r_crop & trough_ok] = c["double_cropped"]
    trees = np.isfinite(y_p10) & (y_p10 >= TREE_LOW) & (y_med >= TREE_MEDIAN) & (n_valid >= 5)
    codes[trees] = c["orchard_trees"]
    codes[np.isfinite(y_max) & (y_max < GREEN_MAX)] = c["fallow_builtup"]
    water = np.isfinite(w_med) & (w_med > WATER_NDWI) & (y_med < 0.1)
    codes[water] = c["water"]
    # Too few clear looks to judge either season.
    codes[(n_valid < 3) | ~(has_k | has_r)] = NO_DATA_CODE

    feats = {
        "kharif_peak": k_peak,
        "rabi_peak": r_peak,
        "trough": trough,
        "year_max": y_max,
        "year_p10": y_p10,
        "ndwi_median": w_med,
        "n_valid": n_valid,
    }
    return codes, feats


def class_shares(codes: np.ndarray) -> dict[str, float]:
    """Area share of each class among pixels with a class (no-data pixels excluded)."""
    valid = codes != NO_DATA_CODE
    n = int(valid.sum())
    if n == 0:
        return {k: 0.0 for k in CLASSES}
    return {k: float((codes[valid] == v["code"]).sum()) / n for k, v in CLASSES.items()}


def crop_mix_from_shares(shares: dict[str, float], rabi_split: dict[str, float] | None = None) -> dict:
    """Map S2 class shares to the village crop-mix keys (crop_mix_rabi / crop_mix_kharif).

    Denominator is cropland seen by the satellite: kharif-only + rabi-only + double-cropped.
    Orchards, water and fallow/built-up are not plots in the village model. Within that
    cropland, a plot is fallow in a season if it carried no crop then. NDVI cannot split the
    rabi crop into wheat and potato, so the rabi crop share is divided in the ratio of the
    existing village assumption (``rabi_split``, default wheat 0.65 : potato 0.20).
    """
    k = shares.get("kharif_paddy", 0.0)
    r = shares.get("rabi_wheat_mustard", 0.0)
    d = shares.get("double_cropped", 0.0)
    crop = k + r + d
    if crop <= 0:
        raise ValueError("no cropland in shares")
    if rabi_split is None:
        try:
            from sinchai_schemas import constants as C

            mix = dict(C.get("crop_mix_rabi"))
            rabi_split = {kk: vv for kk, vv in mix.items() if kk != "fallow"}
        except Exception:  # constants unavailable: fall back to the documented default
            rabi_split = {"wheat": 0.65, "potato": 0.20}
    tot = sum(rabi_split.values())
    rabi_cropped = (r + d) / crop
    rabi = {kk: round(rabi_cropped * vv / tot, 4) for kk, vv in rabi_split.items()}
    rabi["fallow"] = round(1.0 - sum(rabi.values()), 4)
    paddy = round((k + d) / crop, 4)
    kharif = {"paddy": paddy, "fallow": round(1.0 - paddy, 4)}
    return {
        "crop_mix_rabi": rabi,
        "crop_mix_kharif": kharif,
        "cropland_share_of_aoi": round(crop, 4),
        "label": "DERIVED from REAL Sentinel-2 imagery; not validated against field labels",
    }


def crop_mix_from_s2(path: Path = SHARES_PATH) -> dict:
    """Crop mix for the synthetic village, from the committed Sentinel-2 snapshot (offline).

    Returns {"crop_mix_rabi": {...}, "crop_mix_kharif": {...}, ...} with the same keys as
    constants.yaml, so a caller can pass it where village.py reads ``C.get("crop_mix_rabi")``.
    """
    data = json.loads(Path(path).read_text())
    return crop_mix_from_shares(data["shares"])


# --------------------------------------------------------------------------------------------
# Fetch (network)
# --------------------------------------------------------------------------------------------


@dataclass
class Scene:
    id: str
    date: date
    cloud: float
    hrefs: dict[str, str]
    scale: float
    offset: float
    clear: float = 0.0


_SITE_OVERRIDE: tuple[float, float] | None = None


def _site() -> tuple[float, float]:
    if _SITE_OVERRIDE is not None:
        return _SITE_OVERRIDE
    try:
        from sinchai_schemas import constants as C

        return float(C.get("site_lat")), float(C.get("site_lon"))
    except Exception:
        return 25.86, 85.78


def aoi_utm() -> tuple[float, float, float, float]:
    """AOI bounds (left, bottom, right, top) in UTM 45N, snapped to the 10 m Sentinel-2 grid."""
    from rasterio.warp import transform

    lat, lon = _site()
    xs, ys = transform("EPSG:4326", f"EPSG:{UTM_EPSG}", [lon], [lat])
    cx = round(xs[0] / PIXEL_M) * PIXEL_M
    cy = round(ys[0] / PIXEL_M) * PIXEL_M
    return cx - AOI_HALF_M, cy - AOI_HALF_M, cx + AOI_HALF_M, cy + AOI_HALF_M


def search_scenes(max_cloud: float = 95.0) -> list[Scene]:
    lat, lon = _site()
    body = {
        "collections": [COLLECTION],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{YEAR_START}T00:00:00Z/{YEAR_END}T23:59:59Z",
        "limit": 300,
        "query": {"eo:cloud_cover": {"lt": max_cloud}, "grid:code": {"eq": MGRS_TILE}},
    }
    feats = []
    url: str | None = STAC_URL
    with httpx.Client(timeout=60) as client:
        while url:
            r = client.post(url, json=body)
            r.raise_for_status()
            js = r.json()
            feats += js["features"]
            nxt = [ln for ln in js.get("links", []) if ln.get("rel") == "next"]
            url, body = (nxt[0]["href"], nxt[0].get("body", body)) if nxt else (None, body)
    by_date: dict[date, Scene] = {}
    for f in feats:
        p = f["properties"]
        d = date.fromisoformat(p["datetime"][:10])
        a = f["assets"]
        rb = (a["red"].get("raster:bands") or [{}])[0]
        s = Scene(
            id=f["id"],
            date=d,
            cloud=float(p["eo:cloud_cover"]),
            hrefs={k: a[k]["href"] for k in ("blue", "green", "red", "nir", "scl")},
            scale=float(rb.get("scale", 1e-4)),
            offset=float(rb.get("offset", 0.0)),
        )
        # Several processing runs (or two satellites) on one day: keep the least cloudy, then
        # the newest processing run.
        old = by_date.get(d)
        if old is None or (s.cloud, s.id) < (old.cloud, old.id):
            by_date[d] = s
    return sorted(by_date.values(), key=lambda s: s.date)


def _gdal_env():
    import rasterio

    return rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
        GDAL_HTTP_MAX_RETRY="4",
        GDAL_HTTP_RETRY_DELAY="2",
        VSI_CACHE="TRUE",
    )


def _read_window(href: str, bounds, shape: tuple[int, int]) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds

    with rasterio.open(href) as ds:
        win = from_bounds(*bounds, transform=ds.transform)
        return ds.read(1, window=win, out_shape=shape, resampling=Resampling.nearest, boundless=False)


def _reflectance(raw: np.ndarray, s: Scene) -> np.ndarray:
    out = raw.astype(np.float32) * s.scale + s.offset
    out[raw == 0] = np.nan
    return out


def fetch(verbose: bool = True) -> dict:
    """Search, screen by SCL over the AOI, read the windows and write the NDVI stack snapshot."""
    bounds = aoi_utm()
    n = int(round(2 * AOI_HALF_M / PIXEL_M))
    shape = (n, n)
    scenes = search_scenes()
    if verbose:
        print(f"{len(scenes)} candidate dates on {MGRS_TILE}")
    kept: list[tuple[Scene, np.ndarray]] = []
    with _gdal_env():
        for s in scenes:
            try:
                scl = _read_window(s.hrefs["scl"], bounds, shape)
            except Exception as exc:  # one bad object should not stop the run
                if verbose:
                    print(f"  skip {s.id}: {exc}")
                continue
            clear = np.isin(scl, SCL_CLEAR)
            s.clear = float(clear.mean())
            if verbose:
                print(f"  {s.date} {s.id} tile cloud {s.cloud:5.1f}%  AOI clear {s.clear:5.1%}")
            if s.clear >= MIN_CLEAR_FRACTION:
                kept.append((s, clear))
        # Thin the dry season: one clearest scene per RABI_BIN_DAYS outside the monsoon.
        chosen: dict[object, tuple[Scene, np.ndarray]] = {}
        for s, clear in kept:
            monsoon = 6 <= s.date.month <= 10
            key = ("m", s.date) if monsoon else ("d", s.date.toordinal() // RABI_BIN_DAYS)
            old = chosen.get(key)
            if old is None or (s.clear, -s.cloud) > (old[0].clear, -old[0].cloud):
                chosen[key] = (s, clear)
        use = sorted(chosen.values(), key=lambda t: t[0].date)
        if verbose:
            print(f"{len(use)} scenes used after AOI screening and dry-season thinning")
        ndvi_l, ndwi_l, meta = [], [], []
        neg_share: list[float] = []
        best_rgb, best_key = None, None
        for s, clear in use:
            red = _reflectance(_read_window(s.hrefs["red"], bounds, shape), s)
            nir = _reflectance(_read_window(s.hrefs["nir"], bounds, shape), s)
            grn = _reflectance(_read_window(s.hrefs["green"], bounds, shape), s)
            with np.errstate(invalid="ignore", divide="ignore"):
                nd = (nir - red) / (nir + red)
                nw = (grn - nir) / (grn + nir)
            nd[~clear] = np.nan
            nw[~clear] = np.nan
            neg_share.append(float((red[clear] < -0.01).mean()) if clear.any() else 0.0)
            ndvi_l.append(nd)
            ndwi_l.append(nw)
            meta.append(
                {
                    "id": s.id,
                    "date": s.date.isoformat(),
                    "tile_cloud_pct": round(s.cloud, 2),
                    "aoi_clear_pct": round(100 * s.clear, 1),
                }
            )
            # Basemap: clearest scene in the rabi growing peak (Jan-Feb), ties by tile cloud.
            if s.date.month in (1, 2):
                key = (s.clear, -s.cloud)
                if best_key is None or key > best_key:
                    blue = _reflectance(_read_window(s.hrefs["blue"], bounds, shape), s)
                    best_rgb, best_key = (np.dstack([red, grn, blue]), s), key
    if not ndvi_l:
        raise RuntimeError("no usable Sentinel-2 scenes over the AOI")
    if max(neg_share) > 0.05:
        # Physically impossible: a wrong radiometric offset, not real data. Stop rather than
        # write a misleading map.
        raise RuntimeError(f"negative red reflectance on {max(neg_share):.0%} of clear pixels")
    ndvi = np.stack(ndvi_l)
    ndwi = np.stack(ndwi_l)

    def _i16(x: np.ndarray) -> np.ndarray:
        q = np.round(np.clip(x, -1, 1) * SCALE_I16)
        return np.where(np.isfinite(x), q, NODATA_I16).astype(np.int16)

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        STACK_PATH,
        ndvi=_i16(ndvi),
        ndwi_median=_i16(np.nanmedian(ndwi, axis=0)),
        dates=np.array([m["date"] for m in meta]),
        scene_ids=np.array([m["id"] for m in meta]),
        bounds_utm=np.array(bounds),
        epsg=np.array(UTM_EPSG),
        pixel_m=np.array(PIXEL_M),
    )
    return {"scenes": meta, "rgb": best_rgb, "bounds": bounds}


def load_stack(path: Path = STACK_PATH) -> dict:
    z = np.load(path)

    def _f(a: np.ndarray) -> np.ndarray:
        out = a.astype(np.float32) / SCALE_I16
        out[a == NODATA_I16] = np.nan
        return out

    return {
        "ndvi": _f(z["ndvi"]),
        "ndwi_median": _f(z["ndwi_median"]),
        "dates": [date.fromisoformat(str(d)) for d in z["dates"]],
        "scene_ids": [str(s) for s in z["scene_ids"]],
        "bounds_utm": tuple(float(v) for v in z["bounds_utm"]),
        "epsg": int(z["epsg"]),
    }


# --------------------------------------------------------------------------------------------
# Outputs: PNGs + JSON
# --------------------------------------------------------------------------------------------


def _warp_to_wgs84(arr: np.ndarray, bounds_utm, resampling) -> tuple[np.ndarray, tuple]:
    """Reproject (bands, H, W) from UTM to a lon/lat grid with the same pixel count."""
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject, transform_bounds

    bands, h, w = arr.shape
    src_t = from_bounds(*bounds_utm, w, h)
    ll = transform_bounds(f"EPSG:{UTM_EPSG}", "EPSG:4326", *bounds_utm)
    dst_t = from_bounds(*ll, w, h)
    out = np.full(arr.shape, np.nan, dtype=np.float32)
    for b in range(bands):
        reproject(
            arr[b].astype(np.float32),
            out[b],
            src_transform=src_t,
            src_crs=CRS.from_epsg(UTM_EPSG),
            dst_transform=dst_t,
            dst_crs=CRS.from_epsg(4326),
            resampling=resampling,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    return out, ll


def _bounds_json(ll, extra: dict) -> dict:
    w, s, e, n = (round(v, 6) for v in ll)
    return {
        "crs": "EPSG:4326",
        "west": w,
        "south": s,
        "east": e,
        "north": n,
        "leaflet_bounds": [[s, w], [n, e]],
        **extra,
    }


def write_truecolor(rgb: np.ndarray, bounds_utm, scene_meta: dict, out_dir: Path = BASEMAP_DIR) -> Path:
    from PIL import Image
    from rasterio.enums import Resampling

    warped, ll = _warp_to_wgs84(np.moveaxis(rgb, 2, 0), bounds_utm, Resampling.bilinear)
    img = np.moveaxis(warped, 0, 2)
    lo, hi = np.nanpercentile(img, 2), np.nanpercentile(img, 98)
    st = np.clip((img - lo) / (hi - lo), 0, 1) ** (1 / 1.2)
    alpha = np.isfinite(img).all(axis=2)
    rgba = np.dstack([np.nan_to_num(st) * 255, alpha * 255]).astype(np.uint8)
    out_dir.mkdir(parents=True, exist_ok=True)
    big = Image.fromarray(rgba, "RGBA").resize((rgba.shape[1] * 2, rgba.shape[0] * 2), Image.BICUBIC)
    png = out_dir / "samastipur_s2_truecolor.png"
    big.save(png, optimize=True)
    meta = _bounds_json(
        ll,
        {
            "image": "/basemap/samastipur_s2_truecolor.png",
            "width_px": big.width,
            "height_px": big.height,
            "native_resolution_m": PIXEL_M,
            "scene_id": scene_meta["id"],
            "scene_date": scene_meta["date"],
            "bands": "B04, B03, B02 (2-98 percentile stretch)",
            "label": "REAL (Sentinel-2 L2A imagery)",
        },
    )
    (out_dir / "samastipur_s2_truecolor.json").write_text(json.dumps(meta, indent=2) + "\n")
    return png


def write_class_overlay(codes: np.ndarray, bounds_utm, out_dir: Path = BASEMAP_DIR) -> Path:
    from PIL import Image
    from rasterio.enums import Resampling

    warped, ll = _warp_to_wgs84(codes[None].astype(np.float32), bounds_utm, Resampling.nearest)
    cw = np.nan_to_num(warped[0], nan=NO_DATA_CODE).astype(np.uint8)
    rgba = np.zeros((*cw.shape, 4), dtype=np.uint8)
    for spec in CLASSES.values():
        hexc = spec["color"].lstrip("#")
        rgba[cw == spec["code"]] = [int(hexc[i : i + 2], 16) for i in (0, 2, 4)] + [200]
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(rgba, "RGBA").resize((cw.shape[1] * 2, cw.shape[0] * 2), Image.NEAREST)
    png = out_dir / "samastipur_s2_crops.png"
    img.save(png, optimize=True)
    legend = _bounds_json(
        ll,
        {
            "image": "/basemap/samastipur_s2_crops.png",
            "width_px": img.width,
            "height_px": img.height,
            "alpha": 200,
            "classes": [
                {"key": k, "code": v["code"], "label": v["label"], "color": v["color"]}
                for k, v in CLASSES.items()
            ],
            "transparent": "no data (too few clear observations)",
            "label": "DERIVED classes from REAL Sentinel-2 NDVI; not validated against field labels",
        },
    )
    (out_dir / "samastipur_s2_crops.json").write_text(json.dumps(legend, indent=2) + "\n")
    return png


def write_shares(codes: np.ndarray, scenes: list[dict], bounds_utm, path: Path = SHARES_PATH) -> dict:
    from rasterio.warp import transform_bounds

    shares = class_shares(codes)
    total = codes.size
    nod = int((codes == NO_DATA_CODE).sum())
    px_ha = PIXEL_M * PIXEL_M / 1e4
    lat, lon = _site()
    out = {
        "labels": {"imagery": "REAL", "classes": "DERIVED"},
        "validation": "not validated against field labels",
        "source": {
            "catalogue": "Earth Search STAC v1 (earth-search.aws.element84.com/v1)",
            "reflectance": "DN * 0.0001 - 0.1 (scale and offset from the item raster:bands metadata)",
            "collection": COLLECTION,
            "mgrs_tile": MGRS_TILE,
            "bands": ["B02", "B03", "B04", "B08", "SCL"],
        },
        "aoi": {
            "site_lat": lat,
            "site_lon": lon,
            "size_km": 2 * AOI_HALF_M / 1000,
            "bounds_utm": [round(v, 1) for v in bounds_utm],
            "epsg": UTM_EPSG,
            "bounds_lonlat": [
                round(v, 6) for v in transform_bounds(f"EPSG:{UTM_EPSG}", "EPSG:4326", *bounds_utm)
            ],
            "pixels": int(total),
            "pixels_no_data": nod,
        },
        "period": {"start": YEAR_START, "end": YEAR_END},
        "shares": {k: round(v, 4) for k, v in shares.items()},
        "area_ha": {k: round(float((codes == v["code"]).sum()) * px_ha, 1) for k, v in CLASSES.items()},
        "classes": {k: v["label"] for k, v in CLASSES.items()},
        "method": {
            "index": "NDVI = (B08-B04)/(B08+B04) at 10 m; NDWI = (B03-B08)/(B03+B08)",
            "mask": f"SCL classes {list(SCL_CLEAR)} kept; scene used if AOI clear >= {MIN_CLEAR_FRACTION:.0%}",
            "thinning": f"monsoon (Jun-Oct) all usable scenes; other months clearest scene per {RABI_BIN_DAYS} days",
            "windows": {
                "kharif_peak": "Aug 1 - Oct 31",
                "rabi_peak": "Dec 15 - Mar 15",
                "inter_season_trough": "Nov 1 - Dec 20",
            },
            "thresholds": {
                "crop_peak": CROP_PEAK,
                "no_crop_peak": NO_CROP_PEAK,
                "never_green_max": GREEN_MAX,
                "trees_p10": TREE_LOW,
                "trees_median": TREE_MEDIAN,
                "water_ndwi_median": WATER_NDWI,
            },
            "rules": [
                "kharif_paddy: kharif peak >= crop_peak and rabi peak < no_crop_peak",
                "rabi_wheat_mustard: rabi peak >= crop_peak and kharif peak < no_crop_peak",
                "double_cropped: both peaks >= crop_peak with a trough >= 0.15 below the lower peak",
                "orchard_trees: year NDVI 10th percentile >= trees_p10 and median >= trees_median (overrides the above)",
                "fallow_builtup: year NDVI max < never_green_max",
                "water: median NDWI > water_ndwi_median and median NDVI < 0.1",
                "other_mixed: anything else (moderate or partial green-up, sugarcane, mixed pixels)",
                "no data: fewer than 3 clear looks or no look in either peak window",
            ],
            "limits": [
                "Season classes only: NDVI cannot separate paddy from kharif maize, or wheat from rabi maize, mustard or potato.",
                "Fallow land and built-up land are one class.",
                "Monsoon cloud leaves few clear kharif looks; a pixel's kharif peak may be missed.",
            ],
        },
        "scenes": scenes,
        "crop_mix_mapping": crop_mix_from_shares(shares),
    }
    path.write_text(json.dumps(out, indent=2) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Sentinel-2 crop-calendar map for the pilot site")
    ap.add_argument("--offline", action="store_true", help="reclassify the committed NDVI stack (no network)")
    ap.add_argument("--lat", type=float, help="AOI centre latitude (default: site_lat in constants.yaml)")
    ap.add_argument("--lon", type=float, help="AOI centre longitude (default: site_lon in constants.yaml)")
    args = ap.parse_args()
    if (args.lat is None) != (args.lon is None):
        ap.error("--lat and --lon go together")
    if args.lat is not None:
        if args.offline:
            ap.error("--lat/--lon need a fresh fetch, not --offline")
        global _SITE_OVERRIDE
        _SITE_OVERRIDE = (args.lat, args.lon)
    if args.offline:
        st = load_stack()
        scenes = json.loads(SHARES_PATH.read_text())["scenes"]
        bounds = st["bounds_utm"]
        ndvi, dates = st["ndvi"], st["dates"]
        ndwi = np.broadcast_to(st["ndwi_median"], ndvi.shape)
    else:
        res = fetch()
        scenes, bounds = res["scenes"], res["bounds"]
        st = load_stack()
        ndvi, dates = st["ndvi"], st["dates"]
        ndwi = np.broadcast_to(st["ndwi_median"], ndvi.shape)
        if res["rgb"] is not None:
            rgb, s = res["rgb"]
            meta = next(m for m in scenes if m["id"] == s.id)
            print("basemap:", write_truecolor(rgb, bounds, meta))
    codes, _ = classify(ndvi, dates, ndwi=ndwi)
    print("overlay:", write_class_overlay(codes, bounds))
    out = write_shares(codes, scenes, bounds)
    print(f"{len(scenes)} scenes; shares:")
    for k, v in out["shares"].items():
        print(f"  {k:20s} {v:6.1%}  ({out['area_ha'][k]} ha)")
    print("crop mix:", json.dumps(out["crop_mix_mapping"]))
    if not math.isclose(sum(out["shares"].values()), 1.0, abs_tol=1e-3):
        print("warning: shares do not sum to 1")


if __name__ == "__main__":
    main()
