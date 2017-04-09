from helpers import messages

class Proposer:
    rid = -1
    quorumSize = -1
    numReplicas = -1
    ca = -1
    clientSequenceNumber = -1
    logSeqNum = -1

    # Current proposal number.
    # Lowest number that is higher than the highest proposal number seen and a multiple of rid.
    proposalNum = -1

    # Number of attempts proposing a value for this decision
    attemptNum = 1

    # Value the proposer wants to propose if given the chance
    valueToPropose = None
    
    # Value and associated proposal number of the earliest value accepted by the proposer
    acceptedValue = None
    acceptedProposalNum = None

    # Set of addresses the proposer has sent prepare requests to and who it has received responses from
    preparesAllowed = None

    def __init__(self, rid, quorumSize, numReplicas, logSeqNum, ca, csn, valueToPropose):
        self.rid = rid
        self.quorumSize = quorumSize
        self.numReplicas = numReplicas
        self.logSeqNum = logSeqNum
        self.ca = ca
        self.clientSequenceNumber = csn
        self.valueToPropose = valueToPropose
        self.preparesAllowed = set()

    def incrementProposalNum(self, newProposalNum):
        highest = max(self.proposalNum, newProposalNum)
        prevIndex = highest % self.numReplicas
        if prevIndex < self.rid:
            self.proposalNum = highest + (self.rid - prevIndex)
        else:
            self.proposalNum = highest + self.rid + self.numReplicas - 1 - prevIndex

    def beginPrepareRound(self, replica, receivedPropNum=0):
        # Generate a new proposal number for the proposal and clear old proposal tracking
        self.incrementProposalNum(receivedPropNum)
        self.preparesAllowed.clear()

        # For each acceptor, generate a message, send it to the acceptor, and add the acceptor to the sent set
        messages.sendPrepareRequest(replica, self.ca, self.logSeqNum, self.proposalNum)

    def handlePrepareResponse(self, replica, recvPropNum, acceptedPropNum, acceptedValue, acceptorRid):

        # This must be a response indicating an acceptor has seen a larger proposal, so start a new proposal
        if self.proposalNum < recvPropNum:
            self.acceptedValue = acceptedValue
            self.acceptedProposalNum = acceptedPropNum
            self.beginPrepareRound(replica, recvPropNum)
            return

        # This must be a response to a previous proposal by this proposer, so ignore it.
        if self.proposalNum > recvPropNum:
            return

        # Duplicate response (perhaps because of timeout?), so ignore it.
        if acceptorRid in self.preparesAllowed:
            return

        # Otherwise, this response is the most recent proposal this proposer has seen
        # So, if the acceptor has accepted a more recent value, take that accepted value
        if acceptedPropNum > self.acceptedProposalNum:
            self.acceptedProposalNum = acceptedPropNum
            self.acceptedValue = acceptedValue

        # When allowed set reaches quorum, send to all acceptors who have allowed the proposal
        self.preparesAllowed.add(acceptorRid)
        if len(self.preparesAllowed) == self.quorumSize:
            # Send to all acceptors that have allowed your proposal
            for acceptor in self.preparesAllowed:
                proposalValue = self.acceptedValue
                if proposalValue is None:
                    proposalValue = self.valueToPropose

                messages.sendSuggestionRequest(replica, self.ca, self.clientSequenceNumber,
                                               self.logSeqNum, self.proposalNum, proposalValue, acceptor)

        # Otherwise, we've already reached quorum so just send to this acceptor
        elif len(self.preparesAllowed) > self.quorumSize:
            proposalValue = self.acceptedValue
            if proposalValue is None:
                proposalValue = self.valueToPropose

            messages.sendSuggestionRequest(replica, self.ca, self.clientSequenceNumber,
                                           self.logSeqNum, self.proposalNum, proposalValue, acceptorRid)

    def handleSuggestionFail(self, promisedNum, acceptedPropNum, acceptedVal, replica):
        # Update accepted propNum and val if the failure response's is greater
        if acceptedPropNum > self.acceptedProposalNum:
            self.acceptedProposalNum = acceptedPropNum
            self.acceptedValue = acceptedVal

        # If failure failed for this proposal number, begin a new proposal round
        if promisedNum == self.proposalNum:
            self.beginPrepareRound(replica, promisedNum)

        if promisedNum > self.proposalNum:
            print "ERROR: Promised num of failure response greater than originally granted proposal"
            return

        # Already restarted from a failure of this proposal number
        if promisedNum < self.proposalNum:
            return

