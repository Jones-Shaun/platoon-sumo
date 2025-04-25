
import traci
# import sumolib 


traci.start(["sumo", "-c", "osm.sumocfg"])

step = 0
while step < 1000: 
    traci.simulationStep() 
    step+= 1 
traci.close()
