import hashlib, ipaddress
from link import Link
from packet import Packet,PacketTypes

"""
    This class models the forwarding table of a router,
    used by the router to forward packets.
"""
class ForwardingTable:
    LOOPBACK = "local"

    def __init__(self):
        self._table = {}
        self._numWrites = 0

    def setEntry(self,destination,outifaces):
        if not type(outifaces) is list:
            raise Exception("Incorrect format of FIB entry: outgoing interfaces {} are not a list".format(outifaces))
        dest_network = ipaddress.ip_network(destination)
        self._table[dest_network] = outifaces
        self._numWrites += 1

    def setEntryLocal(self,destination):
        self.setEntry(ipaddress.ip_network(destination),[self.LOOPBACK])

    def removeEntry(self,destination):
        self._table.pop(ipaddress.ip_network(destination),None)

    def getEntry(self,destination):
        if destination not in self._table:
            return []   
        return sorted(self._table[destination])

    def getNextHops(self,destination):
        nhs = []
        curr_match = None
        dest_ip = ipaddress.ip_address(destination)
        for k in self._table:
            if dest_ip not in k:   
                continue
            if not curr_match or k.subnet_of(curr_match):
                curr_match = k
        if curr_match:
            nhs = self._table[curr_match]
        return sorted(nhs)

    def getTotalWrites(self):
        return self._numWrites

    def __str__(self):
        desc = ""
        alldests = list(self._table.keys())
        if len(alldests) == 0:
            return "<empty>\n"
        for d in sorted(alldests):
            if self._table[d] == ["local"]:
                desc += "{} directly connected\n".format(d)
            else:
                desc += "{} via {}\n".format(d,", ".join(self._table[d]))
        return desc

    def getDescription(self,routerid):
        return "FIB router {}\n{}".format(routerid,self)

