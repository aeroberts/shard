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


#def generateHoleResponse(seqNum, view, clientId, clientSeqNum, aVal):
    #return str(MessageTypes.HOLE_RESPONSE) + "," + str(seqNum) + "," + \
           #str(None) + "," + str(None) + "," + str(view) + " " + \
           #str(clientId) + "," + str(clientSeqNum) + "," + str(aVal)
#
# Returns (cid, csn, val)
# from valid HOLE_RESPONSE
#def unpackHoleResponse(msg):
    #unpackedMessage = msg.split(",")
    #assert len(unpackedMessage) == 3
#
    #if str(unpackedMessage[0]) != 'None' and unpackedMessage[0] is not None:
        #unpackedMessage[0] = str(unpackedMessage[0])
    #else:
        #unpackedMessage[0] = None
#
    #if str(unpackedMessage[1]) != 'None' and unpackedMessage[1] is not None:
        #unpackedMessage[1] = int(unpackedMessage[1])
    #else:
        #unpackedMessage[1] = None
#
    #if str(unpackedMessage[2]) != 'None' and unpackedMessage[2] is not None:
        #unpackedMessage[2] = str(unpackedMessage[2])
    #else:
        #unpackedMessage[2] = None
#
    #return unpackedMessage
#
## Sends accepted value in log to new primary in response to HOLE REQUEST
## at log entry 'seqNum'
#def sendHoleResponse(replica, newPrimaryRid, seqNum, clientId, clientSeqNum, aVal):
    #m = generateHoleResponse(seqNum, replica.currentView, clientId, clientSeqNum, aVal)
    #sendMessage(m, replica.sock, rid=newPrimaryRid, hosts=replica.hosts)
#
#
#####def unpackClusterMessage(data, addr):