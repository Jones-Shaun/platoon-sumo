"""
This script generates multiple traffic scenarios for SUMO by iterating
through combinations of platoon size, number of platoons, and traffic type.
It creates a SUMO configuration file (.sumocfg) and a routes file (.rou.xml)
for each combination and saves them in a dedicated directory.
It also generates a single simpla.xml file.

The ranges and options for scenario generation are defined as constants at the top.
"""
import dataclasses
import os
import sys
from pathlib import Path, PurePath
import itertools # Import itertools to easily generate combinations



if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))

# --- Scenario Generation Constants ---
# Define the ranges and options for the variables as constants
# PLATOON_SIZES = range(2, 7)         # 2 to 6 inclusive
# PLATOON_SIZES = range(2, 4)         # 2 to 6 inclusive
PLATOON_SIZES = [2, 4, 6]
# PLATOON_SIZES = [2]

# NUM_PLATOONS_OPTIONS = range(0, 51, 10) # 0, 10, 20, 30, 40, 50
NUM_PLATOONS_OPTIONS = [10, 25, 40]  # 0, 10, 20, 30, 40, 50
TRAFFIC_TYPES = ["light_traffic", "heavy_traffic"]
# TRAFFIC_TYPES = ["light_traffic"]
# Define the base directory name for generated configurations
GENERATED_CONFIGS_DIR_NAME = "auto_generated_configs"
# --- End Scenario Generation Constants ---


