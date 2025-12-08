import ipaddress, math, itertools
import networkx as nx
from abc import ABC, abstractmethod
from link import LinkUtils

class SimulationChecker(ABC):
    verbose = False

    def setVerbose(self, value):
        self.verbose = value

    def printIfVerbose(self,string=""):
        if self.verbose:
            print(string)

    @abstractmethod
    def check(self, time):
        pass

    @abstractmethod
    def printReport(self):
        pass

class EGPChecker(SimulationChecker):
    def __init__(self, routers_list, links_list, routingGraph, destinations, extrouters2data={}, egprouters2ases={}):
        self.routers = {}                     # dict: router-ID -> router-object
        for r in routers_list:
            self.routers[r.getId()] = r
        self.links = links_list
        self.graph = routingGraph
        self.dests = sorted(list(destinations))
        self.exts2ases = {}                   # dict: EXT-router-ID -> ASN
        self.exts2rels = {}                   # dict: EXT-router-ID -> relation
        for e in extrouters2data:
            self.exts2ases[e] = extrouters2data[e][0]
            self.exts2rels[e] = extrouters2data[e][1]
        self.egps2ases = egprouters2ases      # dict: EGP-router-ID -> ASN
        self.iface2nh = {}
        for (u,v) in self.graph.edges():
            out_iface = self.graph[u][v]['interface']
            self.iface2nh[(u,out_iface)] = v
        self.estimated_convergence = nx.diameter(nx.Graph(self.graph))
        self.time2checks = {}
        self._cost_forwarding = -2
        self._pen_blackhole = -8
        self._pen_lies = -16
        self._set_traffic_model()

    def _set_traffic_model(self):
        for u,v in self.graph.edges():
            if u not in self.dests and 'sourced' not in self.graph.nodes[u]:
                self.graph.nodes[u]['sourced'] = self._cost_forwarding * -1
                if u in self.egps2ases:
                    self.graph.nodes[u]['sourced'] = 0
            if v in self.dests:
                d = ipaddress.ip_network(v)
                generated_traffic = int(100/(d.prefixlen + 1))
                self.graph.nodes[u]['sourced'] = min(100, self.graph.nodes[u]['sourced']+generated_traffic)
                self.graph.nodes[v]['attracted'] = generated_traffic
        for n in self.graph.nodes():
            if 'sourced' in self.graph.nodes[n]: 
                print("Node {} sources {} traffic units".format(n,self.graph.nodes[n]['sourced']))
            else:
                print("Node {} attracts {} traffic units".format(n,self.graph.nodes[n]['attracted']))

    def printReport(self):
        tot_churn = 0
        for r in self.egps2ases:
            tot_churn += self.routers[r].getNumberSentRoutingPackets()
        tot_path_revenues = sum(self.time2checks.values())
        print("Path revenues per time step: {}".format(list(self.time2checks.values())))
        print("Total path revenues: {}".format(tot_path_revenues))
        print("Total number of messages received by EXT routers: {}".format(tot_churn))
        print("Total revenues: {}".format(tot_path_revenues - tot_churn * 2))

    def check(self, time):
        revenues = 0
        if time < self.estimated_convergence:
            self.printIfVerbose("[EGP CHECK] Skipping checks until estimated convergence step, which is time {}".format(self.estimated_convergence))
        else:
            current_graph = self._getUpdatedNetworkGraph()            
            router2dest2aspath = {}         # router -> { dest -> as-path-string }
            log = ""
            for r in self.exts2ases:
                router2dest2aspath[r] = self.routers[r].getCurrentRoutes()
                log += "[EGP CHECK] Routes for router {}: {}\n".format(r,router2dest2aspath[r])
            for r in self.egps2ases:
                log += "[EGP CHECK] Routes for router {}: {}\n".format(r,self.routers[r].getCurrentRoutes())
            self.printIfVerbose(log)
            router2pathsrevenues = {}       # router -> (per-path-revenues, path)
            fined_paths = {}                # (router,dest) -> non-consistent path
            for r in self.exts2ases:
                currbests_r = router2dest2aspath[r]
                for dest in currbests_r:
                    currbest_d = currbests_r[dest]
                    if self._has_loop(currbest_d):
                        fined_paths[(r,dest)] = "route {} received at {} for {} has an AS loop".format(currbest_d,r,dest)
            for dest in self.dests:
                routers2multinhs = self._checkRoutingGraph(dest,router2dest2aspath)
                for r in routers2multinhs:
                    if (r,dest) not in fined_paths:
                        fined_paths[(r,dest)] = "routes from {} have multiple AS next-hops ({}) for {}".format(r,",".join(routers2multinhs[r]),dest)
                fwd_graph = self._buildForwardingGraph(dest,current_graph)
                self._computePerDestRevenues(dest,current_graph,fwd_graph,router2dest2aspath,router2pathsrevenues,fined_paths)   # updates router2pathsrevenues and fined_paths
            (revenues_data, router2dest2advpeerlink, advpeerlink2traffic) = self._computeRevenuesPerSourceDestination(current_graph,router2dest2aspath,router2pathsrevenues,fined_paths)
            revenues = 0
            self.printIfVerbose("[EGP CHECK] forwarding cost: {}".format(self._cost_forwarding))
            for (r,d) in revenues_data:
                (fwd_paths,worst_rev,generated_traffic,aspath_factor) = revenues_data[(r,d)]
                if r in router2dest2advpeerlink and d in router2dest2advpeerlink[r]:
                    (u,v) = router2dest2advpeerlink[r][d]
                    if advpeerlink2traffic[(u,v)][0] <= 0:
                        generated_traffic = 0
                    else:
                        generated_traffic = advpeerlink2traffic[(u,v)][0] / advpeerlink2traffic[(u,v)][1]
                rd_revenues = math.floor(worst_rev * generated_traffic * aspath_factor)
                revenues += rd_revenues
                if (r,d) in fined_paths:
                    self.printIfVerbose("[EGP CHECK] revenues for path '{}' that has path_revenues {}, considering that you get a PENALTY because {}: penalty * traffic = {} * {} = {}".format(fwd_paths[0][1],fwd_paths[0][0],fined_paths[(r,d)],worst_rev,generated_traffic,rd_revenues))
                else:
                    self.printIfVerbose("[EGP CHECK] revenues for path '{}' that has path_revenues {}: (path_revenues + forwarding_costs) * traffic * as_path_length = {} * {} * {} = {}".format(fwd_paths[0][1],fwd_paths[0][0],worst_rev,generated_traffic,aspath_factor,rd_revenues))
            self.printIfVerbose("[EGP CHECK] total revenues at this time: {}".format(revenues))
        self.printIfVerbose()
        self.time2checks[time] = revenues

    def _getUpdatedNetworkGraph(self):
        current_graph = self.graph.copy()
        for u,v in self.graph.edges():
            if "linkid" in self.graph[u][v]:
                lid = current_graph[u][v]["linkid"]
                matching_link_objs = [l for l in self.links if l.getId() == lid]
                if len(matching_link_objs) == 0:
                    continue
                link_obj = matching_link_objs[0]
                if not link_obj.isUp():
                    current_graph[u][v]["failed"] = True
                lprops = link_obj.getProperties()
                if "revenues" in lprops:
                    (money_fwd, money_back, asymmetric_revenues) = LinkUtils.get_link_revenues(lprops)
                    if u in self.egps2ases:
                        current_graph[u][v]["revenue"] = money_fwd
                    elif u in self.exts2ases:
                        current_graph[u][v]["revenue"] = money_back
                    else:
                        raise Exception("ERROR: EGP checker didn't find router {} when trying to update network graph".format(start_router))
                    current_graph[u][v]["advanced_peer"] = asymmetric_revenues
        return current_graph

    def _checkRoutingGraph(self,dest,router2dest2aspath):
        aspath_graph = nx.DiGraph()
        routers_multi_extnhs = set([])
        for r in self.routers:
            if r in self.egps2ases:
                continue
            if dest not in router2dest2aspath[r]:
                continue
            aspath_list = router2dest2aspath[r][dest].split()
            for aslink in zip(aspath_list,aspath_list[1:]):
                aspath_graph.add_edge(aslink[0],aslink[1])
                if aspath_graph.out_degree(aslink[0]) > 1:
                    routers_multi_extnhs.add((r,aslink[0]))
        routers2multinhs = dict()
        for (r,a) in routers_multi_extnhs:
            multihop_edges = ["{}->{}".format(a,n) for n in list(aspath_graph.successors(a))]
            routers2multinhs[r] = multihop_edges
        return routers2multinhs

    def _buildForwardingGraph(self,dest,current_graph):
        fwd_graph = nx.DiGraph()
        for r in self.routers:
            dest_net = ipaddress.ip_network(dest)
            for iface in self.routers[r].getForwardingTable().getEntry(dest_net):
                nh = self.iface2nh[(r,iface)]
                money = 0
                failedlink = False
                if iface == self.routers[r].getForwardingTable().LOOPBACK:
                    nh = dest
                else:
                    money = current_graph[r][nh]['revenue']
                    if 'failed' in current_graph[r][nh]:
                        failedlink = True
                fwd_graph.add_edge(r, nh, revenue = money)
                if failedlink:
                    fwd_graph[r][nh]['failed'] = True
                if nh == dest and self._is_customer(r):
                    fwd_graph.nodes()[nh]['customer-dest'] = r
        return fwd_graph

    def _computePerDestRevenues(self,dest,physical_graph,fwd_graph,router2dest2aspath,router2pathsrevenues,fined_paths):
        for r in self.routers:
            if r not in router2pathsrevenues:
                router2pathsrevenues[r] = dict()
            router2pathsrevenues[r][dest] = []
            try:
                all_paths = list(nx.all_simple_paths(fwd_graph, source=r, target=dest))
                if len(all_paths) == 0: 
                    router2pathsrevenues[r][dest].append((self._pen_blackhole,'{}'.format(r)))
                    fined_paths[(r,dest)] = "no forwarding path from {} to {}".format(r,dest)
                for fwd_path in all_paths:
                    if not self._crosses_egp(fwd_path):
                        continue
                    path_revenues = self._computeRevenuesForForwardingPath(r,dest,fwd_path,fwd_graph,router2dest2aspath,fined_paths)
                    router2pathsrevenues[r][dest].append((path_revenues," -> ".join(fwd_path)))
            except nx.exception.NodeNotFound:
                if self._is_customer(r):
                    router2pathsrevenues[r][dest].append((self._pen_blackhole,'{}'.format(r)))
                    fined_paths[(r,dest)] = "no forwarding path from customer {} to {}".format(r,dest)
                elif dest in fwd_graph and 'customer-dest' in fwd_graph.nodes()[dest]:
                    origin_router = fwd_graph.nodes()[dest]['customer-dest']
                    failed_customer = True
                    for egp_router in self.egps2ases:
                        if (egp_router,origin_router) in physical_graph.edges() and ('failed' not in physical_graph[egp_router][origin_router] or physical_graph[egp_router][origin_router]['failed'] != True):
                            failed_customer = False
                    if not failed_customer:
                        aspath_string = router2dest2aspath[origin_router][dest]
                        unique_ases_in_path = self._remove_consecutive_duplicates(aspath_string.split())
                        if len(unique_ases_in_path) == 1:
                            router2pathsrevenues[r][dest].append((self._pen_blackhole,'{}'.format(r)))
                            fined_paths[(r,dest)] = "no forwarding path from {} to customer destination {}".format(r,dest)

    def _computeRevenuesForForwardingPath(self,start_router,dest,fwd_path,fwd_graph,router2dest2aspath,fined_paths):
        if fwd_path[0] in self.egps2ases:
            return 0
        if (fwd_path[0],fwd_path[-1]) in fined_paths:
            return self._pen_lies
        path_revenues = 0
        curr_aspath = "-1"            # by default, we assume no path from the current router to the current destination
        u_aspath = "-1"               # by default, we assume no path from any intermediate router as well
        if start_router in router2dest2aspath and dest in router2dest2aspath[start_router] and router2dest2aspath[start_router][dest] != None:
            curr_aspath = router2dest2aspath[start_router][dest].split()
        for (u,v) in zip(fwd_path,fwd_path[1:]):
            path_revenues += int(fwd_graph[u][v]['revenue'])
            if 'failed' in fwd_graph[u][v] and fwd_graph[u][v]['failed'] == True:
                fined_paths[(start_router,dest)] = "forwarding path from {} crosses failed link ({},{})".format(start_router,u,v)
                path_revenues = self._pen_lies
                break
            elif u in self.egps2ases:
                pass
            else:
                if u in router2dest2aspath and dest in router2dest2aspath[u] and router2dest2aspath[u][dest] != None:
                    u_aspath = router2dest2aspath[u][dest].split()
                if curr_aspath[:len(u_aspath)] != u_aspath:
                    fined_paths[(start_router,dest)] = "AS path ({}) from {} is NOT consistent with actual AS path ({}) from {}".format(router2dest2aspath[start_router][dest],start_router," ".join(u_aspath),u)
                    path_revenues = self._pen_lies
                    break
            if self._getASN(u) != self._getASN(v):
                curr_aspath = curr_aspath[1:]
        return path_revenues

    def _computeRevenuesPerSourceDestination(self,current_graph,router2dest2aspath,router2pathsrevenues,fined_paths):            
        revenues_data = {}              # (router,dest) -> <fwd_paths,fwd_revenues,generated_traffic,aspath_factor>
        router2dest2advpeerlink = {}    # router -> dest -> directed_link_with_advanced_peer (if any)
        advpeerlink2traffic = {}        # directed_link_with_advanced_peer -> (traffic_balance,num_paths)
        for r in router2pathsrevenues:
            router2dest2advpeerlink[r] = {}
            if int(current_graph.nodes[r]['sourced']) == 0:
                continue
            dest2aspath = router2dest2aspath[r]
            for d in router2pathsrevenues[r]:
                sorted_paths = sorted(router2pathsrevenues[r][d], key = lambda x: x[0])
                if len(sorted_paths) == 0:
                    continue
                (worst_rev, worst_path) = sorted_paths[0]               # all the traffic from r to d is allocated to the worst path
                if (r,d) not in fined_paths:
                    worst_rev += self._cost_forwarding
                generated_traffic = min(current_graph.nodes[r]['sourced'],current_graph.nodes[d]['attracted'])   # for each network, amount of incoming traffic is often approximately symmetric to the amount of outgoing traffic
                worst_path_hops = worst_path.split(' -> ')
                for (u,v) in zip(worst_path_hops,worst_path_hops[1:]):
                    if 'advanced_peer' in current_graph[u][v] and current_graph[u][v]['advanced_peer'] == True:
                        router2dest2advpeerlink[r][d] = (u,v)
                        if (u,v) not in advpeerlink2traffic:
                            advpeerlink2traffic[(u,v)] = [0,0]
                        if (v,u) not in advpeerlink2traffic:
                            advpeerlink2traffic[(v,u)] = [0,0]
                        advpeerlink2traffic[(u,v)][0] += generated_traffic
                        advpeerlink2traffic[(u,v)][1] += 1
                        advpeerlink2traffic[(v,u)][0] -= generated_traffic
                aspath_factor = 1
                if d in dest2aspath and (r,d) not in fined_paths:
                    num_ases_in_path = len(set(self._remove_consecutive_duplicates(dest2aspath[d].split())))
                    aspath_factor = 10/num_ases_in_path         # longer AS paths attract less traffic
                revenues_data[(r,d)] = (sorted_paths,worst_rev,generated_traffic,aspath_factor)
        if len(advpeerlink2traffic) > 0:
            self.printIfVerbose("[EGP CHECK] processing links with advanced peers: only links with positive traffic balance contribute to revenues; for each of these links, exceeding traffic is spread equally across paths crossing the link")
            for link in advpeerlink2traffic:
                self.printIfVerbose("[EGP CHECK] advanced-peer link {} has a traffic balance of {} units, across {} paths crossing the link".format(link,advpeerlink2traffic[link][0],advpeerlink2traffic[link][1]))
            self.printIfVerbose()
        return (revenues_data, router2dest2advpeerlink, advpeerlink2traffic)

    def _getASN(self,node):
        if node in self.exts2ases:
            return self.exts2ases[node]
        elif node in self.egps2ases:
            return self.egps2ases[node]
        return None

    def _is_customer(self,router):
        if router not in self.exts2rels:
            return False
        return self.exts2rels[router] == "customer"

    def _crosses_egp(self,fwd_path):
        check = False
        for node in fwd_path:
            if node in self.egps2ases:
                return True
        return check

    def _has_loop(self,aspath_string):
        cleaned_aspath = self._remove_consecutive_duplicates(aspath_string.split())
        cleaned_aspath_list = cleaned_aspath.split()
        return len(set(cleaned_aspath_list)) < len(cleaned_aspath_list)

    def _remove_consecutive_duplicates(self,s):
        return ''.join(char for char, _ in itertools.groupby(s))

