from clientRequest import ClientRequest
from paxos import MessageTypes,messages

# Unpack Type,CSN, Data message from client to return (Type, CSN, Data)
def unpackClientMessage(data, addr):
    metadata, message = data.split(" ", 1)
    metadata = metadata.split(",")

    assert(len(metadata) == 2)
    assert(len(metadata[0]) > 0)
    assert(len(metadata[1]) > 0)

    mType = int(metadata[0])
    csn = int(metadata[1])

    key = None
    val = None
    if mType == MessageTypes.GET or mType == MessageTypes.DELETE:
        key = message

    elif mType == MessageTypes.PUT:
        key,val = message.split(",",1)

    else: # Add Shard
        print "Figure this out later"

    return ClientRequest(metadata[0],key,val,addr,metadata[1])


# Generate Client Request to forward to shard (either broadcast or otherwise)
def generateRequestForward(clientRequest, shardData, masterSeqNum):
    return str(clientRequest.type) + "," + \
           str(masterSeqNum) + "," + str(shardData.mostRecentView) + " " + \
           str(clientRequest.key) + "," + str(clientRequest.value)

# Given a client request and shard data, forward the client request to current shard leader
# thought to be alive
# Returns [ Type, MasterSeqNum, ShardMostRecentView, Key, Val ]
#   If error, Key = None, Val = Error
def sendRequestForward(sock, clientRequest, shardData, masterSeqNum):
    message = generateRequestForward(clientRequest, shardData, masterSeqNum)
    laddr = shardData.getLeaderAddress()
    messages.sendMessage(message, sock, IP=laddr.ip, PORT=laddr.port)
    return

def unpackClusterResponse(data):
    metadata, message = data.split(" ", 1)
    metadata = metadata.split(",")

    assert(len(metadata) == 3)
    assert(len(metadata[0]) > 0)
    assert(len(metadata[1]) > 0)
    assert(len(metadata[2]) > 0)

    mType = int(metadata[0])
    msn = int(metadata[1])
    smrv = int(metadata[2])

    # Could be add shard as well?
    if mType == MessageTypes.GET or mType == MessageTypes.PUT or mType == MessageTypes.DELETE:
        try:
            key,val = message.split(",", 1)
        except ValueError:
            key = None
            val = message

    return mType,msn,smrv,key,val

def generateResponseToClient(clientRequest, key, val):
    return str(clientRequest.type) + "," + \
           str(clientRequest.clientSeqNum) + " " + \
           str(key) + "," + str(val)

def sendResponseToClient(sock, clientRequest, key, val):
    message = generateResponseToClient(clientRequest, key, val)
    caddr = clientRequest.clientAddress
    messages.sendMessage(message, sock, IP=caddr.ip, PORT=caddr.port)
    return
