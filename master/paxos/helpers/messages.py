from messageTypes import MessageTypes
from messageTypes import getMessageTypeString

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
def broadcastMessage(message, rsock, hosts):
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
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum)

# Returns propNum from valid PREPARE_REQUEST
def unpackPrepareRequestData(msg):
    assert len(msg) > 0
    return int(msg)

# Broadcasts a prepare request to all replicas
def sendPrepareRequest(replica, ca, seqNum, propNum):
    # For each acceptor, generate a message, send it to the acceptor, and add the acceptor to the sent set
    m = generatePrepareRequest(seqNum, propNum, ca, replica.currentView)
    broadcastMessage(m, replica.sock, replica.hosts)

#------------------------------------------
#
#         PREPARE_ALLOW/DISALLOW
#
#------------------------------------------

# Generates PREPARE_DISALLOW message
def generatePrepareAllowDisallow(seqNum, ca, view, propNum, aPropNum, aPropKV):
    return str(MessageTypes.PREPARE_ALLOWDISALLOW) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum) + "," + str(aPropNum) + "," + str(aPropKV[0]) + "," + str(aPropKV[1]) + "," + str(aPropKV[2])

# Message data in: "propNum,acceptedPropNum,acceptedReqType,acceptedReqKey,acceptedReqValue"
# Returns [propNum, acceptedPropNum, acceptedRequestType, acceptedRequestKey, acceptedRequestValue]
def unpackPrepareAllowDisallowData(msg):
    return unpackReplicaToReplicaMessageData(msg, MessageTypes.PREPARE_ALLOWDISALLOW)

# Sends Allow or Disallow message to replica with replica id of RID
def sendPrepareAllowDisallow(replica, ca, recvRid, seqNum, propNum, aPropNum, aPropKV):
    m = generatePrepareAllowDisallow(seqNum, ca, replica.currentView, propNum, aPropNum, aPropKV)
    sendMessage(m, replica.sock, rid=recvRid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_REQUEST
#
#------------------------------------------

# Generate SUGGESTION_REQUEST message of form
#   `type,seqNum propNum,val`
def generateSuggestionRequest(seqNum, ca, view, csn, propNum, requestKV):
    return str(MessageTypes.SUGGESTION_REQUEST) + "," + \
           str(seqNum) + "," + str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum) + "," + str(csn) + "," + \
           str(requestKV[0]) + "," + str(requestKV[1]) + "," + str(requestKV[2])

# Message in: "propNum,clientSeqNum,requestType,requestKey,requestValue"
# Returns [propNum, clientSeqNum, requestType, requestKey, requestValue]
def unpackSuggestionRequestData(data):
    return unpackReplicaToReplicaMessageData(data, MessageTypes.SUGGESTION_REQUEST)

