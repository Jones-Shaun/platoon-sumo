"""
SUMO Platoon Analysis Script with Simpla Integration
---------------------------------------------------
This script integrates SUMO's simpla tool for platooning and calculates:
- Vehicular density
- Traffic flow
- Headway consistency within platoons
- Fuel/energy efficiency
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
import time

# Check if SUMO_HOME is in environment variables and add to path
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
    # Add simpla to path
    simpla_path = os.path.join(tools, 'simpla')
    sys.path.append(simpla_path)
else:
    sys.exit("Please declare the environment variable 'SUMO_HOME'")

import traci
import sumolib


class PlatoonAnalyzer:
    """Class to analyze traffic metrics with focus on platooning using simpla."""
    
    def __init__(self, sumo_config, simpla_config=None, platoon_ids=None, output_dir="./results/"):
        """
        Initialize the analyzer.
        
        Args:
            sumo_config (str): Path to SUMO configuration file
            simpla_config (str): Path to simpla configuration file
            platoon_ids (list): List of vehicle IDs in the platoon. If None, 
                               vehicles with 'platoon' in their ID will be considered
            output_dir (str): Directory to save results
        """
        
        # Check SUMO environment
        if 'SUMO_HOME' not in os.environ:
            raise EnvironmentError("SUMO_HOME environment variable not set")
            
        # Verify SUMO installation
        try:
            sumolib.checkBinary('sumo')
        except Exception as e:
            raise EnvironmentError(f"SUMO installation not found: {e}")
            
        # Verify input files exist
        if not os.path.exists(sumo_config):
            raise FileNotFoundError(f"SUMO configuration file not found: {sumo_config}")
        if simpla_config and not os.path.exists(simpla_config):
            raise FileNotFoundError(f"Simpla configuration file not found: {simpla_config}")
            
        self.sumo_config = sumo_config
        self.simpla_config = simpla_config
        self.platoon_ids = platoon_ids
        self.output_dir = output_dir
        self.network = None
        
        # Data storage
        self.vehicle_data = defaultdict(list)
        self.platoon_data = defaultdict(list)
        self.global_metrics = defaultdict(list)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)


    def start_simulation(self, gui=False, max_retries=3):
        """Start SUMO simulation with or without GUI."""
        for attempt in range(max_retries):   
            try: 
                if gui:
                    sumo_binary = sumolib.checkBinary('sumo-gui')
                else:
                    sumo_binary = sumolib.checkBinary('sumo')
                
                # Start SUMO with TraCI and simpla configuration
                cmd = [sumo_binary, "-c", self.sumo_config, "--time-to-teleport", "300"]
                if self.simpla_config:
                    cmd.extend(["--additional-files", self.simpla_config])
                
                traci.start(cmd)
                
                # Load simpla if config is provided
                if self.simpla_config:
                    try:
                        from simpla import SimplaException
                        traci.setOrder(1)  # Set order for simpla
                        print(f"Simpla loaded with config: {self.simpla_config}")
                    except (ImportError, SimplaException) as e:
                        print(f"Warning: Failed to load simpla: {e}")
                        print("Running without simpla support.")
                    
                self.network = sumolib.net.readNet(traci.simulation.getParameter("", "net-file"))
                return True
                
            except traci.exceptions.FatalTraCIError as e: 
                print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                try:
                    traci.close()
                except:
                    pass
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)  # Wait before retrying

    def is_platoon_vehicle(self, veh_id):
        """Check if a vehicle is part of the platoon."""
        if self.platoon_ids is not None:
            return veh_id in self.platoon_ids
        else:
            # If simpla is active, check for simpla platoon flag
            try:
                return bool(int(traci.vehicle.getParameter(veh_id, "simpla.platoon")))
            except:
                # Fallback: check if vehicle ID contains 'platoon'
                return 'platoon' in veh_id
    
    def get_platoon_id(self, veh_id):
        """Get the platoon ID of a vehicle if it's in a platoon."""
        try:
            return traci.vehicle.getParameter(veh_id, "simpla.platoonId")
        except:
            # If not in a simpla platoon, return None
            return None
    
    def collect_data(self):
        """Collect data during simulation."""
        step = 0
        max_steps = 3600  # Maximum number of steps (1 hour at 1 step/second)
        
        try:
            while step < max_steps and traci.simulation.getMinExpectedNumber() > 0:
                try:
                    traci.simulationStep()
                    
                    # Get all vehicles in the simulation
                    vehicles = traci.vehicle.getIDList()
                    
                    # Calculate global metrics
                    self.calculate_global_metrics(vehicles, step)
                    
                    # Collect individual vehicle data
                    for veh_id in vehicles:
                        self.collect_vehicle_data(veh_id, step)
                    
                    # Calculate platoon-specific metrics
                    self.calculate_platoon_metrics(vehicles, step)
                    
                    step += 1
                    
                except traci.exceptions.FatalTraCIError as e:
                    print(f"TraCI connection lost at step {step}: {e}")
                    break
                    
        except Exception as e:
            print(f"Error during simulation at step {step}: {e}")
            
        finally:
            try:
                self.close_simulation()
            except:
                pass

    def collect_vehicle_data(self, veh_id, step):
        """Collect data for a specific vehicle."""
        # Get simpla platoon parameters if available
        try:
            platoon_role = traci.vehicle.getParameter(veh_id, "simpla.platoonRole")
            platoon_id = traci.vehicle.getParameter(veh_id, "simpla.platoonId")
            target_gap = float(traci.vehicle.getParameter(veh_id, "simpla.targetGap"))
        except:
            platoon_role = "none"
            platoon_id = None
            target_gap = -1
            
        data = {
            'time_step': step,
            'vehicle_id': veh_id,
            'is_platoon': self.is_platoon_vehicle(veh_id),
            'platoon_role': platoon_role,
            'platoon_id': platoon_id,
            'position_x': traci.vehicle.getPosition(veh_id)[0],
            'position_y': traci.vehicle.getPosition(veh_id)[1],
            'speed': traci.vehicle.getSpeed(veh_id),
            'acceleration': traci.vehicle.getAcceleration(veh_id),
            'road_id': traci.vehicle.getRoadID(veh_id),
            'lane_id': traci.vehicle.getLaneID(veh_id),
            'distance': traci.vehicle.getDistance(veh_id),
            'target_gap': target_gap,
            'fuel_consumption': traci.vehicle.getFuelConsumption(veh_id),
            'co2_emission': traci.vehicle.getCO2Emission(veh_id),
            'leader': traci.vehicle.getLeader(veh_id) if traci.vehicle.getLeader(veh_id) else (None, -1)
        }
        
        # Store the data
        for key, value in data.items():
            self.vehicle_data[key].append(value)
    
    def calculate_global_metrics(self, vehicles, step):
        """Calculate global traffic metrics."""
        # Number of vehicles
        num_vehicles = len(vehicles)
        
        # Total road length (m)
        total_road_length = sum([edge.getLength() for edge in self.network.getEdges()])
        
        # Vehicle density (vehicles/km)
        density = num_vehicles / (total_road_length / 1000)
        
        # Traffic flow (vehicles/hour) - calculated from vehicles passing a reference point
        # For simplicity, we'll use the number of active vehicles as a proxy
        flow = num_vehicles * 3600 / (step + 1)  # assuming 1 time step = 1 second
        
        # Store metrics
        self.global_metrics['time_step'].append(step)
        self.global_metrics['num_vehicles'].append(num_vehicles)
        self.global_metrics['density'].append(density)
        self.global_metrics['flow'].append(flow)
    
    def calculate_platoon_metrics(self, vehicles, step):
        """Calculate platoon-specific metrics."""
        # Group vehicles by platoon
        platoons = {}
        for veh_id in vehicles:
            # Skip non-platoon vehicles
            if not self.is_platoon_vehicle(veh_id):
                continue
                
            # Get platoon ID
            platoon_id = self.get_platoon_id(veh_id)
            if platoon_id is None:
                # Fallback: use vehicle ID for non-simpla platoons
                platoon_id = "manual_platoon"
                
            # Add vehicle to platoon
            if platoon_id not in platoons:
                platoons[platoon_id] = []
            platoons[platoon_id].append(veh_id)
        
        # Skip if no platoons found
        if not platoons:
            return
            
        # Process each platoon
        for platoon_id, platoon_vehicles in platoons.items():
            # Skip single-vehicle "platoons"
            if len(platoon_vehicles) <= 1:
                continue
                
            # Calculate headway consistency within platoon
            headways = []
            time_gaps = []
            positions = {}
            speeds = {}
            fuel_consumptions = []
            
            # First, collect positions and speeds
            for veh_id in platoon_vehicles:
                positions[veh_id] = traci.vehicle.getPosition(veh_id)
                speeds[veh_id] = traci.vehicle.getSpeed(veh_id)
                fuel_consumptions.append(traci.vehicle.getFuelConsumption(veh_id))
            
            # Calculate headways (time gaps) between consecutive platoon vehicles
            sorted_vehicles = sorted(platoon_vehicles, key=lambda v: traci.vehicle.getDistance(v))
            
            for i in range(1, len(sorted_vehicles)):
                lead_veh = sorted_vehicles[i-1]
                follow_veh = sorted_vehicles[i]
                
                # Get leader info using SUMO's built-in function
                leader_info = traci.vehicle.getLeader(follow_veh)
                
                if leader_info and leader_info[0] == lead_veh:
                    # Distance gap
                    distance_gap = leader_info[1]
                    
                    # Time headway (seconds) - if follower is moving
                    speed = speeds[follow_veh]
                    if speed > 0:
                        time_headway = distance_gap / speed
                        headways.append(time_headway)
                        time_gaps.append(time_headway)
            
            # Calculate metrics
            avg_headway = np.mean(headways) if headways else np.nan
            std_headway = np.std(headways) if headways else np.nan
            avg_fuel = np.mean(fuel_consumptions)
            
            # Store platoon metrics
            self.platoon_data['time_step'].append(step)
            self.platoon_data['platoon_id'].append(platoon_id)
            self.platoon_data['platoon_size'].append(len(platoon_vehicles))
            self.platoon_data['avg_headway'].append(avg_headway)
            self.platoon_data['std_headway'].append(std_headway)
            self.platoon_data['headway_consistency'].append(1 / (std_headway + 0.001) if not np.isnan(std_headway) else np.nan)
            self.platoon_data['avg_fuel_consumption'].append(avg_fuel)
    
    def close_simulation(self):
        """Close SUMO simulation."""
        traci.close()
    
    def process_results(self):
        """Process and analyze collected data."""
        # Convert to dataframes
        vehicle_df = pd.DataFrame(self.vehicle_data)
        platoon_df = pd.DataFrame(self.platoon_data)
        global_df = pd.DataFrame(self.global_metrics)
        
        # Save raw data
        vehicle_df.to_csv(os.path.join(self.output_dir, 'vehicle_data.csv'), index=False)
        platoon_df.to_csv(os.path.join(self.output_dir, 'platoon_data.csv'), index=False)
        global_df.to_csv(os.path.join(self.output_dir, 'global_metrics.csv'), index=False)
        
        return {
            'vehicle_data': vehicle_df,
            'platoon_data': platoon_df,
            'global_metrics': global_df
        }
    
    def generate_plots(self, data):
        """Generate plots for visualization."""
        # Extract dataframes
        vehicle_df = data['vehicle_data']
        platoon_df = data['platoon_data']
        global_df = data['global_metrics']
        
        # 1. Plot vehicular density over time
        plt.figure(figsize=(10, 6))
        plt.plot(global_df['time_step'], global_df['density'])
        plt.title('Vehicular Density Over Time')
        plt.xlabel('Simulation Time Step')
        plt.ylabel('Density (vehicles/km)')
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, 'density_plot.png'))
        
        # 2. Plot traffic flow over time
        plt.figure(figsize=(10, 6))
        plt.plot(global_df['time_step'], global_df['flow'])
        plt.title('Traffic Flow Over Time')
        plt.xlabel('Simulation Time Step')
        plt.ylabel('Flow (vehicles/hour)')
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, 'flow_plot.png'))
        
        # 3. Plot headway consistency within platoon
        if not platoon_df.empty and 'avg_headway' in platoon_df.columns:
            # Group by time step if there are multiple platoons
            if 'platoon_id' in platoon_df.columns:
                grouped = platoon_df.groupby(['time_step', 'platoon_id'])
                for platoon_id, group in grouped:
                    plt.figure(figsize=(10, 6))
                    plt.plot(group['time_step'], group['avg_headway'])
                    plt.fill_between(
                        group['time_step'],
                        group['avg_headway'] - group['std_headway'],
                        group['avg_headway'] + group['std_headway'],
                        alpha=0.3
                    )
                    plt.title(f'Platoon {platoon_id} Headway Over Time')
                    plt.xlabel('Simulation Time Step')
                    plt.ylabel('Average Headway (s)')
                    plt.grid(True)
                    plt.savefig(os.path.join(self.output_dir, f'headway_plot_platoon_{platoon_id}.png'))
            else:
                plt.figure(figsize=(10, 6))
                plt.plot(platoon_df['time_step'], platoon_df['avg_headway'])
                plt.fill_between(
                    platoon_df['time_step'],
                    platoon_df['avg_headway'] - platoon_df['std_headway'],
                    platoon_df['avg_headway'] + platoon_df['std_headway'],
                    alpha=0.3
                )
                plt.title('Platoon Headway Over Time')
                plt.xlabel('Simulation Time Step')
                plt.ylabel('Average Headway (s)')
                plt.grid(True)
                plt.savefig(os.path.join(self.output_dir, 'headway_plot.png'))
        
        # 4. Plot fuel consumption
        if 'is_platoon' in vehicle_df.columns:
            platoon_vehicles = vehicle_df[vehicle_df['is_platoon'] == True]
            regular_vehicles = vehicle_df[vehicle_df['is_platoon'] == False]
            
            # Group by time step and calculate average
            if not platoon_vehicles.empty and not regular_vehicles.empty:
                platoon_fuel = platoon_vehicles.groupby('time_step')['fuel_consumption'].mean()
                regular_fuel = regular_vehicles.groupby('time_step')['fuel_consumption'].mean()
                
                plt.figure(figsize=(10, 6))
                plt.plot(platoon_fuel.index, platoon_fuel.values, label='Platoon Vehicles')
                plt.plot(regular_fuel.index, regular_fuel.values, label='Regular Vehicles')
                plt.title('Average Fuel Consumption Over Time')
                plt.xlabel('Simulation Time Step')
                plt.ylabel('Fuel Consumption (ml/s)')
                plt.legend()
                plt.grid(True)
                plt.savefig(os.path.join(self.output_dir, 'fuel_consumption_plot.png'))
    
    def summarize_metrics(self, data):
        """Print a summary of key metrics."""
        # Extract dataframes
        vehicle_df = data['vehicle_data']
        platoon_df = data['platoon_data']
        global_df = data['global_metrics']
        
        # Summary statistics
        summary = {
            'average_density': global_df['density'].mean(),
            'average_flow': global_df['flow'].mean(),
        }
        
        # Add platoon metrics if available
        if not platoon_df.empty and 'avg_headway' in platoon_df.columns:
            summary['average_platoon_headway'] = platoon_df['avg_headway'].mean()
            if 'headway_consistency' in platoon_df.columns:
                summary['headway_consistency'] = platoon_df['headway_consistency'].mean()
        
        # Calculate fuel efficiency comparison
        if 'is_platoon' in vehicle_df.columns:
            platoon_vehicles = vehicle_df[vehicle_df['is_platoon'] == True]
            regular_vehicles = vehicle_df[vehicle_df['is_platoon'] == False]
            
            if not platoon_vehicles.empty and not regular_vehicles.empty:
                avg_platoon_fuel = platoon_vehicles['fuel_consumption'].mean()
                avg_regular_fuel = regular_vehicles['fuel_consumption'].mean()
                fuel_efficiency_gain = ((avg_regular_fuel - avg_platoon_fuel) / avg_regular_fuel) * 100
                
                summary['avg_platoon_fuel_consumption'] = avg_platoon_fuel
                summary['avg_regular_fuel_consumption'] = avg_regular_fuel
                summary['fuel_efficiency_gain_percent'] = fuel_efficiency_gain
        
        # Save summary
        with open(os.path.join(self.output_dir, 'metrics_summary.txt'), 'w') as f:
            f.write("Traffic Metrics Summary\n")
            f.write("======================\n\n")
            
            for key, value in summary.items():
                f.write(f"{key.replace('_', ' ').title()}: {value:.4f}\n")
        
        return summary
    
    def run_analysis(self, gui=False):
        """Run the full analysis pipeline."""
        try:
            print("Starting SUMO simulation...")
            if not self.start_simulation(gui):
                raise RuntimeError("Failed to start simulation after multiple attempts")
            
            print("Collecting simulation data...")
            self.collect_data()
            
            if not self.vehicle_data:
                raise RuntimeError("No data collected during simulation")
            
            print("Processing results...")
            data = self.process_results()
            
            print("Generating plots...")
            self.generate_plots(data)
            
            print("Summarizing metrics...")
            summary = self.summarize_metrics(data)
            
            print("Analysis complete! Results saved to:", self.output_dir)
            return data, summary
            
        except Exception as e:
            print(f"Error during analysis: {e}")
            return None, None
        finally:
            try:
                self.close_simulation()
            except:
                pass


