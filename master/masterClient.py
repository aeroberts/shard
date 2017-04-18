import argparse
import socket

from paxos.paxosHelpers import MessageTypes,getMessageTypeString
from paxos.paxosHelpers import ClientAddress
from paxos.paxosHelpers import messages
import masterMessages

# Globals / constants
TIMEOUT_DEFAULT = 20
REQUEST_TYPES = ["GET", "PUT", "DELETE", "ADD_SHARD"]

def handleMasterResponse(data, highestAccepted):
    responseType, responseSN, key, value = masterMessages.unpackMasterResponse(data)

    if responseSN <= highestAccepted:
        print "Error: Received older sequence number response from master"

    elif responseSN >= highestAccepted+2:
        print "Error: Received sequence number greater than most recent sent"

    else:
        print "Performed request:",getMessageTypeString(responseType)," k:",key,"v:",value

    success = validateResponse(responseType, key, value)
    if success:
        print "Successful response"
    else:
        print "Unsuccessful response"

    # TODO: Double check this logic
    return responseSN

def validateResponse(responseType, key, value):
    if responseType == None:
        print "Error unpacking. No Type"
        return False

    if responseType == MessageTypes.GET or responseType == MessageTypes.PUT:
        if key == "None" or value == "None":
            print "Received response with no key or value for GET/PUT. Key:", key, "Value:", value
            return False

    if responseType == MessageTypes.DELETE:
        if key == "None":
            print "Received response with no key for DELETE"
            return False

    if responseType == MessageTypes.ADD_SHARD:
        if key != "Success":
            print "Unsuccessful ADD_SHARD Response"
            return False

    return True

def sendRequest(csock, master, request):
    sendRequest.timeout = TIMEOUT_DEFAULT

    if not args.dropFirst:
        messages.sendMessage(request, csock, IP=master.ip, PORT=master.port)
        if debugMode: print "Sent message:", request
    else:
        args.dropFirst = False

    try: # Wait to receive response from master, broadcast to all replicas if fail
        csock.settimeout(sendRequest.timeout)
        data, addr = csock.recvfrom(1024)

        if debugMode: print "Received message:", data
        sendRequest.highestAccepted = handleMasterResponse(data, sendRequest.highestAccepted)
        return

    except socket.timeout:
        #sendRequest.timeout *= 2
        while True:
            messages.sendMessage(request, csock, IP=master.ip, PORT=master.port)
            if debugMode: print "TIMEOUT.  Resend message: ", request

            try:
                csock.settimeout(sendRequest.timeout)
                data, addr = csock.recvfrom(1024)

                if debugMode: print "Received message:", data
                sendRequest.highestAccepted = handleMasterResponse(data, sendRequest.highestAccepted)
                return

            except socket.timeout:
                print "Yeah ok"
                #sendRequest.timeout *= 2

# Checks if the input is valid or not
# Returns false if the input is invalid, returns the message to send otherwise
def validateInput(userInput, seqNum):
    try:
        mType, content = userInput.split(" ", 1)

    except ValueError:
        print "Not enough arguments supplied.  Requests can be of the form: GET _key_, PUT _key_ _val_, " \
              "DELETE _key_, and ADD_SHARD IP,PORT IP,PORT ... IP,PORT"
        return False

    if mType.upper() not in REQUEST_TYPES:
        print "Request type not found.  Requests can be of the form: GET _key_, PUT _key_ _val_, " \
              "DELETE _key_, and ADD_SHARD"
        return False

    if mType.upper() == "GET":
        if not content.isalnum():
            print "Invalid key.  Keys must be alphanumeric only"
            return False

        return str(MessageTypes.GET) + "," + str(seqNum) + " " + content + ",None"

    if mType.upper() == "DELETE":
        if not content.isalnum():
            print "Invalid key.  Keys must be alphanumeric only"
            return False

        return str(MessageTypes.DELETE) + "," + str(seqNum) + " " + content + ",None"

    if mType.upper() == "PUT":
        try:
            k,v = content.split(" ",1)

        except ValueError:
            print "Invalid Key/Value pair, must include value for PUT"
            return False

        if not k.isalnum():
            print "Invalid key.  Keys must be alphanumeric only"
            return False

        if len(v) == 0:
            print "Invalid value for PUT, value must be alphanumeric only"
            return False

        return str(MessageTypes.PUT) + "," + str(seqNum) + " " + k + "," + v

    # TODO: Do we need to check that IP,PORT pairs don't already exist in another cluster?
    if mType.upper() == "ADD_SHARD":
        addresses = userInput.split(" ")
        for addr in addresses:
            try:
                ip, port = addr.split(",", 1)
                port = int(port)

            except ValueError:
                print "Invalid ADD_SHARD request.  Must be of type ADD_SHARD IP,PORT IP,PORT ... IP,PORT"

        return str(MessageTypes.ADD_SHARD) + "," + str(seqNum) + " " + content

        return False

    return False

def interactiveMode(csock, master):
    sequenceNum = 0
    while True:
        userInput = raw_input('Type your request: ')
        if len(userInput) == 0:
            continue

        message = validateInput(userInput, sequenceNum)
        if message == False:
            continue

        sendRequest(csock, master, message)
        sequenceNum += 1

def batchMode(batchFN, csock, master):
    sequenceNum = 0
    with open(batchFN) as batchFile:
        for line in batchFile:
            if len(line) == 0:
                continue

            message = validateInput(line, sequenceNum)
            if message == False:
                continue

            sendRequest(csock, master, message)
            sequenceNum += 1

#---------------------------------------------------------------
#
#                 Initialize Client Process
#
#---------------------------------------------------------------
# Pull command line arguments - numFails required, batch mode and filename optional
parser = argparse.ArgumentParser(prog='client')
parser.add_argument('input_file', help="Input config file for client of form [master_ip master_port client_ip")
parser.add_argument('-b', '--batch', action='store', help="Batch mode and associated batch messages to send")
parser.add_argument('-d', '--debug', action='store_true', help="Enable extra debug printing")
parser.add_argument('-r', '--dropRandom', action='store', help='Randomly drop all sent messages dropRandom% of the time')
parser.add_argument('-f', '--dropFirst', action='store_true', help='Drop first request sent')
args = parser.parse_args()
messages.sendMessage.dropRandom = False

if args.dropFirst:
    print "Client will 'drop' first message sent"


if args.dropRandom is not None:
    messages.sendMessage.dropRandom = args.dropRandom
else:
    messages.sendMessage.dropRandom = False

masterIP = None
masterPort = None
clientIP = None
with open(args.input_file) as inputFile:
    for line in inputFile:
        inputLine = line.split(" ")
        assert(len(inputLine) == 3 and len(inputLine[0]) > 0 and len(inputLine[1]) > 0 and len(inputLine[2]) > 0)
        masterIP = inputLine[0]
        masterPort = inputLine[1]
        ip = inputLine[2]

master = ClientAddress(masterIP, int(masterPort))
batch = args.batch
debugMode = args.debug

if debugMode: print "Batch:", batch

sendRequest.timeout = 4
sendRequest.highestAccepted = -1

# Get hosts from config file
# (For now) send to master (any of them)
csock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
bound = False
port = 6000
while not bound:
    try:
        csock.bind((ip, port))
        bound = True
    except:
        port += 1

if debugMode: print "Bound on port", port


# Check if batch mode
if batch:
    batchMode(batch, csock, master)
else:
    interactiveMode(csock, master)
