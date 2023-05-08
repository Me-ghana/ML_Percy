#!/usr/bin/env python3

import argparse
from pathlib import Path
import json
import sys

def main():
    # Setup argument parser and parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('waypoints_file', type=Path, help='Rover waypoints .geojson')
    parser.add_argument('threshold', type=float, help='Distances between waypoints below this value are considered close')
    parser.add_argument('-s', '--summary', action='store_true', help='Output summary of waypoint groups')
    parser.add_argument('-i', '--indent', type=int, default=None, help='Output JSON indenting')
    parser.add_argument('-p', '--plot', action='store_true', help='Plot waypoint groups')
    parser.add_argument('-gs', '--group-size', type=int, default=2, help='Minimum group size to plot')
    
    args = parser.parse_args()

    # Parse waypoints
    with open(args.waypoints_file) as f:
        waypoints = json.load(f)['features']

    # Group waypoints that are close together
    groups = []
    current_group = []
    threshold = args.threshold

    dist_m = lambda w: float(w['properties']['dist_m'])

    for waypoint in waypoints:
        # If current group is empty, current waypoint is always added to current group
        if not current_group:
            current_group.append(waypoint)
            continue
        
        # If distance between current and last waypoint is less than the threshold, add current waypoint
        # to current group. Otherwise, add current waypoint to new group
        if dist_m(waypoint) <= threshold:
            current_group.append(waypoint)
        else:
            groups.append(current_group)
            current_group = []
            current_group.append(waypoint)

    # Sort groups by size in descending order (largest group first)
    groups = list(reversed(sorted(groups, key=len)))

    # Summarize groups (count, sol range) if specified, and print output
    if args.summary:
        groups_summary = list(map(lambda x: {'count': len(x), 'sol-range': (x[0]['properties']['sol'], x[-1]['properties']['sol'])}, groups))
        print(json.dumps(groups_summary, indent=args.indent))
    else:
        print(json.dumps(groups, indent=args.indent))

    # Plot if specified
    if not args.plot:
        return
    
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("Error importing matplotlib. Aborting.", file=sys.stderr)
        sys.exit(1)

    fig, ax = plt.subplots()

    # Plot path
    lons = list(map(lambda w: w["properties"]["lon"], waypoints))
    lats = list(map(lambda w: w["properties"]["lat"], waypoints))
    ax.plot(lons, lats, color="black")

    # Label sols
    for waypoint in waypoints:
        lon = waypoint["properties"]["lon"]
        lat = waypoint["properties"]["lat"]
        sol = waypoint["properties"]["sol"]
        ax.annotate(sol, (lon, lat), size=12)

    # Plot groups
    for group in groups:
        lons = list(map(lambda w: w["properties"]["lon"], group))
        lats = list(map(lambda w: w["properties"]["lat"], group))
        if len(group) > args.group_size:
            ax.plot(lons, lats, marker='o', linewidth=5, markersize=10)

    plt.show()

if __name__ == '__main__':
    main()