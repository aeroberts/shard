import argparse
import socket

from helpers import MessageTypes
from helpers import messages
from replica import *

#--------------------------------------------------------
#
#            Replica Message Handling Functions
#
#--------------------------------------------------------

def handleReplicaMessage(replica, ca, type, seqNum, msg, addr, associatedView):
    if associatedView < replica.currentView and type != MessageTypes.SUGGESTION_ACCEPT:
        if debugMode: print "WARNING: Dropping message because it is from a past view:", type
        return

    if associatedView > replica.currentView:
        replica.viewChange(associatedView)

    if type == MessageTypes.PREPARE_REQUEST:
        if debugMode: print "Received PREPARE_REQUEST"
        propNum = messages.unpackPrepareRequest(msg)
        recvRid = replica.getRid(addr)
        replica.handlePrepareRequest(ca, recvRid, seqNum, propNum)

    elif type == MessageTypes.PREPARE_ALLOWDISALLOW:
        if debugMode: print "Received PREPARE_ALLOWDISALLOW"

        if seqNum in replica.log:
            if debugMode: print "Received PREPARE_ALLOWDISALLOW for learned value"
            return

        if not replica.isPrimary:
            if debugMode: print "WARNING: Handling PREPARE_ALLOWDISALLOW when no longer primary for LSN " + str(seqNum)
            return

        acceptorRid = replica.getRid(addr)
        messageData = messages.unpackPrepareAllowDisallow(msg)
        replica.handlePrepareResponse(seqNum, messageData, acceptorRid)

    elif type == MessageTypes.SUGGESTION_REQUEST:
        if debugMode: print "Received SUGGESTION_REQUEST"
        recvRid = replica.getRid(addr)
        messageData = messages.unpackSuggestionRequest(msg)
        replica.handleSuggestionRequest(ca, recvRid, messageData[1], seqNum, messageData[0], messageData[2:])

    elif type == MessageTypes.SUGGESTION_ACCEPT:
        if debugMode: print "Received SUGGESTION_ACCEPT"

        if seqNum in replica.log:
            if debugMode: print "Received SUGGESTION_ACCEPT for learned value"
            return

        senderRid = replica.getRid(addr)
        messageData = messages.unpackSuggestionAccept(msg)
        replica.handleSuggestionAccept(senderRid, ca, messageData[1], seqNum, messageData[0], messageData[2:])

    elif type == MessageTypes.SUGGESTION_FAILURE:
        if debugMode: print "Received SUGGESTION_FAILURE"

        if seqNum in replica.log:
            if debugMode: print "Received SUGGESTION_FAILURE for learned value"
            return

        messageData = messages.unpackSuggestionFailure(msg)
        replica.handleSuggestionFail(seqNum, messageData[0], messageData[1], messageData[2:])

    elif type == MessageTypes.HIGHEST_OBSERVED:
        if debugMode: print "Received HIGHEST_OBSERVED"
        senderRid = replica.getRid(addr)
        replica.handleHighestObserved(senderRid, seqNum, associatedView)

    elif type == MessageTypes.HOLE_REQUEST:
        if debugMode: print "Received HOLE_REQUEST"
        senderRid = replica.getRid(addr)
        replica.handleHoleRequest(senderRid, seqNum)

    elif type == MessageTypes.HOLE_RESPONSE:
        if debugMode: print "Received HOLE_RESPONSE"
        holeLogEntry = messages.unpackHoleResponse(msg)
        clientId = holeLogEntry[0]
        clientSeqNum = holeLogEntry[1]
        requestKV = holeLogEntry[2:]

        senderRid = replica.getRid(addr)
        replica.handleHoleResponse(senderRid, seqNum, clientId, clientSeqNum, requestKV)

    else:
        print "Error: Invalid replica message received -- malformed type", msg

#--------------------------------------------------------
#
#            Client Message Handling Functions
#
#--------------------------------------------------------

