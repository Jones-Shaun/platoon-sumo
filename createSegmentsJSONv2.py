"""
createSegmentsJSONv2.py  ("Create Segments JSON v2")

Runs a **very short** SUMO session, queries every traffic‑light, and
records which signal index controls which incoming lane / edge.  The
mapping is written to **traffic_signal_mapping.json** and reused by the
platoon‑aware coordination scripts.

Key simplification v2
---------------------
* **No command‑line config required.** The script always loads the
  network at *osm/osm.sumocfg* relative to the project root.  Pass
  `--config` only if you really need a different file.
* Keeps a `--nogui` switch for convenience.

Typical call (batch‑friendly):
    python createSegmentsJSONv2.py --nogui
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure SUMO Python tools are importable
# ---------------------------------------------------------------------------
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    raise EnvironmentError(
        "SUMO_HOME not set. Please set the environment variable to your SUMO installation root."
    )

import traci  # noqa: E402  pylint: disable=wrong-import-position

###############################################################################
# Helper functions                                                            #
###############################################################################

def start_sumo(config_file: str, use_gui: bool) -> None:
    """Launch SUMO via TraCI; returns once connection is ready."""
    binary = "sumo-gui" if use_gui else "sumo"
    traci.start([binary, "-c", config_file], port=0)  # port 0 = auto pick


def build_signal_mapping() -> dict[str, dict[int, dict[str, str]]]:
    """Collect signal‑index → incoming lane / edge mapping for every TL."""
    mapping: dict[str, dict[int, dict[str, str]]] = {}

    for tl_id in traci.trafficlight.getIDList():
        mapping[tl_id] = {}

        # getControlledLinks: List[List[Tuple(inLane, outLane, via)]]
        links_nested = traci.trafficlight.getControlledLinks(tl_id)
        flat_links = [lnk for sub in links_nested for lnk in sub]

        for idx, lnk in enumerate(flat_links):
            in_lane = lnk[0]
            try:
                edge_id = traci.lane.getEdgeID(in_lane)
            except traci.TraCIException:
                edge_id = "UNKNOWN"

            mapping[tl_id][idx] = {
                "incoming_lane": in_lane,
                "edge_id": edge_id,
            }

    return mapping

###############################################################################
# Main routine                                                                #
###############################################################################

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create traffic_signal_mapping.json for the current network",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        default=str(Path("osm") / "osm.sumocfg"),
        help="SUMO *.sumocfg file to load (default: osm/osm.sumocfg)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="traffic_signal_mapping.json",
        help="Output JSON filename",
    )
    parser.add_argument(
        "--nogui",
        action="store_true",
        help="Run SUMO without GUI (recommended for batch)",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Launch SUMO, build mapping, save JSON
    # ------------------------------------------------------------------
    start_sumo(args.config, use_gui=not args.nogui)
    mapping = build_signal_mapping()

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=4)

    print(f"Saved mapping for {len(mapping)} traffic‑lights → {args.output}")

    traci.close()


if __name__ == "__main__":
    main()
