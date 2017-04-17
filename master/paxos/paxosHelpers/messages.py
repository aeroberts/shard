from messageTypes import MessageTypes
from messageTypes import getMessageTypeString
import random

class ClientAddress:
    ip = None
    port = None

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __str__(self):
        return str(self.ip) + "-" + str(self.port)

    def __hash__(self):
        return hash((self.ip, self.port))

    def __eq__(self, other):
        return self.ip == other.ip and self.port == other.port

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

    print "Broadcasting message: " + str(message)

    for h in hosts:
        rsock.sendto(message, (h[0], int(h[1])))

# Send a message to replica at IP, PORT
# Expects message to be well-formed
#   `Type,SeqNum Data` if from replica to replica
#   `PID,CSN Data` if from client to replica
def sendMessage(message, sock, IP=None, PORT=None, rid=None, hosts=None):
    if sendMessage.dropRandom is not False:
        print "Randint: ",str(random.randint(0, 100))
        if random.randint(0, 100) < int(sendMessage.dropRandom):
            print "\n\nDROPPING RANDOM MESSAGE\n\n"
            return

    assert IP is not None and PORT is not None or rid is not None and hosts is not None

    if IP is not None and PORT is not None:     # Send to specified IP and PORT
        print "\t\t\tSending message: " + message + " - to: " + str(IP) + "-" + str(PORT)
        sock.sendto(message, (IP, int(PORT)))
    else:                                       # Send to IP and PORT at replica with RID
        print "\t\t\tSending message: " + message + " - to: " + str(hosts[rid][0]) + "-" + str(hosts[rid][1])
        sock.sendto(message, (hosts[rid][0], int(hosts[rid][1])))

#------------------------------------------
#
#             PREPARE_REQUEST
#
#------------------------------------------

# Generates PREPARE_REQUEST message
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

    print "\t\t\tSending prepare request to all acceptors with propNum " + str(propNum)

    broadcastMessage(m, replica.sock, replica.hosts)

#------------------------------------------
#
#         PREPARE_ALLOW/DISALLOW
#
#------------------------------------------

# Generates PREPARE_ALLOWDISALLOW message
def generatePrepareAllowDisallow(seqNum, ca, view, propNum, aPropNum, aDataString):
    return str(MessageTypes.PREPARE_ALLOWDISALLOW) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum) + "," + str(aPropNum) + "," + str(aDataString)

# Message data in: "propNum,acceptedPropNum,acceptedReqType,acceptedReqKey,acceptedReqValue"
# Returns [propNum, acceptedPropNum, acceptedRequestType, acceptedRequestKey, acceptedRequestValue]
def unpackPrepareAllowDisallowData(msg):
    return unpackFourArgReplicaToReplicaMessageData(msg, MessageTypes.PREPARE_ALLOWDISALLOW)

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
def generateSuggestionRequest(seqNum, ca, view, csn, propNum, proposalDataString):
    return str(MessageTypes.SUGGESTION_REQUEST) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(propNum) + "," + str(csn) + "," + str(proposalDataString)

# Message in: "propNum,clientSeqNum,requestType,requestKey,requestValue"
# Returns [propNum, clientSeqNum, requestType, requestKey, requestValue]
def unpackSuggestionRequestData(data):
    return unpackFourArgReplicaToReplicaMessageData(data, MessageTypes.SUGGESTION_REQUEST)

