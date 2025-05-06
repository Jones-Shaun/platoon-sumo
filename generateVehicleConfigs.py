"""
This script generates different traffic scenarios for SUMO using the SUMO Traffic Simulation Framework.
It creates a configuration file for each scenario type (platoon_only, light_traffic, heavy_traffic) and
saves them in the specified directory.
It also generates a simpla.xml file for platoon analysis using the SUMO Traffic Simulation Framework.
"""
import dataclasses
import os
import sys

# Import sumolib - make sure your Conda environment is activated and SUMO is installed
# and SUMO_HOME is set correctly for sumolib to function fully.
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))


import sumolib
from pathlib import Path, PurePath


@dataclasses.dataclass
class PlatoonGenerator:
    """
    Class to generate different traffic scenarios for SUMO using the SUMO Traffic Simulation Framework.
    It creates a traffic demand configuration file for each scenario type (platoon_only, light_traffic, heavy_traffic) and
    a simpla.xml file for platooning.
    """
    # Define paths
    target_dir = Path.cwd()
    generated_path = Path.cwd() / "generated_configs"
    simpla_path: PurePath = generated_path / "simpla" # Use generated_path for consistency

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Base SUMO files
    base_path = Path.cwd() / "osm"
    base_net: str = str(base_path / "osm.net.xml") # Convert Path to string for use in config files
    base_config: str = str(base_path / "osm.sumocfg") # Convert Path to string

    # Output directory for analysis results (though not directly used in this script's output paths)
    output_dir: str = "platoon_analysis"

    # Default platoon parameters
    platoon_size: int = 5
    platoon_duration: int = 300 # Not currently used in flow definition, but kept
    platoon_start_time: int = 0 # Not currently used in flow definition, but kept

    # Scenario type (default)
    scenario_type: str = "platoon_only"

    # Simpla configuration XML as a string
    SIMPLA_CONFIG = """<?xml version="1.0" encoding="UTF-8"?>
    <configuration>
        <vehicleSelectors value="truck"/>  <maxVehicleLength value="12.0"/>
        <maxPlatoonGap value="10.0"/>
        <catchupHeadway value="2.0"/>
        <platoonSplitTime value="3.0"/>

        <managedLanes value=""/>
        <mingap value="0.5"/>
        <catchupSpeed value="0.15"/>  <switchImpatienceFactor value="1.0"/>

        <lcMode value="597"/>
        <speedFactor value="1.0"/>
        <verbosity value="3"/>
        <vTypeMap original="truck" leader="truck_platoon_leader" follower="truck_platoon_follower"/>
    </configuration>"""

    # Dictionary to hold route file content strings
    route_files: dict = None

    def generate_traffic_scenario(self, base_net_path=Path.cwd() / "osm" / "osm.net.xml"):
        """
        Generate different traffic scenarios for comparison using simpla.

        Args:
            base_net_path (Path): Path to the base network file.

        Returns:
            Path: Path to the generated configurations directory.
        """
        # Verify network file exists
        if not base_net_path.exists():
            raise FileNotFoundError(f"Network file not found: {base_net_path}")

        # Define the main route edges
        # These are hardcoded for now based on your provided lists
        northbound_edges = [
            "228470926", "1318032192", "1318032193", "1318032191#0", "228463837", "173228852"
        ]

        southbound_edges = [
            "116044310#0", "173228850#0", "173228850#0-AddedOffRampEdge", "173228850#1", "228463846#2",
        ]

        eastbound_edges = [
            # Add eastbound edges if needed
        ]

        westbound_edges_1 = [
            "-713034546", "-711663927#1", "-711663927#0", "-319510213#1", "-319510213#0",
            "228463831#0", "8824804#0", "8824804#1-AddedOnRampEdge", "8824804#1",
            "319510214#0", "319510214#1", "319510214#2"
        ]

        # Convert 50 MPH to m/s (approx 22.352 m/s)
        speed_limit = 22.352

        num_platoons = 1 # Default number of platoons
        while True:
            # Ask how many platoons will be generated
            try:
                num_platoons_input = input(f"Enter the number of platoons to generate (default is {num_platoons}): ")
                if not num_platoons_input:
                    break # Use default if input is empty
                num_platoons_input = int(num_platoons_input)
                if num_platoons_input > 0:
                    num_platoons = num_platoons_input
                    break
                print("Please enter a positive number.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        platoon_elements = []
        # Generate flow elements for each platoon
        for i in range(num_platoons):
            # Depart time offset to space out platoons
            depart_offset = (i + 1) * 40
            platoon_elements.append(
                f'<flow id="truck_platoon_{i}" type="truck" route="main_route" begin="{depart_offset}" number="{self.platoon_size if self.platoon_size else 5}" departLane="0" departSpeed="{speed_limit}" period="1"/>'
            )

        # Join the platoon elements into a single string for embedding in the routes file
        platoon_elements_str = '\n    '.join(platoon_elements)

        # Join the northbound edges into a single string for the route definition
        northbound_edges_str = ' '.join(northbound_edges)

        # Define the route file content for each scenario
        self.route_files = {
            'platoon_only': f"""<routes>
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>

    <route id="main_route" edges="{northbound_edges_str}"/>
    {platoon_elements_str}
</routes>""", # Use triple quotes for multi-line strings

            'light_traffic': f"""<routes>
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>

    <route id="main_route" edges="{northbound_edges_str}"/>
    <flow id="light_flow" type="car" route="main_route" begin="0" end="3600" period="12" departLane="random" departSpeed="max"/>

    {platoon_elements_str}
</routes>""",

            'heavy_traffic': f"""<routes>
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>

    <route id="main_route" edges="{northbound_edges_str}"/>
    <flow id="heavy_flow_cars" type="car" route="main_route" begin="0" end="3600" period="2" departLane="random" departSpeed="max"/>

    {platoon_elements_str}
</routes>"""
        }

        scenario_name = f"{self.scenario_type}_scenario"
        traffic_dir = self.generated_path / "traffic"
        traffic_dir.mkdir(parents=True, exist_ok=True)
        routes_file = traffic_dir / f"{scenario_name}_routes.xml"
        config_file = traffic_dir / f"{scenario_name}.sumocfg"

        # Create route file with different settings based on scenario
        if self.scenario_type in self.route_files: # Check if scenario_type is a valid key
            with open(routes_file, 'w') as f:
                f.write(self.route_files[self.scenario_type])
        else:
             print(f"Warning: Unknown scenario type '{self.scenario_type}'. No route file generated.")


        # Create config file that includes simpla
        # Ensure paths in the config file are correctly formatted for SUMO
        with open(config_file, 'w') as f:
            f.write(
                f"""<?xml version="1.0" encoding="UTF-8"?>
    <configuration>
        <input>
            <net-file value="{base_net_path}"/>
            <route-files value="{routes_file}"/>
            <additional-files value="{Path.cwd() / "osm" /"osm.poly.xml.gz"}"/>
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
    </configuration>"""
            )

        # Ensure the simpla directory exists and write the simpla.xml
        self.simpla_path.mkdir(parents=True, exist_ok=True)
        with open(self.simpla_path / "simpla.xml", 'w') as f:
            f.write(self.SIMPLA_CONFIG)

        return self.generated_path # Return the path to the generated configs directory


if __name__ == "__main__":
    try:
        # Get user input for platoon size
        platoon_size_input = None # Initialize to None
        while True:
            try:
                platoon_size_str = input("Enter desired platoon size (3-10) or press Enter for default (5): ")
                if not platoon_size_str:
                    break # Use default (None) if input is empty
                platoon_size_input = int(platoon_size_str)
                if 3 <= platoon_size_input <= 10:
                    break
                print("Please enter a number between 3 and 10.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")

        # Generate different traffic scenarios
        scenarios = ["platoon_only", "light_traffic", "heavy_traffic"]
        for scenario in scenarios:
            print(f"\nGenerating {scenario} scenario...")
            try:
                # Pass the user-provided platoon size to the PlatoonGenerator instance
                pa = PlatoonGenerator(scenario_type=scenario, platoon_size=platoon_size_input)
                config_path = pa.generate_traffic_scenario()
                print(f"Scenario configurations saved to: {config_path}")

            except Exception as e:
                print(f"Error generating {scenario} scenario: {e}")
                # Continue to the next scenario even if one fails
                continue

    except Exception as e:
        print(f"Fatal error during scenario generation: {e}")
        sys.exit(1)