@dataclasses.dataclass
class ScenarioGenerator:
    """
    Class to generate a single traffic scenario configuration (routes and sumocfg).
    Modified from PlatoonGenerator to accept parameters programmatically.
    """
    # Define base paths using the constant directory name
    target_base_dir = Path.cwd() # Base directory for generated configs
    generated_path: Path = target_base_dir / GENERATED_CONFIGS_DIR_NAME
    simpla_configs_path: Path = generated_path / "simpla" # Path for simpla.xml

    # Ensure the base generated configs directory exists
    generated_path.mkdir(parents=True, exist_ok=True)
    # Ensure the simpla configs directory exists
    simpla_configs_path.mkdir(parents=True, exist_ok=True)


    # Base SUMO files
    base_path = Path.cwd() / "osm"
    base_net: str = str(base_path / "osm.net.xml") # Convert Path to string for use in config files

    # Scenario parameters (will be set programmatically when creating an instance)
    platoon_size: int = 5
    num_platoons: int = 0 # Default to 0 platoons if not specified
    scenario_type: str = "light_traffic" # Default traffic type

    # Simpla configuration XML as a string (kept generic)
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


    def generate_files(self, base_net_path=Path.cwd() / "osm" / "osm.net.xml"):
        """
        Generates the routes and sumocfg files for a single scenario combination.

        Args:
            base_net_path (Path): Path to the base network file.
        """
        # Verify network file exists
        if not base_net_path.exists():
            raise FileNotFoundError(f"Network file not found: {base_net_path}")

        # Define the main route edges (hardcoded as in the original script)
        northbound_edges = [
            "228470926", "1318032192", "1318032193", "1318032191#0", "228463837", "173228852"
        ]
        # Join the northbound edges into a single string for the route definition
        northbound_edges_str = ' '.join(northbound_edges)

        # Convert 50 MPH to m/s (approx 22.352 m/s)
        speed_limit = 22.352

        # Generate flow elements for each platoon if num_platoons > 0
        platoon_elements = []
        if self.num_platoons > 0:
            for i in range(self.num_platoons):
                # Depart time offset to space out platoons
                depart_offset = (i + 1) * 40
                platoon_elements.append(
                    f'<flow id="truck_platoon_{i}" type="truck" route="main_route" begin="{depart_offset}" number="{self.platoon_size}" departLane="0" departSpeed="{speed_limit}" period="1"/>'
                )

        # Join the platoon elements into a single string for embedding in the routes file
        platoon_elements_str = '\n    '.join(platoon_elements)

        # Define the route file content based on scenario type
        # Note: Platoon_only logic is now integrated into the traffic type logic
        # based on num_platoons.
        if self.scenario_type == 'light_traffic':
            route_file_content = f"""<routes>
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>

    <route id="main_route" edges="{northbound_edges_str}"/>
    <flow id="light_flow" type="car" route="main_route" begin="0" end="3600" period="12" departLane="random" departSpeed="max"/>

    {platoon_elements_str}
</routes>"""
        elif self.scenario_type == 'heavy_traffic':
             route_file_content = f"""<routes>
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="car" accel="1.5" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="{speed_limit}" color="0.5,0.5,0.5"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>

    <route id="main_route" edges="{northbound_edges_str}"/>
    <flow id="heavy_flow_cars" type="car" route="main_route" begin="0" end="3600" period="2" departLane="random" departSpeed="max"/>

    {platoon_elements_str}
</routes>"""
        else:
            # Handle the case where scenario_type is not light or heavy traffic
            # If num_platoons > 0, it's effectively a platoon_only scenario on its own
            # If num_platoons == 0, it's an empty scenario or needs different base traffic
             route_file_content = f"""<routes>
    <vType id="truck" accel="1.0" decel="3.0" sigma="0.5" length="10" minGap="3" maxSpeed="{speed_limit}" color="1,1,0"/>
    <vType id="truck_platoon_leader" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="2" maxSpeed="{speed_limit}" color="0.8,0.4,0"/>
    <vType id="truck_platoon_follower" accel="1.0" decel="3.0" sigma="0.0" length="10" minGap="0.5" maxSpeed="{speed_limit}" color="0.8,0.8,0"/>

    <route id="main_route" edges="{northbound_edges_str}"/>
    {platoon_elements_str}
</routes>"""
             if self.num_platoons == 0:
                 print(f"Warning: Scenario type '{self.scenario_type}' with 0 platoons will generate an empty route file.")


        # Define filenames based on parameters
        routes_filename = f"routes_ps{self.platoon_size}_np{self.num_platoons}_traffic_{self.scenario_type}.rou.xml"
        config_filename = f"config_ps{self.platoon_size}_np{self.num_platoons}_traffic_{self.scenario_type}.sumocfg"

        routes_file_path = self.generated_path / routes_filename
        config_file_path = self.generated_path / config_filename

        # Create route file
        with open(routes_file_path, 'w') as f:
            f.write(route_file_content)

        # Create config file
        with open(config_file_path, 'w') as f:
            f.write(
                f"""<?xml version="1.0" encoding="UTF-8"?>
    <configuration>
        <input>
            <net-file value="{base_net_path}"/>
            <route-files value="{routes_file_path}"/>
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

        # Generate simpla.xml only once in the simpla subdirectory
        simpla_xml_path = self.simpla_configs_path / "simpla.xml"
        if not simpla_xml_path.exists():
            with open(simpla_xml_path, 'w') as f:
                f.write(self.SIMPLA_CONFIG)


# --- Main script logic to generate multiple configurations ---
if __name__ == "__main__":
    print("Generating multiple SUMO traffic scenarios...")

    # Use itertools.product to get all combinations of the defined constants
    for platoon_size, num_platoons, traffic_type in itertools.product(PLATOON_SIZES, NUM_PLATOONS_OPTIONS, TRAFFIC_TYPES):
        print(f"\nGenerating scenario: Platoon Size={platoon_size}, Num Platoons={num_platoons}, Traffic={traffic_type}")

        try:
            # Create an instance of ScenarioGenerator for the current combination
            generator = ScenarioGenerator(
                platoon_size=platoon_size,
                num_platoons=num_platoons,
                scenario_type=traffic_type
            )

            # Generate the files for this scenario
            generator.generate_files()

            print("Scenario files generated successfully.")

        except Exception as e:
            print(f"Error generating scenario (PS={platoon_size}, NP={num_platoons}, Traffic={traffic_type}): {e}")
            # Continue to the next combination even if one fails
            continue

    print("\nFinished generating all specified traffic scenarios.")
