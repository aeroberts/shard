from hashlib import md5

def hashKey(key):
    #digest = md5.new(key).digest()
    #print "Digest type: " + type(digest) + " - value: " + str(digest) + " - as long: " + str(long(digest))
    return md5.new(key).digest()

