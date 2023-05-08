#!/usr/bin/env python3

import argparse
from pathlib import Path
import json
from math import ceil

from cycler import cycler
from pyproj import Transformer, CRS
import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import png
import rasterio
from rasterio.transform import AffineTransformer
from rasterio.windows import Window

# Setup argument parser and parse args
parser = argparse.ArgumentParser()
parser.add_argument('geotiff_file', type=Path, help='Source GeoTIFF')
parser.add_argument('waypoint_file', type=Path, help='Waypoints .geojson')
parser.add_argument('-o', '--output', type=Path, default=Path('./tiles'), help='Tile output directory')
parser.add_argument('-ts', '--tile-size', type=int, default=640, help='Tile size')
parser.add_argument('-p', '--preview', action='store_true', help='Preview tiles')
parser.add_argument('-po', '--preview-only', action='store_true', help='Preview only. Implies -p.')
args = parser.parse_args()

if args.preview_only:
    args.preview = True

# Open image
src = rasterio.open(args.geotiff_file)
crs = CRS.from_wkt(src.crs.wkt)

# Origin
origin = (src.crs.data['lon_0'], src.crs.data['lat_0'])

# Create geographic (lon, lat) to projected (x, y) coordinate transformer
t = Transformer.from_crs(crs.geodetic_crs, crs)
t_inv = Transformer.from_crs(crs, crs.geodetic_crs)

# Create geographic (lon, lat) to pixel coordinate transformer
def t_px(lon, lat):
    x, y = t.transform(lon, lat)
    row, col = src.index(x, y)
    return col, row

# Get range of waypoint coordinates
with open(args.waypoint_file) as f:
    waypoints = json.load(f)['features']
lons, lats = zip(*list(map(lambda w: (w['properties']['lon'], w['properties']['lat']), waypoints)))
waypoints_px = list(map(lambda x: t_px(x[0], x[1]), zip(lons, lats)))
lon_range = (min(lons), max(lons))
lat_range = (min(lats), max(lats))

# Convert coordinate ranges to pixel coordinate ranges
col_range, row_range = zip(*(t_px(lon_range[0], lat_range[1]), t_px(lon_range[1], lat_range[0])))
col_range, row_range = (np.array(col_range, ndmin = 2), np.array(row_range, ndmin = 2))

# Tile
tile_size = args.tile_size
tile_spacing = tile_size // 2

# Round pixel coordinate ranges to even multiple of window spacing and re-center
def round_and_center(x):
    size = ceil((x[0, 1] - x[0, 0]) / tile_spacing) * tile_spacing
    difference = size - (x[0, 1] - x[0, 0])
    x[0, 1] = x[0, 0] + size
    x -= difference // 2
    return x

col_range = round_and_center(col_range)
row_range = round_and_center(row_range)

# Generate window coordinates
tile_x, tile_y = np.meshgrid(np.arange(col_range[0, 0], col_range[0, 1], tile_spacing), np.arange(row_range[0, 0], row_range[0, 1], tile_spacing))
tile_x, tile_y = tile_x.flatten(), tile_y.flatten()

if args.preview:
    # Preview window
    preview_win_center = (48144, 46448)
    preview_win_size = 16384 * 2
    preview_win = Window(preview_win_center[0] - (preview_win_size // 2), preview_win_center[1] - (preview_win_size // 2), preview_win_size, preview_win_size)

    # Create window pixel coordinates transformer
    t_preview_win = AffineTransformer(src.window_transform(preview_win))

    def t_px_preview_win(lon, lat):
        x, y = t.transform(lon, lat)
        row, col = t_preview_win.rowcol(x, y)
        return col, row

    # Plot preview window
    plt.imshow(src.read(1, window=preview_win), cmap='gray', vmin=0, vmax=255)
    ax = plt.gca()
    ax.autoscale(enable=False)

    # Plot waypoints
    waypoints_preview_win = list(map(lambda x: t_px_preview_win(x[0], x[1]), zip(lons, lats)))
    x_px, y_px = zip(*waypoints_preview_win)
    plt.plot(x_px, y_px, color='black', marker='o', markersize=5.0, markerfacecolor='white', markeredgecolor='black')

# Plot and save tiles
for i, v in enumerate(zip(tile_x, tile_y)):
    x, y = v

    # Skip if no waypoint is positive
    if not any(map(lambda w: (w[0] >= x and w[0] < (x + tile_size)) and (w[1] >= y and w[1] < (y + tile_size)), waypoints_px)):
        continue
    
    if not args.preview_only:
        # Save tile to file
        tile_window = Window(x, y, tile_size, tile_size)
        raster_data = src.read(1, window=tile_window)

        lon_range, lat_range = zip(*(t_inv.transform(*src.xy(y, x)), t_inv.transform(*src.xy(y + tile_size - 1, x + tile_size - 1))))
        lon_range, lat_range = sorted(lon_range), sorted(lat_range)
        
        filename = f'{i}_{lat_range[0]}_{lat_range[1]}_{lon_range[0]}_{lon_range[1]}.png'
        
        path = args.output
        if not path.exists():
            path.mkdir()
        path /= filename

        png.from_array(raster_data, 'L').save(path)
    
    if args.preview:
        # Plot tile
        x -= (preview_win_center[0] - (preview_win_size // 2))
        y -= (preview_win_center[1] - (preview_win_size // 2))

        ax.add_patch(Rectangle((x, y), tile_size, tile_size, fill = False, linewidth = 1, edgecolor = 'white'))
        plt.text(x, y, f'{i}', backgroundcolor = 'white')

if args.preview:
    plt.show()