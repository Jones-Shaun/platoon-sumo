#README

GROUP: TRUCK-TRAIN
George Mason University's CS690 Connected and Autonomous Vehicles Final Project

Project is so far scoped to simulating a platoon of trucks on a highway map in sumo to gain insightful metrics on truck platooning and the benefits of platooning

Future scope is to generate an algorithm that will do spontaneous platooning and V2X communication with environmental factors like traffic lights to maintain integrity of a platoon, an analogy could be a literal truck-train. 

conda create -n simpla_sumo_env python=3.9
conda activate simpla_sumo_env
conda config --add channels conda-forge
conda config --set channel_priority strict
conda install pysumo simpla

run generateScenarios.py
run mainScript.py
output should be in a .csv file in the same directory as mainScript.py
