import threading
import time
import socket
import messages
import messageTypes

#def broadcastSendKeyRequest(sock, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
#def broadcastSendKeyResponse(sock, nsAddrs, osView, filteredKVStore):

# Client must call sock.close() before calling thread.kill()
# Must be called like oldShardAddrList[:], int(o/nsMRV), int(upper/lowerKB), str(addrString) so they are copies not references
def broadcastSendKeyRequestWithTimeout(sock, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
    while True:
        try:
            messages.broadcastSendKeyRequest(sock, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString)
            time.sleep(1)
        except:
            print "EXCEPT IN THREAD2"
            return


# Client must call sock.close() before calling thread.kill()
# Must be called like nsAddrs[:], int(osView), filteredKVStore[:] so they are copies not references
def broadcastSendKeyResponseWithTimeout(sock, nsAddrs, osView, filteredKVStore):
    while True:
        try:
            messages.broadcastSendKeyResponse(sock, nsAddrs, osView, filteredKVStore)
            time.sleep(1)
        except:
            print "EXCEPT IN THREAD"
            return

