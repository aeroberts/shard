class ShardData:
    sid = None
    mostRecentView = None
    viewChanging = False

    # List of IP/Port of all replicas in shard (in rid order)
    replicaAddresses = None

    # Replicas is a list of `ClientAddress` (not clients but it works) for each replica
    def __init__(self, sid, replicas):
        self.sid = sid
        self.mostRecentView = 0
        self.viewChanging = False
        self.replicaAddresses = []

        for replica in replicas:
            self.replicaAddresses.append(replica)

    def containsAddr(self, addr):
        return addr in self.replicaAddresses

    def getLeaderAddress(self):
        return self.replicaAddresses[self.mostRecentView]

    # Returns "|IP,Port|IP,Port|...|IP,Port"
    def generateAddrString(self):
        addrString = ""
        for addr in self.replicaAddresses:
            addrString += "|" + str(addr.ip) + "," + str(addr.port)

        return addrString

    def getLeader(self):
        return self.mostRecentView % len(self.replicaAddresses)
