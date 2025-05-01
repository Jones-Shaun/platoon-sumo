import traci
import os
import simpla  # Import Simpla
import csv

# Important details from congiguration files:
# One simulation step is 1 second
# Simulation time is 3600 seconds (1 hour)
# First northbound edge on fairfax county parkway
# edge_north_0 = "228470926"
# Last northbound edge on fairfax county parkway
# edge_north_1 = "173228852"
# First southbound edge on fairfax county parkway
# edge_south_0 = "16044310#0"
# Last southbound edge on fairfax county parkway
# edge_south_1 = "228463846#2"

SIM_TIME = 3600  # Total simulation time in seconds (and steps)

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

def run_simulation():
    # Start SUMO simulation
    sumo_binary = "sumo-gui"  # Use "sumo-gui" for gui mode
    # sumo_config = os.path.join(os.getcwd(), "generated_configs", "traffic", "platoon_only_scenario.sumocfg")
    # sumo_config = os.path.join(os.getcwd(), "generated_configs", "traffic", "light_traffic_scenario.sumocfg")
    sumo_config = os.path.join(os.getcwd(), "generated_configs", "traffic", "heavy_traffic_scenario.sumocfg")
    simpla_config = os.path.join(os.getcwd(), "generated_configs", "simpla", "simpla.xml")

    # Ensure the required files exist
    if not os.path.exists(sumo_config):
        raise FileNotFoundError(f"The file '{sumo_config}' is missing. Please ensure it exists.")
    
    if not os.path.exists(simpla_config):
        raise FileNotFoundError(f"The file '{simpla_config}' is missing. Please ensure it exists.")
    
    sumo_cmd = [sumo_binary, "-c", sumo_config]
    traci.start(sumo_cmd)

    # Initialize Simpla for platooning
    simpla.load(simpla_config)

    try:
        step = 0
        while step < SIM_TIME:  # Run for 3600 steps
            step += 1
            traci.simulationStep()  # Advance the simulation by one step
            
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
            total_distance = 0
            distance_count = 0

            all_vehicle_positions = []

            for edge in northbound_edges:
                num_lanes = traci.edge.getLaneNumber(edge)  # Get number of lanes for the edge
                for i in range(num_lanes):
                    lane_id = f"{edge}_{i}"  # Get lane ID
                    vehicle_ids = traci.lane.getLastStepVehicleIDs(lane_id)

                    # Get positions of vehicles on this lane
                    vehicle_positions = [traci.vehicle.getLanePosition(veh_id) for veh_id in vehicle_ids]
                    all_vehicle_positions.extend(vehicle_positions)

            # Sort all vehicle positions across all lanes from downstream (0) to upstream (laneLength)
            all_vehicle_positions.sort(reverse=True)

            # Compute inter-vehicle distances
            for j in range(len(all_vehicle_positions) - 1):
                dist = all_vehicle_positions[j] - all_vehicle_positions[j + 1]
                total_distance += dist
                distance_count += 1

            # Compute average inter-vehicle distance
            # Note: This is the average distance between vehicles on the same lane
            if distance_count > 0:
                avg_intervehicular_distance = total_distance / distance_count
            else:
                avg_intervehicular_distance = 0.0
            
            # Note: Literally: the number of vehicles on the edges at the last step
            # Alternatively: use the output of the inductive loop detectors (commented out further down)
            
            # Calculate the average northbound flow (using the defined edges)
            northbound_flow = sum([traci.edge.getLastStepVehicleNumber(edge) for edge in northbound_edges])
            # Calculate the average southbound flow (using the defined edges)
            southbound_flow = sum([traci.edge.getLastStepVehicleNumber(edge) for edge in southbound_edges])
            
            # Calculate the average speed of vehicles on the southbound edges
            total_speed = 0
            total_vehicles = 0

            for edge in northbound_edges:
                n_vehicles = traci.edge.getLastStepVehicleNumber(edge)
                mean_speed = traci.edge.getLastStepMeanSpeed(edge)
                total_speed += mean_speed * n_vehicles
                total_vehicles += n_vehicles

            northbound_speed = total_speed / max(1, total_vehicles)
            
            # Calculate the average speed of vehicles on the southbound edges
            total_speed = 0
            total_vehicles = 0

            for edge in southbound_edges:
                n_vehicles = traci.edge.getLastStepVehicleNumber(edge)
                mean_speed = traci.edge.getLastStepMeanSpeed(edge)
                total_speed += mean_speed * n_vehicles
                total_vehicles += n_vehicles

            southbound_speed = total_speed / max(1, total_vehicles)
            
            # Collect data points (Metrics)
            metrics = {
                "num_vehicles": num_vehicles,
                "avg_intervehicular_distance": avg_intervehicular_distance,
                "northbound_flow": northbound_flow,
                "southbound_flow": southbound_flow,
                "northbound_speed": northbound_speed,
                "southbound_speed": southbound_speed,
                "average_speed": avg_speed,
            }
            
            # Print metrics for each step
            # print(f"Step {step}: {metrics}")
            
            # Save every fifth step's data into a CSV file
            if step % 5 == 0:
                output_file = "simulation_metrics.csv"
                
                # Overwrite the file on the first step
                mode = "w" if step == 5 else "a"
                
                with open(output_file, mode=mode, newline="") as csv_file:
                    fieldnames = metrics.keys()
                    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                    
                    # Write the header only when creating a new file
                    if step == 5:
                        writer.writeheader()
                    
                    # Write the metrics for the current step
                    writer.writerow(metrics)

    finally:
        traci.close()  # Ensure SUMO closes properly
        
    
if __name__ == "__main__":
    run_simulation()