"""
    This class implements the data-plane logic of the simulated router.
    It implements forwarding, but delegates the computation of forwarding
    entries to an input RoutingAlgorithm.
"""
class Router:
    _SENT = 0
    _RECV = 1
    _DROP = 2
    _FORW = 3
    
    """
        The Router constructor takes as input
        - rId: the router id
        - numOfInterfaces: number of physical network interfaces of the router
        - ra: the routing algorithm
    """
    def __init__(self, rId, rIP):
        self._id = rId
        self._ip = rIP
        self._links = {}
        self._fib = ForwardingTable()

        self._counter = [0,0,0,0,0]
        self._counter[self._SENT] = 0
        self._counter[self._RECV] = 0
        self._counter[self._DROP] = 0
        self._counter[self._FORW] = 0
        self._numSentRoutingPackets = 0       # sent control-plane packets
        self._originatedIcmpPackets = {}      # interface receiving expired packets -> number of received expired packets

        self._ralg = None
        self._current_time = 0
        self._update_interval = 1
        self._updates_buffer = []

        self._ifaces_noicmp = set([])
        self._last_traceout = None

        self._verbose = False
        print("Created router {}".format(self.getId()))

    def addLink(self, l):
        i0 = l.getInterface(0)
        r0 = l.getRouter(0)
        i1 = l.getInterface(1)
        r1 = l.getRouter(1)
        print("Adding link {} to {}".format(l,self._id))
        if (r0 == self._id):
            self._links[i0] = l
        elif (r1 == self._id):
            self._links[i1] = l

    def setTimeStep(self, time):
        self._current_time = int(time)

    def setUpdateInterval(self, value):
        self._update_interval = int(value)

    def setRoutingDaemon(self, ra):
        self._ralg = ra
        self._ralg.bindToRouter(self._id,self._ip,self._fib)

    def setVerbose(self, value):
        self._verbose = value
        self._ralg.setVerbose(value)

    def getId(self):
       return self._id;

    def getIp(self):
        return self._ip

    def getLinks(self):
       return self._links

    def getForwardingTable(self):
       return self._fib

    def getCurrentRoutes(self):
        return self._ralg.getCurrentRoutes()

    def getReceivedRoutes(self,neighbour_ip):
        return self._ralg.getReceivedRoutes(neighbour_ip)

    def getCurrentTime(self):
        return int(self._current_time)

    def getNumberSentRoutingPackets(self):
        return self._numSentRoutingPackets

    def getNumInterfaces(self):
        return len(self._links)

    def isInterfaceUp(self, iface):
        if (iface == self._fib.LOOPBACK):
            return True
        else:
            return self._links[iface].isUp()

    def getInterfaceRevenues(self, iface):
        linkProps = self._links[iface].getProperties()
        if 'revenues' not in linkProps:
            return 0
        return linkProps['revenues']

    def getStateAllInterfaces(self):
        links2state = {}
        for i in self._links:
            links2state[i] = {}
            if self.isInterfaceUp(i):
                links2state[i]['state'] = "up"
            else:
                links2state[i]['state'] = "down"
            links2state[i]['revenues'] = self.getInterfaceRevenues(i)
        return links2state

    def getTracerouteOutput(self):
        return self._ralg.getTracerouteOutput()

    def getSentTrafficPackets(self):
        return self._counter[self._SENT]

    def getReceivedTrafficPackets(self):
        return self._counter[self._RECV]

    def getDroppedTrafficPackets(self):
        return self._counter[self._DROP]

    def getNumExpiredPacketsPerInterface(self):
        return self._originatedIcmpPackets

    def getAllTrafficStats(self):
        s = "Data-plane traffic stats for {}: ".format(self._id)
        s += " sent {}".format(self._counter[self._SENT])
        s += " rcvd {}".format(self._counter[self._RECV])
        s += " fwd {}".format(self._counter[self._FORW])
        s += " drop {}".format(self._counter[self._DROP]) 
        return s
        
    def __str__(self):
        s = "Router {} has {} interfaces".format(self._id,self.getNumInterfaces())
        if self._ralg:
            s += ", routing algorithm {}".format(self._ralg)
        return s

    def _printPacketEvent(self,string):
        print("{}".format(string))

    """
        Dump the forwarding table to stdout
    """
    def dumpForwardingTable(self):
        print("{}".format(self._fib.getDescription(self._id)))

    """
        Dump packet Stats to stdout for both the router and each link.
        s : sent , r : recv , d : drop , f : forw
    """
    def dumpTrafficStats(self,skipPerLink=False):  
        s = self.getAllTrafficStats()
        if not skipPerLink:
            for lId in self._links:
                s += "{}\n".format(self._links[lId].dumpPacketStats());
        print(s, end="")

    """
        Sends a packet, either directly on an interface (if one is specified)
        or looks the interface up in the forwarding table.
        Handles cases of no interface, down interface and expired TTL.
    """
    def send(self, p, out_iface=None, in_iface=None, description=None):
        outlog = []
        if p == None:
            return outlog
        isDataPacket = (p.getType() == PacketTypes.DATA.value)
        outgoing_iface = out_iface
        if outgoing_iface == None:
            ifaces = self._fib.getNextHops(p.getDestination())
            if (len(ifaces) == 0):
                if isDataPacket: outlog.append("Router {}: No outgoing interfaces, DROP packet {}".format(self._id,p))
                self._counter[self._DROP] += 1
                return outlog
            outgoing_iface = self._getOutgoingIface(ifaces,p)
        if outgoing_iface == self._fib.LOOPBACK:
            outlog.append("Router {}: Consumed packet {}".format(self._id,p))
            self._counter[self._RECV] += 1
        elif not self.isInterfaceUp(outgoing_iface):
            if isDataPacket: outlog.append("Router {}: Outgoing interface {} is down, DROP packet {}".format(self._id,outgoing_iface,p))
            self._counter[self._DROP] += 1
        elif p.getTtl() < 1:
            if isDataPacket: outlog.append("Router {}: Expired TTL, DROP packet ".format(self._id,p))
            self._counter[self._DROP] += 1
            newp = self._generateIcmpPacket(p,in_iface)
            outlog += self.send(newp)
        else:
            p.decrementTtl()
            if isDataPacket:
                if len(p.getPayload().getData()) == 0:
                    self._counter[self._SENT] += 1
                    outlog.append("Router {}: Sent NEW packet {} over outgoing interface {}".format(self._id,p,outgoing_iface))
                else:
                    self._counter[self._FORW] += 1
                    outlog.append("Router {}: Forwarded packet {} over outgoing interface {}".format(self._id,p,outgoing_iface))
            if outgoing_iface != self._fib.LOOPBACK or p.getType() != PacketTypes.ICMP.value:
                self._links[outgoing_iface].enqueuePackets(self._id, p)
        return outlog

    """
        Main interface method, called by simulator at each time step.
    """
    def go(self):
       self._ralg.update(self.getStateAllInterfaces(),self.getCurrentTime())
       datalog = self._processPackets()
       self._sendRoutingMessages()
       routinglog = self._finalizeIteration()
       return (datalog,routinglog)

    """
        Loop through all the interfaces checking to see if there is 
        a packet to receive and process it. If it is destined for us
        print a message. If it is a broadcast packet pass it to the 
        routing algorithm to decode, we only broadcast routing packets.
        Otherwise we forward the packet.
    """
    def _processPackets(self):
        outlog = []
        data_pkts = []
        for iface in self._links:
            while True:
                p = self._recv(iface)
                if p is None:
                    break
                if (p.getDestination() == PacketTypes.BROADCAST.value):
                    self._updates_buffer.append((p, iface))
                else:
                    data_pkts.append((p,iface))
        if (self._current_time % self._update_interval) == 0:
            for (buffpkt, buffiface) in self._updates_buffer:
                self._ralg.processRoutingPacket(buffpkt, buffiface)
            self._updates_buffer = []
        for (p,iface) in data_pkts:
            send_outcome = self.send(p, in_iface=iface)
            outlog += send_outcome
        return outlog

    """
        Receives a packet on the interface specified, if no packet is 
        available null is returned.
    """
    def _recv(self, iface):
        return self._links[iface].dequeuePackets(self._id)

    """
        Calls the routing algorithm to generate a routing
        table packet for each interface and sends it on that
        interface.
    """
    def _sendRoutingMessages(self):
        p = None
        for iface in self._links:
            p = self._ralg.generateRoutingPacket(iface)
            if p is not None:
                self.send(p, out_iface=iface)
                self._numSentRoutingPackets += 1

    """
        Selects the actual outgoing interface for the input packet among
        the input list of possible interfaces.
    """
    def _getOutgoingIface(self,ifaces,packet):
        string2hash = "{}{}{}{}{}".format(self._id,packet.getSourcePort(),packet.getDestinationPort(),packet.getSource(),packet.getDestination())
        h = hashlib.new('sha256')
        h.update(string2hash.encode())
        hashnum = int(h.hexdigest(),16) % len(ifaces)
        return ifaces[hashnum]

    """
        Generates an ICMP packet for the expired input packet.
    """   
    def _generateIcmpPacket(self, expired_packet, incoming_iface):
        self._incrementOriginatedIcmps(incoming_iface)
        if incoming_iface in self._ifaces_noicmp:
            return None
        newp = Packet(self.getId(),expired_packet.getSource())
        newp.setType(PacketTypes.ICMP.value)
        newp.setDestinationPort(expired_packet.getSourcePort())
        newp.setSequenceNumber(expired_packet.getSequenceNumber())
        return newp

    def _incrementOriginatedIcmps(self, expired_packet_iface):
        if expired_packet_iface not in self._originatedIcmpPackets:
            self._originatedIcmpPackets[expired_packet_iface] = 0
        self._originatedIcmpPackets[expired_packet_iface] += 1

    def _finalizeIteration(self):
        log = self._ralg.getOutlog()
        self._ralg.finalizeIteration()
        return log

    """
        Method to add a public remote destination 
        (that will be announced to neighbours).
    """
    def addRemoteDestinations(self, subnets, aspath):
        self._ralg.setDefaultPath(subnets, aspath, is_public_route=True)

    """
        Method to add a private remote destination
        (that will never be announced to neighbours).
    """
    def addPrivateDestinations(self, subnets, aspath):
        self._ralg.setDefaultPath(subnets, aspath, is_public_route=False)

