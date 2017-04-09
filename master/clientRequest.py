from paxos import MessageTypes

class ClientRequest:
    type = None
    key = None
    value = None
    clientAddress = None
    clientSeqNum = None
    masterSeqNum = None
    assignedView = None
    receivedView = None
    receivedCount = None

    def __init__(self, type, key, val, ca, csn, curMRV=None, msn=None):
        self.type = type
        self.key = key
        self.value = val
        self.clientAddress = ca
        self.clientSeqNum = csn
        self.assignedView = curMRV
        self.receivedView = None
        self.masterSeqNum = msn
        self.receivedCount = 0

        assert(self.type in MessageTypes)
        assert(hasattr(ca, 'ip'))
        assert(hasattr(ca, 'port'))
