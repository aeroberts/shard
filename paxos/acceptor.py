from helpers import messages


class Acceptor:
    promisedNum = None
    acceptedPropNum = None
    acceptedValue = None

    def __init__(self, promisedNum=None, acceptedPropNum=None, acceptedValue=None):
        self.promisedNum = promisedNum
        self.acceptedPropNum = acceptedPropNum
        self.acceptedValue = acceptedValue
        return

    def handlePrepareRequest(self, replica, ca, recvRid, seqNum, propNum):
        if self.promisedNum is None:
            self.promisedNum = propNum
            messages.sendPrepareAllowDisallow(replica, ca, recvRid, seqNum, self.promisedNum,
                                              self.acceptedPropNum, self.acceptedValue)
            return

        if self.promisedNum >= propNum:
            messages.sendPrepareAllowDisallow(replica, ca, recvRid, seqNum, self.promisedNum,
                                              self.acceptedPropNum, self.acceptedValue)
            return

        # Can be combined with first "== None or  < propNum"
        if self.promisedNum < propNum:
            self.promisedNum = propNum
            messages.sendPrepareAllowDisallow(replica, ca, recvRid, seqNum, self.promisedNum,
                                              self.acceptedPropNum, self.acceptedValue)
            return

    def handleSuggestionRequest(self, replica, ca, recvRid, csn, seqNum, propNum, value):
        if self.promisedNum is None:
            print "Error! Received suggestion request before prepare request!"
            return

        if self.promisedNum <= propNum:
            self.promisedNum = propNum
            self.acceptedPropNum = propNum
            self.acceptedValue = value
            messages.sendSuggestionAccept(replica, ca, csn, seqNum, self.acceptedPropNum, self.acceptedValue)
            return

        # Already accepted a value with a higher proposal num, so send failure
        if self.promisedNum > propNum:
            messages.sendSuggestionFailure(replica, ca, recvRid, seqNum, self.promisedNum,
                                           self.acceptedPropNum, self.acceptedValue)
            return
