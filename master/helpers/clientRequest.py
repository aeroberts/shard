from paxos import MessageTypes

class ClientRequest:
    type = None
    key = None
    value = None
    clientAddress = None
    clientSeqNum = None
    masterSeqNum = None

    def __init__(self, type, key, val, ca, csn, msn=None):
        self.type = type
        self.key = key
        self.value = val
        self.clientAddress = ca
        self.clientSeqNum = csn
        self.masterSeqNum = msn

        assert(self.type in MessageTypes)
        assert(hasattr(ca, 'ip'))
        assert(hasattr(ca, 'port'))
