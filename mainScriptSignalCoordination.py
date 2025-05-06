"""
This script runs a SUMO simulation with generated traffic scenarios and
includes platoon-aware traffic signal control using TraCI.
It implements logic to extend the green phase for main road approaches
if a platoon truck is within a certain distance of the signal.
Otherwise, traffic lights follow their standard fixed-time program.

It loads traffic signal mapping data from a JSON file (traffic_signal_mapping.json)
to assist in identifying main road approaches and correctly applying
the platoon-aware control logic.
"""
import sys
import os
import json  # Import the json library for loading the mapping file

# This block tries to add the SUMO tools directory to the system path.
# It's important for finding the traci and sumolib modules if they aren't
# installed directly in the environment (though installing with conda/pip is preferred).

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))

# Import necessary libraries
# traci allows interaction with the running SUMO simulation
import traci
# os for interacting with the operating system (paths, environment variables)
import os
# simpla for platooning functionality (assuming it's used in the simulation)
import simpla  # Import Simpla
# csv for writing simulation metrics to a CSV file
import csv
# pathlib for working with file paths in a more object-oriented way
from pathlib import Path


# Important details from configuration files:
# One simulation step is 1 second
# Simulation time is 3600 seconds (1 hour)

SIM_TIME = 3600  # Total simulation time in seconds (and steps)

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
# List to store the IDs of all traffic lights in the simulation
traffic_light_ids = []
# Dictionary to store the current phase index for each traffic light
current_phase_index = {}
# Dictionary to store the duration for the current phase for each traffic light
current_phase_duration = {}
# Dictionary to store the time remaining in the current phase for each traffic light
time_in_current_phase = {}

# Define simple fixed-time traffic light programs (example)
# This will be populated after connecting to SUMO by reading the network's programs.
TRAFFIC_LIGHT_PROGRAMS = {}

# Define the distance threshold for platoon truck detection (in meters)
PLATOON_DETECTION_DISTANCE = 150 # Example: 150 meters - adjust as needed

# --- Define which phases are 'main road green' for each traffic light ---
# This is CRUCIAL and depends entirely on your specific SUMO network's traffic light programs.
# You need to inspect your .net.xml or use traci.trafficlight.getCompleteRedYellowGreenDefinition()
# to determine which phase indices correspond to the main road having a green light.
# Use the traffic_signal_mapping.json file (generated previously) to help you
# accurately populate this dictionary with the correct traffic light IDs and phase indices.
# Example structure: {'traffic_light_id': [list of main_road_green_phase_indices]}
# Replace 'your_tl_id_1', 'your_tl_id_2' with the actual IDs from your network.
# Replace the phase indices [0, 2] and [1] with the correct indices for your programs.
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


