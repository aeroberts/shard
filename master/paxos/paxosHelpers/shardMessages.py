from messages import *
from messageTypes import MessageTypes

#==========================================#
#                                          #
#           ADD_SHARD Messages             #
#                                          #
#==========================================#

# Given IP,Port|IP,Port|IP,Port string, return array of client addresses
def unpackIPPortData(data):
    addresses = []
    for pair in data.split("|"):
        try:
            ip,port = pair.split(",", 1)
            port = int(port)
            addresses.append(ClientAddress(ip, port))
        except ValueError:
            print "Error unpacking ip/port in unpackIPPortData"

    return addresses

def unpackBatchKeyValues(kvString):
    batchDict = {}
    for pair in kvString.split("|"):
        try:
            batchKey, batchValue = pair.split(",", 1)
            batchKey = str(batchKey)
            batchValue = str(batchValue)
            assert(batchKey != 'None' and batchValue != 'None')
            batchDict[batchKey] = batchValue
        except ValueError:
            print "Error unpacking batch key/values in unpackBatchKeyValues"

    return batchDict

#-------------------------
#      START_SHARD
#-------------------------

# Returns LowerKeyBound, UpperKeyBound, osLeader Address, CA list of osReplicas
def unpackStartShardData(msg):
    data, osAddrs = msg.split("|",1)
    data = data.split(",")

    assert(len(data) == 3)
    assert(data[0] is not None)
    assert(data[1] is not None)
    assert(data[2] is not None)

    lowerKeyBound = data[0]
    upperKeyBound = data[1]

    osAddrList = unpackIPPortData(osAddrs)
    osLeaderAddr = osAddrList[int(data[2])]

    return lowerKeyBound, upperKeyBound, osLeaderAddr, osAddrList

# Returns "LowerKeyBound,UpperKeyBound,osLeaderId|osIP1,osPort1|...|osIPN,osPortN"
# Only called by master
def generateStartShard(msn, shardMostRecentView, lowerKeyBound, upperKeyBound, shardData):
    addrString = shardData.generateAddrString()
    return str(MessageTypes.START_SHARD) + "," + str(msn) + "," + str(shardMostRecentView) + " " + \
        str(lowerKeyBound) + "," + str(upperKeyBound) + "," + str(shardData.mostRecentView) + addrString

# Only called by Master
def sendStartShard(sock, newShardAddr, msn, shardMostRecentView, lowerKeyBound, upperKeyBound, shardData):
    m = generateStartShard(msn, shardMostRecentView, lowerKeyBound, upperKeyBound, shardData)
    sendMessage(m, sock, IP=newShardAddr.ip, PORT= newShardAddr.port)

#-------------------------
#      BEGIN_STARTUP
#-------------------------

# Returns LowerKeyBound, UpperKeyBound
def unpackBeginStartupData(msg):
    data = msg.split(",")

    assert(len(data) == 2)
    assert(data[0] is not None)
    assert(data[1] is not None)

    return data[0], data[1]

def generateBeginStartup(msg):
    return

def sendBeginStartup(replica, ca, csn):
    print "SSS"

#-------------------------
#    SEND_KEYS_REQUEST
#-------------------------

# Probably don't need nsAddrList.  Only necessary to forward so that
# after SendMessage we have replica addresses
# Returns LowerKeyBound, UpperKeyBound, nsLeader Address, CA list of nsReplicas
def unpackSendKeysRequestData(msg):
    data, nsAddrs = msg.split("|", 1)
    data = data.split(",")

    assert (len(data) == 3)
    assert (data[0] is not None)
    assert (data[1] is not None)
    assert (data[2] is not None)

    lowerKeyBound = data[0]
    upperKeyBound = data[1]

    nsAddrList = unpackIPPortData(nsAddrs)
    nsLeaderAddr = nsAddrList[int(data[2])]

    return lowerKeyBound, upperKeyBound, nsLeaderAddr, nsAddrList

