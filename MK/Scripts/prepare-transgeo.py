#!/usr/bin/env python3

import argparse
from collections import defaultdict
from enum import Enum
import json
from io import StringIO
from pathlib import Path
from pprint import pp
from random import sample
import sys
from zipfile import ZipFile, Path as ZipPath
import re
import random

import numpy as np
from pyproj import Transformer, CRS
import rasterio
from rasterio.transform import AffineTransformer

def main():
    # Setup argument parser and parse program arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, help="Image manifest JSON file")
    parser.add_argument("aerial_root", type=Path, help="Aerial images root")
    parser.add_argument("ground_root", type=Path, help="Ground images root")
    parser.add_argument("geotiff", type=Path, help="GeoTiff")
    parser.add_argument("-a", "--panorama-aspect-ratio", type=float, default=2.0, help="Minimum aspect ratio for a ground image to be considered a panorama.")
    parser.add_argument("-p", "--max-positive-panoramas", type=int, default=2, help="Maximum number of positive panoramas per aerial image.")
    parser.add_argument("-d", "--distraction-proportion", type=float, default=1.0, help="Proportion of distractions (aerial images covering no panoramas) to keep. 1.0 is 100%%.")
    parser.add_argument("-t", "--train-proportion", type=float, default=0.5, help="Traintest split proportion. 1.0 is 100%% train.")
    parser.add_argument("-z", "--zip-prefix", type=Path, default=Path("mars-transgeo"), help="Prefix for all files added to zip.")
    parser.add_argument("-o", "--output", type=Path, default=Path("./mars-transgeo.zip"), help="Output filename")
    args = parser.parse_args()

    args.distraction_proportion = max(min(args.distraction_proportion, 1.0), 0)
    args.train_proportion = max(min(args.train_proportion, 1.0), 0)

    # Load input
    with open(args.manifest) as f:
        manifest = json.load(f)

    # Open geotiff
    src = rasterio.open(args.geotiff)
    crs = CRS.from_wkt(src.crs.wkt)

    # Create geographic (lon, lat) to projected (x, y) coordinate transformer
    t = Transformer.from_crs(crs.geodetic_crs, crs)
    t_inv = Transformer.from_crs(crs, crs.geodetic_crs)

    # Create geographic (lon, lat) to pixel coordinate transformer
    def t_px(lon, lat):
        x, y = t.transform(lon, lat)
        row, col = src.index(x, y)
        return np.array([col, row])
    
    def ground_aerial_offset_px(lon_ground, lat_ground, lon_aerial, lat_aerial):
        px_ground = t_px(lon_ground, lat_ground)
        px_aerial = t_px(lon_aerial, lat_aerial)
        return px_ground - px_aerial

    def remove_ground_image(ground_key):
        # Remove ground image item
        del manifest["ground"][ground_key]

        # Remove ground image from aerial image items
        for aerial_item in manifest["aerial"].values():
            if ground_key in aerial_item["positive"]:
                aerial_item["positive"].remove(ground_key)
            if ground_key in aerial_item["semi-positive"]:
                aerial_item["semi-positive"].remove(ground_key)

    def remove_aerial_image(aerial_key):
        # Remove aerial image item
        del manifest["aerial"][aerial_key]

        # Remove aerial image from ground image items
        for ground_item in manifest["ground"].values():
            if aerial_key in ground_item["positive"]:
                ground_item["positive"].remove(aerial_key)
            if aerial_key in ground_item["semi-positive"]:
                ground_item["semi-positive"].remove(aerial_key)

    # Remove duplicate images
    image_names = defaultdict(list)
    for image_key in list(manifest["aerial"].keys()) + list(manifest["ground"].keys()):
        image_name = Path(image_key).name
        image_names[image_name].append(image_key)
    
    for k, v in filter(lambda x: len(x[1]) > 1, image_names.items()):
        print(f"Removing {len(v) - 1} duplicate(s) of {k}")
        for k in v[1:]:
            if k in manifest["aerial"]:
                remove_aerial_image(k)
            elif k in manifest["ground"]:
                remove_ground_image(k)

    # Remove images with spaces in their names
    for image_key in list(manifest["aerial"].keys()) + list(manifest["ground"].keys()):
        name = Path(image_key).name
        if name.count(" "):
            print(f"Removing {image_key}")
            if image_key in manifest["aerial"]:
                remove_aerial_image(image_key)
            elif image_key in manifest["ground"]:
                remove_ground_image(image_key)
    
    # Remove non-panoramas
    for ground_key, _ in list(filter(lambda x: (x[1]["size"]["w"] / x[1]["size"]["h"]) < args.panorama_aspect_ratio, manifest["ground"].items())):
        print(f"Removing non-panorama {ground_key}")
        remove_ground_image(ground_key)

    # Enforce maximum panoramas per aerial
    for aerial_key, aerial_item in manifest["aerial"].items():
        if args.max_positive_panoramas and len(aerial_item["positive"]) > args.max_positive_panoramas:
            # Pick panoramas
            print(f"Picking panoramas for {aerial_key}")
            panorama_sample = sample(aerial_item["positive"], args.max_positive_panoramas)
            
            # Remove leftover panoramas
            for leftover in list(filter(lambda x: x not in panorama_sample, aerial_item["positive"])):
                print(f"Removing leftover panorama {leftover}")
                remove_ground_image(leftover)

            aerial_item["positive"] = panorama_sample

    # Remove distractions
    distractions = list(filter(lambda x: not manifest["aerial"][x]["positive"] and not manifest["aerial"][x]["semi-positive"], manifest["aerial"].keys()))
    remove_count = int((1 - args.distraction_proportion) * len(distractions))
    print(f"Removing {remove_count} distractions")
    for x in sample(distractions, remove_count):
        remove_aerial_image(x)

    # Remove ground images with less than 3 semi-positive aerial images
    for ground_key, _ in list(filter(lambda x: len(x[1]["semi-positive"]) < 3, manifest["ground"].items())):
        print(f"Removing {ground_key} for having less than 3 semi-positive aerial images")
        remove_ground_image(ground_key)

    # Create zip file
    with ZipFile(args.output, "w") as zf:
        # Add aerial / satellite images
        print("Adding satellite images to archive...")
        aerial_images = []
        for aerial_image in manifest["aerial"].keys():
            aerial_image_path = args.aerial_root / aerial_image
            if not aerial_image_path.exists():
                print(f"{aerial_image_path} does not exist, skipping")
                continue
            aerial_images.append(aerial_image)
            zf.write(aerial_image_path, str(args.zip_prefix / "Mars/satellite" / Path(aerial_image).name))

        # Aerial / satellite list
        zf.writestr(str(args.zip_prefix / "splits/Mars/satellite_list.txt"), "\n".join(map(lambda x: Path(x).name, aerial_images)))

        # Add ground / panorama images
        print("Adding ground images to archive...")
        ground_images = []
        for ground_image in manifest["ground"].keys():
            ground_image_path = args.ground_root / ground_image
            if not ground_image_path.exists():
                print(f"{ground_image_path} does not exist, skipping")
                continue
            ground_images.append(ground_image)
            zf.write(ground_image_path, str(args.zip_prefix / "Mars/panorama/" / Path(ground_image).name))
        
        # Create list of all sols in dataset of ground images
        sols = []
        for ground_image_sols in manifest["ground"].keys():
            sol_num = int(re.findall('_\d{4}_', ground_image_sols)[0][1:][:-1])
            sols.append(sol_num)

        # Randomly remove a set of sols for testing
        # Remove duplicate sols
        sols = [*set(sols)]
        sols_in_training = int(int(len(sols)) * args.train_proportion)
        print("Length of sols is {}".format(len(sols)))
        print("Number of sols in training set are {}".format(sols_in_training))
        random.shuffle(sols)
        sols = sols[:sols_in_training]

        # Crate the train set with the images that contain the sols in the list
        train_set = []
        test_set = []
        for ground_image_sols in manifest["ground"].keys():
            sol_num = int(re.findall('_\d{4}_', ground_image_sols)[0][1:][:-1])
            if sol_num in sols:
                train_set.append(ground_image_sols)
            else:
                test_set.append(ground_image_sols)

        # Splits
        # train_set = set(sample(ground_images, int(len(ground_images) * args.train_proportion)))
        # test_set = set(ground_images) - train_set

        print("The train set has {} images".format(len(train_set)))
        print("The test set has {} images".format(len(test_set)))

        # Train splits file
        with StringIO() as train_string:
            for ground_image in train_set:
                ground_name = Path(ground_image).name
                ground_item = manifest["ground"][ground_image]

                for positive_aerial in ground_item["positive"]:
                    positive_name = Path(positive_aerial).name
                    positive_item = manifest["aerial"][positive_aerial]
                    offset_px = ground_aerial_offset_px(*ground_item["location"].values(), *positive_item["center"].values())
                    train_string.write(f"{ground_name} {positive_name} {offset_px[1]} {offset_px[0]}")

                    if len(ground_item["semi-positive"]) < 3:
                        print(f"{ground_image} has less than 3 semi-positive aerial images, skipping")
                        continue
                    elif len(ground_item["semi-positive"]) > 3:
                        print(f"{ground_image} has more than 3 semi-positive aerial images")

                    for semi_positive_aerial in ground_item["semi-positive"][0:3]:
                        semi_positive_name = Path(semi_positive_aerial).name
                        semi_positive_item = manifest["aerial"][semi_positive_aerial]
                        offset_px = ground_aerial_offset_px(*ground_item["location"].values(), *semi_positive_item["center"].values())
                        train_string.write(f" {semi_positive_name} {offset_px[1]} {offset_px[0]}")

                    train_string.write("\n")

            zf.writestr(str(args.zip_prefix / "splits/Mars/same_area_balanced_train.txt"), train_string.getvalue())

        # Train splits file
        with StringIO() as test_string:
            for ground_image in test_set:
                ground_name = Path(ground_image).name
                ground_item = manifest["ground"][ground_image]

                for positive_aerial in ground_item["positive"]:
                    positive_name = Path(positive_aerial).name
                    positive_item = manifest["aerial"][positive_aerial]
                    offset_px = ground_aerial_offset_px(*ground_item["location"].values(), *positive_item["center"].values())
                    test_string.write(f"{ground_name} {positive_name} {offset_px[1]} {offset_px[0]}")
                
                    for semi_positive_aerial in ground_item["semi-positive"][0:3]:
                        semi_positive_name = Path(semi_positive_aerial).name
                        semi_positive_item = manifest["aerial"][semi_positive_aerial]
                        offset_px = ground_aerial_offset_px(*ground_item["location"].values(), *semi_positive_item["center"].values())
                        test_string.write(f" {semi_positive_name} {offset_px[1]} {offset_px[0]}")

                    test_string.write("\n")

            zf.writestr(str(args.zip_prefix / "splits/Mars/same_area_balanced_test.txt"), test_string.getvalue())

        # Add manifest
        print("Adding manifest to archive...")
        zf.writestr(str(args.zip_prefix / "manifest.json"), json.dumps(manifest, indent=4))

if __name__ == "__main__":
    main()
    
