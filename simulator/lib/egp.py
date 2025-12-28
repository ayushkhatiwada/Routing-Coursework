from routingAbstractions import AbstractRoutingDaemon
from packet import RoutingPacket, Payload


class EGP(AbstractRoutingDaemon):
    """
    Simplified BGP implementation for Stage 1 coursework.
    Handles route exchange with EXT neighbors using customer-provider-peer policy model.
    """

    def __init__(self):
        super().__init__()
        self._id = None                     # Router ID
        self._ip = None                     # Router IP address
        self._fib = None                    # ForwardingTable reference
        self._asn = None                    # Local AS number
        self._neighbours = {}               # iface -> neighbour IP
        self._relations = {}                # iface -> relation (customer/peer/provider)
        self._ip_to_iface = {}              # neighbour IP -> iface
        
        # Route storage
        self._received_routes = {}          # dest -> { iface -> as_path }
        self._best_routes = {}              # dest -> (iface, as_path)
        
        # Advertisement tracking
        self._advertised = {}               # iface -> { dest -> as_path }
        self._routes_changed = set()        # destinations with route changes this round
        
        # Link state tracking
        self._link_states = {}              # iface -> 'up' or 'down'
        self._first_update = True           # Flag for first update call

    def setParameters(self, parameters):
        """Store AS-ID and neighbor/relation info from configuration."""
        self._asn = parameters.get('AS-ID', 'UNKNOWN')
        
        if 'neighbours' in parameters:
            self._neighbours = dict(parameters['neighbours'])
            # Build reverse mapping
            for iface, ip in self._neighbours.items():
                self._ip_to_iface[ip] = iface
        
        if 'relations' in parameters:
            self._relations = dict(parameters['relations'])

    def bindToRouter(self, router_id, router_ip, fwd_table):
        """Store router ID, IP, and forwarding table reference."""
        self._id = router_id
        self._ip = router_ip
        self._fib = fwd_table

    def update(self, interfaces2state, currentTime):
        """
        Handle link state changes at the beginning of each simulation round.
        """
        for iface in interfaces2state:
            new_state = interfaces2state[iface]['state']
            old_state = self._link_states.get(iface, None)
            
            if old_state is None:
                # First time seeing this interface
                self._link_states[iface] = new_state
                continue
            
            if old_state != new_state:
                self._link_states[iface] = new_state
                
                if new_state == 'down':
                    # Link went down - remove all routes via this interface
                    self._handle_link_down(iface)
                else:
                    # Link came up - mark for re-announcement
                    self._handle_link_up(iface)
        
        self._first_update = False

    def _handle_link_down(self, iface):
        """Handle link failure - remove routes received via this interface."""
        affected_dests = set()
        
        # Remove all routes received on this interface
        for dest in list(self._received_routes.keys()):
            if iface in self._received_routes[dest]:
                del self._received_routes[dest][iface]
                affected_dests.add(dest)
                if not self._received_routes[dest]:
                    del self._received_routes[dest]
        
        # Re-select best routes for affected destinations
        for dest in affected_dests:
            self._select_best_route(dest)
            self._routes_changed.add(dest)

    def _handle_link_up(self, iface):
        """Handle link coming up - mark routes for re-advertisement."""
        # Clear advertised state for this interface to trigger re-announcement
        if iface in self._advertised:
            self._advertised[iface] = {}
        
        # Mark all destinations as changed to trigger advertisements
        for dest in self._best_routes:
            self._routes_changed.add(dest)

    def processRoutingPacket(self, packet, iface):
        """
        Process routing packets received from EXT neighbors.
        Parse EGP-update and EGP-withdrawal messages.
        """
        payload = packet.getPayload().getData()
        speaker = None
        processed_dests = set()
        
        for data in payload:
            if data.startswith('speaker'):
                # Extract speaker IP: "speaker: <IP>" or "speaker <IP>"
                parts = data.split()
                if len(parts) >= 2:
                    speaker = parts[1].rstrip(':')
                    if speaker.endswith(':'):
                        speaker = speaker[:-1]
                    # Handle "speaker: IP" format
                    if ':' in data and len(parts) >= 2:
                        speaker = data.split(':')[1].strip()
            
            elif data.startswith('EGP-update'):
                # Format: "EGP-update prefix: <prefix> AS-path: <as_path>"
                dest = self._parse_prefix(data)
                as_path = self._parse_aspath(data)
                
                if dest and as_path is not None:
                    if dest in processed_dests:
                        # Skip duplicate updates for same dest in same packet
                        continue
                    processed_dests.add(dest)
                    
                    # Prepend our AS to the path
                    new_path = "{} {}".format(self._asn, as_path)
                    
                    # Store the route
                    if dest not in self._received_routes:
                        self._received_routes[dest] = {}
                    self._received_routes[dest][iface] = new_path
                    
                    # Re-select best route for this destination
                    self._select_best_route(dest)
                    self._routes_changed.add(dest)
            
            elif data.startswith('EGP-withdrawal'):
                # Format: "EGP-withdrawal prefix: <prefix>"
                dest = self._parse_prefix(data)
                
                if dest:
                    if dest in processed_dests:
                        continue
                    processed_dests.add(dest)
                    
                    # Remove the route from this interface
                    if dest in self._received_routes and iface in self._received_routes[dest]:
                        del self._received_routes[dest][iface]
                        if not self._received_routes[dest]:
                            del self._received_routes[dest]
                    
                    # Re-select best route for this destination
                    self._select_best_route(dest)
                    self._routes_changed.add(dest)

    def _parse_prefix(self, data):
        """Extract prefix from EGP-update or EGP-withdrawal message."""
        # Format: "EGP-update prefix: <prefix> AS-path: <path>"
        # or "EGP-withdrawal prefix: <prefix>"
        try:
            if 'prefix:' in data:
                parts = data.split('prefix:')
                if len(parts) >= 2:
                    prefix_part = parts[1].strip()
                    # Take first word (prefix) before AS-path
                    prefix = prefix_part.split()[0]
                    return prefix
        except:
            pass
        return None

    def _parse_aspath(self, data):
        """Extract AS-path from EGP-update message."""
        # Format: "EGP-update prefix: <prefix> AS-path: <path>"
        try:
            if 'AS-path:' in data:
                parts = data.split('AS-path:')
                if len(parts) >= 2:
                    return parts[1].strip()
        except:
            pass
        return None

    def _select_best_route(self, dest):
        """
        Select best route for a destination based on:
        1. Relation preference: customer > peer > provider
        2. Interface name for stability (lexicographically smaller)
        3. Switch to shorter path only if difference is significant (3+ hops)
        """
        if dest not in self._received_routes or not self._received_routes[dest]:
            # No routes available - remove from best routes and FIB
            if dest in self._best_routes:
                del self._best_routes[dest]
            self._fib.removeEntry(dest)
            return
        
        candidates = []
        
        for iface, as_path in self._received_routes[dest].items():
            # Skip routes that contain our AS (loop detection)
            if self._has_loop(as_path):
                continue
            
            # Skip routes via down interfaces
            if self._link_states.get(iface, 'up') == 'down':
                continue
            
            relation = self._relations.get(iface, 'provider')
            relation_priority = self._get_relation_priority(relation)
            path_length = len(as_path.split())
            
            candidates.append((relation_priority, iface, path_length, as_path))
        
        if not candidates:
            # No valid routes
            if dest in self._best_routes:
                del self._best_routes[dest]
            self._fib.removeEntry(dest)
            return
        
        # Sort by relation priority (higher first), then interface name
        candidates.sort(key=lambda x: (-x[0], x[1]))
        
        # Get the best by relation and interface (most stable choice)
        best = candidates[0]
        best_iface = best[1]
        best_path_length = best[2]
        best_path = best[3]
        best_relation = best[0]
        
        # Check if there's a significantly shorter path (3+ hops shorter)
        # from same relation type that we should switch to
        for candidate in candidates[1:]:
            if candidate[0] != best_relation:
                break  # Different relation type, stop checking
            if best_path_length - candidate[2] >= 3:
                # This candidate has significantly shorter path, use it
                best_iface = candidate[1]
                best_path = candidate[3]
                break  # Take the first qualifying interface
        
        self._best_routes[dest] = (best_iface, best_path)
        self._fib.setEntry(dest, [best_iface])

    def _has_loop(self, as_path):
        """Check if AS-path contains our AS (loop detection)."""
        ases = as_path.split()
        # Check if our AS appears more than once (at the beginning)
        # Our AS is at position 0 (we prepended it), so look for duplicates
        for i, asn in enumerate(ases):
            if i > 0 and asn == self._asn:
                return True
        return False

    def _get_relation_priority(self, relation):
        """Get priority for relation type. Higher is better."""
        if relation == 'customer':
            return 3
        elif relation == 'peer':
            return 2
        elif relation == 'provider':
            return 1
        return 0

    def generateRoutingPacket(self, iface):
        """
        Generate routing packet for this interface based on export policy:
        - Routes from customers -> advertise to all
        - Routes from peers/providers -> advertise only to customers
        """
        if iface not in self._neighbours:
            return None
        
        # Check if link is up
        if self._link_states.get(iface, 'up') == 'down':
            return None
        
        neighbour_relation = self._relations.get(iface, 'provider')
        to_announce = []
        to_withdraw = []
        
        # Initialize advertised tracking for this interface
        if iface not in self._advertised:
            self._advertised[iface] = {}
        
        # Determine what we should be advertising
        should_advertise = {}
        
        for dest, (route_iface, as_path) in self._best_routes.items():
            # Don't advertise routes back to the interface we learned them from
            if route_iface == iface:
                continue
            
            route_relation = self._relations.get(route_iface, 'provider')
            
            # Export policy check
            if self._should_export(route_relation, neighbour_relation):
                should_advertise[dest] = as_path
        
        # Find new announcements
        for dest, as_path in should_advertise.items():
            if dest not in self._advertised[iface]:
                # New route
                to_announce.append((dest, as_path))
            elif self._advertised[iface][dest] != as_path:
                # Route changed
                to_announce.append((dest, as_path))
        
        # Find withdrawals
        for dest in list(self._advertised[iface].keys()):
            if dest not in should_advertise:
                to_withdraw.append(dest)
        
        # Build packet if there's something to send
        if not to_announce and not to_withdraw:
            return None
        
        pkt = RoutingPacket(self._ip)
        payload = Payload()
        payload.addEntry("speaker: {}".format(self._ip))
        
        for (dest, as_path) in to_announce:
            payload.addEntry("EGP-update prefix: {} AS-path: {}".format(dest, as_path))
            self._advertised[iface][dest] = as_path
        
        for dest in to_withdraw:
            payload.addEntry("EGP-withdrawal prefix: {}".format(dest))
            if dest in self._advertised[iface]:
                del self._advertised[iface][dest]
        
        pkt.setPayload(payload)
        return pkt

    def _should_export(self, route_relation, neighbour_relation):
        """
        Determine if a route should be exported based on customer-provider-peer policy.
        - Routes from customers -> export to all
        - Routes from peers/providers -> export only to customers
        """
        if route_relation == 'customer':
            # Customer routes go to everyone
            return True
        else:
            # Peer/provider routes only go to customers
            return neighbour_relation == 'customer'

    def getCurrentRoutes(self):
        """Return current best routes for the checker."""
        result = {}
        for dest, (iface, as_path) in self._best_routes.items():
            result[dest] = as_path
        return result

    def __str__(self):
        return "EGP object {} (AS {})".format(hash(self), self._asn)
