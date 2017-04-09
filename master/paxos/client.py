import argparse
import math
import os
import socket
import time

from helpers import messages

# Globals / constants
TIMEOUT_DEFAULT = 5

def handleReplicaResponse(data, isBroadcast, highestAccepted):
    responseView, responseId, responseSN = messages.unpackReplicaResponse(data)

    # Old un-processed message, can safely ignore
    if responseSN <= highestAccepted:
        if debugMode: print "Processing already accepted sequence num"
        return highestAccepted

    if responseSN > highestAccepted:
        if responseSN - highestAccepted > 1:
            print "Error: highest accepted SN is two lower than received"
            exit()
        else:
            if debugMode: print "Next highest learned, can send new message"

    if responseView > sendChat.clientView:
        if not isBroadcast: # Sent single request to master and received response.  SHOULD BE CURRENT VIEW
            print "Error: Received new view from single master"
        sendChat.clientView = responseView

    elif responseView == sendChat.clientView:
        #print "Received same view back"
        if isBroadcast:
            print "Error: Received current view from broadcast"

    else:
        print "Error: Received older view"

    sendChat.mostRecentRecv = True
    return responseSN


def sendChat(csock, hosts, pid, sequenceNum, message, numMajority):
    msg = pid + "," + str(sequenceNum) + "," + str(sendChat.clientView) + " " + message

    sendRid = sendChat.clientView % len(hosts)
    messages.sendMessage(msg, csock, rid=sendRid, hosts=hosts)
    if debugMode: print "Sent message:", msg, "to", sendChat.clientView

    try: # Wait to receive response from master, broadcast to all replicas if fail
        startTime = time.time()
        endTime = time.time()
        elapsed = endTime - startTime

        while elapsed < sendChat.timeout:
            csock.settimeout(sendChat.timeout-elapsed)
            data, addr = csock.recvfrom(1024)
            if debugMode: print "Received message:", data
            sendChat.highestAccepted = handleReplicaResponse(data, False, sendChat.highestAccepted)

            if sendChat.mostRecentRecv:
                break

            endTime = time.time()
            elapsed = endTime - startTime


    except socket.timeout:
        sendChat.timeout = sendChat.timeout*2

        while True:
            msg = pid + "," + str(sequenceNum) + "," + str(sendChat.clientView) + " " + message
            print "Error: Timeout, resend to all replicas", msg
            messages.broadcastMessage(msg, csock, hosts)
            try:
                bStartTime = time.time()
                bEndTime = time.time()
                bElapsed = bEndTime - bStartTime

                while bElapsed < sendChat.timeout:
                    csock.settimeout(sendChat.timeout-bElapsed)
                    data, addr = csock.recvfrom(1024)
                    if debugMode: print "Received message:", data
                    sendChat.highestAccepted = handleReplicaResponse(data, True, sendChat.highestAccepted)

                    if sendChat.mostRecentRecv:
                        break

                    bEndTime = time.time()
                    bElapsed = bEndTime - bStartTime

            except socket.timeout:
                sendChat.timeout = sendChat.timeout*2
                print "Error: Failed to hear from any replicas on broadcast, increment view and rebroadcast"
                sendChat.clientView += 1

            else:
                sendChat.timeout = TIMEOUT_DEFAULT
                break
    else:
        sendChat.timeout = TIMEOUT_DEFAULT

    sequenceNum += 1


def interactiveMode(csock, hosts, pid, numFailures):
    numMajority = math.floor((len(hosts)/2)+1)
    sequenceNum = 0
    while True:
        userInput = raw_input('Type your message: ')
        if len(userInput) == 0:
            continue

        sendChat.mostRecentRecv = False
        sendChat(csock, hosts, pid, sequenceNum, userInput, numMajority)
        sequenceNum += 1

def batchMode(batchFN, csock, hosts, pid, numFailures):
    numMajority = math.floor((len(hosts)/2)+1)
    sequenceNum = 0
    with open(batchFN) as batchFile:
        for line in batchFile:
            sendChat.mostRecentRecv = False
            sendChat(csock, hosts, pid, sequenceNum, line, numMajority)
            sequenceNum += 1

#---------------------------------------------------------------
#
#                 Initialize Client Process
#
#---------------------------------------------------------------
# Pull command line arguments - numFails required, batch mode and filename optional
parser = argparse.ArgumentParser(prog='client')
parser.add_argument('numFails', help="The number of acceptable failures")
parser.add_argument('hosts', help="Hosts config file -- lines of ip port for all hosts")
parser.add_argument('ip', help="This machine's public facing IP")
parser.add_argument('-b', '--batch', action='store', help="Batch mode and associated batch messages to send")
parser.add_argument('-d', '--debug', action='store_true', help="Enable extra debug printing")
args = parser.parse_args()

numFailures = args.numFails
hostsFile = args.hosts
ip = args.ip
batch = args.batch
debugMode = args.debug

if debugMode: print "Batch:",batch

sendChat.timeout = 5
sendChat.clientView = 0
sendChat.highestAccepted = -1

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

hosts = messages.getHosts(hostsFile)
pid = str(os.getpid())

# Check if batch mode
if batch:
    batchMode(batch, csock, hosts, pid, numFailures)
else:
    interactiveMode(csock, hosts, pid, numFailures)
