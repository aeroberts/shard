import socket

import helpers
from helpers import ShardData
from master import masterMessages
from paxos import ClientAddress,MessageTypes

maxHashVal = 340282366920938463463374607431768211455

class Master:
    # Master Metadata
    numShards = None
    numFailures = None
    quorumSize = None
    masterSeqNum = None

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

    def __init__(self, masterIP, masterPort, numShards, numFailures, shardAddresses):
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

        if self.sidToMessageInFlight[requestSID] == None:
            assert(len(self.sidToMq[requestSID]) == 0)
            clientRequest.masterSeqNum = self.masterSeqNum
            self.msnToResponseCount[self.masterSeqNum] = clientRequest
            masterMessages.sendRequestForward(clientRequest, shardData)
            self.masterSeqNum += 1
            self.sidToMessageInFlight[requestSID] = clientRequest

        else:
            self.sidToMQ[requestSID].append(clientRequest)

    def handleClusterMessage(self, data, addr, receivedSID):
        mType,msn,smrv,key,val = masterMessages.unpackClusterResponse(data)

        if not msn in self.msnToResponseCount:
            print "Error, msn missing on response from paxos"

        clientRequest = self.msnToRequest[msn]
        shardData = self.sidToSData[receivedSID]

        if not self.validateResponse(clientRequest, key, val):
            return

        if clientRequest.receivedCount == 0:
            clientRequest.receivedView = smrv

        clientRequest.receivedCount += 1

        if smrv != clientRequest.receivedView:
            print "Warning: Received mismatched view from response"

        if clientRequest.receivedCount == 1:
            assert(clientRequest == self.sidToMessageInFlight[receivedSID])

            # Reply to client
            masterMessages.sendResponseToClient(clientRequest, key, val)
            self.clientToClientMessage.pop(clientRequest.clientAddress)

            # Check if there are any messages in the queue.  If not, return.
            if len(self.sidToMQ[receivedSID]) <= 0:
                return

            # Dequeue and send next message for this cluster
            nextRequest = self.sidToMQ[receivedSID].pop[0]

            nextRequest.masterSeqNum = self.masterSeqNum
            self.msnToResponseCount[self.masterSeqNum] = nextRequest
            masterMessages.sendRequestForward(nextRequest, shardData)
            self.masterSeqNum += 1
            self.sidToMessageInFlight[receivedSID] = clientRequest

        # Check to see if view change occurred
        if smrv > shardData.mostRecentView:
            assert(shardData.viewChanging == True)
            shardData.viewChanging = False
            shardData.mostRecentView = smrv

        elif smrv == shardData.mostRecentView:
            assert(shardData.viewChanging == False)

        elif smrv < shardData.mostRecentView:
            print "Warning: Recived older view for current request"

    def validateResponse(self, clientRequest, mType, key, val, msn):
        if key == None: # Error
            print "Master received error from cluster:",val
            return False

        if key != clientRequest.key:
            print "Master recieved mismatched key on cluster response:",clientRequest.key,"and",key
            return False

        if mType == MessageTypes.PUT and val != clientRequest.value:
            print "Master received mismatched val on PUT response",clientRequest.value,"and",val
            return False

        if msn != clientRequest.masterSeqNum:
            print "Master recieved mismatched msn on response",clientRequest.masterSeqNum,"and",msn
            return False