# addrString is a list of addresses of this cluster of the form "|IP,Port|IP,Port|...|IP,Port"
# osMRV = old shard most recent view.  Send in metadata
# nsMRV = new shard most recent view.  Send it data so old shard knows who to send to
# Sequence num should always be 1 because SendKeysRequest is always the first message between two clusters
def generateSendKeysRequest(msn, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
    metadataString = str(MessageTypes.SEND_KEYS_REQUEST) + "," + str(msn) + "," + str(osMRV) + " "
    dataString = str(lowerKeyBound) + "," + str(upperKeyBound) + "," + str(nsMRV) + "|" + addrString
    return metadataString + dataString

# Called by new shard sending to old shard
def sendSendKeysRequest(sock, msn, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
    m = generateSendKeysRequest(msn, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString)
    osLeaderAddr = oldShardAddrList[osMRV % len(oldShardAddrList)]
    sendMessage(m, sock, IP=osLeaderAddr.ip, PORT=osLeaderAddr.port)

def broadcastSendKeyRequest(sock, msn, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
    m = generateSendKeysRequest(msn, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString)
    for addr in oldShardAddrList:
        sendMessage(m, sock, IP=addr.ip, PORT=addr.port)

#-------------------------
#   SEND_KEYS_RESPONSE
#-------------------------

# Returns osView, dictionary of (hashed) keys to values
def unpackSendKeysResponseData(msg):
    osView, kvString = msg.split(",", 1)
    pairs = kvString[1:].split("|")
    store = {}
    for pair in pairs:
        key, value = pair.split(",", 1)
        assert(len(key) > 0)
        assert(len(value) > 0)
        store[key] = value

    return osView, store

# Given dictionary of keys to send, output "Type,msn=1,nsMRV Key,Val|...|Key,Val" string
def generateSendKeysResponse(msn, osView, nsView, filteredKVStore):
    metadataString = str(MessageTypes.SEND_KEYS_RESPONSE) + "," + str(msn) + "," + str(nsView) + " " + str(osView) + "|"
    kvString = ""
    for key,value in filteredKVStore.iteritems():
        kvString += str(key) + "," + str(value) + "|"

    return metadataString + kvString[:-1]

# Sent from OS to NS.  Given the current view and current nsLeader (based on nsView sent in original message)
# send all keys NS will be responsible for from this replica
def sendSendKeysResponse(sock, msn, nsAddrs, osView, nsView, filteredKVStore):
    nsLeaderAddr = nsAddrs[nsView % len(nsAddrs)]
    m = generateSendKeysResponse(msn, osView, nsView, filteredKVStore)
    sendMessage(m, sock, IP=nsLeaderAddr.ip, PORT=nsLeaderAddr.port)

# Sent from OS to NS.  Given the current view and list of addresses in NS, send all keys
# NS will be responsible for from this replica
def broadcastSendKeyResponse(sock, msn, nsAddrs, osView, nsView, filteredKVStore):
    m = generateSendKeysResponse(msn, osView, nsView, filteredKVStore)
    for addr in nsAddrs:
        sendMessage(m, sock, IP=addr.ip, PORT=addr.port)

#-------------------------
#      KEYS_LEARNED
#-------------------------

# Returns True if 'Success' is unpacked (only thing it sends, probably don't need this function)

def unpackKeysLearnedData(msg):
    return msg

# Outputs, "Type,MSN,SMRV Data", where smrv = osMRV and msn will be 1
def generateKeysLearned(nsMRV, msn, sid):
    return str(MessageTypes.KEYS_LEARNED) + "," + str(msn) + "," + str(nsMRV) + " " + str(sid)

def sendKeysLearned(sock, nsMRV, osLeaderIP, osLeaderPort, msn, sid):
    m = generateKeysLearned(nsMRV, msn, sid)
    sendMessage(m, sock, IP=osLeaderIP, PORT=osLeaderPort)

#-------------------------
#      SHARD_READY
#-------------------------

def generateShardReadyLearned(msn, newShardView, lowerKeyBound, upperKeyBound):
    lkb = str(lowerKeyBound)
    ukb = str(upperKeyBound)
    returnString = str(MessageTypes.SHARD_READY)
    returnString += ","
    returnString += str(msn)
    returnString += ","
    returnString += str(newShardView)
    returnString += ","
    returnString += str(int(lkb))
    returnString += ","
    returnString += str(int(ukb))

    return returnString

# Learner has learned SHARD_READY value and sends it to master
def sendShardReadyLearned(sock, masterAddr, msn, nsMRV, lowerKeyBound, upperKeyBound):
    lowerKeyBound = str(lowerKeyBound)
    upperKeyBound = str(upperKeyBound)
    print "LKB: " + lowerKeyBound + " - UKB: " + upperKeyBound
    m = generateShardReadyLearned(msn, nsMRV, lowerKeyBound, upperKeyBound)
    sendMessage(m, sock, IP=masterAddr.ip, PORT=masterAddr.port)
