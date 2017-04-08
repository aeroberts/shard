from clientRequest import ClientRequest
from paxos import MessageTypes

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
    print "hi"

# Given a client request and shard data, forward the client request to current shard leader
# thought to be alive
def sendRequestForward(clientRequest, shardData, masterSeqNum):
    generateRequestForward(clientRequest, shardData, masterSeqNum)
    print "hihi"
