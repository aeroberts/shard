from clientRequest import ClientRequest
from paxos import MessageTypes
from paxos import sendMessage
from paxos import ClientAddress
from paxos import paxosHelpers

# Unpack Type,CSN, Data message from client to return (Type, CSN, Data)
def unpackClientMessage(master, data, addr):
    metadata, message = data.split(" ", 1)
    metadata = metadata.split(",")

    assert(len(metadata) == 2)
    assert(len(metadata[0]) > 0)
    assert(len(metadata[1]) > 0)

    mType = int(metadata[0])
    csn = int(metadata[1])

    curMRV = None

    if mType == MessageTypes.GET or mType == MessageTypes.DELETE:
        key, noneVal = message.split(",", 1)
        val = None
        associatedShard = master.sidToSData[master.getAssociatedSID(key)]
        curMRV = associatedShard.mostRecentView

    elif mType == MessageTypes.PUT:
        key, val = message.split(",", 1)
        associatedShard = master.sidToSData[master.getAssociatedSID(key)]
        curMRV = associatedShard.mostRecentView

    elif mType == MessageTypes.ADD_SHARD:

        caAddressList = []
        addresses = message.split(" ")
        for address in addresses:
            try:
                ip, port = address.split(",")
                #addr = ClientAddress(ip, int(port))
                caAddressList.append(ClientAddress(ip, int(port)))

            except ValueError:
                print "Invalid ADD_SHARD Message received:",message

        key = caAddressList
        val = None
        curMRV = 0

    else: # Error
        print "ERROR: Received invalid message from client"
        return

    print "handle and unpack client message. type: " + paxosHelpers.getMessageTypeString(mType) + " - data: " + str(key) + " | " + str(val) + "\n"

    return ClientRequest(mType,key,val,addr,csn, curMRV)

# Generate Client Request to forward to shard (either broadcast or otherwise)
def generateRequestForward(clientRequest, shardData, masterSeqNum):
    mType = clientRequest.type
    if mType == MessageTypes.GET or mType == MessageTypes.PUT or mType == MessageTypes.DELETE:

        print "\ngenerateRequestForward:"
        print "1: " + str(clientRequest.type)
        print "2: " + str(masterSeqNum)
        print "3: " + str(shardData.mostRecentView)
        print "4: " + str(clientRequest.key)
        print "5: " + str(clientRequest.value)

        reqString = str(clientRequest.type) + "," + \
               str(masterSeqNum) + "," + str(shardData.mostRecentView) + " " + \
               str(clientRequest.key) + "," + str(clientRequest.value)

        return reqString

    elif clientRequest.type == MessageTypes.START_SHARD:
        return str(int(MessageTypes.START_SHARD)) + "," + \
               str(masterSeqNum) + "," + str(shardData.mostRecentView) + " " + \
               str(clientRequest.key) + "," + str(clientRequest.value)


# Given a client request and shard data, forward the client request to current shard leader
# thought to be alive
# Returns [ Type, MasterSeqNum, ShardMostRecentView, Key, Val ]
#   If error, Key = None, Val = Error
def sendRequestForward(sock, clientRequest, shardData):
    message = generateRequestForward(clientRequest, shardData, clientRequest.masterSeqNum)
    laddr = shardData.getLeaderAddress()
    sendMessage(message, sock, IP=laddr.ip, PORT=laddr.port)
    return

def broadcastRequestForward(sock, clientRequest, shardData, masterSeqNum):
    message = generateRequestForward(clientRequest, shardData, masterSeqNum)
    for addr in shardData.replicaAddresses:
        sendMessage(message, sock, IP=addr.ip, PORT=addr.port)

def generateResponseToClient(clientRequest, key, val):
    return str(clientRequest.type) + "," + \
           str(clientRequest.clientSeqNum) + " " + \
           str(key) + "," + str(val)

def sendResponseToClient(sock, clientRequest, responseData):

    print "sendResponseToClient: clientRequest: " + str(clientRequest) + " -- responseData: " + str(responseData)

    # TODO: Update this for non-standard message replies from paxos AKA KEYS_LEARNED and SHARD_READY
    # Alex - KEYS_LEARNED should only occur between two paxos clusters
    responseKey = responseData[1]
    responseVal = responseData[2]
    message = generateResponseToClient(clientRequest, responseKey, responseVal)
    caddr = clientRequest.clientAddress
    sendMessage(message, sock, IP=caddr.ip, PORT=caddr.port)
    return

# FOR CLIENT FROM MASTER
def unpackMasterResponse(data):
    print "Unpack master response: " + str(data)
    metadata, message = data.split(" ", 1)
    metadata = metadata.split(",")

    assert(len(metadata) == 2)
    assert(len(metadata[0]) > 0)
    assert(len(metadata[1]) > 0)

    mType = int(metadata[0])
    csn = int(metadata[1])

    if mType == MessageTypes.GET or mType == MessageTypes.PUT or mType == MessageTypes.DELETE:
        try:
            k,v = message.split(',', 1)
            return mType, csn, k, v

        except ValueError:
            return None, None, message, None

    elif mType == MessageTypes.ADD_SHARD:
        return mType, csn, "Success", None

    elif mType == MessageTypes.START_SHARD:
        bounds = message.split(",")
        assert (len(bounds) == 2)
        assert (bounds[0] is not None and bounds[0] != 'None')
        assert (bounds[1] is not None and bounds[1] != 'None')

        return mType, csn, bounds[0], bounds[1]

    else:
        return None, None, "Invalid Type Returned", None
