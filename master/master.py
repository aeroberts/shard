import socket
from random import randint

import helpers
import math
from helpers import ShardData
from paxos import paxosHelpers
import masterMessages
from paxos import ClientAddress,MessageTypes
from paxos import messages
from paxos import paxosHelpers

maxHashVal = paxosHelpers.getMaxHashVal()

class Master:
    # Master Metadata
    numShards = None
    numFailures = None
    quorumSize = None
    masterSeqNum = None
    addShardSIDKey = None

    # Command Line Args
    filterClient = None
    hasFilteredClient = None
    filterLeader = None
    hasFilteredLeader = None

    # Master Networking
    masterIP = None
    masterPort = None
    msock = None

    # List of sid in sorted order MUST be sorted after inserting an element
    # Used in determining the associated sid for a key and for add_shard
    sidList = None

    # Map from shard id to queue of messages for a specific shard
    # Used to queue messages when receiving from client and dequeue when receive from replica
    sidToMQ = None

    # Map from shard id to shard data for each shard
    sidToSData = None

    # Maps a client (indexed by address) to its message in a specific queue.
    # Used for timeout
    clientToClientMessage = None

    # Maps shard id to current ClientRequest in flight
    # Used to check if a message is currently in flight, and broadcast when timeout occurs
    sidToMessageInFlight = None

    # Tracks the master sequence number to the request send to a shard.  Used for counting f+1 responses.
    msnToRequest = None

    def __init__(self, masterIP, masterPort, numShards, numFailures, shardAddresses, FC=None, FL=None):
        self.numShards = numShards
        self.numFailures = numFailures
        self.quorumSize = numFailures+1
        self.masterSeqNum = 0
        self.addShardSeqNum = 0
        self.addShardSIDKey = 0
        self.sidList = []
        self.sidToMQ = {}
        self.sidToSData = {}
        self.clientToClientMessage = {}
        self.sidToMessageInFlight = {}
        self.msnToRequest = {}

        if FC != None:
            self.filterClient = FC
            self.hasFilteredClient = False
            print "Master will drop first response to client with key'" + self.filterClient + "'"
        else:
            self.hasFilteredClient = True

        if FL != None:
            self.filterLeader = FL
            self.hasFilteredLeader = False
            print "Master will drop first request with key '" + self.filterLeader + "' to leader"
        else:
            self.hasFilteredLeader = True

        print "\n"

        shardNo = 0

        # maxHashVal = 24+1 = 25
        # evenShardDistro = floor(25/3) = 8
        # numShards = 3
        # shard 1: 0-7 = shardNo * evenDistro to (shardNo+1 * evenDistro)-1
        # shard 2: 8-15
        # shard 3: 16-23
        # shard 4: 24
        evenShardDistro = int(math.floor((maxHashVal+1) / numShards))
        for shard in shardAddresses:
            # Creates initial hash divisions
            lowerBound = evenShardDistro * shardNo
            sid = (evenShardDistro * (shardNo + 1)) - 1
            shardNo += 1

            self.sidToSData[sid] = ShardData(sid, lowerBound, shard)
            self.sidList.append(sid)
            self.sidToMQ[sid] = []
            self.sidToMessageInFlight[sid] = None

        assert(shardNo == numShards)
        self.sidList.sort()

        # Bind to socket
        self.msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.msock.bind((masterIP, masterPort))

        return

    def getAssociatedSID(self, key): # This can be way better
        sIndex = 0
        hashKey = paxosHelpers.hashKey(key)

        # [-----1------2--(2.2 hash value)----3------4-----5---]
        # shard 3 handles 2.2, so iterate until we hit a larger shard id, then return it
        while self.sidList[sIndex] < hashKey:
                sIndex += 1
                if sIndex == len(self.sidList):
                    return self.sidList[0]

        return self.sidList[sIndex]

    def fromCluster(self, clientAddress):
        for sid, sd in self.sidToSData.iteritems():
            if sd.containsClientAddress(clientAddress):
                return sid

        return False

    def addShard(self, shardAddrs, clientRequest):
        # Generate new hash
        self.addShardSIDKey += randint(0, 20)
        newSID = paxosHelpers.hashKey(self.addShardSIDKey)

        osSID = self.getAssociatedSID(newSID)
        oldShard = self.sidToSData[osSID]
        lowerBound = oldShard.lowerBound
        oldShard.lowerBound = newSID+1

        # Initialize the new data structures for this new shard
        self.sidToSData[newSID] = ShardData(newSID, lowerBound, shardAddrs)
        self.sidList.append(newSID)
        self.sidList.sort()
        self.sidToMQ[newSID] = []
        self.sidToMessageInFlight[newSID] = clientRequest

        # Transition all requests on old message queue to new message queue that have key with newSID as associatedSID
        # Change their views (to -1?)
        for osClientRequest in self.sidToMQ[osSID]:
            if self.getAssociateSID(osClientRequest.key) == newSID:
                self.sidToMQ[newSID].append(osClientRequest)
                osClientRequest.transferRequestReset()

        self.sidToMQ[osSID][:] = [x for x in self.sidToMQ[osSID] if self.getAssociatedSID(x.key) == osSID]



        return lowerBound, newSID, oldShard.mostRecentView, oldShard.replicaAddresses
        # put newSID into self.sidToSData, create a queue for it, BUT DON'T SEND MESSAGES TO NEW SID
        # Send [newSID+1, oldSID] to oldShard

        # calculate lower/upper bounds
        # get associated shard to take from
        # return AddrString and view

        return

    def serve(self):
        # Loop on receiving udp messages
        while True:
            data, addr = self.msock.recvfrom(1024)  # buff size 1024 byte
            self.handleMessage(data, addr)

    def handleMessage(self, data, addr):

        print "Master received message: " + str(data)

        # Check if from client or replica
        addr = list(addr)
        addr = ClientAddress(addr[0], addr[1])

        receivedSID = self.fromCluster(addr)
        if receivedSID == False:
            self.handleClientMessage(data, addr)
        else:
            self.handleClusterMessage(data, receivedSID)

        #
        # If from client
        # Check if client has timed out (already has submitted message)
        #   If timeout, handle (track timeout for a cluster, and reset on broadcast.  old view timeouts don't matter)
        #       Only care if timeout message is on current view?
        # If not timeout, add to message queue for specific replica, send if that queue is empty
        #
        # If from replica
        # If response from client, respond to client
        #   Remove client from clientToClientMessage
        #   Send next message to paxos cluster
        # If addShard response, figure out what to do

    def handleClientMessage(self, data, addr):

        print "Master handling client message (",addr.ip, " ",addr.port,")"

        # Unpack message
        clientRequest = masterMessages.unpackClientMessage(self, data, addr)

        if clientRequest.type != MessageTypes.ADD_SHARD:
            requestSID = self.getAssociatedSID(clientRequest.key)
            shardData = self.sidToSData[requestSID]

        # Client timed out
        if addr in self.clientToClientMessage:

            if clientRequest.type == MessageTypes.ADD_SHARD:
                leaderAddr = clientRequest.key.split(" ", 1)
                leaderAddr = leaderAddr.split(",")
                leaderAddr = ClientAddress(leaderAddr[0], leaderAddr[1])
                for SD in shardData:
                    if SD.containsClientAddress(leaderAddr):
                        requestSID = SD.sid
                        shardData = SD

            print "Master: Client timed out"

            shardMRV = shardData.mostRecentView
            crView = self.clientToClientMessage[addr].assignedView

            # Check if the MRV is equal to the current view, if it is, then broadcast the current in flight
            # Else, the timeout occurred on a previous view, and we've already timeout / switched because of another message
            if shardMRV > crView:
                self.clientToClientMessage[addr].assignedView = shardMRV

            elif shardMRV == crView:
                # Set viewChanging to True and broadcast
                masterMessages.broadcastRequestForward(
                    self.msock, self.sidToMessageInFlight[requestSID], shardData, self.sidToMessageInFlight[requestSID].masterSeqNum
                )
                self.sidToSData[requestSID].mostRecentView += 1

            return # I think we want to return in all cases
        else:

            print "Master: Handling request (first time this request was received)"

            self.clientToClientMessage[addr] = clientRequest

            if clientRequest.type == MessageTypes.ADD_SHARD:
                shardAddrs = clientRequest.getAddShardAddrs()
                lowerBound, newShardSID, osMRV, osAddrList = self.addShard(shardAddrs, clientRequest)
                clientRequest.transformAddShard(self.masterSeqNum, lowerBound, newShardSID, osMRV, osAddrList)
                self.masterSeqNum += 1

                masterMessages.sendRequestForward(self.msock, clientRequest, self.sidToSData[newShardSID])
                return

        # No messages currently queued or in flight, send this one
        if self.sidToMessageInFlight[requestSID] is None:

            print "No messages currently in flight"

            assert(len(self.sidToMQ[requestSID]) == 0)
            clientRequest.masterSeqNum = self.masterSeqNum
            self.msnToRequest[self.masterSeqNum] = clientRequest
            print "assigned MSN:",self.masterSeqNum

            # Send if not filtering for test case
            if self.hasFilteredLeader is True or self.filterLeader != clientRequest.key:
                masterMessages.sendRequestForward(self.msock, clientRequest, shardData)
            else:
                print "Filtering leader\n"
                self.hasFilteredLeader = True

            self.masterSeqNum += 1
            self.sidToMessageInFlight[requestSID] = clientRequest

        else:

            print "Appending message"

            self.sidToMQ[requestSID].append(clientRequest)

    def handleClusterMessage(self, message, receivedSID):

        print "handleClusterMessage: " + str(message)

        masterSeqNum, receivedMRV, requestData = messages.unpackPaxosResponse(message)

        if masterSeqNum not in self.msnToRequest:
            print "Error, master sequence number missing on response from paxos"

        clientRequest = self.msnToRequest[masterSeqNum]
        shardData = self.sidToSData[receivedSID]

        if clientRequest.receivedCount == 0:
            clientRequest.receivedView = receivedMRV

        clientRequest.receivedCount += 1

        if receivedMRV != clientRequest.receivedView:
            print "Warning: Received mismatched view from response"

        if clientRequest.receivedCount == 1:
            assert(clientRequest == self.sidToMessageInFlight[receivedSID])

            # TODO: Double check this
            # Master received response for currently in flight request to shard receivedSID, so clear it from the map
            self.sidToMessageInFlight[receivedSID] = None

            # Reply to client
            # Send if not filtering for test case
            if self.hasFilteredClient is True or self.filterClient != clientRequest.key:
                masterMessages.sendResponseToClient(self.msock, clientRequest, requestData)
            else:
                self.hasFilteredClient = True
                print "Filtered Client"

            self.clientToClientMessage.pop(clientRequest.clientAddress)

            # Check if there are any messages in the queue.  If not, return.
            if len(self.sidToMQ[receivedSID]) <= 0:
                return

            # De-queue and send next message for this cluster
            nextRequest = self.sidToMQ[receivedSID].pop[0]
            nextRequest.masterSeqNum = self.masterSeqNum
            self.msnToRequest[self.masterSeqNum] = nextRequest

            # Send if not filtering for test case
            if self.hasFilteredLeader is True or self.filterLeader != clientRequest.key:
                masterMessages.sendRequestForward(self.msock, nextRequest, shardData)
            else:
                self.hasFilteredLeader = True

            self.masterSeqNum += 1
            self.sidToMessageInFlight[receivedSID] = nextRequest

        # Check to see if view change occurred
        if receivedMRV > shardData.mostRecentView:
            assert(shardData.viewChanging == True)
            shardData.viewChanging = False
            shardData.mostRecentView = receivedMRV

        elif receivedMRV == shardData.mostRecentView:
            assert(shardData.viewChanging == False)

        elif receivedMRV < shardData.mostRecentView:
            print "Warning: received older view for current request"
