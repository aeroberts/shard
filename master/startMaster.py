from paxos import ClientAddress
from paxos import paxosHelpers
from master import Master
import argparse

# Initializes master and connect predetermined clusters
# Takes command line arguments

# Read config file to start master, pass into master __init__()

#master = Master(command line arguments)

parser = argparse.ArgumentParser(prog='startCluster')
parser.add_argument('configFile', help='config file listing host ip port pairs indexed by replica id')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debug printing')
parser.add_argument('-fc', '--filterClient', action='store', help='Drop first response to client with filter for key')
parser.add_argument('-fl', '--filterLeader', action='store', help='Drop first request to leader with filter for key')
parser.add_argument('-r', '--dropRandom', action='store', help='Randomly drop all sent messages dropRandom% of the time')
parser.add_argument('-nq', '--noQueue', action='store', help='No messages from the queue for the initial cluster idea will be sent from the message queue')
args = parser.parse_args()
paxosHelpers.sendMessage.dropRandom = False

# Test case command line flag handling
if args.dropRandom is not None:
    paxosHelpers.sendMessage.dropRandom = args.dropRandom
else:
    paxosHelpers.sendMessage.dropRandom = False

with open(args.configFile, 'r') as configFile:
    configData = configFile.readlines()

assert(configData is not None)


masterAddress = configData[0].split(" ", 1)
masterIP = masterAddress[0]
masterPort = int(masterAddress[1])
numShards = int(configData[1])

filterLeader = args.filterLeader
filterClient = args.filterClient

# Creates array of arrays of ClientAddress-s
shardAddresses = [[ClientAddress(a.split(',')[0], a.split(',')[1]) for a in line.split(" ")] for line in configData[2:]]

for clusterList in shardAddresses:
    for shardAddress in clusterList:
        shardAddress.port = shardAddress.port.rstrip("\n")

master = Master(masterIP, masterPort, numShards, shardAddresses, FC=filterClient, FL=filterLeader)

# If -fl or -fc, modify master here
# More testing command line flags handled here
if args.noQueue is not None:
    try:
        nq = int(args.noQueue)
        if nq > numShards:
            print "NQ must be less than number of shards"
            exit()

        master.setNoQueue(nq)
    except TypeError:
        print "-nq must pass int"
        exit()

master.serve()
