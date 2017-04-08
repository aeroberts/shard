from hashlib import md5

def hashKey(key):
    return md5.new(key).digest()