def create_simpla_config(output_path="simpla.cfg"):
    """
    Create a configuration file for simpla platoon management.
    
    Args:
        output_path (str): Path to save the simpla config file
        
    Returns:
        str: Path to the created config file
    """
    # Simpla configuration XML
    simpla_config = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <!-- SPD (Sublane-based Platooning for SUMO Driver) Configuration -->
    
    <!-- Platoon Attributes -->
    <vehicleSelectors value="truck"/>  <!-- Only select trucks for platooning -->
    <maxVehicleLength value="12.0"/>
    <maxPlatoonGap value="10.0"/>
    <catchupHeadway value="2.0"/>
    <platoonSplitTime value="3.0"/>
    
    <!-- Platoon Management -->
    <managedLanes value=""/>
    <mingap value="0.5"/>
    <catchupSpeed value="0.15"/>  <!-- % of driving speed -->
    <switchImpatienceFactor value="1.0"/>
    
    <!-- Platoon Operation -->
    <lcMode value="597"/>
    <speedFactor value="1.0"/>
    <verbosity value="3"/>
    <vTypeMap original="truck" leader="truck_platoon_leader" follower="truck_platoon_follower"/>
</configuration>"""
    
    # Write to file
    with open(output_path, 'w') as f:
        f.write(simpla_config)
        
    return output_path


def generate_traffic_scenario(scenario_type, platoon_size=None, base_net="osm.net.xml"):
    """
    Generate different traffic scenarios for comparison using simpla.
    
    Args:
        scenario_type (str): One of 'platoon_only', 'light_traffic', 'heavy_traffic'
        platoon_size (int): Desired size of truck platoons. If None, default sizes are used
        base_net (str): Base network file
    
    Returns:
        str: Path to the generated scenario configuration file
    """
    # Verify network file exists
    if not os.path.exists(base_net):
        raise FileNotFoundError(f"Network file not found: {base_net}")
        
    # Load network to get valid edges
    try:
        net = sumolib.net.readNet(base_net)
        # Get main route edges (highway type)
        main_edges = [edge.getID() for edge in net.getEdges() 
                     if edge.getType() in ['highway.primary_link', 'highway.primary' , 'highway.secondary' , 'highway.secondary_link']]
        if not main_edges:
            raise ValueError("No valid highway edges found in network")
    except Exception as e:
        raise RuntimeError(f"Failed to load network: {e}")
    
    scenario_name = f"{scenario_type}_scenario"
    routes_file = f"{scenario_name}_routes.xml"
    config_file = f"{scenario_name}.sumocfg"
    
    # Create simpla configuration
    simpla_config = create_simpla_config("generated_configs/simpla/simpla.cfg")
    
    # Convert 50 MPH to m/s (22.352 m/s)
    speed_limit = 22.352
    
    # Create route file with different settings based on scenario
    if scenario_type == "platoon_only":
        # Define vehicle types compatible with simpla
        with open(routes_file, 'w') as f:
            f.write(f"""<routes>
    <!-- Vehicle types for truck platoons -->
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>
    
    <!-- Create truck platoons -->
    <route id="main_route" edges="{' '.join(main_edges)}"/>
    <flow id="truck_platoon" type="truck" route="main_route" begin="0" number="{platoon_size if platoon_size else 5}" departLane="0" departSpeed="{speed_limit}"/>
