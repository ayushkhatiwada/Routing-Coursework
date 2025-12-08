import json
import networkx as nx

from router import Router, ForwardingTable
from link import Link, LinkUtils
from event import Event
from checkers import EGPChecker
from routingAbstractions import AbstractRoutingDaemon
from ext import EXT
from egp import EGP

"""
    Factory for routing daemons that can currently be used within the simulator
"""
class RoutingDaemonsFactory:
    def __init__(self):
        self._availableDaemons = {"ext": EXT(), "EGP": EGP()}

    def getRoutingDaemon(self, daemonId):
        daemon = self._availableDaemons[daemonId]
        assert issubclass(daemon.__class__, AbstractRoutingDaemon)
        return daemon

class ConfigParser:
    def __init__(self, filename, s):
        self._routers = []
        self._events = []
        self._links = []
        self._tracesources = []
        self._sim = s
        print(f"Reading file {filename}")
        with open(filename, 'rt') as f:
            configData = json.load(f)
            self.process(configData)
        self._sim.add_routers(self._routers)
        self._sim.add_links(self._links)
        self._sim.add_events(self._events)

    def process(self, configData):
        routingGraph = nx.DiGraph()
        iface_weights = {}
        internal_dests = []
        external_dests = set([])
        topochanges_times = []
        ext_dict = {}
        egp_dict = {}

        if 'routers' in configData:
            for router in configData['routers']:
                r = Router(
                    rId=router['rId'],
                    rIP=router['ipAddress']
                )
                if 'updateInterval' in router and router['updateInterval'] > 1:
                    r.setUpdateInterval(router['updateInterval'])
                if 'verbose' in router:
                    r.setVerbose(router['verbose'] == 'True')
                proto = router['routingProtocol']
                ra = RoutingDaemonsFactory().getRoutingDaemon(proto)
                params = {}
                if 'routingProtocols' in configData and proto in configData['routingProtocols']:
                    if 'all-routers' in configData['routingProtocols'][proto]:
                        params.update(configData['routingProtocols'][proto]['all-routers'])
                    if router['rId'] in configData['routingProtocols'][proto]:
                        params.update(configData['routingProtocols'][proto][router['rId']])
                ra.setParameters(params)
                r.setRoutingDaemon(ra)
                self._routers.append(r)
                if proto == "IGP":
                    routingGraph.add_edge(router['rId'], router['ipAddress'], weight=1, interface=ForwardingTable().LOOPBACK)
                    internal_dests.append(router['ipAddress'])
                    if 'weights' in params:
                        for linkid in params['weights']:
                            iface_weights[linkid] = params['weights'][linkid]
                elif proto == "ext":
                    ext_dict[router['rId']] = (configData['routingProtocols'][proto][router['rId']]["AS-ID"],configData['routingProtocols'][proto][router['rId']]["relation"])
                elif proto == "EGP":
                    egp_dict[router['rId']] = configData['routingProtocols'][proto][router['rId']]["AS-ID"]

        if 'links' in configData:
            for link in configData['links']:
                r0, i0 = link['interfaces'][0].split('-')
                r1, i1 = link['interfaces'][1].split('-')
                conf_props = {}
                if 'properties' in link:
                    conf_props = link['properties']
                l = Link(
                    r0=r0,
                    i0=link['interfaces'][0],
                    r1=r1,
                    i1=link['interfaces'][1],
                    linkId=link['id'],
                    prop=conf_props,
                )
                if link['status'] == "up":
                    l.setState(True)
                elif link['status'] == "down":
                    l.setState(False)
                else:
                    print(f"Unknown link state {link['status']}")
                self._links.append(l)
                (money_fwd, money_back, asymmetric_revenues) = LinkUtils.get_link_revenues(link['properties'])
                w1 = 1
                if link['interfaces'][0] in iface_weights:
                    w1 = iface_weights[link['interfaces'][0]]
                routingGraph.add_edge(r0, r1, linkid=link['id'], interface=link['interfaces'][0], weight=w1, revenue=money_fwd, advanced_peer=asymmetric_revenues)
                w2 = 1
                if link['interfaces'][1] in iface_weights:
                    w2 = iface_weights[link['interfaces'][1]]
                routingGraph.add_edge(r1, r0, linkid=link['id'], interface=link['interfaces'][1], weight=w2, revenue=money_back, advanced_peer=asymmetric_revenues)

        for event in configData['events']:
            if event['type'] == "send":
                args = [event['src'], event['dest']]
                if 'ttl' in event:
                    args += [event['ttl']]
                e = Event(event['type'], int(event['time']), args)
                self._events.append(e)

            elif event['type'] == "uplink" or event['type'] == "downlink":
                e = Event(event['type'], int(event['time']), event['link'])
                self._events.append(e)
                if int(event['time']) not in topochanges_times:
                    topochanges_times.append(int(event['time']))

            elif event['type'] == "newlinkproperties":
                args = [event['link'],event['properties']]
                e = Event(event['type'], int(event['time']), args)
                self._events.append(e)

            elif event['type'] == "stop":
                self._sim.set_stop_time(int(event['time']))

            elif event['type'] == "dumpfib":
                args = []
                args.append(event['args'])
                e = Event(event['type'], int(event['time']), args)
                self._events.append(e)

            elif event['type'] == "dumpstats":
                args = []
                args.append(event['args'])
                e = Event(event['type'], int(event['time']), args)
                self._events.append(e)

            elif event['type'] == "advert":
                args = [event['router'], event['prefix'], event['AS-path']]
                e = Event(event['type'], int(event['time']), args)
                self._events.append(e)
                for p in event['prefix'].split():
                    routingGraph.add_edge(event['router'], p, weight=1, interface=ForwardingTable.LOOPBACK)
                    external_dests.add(p)

            elif event['type'] == "addprivatepath":
                args = [event['router'], event['prefix'], event['AS-path']]
                e = Event(event['type'], int(event['time']), args)
                self._events.append(e)
                for p in event['prefix'].split():
                    routingGraph.add_edge(event['router'], p, weight=1, interface=ForwardingTable.LOOPBACK)
                    external_dests.add(p)

            else:
                print(f"Unrecognized event: {event}")
                exit(1)

        egpchecker = EGPChecker(self._routers, self._links, routingGraph, list(external_dests), extrouters2data=ext_dict, egprouters2ases=egp_dict)
        simcheckers = [egpchecker]
        self._sim.set_checkers(simcheckers)

