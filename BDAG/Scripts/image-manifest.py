#!/usr/bin/env python3

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

from PIL import Image

# Setup argument parser and parse program arguments
parser = argparse.ArgumentParser()
parser.add_argument('aerial_image_directory', type=Path, help='Directory containing labelled aerial images')
parser.add_argument('ground_image_directory', type=Path, help='Root of directory tree containing labelled ground images')
parser.add_argument('-o', '--output', type=Path, default=Path('./image-manifest.json'), help='Output JSON file')

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
aerial_label_re = re.compile(r"(?P<id>\d+)_(?P<center_lon>-?\d+\.\d+)_(?P<center_lat>-?\d+\.\d+)_(?P<min_pos_lon>-?\d+\.\d+)_(?P<max_pos_lat>-?\d+\.\d+)_(?P<max_pos_lon>-?\d+\.\d+)_(?P<min_pos_lat>-?\d+\.\d+)_(?P<min_semi_lon>-?\d+\.\d+)_(?P<max_semi_lat>-?\d+\.\d+)_(?P<max_semi_lon>-?\d+\.\d+)_(?P<min_semi_lat>-?\d+\.\d+)\.png")
ground_label_re = re.compile(r"LAT_(?P<lat>-?\d+\.\d+)LONG_(?P<lon>-?\d+\.\d+).*\.png")
size_re = re.compile(r"\d+x\d+")

recursive_default_dict = lambda: defaultdict(recursive_default_dict)
manifest = recursive_default_dict()

# Get labelled aerial images
for aerial_image_path in aerial_image_directory.glob('*.png'):
    name = aerial_image_path.name

    # Check if label format is correct
    match = aerial_label_re.match(name)
    if not match:
        print(f"{aerial_image_path} does not match aerial image label format. Skipping image.", file=sys.stderr)
        continue

    groups = match.groupdict()
    aerial_item = manifest["aerial"][str(aerial_image_path.relative_to(aerial_image_directory))]
    aerial_item["id"] = groups["id"]
    aerial_item["size"] = dict(zip(("w", "h"), Image.open(aerial_image_path).size))
    aerial_item["center"] = {"lon": groups["center_lon"], "lat": groups["center_lat"]}
    aerial_item["positive-boundary"] = [
        {"lon": groups["min_pos_lon"], "lat": groups["max_pos_lat"]},
        {"lon": groups["max_pos_lon"], "lat": groups["min_pos_lat"]}
    ]
    aerial_item["semi-positive-boundary"] = [
        {"lon": groups["min_semi_lon"], "lat": groups["max_semi_lat"]},
        {"lon": groups["max_semi_lon"], "lat": groups["min_semi_lat"]}
    ]
    aerial_item["positive"] = []
    aerial_item["semi-positive"] = []

is_positive = lambda ground_item, aerial_item: (aerial_item["positive-boundary"][0]["lon"] <= ground_item["location"]["lon"] <= aerial_item["positive-boundary"][1]["lon"]) and (aerial_item["positive-boundary"][1]["lat"] <= ground_item["location"]["lat"] <= aerial_item["positive-boundary"][0]["lat"])
is_semi_positive = lambda ground_item, aerial_item: (aerial_item["semi-positive-boundary"][0]["lon"] <= ground_item["location"]["lon"] <= aerial_item["semi-positive-boundary"][1]["lon"]) and (aerial_item["semi-positive-boundary"][1]["lat"] <= ground_item["location"]["lat"] <= aerial_item["semi-positive-boundary"][0]["lat"])
    
# Get labelled ground images
for ground_image_path in ground_image_directory.glob('**/*/*.png'):   
    # Check if label format is correct
    name = ground_image_path.name
    match = ground_label_re.match(name)
    if not match:
        print(f"{aerial_image_path} does not match aerial image label format. Skipping image.", file=sys.stderr)
        continue

    groups = match.groupdict()
    ground_key = str(ground_image_path.relative_to(ground_image_directory))
    ground_item = manifest["ground"][ground_key]
    ground_item["size"] = dict(zip(("w", "h"), Image.open(ground_image_path).size))
    ground_item["location"] = {"lon": groups["lon"], "lat": groups["lat"]}
    ground_item["positive"] = []
    ground_item["semi-positive"] = []

    # Find positive and semi-positive images
    for k, aerial_item in manifest["aerial"].items():
        if is_positive(ground_item, aerial_item):
            ground_item["positive"].append(k)
            aerial_item["positive"].append(ground_key)
        elif is_semi_positive(ground_item, aerial_item):
            ground_item["semi-positive"].append(k)
            aerial_item["semi-positive"].append(ground_key)

with open(args.output, "w") as f:
    json.dump(manifest, f, indent=4)