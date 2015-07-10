__author__ = 'chris'
"""
Just using this class for testing the DHT for now.
We will fit the actual implementation in where appropriate.
"""
import stun
import pickle

from twisted.application import service, internet
from twisted.python.log import ILogObserver

from bitcoin import *

from binascii import hexlify, unhexlify

from txjsonrpc.netstring import jsonrpc

from guidutils.guid import GUID

from dht.utils import digest
from dht.network import Server
from dht import log
from dht.node import Node


response = stun.get_ip_info(stun_host="stun.l.google.com", source_port=0, stun_port=19302)
ip_address = response[1]
port = response[2]

sys.path.append(os.path.dirname(__file__))
application = service.Application("openbazaar")
application.setComponent(ILogObserver, log.FileLogObserver(sys.stdout, log.INFO).emit)

# key generation for testing
if os.path.isfile('keys.pickle'):
    keys = pickle.load(open("keys.pickle", "r"))
    g = keys["guid"]
else:
    print "Generating GUID, stand by..."
    g = GUID()
    keys = {'guid': g}
    pickle.dump(keys, open("keys.pickle", "wb"))

# kademlia
node = Node(g.guid, ip=ip_address, port=port, signed_pubkey=g.signed_pubkey)
kserver = Server(node)
kserver.bootstrap(kserver.querySeed("162.213.253.147:8080"))
server = internet.UDPServer(18467, kserver.protocol)
server.setServiceParent(application)


# RPC-Server
class RPCCalls(jsonrpc.JSONRPC):
    def jsonrpc_getpubkey(self):
        return hexlify(g.signed_pubkey)

    def jsonrpc_getinfo(self):
        info = {"version": "0.1"}
        num_peers = 0
        for bucket in kserver.protocol.router.buckets:
            num_peers += bucket.__len__()
        info["known peers"] = num_peers
        info["stored messages"] = len(kserver.storage.data)
        size = sys.getsizeof(kserver.storage.data)
        size += sum(map(sys.getsizeof, kserver.storage.data.itervalues())) + sum(
            map(sys.getsizeof, kserver.storage.data.iterkeys()))
        info["db size"] = size
        return info

    def jsonrpc_set(self, keyword, key):
        def handle_result(result):
            print "JSONRPC result:", result

        d = kserver.set(str(keyword), digest(key), node.proto.SerializeToString())
        d.addCallback(handle_result)
        return "Sending store request..."

    def jsonrpc_get(self, keyword):
        def handle_result(result):
            print "JSONRPC result:", result

        d = kserver.get(keyword)
        d.addCallback(handle_result)
        return "Sent get request. Check log output for result"

    def jsonrpc_delete(self, keyword, key):
        def handle_result(result):
            print "JSONRPC result:", result

        signature = g.signing_key.sign(digest(key))
        d = kserver.delete(str(keyword), digest(key), signature[:64])
        d.addCallback(handle_result)
        return "Sending delete request..."

    def jsonrpc_shutdown(self):
        for addr in kserver.protocol:
            connection = kserver.protocol._active_connections.get(addr)
            if connection is not None:
                connection.shutdown()
        return "Closing all connections."


factory = jsonrpc.RPCFactory(RPCCalls)
factory.addIntrospection()
jsonrpcServer = internet.TCPServer(18465, factory, interface="127.0.0.1")
jsonrpcServer.setServiceParent(application)
