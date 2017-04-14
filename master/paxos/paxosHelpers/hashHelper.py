from hashlib import md5

def hashKey(key):
    #digest = md5.new(key).digest()
    #print "Digest type: " + type(digest) + " - value: " + str(digest) + " - as long: " + str(long(digest))
    m = md5()
    m.update(key)
    return int(m.hexdigest(), 16)

def getMaxHashVal():
    return 340282366920938463463374607431768211455