import time
import shardMessages
import errno
import os

PROC_DEFAULT_TIMEOUT = 8

# pid_exists adapated from
# http://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
def pid_exists(pid):
    """Check whether pid exists in the current process table.
    UNIX only.
    """
    if pid < 0:
        return False
    if pid == 0:
        # According to "man 2 kill" PID 0 refers to every process
        # in the process group of the calling process.
        # On certain systems 0 is a valid PID but we have no way
        # to know that in a portable fashion.
        raise ValueError('invalid PID 0')
    try:
        os.kill(pid, 0)
    except OSError as err:
        if err.errno == errno.ESRCH:
            # ESRCH == No such process
            return False
        elif err.errno == errno.EPERM:
            # EPERM clearly means there's a process to deny access to
            return True
        else:
            # According to "man 2 kill" possible error values are
            # (EINVAL, EPERM, ESRCH)
            print "Warning: Should never reach here"
            return False
    else:
        return True

# def broadcastSendKeyRequest(sock, oldShardAddrList, osMRV, nsMRV, lowerKeyBound, upperKeyBound, addrString):
# def broadcastSendKeyResponse(sock, nsAddrs, osView, filteredKVStore):

# Client must call sock.close() before calling proc.kill()
# Must be called like oldShardAddrList[:], int(o/nsMRV), int(upper/lowerKB), str(addrString) so they are copies not references
def sendSendKeyRequestWithTimeout(sock, msn, oldShardAddrList, osMRV, nsMRV,
                                       lowerKeyBound, upperKeyBound, addrString, replicaPid):
    shardMessages.sendSendKeysRequest(sock, msn, oldShardAddrList, osMRV, nsMRV,
                                          lowerKeyBound, upperKeyBound, addrString)
    while True:
        time.sleep(PROC_DEFAULT_TIMEOUT)
        if pid_exists(replicaPid):
            print "Parent doesn't exist, exit"
            exit()
        try:
            shardMessages.broadcastSendKeyRequest(sock, msn, oldShardAddrList, osMRV, nsMRV,
                                             lowerKeyBound, upperKeyBound, addrString)
            # increment view
            osMRV += 1
        except:
            print "EXCEPT IN THREAD2"
            return



# Client must call sock.close() before calling proc.kill()
# Must be called like nsAddrs[:], int(osView), filteredKVStore[:] so they are copies not references
def sendSendKeyResponseWithTimeout(sock, msn, nsAddrs, osView, nsView, filteredKVStore, replicaPid):
    print "In SSKRWT, nsAddrs:",str(nsAddrs)
    shardMessages.sendSendKeysResponse(sock, msn, nsAddrs, osView, nsView, filteredKVStore)
    while True:
        time.sleep(PROC_DEFAULT_TIMEOUT)
        if pid_exists(replicaPid) is False:
            print "Parent doesn't exist, exit"
            exit()

        try:
            shardMessages.broadcastSendKeyResponse(sock, msn, nsAddrs, osView, nsView, filteredKVStore)
            # Increment view
            nsView += 1
        except:
            print "EXCEPT IN THREAD"
            exit()

