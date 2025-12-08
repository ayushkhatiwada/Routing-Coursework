from abc import ABC, abstractmethod

"""
    Class documenting the methods that must be implemented by routing daemons.
"""
class AbstractRoutingDaemon(ABC):

    "Constructor"
    def __init__(self):
        self._verbose = False
        self._outlog = []
    
    "Setter of router-local parameters specified in the configuration and of options to be applied to all routers"
    @abstractmethod
    def setParameters(self, parameters):
        pass

    "Setter of the router ID and reference to forwarding table used to forward packets"
    @abstractmethod
    def bindToRouter(self, router_id, router_ip, fwd_table):
        pass

    "Method called at the beginning of every simulation round."
    @abstractmethod
    def update(self, interfaces2state, currentTime):
        pass

    "Processor of a new packet received by the router and destined to this routing algorithm."
    @abstractmethod
    def processRoutingPacket(self, packet, iface):
        pass

    "Generator of control-plane packet to be sent out of the input interface in the current round. It must return a RoutingPacket object, or None (if no packet needs to be sent)."
    @abstractmethod
    def generateRoutingPacket(self, iface):
        pass

    "Method called at the end of every simulation round."
    def finalizeIteration(self):
        self._outlog = []

    def getCurrentRoutes(self):
        return "<method not implemented>"

    def getOutlog(self):
        return self._outlog

    def setVerbose(self,value):
        self._verbose = value

    def _logIfVerbose(self,string=""):
        if self._verbose:
            self._outlog.append(string)

    def _printIfVerbose(self,string=""):
        if self._verbose:
            print(string)

