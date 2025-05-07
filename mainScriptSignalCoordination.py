import os, sys, csv
from pathlib import Path

# SUMO / TraCI setup
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci
import simpla

# ────────── constants ──────────
SIM_TIME = 3600
PLATOON_DETECTION_DISTANCE = 150
MAPPING_FILE = "traffic_signal_mapping.json"   # generated earlier

northbound_edges = [
    "228470926", "1318032192", "1318032193",
    "1318032191#0", "228463837", "173228852",
]
southbound_edges = [
    "116044310#0", "173228850#0",
    "173228850#0-AddedOffRampEdge", "173228850#1",
    "228463846#2",
]
main_edges = set(northbound_edges + southbound_edges)

# ────────── helpers ──────────
def ask_scenario():
    print("1. Platoon Only\n2. Light Traffic\n3. Heavy Traffic")
    choice = input("Scenario 1/2/3: ").strip()
    names = {"1": "platoon_only_scenario",
             "2": "light_traffic_scenario",
             "3": "heavy_traffic_scenario"}
    return Path("generated_configs/traffic")/f"{names[choice]}.sumocfg"

def ask_gui():
    return "sumo-gui" if input("GUI? (y/n): ").lower().startswith("y") else "sumo"

def load_mapping(path):
    import json
    with open(path) as fh:
        return json.load(fh)

def derive_main_green(mapping):
    res = {}
    for tl in traci.trafficlight.getIDList():
        sig_on_main = {int(i) for i, info in mapping.get(tl, {}).items()
                       if info["edge_id"] in main_edges}
        if not sig_on_main:
            continue
        phases = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0].phases
        res[tl] = [idx for idx, ph in enumerate(phases)
                   if any(s < len(ph.state) and ph.state[s] in "gG" for s in sig_on_main)]
    return res

def edge_speed(edges):
    total = n = 0
    for e in edges:
        if e in traci.edge.getIDList():
            v = traci.edge.getLastStepVehicleNumber(e)
            total += traci.edge.getLastStepMeanSpeed(e) * v
            n += v
    return total / n if n else 0

# ────────── main run ──────────
def run_simulation():
    sumo_bin = ask_gui()
    cfg_path = ask_scenario()
    simpla_cfg = Path("generated_configs/simpla/simpla.xml")

    # connect
    traci.start([sumo_bin, "-c", str(cfg_path)])
    simpla.load(str(simpla_cfg))

    # mapping → phases
    mapping = load_mapping(MAPPING_FILE)
    MAIN_GREEN = derive_main_green(mapping)

    # TL timers
    phase_idx = {}
    phase_dur = {}
    phase_time = {}
    for tl in traci.trafficlight.getIDList():
        logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0]
        phase_idx[tl] = traci.trafficlight.getPhase(tl)
        phase_dur[tl] = logic.phases[phase_idx[tl]].duration
        phase_time[tl] = 0

    rows = []
    step = 0
    while step < SIM_TIME:
        step += 1
        traci.simulationStep()

        # ─── platoon‑aware extension ───
        for tl in phase_idx:
            phase_time[tl] += 1
            cur = phase_idx[tl]
            on_main_green = cur in MAIN_GREEN.get(tl, [])

            platoon_near = False
            for link_set in traci.trafficlight.getControlledLinks(tl):
                inc = link_set[0][0]      # incoming lane
                if traci.lane.getEdgeID(inc) not in main_edges:
                    continue
                for v in traci.lane.getLastStepVehicleIDs(inc):
                    vt = traci.vehicle.getTypeID(v).lower()
                    if "truck" in vt and "platoon" in vt:
                        dist = traci.lane.getLength(inc) - traci.vehicle.getLanePosition(v)
                        if dist <= PLATOON_DETECTION_DISTANCE:
                            platoon_near = True
                            break
                if platoon_near:
                    break

            if phase_time[tl] >= phase_dur[tl]:
                if not (on_main_green and platoon_near):
                    nxt = (cur + 1) % len(traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0].phases)
                    traci.trafficlight.setPhase(tl, nxt)
                    phase_idx[tl] = nxt
                    phase_dur[tl] = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl)[0].phases[nxt].duration
                    phase_time[tl] = 0
        # ─── metrics identical to working baseline ───
        veh_ids = traci.vehicle.getIDList()
        num_veh = len(veh_ids)
        avg_speed = (sum(traci.vehicle.getSpeed(v) for v in veh_ids) / num_veh) if num_veh else 0

        positions = []
        for e in northbound_edges:
            if e in traci.edge.getIDList():
                for ln in range(traci.edge.getLaneNumber(e)):
                    positions += [traci.vehicle.getLanePosition(v)
                                   for v in traci.lane.getLastStepVehicleIDs(f"{e}_{ln}")]
        positions.sort(reverse=True)
        gaps = [positions[i] - positions[i + 1] for i in range(len(positions) - 1)]
        avg_gap = sum(gaps)/len(gaps) if gaps else 0

        flow_nb = sum(traci.edge.getLastStepVehicleNumber(e) for e in northbound_edges if e in traci.edge.getIDList())
        flow_sb = sum(traci.edge.getLastStepVehicleNumber(e) for e in southbound_edges if e in traci.edge.getIDList())

        rows.append({
            "step": step,
            "num_vehicles": num_veh,
            "avg_intervehicular_distance": avg_gap,
            "northbound_flow": flow_nb,
            "southbound_flow": flow_sb,
            "northbound_speed": edge_speed(northbound_edges),
            "southbound_speed": edge_speed(southbound_edges),
            "average_speed": avg_speed,
        })

    traci.close()

    # write once at end
    Path("simulation_metrics").mkdir(exist_ok=True)
    out = Path("simulation_metrics/test.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"metrics saved → {out}")

if __name__ == "__main__":
    run_simulation()
