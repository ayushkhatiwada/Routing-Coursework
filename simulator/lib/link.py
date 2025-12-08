from packet import PacketTypes

"""
  The Link class that represents a link between two routers.
  It contains four packet queues, and in bound and out bound queue for
  each end. It also simulates the moving of packets from one end to
  the other end.
"""
class Link:
    _SENT = 0
    _RECV = 1
    _DROP = 2

    """
      Constructor that takes router id, interface id, and interface weight.
      for both ends of the link.
      - r0 router 0's id
      - i0 router 0's interface
      - r1 router 1's id
      - i1 router 1's interface
    """
    def __init__(self, r0, i0, r1, i1, linkId, prop):
        self._id = linkId
        self._router = [r0, r1]
        self._iface = [i0, i1]
        self._properties = prop
        self._up = True

        self._in = [None, None]
        self._out = [None, None]
        self._in[0] = []
        self._out[0] = []
        self._in[1] = []
        self._out[1] = []

        self._counter = [[None, None], [None, None]]
        self._counter[0][self._SENT] = 0
        self._counter[0][self._RECV] = 0
        self._counter[1][self._SENT] = 0
        self._counter[1][self._RECV] = 0

    """
      Return the link ID.
    """
    def getId(self):
        return self._id

    """
      Get the router attached to a particular end of the link, 0 specifies
      one end and 1 the other.
    """
    def getRouter(self, id):
        if id == 0:
            return self._router[0]
        else:
            return self._router[1]

    """
      Get the interface attached to a particular end of the link, 0 specifies
      one end and 1 the other.
    """
    def getInterface(self, id):
        if id == 0:
            return self._iface[0]
        else:
            return self._iface[1]

    """
      Is the link up or down.
    """
    def isUp(self):
        return self._up

    """
      Sets the link status.
    """
    def setState(self, s):
        self._up = s

    """
      Updates the link properties, overriding values for properties which already had values.
    """
    def updateProperties(self, newprops):
        for prop in newprops:
            self._properties[prop] = newprops[prop]

    """
      Returns all the link properties.
    """
    def getProperties(self):
        return self._properties

    """
      If the link is up moves the packets from the out queue of one end
      to the in queue of the other end.
    """
    def movePackets(self):
        p = None
        payload = None
        if self.isUp():
            while len(self._out[0]) > 0:
                p = self._out[0][0]
                if p.getType() == PacketTypes.DATA.value:
                    payload = p.getPayload()
                    payload.addEntry("{}->{}".format(self._router[0], self._router[1]))
                    p.setPayload(payload)
                self._in[1].append(p)
                self._out[0].remove(p)
            while len(self._out[1]) > 0:
                p = self._out[1][0]
                if p.getType() == PacketTypes.DATA.value:
                    payload = p.getPayload()
                    payload.addEntry("{}->{}".format(self._router[1], self._router[0]))
                    p.setPayload(payload)
                self._in[0].append(p)
                self._out[1].remove(p)

    """
      Places the Packet p, in the out bound queue for the
      router specified by router id.
      - routerid the router whose out bound queue to place the packet in.
      - p the packet being sent.
    """
    def enqueuePackets(self, routerid, p):
        if routerid == self._router[0]:
            self._out[0].append(p)
            self._counter[0][self._SENT] += 1
        else:
            self._out[1].append(p)
            self._counter[1][self._SENT] += 1

    """
      Retreives a Packet, from the inbound queue for the
      router specified by router id. If no packet is present returns null.
      @param routerid the router whose in bound queue to remove the packet from.
      @return the packet being retrieved.
    """
    def dequeuePackets(self, routerid):
        p = None
        if routerid == self._router[0]:
            if len(self._in[0]) > 0:
                p = self._in[0].pop(0)
                self._counter[0][self._RECV] += 1
                return p
        else:
            if len(self._in[1]) > 0:
                p = self._in[1].pop(0)
                self._counter[1][self._RECV] += 1
                return p
        return None

    """
      Returns the queue length for a particular direction and end of
      the link.
      @param iface 0, 1 specifies the end.
      @param inbound specifies whether in it the in or out
      queue.
      @return the length of the queue
    """
    def queueLength(self, iface, inbound):
        if inbound:
            return len(self._in[iface])
        else:
            return len(self._out[iface])

    def _getDescription(self):
        s = "({0}.{1} <--> {2}.{3})".format(self._router[0], self._iface[0], self._router[1], self._iface[1])
        return s

    """
      Generic to string method
    """
    def __str__(self):
        return self._getDescription()

    """
      Returns the packet counters for this link.
    """
    def dumpPacketStats(self):
        s = self._getDescription()
        s += " sent {0} rcvd {1}".format(self._counter[1][self._SENT], self._counter[1][self._RECV])
        return s

class LinkUtils:
    @staticmethod
    def get_link_revenues(link_properties):
        money_fwd = 0
        money_back = 0
        asymmetric_revenues = False
        if 'revenues' in link_properties:
            money_fwd = link_properties['revenues']
            money_back = link_properties['revenues']
            if ';' in link_properties['revenues']:
                money_fwd = link_properties['revenues'].split(';')[0].strip()
                money_back = link_properties['revenues'].split(';')[1].strip()
                asymmetric_revenues = True
        return (money_fwd, money_back, asymmetric_revenues)
