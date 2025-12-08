from enum import Enum

"""
    Class that specifies all used packet types.
"""
class PacketTypes(Enum):    
    UNKNOWN = "unknown"            # unknown packet, used before a packet is classified.
    DATA = "data"                  # data packet
    ROUTING = "routing"            # control-plane packet, supposed to be exchanged between routing daemons
    ICMP = "icmp"                  # error packet
    BROADCAST = "BCAST"            # packet sent in broadcast
    UNKNOWNADDR = "UNKNOWN_ADDR"   # unknown address

"""
    Class that represents the payload of a packet.
"""
class Payload:
    def __init__(self):
        self._data = list()
    
    def addEntry(self, o):
        self._data.append(str(o))

    def getData(self):
        return self._data
  
    def __str__(self):
        return str(self._data)

"""
    Class that models a network packet. 
"""
class Packet:
    def __init__(self, s, d):
        self._src = s
        self._dst = d
        self._srcport = 50000
        self._dstport = 8080
        self._type = PacketTypes.UNKNOWN.value
        self._data = Payload()
        self._seq = 0
        self._ttl = 255

    def __str__(self):
        s = "type {} src {}:{} dst {}:{} ttl {} seq {}".format(self._type, self._src, self._srcport, self._dst, self._dstport, self._ttl, self._seq)
        if self._type == PacketTypes.DATA.value:
            if len(self._data.getData()) > 0:
                s += " path"
                d = self._data.getData()
                for i in d:
                    s += " ({})".format(i)
        else:
            s += " payload {}".format(self._data)
        return "<{}>".format(s)

    def getSource(self):
        return self._src

    def getDestination(self):
        return self._dst

    def getSourcePort(self):
        return self._srcport

    def getDestinationPort(self):
        return self._dstport

    def getType(self):
        return self._type;

    def getSequenceNumber(self):
        return self._seq

    def getPayload(self):
        return self._data

    def getTtl(self):
        return self._ttl

    def setSourcePort(self, val):
        self._srcport = val

    def setDestinationPort(self, val):
        self._dstport = val

    def setSequenceNumber(self, s):
        self._seq = s

    def setType(self, t):
        self._type = t

    def setPayload(self, d):
        if type(d) != Payload:
            raise Exception("ERROR: cannot set the payload of a packet to a type {}, different from {}".format(type(d),Payload))
        self._data = d

    def decrementTtl(self):
        self._ttl -= 1

    def setTtl(self,value):
        self._ttl = int(value)

"""
    Class that represents a control-plane packet exchanged between routing daemons.
"""
class RoutingPacket(Packet):
    def __init__(self, src):
        super().__init__(src,None)
        self._src = src
        self._dst = PacketTypes.BROADCAST.value
        self._type = PacketTypes.ROUTING.value
        self._srcport = 2300
        self._dstport = 2300

