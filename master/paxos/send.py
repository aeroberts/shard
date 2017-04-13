import argparse
import socket

from helpers import MessageTypes
from helpers import messages
from helpers import shardMessages
from replica import *

#--------------------------------------------------------
#
#            Replica Message Handling Functions
#
#--------------------------------------------------------

def handleReplicaMessage(replica, ca, type, seqNum, message, addr, associatedView):
    if associatedView < replica.currentView and type != MessageTypes.SUGGESTION_ACCEPT:
        if debugMode: print "WARNING: Dropping message because it is from a past view:", type
        return

    if associatedView > replica.currentView:
        replica.viewChange(associatedView)

    if type == MessageTypes.PREPARE_REQUEST:
        if debugMode: print "Received PREPARE_REQUEST"
        propNum = messages.unpackPrepareRequestData(message)
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
        messageData = messages.unpackPrepareAllowDisallowData(message)
        replica.handlePrepareResponse(seqNum, messageData[0], messageData[1], messageData[2:], acceptorRid)

    elif type == MessageTypes.SUGGESTION_REQUEST:
        if debugMode: print "Received SUGGESTION_REQUEST"
        recvRid = replica.getRid(addr)
        messageData = messages.unpackSuggestionRequestData(message)
        replica.handleSuggestionRequest(ca, recvRid, seqNum, messageData[0], messageData[1], messageData[2:])

    elif type == MessageTypes.SUGGESTION_ACCEPT:
        if debugMode: print "Received SUGGESTION_ACCEPT"

        if seqNum in replica.log:
            if debugMode: print "Received SUGGESTION_ACCEPT for learned value"
            return

        senderRid = replica.getRid(addr)
        messageData = messages.unpackSuggestionAcceptData(message)
        replica.handleSuggestionAccept(senderRid, ca, messageData[1], seqNum, messageData[0], messageData[2:])

    elif type == MessageTypes.SUGGESTION_FAILURE:
        if debugMode: print "Received SUGGESTION_FAILURE"

        if seqNum in replica.log:
            if debugMode: print "Received SUGGESTION_FAILURE for learned value"
            return

        messageData = messages.unpackSuggestionFailureData(message)
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
        holeLogEntry = messages.unpackHoleResponseData(message)
        clientId = holeLogEntry[0]
        clientSeqNum = holeLogEntry[1]
        requestString = str(holeLogEntry[2]) + "," + str(holeLogEntry[3])
        senderRid = replica.getRid(addr)
        replica.handleHoleResponse(senderRid, seqNum, clientId, clientSeqNum, requestString)

    else:
        print "Error: Invalid replica message received -- malformed type", message

#--------------------------------------------------------
#
#            Client Message Handling Functions
#
#--------------------------------------------------------
def handleClientMessage(replica, masterSeqNum, receivedShardMRV, clientAddress, messageType, messageDataString):
    if receivedShardMRV > replica.currentView:
        replica.viewChange(receivedShardMRV)

    if receivedShardMRV == replica.currentView and not replica.isPrimary:
        if debugMode: print "View change!"
        replica.viewChange(replica.currentView+1)

        if not replica.isPrimary:
            if debugMode: print "Not primary after view change, drop client request"
            return

    elif receivedShardMRV < replica.currentView:
        if debugMode: print "Warning: Stale client"
        if not replica.isPrimary:
            return  # Drop the message, let the current primary handle it
        # Received as broadcast, client has out of date view, don't need to view change
        # complete request if master, update client view

    # Transform received START_SHARD into internal paxos BEGIN_STARTUP message
    if messageType == MessageTypes.START_SHARD:
        messageType = MessageTypes.BEGIN_STARTUP
        reqData = messages.unpackStartShard(messageDataString)
        messageDataString = reqData[0] + "," + reqData[1] + "," + reqData[2] + "," + reqData[3]

    # Transform received SEND_KEYS_REQUEST into internal paxos SEND_KEYS message
    elif messageType == MessageTypes.SEND_KEYS_REQUEST:
        messageType = MessageTypes.SEND_KEYS
        reqData = messages.unpackSendKeysRequest(messageDataString)
        messageDataString = reqData[0] + "," + reqData[1] + "," + reqData[2] + "," + reqData[3]

    # Transform received SEND_KEYS_RESPONSE into internal paxos BATCH_PUT message
    elif messageType == MessageTypes.SEND_KEYS_RESPONSE:
        messageType = MessageTypes.BATCH_PUT
        if replica.isPrimary:
            replica.stopRequestTimeout()

    elif messageType == MessageTypes.KEYS_LEARNED:
        # Stop learner timeout (double check that you have one I guess?)
        # On receiving KEYS_LEARNED, sock.close() and t.kill(), then remove sid from sidToThreadSock
        messageType = MessageTypes.CHANGE_BOUNDS
        SID = messageDataString
        replica.stopTimeout(SID)

    # Value (action) to eventually learn: "Action,Data"
    actionToLearnString = str(messageType) + "," + str(messageDataString)
    if replica.reconciling:
        replica.addProposeToQueue(clientAddress, masterSeqNum, actionToLearnString)
        return

    # If CID-CSN has already been learned, send a VALUE_LEARNED message back to client
    clientId = clientAddress.toClientId()
    if clientId in replica.learnedValues:
        if masterSeqNum in replica.learnedValues[clientId]:
            print("ERROR: Received request on already learned MSN")
            assert(0 & "Received request on already learned MSN")
            logSeqNum = replica.learnedValues[clientId][masterSeqNum]
            learnedValue = replica.log[logSeqNum][0]
            learnedType, learnedString = learnedValue.split(",", 1)
            messages.respondValueLearned(replica, clientAddress, masterSeqNum, receivedShardMRV, learnedType, learnedString)

    # If currently trying to learn this CID-CSN, return because we don't need to re-propose
    if clientId in replica.learningValues:
        if masterSeqNum in replica.learningValues[clientId]:
            if debugMode: print "WARNING: Old primary alive and received request from client twice " \
                   "(must have been broadcast), everyone thinks we're dead"
            replica.viewChange(replica.currentView+1, True)

    replica.beginPropose(clientAddress, masterSeqNum, actionToLearnString)

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
        type, seqNum, cIP, cPort, associatedView, messageDataString = messages.unpackReplicaMetadata(data)
        ca = messages.ClientAddress(cIP, cPort)
        handleReplicaMessage(replica, ca, int(type), int(seqNum), messageDataString, addr, associatedView)

    else:
        messageType, masterSeqNum, shardMRV, messageDataString = messages.unpackClientMessageMetadata(data)
        clientAddress = messages.ClientAddress(addr[0], addr[1])
        handleClientMessage(replica, masterSeqNum, shardMRV, clientAddress, messageType, messageDataString)


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
