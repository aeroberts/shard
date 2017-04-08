import random # REMOVE
from shard import ShardData
import helpers
import socket
from paxos import ClientAddress
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

    # Maps shard id to current message in flight
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

    def fromClient(self, addr):
        for sd in self.sidToSData.itervalues():
            if sd.containsAddr(addr):
                return False

        return True

    def serve(self):
        # Loop on receiving udp messages
        while True:
            data, addr = self.msock.recvfrom(1024)  # buff size 1024 byte
            self.handleMessage(data, addr)

    def handleMessage(self, data, addr):
        # Check if from client or replica
        addr = list(addr)
        addr = ClientAddress(addr[0], addr[1])
        if self.fromClient(addr):
            self.handleClientMessage(data, addr)
        else:
            self.handleClusterMessage(data, addr)

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
        messageType,csn = masterMessages.unpackClientMessage(data)
        # Hash key to determine replica

