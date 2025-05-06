"""
This script iterates through generated SUMO configuration files,
runs a simulation for each using TraCI, applies platoon-aware
traffic signal coordination, and saves metrics for each scenario.

It requires the traffic_signal_mapping.json file and the
auto_generated_configs directory with scenario files to exist.

Fixes TypeError: start() got an unexpected keyword argument 'proc'.
"""
import sys
import os
import json
import csv
# Removed subprocess as it's no longer needed for startup
# import subprocess
from pathlib import Path
import re # Import regex for parsing filenames

# This block tries to add the SUMO tools directory to the system path.
# It's important for finding traci if it's not installed directly in the environment.
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))

# Import necessary libraries
import traci
# simpla for platooning functionality (assuming it's used in the simulation)
import simpla


# Important details from configuration files:
# One simulation step is 1 second
# Simulation time is 3600 seconds (1 hour)
SIM_TIME = 100  # Total simulation time in seconds (and steps)

# Define the edges that make up the main routes
# These are used for calculating flow and speed metrics on specific parts of the network
northbound_edges = [
    "228470926",  # First
    "1318032192", # Second
    "1318032193", # Third
    "1318032191#0", # Fourth
    "228463837", # Fifth
    "173228852"   # Last
]

southbound_edges = [
    "116044310#0",  # First
    "173228850#0", # Second
    "173228850#0-AddedOffRampEdge", # Third
    "173228850#1", # Fourth
    "228463846#2", # Last
]

# --- Traffic Signal Control Variables ---
# Define the distance threshold for platoon truck detection (in meters)
PLATOON_DETECTION_DISTANCE = 150 # Example: 150 meters - adjust as needed

# --- Define which phases are 'main road green' for each traffic light ---
# This is CRUCIAL and depends entirely on your specific SUMO network's traffic light programs.
# You need to inspect your .net.xml or the traffic_signal_mapping.json file
# to determine which phase indices correspond to the main road having a green light.
# Example structure: {'traffic_light_id': [list of main_road_green_phase_indices]}
# Replace 'your_tl_id_1', 'your_tl_id_2' with the actual IDs from your network.
# Replace the phase indices [0, 2] and [1] with the correct indices for your programs.
# ** YOU MUST POPULATE THIS DICTIONARY BASED ON YOUR NETWORK AND MAPPING FILE **
MAIN_ROAD_GREEN_PHASES = {
    # Example: Assuming traffic light 'my_traffic_light_1' has main road green on phases 0 and 2
    # 'my_traffic_light_1': [0, 2],
    # Example: Assuming traffic light 'my_traffic_light_2' has main road green on phase 1
    # 'my_traffic_light_2': [1],
    # Add all your main road traffic lights and their green phase indices here:
}

# Define the filename for the traffic signal mapping JSON file
TRAFFIC_SIGNAL_MAPPING_FILE = "traffic_signal_mapping.json"

# Dictionary to store the loaded traffic signal mapping from the JSON file
traffic_signal_mapping = {}

# --- End Traffic Signal Control Variables ---

# --- Simulation Output Directories ---
GENERATED_CONFIGS_DIR = Path.cwd() / "auto_generated_configs"
SIMULATION_METRICS_BASE_DIR = Path.cwd() / "simulation_metrics"

# Ensure the base metrics directory exists
SIMULATION_METRICS_BASE_DIR.mkdir(parents=True, exist_ok=True)
# --- End Simulation Output Directories ---


def load_traffic_signal_mapping():
    """
    Loads the traffic signal mapping from the JSON file.
    Exits if the file is not found or invalid.
    """
    global traffic_signal_mapping
    try:
        with open(TRAFFIC_SIGNAL_MAPPING_FILE, 'r') as f:
            traffic_signal_mapping = json.load(f)
        print(f"Traffic signal mapping loaded from '{TRAFFIC_SIGNAL_MAPPING_FILE}'")
    except FileNotFoundError:
        print(f"Error: Traffic signal mapping file '{TRAFFIC_SIGNAL_MAPPING_FILE}' not found.")
        print("Please run a script to generate this file first (e.g., generateVehicleConfigs.py with JSON generation enabled or a dedicated script).")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from '{TRAFFIC_SIGNAL_MAPPING_FILE}': {e}")
        print("Please check the file content for valid JSON format.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while loading mapping file: {e}")
        sys.exit(1)


