class ShardData:
    sid = None
    mostRecentView = None

    # List of IP/Port of all replicas in shard (in rid order)
    replicaAddresses = None

    # Replicas is a list of `ClientAddress` (not clients but it works) for each replica
    def __init__(self, sid, replicas):
        self.sid = sid
        self.mostRecentView = 0
        self.replicaAddresses = []

        for replica in replicas:
            self.replicaAddresses.append(replica)

    def containsAddr(self, addr):
        return addr in self.replicaAddresses

    def getLeaderAddress(self):
        return self.replicaAddresses[self.mostRecentView]