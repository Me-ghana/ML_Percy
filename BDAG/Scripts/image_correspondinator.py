#!/usr/bin/env python3

import argparse
from collections import defaultdict
from glob import glob
import json
from pathlib import Path
import re
import sys

# Setup argument parser and parse program arguments
parser = argparse.ArgumentParser()
parser.add_argument('aerial_image_directory', type=Path, help='Directory containing labelled aerial images')
parser.add_argument('ground_image_directory', type=Path, help='Root of directory tree containing labelled ground images')
parser.add_argument('-o', '--output', type=Path, default=Path('./image-correspondences.json'), help='Output JSON file')

args = parser.parse_args()
aerial_image_directory = args.aerial_image_directory
ground_image_directory = args.ground_image_directory

# Check arguments
if not aerial_image_directory.is_dir():
    print("Specified aerial image directory path does not exist or is not a directory", file=sys.stderr)
    sys.exit(1)
if not ground_image_directory.is_dir():
    print("Specified ground image directory path does not exist or is not a directory", file=sys.stderr)
    sys.exit(1)

# Compile regular expressions matching label formats
aerial_label_re = re.compile(r"(?P<tile_id>\d+)_(?P<min_lat>-?\d+\.\d+)_(?P<max_lat>-?\d+\.\d+)_(?P<min_lon>-?\d+\.\d+)_(?P<max_lon>-?\d+\.\d+)\.png")
ground_label_re = re.compile(r"(?P<lat>-?\d+\.\d+)_(?P<lon>-?\d+\.\d+)_.*\.png")
size_re = re.compile(r"\d+x\d+")

# Get labelled aerial images
aerial_images = {}
for aerial_image_path in aerial_image_directory.glob('*.png'):
    name = aerial_image_path.name

    # Check if label format is correct
    match = aerial_label_re.match(name)
    if match:
        groups = match.groupdict()
        aerial_images[str(aerial_image_path.relative_to(aerial_image_directory))] = groups
    else:
        print(f"{aerial_image_path} does not match aerial image label format. Skipping image.", file=sys.stderr)

# Get labelled ground images
ground_images = {}
for ground_image_path in ground_image_directory.glob('**/labelled/*/*.png'):
    # Check if image is contained in directory specifying its size
    size = ground_image_path.parts[-2]
    if not size_re.match(size):
        print(f"{ground_image_path} is not contained in directory specifying size. Skipping image.", file=sys.stderr)
        continue
    
    # Check if label format is correct
    name = ground_image_path.name
    match = ground_label_re.match(name)
    if match:
        groups = match.groupdict()
        groups["size"] = size
        ground_images[str(ground_image_path.relative_to(ground_image_directory))] = groups
    else:
        print(f"{ground_image_path} does not match ground image label format. Skipping image.", file=sys.stderr)

# Correlate images
recursive_default_dict = lambda: defaultdict(recursive_default_dict)
image_correspondences = recursive_default_dict()

# Images correspond if ground lon, lat coordinates are within aerial coordinates
check_image_correspondence = lambda ground, aerial: (aerial['min_lon'] <= ground['lon'] <= aerial['max_lon']) and (aerial['min_lat'] <= ground['lat'] <= aerial['max_lat'])

# Loop through aerial images
for aerial_image_path, aerial_image_values in aerial_images.items():
    image_correspondences[aerial_image_path]["tile-id"] = aerial_image_values["tile_id"]
    image_correspondences[aerial_image_path]["size"] = "640x640" # Hardcoded for now
    image_correspondences[aerial_image_path]["min-lon"] = aerial_image_values["min_lon"]
    image_correspondences[aerial_image_path]["max_lon"] = aerial_image_values["max_lon"]
    image_correspondences[aerial_image_path]["min-lat"] = aerial_image_values["min_lat"]
    image_correspondences[aerial_image_path]["max_lat"] = aerial_image_values["max_lat"]
    image_correspondences[aerial_image_path]["ground-images"] = recursive_default_dict()

    # Loop through ground images
    for ground_image_path, ground_image_values in ground_images.items():
        # Check if ground image corresponds to aerial image
        if check_image_correspondence(ground_image_values, aerial_image_values):
            image_correspondences[aerial_image_path]["ground-images"][ground_image_values["size"]][ground_image_path]["lon"] = ground_image_values["lon"]
            image_correspondences[aerial_image_path]["ground-images"][ground_image_values["size"]][ground_image_path]["lat"] = ground_image_values["lon"]

with open(args.output, "w") as f:
    json.dump(image_correspondences, f, indent=4)