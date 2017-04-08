from messageTypes import MessageTypes

class ClientAddress:
    ip = None
    port = None

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __str__(self):
        return str(self.ip) + "-" + str(self.port)

    def toClientId(self):
        return str(self.ip) + str(self.port)

# Given a hostfile containing 'ip port' of all replicas, parse
# into an array of [[ip port], [ip port], ... [ip port]]
def getHosts(hostFile):
    hfile = open(hostFile, "r")
    hosts = [h.split() for h in hfile.readlines()]
    return [[h[0], int(h[1])] for h in hosts]

# Send a message to all other replicas
# Expects message to be well-formed
#   `Type,SeqNum Data` if from replica to replica
#   `PID,CSN Data` if from client to replica
def broadcastMessage(message, rsock, hosts, rid=-1):
    for h in hosts:
        rsock.sendto(message, (h[0], int(h[1])))

# Send a message to replica at IP, PORT
# Expects message to be well-formed
#   `Type,SeqNum Data` if from replica to replica
#   `PID,CSN Data` if from client to replica
def sendMessage(message, sock, IP=None, PORT=None, rid=None, hosts=None):
    assert IP is not None and PORT is not None or rid is not None and hosts is not None

    if IP is not None and PORT is not None:     # Send to specified IP and PORT
        sock.sendto(message, (IP, int(PORT)))
    else:                                       # Send to IP and PORT at replica with RID
        sock.sendto(message, (hosts[rid][0], int(hosts[rid][1])))

#------------------------------------------
#
#             PREPARE_REQUEST
#
#------------------------------------------

# Generates PREPARE_REQUEST message of form
#   `Type,seqNum propNum`
def generatePrepareRequest(seqNum, propNum, ca, view):
    return str(MessageTypes.PREPARE_REQUEST) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + str(propNum)

# Returns propNum from valid PREPARE_REQUEST
def unpackPrepareRequest(msg):
    assert len(msg) > 0
    return int(msg)

# Broadcasts a prepare request to all replicas
def sendPrepareRequest(replica, ca, seqNum, propNum):
    # For each acceptor, generate a message, send it to the acceptor, and add the acceptor to the sent set
    m = generatePrepareRequest(seqNum, propNum, ca, replica.currentView)
    broadcastMessage(m, replica.sock, replica.hosts, replica.rid)

#------------------------------------------
#
#         PREPARE_ALLOW/DISALLOW
#
#------------------------------------------

# Generates PREAPRE_DISALLOW message of form
#   `type,seqNum propNum,aPropNum,aPropVal`
def generatePrepareAllowDisallow(seqNum, ca, view, propNum, aPropNum, aPropVal):
    return str(MessageTypes.PREPARE_ALLOWDISALLOW) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum) + "," + str(aPropNum) + "," + str(aPropVal)

# Returns (propNum, aPropNum, aPropVal)
# from valid PREPARE_ALLOW or PREPARE_DISALLOW
def unpackPrepareAllowDisallow(msg):
    vals = msg.split(",")
    if len(vals) != 3 or len(vals[0]) == 0 or len(vals[1]) == 0 or len(vals[2]) == 0:
        print "Error: Malformed prepare allow/disallow recieved"
        assert len(vals) == 3
        assert len(vals[0]) > 0
        assert len(vals[1]) > 0
        assert len(vals[2]) > 0

    if vals[0] != 'None':
        vals[0] = int(vals[0])
    else:
        vals[0] = None

    if vals[1] != 'None':
        vals[1] = int(vals[1])
    else:
        vals[1] = None

    return vals[0], vals[1], vals[2]

# Sends Allow or Disallow message to replica with replica id of RID
def sendPrepareAllowDisallow(replica, ca, recvRid, seqNum, propNum, aPropNum, aPropVal):
    m = generatePrepareAllowDisallow(seqNum, ca, replica.currentView, propNum, aPropNum, aPropVal)
    sendMessage(m, replica.sock, rid=recvRid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_REQUEST
#
#------------------------------------------

# Generate SUGGESTION_REQUEST message of form
#   `type,seqNum propNum,val`
def generateSuggestionRequest(seqNum, ca, view, csn, propNum, val):
    return str(MessageTypes.SUGGESTION_REQUEST) + "," + \
           str(seqNum) + "," + str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum) + "," + str(val) + "," + str(csn)

