import random # REMOVE
from helpers import ShardData
import helpers
import socket
from paxos import ClientAddress,MessageTypes
from helpers import masterMessages

maxHashVal = 340282366920938463463374607431768211455

class Master:
    # Master Metadata
    numShards = None
    numFailures = None
    masterSeqNum = None

    # Master Networking
    masterIP = None
    masterPort = None
    msock = None

    # List of sid in sorted order MUST be sorted after inserting an element
    sidList = None

    # Map from shard id to queue of messages for a specific shard
    sidToMQ = None

    # Map from shard id to shard data for each shard
    sidToSData = None

    # Maps a client (indexed by address) to its message in a specific queue.  May not be necessary (used for timeout)
    clientToClientMessage = None

    # Maps shard id to current ClientRequest in flight
    sidToMessageInFlight = None

    def __init__(self, masterIP, masterPort, numShards, numFailures, shardAddresses):
        self.numShards = numShards
        self.numFailures = numFailures
        self.masterSeqNum = 0
        self.sidList = []
        self.sidToMQ = []
        self.sidToSData = []
        self.clientToClientMessage = []
        self.sidToMessageInFlight = []

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

        if len(self.sidToMQ[requestSID]) == 0:
            masterMessages.sendRequestForward(clientRequest, self.sidToSData[requestSID], self.masterSeqNum)
            self.masterSeqNum += 1
            self.sidToMessageInFlight[requestSID] = clientRequest

        else:
            self.sidToMQ[requestSID].append(clientRequest)

    def handleClusterMessage(self, data, addr, receivedSID):
        # Respond to client
        clientRequest = self.sidToMessageInFlight[receivedSID]
        self.sidToMessageInFlight[receivedSID] = None

        mType,msn,smrv,key,val = masterMessages.unpackClusterResponse(data)

        if not self.validateResponse(clientRequest, key, val):
            return

        # Reply to client
        masterMessages.sendResponseToClient(clientRequest, key, val)

        # Dequeue and send next message for this cluster
        nextRequest = self.sidToMQ[receivedSID].pop[0]
        shardData = self.sidToSData[receivedSID]

        nextRequest.masterSeqNum = self.masterSeqNum
        masterMessages.sendRequestForward(self.msock, nextRequest, shardData, self.masterSeqNum)
        self.sidToMessageInFlight[receivedSID] = nextRequest
        self.masterSeqNum += 1



    def validateResponse(self, clientRequest, mType, key, val):
        if key == None: # Error
            print "Master received error from cluster:",val
            return False

        if key != clientRequest.key:
            print "Master recieved mismatched key on cluster response:",clientRequest.key,"and",key
            return False

        if mType == MessageTypes.PUT and val != clientRequest.value:
            print "Master received mismatched val on PUT response",clientRequest.value,"and",val
            return False

