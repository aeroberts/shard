from paxos import MessageTypes
from paxos import ClientAddress

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

        assert(0 <= self.type < MessageTypes.typeRange)
        assert(hasattr(ca, 'ip'))
        assert(hasattr(ca, 'port'))

    def transformAddShard(self, msn, lowerKeyBound, newSID, osView, osAddrs):
        # self.key = LowerKeyBound,UpperKeyBound,osView|osIP1,osPort1|...|osIPN,osPortN
        self.key = str(lowerKeyBound) + "," + str(newSID) + "," + str(osView)
        for addr in osAddrs:
            self.key += "|" + str(addr.ip) + "," + str(addr.port)

        self.masterSeqNum = msn
        self.type = MessageTypes.START_SHARD

        return

    def transferRequestReset(self):
        self.assignedView = -1

        if self.masterSeqNum is not None:
            print "Warning: Transferring request with MSN assigned"

        if self.receivedCount is not None:
            print "Warning: Transferring request with received count assigned"

        if self.receivedView is not None:
            print "Warning: Transferring request with received view assigned"

    def getAddShardAddrs(self):
        addrs = self.key.split(" ")
        addrList = []
        for addr in addrs:
            addr = addr.split(",")
            addrList.append(ClientAddress(addr[0], addr[1]))

        return addrList

