import time
import shardMessages

# def broadcastSendKeyRequest(sock, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
# def broadcastSendKeyResponse(sock, nsAddrs, osView, filteredKVStore):

# Client must call sock.close() before calling thread.kill()
# Must be called like oldShardAddrList[:], int(o/nsMRV), int(upper/lowerKB), str(addrString) so they are copies not references
def sendSendKeyRequestWithTimeout(sock, msn, oldShardAddrList, osMRV, nsMRV,
                                       lowerKeyBound, upperKeyBound, addrString):
    shardMessages.sendSendKeysRequest(sock, msn, oldShardAddrList, osMRV, nsMRV,
                                          lowerKeyBound, upperKeyBound, addrString)
    while True:
        time.sleep(1)
        try:
            shardMessages.broadcastSendKeyRequest(sock, msn, oldShardAddrList, osMRV, nsMRV,
                                             lowerKeyBound, upperKeyBound, addrString)
            # increment view
            osMRV += 1
        except:
            print "EXCEPT IN THREAD2"
            return


# Client must call sock.close() before calling thread.kill()
# Must be called like nsAddrs[:], int(osView), filteredKVStore[:] so they are copies not references
def sendSendKeyResponseWithTimeout(sock, msn, nsAddrs, osView, nsView, filteredKVStore):
    shardMessages.sendSendKeysResponse(sock, msn, nsAddrs, osView, nsView, filteredKVStore)
    while True:
        time.sleep(1)
        try:
            shardMessages.broadcastSendKeyResponse(sock, msn, nsAddrs, osView, nsView, filteredKVStore)
            # Increment view
            nsView += 1
        except:
            print "EXCEPT IN THREAD"
            return