# Returns (propNum, val, csn)
# from valid SUGGESTION_REQUEST
def unpackSuggestionRequest(msg):
    vals = msg.split(",")
    if len(vals) != 3 or len(vals[0]) == 0 or len(vals[1]) == 0:
        print "Error: Malformed suggestion request received"
        assert len(vals) == 3
        assert len(vals[0]) > 0
        assert len(vals[1]) > 0

    return int(vals[0]), vals[1], int(vals[2])

# Broadcasts a SUGGESTION_REQUEST to all replicas (acceptors)
def sendSuggestionRequest(replica, ca, csn, seqNum, propNum, val, rid):
    m = generateSuggestionRequest(seqNum, ca, replica.currentView, csn, propNum, val)
    sendMessage(m, replica.sock, rid=rid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_FAILURE
#
#------------------------------------------

# Generate SUGGESTION_FAILURE message of form
#   `type,seqNum pPropNum,aPropNum,aVal`
def generateSuggestionFailure(seqNum, ca, view, pPropNum, aPropNum, aVal):
    return str(MessageTypes.SUGGESTION_FAILURE) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(pPropNum) + "," + str(aPropNum) + "," + str(aVal)

# Returns (pPropNum, aPropNum, aVal)
# from valid SUGGESTION_FAILURE
def unpackSuggestionFailure(msg):
    vals = msg.split(",")
    if len(vals) != 3 or len(vals[0]) == 0 or len(vals[1]) == 0 or len(vals[2]) == 0:
        print "Error: Malformed suggestion request recieved"
        assert len(vals) == 3
        assert len(vals[0]) > 0
        assert len(vals[1]) > 0
        assert len(vals[2]) > 0

    if vals[0] is not 'None':
        vals[0] = int(vals[0])

    if vals[1] is not 'None':
        vals[1] = int(vals[1])

    return int(vals[0]), int(vals[1]), vals[2]

# Sends suggestion failure message to replica with replica id of RID
def sendSuggestionFailure(replica, ca, recvRid, seqNum, pPropNum, aPropNum, aVal):
    m = generateSuggestionFailure(seqNum, ca, replica.currentView, pPropNum, aPropNum, aVal)
    sendMessage(m, replica.sock, rid=recvRid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_ACCEPT
#
#------------------------------------------

# Generate SUGGESTION_ACCEPT message of form
#   `type,seqNum aPropNum,aVal`
def generateSuggestionAccept(seqNum, ca, view, aPropNum, aVal, csn):
    return str(MessageTypes.SUGGESTION_ACCEPT) + "," + \
           str(seqNum) + "," + str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(aPropNum) + "," + str(aVal) + "," + str(csn)

# Returns (aPropNum, aVal, csn)
# from valid SUGGESTION_ACCEPT
def unpackSuggestionAccept(msg):
    vals = msg.split(",")
    if len(vals) != 3 or len(vals[0]) == 0 or len(vals[1]) == 0:
        print "Error: Malformed suggestion allow recieved"
        assert len(vals) == 3
        assert len(vals[0]) > 0
        assert len(vals[1]) > 0
        assert len(vals[2]) > 0

    return int(vals[0]), vals[1], int(vals[2])

# Broadcasts acceptance of a value at proposal number aPropNum to all learners
def sendSuggestionAccept(replica, ca, csn, seqNum, aPropNum, aVal):
    m = generateSuggestionAccept(seqNum, ca, replica.currentView, aPropNum, aVal, csn)
    broadcastMessage(m, replica.sock, replica.hosts, replica.rid)

#------------------------------------------
#
#           HIGHEST_OBSERVED
#
#------------------------------------------

# Generate HIGHEST_OBSERVED message of form
#   `type,highestSeqNum,cip,cport,view`
def generateHighestObserved(seqNum, view):
    return str(MessageTypes.HIGHEST_OBSERVED) + "," + \
           str(seqNum) + "," + str('None') + "," + str('None') + "," + str(view)

# Unneeded as lsn is sent as part of metadata, so there is no message content to unpack
# def unpackHighestObserved(msg):

# Broadcasts acceptance of a value at proposal number aPropNum to all learners
def sendHighestObserved(replica, newPrimaryRid, seqNum):
    m = generateHighestObserved(seqNum, replica.currentView)
    sendMessage(m, replica.sock, rid=newPrimaryRid, hosts=replica.hosts)


#------------------------------------------
#
#           HOLE_REQUEST
#
#------------------------------------------

# Generate HOLE_REQUEST message of form
#   `type,holeSeqNum,cip,cport,view`
def generateHoleRequest(seqNum, view):
    return str(MessageTypes.HOLE_REQUEST) + "," + \
           str(seqNum) + "," + str(None) + "," + str(None) + "," + str(view)

# Unneeded as lsn is sent as part of metadata, so there is no message content to unpack
# def unpackHoleRequest(msg):

# Broadcasts acceptance of a value at proposal number aPropNum to all learners
def sendHoleRequest(replica, seqNum):
    m = generateHoleRequest(seqNum, replica.currentView)
    broadcastMessage(m, replica.sock, replica.hosts, replica.rid)

#------------------------------------------
#
#           HOLE_RESPONSE
#
#------------------------------------------

# Generate HOLE_RESPONSE message of form
#   `type,seqNum,cip,cport,view aVal`
def generateHoleResponse(seqNum, view, clientId, clientSeqNum, aVal):
    return str(MessageTypes.HOLE_RESPONSE) + "," + str(seqNum) + "," + \
           str(None) + "," + str(None) + "," + str(view) + " " + \
           str(clientId) + "," + str(clientSeqNum) + "," + str(aVal)

# Returns (cid, csn, val)
# from valid HOLE_RESPONSE
def unpackHoleResponse(msg):
    unpackedMessage = msg.split(",")
    assert len(unpackedMessage) == 3

    if str(unpackedMessage[0]) != 'None' and unpackedMessage[0] is not None:
        unpackedMessage[0] = str(unpackedMessage[0])
    else:
        unpackedMessage[0] = None

    if str(unpackedMessage[1]) != 'None' and unpackedMessage[1] is not None:
        unpackedMessage[1] = int(unpackedMessage[1])
    else:
        unpackedMessage[1] = None

    if str(unpackedMessage[2]) != 'None' and unpackedMessage[2] is not None:
        unpackedMessage[2] = str(unpackedMessage[2])
    else:
        unpackedMessage[2] = None

    return unpackedMessage

# Sends accepted value in log to new primary in response to HOLE REQUEST
# at log entry 'seqNum'
def sendHoleResponse(replica, newPrimaryRid, seqNum, clientId, clientSeqNum, aVal):
    m = generateHoleResponse(seqNum, replica.currentView, clientId, clientSeqNum, aVal)
    sendMessage(m, replica.sock, rid=newPrimaryRid, hosts=replica.hosts)



#------------------------------------------
#
#             VALUE_LEARNED
#
#------------------------------------------

def generateValueLearned(curView, rid, csn):
    return str(curView) + "," + str(rid) + "," + str(csn)

# Returns (view, rid, csn)
def unpackReplicaResponse(msg):
    response = msg.split(",")

    if len(response) < 3 or len(response[0]) == 0 or len(response[1]) == 0:
        print "Error: recievied malformed replica response to client"
        assert len(response) == 3
        assert len(response[0]) > 0
        assert len(response[1]) > 0

    return int(response[0]), int(response[1]), int(response[2])

def sendValueLearned(replica, ca, csn):
    m = generateValueLearned(replica.currentView, replica.rid, csn)
    sendMessage(m, replica.sock, IP=ca.ip, PORT=ca.port)

# Returns (type, seqNum, ca.ip, ca.port, associatedView, data) from any valid replica message
def unpackReplicaMessage(data):
    splitData = data.split(" ", 1)
    metadata = splitData[0]

    message = None
    if len(splitData) == 2:
        message = splitData[1]

    metadata = metadata.split(",")

    assert len(metadata) == 5
    assert len(metadata[0]) > 0
    assert len(metadata[1]) > 0
    assert len(metadata[2]) > 0
    assert len(metadata[3]) > 0
    assert len(metadata[4]) > 0

    if metadata[2] == 'None':
        metadata[2] = None

    if metadata[3] != 'None':
        metadata[3] = int(metadata[3])

    return int(metadata[0]), int(metadata[1]), metadata[2], metadata[3], int(metadata[4]), message

# Returns (PID, CSN, ViewNum, msg) from any valid client message
def unpackClientMessage(data):
    metadata, message = data.split(" ", 1)
    metadata = metadata.split(",")

    if len(metadata) < 3 or len(metadata[0]) == 0 or len(metadata[1]) == 0 or len(metadata[2]) == 0:
        print "Malformed client request"
        return None

    return int(metadata[0]), int(metadata[1]), int(metadata[2]), message


#------------------------
#
# For master
#
#------------------------