</routes>""")
    
    elif scenario_type == "light_traffic":
        # Create truck platoons with light background traffic
        with open(routes_file, 'w') as f:
            f.write(f"""<routes>
    <!-- Vehicle types -->
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>
    
    <!-- Truck platoons -->
    <route id="main_route" edges="{' '.join(main_edges)}"/>
    <flow id="truck_platoon" type="truck" route="main_route" begin="0" number="{platoon_size if platoon_size else 5}" departLane="0" departSpeed="{speed_limit}"/>
    
    <!-- Light traffic: 300 vehicles/hour (1 every 12 seconds) -->
    <flow id="light_flow" type="car" route="main_route" begin="10" end="3600" period="12" departLane="random" departSpeed="max"/>
</routes>""")
    
    elif scenario_type == "heavy_traffic":
        # Create truck platoons amidst heavy background traffic
        with open(routes_file, 'w') as f:
            f.write(f"""<routes>
    <!-- Vehicle types -->
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>
    
    <!-- Truck platoons -->
    <route id="main_route" edges="{' '.join(main_edges)}"/>
    <flow id="truck_platoon" type="truck" route="main_route" begin="0" number="{platoon_size if platoon_size else 5}" departLane="0" departSpeed="{speed_limit}"/>
    
    <!-- Heavy traffic: 1800 vehicles/hour (1 every 2 seconds) -->
    <flow id="heavy_flow_cars" type="car" route="main_route" begin="10" end="3600" period="2" departLane="random" departSpeed="max"/>
    <flow id="heavy_flow_trucks" type="truck" route="main_route" begin="10" end="3600" period="12" departLane="random" departSpeed="max"/>
