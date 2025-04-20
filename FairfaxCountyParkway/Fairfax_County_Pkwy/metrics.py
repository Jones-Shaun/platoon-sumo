"""
Basic Traffic Metrics Collection Script
-------------------------------------
This script collects basic traffic metrics using SUMO's TraCI interface:
- Vehicular density
- Traffic flow
- Average speed
- Fuel consumption
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
else:
    sys.exit("Please declare the environment variable 'SUMO_HOME'")

import traci
import sumolib

class TrafficAnalyzer:
    """Class to analyze basic traffic metrics."""
    
    def __init__(self, sumo_config, output_dir="./results/"):
        """
        Initialize the analyzer.
        
        Args:
            sumo_config (str): Path to SUMO configuration file
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
            
        # Verify input file exists
        if not os.path.exists(sumo_config):
            raise FileNotFoundError(f"SUMO configuration file not found: {sumo_config}")
            
        self.sumo_config = sumo_config
        self.output_dir = output_dir
        self.network = None
        
        # Data storage
        self.vehicle_data = defaultdict(list)
        self.global_metrics = defaultdict(list)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def start_simulation(self, gui=False, max_retries=3):
        """Start SUMO simulation with or without GUI."""
        for attempt in range(max_retries):   
        
            print(f"Attempt {attempt + 1}/{max_retries} to start simulation...")
            
            # Check if SUMO_HOME is set
            if 'SUMO_HOME' not in os.environ:
                raise EnvironmentError("SUMO_HOME environment variable not set")
            print(f"SUMO_HOME is set to: {os.environ['SUMO_HOME']}")
            
            # Always use sumo (not sumo-gui) for headless simulation
            sumo_binary = sumolib.checkBinary('sumo')
            print(f"Using SUMO binary: {sumo_binary}")
            
            # Check if config file exists
            if not os.path.exists(self.sumo_config):
                raise FileNotFoundError(f"SUMO configuration file not found: {self.sumo_config}")
            print(f"Using config file: {self.sumo_config}")
            
            # Start SUMO with TraCI
            cmd = [sumo_binary, "-c", self.sumo_config]
            print(f"Starting SUMO with command: {' '.join(cmd)}")
            
            try:
                traci.start(cmd)
                print("TraCI connection established successfully")
            except Exception as e:
                print(f"Error during traci.start(): {str(e)}")
                raise
            
            try:
                net_file = 'osm.net.xml'
                print(f"Network file from simulation: {net_file}")
                self.network = sumolib.net.readNet(net_file)
                print("Network loaded successfully")
            except Exception as e:
                print(f"Error loading network: {str(e)}")
                raise
            
            return True
                
            # except traci.exceptions.FatalTraCIError as e: 
            #     print(f"TraCI error: {e}")
            #     try:
            #         traci.close()
            #     except:
            #         print("Failed to close TraCI connection")
            #     if attempt == max_retries - 1:
            #         raise
            #     time.sleep(2)  # Wait before retrying
            # except Exception as e:
            #     print(f"Unexpected error: {e}")
            #     try:
            #         traci.close()
            #     except:
            #         print("Failed to close TraCI connection")
            #     if attempt == max_retries - 1:
            #         raise
            #     time.sleep(2)  # Wait before retrying

    def collect_data(self):
        """Collect data during simulation."""
        step = 0
        max_steps = 10  # Maximum number of steps (1 hour at 1 step/second is 3600 seconds, changed because simulation took too long without gui speed up)
        # metrics have been generated, we need to figure out if they are correct.  
        
        try:
            while step < max_steps and traci.simulation.getMinExpectedNumber() > 0:
                try:
                    traci.simulationStep()
                    
                    # Get all vehicles in the simulation
                    vehicles = traci.vehicle.getIDList()
                    
                    # Calculate global metrics
                    self.calculate_global_metrics(vehicles, step)
                    print()
                    # Collect individual vehicle data
                    for veh_id in vehicles:
                        self.collect_vehicle_data(veh_id, step)
                    
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
        data = {
            'time_step': step,
            'vehicle_id': veh_id,
            'position_x': traci.vehicle.getPosition(veh_id)[0],
            'position_y': traci.vehicle.getPosition(veh_id)[1],
            'speed': traci.vehicle.getSpeed(veh_id),
            'acceleration': traci.vehicle.getAcceleration(veh_id),
            'road_id': traci.vehicle.getRoadID(veh_id),
            'lane_id': traci.vehicle.getLaneID(veh_id),
            'distance': traci.vehicle.getDistance(veh_id),
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
        
        # Traffic flow (vehicles/hour)
        flow = num_vehicles * 3600 / (step + 1)  # assuming 1 time step = 1 second
        
        # Average speed (m/s)
        speeds = [traci.vehicle.getSpeed(veh_id) for veh_id in vehicles]
        avg_speed = np.mean(speeds) if speeds else 0
        
        # Store metrics
        self.global_metrics['time_step'].append(step)
        self.global_metrics['num_vehicles'].append(num_vehicles)
        self.global_metrics['density'].append(density)
        self.global_metrics['flow'].append(flow)
        self.global_metrics['avg_speed'].append(avg_speed)
    
    def close_simulation(self):
        """Close SUMO simulation."""
        traci.close()
    
    def process_results(self):
        """Process and analyze collected data."""
        # Convert to dataframes
        vehicle_df = pd.DataFrame(self.vehicle_data)
        global_df = pd.DataFrame(self.global_metrics)
        
        # Save raw data
        vehicle_df.to_csv(os.path.join(self.output_dir, 'vehicle_data.csv'), index=False)
        global_df.to_csv(os.path.join(self.output_dir, 'global_metrics.csv'), index=False)
        
        return {
            'vehicle_data': vehicle_df,
            'global_metrics': global_df
        }
    
    def generate_plots(self, data):
        """Generate plots for visualization."""
        # Extract dataframes
        vehicle_df = data['vehicle_data']
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
        
        # 3. Plot average speed over time
        plt.figure(figsize=(10, 6))
        plt.plot(global_df['time_step'], global_df['avg_speed'])
        plt.title('Average Speed Over Time')
        plt.xlabel('Simulation Time Step')
        plt.ylabel('Average Speed (m/s)')
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, 'speed_plot.png'))
        
        # 4. Plot fuel consumption over time
        if not vehicle_df.empty:
            fuel_consumption = vehicle_df.groupby('time_step')['fuel_consumption'].mean()
            plt.figure(figsize=(10, 6))
            plt.plot(fuel_consumption.index, fuel_consumption.values)
            plt.title('Average Fuel Consumption Over Time')
            plt.xlabel('Simulation Time Step')
            plt.ylabel('Fuel Consumption (ml/s)')
            plt.grid(True)
            plt.savefig(os.path.join(self.output_dir, 'fuel_consumption_plot.png'))
    
    def summarize_metrics(self, data):
        """Print a summary of key metrics."""
        # Extract dataframes
        vehicle_df = data['vehicle_data']
        global_df = data['global_metrics']
        
        # Summary statistics
        summary = {
            'average_density': global_df['density'].mean(),
            'average_flow': global_df['flow'].mean(),
            'average_speed': global_df['avg_speed'].mean(),
            'average_fuel_consumption': vehicle_df['fuel_consumption'].mean() if not vehicle_df.empty else 0
        }
        
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

if __name__ == "__main__":
    try:
        print("Starting traffic analysis...")
        
        # Check if SUMO_HOME is set
        if 'SUMO_HOME' not in os.environ:
            print("Error: SUMO_HOME environment variable is not set")
            print("Please set SUMO_HOME to your SUMO installation directory")
            sys.exit(1)
            
        # Check if config file exists
        config_file = "osm.sumocfg"
        if not os.path.exists(config_file):
            print(f"Error: Configuration file not found: {config_file}")
            print("Please make sure the file exists in the current directory")
            sys.exit(1)
            
        # Initialize analyzer
        print(f"Initializing analyzer with config: {config_file}")
        analyzer = TrafficAnalyzer(
            sumo_config=config_file,
            output_dir="results/"
        )
        
        # Run analysis without GUI
        print("Starting analysis...")
        data, summary = analyzer.run_analysis(gui=False)  # Disable GUI for headless simulation
        
        if summary:
            print("\nSummary of metrics:")
            for metric, value in summary.items():
                print(f"{metric}: {value:.4f}")
        else:
            print("No summary data available - analysis may have failed")
                
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