def handleClientMessage(replica, pid, csn, clientView, msg, clientAddress):
    if pid == None:
        print "Error: Malformed client request"
        return

    if clientView > replica.currentView:
        replica.viewChange(clientView)

    if clientView == replica.currentView and not replica.isPrimary:
        if debugMode: print "View change!"
        replica.viewChange(replica.currentView+1)

        if not replica.isPrimary:
            if debugMode: print "Not master after view change, drop client request"
            return

    elif clientView < replica.currentView:
        if debugMode: print "Warning: Stale client"
        if not replica.isPrimary:
            # Drop the message, let the current primary handle it
            return

        # Received as broadcast, client has out of date view, don't need to view change
        # complete request if master, update client view

    if replica.reconciling:
        replica.addProposeToQueue(clientAddress, csn, msg)
        return

    # If CID-CSN has already been learned, send a VALUE_LEARNED message back to client
    clientId = clientAddress.toClientId()
    if clientId in replica.learnedValues:
        if csn in replica.learnedValues[clientId]:
            messages.sendValueLearned(replica, clientAddress, csn)

    # If currently trying to learn this CID-CSN, return because we don't need to re-propose
    if clientId in replica.learningValues:
        if csn in replica.learningValues[clientId]:
            if debugMode: print "WARNING: Old primary alive and received request from client twice " \
                   "(must have been broadcast), everyone thinks we're dead"
            replica.viewChange(replica.currentView+1, True)

    replica.beginPropose(clientAddress, csn, msg)

#--------------------------------------------------------
#
#            Base message handling
#
#--------------------------------------------------------

# Handles message of "data" from addr
# Should be moved to replica / master file
def handleMessage(data, addr, replica):
    if handleMessage.toKill:
        handleMessage.messagesReceived += 1
        if handleMessage.messagesReceived >= handleMessage.killNum and replica.rid == 0:
            exit()

    # Determine if message comes from replicate / master
    # Or from client
    # If TYPE = Client type message (GET/PUT/DELETE/

    addr = list(addr)
    if addr in replica.hosts:
        type,seqNum,cIP,cPort,associatedView,msg = messages.unpackReplicaMessage(data)
        ca = messages.ClientAddress(cIP, cPort)
        handleReplicaMessage(replica, ca, int(type), int(seqNum), msg, addr, associatedView)

    else:
        pid,csn,clientView,msg = messages.unpackClientMessage(data)
        clientAddress = messages.ClientAddress(addr[0], addr[1])
        handleClientMessage(replica, pid, csn, clientView, msg, clientAddress)

    return

#---------------------------------------------------------
#
#                     Loop on recv
#
#---------------------------------------------------------

parser = argparse.ArgumentParser(prog='send')
parser.add_argument('numFails', help='The number of acceptable failures')
parser.add_argument('replicaId', help='This replica\'s Id')
parser.add_argument('hostFile', help='config file listing host ip port pairs indexed by replica id')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debug printing')
parser.add_argument('-s', '--skip', action='store', help='Skip this sequence number when you are primary')
parser.add_argument('-k', '--kill', action='store', help='Kill original primary after kill many messages are recv')
parser.add_argument('-q', '--quiet', action='store_true', help='Silences printing no-ops when printing the log')
args = parser.parse_args()

debugMode = args.debug
skipNum = args.skip

if skipNum is not None:
    skipNum = int(skipNum)

printNoops = True
if args.quiet is not None and args.quiet:
    printNoops = False

handleMessage.toKill = False
handleMessage.messagesReceived = 0
handleMessage.killNum = 0
if args.kill is not None:
    handleMessage.toKill = True
    handleMessage.killNum = int(args.kill)
else:
    handleMessage.toKill = False

# Initialize the process
replica = Replica(int(args.numFails), int(args.replicaId), messages.getHosts(args.hostFile),
                  int(0), skipNum, printNoops, debugMode)

print "Initialized replica at:", replica.ip, replica.port, "with quorum size", replica.quorumSize

rsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rsock.bind((replica.ip, replica.port))
replica.sock = rsock

# Loop on receiving udp messages
while True:
    data, addr = rsock.recvfrom(1024) # buff size 1024 byte
    handleMessage(data, addr, replica)
    # time.sleep(1)