</routes>""")
    
    # Create config file that includes simpla
    with open(config_file, 'w') as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{base_net}"/>
        <route-files value="{routes_file}"/>
        <additional-files value="osm.poly.xml.gz"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>
    </time>
    <processing>
        <lateral-resolution value="0.13"/>
    </processing>
    <report>
        <verbose value="true"/>
        <no-step-log value="true"/>
    </report>
    <gui_only>
        <start value="true"/>
    </gui_only>
    <random_number>
        <seed value="23423"/>
    </random_number>
</configuration>""")
    
    return config_file


if __name__ == "__main__":
    try:
        # Get user input for platoon size
        while True:
            try:
                platoon_size = input("Enter desired platoon size (3-10) or press Enter for default (5): ")
                if not platoon_size:
                    platoon_size = None
                    break
                platoon_size = int(platoon_size)
                if 3 <= platoon_size <= 10:
                    break
                print("Please enter a number between 3 and 10")
            except ValueError:
                print("Please enter a valid number")
        
        # Initialize analyzer
        analyzer = PlatoonAnalyzer(
            sumo_config="generated_configs/traffic/platoon_only_scenario.sumocfg",
            simpla_config="generated_configs/simpla/simpla.cfg",
            output_dir="results/"
        )
        
        # Generate different traffic scenarios
        scenarios = ["platoon_only", "light_traffic", "heavy_traffic"]
        for scenario in scenarios:
            print(f"\nGenerating {scenario} scenario...")
            try:
                config_file = generate_traffic_scenario(
                    scenario,
                    platoon_size=platoon_size,
                    base_net="osm_files/osm.net.xml"
                )
                print(f"Scenario configuration saved to: {config_file}")
                
                # Run analysis for each scenario
                analyzer.sumo_config = config_file
                data, summary = analyzer.run_analysis(gui=True)  # Enable GUI for visualization
                print(f"\nSummary for {scenario} scenario:")
                for metric, value in summary.items():
                    print(f"{metric}: {value:.4f}")
            except Exception as e:
                print(f"Error in {scenario} scenario: {e}")
                continue
                
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1) 