def run_simulation():
    """
    Starts and runs the SUMO simulation, controls traffic lights,
    and collects simulation metrics.
    """
    # Ask user if they want GUI and which scenario to run
    sumo_binary = ask_gui()
    sumo_config = ask_scenario()

    # Construct path to the Simpla configuration file
    simpla_config = os.path.join(os.getcwd(), "generated_configs", "simpla", "simpla.xml")

    # Ensure the required files exist before starting SUMO
    if not os.path.exists(sumo_config):
        raise FileNotFoundError(f"The file '{sumo_config}' is missing. Please ensure it exists.")

    if not os.path.exists(simpla_config):
        raise FileNotFoundError(f"The file '{simpla_config}' is missing. Please ensure it exists.")

    # Define the command to start SUMO
    sumo_cmd = [sumo_binary, "-c", sumo_config]

    # Start the SUMO simulation and connect via TraCI
    # The try-except block handles potential errors during connection
    try:
        print("Starting SUMO simulation and connecting via TraCI...")
        # Use port 0 to let SUMO choose a free port, then get the port
        traci.start(sumo_cmd, port=0)
        print("TraCI connection established.")
    except traci.TraCIException as e:
        print(f"Error starting SUMO or connecting via TraCI: {e}")
        print("Please ensure SUMO is installed and SUMO_HOME is set correctly.")
        print("Also, check your SUMO configuration file for errors.")
        sys.exit(1)
    except FileNotFoundError:
         print(f"\nError: SUMO binary '{sumo_binary}' not found.")
         print("Please ensure that SUMO is installed and the directory containing")
         print(f"'{sumo_binary}' is in your system's PATH environment variable,")
         print("or that SUMO_HOME is set correctly and its 'bin' directory is in PATH.")
         sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred during SUMO startup: {e}")
        sys.exit(1)


    # Initialize Simpla for platooning after establishing TraCI connection
    # Simpla needs a running simulation to load its configuration
    try:
        simpla.load(simpla_config)
        print("Simpla loaded successfully.")
    except Exception as e:
        print(f"Error loading Simpla configuration: {e}")
        # Decide if this is a fatal error or if the simulation can continue without Simpla
        # For this example, we'll print a warning and continue.
        print("Warning: Simpla might not be fully functional.")


    # --- Load Traffic Signal to Incoming Lane Mapping from JSON ---
    global traffic_signal_mapping
    try:
        with open(TRAFFIC_SIGNAL_MAPPING_FILE, 'r') as f:
            traffic_signal_mapping = json.load(f)
        print(f"Traffic signal mapping loaded from '{TRAFFIC_SIGNAL_MAPPING_FILE}'")
    except FileNotFoundError:
        print(f"Error: Traffic signal mapping file '{TRAFFIC_SIGNAL_MAPPING_FILE}' not found.")
        print("Please run a script to generate this file first (e.g., the previous version of this script with GENERATE_MAPPING_JSON=True).")
        # This is a critical error for platoon-aware control, so we should exit.
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from '{TRAFFIC_SIGNAL_MAPPING_FILE}': {e}")
        print("Please check the file content for valid JSON format.")
        sys.exit(1) # Exit if JSON is invalid
    except Exception as e:
        print(f"An unexpected error occurred while loading mapping file: {e}")
        sys.exit(1) # Exit on other loading errors


    # --- Traffic Signal Control Initialization ---
    # Get the IDs of all traffic lights in the simulation
    global traffic_light_ids
    traffic_light_ids = traci.trafficlight.getIDList()
    print(f"\nFound traffic lights: {traffic_light_ids}")

    # Initialize phase tracking for each traffic light and populate TRAFFIC_LIGHT_PROGRAMS
    global current_phase_index, current_phase_duration, time_in_current_phase, TRAFFIC_LIGHT_PROGRAMS, MAIN_ROAD_GREEN_PHASES
    for tl_id in traffic_light_ids:
        # Get the current program and phase
        program_id = traci.trafficlight.getProgram(tl_id)
        # Get the first logic program defined for this traffic light
        # Assumes traffic lights have at least one logic program
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

        except IndexError:
            print(f"Warning: Traffic light '{tl_id}' has no defined logic programs. Skipping traffic signal control for this TL.")
            # Remove this TL from the list of controlled traffic lights
            traffic_light_ids.remove(tl_id)
            continue # Move to the next traffic light


        # --- IMPORTANT: You MUST populate MAIN_ROAD_GREEN_PHASES with the correct phase indices for each TL ---
        # If a traffic light ID is found but not in MAIN_ROAD_GREEN_PHASES, add a placeholder
        if tl_id not in MAIN_ROAD_GREEN_PHASES:
             MAIN_ROAD_GREEN_PHASES[tl_id] = [] # Default to empty list, meaning no main road green phases defined
             print(f"Warning: Traffic light '{tl_id}' not found in MAIN_ROAD_GREEN_PHASES. Please define its main road green phase indices for platoon-aware control.")


    # --- End Traffic Signal Control Initialization ---


    try:
        step = 0
        # Simulation loop
        while step < SIM_TIME:
            step += 1
            traci.simulationStep()  # Advance the simulation by one step

            # --- Traffic Signal Control Logic (Platoon-Aware Green Extension) ---
            for tl_id in traffic_light_ids:
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

            # Save data into a CSV file every 5 steps
            if step % 5 == 0:
                output_file = "simulation_metrics.csv"

                # Overwrite the file on the first data write (step 5)
                mode = "w" if step == 5 else "a"

                with open(output_file, mode=mode, newline="") as csv_file:
                    fieldnames = metrics.keys()
                    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                    # Write the header only when creating a new file (step 5)
                    if step == 5:
                        writer.writeheader()

                    # Write the metrics for the current step
                    writer.writerow(metrics)

    except traci.TraCIException as e:
        print(f"TraCI error during simulation step {step}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during simulation step {step}: {e}")

    finally:
        # Ensure SUMO closes properly even if errors occur
        print("Simulation finished. Closing TraCI connection.")
        traci.close()


def ask_scenario():
    """
    Asks the user to select a traffic scenario configuration file.
    Returns the path to the selected SUMO configuration file (.sumocfg).
    """
    traffic_configs_dir = Path.cwd() / "generated_configs" / "traffic"
    # Ensure the traffic configs directory exists
    if not traffic_configs_dir.exists():
        print(f"Error: Traffic configurations directory not found at {traffic_configs_dir}")
        print("Please run generateVehicleConfigs.py first to create the scenarios.")
        sys.exit(1)

    # Find all .sumocfg files in the traffic configurations directory
    config_files = list(traffic_configs_dir.glob("*.sumocfg"))

    if not config_files:
        print(f"Error: No .sumocfg files found in {traffic_configs_dir}")
        print("Please run generateVehicleConfigs.py first to create the scenarios.")
        sys.exit(1)

    # Present the found config files to the user
    print("Select a traffic scenario to run:")
    for i, config_file in enumerate(config_files):
        print(f"{i + 1}. {config_file.name}")

    while True:
        try:
            choice = input(f"Enter the number corresponding to your choice (1-{len(config_files)}): ").strip()
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(config_files):
                return str(config_files[choice_index]) # Return the selected file path as a string
            else:
                print("Invalid choice. Please enter a number within the range.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def ask_gui():
    """
    Asks the user if they want to run the simulation with the SUMO-GUI.
    Returns "sumo-gui" if yes, "sumo" if no.
    """
    while True:
        gui_choice = input("Do you want to run the simulation in GUI mode? (y/n): ").strip().lower()

        if gui_choice == "y":
            return "sumo-gui"
        elif gui_choice == "n":
            return "sumo"
        else:
            print("Invalid choice. Please enter 'y' or 'n'.")


if __name__ == "__main__":
    run_simulation()
