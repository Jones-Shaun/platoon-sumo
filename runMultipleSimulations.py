#!/usr/bin/env python3
"""
Runs every scenario in auto_generated_configs twice:
    fixed‑time (no coordination)
    platoon‑aware green‑extension (coordination)

Outputs one CSV per run in simulation_metrics/ with names like:
    ps4_np50_traffic_light_coordination.csv
    ps4_np50_traffic_light_nocoordination.csv
    files analyzed in simulation_metrics/metrics_analysis.ipynb
"""
import os, sys, re, csv, glob
from pathlib import Path

# SUMO libs
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
from sumolib import checkBinary
import traci, simpla

# constants
SIM_TIME = 3600
AUTO_DIR = Path("auto_generated_configs")
SIMPLA_CFG = AUTO_DIR / "simpla" / "simpla.xml"
OUT_DIR = Path("simulation_metrics"); OUT_DIR.mkdir(exist_ok=True)
PLATOON_DIST = 150      # m to stop‑line that triggers extension

NB_EDGES = [
    "228470926","1318032192","1318032193",
    "1318032191#0","228463837","173228852",
]
SB_EDGES = [
    "116044310#0","173228850#0",
    "173228850#0-AddedOffRampEdge","173228850#1",
    "228463846#2",
]
MAIN_EDGES = set(NB_EDGES + SB_EDGES)

# utilities
def scenario_cfgs():
    pat = str(AUTO_DIR / "config_ps*_np*_traffic_*_traffic.sumocfg")
    return sorted(glob.glob(pat))

def tag_from_cfg(cfg: Path) -> str:
    m = re.search(r"config_(ps\d+_np\d+_traffic_\w+)_traffic", cfg.stem)
    if not m:
        raise ValueError(f"Unexpected cfg name: {cfg.name}")
    return m.group(1)

def edge_speed(edges):
    tot = n = 0
    for e in edges:
        if e in traci.edge.getIDList():
            v = traci.edge.getLastStepVehicleNumber(e)
            tot += traci.edge.getLastStepMeanSpeed(e) * v
            n += v
    return tot / n if n else 0

# coordination helpers
def derive_main_green(main_edges):
    """Return {tl: [phase indices where main‑road is green]}"""
    res = {}
    for tl in traci.trafficlight.getIDList():
        phases = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0].phases
        sig_on_main = {
            i for i, link in enumerate(
                [l[0] for sub in traci.trafficlight.getControlledLinks(tl) for l in sub]
            )
            if traci.lane.getEdgeID(link) in main_edges
        }
        if not sig_on_main:
            continue
        res[tl] = [
            idx for idx, ph in enumerate(phases)
            if any(s < len(ph.state) and ph.state[s] in "gG" for s in sig_on_main)
        ]
    return res

def apply_coordination(MAIN_GREEN, phase_idx, phase_dur, phase_time):
    """green‑extension logic executed each step"""
    for tl in phase_idx:
        phase_time[tl] += 1
        on_main = phase_idx[tl] in MAIN_GREEN.get(tl, [])
        platoon_close = False
        for lset in traci.trafficlight.getControlledLinks(tl):
            inc = lset[0][0]
            if traci.lane.getEdgeID(inc) not in MAIN_EDGES:
                continue
            for v in traci.lane.getLastStepVehicleIDs(inc):
                vt = traci.vehicle.getTypeID(v).lower()
                if "truck" in vt and "platoon" in vt:
                    dist = traci.lane.getLength(inc) - traci.vehicle.getLanePosition(v)
                    if dist <= PLATOON_DIST:
                        platoon_close = True; break
            if platoon_close: break
        if phase_time[tl] >= phase_dur[tl]:
            if not (on_main and platoon_close):
                nxt = (phase_idx[tl] + 1) % len(
                    traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0].phases
                )
                traci.trafficlight.setPhase(tl, nxt)
                phase_idx[tl] = nxt
                phase_dur[tl] = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0].phases[nxt].duration
                phase_time[tl] = 0

# simulation core
def run_one(cfg_path: Path, csv_path: Path, use_coord: bool):
    traci.start([checkBinary("sumo"), "-c", str(cfg_path)])
    simpla.load(str(SIMPLA_CFG))

    # Traffic light timing initialization
    tl_ids = traci.trafficlight.getIDList()
    phase_idx = {tl: traci.trafficlight.getPhase(tl) for tl in tl_ids}
    phase_dur = {
        tl: traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0]
        .phases[phase_idx[tl]].duration for tl in tl_ids
    }
    phase_time = {tl: 0 for tl in tl_ids}

    MAIN_GREEN = derive_main_green(MAIN_EDGES) if use_coord else {}

    with open(csv_path, "w", newline="") as fh:
        writer = None
        for step in range(1, SIM_TIME + 1):
            traci.simulationStep()

            if use_coord:
                apply_coordination(MAIN_GREEN, phase_idx, phase_dur, phase_time)

            # metrics
            ids = traci.vehicle.getIDList()
            num = len(ids)
            spd_all = sum(traci.vehicle.getSpeed(v) for v in ids) / num if num else 0

            pos = []
            for e in NB_EDGES:
                if e in traci.edge.getIDList():
                    for ln in range(traci.edge.getLaneNumber(e)):
                        pos += [
                            traci.vehicle.getLanePosition(v)
                            for v in traci.lane.getLastStepVehicleIDs(f"{e}_{ln}")
                        ]
            pos.sort(reverse=True)
            gaps = [pos[i] - pos[i + 1] for i in range(len(pos) - 1)]
            avg_gap = sum(gaps) / len(gaps) if gaps else 0

            flow_nb = sum(traci.edge.getLastStepVehicleNumber(e) for e in NB_EDGES if e in traci.edge.getIDList())
            flow_sb = sum(traci.edge.getLastStepVehicleNumber(e) for e in SB_EDGES if e in traci.edge.getIDList())

            row = {
                "step": step, "num_vehicles": num, "avg_gap_nb": avg_gap,
                "flow_nb": flow_nb, "flow_sb": flow_sb,
                "spd_nb": edge_speed(NB_EDGES),
                "spd_sb": edge_speed(SB_EDGES),
                "spd_all": spd_all,
            }
            if writer is None:
                writer = csv.DictWriter(fh, fieldnames=row.keys())
                writer.writeheader()
            writer.writerow(row)
    traci.close()


def main():
    if not SIMPLA_CFG.exists():
        print("Missing Simpla config:", SIMPLA_CFG); sys.exit(1)

    for cfg_file in scenario_cfgs():
        tag = tag_from_cfg(Path(cfg_file))
        for coord_flag, suffix in ((True, "coordination"), (False, "nocoordination")):
            out_csv = OUT_DIR / f"{tag}_{suffix}.csv"
            mode = "coord" if coord_flag else "baseline"
            print(f"Running {tag}  [{mode}] …")
            run_one(Path(cfg_file), out_csv, use_coord=coord_flag)
            print(f"  → saved {out_csv}")

if __name__ == "__main__":
    main()
