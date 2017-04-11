import math

from acceptor import Acceptor
from helpers import messages
from proposer import Proposer


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

    # Sequence number to proposer
    proposers = {}

    # Sequence number to acceptor metadata
    acceptors = {}

    # Sequence number to replicas that have accepted
    accepted = {}

    # Learned and learning tracking
    learnedValues = None
    learningValues = None

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

    def getNextSequenceNumber(self):
        self.highestInFlight += 1

        if self.skipNum is not None and self.skipNum == self.highestInFlight:
            self.highestInFlight += 1

        return self.highestInFlight

    def getRid(self, addr):
        return self.hosts.index(addr)

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
                        self.learnedValues[metadata[1]] = set()
                    self.learnedValues[metadata[1]].add(metadata[2])
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

    def addProposeToQueue(self, clientAddress, clientSeqNum, msg):
            self.reconcileQueue.append((clientAddress, clientSeqNum, msg))

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

    def handleHoleResponse(self, recvRid, logSeqNum, clientId, clientSeqNum, requestKV):
        # If already patched this hole, ignore the message
        if logSeqNum not in self.holeRequestsSent:
            return

        # If patching the hole with a value, set the value and remove it from the hole set
        if requestKV is not None:
            self.learnValue(logSeqNum, clientId, clientSeqNum, requestKV)

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
    def beginPropose(self, clientAddress, clientSeqNum, kvToPropose):
        logSeqNum = self.getNextSequenceNumber()

        proposer = self.createProposer(int(logSeqNum), clientAddress, clientSeqNum, kvToPropose)

        clientId = clientAddress.toClientId()
        if clientId not in self.learningValues:
            self.learningValues[clientId] = set()
        self.learningValues[clientId].add(clientSeqNum)

        proposer.beginPrepareRound(self)

    # Creates a proposer at logSeqNum index if one does not already exist
    def createProposer(self, logSeqNum, clientAddress, clientSeqNum, kvToPropose):
        if logSeqNum in self.proposers:
            print "Error: Proposer already exists"
            return

        self.proposers[logSeqNum] = Proposer(self.rid, self.quorumSize, self.numReplicas,
                                             logSeqNum, clientAddress, clientSeqNum, kvToPropose)
        return self.proposers[logSeqNum]

    def handlePrepareResponse(self, seqNum, messageData, acceptorRid):
        self.proposers[seqNum].handlePrepareResponse(self, messageData[0], messageData[1], messageData[2:], acceptorRid)

    def handleSuggestionFail(self, logSeqNum, promisedNum, acceptedPropNum, acceptedKV):
        self.proposers[logSeqNum].handleSuggestionFail(promisedNum, acceptedPropNum, acceptedKV, self)

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

    def handleSuggestionRequest(self, ca, recvRid, csn, seqNum, propNum, requestKV):
        if seqNum not in self.acceptors or self.acceptors[seqNum] is None:
            print "Error, received suggestion request before prepare request for that LSN received (",seqNum,")"

        self.acceptors[seqNum].handleSuggestionRequest(self, ca, recvRid, csn, seqNum, propNum, requestKV)

    #####################################
    #                                   #
    #    Learner handling functions     #
    #                                   #
    #####################################

    def handleSuggestionAccept(self, senderRid, clientAddress, csn, logSeqNum, acceptedPropNum, acceptedKV):

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
                    self.learnValue(logSeqNum, clientAddress.toClientId(), csn, acceptedKV)
                    messages.sendValueLearned(self, clientAddress, csn)

                    # Garbage collect
                    self.accepted[logSeqNum].clear()
                    self.printLog()

                    # While only the primary should, if another replica has a proposer at this lsn, delete it
                    self.killProposerWithRestartIfNecessary(clientAddress, logSeqNum)

    def killProposerWithRestartIfNecessary(self, clientAddress, logSeqNum):
        if logSeqNum not in self.proposers:
            return

        # Re-propose if a different value was learned here or the request came from a different client
        differentKvLearned = (self.log[logSeqNum] != self.proposers[logSeqNum].kvToPropose)
        if self.proposers[logSeqNum].ca != clientAddress or differentKvLearned:
            print "ERROR: This should probably not happen. Two proposers for one sequence number"
            kvToPropose = self.proposers[logSeqNum].kvToPropose
            csnToPropose = self.proposers[logSeqNum].clientSequenceNumber
            cidToPropose = self.proposers[logSeqNum].ca
            self.beginPropose(cidToPropose, csnToPropose, kvToPropose)

        deleted = self.proposers.pop(logSeqNum, None)

        if deleted is None:
            print "Error: Could not delete proposer at " + logSeqNum

        if not self.isPrimary:
            print "Warning: non-primary had proposer (now deleted)"

    def learnValue(self, logSeqNum, clientId, clientSeqNum, learnKV, writeToLog=True):

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
                self.learnedValues[clientId] = set()

            self.learnedValues[clientId].add(clientSeqNum)

        # Log value and do operation on KV store
        if learnKV[0] == "GET":
            print "What to do here?" #TODO: What to do here??
        elif learnKV[0] == "PUT":
            self.kvStore[learnKV[1]] = learnKV[2]
        else:
            del self.kvStore[learnKV[1]]

        self.log[logSeqNum] = (learnKV, clientId, clientSeqNum)

        if writeToLog:
            self.appendStableLog(logSeqNum, clientId, clientSeqNum, learnKV)