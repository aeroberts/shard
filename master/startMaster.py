from paxos import ClientAddress
from master import Master
import argparse

# Initializes master and connect predetermined clusters
# Takes command line arguments

# Read config file to start master, pass into master __init__()

#master = Master(command line arguments)

parser = argparse.ArgumentParser(prog='startCluster')
parser.add_argument('numFails', help='The number of acceptable failures')
parser.add_argument('configFile', help='config file listing host ip port pairs indexed by replica id')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debug printing')
parser.add_argument('-fc', '--filterClient', action='store_true', help='Drop first response to client with filter for key')
parser.add_argument('-fl', '--filterLeader', action='store_true', help='Drop first request to leader with filter for key')
args = parser.parse_args()

configData = None
with open(args.configFile, 'r') as configFile:
    configData = configFile.readlines()

assert(configData is not None)

# Creates array of arrays of ClientAddress-s
shardAddresses = [[ClientAddress(a.split(',')[0], a.split(',')[1]) for a in line] for line in configData[3:]]
master = Master(configData[0], configData[1], configData[2], shardAddresses)

# If -fl or -fc, modify master here

master.serve()
