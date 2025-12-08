from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket,Payload

''' 
  External neighbour of EGP speakers.
  Implements minimalistic functionalities based on simplifying assumptions, including: (i) only one EGP neighbour, and (ii) always prefer routes offered by the EGP neighbour over any other.
'''
class EXT(AbstractRoutingDaemon):

    "Constructor"
    def __init__(self):
        super().__init__()
        self._id = None
        self._ip = None
        self._asn = None
        self._last_interface_state = None
        self._default_routes = {}               # dest -> (aspath, public|private)
        self._current_routes = {}               # dest -> current aspath
        self._received_routes = {}              # neighbour -> { dest -> selected aspath }
        self._dests_offered_routes = set({})    # set of destinations for which we offer a path externally
        self._dests_with_new_route = set([])    # set of destinations for which we have a new path in this iteration

    "Setter of router-local parameters specified in the configuration and of options to be applied to all routers"
    def setParameters(self, parameters):
        self._asn = parameters['AS-ID']

    "Setter of the router ID and reference to forwarding table used to forward packets"
    def bindToRouter(self, router_id, router_ip, fwd_table):
        self._id = router_id
        self._ip = router_ip
        self._fib = fwd_table

    def __str__(self):
        return "EXT object {}".format(hash(self))

    "Refresher that is run at the beginning of every simulation round."
    def update(self, interfaces2state, currentTime):
        if len(interfaces2state) > 1:
            raise Exception("[EXT] Cannot be configured with more than one physical interface")
        i = next(iter(interfaces2state))
        if self._last_interface_state != None and interfaces2state[i]['state'] != self._last_interface_state:
            if interfaces2state[i]['state'] == 'down':
                for d in self._current_routes:
                    self._fib.removeEntry(d)
                self._received_routes = {}
                self._current_routes = {}
                for d in self._default_routes:
                    self._current_routes[d] = self._default_routes[d][0]
                    self._fib.setEntryLocal(d)
            else:
                for known_dest in self._default_routes.keys():
                    if self._default_routes[known_dest][1] == 'public':
                        self._dests_with_new_route.add(known_dest)
        self._last_interface_state = interfaces2state[i]['state']

    "Processor of a new packet received by the router and destined to this routing algorithm."
    def processRoutingPacket(self, packet, iface):
        self._logIfVerbose("[EXT] Router {}: I have just received a routing packet with payload {} on interface {}".format(self._id,packet.getPayload().getData(),iface))
        speaker = None
        processed_dests = set([])
        for data in packet.getPayload().getData():
            if data.startswith('speaker'):
                speaker = data.split()[1]
            elif data.startswith('EGP-update'):
                dest = data.split()[2]
                if dest in processed_dests:
                    raise Exception("[EXT] multiple updates or withdrawals in the same packet for the same destination {}".format(dest))
                processed_dests.add(dest)
                aspath = " ".join(data.split()[4:])
                if speaker not in self._received_routes:
                    self._received_routes[speaker] = dict()
                self._received_routes[speaker][dest] = "{} {}".format(self.getASN(),aspath)
                has_private_route = (dest in self._default_routes and self._default_routes[dest][1] == 'private')
                if not self._is_destination_local(dest) and not has_private_route:
                    if (dest in self._current_routes) and (dest in self._default_routes) and (self._current_routes[dest] == self._default_routes[dest][0]):
                        self._dests_with_new_route.add(dest)
                    self._current_routes[dest] = "{} {}".format(self.getASN(),aspath)
                    self._fib.setEntry(dest,[iface])
                else:
                    self._fib.setEntry(dest,[self._fib.LOOPBACK])
                    self._current_routes[dest] = self._default_routes[dest][0]
            elif data.startswith("EGP-withdrawal"):
                dest = data.split()[2]
                if speaker not in self._received_routes:
                    continue
                if dest in self._received_routes[speaker]:
                    if dest in processed_dests:
                        raise Exception("[EXT] multiple updates or withdrawals in the same packet for the same destination {}".format(dest))
                    processed_dests.add(dest)
                    if self._received_routes[speaker][dest] == self._current_routes[dest]:
                        if dest in self._default_routes:
                            self._current_routes[dest] = self._default_routes[dest][0]
                            self._fib.setEntryLocal(dest)
                            self._dests_with_new_route.add(dest)
                        else:
                            self._current_routes.pop(dest)
                            self._fib.removeEntry(dest)
                    self._received_routes[speaker].pop(dest)
                self._logIfVerbose("[EXT] Router {}: routes recorded for EGP neighbour after processing withdrawal {} are {}".format(self._id,data,self._received_routes[speaker]))
            else:
                raise Exception("[EXT] Router {} has received malformed EGP packet {}".format(self._id,packet))

    def _is_destination_local(self, dest):
        if dest not in self._default_routes:
            return False
        (aspath,_) = self._default_routes[dest]
        all_ases = set(aspath.split())
        if len(all_ases) > 1:
            return False
        return True

    "Generator of control-plane packet to be sent out of the input interface in the current round. It must return a RoutingPacket object, or None (if no packet needs to be sent)."
    def generateRoutingPacket(self, iface):
        to_announce = []
        to_withdraw = []
        for d in sorted(self._dests_with_new_route):
            (default_path, visibility) = self._default_routes[d]
            if self._current_routes[d] == default_path and visibility == "public":
                self._logIfVerbose("[EXT] Router {} to announce for destination {}: current route {}; default route {}".format(self._id,d,self._current_routes[d],default_path))
                to_announce.append(d)
                self._dests_offered_routes.add(d)
            elif self._current_routes[d] == default_path and visibility == "private" and d in self._dests_offered_routes:
                self._logIfVerbose("[EXT] Router {} to withdraw for destination {}: current private route {}; default route {}".format(self._id,d,self._current_routes[d],default_path))
                to_withdraw.append(d)
                if d in self._dests_offered_routes:
                    self._dests_offered_routes.remove(d)
            elif self._current_routes[d] != default_path and default_path != None and d in self._dests_offered_routes:
                self._logIfVerbose("[EXT] Router {} to withdraw for destination {}: current neighbour-offered route {}; default route {}".format(self._id,d,self._current_routes[d],default_path))
                to_withdraw.append(d)
                if d in self._dests_offered_routes:
                    self._dests_offered_routes.remove(d)
        self._dests_with_new_route = set([])
        pkt = self._build_packet(to_announce,to_withdraw)
        if pkt:
            self._logIfVerbose("[EXT] Router {} sending message on {}: {}".format(self._id,iface,pkt.getPayload()))
        return pkt

    def _build_packet(self,dests_to_announce,dests_to_withdraw):
        if len(dests_to_announce) + len(dests_to_withdraw) == 0:
            return None
        pkt = RoutingPacket(self._ip)
        payload = Payload()
        payload.addEntry("speaker: {}".format(self._ip))
        for d in dests_to_announce:
            payload.addEntry("EGP-update prefix: {} AS-path: {}".format(d,self._current_routes[d]))
        for d in dests_to_withdraw:
            payload.addEntry("EGP-withdrawal prefix: {}".format(d))
        pkt.setPayload(payload)
        return pkt

    " Sets default paths to destinations "
    def setDefaultPath(self, subnets, aspath, is_public_route):
        visibility = "private"
        if is_public_route:
            visibility = "public"
        for subnet in subnets.split():
            self._default_routes[subnet] = (aspath,visibility)
            self._current_routes[subnet] = aspath
            self._fib.setEntryLocal(subnet)
            self._dests_with_new_route.add(subnet)

    " Returns the local AS number "
    def getASN(self):
        return self._asn

    " Returns a dictionary { destination -> aspath } "
    def getReceivedRoutes(self, neighbour_ip):
        return self._received_routes[neighbour_ip]

    " Returns a dictionary { destination -> aspath } "
    def getCurrentRoutes(self):
        return self._current_routes