# Broadcasts a SUGGESTION_REQUEST to all replicas (acceptors)
def sendSuggestionRequest(replica, ca, csn, seqNum, propNum, proposalDataString, rid):
    m = generateSuggestionRequest(seqNum, ca, replica.currentView, csn, propNum, proposalDataString)
    sendMessage(m, replica.sock, rid=rid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_FAILURE
#
#------------------------------------------

# Generate SUGGESTION_FAILURE message of form
#   `type,seqNum pPropNum,aPropNum,aVal`
def generateSuggestionFailure(seqNum, ca, view, pPropNum, aPropNum, aDataString):
    return str(MessageTypes.SUGGESTION_FAILURE) + "," + str(seqNum) + "," + \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(pPropNum) + "," + str(aPropNum) + "," + str(aDataString)

# Message in: "promisedPropNum,acceptedPropNum,acceptedReqType,acceptedReqKey,acceptedReqVal"
# Returns [promisedPropNum, acceptedPropNum, acceptedReqType, acceptedReqKey, acceptedReqVal]
def unpackSuggestionFailureData(data):
    return unpackFourArgReplicaToReplicaMessageData(data, MessageTypes.SUGGESTION_FAILURE)

# Sends suggestion failure message to replica with replica id of RID
def sendSuggestionFailure(replica, ca, recvRid, seqNum, pPropNum, aPropNum, aDataString):
    m = generateSuggestionFailure(seqNum, ca, replica.currentView, pPropNum, aPropNum, aDataString)
    sendMessage(m, replica.sock, rid=recvRid, hosts=replica.hosts)

#------------------------------------------
#
#           SUGGESTION_ACCEPT
#
#------------------------------------------

# Generate SUGGESTION_ACCEPT message of form
#   `type,seqNum aPropNum,aVal`
def generateSuggestionAccept(seqNum, ca, view, aPropNum, csn, aDataString):
    return str(MessageTypes.SUGGESTION_ACCEPT) + "," + str(seqNum) + "," +  \
           str(ca.ip) + "," + str(ca.port) + "," + str(view) + " " + \
           str(aPropNum) + "," + str(csn) + "," + str(aDataString)

# Returns (aPropNum, aVal, csn)
# from valid SUGGESTION_ACCEPT
def unpackSuggestionAcceptData(data):
    return unpackFourArgReplicaToReplicaMessageData(data, MessageTypes.SUGGESTION_ACCEPT)

# Broadcasts acceptance of a value at proposal number aPropNum to all learners
def sendSuggestionAccept(replica, ca, csn, seqNum, aPropNum, aDataString):
    m = generateSuggestionAccept(seqNum, ca, replica.currentView, aPropNum, csn, aDataString)
    broadcastMessage(m, replica.sock, replica.hosts)

#------------------------------------------
#
#           HIGHEST_OBSERVED
#
#------------------------------------------

# Generate HIGHEST_OBSERVED message of form
#   `type,highestSeqNum,cip,cport,view`
def generateHighestObserved(seqNum, view):
    return str(MessageTypes.HIGHEST_OBSERVED) + "," + str(seqNum) + "," + \
           str('None') + "," + str('None') + "," + str(view)

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
    return str(MessageTypes.HOLE_REQUEST) + "," + str(seqNum) + "," + \
           str(None) + "," + str(None) + "," + str(view)

# Unneeded as lsn is sent as part of metadata, so there is no message content to unpack
# def unpackHoleRequest(msg):

# Broadcasts acceptance of a value at proposal number aPropNum to all learners
def sendHoleRequest(replica, seqNum):
    m = generateHoleRequest(seqNum, replica.currentView)
    broadcastMessage(m, replica.sock, replica.hosts)

#------------------------------------------
#
#           HOLE_RESPONSE
#
#------------------------------------------

# Generate HOLE_RESPONSE message of form
#   `type,seqNum,cip,cport,view aVal`
def generateHoleResponse(seqNum, view, clientId, clientSeqNum, aDataString):
    return str(MessageTypes.HOLE_RESPONSE) + "," + str(seqNum) + "," + \
           str(None) + "," + str(None) + "," + str(view) + " " + \
           str(clientId) + "," + str(clientSeqNum) + "," + str(aDataString)

# Returns (cid, csn, val)
# from valid HOLE_RESPONSE
def unpackHoleResponseData(data):
    return unpackFourArgReplicaToReplicaMessageData(data, MessageTypes.HOLE_RESPONSE)

# Sends accepted value in log to new primary in response to HOLE REQUEST
# at log entry 'seqNum'
def sendHoleResponse(replica, newPrimaryRid, seqNum, clientId, clientSeqNum, aDataString):
    m = generateHoleResponse(seqNum, replica.currentView, clientId, clientSeqNum, aDataString)
    sendMessage(m, replica.sock, rid=newPrimaryRid, hosts=replica.hosts)

#------------------------------------------
#
#             VALUE_LEARNED
#
#------------------------------------------

def generateValueLearnedMessage(masterSeqNum, shardMRV, learnedReqType, learnedDataString):
    print "Generated value learned message: " + str(learnedReqType) + "," + str(masterSeqNum) + "," + str(shardMRV) + "," + str(learnedDataString)
    return str(learnedReqType) + "," + str(masterSeqNum) + "," + str(shardMRV) + "," + str(learnedDataString)

# Message in: "messageType,masterSeqNum,shardMRV,learnedDataString"
# Returns (masterSeqNum, shardMRV, learnedType, [learnedData])
def unpackPaxosResponse(data):
    vals = data.split(",", 3)
    if len(vals) != 4 or len(vals[0]) == 0 or len(vals[1]) == 0 or len(vals[2]) == 0 or len(vals[3]) == 0:
        assert len(vals) == 4
        assert len(vals[0]) > 0 and len(vals[1]) > 0 and len(vals[2]) > 0 and len(vals[3]) > 0

    if vals[0] != 'None':
        vals[0] = int(vals[0])
    else:
        print "ERROR: No message type found while unpacking paxos request"
        vals[0] = None

    if vals[1] != 'None':
        vals[1] = int(vals[1])
    else:
        vals[1] = None

    if vals[2] != 'None':
        vals[2] = int(vals[2])
    else:
        vals[2] = None

    print "Calling unpackRequestDataString(" + str(vals[0]) + "  ,  " + str(vals[3]) + ")"
    requestData = unpackRequestDataString(str(vals[0]) + "," + str(vals[3]))

    return vals[1], vals[2], requestData

def respondValueLearned(replica, ca, masterSeqNum, shardMRV, learnedReqType, learnedData):
    learnedDataString = packLearnedData(learnedReqType, learnedData)
    m = generateValueLearnedMessage(masterSeqNum, shardMRV, learnedReqType, learnedDataString)
    sendMessage(m, replica.sock, IP=ca.ip, PORT=ca.port)

##############################################
#                                            #
#   Client and Replica Metadata Unpacking    #
#                                            #
##############################################

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


# Message in: "Type,masterSeqNum,shardMRV DataString"
# Data out: [Type, MasterSeqNum, ShardMRV, DataString]
def unpackClientMessageMetadata(data):
    metadata, messageDataString = data.split(" ", 1)

    metadata = metadata.split(",")
    assert(len(metadata) == 3)
    assert(len(metadata[0]) > 0)
    assert(len(metadata[1]) > 0)
    assert(len(metadata[2]) > 0)

    return int(metadata[0]), int(metadata[1]), int(metadata[2]), messageDataString

#####################################
#                                   #
#          Misc Functions           #
#                                   #
#####################################

def packLearnedData(requestType, learnedData):
    requestType = int(requestType)

    # GET_REQUEST: "Key,Value"
    # [learnKey, getValue]
    if requestType == MessageTypes.GET:
        assert(len(learnedData) == 2)
        return str(learnedData[0]) + "," + str(learnedData[1])

    # PUT_REQUEST: "Key,Status"
    # returnData = [learnKey, 'Success']
    elif requestType == MessageTypes.PUT:
        assert (len(learnedData) == 2)
        return str(learnedData[0]) + "," + str(learnedData[1])

    # BATCH_PUT: "Status"
    # returnData = "Status"
    elif requestType == MessageTypes.BATCH_PUT:
        return str(learnedData)

    # DELETE_REQUEST: "Key,Status"
    # returnData = [learnKey, 'Success']
    elif requestType == MessageTypes.DELETE:
        assert (len(learnedData) == 2)
        return str(learnedData[0]) + "," + str(learnedData[1])

    # BEGIN_STARTUP: ?
    elif requestType == MessageTypes.BEGIN_STARTUP:
        return ""

    # SEND_KEYS: ?
    elif requestType == MessageTypes.SEND_KEYS:
        return ""

    else:
        print "ERROR: Unrecognized message type found in packLearnedData"
        assert(0 & "Unrecognized message type found in packLearnedData")
        return ""

# Assuming message = "data1,data2,request" where request = "type,data"
def unpackFourArgReplicaToReplicaMessageData(message, messageType):
    vals = message.split(",", 2)
    if len(vals) != 3 or len(vals[0]) == 0 or len(vals[1]) == 0 or len(vals[2]) == 0:
        print "Error: Malformed " + getMessageTypeString(messageType) + " received"
        assert len(vals) == 3
        assert len(vals[0]) > 0 and len(vals[1]) > 0 and len(vals[2]) > 0

    if vals[0] != 'None':
        vals[0] = int(vals[0])
    else:
        vals[0] = None

    if vals[1] != 'None':
        vals[1] = int(vals[1])
    else:
        vals[1] = None

    if vals[2] is None:
        print "Error: no request data found"
        assert(vals[2] is not None)
    elif vals[2] == 'None':
        vals.append('None')
    else:
        reqData = vals[2].split(",", 1)
        assert(reqData is not None and len(reqData) == 2)
        vals[2] = reqData[0]
        vals.append(reqData[1])

    return vals

def unpackRequestDataString(requestValueString):
    print "\t\tunpackRequestDataString: " + str(requestValueString)
    requestType, requestDataString = requestValueString.split(",", 1)
    requestType = int(requestType)

    # GET_REQUEST: "Key,'None'"
    # [MessageTypes.GET, Key]
    if requestType == MessageTypes.GET:
        assert(requestDataString is not None and requestDataString != 'None')
        keyNone = requestDataString.split(",", 1)
        assert(len(keyNone) == 2)

        return [MessageTypes.GET, keyNone[0], keyNone[1]]

    # PUT_REQUEST: "Key,Value"
    # [MessageTypes.PUT, Key, Value]
    elif requestType == MessageTypes.PUT:
        dataList = requestDataString.split(",")
        assert(len(dataList) == 2)
        assert(dataList[0] is not None and dataList[0] != 'None')
        assert(dataList[1] is not None and dataList[1] != 'None')
        return [MessageTypes.PUT, str(dataList[0]), str(dataList[1])]

    # BATCH_PUT: "Key,Val|Key,Val|...|Key,Val"
    # [MessageTypes.BATCH_PUT, "Key,Val|Key,Val|...|Key,Val"]
    elif requestType == MessageTypes.BATCH_PUT:
        assert(requestDataString is not None and requestDataString != 'None')
        return [MessageTypes.BATCH_PUT, requestDataString]

    # DELETE_REQUEST: "Key,'None'"
    # [MessageTypes.DELETE, Key]
    elif requestType == MessageTypes.DELETE:
        assert(requestDataString is not None and requestDataString != 'None')
        keyNone = requestDataString.split(",", 1)
        assert (len(keyNone) == 2)

        if keyNone[1] == 'None':
            return [MessageTypes.DELETE, requestDataString]
        else:
            return [MessageTypes.DELETE, keyNone[0], keyNone[1]]

    # BEGIN_STARTUP: "LowerKeyBound,UpperKeyBound,osView,osIP1,osPort1|...|osIPN,osPortN"
    # [MessageTypes.BEGIN_STARTUP, LowerKeyBound, UpperKeyBound, osView, "osIP1,osPort1|...|osIPN,osPortN"]
    elif requestType == MessageTypes.BEGIN_STARTUP:
        dataList = requestDataString.split(",", 3)
        assert (dataList[0] is not None and dataList[0] != 'None')
        assert (dataList[1] is not None and dataList[1] != 'None')
        assert (dataList[2] is not None and dataList[2] != 'None')
        assert (dataList[3] is not None and dataList[3] != 'None')
        return [MessageTypes.BEGIN_STARTUP, int(dataList[0]), int(dataList[1]), int(dataList[2]), str(dataList[3])]

    # SEND_KEYS: "LowerKeyBound,UpperKeyBound,nsView,nsIP1,nsPort1|...|nsIPN,nsPortN"
    # [MessageTypes.SEND_KEYS, LowerKeyBound, UpperKeyBound, nsView, "nsIP1,nsPort1|...|nsIPN,nsPortN"]
    elif requestType == MessageTypes.SEND_KEYS:
        dataList = requestDataString.split(",", 3)
        assert (dataList[0] is not None and dataList[0] != 'None')
        assert (dataList[1] is not None and dataList[1] != 'None')
        assert (dataList[2] is not None and dataList[2] != 'None')
        assert (dataList[3] is not None and dataList[3] != 'None')
        return [MessageTypes.SEND_KEYS, int(dataList[0]), int(dataList[1]), int(dataList[2]), str(dataList[3])]

    # SHARD_READY: "LowerKeyBound,UpperKeyBound"
    # [MessageTypes.SHARD_READY, LowerKeyBound, UpperKeyBound]
    elif requestType == MessageTypes.SHARD_READY:
        bounds = requestDataString.split(",")
        assert(len(bounds) == 2)
        assert (bounds[0] is not None and bounds[0] != 'None')
        assert (bounds[1] is not None and bounds[1] != 'None')
        return [MessageTypes.SHARD_READY, int(bounds[0]), int(bounds[1])]

    else:
        print "ERROR: Unrecognized message type found in getAndValidateRequestData"
        assert(0 & "Unrecognized message type found in getAndValidateRequestData")
        return False

#################################################
#                                               #
#       Master Message String Unpacking         #
#                                               #
#################################################

def unpackStartShard(inputString):
    stringData = inputString.split(",", 2)
    assert(len(stringData) == 3)
    assert (stringData[0] is not None and stringData[0] != 'None')
    assert (stringData[1] is not None and stringData[1] != 'None')

    substringData = stringData[2].split("|", 1)
    assert(len(substringData) == 2)
    assert(substringData[0] is not None and substringData[0] != 'None')

    return [stringData[0], stringData[1], substringData[0], substringData[1]]

def unpackSendKeysRequest(inputString):
    stringData = inputString.split(",", 2)
    assert (len(stringData) == 3)
    assert (stringData[0] is not None and stringData[0] != 'None')
    assert (stringData[1] is not None and stringData[1] != 'None')

    substringData = stringData[2].split("|", 1)
    assert (len(substringData) == 2)
    assert (substringData[0] is not None and substringData[0] != 'None')

    print "Unpack send keys request: "
    print "  inputString: " + str(inputString)
    print "  stringData: " + str(stringData)
    print "  substringData: " + str(substringData)

    return [stringData[0], stringData[1], substringData[0], substringData[1]]