# Broadcasts a SUGGESTION_REQUEST to all replicas (acceptors)
def sendSuggestionRequest(replica, ca, csn, seqNum, propNum, proposalKV, rid):
    m = generateSuggestionRequest(seqNum, ca, replica.currentView, csn, propNum, proposalKV)
    sendMessage(m, replica.sock, rid=rid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_FAILURE
#
#------------------------------------------

# Generate SUGGESTION_FAILURE message of form
#   `type,seqNum pPropNum,aPropNum,aVal`
def generateSuggestionFailure(seqNum, ca, view, pPropNum, aPropNum, acceptedKV):
    return str(MessageTypes.SUGGESTION_FAILURE) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(pPropNum) + "," + str(aPropNum) + "," +  \
           str(acceptedKV[0]) + "," + str(acceptedKV[1]) + "," + str(acceptedKV[2])

# Message in: "promisedPropNum,acceptedPropNum,acceptedReqType,acceptedReqKey,acceptedReqVal"
# Returns [promisedPropNum, acceptedPropNum, acceptedReqType, acceptedReqKey, acceptedReqVal]
def unpackSuggestionFailureData(data):
    return unpackReplicaToReplicaMessageData(data, MessageTypes.SUGGESTION_FAILURE)

# Sends suggestion failure message to replica with replica id of RID
def sendSuggestionFailure(replica, ca, recvRid, seqNum, pPropNum, aPropNum, acceptedKV):
    m = generateSuggestionFailure(seqNum, ca, replica.currentView, pPropNum, aPropNum, acceptedKV)
    sendMessage(m, replica.sock, rid=recvRid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_ACCEPT
#
#------------------------------------------

# Generate SUGGESTION_ACCEPT message of form
#   `type,seqNum aPropNum,aVal`
def generateSuggestionAccept(seqNum, ca, view, aPropNum, csn, acceptedKV):
    return str(MessageTypes.SUGGESTION_ACCEPT) + "," + \
           str(seqNum) + "," + str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(aPropNum) + "," + str(csn) + "," + \
           str(acceptedKV[0]) + "," + str(acceptedKV[1]) + "," + str(acceptedKV[2])

# Returns (aPropNum, aVal, csn)
# from valid SUGGESTION_ACCEPT
def unpackSuggestionAcceptData(data):
    return unpackReplicaToReplicaMessageData(data, MessageTypes.SUGGESTION_ACCEPT)

# Broadcasts acceptance of a value at proposal number aPropNum to all learners
def sendSuggestionAccept(replica, ca, csn, seqNum, aPropNum, acceptedKV):
    m = generateSuggestionAccept(seqNum, ca, replica.currentView, aPropNum, acceptedKV, csn)
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
def generateHoleResponse(seqNum, view, clientId, clientSeqNum, acceptedKV):
    return str(MessageTypes.HOLE_RESPONSE) + "," + str(seqNum) + "," + \
           str(None) + "," + str(None) + "," + str(view) + " " + \
           str(clientId) + "," + str(clientSeqNum) + "," + \
           str(acceptedKV[0]) + "," + str(acceptedKV[1]) + "," + str(acceptedKV[2])

# Returns (cid, csn, val)
# from valid HOLE_RESPONSE
def unpackHoleResponseData(data):
    return unpackReplicaToReplicaMessageData(data, MessageTypes.HOLE_RESPONSE)

# Sends accepted value in log to new primary in response to HOLE REQUEST
# at log entry 'seqNum'
def sendHoleResponse(replica, newPrimaryRid, seqNum, clientId, clientSeqNum, acceptedKV):
    m = generateHoleResponse(seqNum, replica.currentView, clientId, clientSeqNum, acceptedKV)
    sendMessage(m, replica.sock, rid=newPrimaryRid, hosts=replica.hosts)

#------------------------------------------
#
#             VALUE_LEARNED
#
#------------------------------------------

def generateValueLearnedMessage(masterSeqNum, shardMRV, learnedKV):
    return str(masterSeqNum) + "," + str(shardMRV) + "," + \
           str(learnedKV[0]) + "," + str(learnedKV[1]) + "," + str(learnedKV[2])

# Returns (view, rid, csn)
def unpackReplicaResponse(data):
    vals = data.split(",", 4)
    if len(vals) != 5 or not all(len(i) != 0 for i in vals):
        print "Error: Malformed value learned"
        assert len(vals) == 5
        assert len(vals[0]) > 0 and len(vals[1]) > 0 and len(vals[2]) > 0 and len(vals[3]) > 0 and len(vals[4]) > 0

    vals[0] = int(vals[0])
    vals[1] = int(vals[1])
    checkKeyValueData(vals[2:])
    return vals

def sendValueLearned(replica, ca, masterSeqNum, shardMRV, learnedKV):
    m = generateValueLearnedMessage(masterSeqNum, shardMRV, learnedKV)
    sendMessage(m, replica.sock, IP=ca.ip, PORT=ca.port)

# Returns (type, seqNum, ca.ip, ca.port, associatedView, data) from any valid replica message
def unpackReplicaMetadata(data):
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

# Message in: "Type,masterSeqNum,shardMRV,requestKey,requestValue"
# Data out: [masterSeqNum, shardMRV, requestTYpe, requestKey, requestValue]
def unpackClientMessage(data):
    vals = data.split(",", 4)
    checkKeyValueData(list(vals[0], vals[3], vals[4]))
    if len(vals) != 5 or not all(len(i) != 0 for i in vals):
        print "Error: Malformed paxos client request"
        assert len(vals) == 5
        assert len(vals[1]) > 0 and len(vals[2]) > 0

    if vals[0] != 'None':
        vals[0] = int(vals[0])
    else:
        vals[0] = None

    if vals[1] != 'None':
        vals[1] = int(vals[1])
    else:
        vals[1] = None

    return vals


#==========================================#
#                                          #
#           ADD_SHARD Messages             #
#                                          #
#==========================================#

#-------------------------
#      START_SHARD
#-------------------------

def unpackStartShard(msg):
    print "USS"

def generateStartShard(msg):
    print "GSS"

def sendStartShard(replica, ca, csn):
    print "SSS"

#-------------------------
#      BEGIN_STARTUP
#-------------------------

def unpackBeginStartup(msg):
    print "USS"

def generateBeginStartup(msg):
    print "GSS"

def sendBeginStartup(replica, ca, csn):
    print "SSS"

#-------------------------
#    SEND_KEYS_REQUEST
#-------------------------

def unpackSendKeysRequest(msg):
    print "USS"

def generateSendKeysRequest(msg):
    print "GSS"

def sendSendKeysRequest(replica, ca, csn):
    print "SSS"

#-------------------------
#       SEND_KEYS
#-------------------------

def unpackSendKeys(msg):
    print "USS"

def generateSendKeys(msg):
    print "GSS"

def sendSendKeys(replica, ca, csn):
    print "SSS"

#-------------------------
#   SEND_KEYS_RESPONSE
#-------------------------

def unpackSendKeysResponse(msg):
    print "USS"

def generateSendKeysResponse(msg):
    print "GSS"

def sendSendKeysResponse(replica, ca, csn):
    print "SSS"

#-------------------------
#      KEYS_LEARNED
#-------------------------

def unpackKeysLearned(msg):
    print "USS"

def generateKeysLearned(msg):
    print "GSS"

def sendKeysLearned(replica, ca, csn):
    print "SSS"

#-------------------------
#      SHARD_READY
#-------------------------

def unpackShardReady(msg):
    print "USS"

def generateShardReady(msg):
    print "GSS"

def sendShardReady(replica, ca, csn):
    print "SSS"

def sendShardReadyLearned(replica, ca, csn):
    print "sending SSRL"

#####################################
#                                   #
#          Misc Functions           #
#                                   #
#####################################

def unpackReplicaToReplicaMessageData(data, messageType):
    vals = data.split(",", 4)
    if len(vals) != 5 or not all(len(i) != 0 for i in vals):
        print "Error: Malformed " + getMessageTypeString(messageType) + " received"
        assert len(vals) == 5
        assert len(vals[0]) > 0 and len(vals[1]) > 0

    if vals[0] != 'None':
        vals[0] = int(vals[0])
    else:
        vals[0] = None

    if vals[1] != 'None':
        vals[1] = int(vals[1])
    else:
        vals[1] = None

    checkKeyValueData(vals[2:])
    vals[2] = int(vals[2])

    return vals

def checkKeyValueData(requestKV):
    requestType = requestKV[0]
    requestKey = requestKV[1]
    requestValue = requestKV[2]

    if requestType is None or requestType == 'None':
        print "No kv request type found in message"
        assert(0 and "No kv request type found in message")

    requestType = int(requestType)
    if requestType != MessageTypes.GET or requestType != MessageTypes.PUT or requestType != MessageTypes.DELETE:
        print "Malformed kv request type found in message. Message type found: " + str(requestType)
        assert(0 and "Malformed kv request type found: " + str(requestType))

    if requestKey is None or requestKey == 'None' or len(requestKey) == 0:
        print "KV key malformed or 'None'"
        assert(0 and "No data found for kv key or key is 'None' in message")

    checkValue = (requestType == MessageTypes.PUT)
    if checkValue and (requestValue is None or requestValue == 'None' or len(requestValue) == 0):
        print "KV value malformed or 'None' with PUT request type"
        assert(0 and "No data found for kv value or value is 'None' in message")

