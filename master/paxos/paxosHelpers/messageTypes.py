class MessageTypes:
    PREPARE_REQUEST, \
    PREPARE_ALLOWDISALLOW, \
    SUGGESTION_REQUEST, \
    SUGGESTION_FAILURE, \
    SUGGESTION_ACCEPT, \
    HIGHEST_OBSERVED, \
    HOLE_REQUEST, \
    HOLE_RESPONSE, \
    PUT, \
    GET, \
    DELETE, \
    ADD_SHARD, \
    START_SHARD, \
    SEND_KEYS_REQUEST, \
    SEND_KEYS, \
    SEND_KEYS_RESPONSE, \
    BATCH_PUT, \
    BEGIN_STARTUP, \
    KEYS_LEARNED, \
    SHARD_READY, \
    CHANGE_BOUNDS = range(21)

    typeRange = 21

def getMessageTypeString(messageType):
    messageType = int(messageType)
    return {
        MessageTypes.PREPARE_REQUEST: "PREPARE_REQUEST",
        MessageTypes.PREPARE_ALLOWDISALLOW: "PREPARE_ALLOWDISALLOW",
        MessageTypes.SUGGESTION_REQUEST: "SUGGESTION_REQUEST",
        MessageTypes.SUGGESTION_ACCEPT: "SUGGESTION_ACCEPT",
        MessageTypes.SUGGESTION_FAILURE: "SUGGESTION_FAILURE",
        MessageTypes.HIGHEST_OBSERVED: "HIGHEST_OBSERVED",
        MessageTypes.HOLE_REQUEST: "HOLE_REQUEST",
        MessageTypes.HOLE_RESPONSE: "HOLE_RESPONSE",
        MessageTypes.PUT: "PUT",
        MessageTypes.GET: "GET",
        MessageTypes.DELETE: "DELETE",
        MessageTypes.ADD_SHARD: "ADD_SHARD",
        MessageTypes.SEND_KEYS_REQUEST: "SEND_KEYS_REQUEST",
        MessageTypes.SEND_KEYS: "SEND_KEYS",
        MessageTypes.SEND_KEYS_RESPONSE: "SEND_KEYS_RESPONSE",
        MessageTypes.BATCH_PUT: "BATCH_PUT",
        MessageTypes.BEGIN_STARTUP: "BEGIN_STARTUP",
        MessageTypes.KEYS_LEARNED: "KEYS_LEARNED",
        MessageTypes.SHARD_READY: "SHARD_READY",
        MessageTypes.CHANGE_BOUNDS: "CHANGE_BOUNDS"
    }[messageType]
