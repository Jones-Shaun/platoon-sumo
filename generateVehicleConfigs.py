"""
This script generates different traffic scenarios for SUMO using the SUMO Traffic Simulation Framework.
It creates a configuration file for each scenario type (platoon_only, light_traffic, heavy_traffic) and
saves them in the specified directory.
It also generates a simpla.xml file for platoon analysis using the SUMO Traffic Simulation Framework.
"""
import dataclasses
import os
import sys

import sumolib
from pathlib import Path, PurePath


@dataclasses.dataclass
class PlatoonGenerator:
    """
    Class to generate different traffic scenarios for SUMO using the SUMO Traffic Simulation Framework.
    It creates a traffic demand configuration file for each scenario type (platoon_only, light_traffic, heavy_traffic) and
    a simpla.xml file for platooning.
    """
    simpla_path: PurePath = Path.cwd() / "generated_configs" / "simpla"

    target_dir = Path.cwd()
    generated_path = Path.cwd() / "generated_configs"
    target_dir.mkdir(parents=True, exist_ok=True)
    base_path = Path.cwd() / "osm"
    base_net: str = "osm.net.xml"
    base_config: str = "osm.sumocfg"
    output_dir: str = "platoon_analysis"
    platoon_size: int = 5
    platoon_duration: int = 300
    platoon_start_time: int = 0
    scenario_type: str = "platoon_only"

    SIMPLA_CONFIG = """<?xml version="1.0" encoding="UTF-8"?>\n    <configuration>\n        <!-- SPD (Sublane-based Platooning for SUMO Driver) Configuration -->\n\n        <!-- Platoon Attributes -->\n        <vehicleSelectors value="truck"/>  <!-- Only select trucks for platooning -->\n        <maxVehicleLength value="12.0"/>\n        <maxPlatoonGap value="10.0"/>\n        <catchupHeadway value="2.0"/>\n        <platoonSplitTime value="3.0"/>\n\n        <!-- Platoon Management -->\n        <managedLanes value=""/>\n        <mingap value="0.5"/>\n        <catchupSpeed value="0.15"/>  <!-- % of driving speed -->\n        <switchImpatienceFactor value="1.0"/>\n\n        <!-- Platoon Operation -->\n        <lcMode value="597"/>\n        <speedFactor value="1.0"/>\n        <verbosity value="3"/>\n        <vTypeMap original="truck" leader="truck_platoon_leader" follower="truck_platoon_follower"/>\n    </configuration>"""
    route_files: dict = None

    def generate_traffic_scenario(self, base_net=Path.cwd() / "osm" / "osm.net.xml"):
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
        # try:
        #     net = sumolib.net.readNet(base_net)
        #     # Get main route edges (highway type)
        #     main_edges = [edge.getID() for edge in net.getEdges()
        #                   if edge.getType() in ['highway.primary_link', 'highway.primary', 'highway.secondary',
        #                                         'highway.secondary_link']]
        #     if not main_edges:
        #         raise ValueError("No valid highway edges found in network")
        # except Exception as e:
        #     raise RuntimeError(f"Failed to load network: {e}")
        
        # Define the main route to be the northbound fairfax county parkway edges
        main_edges = [
            "228470926",  # First
            "1318032192", # Second
            "1318032193", # Third
            "1318032191#0", # Fourth
            "228463837", # Fifth
            "173228852"   # Last
        ]
            

        speed_limit = 22.352


        self.route_files = {
            'platoon_only': f'<routes>\n    <!-- Vehicle types for truck platoons -->\n    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>\n    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>\n    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>\n    \n    <!-- Create truck platoons -->\n    <route id="main_route" edges="{' '.join(main_edges)}"/>\n    <flow id="truck_platoon" type="truck" route="main_route" begin="0" number="{platoon_size if platoon_size else 5}" departLane="0" departSpeed="{speed_limit}" period="1"/>\n</routes>',
            'light_traffic': f'<routes>\n    <!-- Vehicle types -->\n    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>\n    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>\n    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>\n    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>\n    \n    <!-- Truck platoons -->\n    <route id="main_route" edges="{' '.join(main_edges)}"/>\n    <flow id="truck_platoon" type="truck" route="main_route" begin="0" number="{platoon_size if platoon_size else 5}" departLane="0" departSpeed="{speed_limit}" period="1"/>\n    \n    <!-- Light traffic: 300 vehicles/hour (1 every 12 seconds) -->\n    <flow id="light_flow" type="car" route="main_route" begin="10" end="3600" period="12" departLane="random" departSpeed="max"/>\n</routes>',
            'heavy_traffic': f'<routes>\n    <!-- Vehicle types -->\n    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>\n    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>\n    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>\n    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>\n    \n    <!-- Truck platoons -->\n    <route id="main_route" edges="{' '.join(main_edges)}"/>\n    <flow id="truck_platoon" type="truck" route="main_route" begin="0" number="{platoon_size if platoon_size else 5}" departLane="0" departSpeed="{speed_limit}" period="1"/>\n    \n    <!-- Heavy traffic: 1800 vehicles/hour (1 every 2 seconds) -->\n    <flow id="heavy_flow_cars" type="car" route="main_route" begin="10" end="3600" period="2" departLane="random" departSpeed="max"/>\n</routes>'
        }

        scenario_name = f"{self.scenario_type}_scenario"
        traffic_dir = self.generated_path / "traffic"
        traffic_dir.mkdir(parents=True, exist_ok=True)
        routes_file = traffic_dir / f"{scenario_name}_routes.xml"
        config_file = traffic_dir / f"{scenario_name}.sumocfg"
        # Convert 50 MPH to m/s (22.352 m/s)

        # Create route file with different settings based on scenario
        if self.scenario_type in self.route_files.keys():
            # Define vehicle types compatible with simpla
            with open(routes_file, 'w') as f:
                f.write(self.route_files[self.scenario_type])

        # Create config file that includes simpla
        with open(config_file, 'w') as f:
            f.write(
                f'<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n    <configuration>\n        <input>\n            <net-file value=\"{base_net}\"/>\n            <route-files value=\"{routes_file}\"/>\n            <additional-files value=\"{Path.cwd() / "osm" /"osm.poly.xml.gz"} \"/>\n        </input>\n        <time>\n            <begin value=\"0\"/>\n            <end value=\"3600\"/>\n        </time>\n        <processing>\n            <lateral-resolution value=\"0.13\"/>\n        </processing>\n        <report>\n            <verbose value=\"true\"/>\n            <no-step-log value=\"true\"/>\n        </report>\n        <gui_only>\n            <start value=\"true\"/>\n        </gui_only>\n        <random_number>\n            <seed value=\"23423\"/>\n        </random_number>\n    </configuration>')

        self.simpla_path.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
        with open(self.simpla_path / "simpla.xml", 'w') as f:
            f.write(self.SIMPLA_CONFIG)
        return self.generated_path


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

        # Generate different traffic scenarios
        scenarios = ["platoon_only", "light_traffic", "heavy_traffic"]
        for scenario in scenarios:
            print(f"\nGenerating {scenario} scenario...")
            try:
                pa = PlatoonGenerator(scenario_type=scenario, platoon_size=platoon_size)
                config_path = pa.generate_traffic_scenario()
                print(f"Scenario configurations saved to: {config_path}")

            except Exception as e:
                print(f"Error in {scenario} scenario: {e}")
                continue

    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

