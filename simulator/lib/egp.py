from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket,Payload

class EGP(AbstractRoutingDaemon):

    "Constructor"
    def __init__(self):
        super().__init__()
        self._id = None
        self._sentPerInterface = {}

    "Setter of router-local parameters specified in the configuration and of options to be applied to all routers"
    def setParameters(self, parameters):
        print("[EGP] Received parameters: {}".format(parameters))

    "Setter of the router ID and reference to forwarding table used to forward packets"
    def bindToRouter(self, router_id, router_ip, fwd_table):
        self._id = router_id
        self._ip = router_ip
        print("[EGP] Current forwarding table of {}\n{}".format(router_id,fwd_table.getDescription(router_id)))

    "Refresher that is run at the beginning of every simulation round."
    def update(self, interfaces2state, currentTime):
        pass

    # These two methods will be called at each step processRoutingPacket & generateRoutingPacket

    "Processor of a new packet received by the router and destined to this routing algorithm."
    def processRoutingPacket(self, packet, iface):
        print("[EGP] Router {}: I have just received a routing packet with payload {} on interface {}".format(self._id,packet.getPayload().getData(),iface))

    "Generator of control-plane packet to be sent out of the input interface in the current round. It must return a RoutingPacket object, or None (if no packet needs to be sent)."
    def generateRoutingPacket(self, iface):
        pkt = None
        if iface not in self._sentPerInterface:
            self._sentPerInterface[iface] = True
            pkt = RoutingPacket(self._id)
            payload = Payload()
            payload.addEntry("Hello world, here is router {} speaking".format(self._id))
            pkt.setPayload(payload)
        return None


    def __str__(self):
        s = "EGP object {}".format(hash(self))
        return s

