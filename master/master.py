import socket

import helpers
from helpers import ShardData
from master import masterMessages
from paxos import ClientAddress,MessageTypes
from paxos import messages

maxHashVal = 340282366920938463463374607431768211455

class Master:
    # Master Metadata
    numShards = None
    numFailures = None
    quorumSize = None
    masterSeqNum = None

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
        self.sidList = []
        self.sidToMQ = []
        self.sidToSData = []
        self.clientToClientMessage = []
        self.sidToMessageInFlight = []
        self.msnToRequest = []

        if FC != None:
            self.filterClient = FC
            self.hasFilteredClient = False
        else:
            self.hasFilteredClient = True

        if FL != None:
            self.filterLeader = FL
            self.hasFilteredLeader = False
        else:
            self.hasFilteredLeader = True

        shardNo = 1
        evenShardDistro = maxHashVal / numShards
        for shard in shardAddresses:
            # Creates initial hash divisions
            sid = evenShardDistro * shardNo
            shardNo += 1

            self.sidList.append(sid)
            self.sidToMQ[sid] = []
            self.sidToSData[sid] = ShardData(sid, shard) # Change to use actual hash function
            self.sidToMessageInFlight[sid] = None

        assert(shardNo == numShards)
        self.sidList.sort()

        # Bind to socket
        self.msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.msock.bind((masterIP, masterPort))

        return


    def getAssociatedSID(self, key): # This can be way better
        sIndex = 0
        hashKey = helpers.hashKey(key)

        # [-----1------2--(2.2 hash value)----3------4-----5]
        # shard 3 handles 2.2, so iterate until we hit a larger shard id, then return it
        while self.sidList[sIndex] < hashKey:
                sIndex += 1
                if sIndex == len(self.sidList):
                    return self.sidList[0]

        return self.sidList[sIndex]

    def fromCluster(self, addr):
        for sid,sd in self.sidToSData.iteritems():
            if sd.containsAddr(addr):
                return sid

        return False

    def serve(self):
        # Loop on receiving udp messages
        while True:
            data, addr = self.msock.recvfrom(1024)  # buff size 1024 byte
            self.handleMessage(data, addr)

    def handleMessage(self, data, addr):
        # Check if from client or replica
        addr = list(addr)
        addr = ClientAddress(addr[0], addr[1])

        receivedSID = self.fromCluster(addr)
        if receivedSID == False:
            self.handleClientMessage(data, addr)
        else:
            self.handleClusterMessage(data, addr, receivedSID)

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

        # Unpack message
        clientRequest = masterMessages.unpackClientMessage(data, addr)
        requestSID = self.getAssociatedSID(clientRequest.key)
        shardData = self.sidToSData[requestSID]

        # Client timed out
        if addr in self.clientToClientMessage:
            shardMRV = shardData.mostRecentView
            crView = self.clientToClientMessage[addr].assignedView

            # Check if the MRV is equal to the current view, if it is, then broadcast the current in flight
            # Else, the timeout occurred on a previous view, and we've already timeout / switched because of another message
            if shardMRV > crView:
                self.clientToClientMessage[addr].assignedView = shardMRV

            elif shardMRV == crView and not shardData.viewChanging:
                # Set viewChanging to True and broadcast
                self.sidToSData[requestSID].viewChanging = True
                masterMessages.broadcastRequestForward(
                    self.msock, self.sidToMessageInFlight[requestSID], shardData, self.masterSeqNum
                )
                return # May not need this?

        # No messages currently queued or in flight, send this one
        if self.sidToMessageInFlight[requestSID] == None:
            assert(len(self.sidToMq[requestSID]) == 0)
            clientRequest.masterSeqNum = self.masterSeqNum
            self.msnToResponseCount[self.masterSeqNum] = clientRequest

            # Send if not filtering for test case
            if self.hasFilteredLeader is True or self.filterLeader != clientRequest.key:
                masterMessages.sendRequestForward(clientRequest, shardData)
                self.hasFilteredLeader = True

            self.masterSeqNum += 1
            self.sidToMessageInFlight[requestSID] = clientRequest

        else:
            self.sidToMQ[requestSID].append(clientRequest)

    def handleClusterMessage(self, message, addr, receivedSID):
        masterSeqNum, shardMRV, learnedKV = messages.unpackPaxosResponse(message)

        if masterSeqNum not in self.msnToResponseCount:
            print "Error, master sequence number missing on response from paxos"

        clientRequest = self.msnToRequest[masterSeqNum]
        shardData = self.sidToSData[receivedSID]

        if not self.validateResponse(clientRequest, learnedKV[0], learnedKV[1], learnedKV[2]):
            return

        if clientRequest.receivedCount == 0:
            clientRequest.receivedView = shardMRV

        clientRequest.receivedCount += 1

        if shardMRV != clientRequest.receivedView:
            print "Warning: Received mismatched view from response"

        if clientRequest.receivedCount == 1:
            assert(clientRequest == self.sidToMessageInFlight[receivedSID])

            # Reply to client
            # Send if not filtering for test case
            if self.hasFilteredClient is True or self.filterClient != clientRequest.key:
                masterMessages.sendResponseToClient(clientRequest, learnedKV[1], learnedKV[2])
                self.hasFilteredClient = True

            self.clientToClientMessage.pop(clientRequest.clientAddress)

            # Check if there are any messages in the queue.  If not, return.
            if len(self.sidToMQ[receivedSID]) <= 0:
                return

            # Dequeue and send next message for this cluster
            nextRequest = self.sidToMQ[receivedSID].pop[0]

            nextRequest.masterSeqNum = self.masterSeqNum
            self.msnToResponseCount[self.masterSeqNum] = nextRequest

            # Send if not filtering for test case
            if self.hasFilteredLeader is True or self.filterLeader != clientRequest.key:
                masterMessages.sendRequestForward(nextRequest, shardData)
                self.hasFilteredLeader = True

            self.masterSeqNum += 1
            self.sidToMessageInFlight[receivedSID] = nextRequest

        # Check to see if view change occurred
        if shardMRV > shardData.mostRecentView:
            assert(shardData.viewChanging == True)
            shardData.viewChanging = False
            shardData.mostRecentView = shardMRV

        elif shardMRV == shardData.mostRecentView:
            assert(shardData.viewChanging == False)

        elif shardMRV < shardData.mostRecentView:
            print "Warning: received older view for current request"

    def validateResponse(self, clientRequest, learnedType, learnedKey, learnedVal, masterSeqNum):
        if learnedKey is None:
            print "No key learned for master request"
            return False

        if learnedKey != clientRequest.key:
            print "Master received mismatched key from cluster response. Expected: " + clientRequest.key + \
                  ". Received: " + learnedKey
            return False

        if learnedType == MessageTypes.PUT and learnedVal != clientRequest.value:
            print "Master received mismatched value on PUT response. Expected: " + clientRequest.value + \
                  ". Received: " + learnedVal
            return False

        if masterSeqNum != clientRequest.masterSeqNum:
            print "Master received mismatched msn on response. Expected: " + clientRequest.masterSeqNum + \
                  ". Received: " + masterSeqNum
            return False

        return True

