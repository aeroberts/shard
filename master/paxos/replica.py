import math
import socket
import threading

from acceptor import Acceptor
from helpers import messages
from helpers import MessageTypes, shardMessages
from proposer import Proposer
from helpers import broadcastSendKeyRequest, broadcastSendKeyResponse, unpackIPPortData, unpackBatchKeyValues


class Replica:
    """Used to maintain replica metadata"""
    numFails = -1
    rid = -1
    quorumSize = -1
    numReplicas = -1

    # Keeps track of primary
    isPrimary = False
    currentView = None

    # Sequence numbers within the log and system
    highestInFlight = -1
    lowestSeqNumNotLearned = -1

    # Flags
    skipNum = -1
    printNoops = False

    # Network Information
    hosts = []
    ip = -1
    port = -1
    sock = None

    # View change state
    reconciling = False
    lastViewReconciled = -1
    highestObservedReceivedSet = None
    highestReconcileObserved = -1
    holeRequestsSent = None
    reconcilesReceived = None
    reconcileQueue = None

    debugMode = False

    # The actual values we have learned
    log = {}
    kvStore = {}

    lowerKeyBound = None
    upperKeyBound = None

    # Sequence number to proposer
    proposers = {}

    # Sequence number to acceptor metadata
    acceptors = {}

    # Sequence number to replicas that have accepted
    accepted = {}

    # Learned and learning tracking
    learnedValues = None
    learningValues = None

    # Tracks SID of Cluster taking / receiving keys from
    sidToThreadSock = None

    # During startup, nsLeader will send SEND_KEYS_REQUEST and begin timeout thread and sock
    requestThreadSock = None # CAN ONLY HAVE THIS ONCE

    def __init__(self, numFails, rid, hosts, currentView, skipNum, printNoops, debugMode):

        # Basic system metadata
        self.numFails = numFails
        self.rid = rid
        self.hosts = hosts
        self.ip = hosts[rid][0]
        self.port = int(hosts[rid][1])
        self.numReplicas = len(hosts)

        # View metadata
        self.currentView = int(currentView)
        self.reconciling = False
        self.lastViewReconciled = -1
        self.highestObservedReceivedSet = set()
        self.highestReconcileObserved = -1
        self.holeRequestsSent = set()
        self.reconcilesReceived = {}
        self.reconcileQueue = []

        self.debugMode = debugMode

        # Tracking metadata. ClientId -> set(CSN's learned)
        self.learnedValues = {}
        self.learningValues = {}

        # Flags
        self.skipNum = skipNum
        self.printNoops = printNoops

        if self.rid == currentView:
            self.isPrimary = True

        # Calculate quorum size
        self.quorumSize = int(math.floor((self.numReplicas/2)+1))

        # Initialize log and learnedValues (necessary if we are recovering from crash)
        self.playStableLog()

        # Initialize sidToThreadSock to be empty dict
        self.sidToThreadSock = {}
        self.requestThreadSock = None

    def getNextSequenceNumber(self):
        self.highestInFlight += 1

        if self.skipNum is not None and self.skipNum == self.highestInFlight:
            self.highestInFlight += 1

        return self.highestInFlight

    def getRid(self, addr):
        return self.hosts.index(addr)

    def getKeysInRange(self, lowerBound, upperBound):
        kvToSend = {}
        for key,value in self.kvStore:
            if lowerBound <= key and key <= upperBound:
                kvToSend[key] = value

    def stopTimeout(self, SID, viewChangedAwayFrom=False):
        if SID in self.sidToThreadSock:
            thread, sock = self.sidToThreadSock[SID]
            sock.close()
            thread.kill()
            self.sidToThreadSock.pop(SID)
        else:
            if viewChangedAwayFrom:
                return

            print "ERROR: No thread/sock at specified SID"

    def stopRequestTimeout(self, viewChangedAwayFrom=False):
        if self.requestThreadSock is not None:
            thread, sock = self.requestThreadSock
            sock.close()
            thread.kill()
            self.requestThreadSock = None
        else:
            if viewChangedAwayFrom:
                return

            print "ERROR: No REQUESTOR thread/sock on nsLeader"

    def stopTimeoutThreads(self):
        for sid in self.sidToThreadSock:
            self.stopTimeout(sid, True)

        self.stopRequestTimeout(True)

    def printLog(self, printInFlight=False):
        maxLearned = max(self.log.keys(), key=int)
        print "============ Printing Log ============"
        for i in xrange(0, max(self.highestInFlight + 1, maxLearned)):
            if i in self.log:
                val = self.log[i][0]
                if val is not None:
                    val = val.rstrip("\n")
                    print val

                if val is None and self.printNoops:
                    print "No-op (Explicitly learned No-op)"

            elif i < maxLearned and self.printNoops:
                print "No-op (Skipped, possibly learned later due to failure)"

            elif i > maxLearned and printInFlight:
                print "In flight"

        print "\n"

    def appendStableLog(self, logSeqNum, cid, csn, msg):
        logFileName = '/tmp/paxos_' + str(self.rid)

        if msg is None:
            msg = "None"

        logData = str(logSeqNum) + "," + str(cid) + "," + str(csn) + " " + str(msg.rstrip("\n")) + "\n"
        with open(logFileName, "a+") as logFile:
            logFile.write(logData)

    def playStableLog(self):
        logFileName = '/tmp/paxos_' + str(self.rid)
        maxLearned = -1

        try:
            logIndex = 0
            with open(logFileName, "r+") as logFile:
                entries = [entry.split(" ", 1) for entry in logFile.readlines()]
                for entry in entries:
                    metadata = entry[0].split(",")

                    metadata[0] = int(metadata[0])
                    maxLearned = max(maxLearned, metadata[0])

                    if metadata[1] == "None":
                        metadata[1] = None

                    if metadata[2] != "None":
                        metadata[2] = int(metadata[2])
                    else:
                        metadata[2] = None

                    entry[1] = entry[1].rstrip("\n")
                    if entry[1] == "None":
                        entry[1] = None

                    self.learnValue(metadata[0], metadata[1], metadata[2], entry[1], False)

                    if metadata[1] not in self.learnedValues:
                        self.learnedValues[metadata[1]] = {}
                    self.learnedValues[metadata[1]][metadata[2]] = logIndex
                    logIndex += 1
        except IOError, e:
            if e.errno != 2:
                raise e

        self.highestInFlight = maxLearned

    ###################
    ##  View Change  ##
    ###################

    def viewChange(self, clientView, isAliveOldPrimary=False):
        # View changing, so clear acceptors, proposers (if any), and any learning values because proposer must be dead
        self.acceptors.clear()
        self.learningValues.clear()
        if len(self.proposers):
            if not isAliveOldPrimary:
                print "ERROR: New master already has proposers, clearing proposers"
            self.proposers.clear()

        # Set the view and check if the replica is a primary
        self.currentView = clientView

        if clientView % self.numReplicas == self.rid:
            if self.debugMode: print "I'm the primary!"
            self.isPrimary = True
            self.reconciling = True

        # If this node is not the primary, tell the new primary your highest in flight
        else:
            self.isPrimary = False
            newPrimaryRid = clientView % self.numReplicas

            print "\tView change, not the primary, sending highestObserved to " + str(newPrimaryRid)

            messages.sendHighestObserved(self, newPrimaryRid, self.highestInFlight)

    def addProposeToQueue(self, clientAddress, clientSeqNum, requestString):
        self.reconcileQueue.append((clientAddress, clientSeqNum, requestString))

    def handleHighestObserved(self, recvRid, logSeqNum, reconcileView):
        # Already reconciled this view, ignore the request
        if self.lastViewReconciled == self.currentView:
            return

        # If received a HIGHEST_OBSERVED message from a replica before the broadcast from a client, trigger VC
        if self.currentView < reconcileView:
            self.viewChange(reconcileView)

        # Already reached quorum, only needed f+1
        if reconcileView < self.currentView:
            print "Warning: All failed and we wrapped around while reconciling"
            return

        self.highestReconcileObserved = max(logSeqNum, self.highestReconcileObserved)

        if recvRid not in self.highestObservedReceivedSet:
            self.highestObservedReceivedSet.add(recvRid)

        if len(self.highestObservedReceivedSet) == self.quorumSize - 1:
            self.highestReconcileObserved = max(self.highestReconcileObserved, self.highestInFlight)
            self.highestObservedReceivedSet.clear()
            self.lastViewReconciled = self.currentView
            self.reconcile()

    def reconcile(self):
        if self.debugMode: print "=== Reconciling ============================"
        self.highestInFlight = self.highestReconcileObserved
        for lsn in xrange(0, self.highestReconcileObserved + 1):
            if lsn not in self.log:
                messages.sendHoleRequest(self, lsn)
                self.holeRequestsSent.add(lsn)
        if self.debugMode: print "=== Done sending reconciliation messages ==="

        if len(self.holeRequestsSent) == 0:
            self.endReconciliation()

    def handleHoleRequest(self, recvRid, logSeqNum):
        returnValue = None
        clientId = None
        clientSeqNum = None

        if logSeqNum in self.log:
            logEntry = self.log[logSeqNum]
            returnValue = logEntry[0]
            clientId = logEntry[1]
            clientSeqNum = logEntry[2]

        messages.sendHoleResponse(self, recvRid, logSeqNum, clientId, clientSeqNum, returnValue)

    def handleHoleResponse(self, recvRid, logSeqNum, clientId, clientSeqNum, requestString):
        # If already patched this hole, ignore the message
        if logSeqNum not in self.holeRequestsSent:
            return

        # If patching the hole with a value, set the value and remove it from the hole set
        if requestString is not None:
            self.learnAction(logSeqNum, clientId, clientSeqNum, requestString)

            if logSeqNum in self.reconcilesReceived:
                self.reconcilesReceived.pop(logSeqNum)

            self.holeRequestsSent.remove(logSeqNum)
            if len(self.holeRequestsSent) == 0:
                self.endReconciliation()

            return

        # If first response
        if logSeqNum not in self.reconcilesReceived:
            self.reconcilesReceived[logSeqNum] = set()
            self.reconcilesReceived[logSeqNum].add(recvRid)

        # Else, if not a duplicate response
        elif recvRid not in self.reconcilesReceived[logSeqNum]:
            self.reconcilesReceived[logSeqNum].add(recvRid)

            # Received f+1 responses for this hole, update val if necessary, remove from hole set
            if len(self.reconcilesReceived) == self.quorumSize:
                if logSeqNum not in self.log:
                    self.learnValue(logSeqNum, None, None, None)

                self.reconcilesReceived.pop(logSeqNum)

                self.holeRequestsSent.remove(logSeqNum)
                if len(self.holeRequestsSent) == 0:
                    self.endReconciliation()

    def endReconciliation(self):
        for tuple in self.reconcileQueue:
            if len(tuple) != 3:
                print "ERROR: reconciliation queue tuple size wrong"

            self.beginPropose(tuple[0], tuple[1], tuple[2])

        # WE MADE IT FAM!
        self.reconcileQueue = []
        self.reconciling = False

    #####################################
    #                                   #
    #    Proposer handling functions    #
    #                                   #
    #####################################

    # From CHAT_MESSAGE, SUGGESTION_FAIL, suggestion_allow kill
    def beginPropose(self, clientAddress, clientSeqNum, requestString):
        logSeqNum = self.getNextSequenceNumber()

        proposer = self.createProposer(int(logSeqNum), clientAddress, clientSeqNum, requestString)

        clientId = clientAddress.toClientId()
        if clientId not in self.learningValues:
            self.learningValues[clientId] = set()
        self.learningValues[clientId].add(clientSeqNum)

        proposer.beginPrepareRound(self)

    # Creates a proposer at logSeqNum index if one does not already exist
    def createProposer(self, logSeqNum, clientAddress, clientSeqNum, requestString):
        if logSeqNum in self.proposers:
            print "Error: Proposer already exists"
            return

        self.proposers[logSeqNum] = Proposer(self.rid, self.quorumSize, self.numReplicas,
                                             logSeqNum, clientAddress, clientSeqNum, requestString)
        return self.proposers[logSeqNum]

    def handlePrepareResponse(self, seqNum, recvPropNum, acceptedPropNum, requestData, acceptorRid):
        requestString = str(requestData[0]) + "," + str(requestData[1])
        self.proposers[seqNum].handlePrepareResponse(self, recvPropNum, acceptedPropNum, requestString, acceptorRid)

    def handleSuggestionFail(self, logSeqNum, promisedNum, acceptedPropNum, requestData):
        requestDataString = str(requestData[0]) + "," + str(requestData[1])
        self.proposers[logSeqNum].handleSuggestionFail(promisedNum, acceptedPropNum, requestDataString, self)

    #####################################
    #                                   #
    #    Acceptor handling functions    #
    #                                   #
    #####################################

    def handlePrepareRequest(self, ca, recvRid, logSeqNum, propNum):
        if logSeqNum not in self.acceptors:
            self.acceptors[logSeqNum] = Acceptor()

        self.highestInFlight = max(logSeqNum, self.highestInFlight)
        self.acceptors[logSeqNum].handlePrepareRequest(self, ca, recvRid, logSeqNum, propNum)

    def handleSuggestionRequest(self, ca, recvRid, seqNum, propNum, clientSeqNum, requestData):
        if seqNum not in self.acceptors or self.acceptors[seqNum] is None:
            print "Error, received suggestion request before prepare request for that LSN received (",seqNum,")"

        requestString = str(requestData[0]) + "," + str(requestData[1])
        self.acceptors[seqNum].handleSuggestionRequest(self, ca, recvRid, seqNum, propNum, clientSeqNum, requestString)

    #####################################
    #                                   #
    #    Learner handling functions     #
    #                                   #
    #####################################

    def handleSuggestionAccept(self, senderRid, clientAddress, csn, logSeqNum, acceptedPropNum, requestData):
        requestString = str(requestData[0]) + "," + str(requestData[1])
        # If it was already learned, ignore the extraneous notification
        if logSeqNum in self.log:
            self.killProposerWithRestartIfNecessary(clientAddress, logSeqNum)
            return

        # First acceptance for this sequence number
        if logSeqNum not in self.accepted:
            self.accepted[logSeqNum] = {}

        # First acceptance of a value for this sequence number
        if acceptedPropNum not in self.accepted[logSeqNum]:
            self.accepted[logSeqNum][acceptedPropNum] = set()
            self.accepted[logSeqNum][acceptedPropNum].add(senderRid)

        else:
            # Finds the highest proposal number the sender has accepted
            highestFromSender = -1
            highestPropNum = -1
            for propNum in self.accepted[logSeqNum]:
                highestPropNum = max(highestPropNum, propNum)

                if senderRid in self.accepted[logSeqNum][propNum]:
                    highestFromSender = max(highestFromSender, propNum)

            # If this acceptance message has a higher proposal number than any previous from that acceptor, accept it
            if highestFromSender < acceptedPropNum and highestPropNum <= acceptedPropNum:
                self.accepted[logSeqNum][acceptedPropNum].add(senderRid)

                # If this is the f+1th acceptor to accept at the highest seen proposal number, learn value
                if len(self.accepted[logSeqNum][acceptedPropNum]) == self.quorumSize:
                    self.learnValue(logSeqNum, clientAddress, csn, requestString)

                    # Garbage collect
                    self.accepted[logSeqNum].clear()
                    self.printLog()

                    # While only the primary should, if another replica has a proposer at this lsn, delete it
                    self.killProposerWithRestartIfNecessary(clientAddress, logSeqNum)

    def killProposerWithRestartIfNecessary(self, clientAddress, logSeqNum):
        if logSeqNum not in self.proposers:
            return

        # Re-propose if a different value was learned here or the request came from a different client
        differentReqLearned = (self.log[logSeqNum] != self.proposers[logSeqNum].valueToPropose)
        if self.proposers[logSeqNum].ca != clientAddress or differentReqLearned:
            print "ERROR: This should probably not happen. Two proposers for one sequence number"
            reqStringToPropose = self.proposers[logSeqNum].valueToPropose
            csnToPropose = self.proposers[logSeqNum].clientSequenceNumber
            cidToPropose = self.proposers[logSeqNum].ca
            self.beginPropose(cidToPropose, csnToPropose, reqStringToPropose)

        deleted = self.proposers.pop(logSeqNum, None)

        if deleted is None:
            print "Error: Could not delete proposer at " + logSeqNum

        if not self.isPrimary:
            print "Warning: non-primary had proposer (now deleted)"

    def learnAction(self, logSeqNum, clientAddress, clientSeqNum, learnRequestString, writeToStableLog=True):
        clientId = clientAddress.toClientId()

        # Remove from learning set (only in learning set if primary)
        if self.isPrimary:
            if clientId in self.learningValues:
                if clientSeqNum not in self.learningValues[clientId]:
                    print "ERROR: ClientSeqNum not in learning set for clientId"
                else:
                    self.learningValues[clientId].remove(clientSeqNum)

        # Add to learned set
        if clientId is not None and clientSeqNum is not None:
            if clientId not in self.learnedValues:
                self.learnedValues[clientId] = {}

            self.learnedValues[clientId][clientSeqNum] = logSeqNum

        # Write to log
        self.log[logSeqNum] = list(clientAddress, clientSeqNum, learnRequestString)
        if writeToStableLog:
            self.appendStableLog(logSeqNum, clientId, clientSeqNum, learnRequestString)

        # If the lowest sequence number not yet learned, commit this action and any enabled by its commit
        if logSeqNum == self.lowestSeqNumNotLearned:
            while self.lowestSeqNumNotLearned in self.log:
                self.commitLearnedAction(self.lowestSeqNumNotLearned)
                self.lowestSeqNumNotLearned += 1

    def commitLearnedAction(self, logSeqNum):
        actionContext = self.log[logSeqNum]
        clientAddress = actionContext[0]
        clientSeqNum = actionContext[1]
        learnData = messages.unpackRequestDataString(actionContext[2])

        # TODO: THROW ERROR FOR GET/PUT/DELETE ON KEYS OUT OF BOUNDS

        # GET_REQUEST: learnData = [MessageTypes.GET, Key]
        if learnData[0] == MessageTypes.GET:
            learnKey = str(learnData[1])
            getValue = self.kvStore[learnKey]
            returnData = [learnKey, getValue]
            messages.respondValueLearned(self, clientAddress, clientSeqNum, self.currentView, learnData[0], returnData)

        # PUT_REQUEST: learnData = [MessageTypes.PUT, Key, Value]
        elif learnData[0] == MessageTypes.PUT:
            learnKey = learnData[1]
            learnValue = learnData[2]
            self.kvStore[learnKey] = learnValue
            returnData = [learnKey, 'Success']
            messages.respondValueLearned(self, clientAddress, clientSeqNum, self.currentView, learnData[0], returnData)

        # BATCH_PUT
        elif learnData[0] == MessageTypes.BATCH_PUT:
            self.commitBatchPut(actionContext)

        # DELETE_REQUEST: learnData = [MessageTypes.DELETE, Key]
        elif learnData[0] == MessageTypes.DELETE:
            self.log[logSeqNum] = learnData
            learnKey = learnData[1]
            del self.kvStore[learnKey]
            returnData = [learnKey, 'Success']
            messages.respondValueLearned(self, clientAddress, clientSeqNum, self.currentView, learnData[0], returnData)

        # BEGIN_STARTUP
        elif learnData[0] == MessageTypes.BEGIN_STARTUP:
            self.commitBeginStartup(learnData, clientSeqNum)

        # SEND_KEYS
        elif learnData[0] == MessageTypes.SEND_KEYS:
            # TODO: CHANGE BOUNDS
            self.commitSendKeys(learnData, clientSeqNum)

    ######################
    #  Commit Functions  #
    ######################

    # BATCH_PUT: learnData = [MessageTypes.BATCH_PUT, "Key,Val|Key,Val|...|Key,Val"]
    def commitBatchGet(self, logSeqNum, clientAddress, clientSeqNum, learnData):
        dictToLearn = unpackBatchKeyValues(learnData[2])

        for batchKey in dictToLearn:
            self.kvStore[batchKey] = dictToLearn[batchKey]

        shardMessages.sendKeysLearned(self.sock, self.currentView, clientAddress.ip,
                                      clientAddress.port, clientSeqNum, int(self.upperKeyBound)+1)

    # learnData = [MT.BEGIN_STARTUP, LowerKeyBound, UpperKeyBound, osView, "osIP1,osPort1|...|osIPN,osPortN"]
    def commitBeginStartup(self, learnData, clientSeqNum):
        self.lowerKeyBound = learnData[1]
        self.upperKeyBound = learnData[2]
        # If not master, return
        if not self.isPrimary:
            return

        # Make copies of data
        lowerKeyBound = str(learnData[1])
        upperKeyBound = str(learnData[2])
        osMRV = int(learnData[3])
        nsMRV = int(self.currentView)
        addrList = unpackIPPortData(learnData[4])
        addrString = str(learnData[4])

        # Create socket
        sendKeysRequestSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sendKeysRequestSock.bind((self.ip, self.port * 2))

        # Create thread
        sendKeysRequestThread = threading.Thread(target=broadcastSendKeyRequest,
                                                 args=(sendKeysRequestSock, clientSeqNum, addrList[:], osMRV, nsMRV,
                                                       lowerKeyBound, upperKeyBound, addrString))

        sendKeysRequestThread.start()

        # Store socket and thread to some data structure
        self.requestThreadSock = (sendKeysRequestThread, sendKeysRequestSock)

        # On receiving SEND_KEYS_RESPONSE, sock.close() and t.kill(), then remove sid from sidToThreadSock

    # learnData = [MessageTypes.SEND_KEYS, LowerKeyBound, UpperKeyBound, nsView, "nsIP1,nsPort1|...|nsIPN,nsPortN"]
    def commitSendKeys(self, learnData, clientSeqNum):
        lowerKeyBound = str(learnData[1])
        upperKeyBound = str(learnData[2])
        nsMRV = int(learnData[3])
        osMRV = int(self.currentView)
        addrList = unpackIPPortData(learnData[4])

        # Grab keys in range
        kvToSend = self.getKeysInRange(lowerKeyBound, upperKeyBound)

        # Create socket
        sendKeysResponseSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sendKeysResponseSock.bind((self.ip, self.port * 2 + 1))

        # Create thread t = threading.thread()
        sendKeysResponseThread = threading.Thread(target=broadcastSendKeyRequest,
                                                  args=(sendKeysResponseSock, clientSeqNum,
                                                        addrList[:], osMRV, nsMRV, kvToSend[:]))

        sendKeysResponseThread.start()

        # Store socket and thread to some data structure
        self.sidToThreadSock[upperKeyBound] = (sendKeysResponseThread, sendKeysResponseSock)

        # On receiving KEYS_LEARNED, sock.close() and t.kill(), then remove sid from sidToThreadSock

    # learnData = [ MessageTypes.CHANGE_BOUNDS, updatedLowerKeyBound ]
    def commitChangeBounds(self, learnData):
        self.lowerKeyBound = learnData[1]