def run_single_simulation(sumo_config_path: Path, sumo_binary: str, scenario_output_dir: Path):
    """
    Runs a single SUMO simulation with the given configuration, applies
    traffic signal coordination, and saves metrics to the specified directory.

    Args:
        sumo_config_path (Path): The path to the SUMO configuration file (.sumocfg).
        sumo_binary (str): The SUMO executable to use ('sumo' or 'sumo-gui').
        scenario_output_dir (Path): The directory to save simulation metrics for this scenario.
    """
    print(f"Running simulation for: {sumo_config_path.name}")

    # Ensure the output directory for this scenario exists
    scenario_output_dir.mkdir(parents=True, exist_ok=True)
    metrics_output_file = scenario_output_dir / "simulation_metrics.csv"

    # Construct the SUMO command
    sumo_cmd = [sumo_binary, "-c", str(sumo_config_path)]

    # --- Start SUMO Simulation ---
    try:
        # Use traci.start to launch SUMO and connect.
        # Removed subprocess.Popen and 'proc' argument as it caused compatibility issues.
        traci.start(sumo_cmd, port=0) # Use port 0 to let SUMO choose a free port
        # print("TraCI connection established.") # Keep this line if you want confirmation per run

    except FileNotFoundError:
        print(f"\nError: SUMO binary '{sumo_binary}' not found.")
        print("Please ensure that SUMO is installed and the directory containing")
        print(f"'{sumo_binary}' is in your system's PATH environment variable,")
        print("or that SUMO_HOME is set correctly and its 'bin' directory is in PATH.")
        return # Skip this simulation scenario
    except traci.TraCIException as e:
        print(f"\nError starting SUMO or connecting via TraCI for {sumo_config_path.name}: {e}")
        print("Please ensure SUMO is installed and SUMO_HOME is set correctly.")
        print("Check your SUMO configuration file and network file for errors.")
        return # Skip this simulation scenario
    except Exception as e:
        print(f"\nAn unexpected error occurred during SUMO startup for {sumo_config_path.name}: {e}")
        return # Skip this simulation scenario
    # --- End Start SUMO Simulation ---


    # Initialize Simpla for platooning (assuming simpla.xml is in a standard location relative to sumocfg)
    # The simpla.xml path needs to be relative to the SUMO config file or an absolute path
    # Assuming simpla.xml is in auto_generated_configs/simpla/simpla.xml
    simpla_config_path = GENERATED_CONFIGS_DIR / "simpla" / "simpla.xml"
    if not simpla_config_path.exists():
         print(f"Warning: Simpla configuration file not found at {simpla_config_path}. Simpla will not be loaded.")
         simpla_loaded = False
    else:
        try:
            # simpla.load expects a string path
            simpla.load(str(simpla_config_path))
            # print("Simpla loaded successfully.") # Keep this line if you want confirmation per run
            simpla_loaded = True
        except Exception as e:
            print(f"Error loading Simpla configuration for {sumo_config_path.name}: {e}")
            print("Warning: Simpla might not be fully functional for this simulation.")
            simpla_loaded = False


    # --- Traffic Signal Control Initialization ---
    # Get the IDs of all traffic lights in the simulation
    traffic_light_ids = traci.trafficlight.getIDList()
    # print(f"\nFound traffic lights: {traffic_light_ids}") # Keep this line if you want confirmation per run

    # Initialize phase tracking for each traffic light and populate TRAFFIC_LIGHT_PROGRAMS
    current_phase_index = {}
    current_phase_duration = {}
    time_in_current_phase = {}
    TRAFFIC_LIGHT_PROGRAMS = {} # Local dictionary for this simulation run
    controlled_traffic_lights = [] # List of TLs we will actually control

    for tl_id in traffic_light_ids:
        # Check if this traffic light is in our MAIN_ROAD_GREEN_PHASES dictionary
        if tl_id not in MAIN_ROAD_GREEN_PHASES:
            # print(f"Warning: Traffic light '{tl_id}' not found in MAIN_ROAD_GREEN_PHASES. Skipping platoon-aware control for this TL.")
            continue # Skip this traffic light if not configured for platoon control

        # Get the first logic program defined for this traffic light
        try:
            logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl_id)[0]
            # Store phase durations
            TRAFFIC_LIGHT_PROGRAMS[tl_id] = [phase.duration for phase in logic.phases]

            # Get the initial phase index
            current_phase_index[tl_id] = traci.trafficlight.getPhase(tl_id)
            # Ensure the initial phase index is valid for the stored program
            if current_phase_index[tl_id] >= len(TRAFFIC_LIGHT_PROGRAMS[tl_id]):
                 print(f"Warning: Initial phase index {current_phase_index[tl_id]} for TL '{tl_id}' is out of bounds. Resetting to 0.")
                 current_phase_index[tl_id] = 0 # Reset to the first phase if out of bounds

            # Set the initial current phase duration and timer
            current_phase_duration[tl_id] = TRAFFIC_LIGHT_PROGRAMS[tl_id][current_phase_index[tl_id]]
            time_in_current_phase[tl_id] = 0 # Start timer for the current phase
            controlled_traffic_lights.append(tl_id) # Add to the list of TLs to control

        except IndexError:
            print(f"Warning: Traffic light '{tl_id}' has no defined logic programs. Skipping traffic signal control for this TL.")
            continue # Skip this traffic light


    # --- End Traffic Signal Control Initialization ---

    # Open the metrics CSV file for writing
    with open(metrics_output_file, mode='w', newline='') as csv_file:
        fieldnames = [
            "step", "num_vehicles", "avg_intervehicular_distance_northbound",
            "northbound_flow", "southbound_flow", "northbound_speed",
            "southbound_speed", "average_speed_all_vehicles"
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader() # Write the header row

        try:
            step = 0
            # Simulation loop
            while step < SIM_TIME:
                step += 1
                traci.simulationStep()  # Advance the simulation by one step

                # --- Traffic Signal Control Logic (Platoon-Aware Green Extension) ---
                # Only apply control logic to traffic lights we are configured to control
                for tl_id in controlled_traffic_lights:
                    # Increment time spent in the current phase
                    time_in_current_phase[tl_id] += 1

                    # Get the current phase index for this traffic light
                    current_phase = current_phase_index[tl_id]

                    # Check if the current phase is a designated 'main road green' phase for this TL
                    is_currently_main_road_green = current_phase in MAIN_ROAD_GREEN_PHASES.get(tl_id, [])

                    # --- Platoon Detection Logic for Main Road Approaches ---
                    platoon_truck_approaching_main_road = False
                    # Get the links (connections) controlled by this traffic light
                    controlled_links = traci.trafficlight.getControlledLinks(tl_id)

                    # Iterate through the links to find vehicles on incoming lanes
                    for link_set in controlled_links:
                        for link in link_set:
                            # A link is a tuple: (incoming_lane, outgoing_lane, via_lane)
                            incoming_lane = link[0]
                            if incoming_lane:  # Ensure incoming lane exists
                                 # Use the loaded mapping data to check if this lane's edge is a main road edge
                                 # Note: link_set.index(link) gets the index of the link within its sublist.
                                 # This index corresponds to the signal index for this link.
                                 try:
                                     link_index = link_set.index(link)
                                     # Ensure tl_id and link_index exist as keys in the mapping
                                     lane_info = traffic_signal_mapping.get(tl_id, {}).get(str(link_index))
                                     edge_id_of_lane = lane_info.get("edge_id") if lane_info else None
                                 except ValueError:
                                     # This can happen if the link structure is unexpected
                                     # print(f"Warning: Could not find index for link {link} in link_set for TL {tl_id}. Cannot determine edge via mapping.")
                                     edge_id_of_lane = None # Cannot determine edge via mapping
                                 except AttributeError:
                                     # This can happen if lane_info is None or doesn't have 'edge_id'
                                     # print(f"Warning: Mapping data for TL {tl_id}, Signal {link_index} is incomplete. Cannot determine edge via mapping.")
                                     edge_id_of_lane = None

                                 # Fallback to direct edge check if mapping is missing or incomplete
                                 if edge_id_of_lane is None or edge_id_of_lane == "N/A (Lane not found)":
                                    try:
                                         edge_id_of_lane = traci.lane.getEdgeID(incoming_lane)
                                    except traci.TraCIException:
                                         # print(f"Warning: Could not get edge ID for lane '{incoming_lane}' via TraCI.")
                                         edge_id_of_lane = None # Still couldn't get edge ID

                                 # Check if the lane's edge is on one of the defined main‑road approaches
                                 is_on_main_road_approach = (
                                        edge_id_of_lane is not None and # Ensure we have a valid edge ID
                                        (edge_id_of_lane in northbound_edges or edge_id_of_lane in southbound_edges)
                                 )

                                 if is_on_main_road_approach:
                                    vehicles_on_lane = traci.lane.getLastStepVehicleIDs(incoming_lane)

                                    for veh_id in vehicles_on_lane:
                                        # Check if the vehicle is a truck (based on vType)
                                        veh_type = traci.vehicle.getTypeID(veh_id)
                                        is_truck = 'truck' in veh_type.lower() # Simple check for 'truck' in type name

                                        # Check if the truck is part of a platoon using Simpla's API
                                        is_in_platoon = False
                                        if simpla_loaded: # Only call simpla if it loaded successfully
                                            try:
                                                # This requires simpla to expose a way to check platoon membership by vehicle ID
                                                # If simpla doesn't have a direct function, you might need to track platoons
                                                # separately or infer from vehicle type/behavior if possible.
                                                # Replace this with the actual Simpla API call if it exists:
                                                platoon_id = simpla.getPlatoonID(veh_id) # Hypothetical Simpla function
                                                if platoon_id != -1:
                                                    is_in_platoon = True
                                            except AttributeError:
                                                # Fallback if simpla.getPlatoonID doesn't exist
                                                if 'platoon' in veh_type.lower():
                                                    is_in_platoon = True
                                                # print("Warning: simpla.getPlatoonID not found. Relying on vType for platoon check.")
                                            except Exception as e:
                                                print(f"Error checking platoon ID for vehicle {veh_id}: {e}")
                                        else: # If simpla didn't load, rely on vType check only
                                             if 'platoon' in veh_type.lower():
                                                is_in_platoon = True


                                        # If it's a platoon truck, check its distance to the end of the lane (stop line)
                                        if is_truck and is_in_platoon:
                                            lane_length = traci.lane.getLength(incoming_lane)
                                            vehicle_position_on_lane = traci.vehicle.getLanePosition(veh_id)
                                            distance_to_stop_line = lane_length - vehicle_position_on_lane

                                            if distance_to_stop_line <= PLATOON_DETECTION_DISTANCE:
                                                platoon_truck_approaching_main_road = True
                                                # print(f"Platoon truck {veh_id} detected approaching TL {tl_id} on main road approach at distance {distance_to_stop_line:.2f}m")
                                                break # No need to check other vehicles on this lane

                                    # If a platoon truck was found on this lane, no need to check other lanes for this link set
                                    if platoon_truck_approaching_main_road:
                                        break
                        # If a platoon truck was found in this link set, no need to check other link sets for this traffic light
                        if platoon_truck_approaching_main_road:
                            break
                    # --- End Platoon Detection Logic ---


                    # --- Phase Change Logic ---
                    # Check if the current phase duration has elapsed
                    if time_in_current_phase[tl_id] >= current_phase_duration[tl_id]:

                        # If the current phase is a main road green AND a platoon truck is approaching
                        # on a main road approach, EXTEND the current phase.
                        if is_currently_main_road_green and platoon_truck_approaching_main_road:
                            # Do nothing - the timer continues, effectively extending the current phase.
                            pass # Explicitly do nothing to extend the current phase
                            # print(f"Extending green phase for TL {tl_id} due to approaching platoon truck.")

                        # Otherwise (not main road green, or no platoon truck approaching),
                        # proceed with the normal fixed-time phase change.
                        else:
                            # Move to the next phase
                            current_phase_index[tl_id] = (current_phase_index[tl_id] + 1) % len(TRAFFIC_LIGHT_PROGRAMS[tl_id])

                            # Set the new phase in the simulation
                            traci.trafficlight.setPhase(tl_id, current_phase_index[tl_id])

                            # Reset the timer for the new phase
                            time_in_current_phase[tl_id] = 0
                            current_phase_duration[tl_id] = TRAFFIC_LIGHT_PROGRAMS[tl_id][current_phase_index[tl_id]]

                # --- End Traffic Signal Control Logic ---


                # --- Simulation Metrics Collection ---
                vehicle_ids = traci.vehicle.getIDList()

                # Get number of vehicles in the simulation
                num_vehicles = len(vehicle_ids)

                # Calculate average speed of vehicles
                if num_vehicles > 0:
                    speeds = [traci.vehicle.getSpeed(veh_id) for veh_id in vehicle_ids]
                    avg_speed = sum(speeds) / num_vehicles
                else:
                    avg_speed = 0.0

                # Calculate average northbound inter-vehicle distance (using the defined edges)
                # This calculation assumes vehicles are on the defined northbound edges.
                # A more robust method might involve checking vehicle edge/lane.
                total_distance = 0
                distance_count = 0

                all_vehicle_positions = []

                for edge in northbound_edges:
                    # Check if edge exists in the network before querying
                    if edge in traci.edge.getIDList():
                        num_lanes = traci.edge.getLaneNumber(edge)
                        for i in range(num_lanes):
                            lane_id = f"{edge}_{i}"
                             # Check if lane exists before querying
                            if lane_id in traci.lane.getIDList():
                                vehicle_ids_on_lane = traci.lane.getLastStepVehicleIDs(lane_id)

                                # Get positions of vehicles on this lane
                                vehicle_positions = [traci.vehicle.getLanePosition(veh_id) for veh_id in vehicle_ids_on_lane]
                                all_vehicle_positions.extend(vehicle_positions)
                            else:
                                # print(f"Warning: Lane '{lane_id}' not found in network.")
                                pass # Ignore if lane not found
                    else:
                        # print(f"Warning: Edge '{edge}' not found in network.")
                        pass # Ignore if edge not found


                # Sort all vehicle positions across all lanes from downstream (0) to upstream (laneLength)
                # This assumes vehicles are on a continuous stretch of road defined by northbound_edges
                # and doesn't account for lane changes or vehicles on different edges within the list
                # being out of order in terms of overall distance along the route.
                # For a truly accurate inter-vehicle distance along a route, you'd need to calculate
                # the distance along the route for each vehicle.
                all_vehicle_positions.sort(reverse=True)

                # Compute inter-vehicle distances between consecutive vehicles in the sorted list
                for j in range(len(all_vehicle_positions) - 1):
                    dist = all_vehicle_positions[j] - all_vehicle_positions[j + 1]
                    total_distance += dist
                    distance_count += 1

                # Compute average inter-vehicle distance
                if distance_count > 0:
                    avg_intervehicular_distance = total_distance / distance_count
                else:
                    avg_intervehicular_distance = 0.0

                # Calculate the average northbound flow (vehicles that entered the edge in the last step)
                northbound_flow = sum([traci.edge.getLastStepVehicleNumber(edge) for edge in northbound_edges if edge in traci.edge.getIDList()])
                # Calculate the average southbound flow
                southbound_flow = sum([traci.edge.getLastStepVehicleNumber(edge) for edge in southbound_edges if edge in traci.edge.getIDList()])

                # Calculate the average speed of vehicles on the northbound edges
                total_speed_nb = 0
                total_vehicles_nb = 0
                for edge in northbound_edges:
                    if edge in traci.edge.getIDList():
                        n_vehicles = traci.edge.getLastStepVehicleNumber(edge)
                        mean_speed = traci.edge.getLastStepMeanSpeed(edge)
                        total_speed_nb += mean_speed * n_vehicles
                        total_vehicles_nb += n_vehicles
                northbound_speed = total_speed_nb / max(1, total_vehicles_nb)

                # Calculate the average speed of vehicles on the southbound edges
                total_speed_sb = 0
                total_vehicles_sb = 0
                for edge in southbound_edges:
                     if edge in traci.edge.getIDList():
                        n_vehicles = traci.edge.getLastStepVehicleNumber(edge)
                        mean_speed = traci.edge.getLastStepMeanSpeed(edge)
                        total_speed_sb += mean_speed * n_vehicles
                        total_vehicles_sb += n_vehicles
                southbound_speed = total_speed_sb / max(1, total_vehicles_sb)


                # Collect data points (Metrics)
                metrics = {
                    "step": step,
                    "num_vehicles": num_vehicles,
                    "avg_intervehicular_distance_northbound": avg_intervehicular_distance, # Renamed for clarity
                    "northbound_flow": northbound_flow,
                    "southbound_flow": southbound_flow,
                    "northbound_speed": northbound_speed,
                    "southbound_speed": southbound_speed,
                    "average_speed_all_vehicles": avg_speed, # Renamed for clarity
                }

                # Print metrics for each step (optional, can be noisy)
                # print(f"Step {step}: {metrics}")

                # Save data into the CSV file for this scenario
                writer.writerow(metrics)

        except traci.TraCIException as e:
            print(f"TraCI error during simulation step {step} for {sumo_config_path.name}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during simulation step {step} for {sumo_config_path.name}: {e}")

        finally:
            # Ensure SUMO closes properly even if errors occur
            print(f"Simulation finished for {sumo_config_path.name}. Closing TraCI connection.")
            traci.close()
            # Note: With traci.start launching the process directly,
            # traci.close() should handle process termination.
            # Removed explicit subprocess.terminate/wait calls.


def ask_gui():
    """
    Asks the user if they want to run the simulations with the SUMO-GUI.
    Returns "sumo-gui" if yes, "sumo" if no.
    """
    while True:
        gui_choice = input("Do you want to run the simulations in GUI mode? (y/n): ").strip().lower()

        if gui_choice == "y":
            return "sumo-gui"
        elif gui_choice == "n":
            return "sumo"
        else:
            print("Invalid choice. Please enter 'y' or 'n'.")


if __name__ == "__main__":
    print("Starting batch simulation run...")

    # Ask the user whether to run with the GUI
    sumo_binary = ask_gui()

    # Load the traffic signal mapping once at the start
    load_traffic_signal_mapping()

    # Find all .sumocfg files in the generated configs directory
    config_files = list(GENERATED_CONFIGS_DIR.glob("*.sumocfg"))

    if not config_files:
        print(f"Error: No .sumocfg files found in '{GENERATED_CONFIGS_DIR}'.")
        print("Please run generateMultipleVehicleConfigs.py first to create the scenario files.")
        sys.exit(1)

    print(f"Found {len(config_files)} scenario configuration files.")

    # Regex to extract parameters from the filename
    # Assumes filename format: config_ps<platoon_size>_np<num_platoons>_traffic_<traffic_type>.sumocfg
    filename_pattern = re.compile(r"config_ps(\d+)_np(\d+)_traffic_(\w+)\.sumocfg")

    # Iterate through each configuration file and run the simulation
    for config_file_path in sorted(config_files): # Sort files for consistent order
        # Extract parameters from the filename
        match = filename_pattern.match(config_file_path.name)
        if not match:
            print(f"Warning: Could not parse parameters from filename '{config_file_path.name}'. Skipping.")
            continue

        platoon_size = match.group(1)
        num_platoons = match.group(2)
        traffic_type = match.group(3)

        # Create a subdirectory name based on the extracted parameters
        scenario_subdir_name = f"ps{platoon_size}_np{num_platoons}_traffic_{traffic_type}"
        scenario_output_dir = SIMULATION_METRICS_BASE_DIR / scenario_subdir_name

        # Run the simulation for this scenario
        run_single_simulation(config_file_path, sumo_binary, scenario_output_dir)

    print("\nBatch simulation run finished.")
