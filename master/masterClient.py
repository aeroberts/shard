import argparse
import socket

from paxos.helpers import MessageTypes
from paxos.helpers import ClientAddress
from paxos.helpers import messages
import masterMessages

# Globals / constants
TIMEOUT_DEFAULT = 2
REQUEST_TYPES = ["GET", "PUT", "DELETE", "ADD_SHARD"]


def handleMasterResponse(data, highestAccepted):
    responseType, responseSN, key, value = masterMessages.unpackMasterResponse(data)

    if responseSN <= highestAccepted:
        print "Error: Received older sequence number response from master"

    elif responseSN >= highestAccepted+2:
        print "Error: Received sequence number greater than most recent sent"

    else:
        print "Performed request:",responseType," k:",key,"v:",value

    success = validateResponse(responseType, key, value)
    if success:
        print "Successful response"
    else:
        print "Unsucessful response"

    return

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
    messages.sendMessage(request, csock, IP=master.ip, PORT=master.port)
    if debugMode: print "Sent message:", request

    try: # Wait to receive response from master, broadcast to all replicas if fail
        csock.settimeout(sendRequest.timeout)
        data, addr = csock.recvfrom(1024)

        if debugMode: print "Received message:", data
        sendRequest.highestAccepted = handleMasterResponse(data, False, sendRequest.highestAccepted)
        return

    except socket.timeout:
        sendRequest.timeout *= 2
        while True:
            messages.sendMessage(request, csock, IP=master.ip, PORT=master.port)
            if debugMode: print "TIMEOUT.  Resend message: ", request

            try:
                csock.settimeout(sendRequest.timeout)
                data, addr = csock.recvfrom(1024)

                if debugMode: print "Received message:", data
                sendRequest.highestAccepted = handleMasterResponse(data, False, sendRequest.highestAccepted)
                return

            except socket.timeout:
                sendRequest.timeout *= 2

# Checks if the input is valid or not
# Returns false if the input is invalid, returns the message to send otherwise
def validateInput(userInput, seqNum):
    try:
        mType,content = userInput.split(" ", 1)

    except ValueError:
        print "Invalid request.  Requests can be of the form: GET _key_, PUT _key_ _val_, " \
              "DELETE _key_, and ADD_SHARD"
        return False

    if mType not in REQUEST_TYPES:
        print "Invalid request.  Requests can be of the form: GET _key_, PUT _key_ _val_, " \
              "DELETE _key_, and ADD_SHARD"
        return False

    if mType == "GET" or mType == "DELETE":
        if not content.isalnum():
            print "Invalid key.  Keys must be alphanumeric only"
            return False

        return str(MessageTypes.GET) + "," + str(seqNum) + " " + content + ",None"

    if mType == "PUT":
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

        return str(MessageTypes.GET) + "," + str(seqNum) + " " + k + "," + v

    if mType == "ADD_SHARD":
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
            sendRequest(csock, master, line)
            sequenceNum += 1

#---------------------------------------------------------------
#
#                 Initialize Client Process
#
#---------------------------------------------------------------
# Pull command line arguments - numFails required, batch mode and filename optional
parser = argparse.ArgumentParser(prog='client')
parser.add_argument('master_ip', help="Cluster master ip address")
parser.add_argument('master_port', help="Cluster master port number")
parser.add_argument('ip', help="This machine's public facing IP")
parser.add_argument('-b', '--batch', action='store', help="Batch mode and associated batch messages to send")
parser.add_argument('-d', '--debug', action='store_true', help="Enable extra debug printing")
args = parser.parse_args()

masterIP = args.master_ip
masterPort = args.master_port
master = ClientAddress(masterIP, int(masterPort))

ip = args.ip
batch = args.batch
debugMode = args.debug

if debugMode: print "Batch:",batch

sendRequest.timeout = 2
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
