// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Foundation
import Network

/// Discovers Bumblebee drones on the local network.
///
/// Primary path is zero-config **Bonjour/mDNS**: each drone advertises a
/// `_bumblebee._tcp` service whose instance resolves to an IP and whose TXT
/// record carries a friendly `name` (e.g. "Bumblebee-20EC") and its hardware
/// `id`. This works on a shared WiFi and over a drone's own hotspot alike,
/// with no IP typing.
///
/// A brute-force /24 subnet scan (rosbridge :9090 probe) stays as a fallback
/// for drones that are reachable but not yet advertising the service. A host
/// with 9090 open counts as a drone only if the drone's REST API or metrics
/// answer like one (DeviceKind); anything else is listed apart as an unknown
/// device. Every row is re-probed every 10 s: a drone switched off greys out,
/// then leaves the list (Liveness).
@MainActor
final class DroneScanner: ObservableObject {
    struct Drone: Identifiable, Equatable {
        let id: String      // ip, stable
        var ip: String { id }
        var name: String
        /// True when the name/ports came from the drone's Bonjour TXT record —
        /// a trusted friendly name the subnet-scan enrichment must not clobber.
        var bonjour: Bool = false
        /// The drone's hardware id (TXT `id` or /api/wifi/status), if known.
        var droneID: String? = nil
        /// False for a host with 9090 open that does not answer like a drone.
        var isDrone: Bool = true
        /// TCP probes of :9090 missed in a row (Liveness).
        var misses: Int = 0
        var liveness: Liveness { Liveness.of(misses: misses) }
    }

    @Published private(set) var found: [Drone] = []
    @Published private(set) var scanning = false
    /// True once at least one scan has finished — lets the UI tell "haven't
    /// scanned yet" apart from "scanned and found nothing".
    @Published private(set) var hasScanned = false
    /// Set when Bonjour browsing cannot run at all — on macOS almost always
    /// because Local Network access was denied for this app.
    @Published private(set) var discoveryError: String?

    /// Drones (not unknown devices) for the list.
    var drones: [Drone] { found.filter(\.isDrone) }
    var unknownDevices: [Drone] { found.filter { !$0.isDrone } }
    /// Ids of the drones listed on the network now.
    var visibleIDs: Set<String> { Set(found.compactMap { $0.droneID?.uppercased() }) }
    var foundIDs: [(ip: String, droneID: String?)] { found.map { ($0.ip, $0.droneID) } }

    nonisolated private let probeQueue = DispatchQueue(label: "gcs.scan", attributes: .concurrent)
    private let session = URLSession(configuration: .drone)
    private var bonjour: BonjourDroneBrowser?
    private var livenessTimer: Timer?
    private var lostAt: [String: Date] = [:]   // ip -> Bonjour said removed

    /// Starts continuous Bonjour discovery and the liveness re-probe. Safe to
    /// call more than once.
    func startDiscovery() {
        startLiveness()
        guard bonjour == nil else { return }
        let browser = BonjourDroneBrowser(
            onFound: { [weak self] ip, name, id in
                Task { @MainActor in self?.upsertBonjour(ip: ip, name: name, droneID: id) }
            },
            onLost: { [weak self] ip in
                Task { @MainActor in self?.bonjourLost(ip) }
            },
            onError: { [weak self] message in
                Task { @MainActor in self?.discoveryError = message }
            })
        bonjour = browser
        browser.start()
    }

    /// Merge a Bonjour-discovered drone into `found`, keyed by IP. A Bonjour
    /// name always wins over a subnet-scan placeholder. A drone that moved to
    /// a new address loses its old row.
    private func upsertBonjour(ip: String, name: String, droneID: String?) {
        let display = name.isEmpty ? ip : name
        lostAt[ip] = nil
        if let id = droneID?.uppercased() {
            found.removeAll { $0.ip != ip && $0.droneID?.uppercased() == id }
        }
        if let idx = found.firstIndex(where: { $0.id == ip }) {
            found[idx].name = display
            found[idx].bonjour = true
            found[idx].isDrone = true
            found[idx].misses = 0
            if let id = droneID { found[idx].droneID = id.uppercased() }
        } else {
            found.append(Drone(id: ip, name: display, bonjour: true, droneID: droneID?.uppercased()))
            sortFound()
        }
    }

    /// Bonjour also says "removed" on a short Wi-Fi blip: the row goes only if
    /// it did not come back within Liveness.lostGrace.
    private func bonjourLost(_ ip: String) {
        let at = Date()
        lostAt[ip] = at
        DispatchQueue.main.asyncAfter(deadline: .now() + Liveness.lostGrace) { [weak self] in
            guard let self = self, self.lostAt[ip] == at else { return }
            self.lostAt[ip] = nil
            self.found.removeAll { $0.id == ip && $0.bonjour }
        }
    }

    private func sortFound() {
        found.sort { $0.ip.compare($1.ip, options: .numeric) == .orderedAscending }
    }

    func scan() {
        guard !scanning else { return }
        guard let prefix = Self.localSubnetPrefix() else { hasScanned = true; return }
        scanning = true
        found = []
        lostAt = [:]
        // NetServiceBrowser never re-reports a service it already announced,
        // so restart it: live drones come back within a moment, gone ones don't.
        bonjour?.stop()
        bonjour = nil
        startDiscovery()

        let group = DispatchGroup()
        let gate = DispatchSemaphore(value: 48) // cap concurrent sockets

        // The semaphore wait must not run on the main thread (it froze the UI
        // for the ~3 s the sweep takes).
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            for i in 1...254 {
                let ip = "\(prefix)\(i)"
                group.enter()
                gate.wait()
                probe(ip: ip, port: 9090, timeout: 0.6) { open in
                    if open {
                        Task { @MainActor in self.add(ip: ip) }
                    }
                    gate.signal()
                    group.leave()
                }
            }
            group.notify(queue: .main) {
                Task { @MainActor [weak self] in
                    self?.scanning = false
                    self?.hasScanned = true
                }
            }
        }
    }

    /// One-off reachability check for a single host — is rosbridge (:9090) open?
    func isReachable(_ ip: String, timeout: TimeInterval = 1.0) async -> Bool {
        await withCheckedContinuation { cont in
            probe(ip: ip, port: 9090, timeout: timeout) { open in cont.resume(returning: open) }
        }
    }

    /// A subnet-scan hit: listed at once, then confirmed as a drone (or not).
    private func add(ip: String) {
        guard !found.contains(where: { $0.id == ip }) else { return }
        found.append(Drone(id: ip, name: ip))
        sortFound()
        Task { await classify(ip: ip) }
    }

    private func classify(ip: String) async {
        async let status = fetchJSON("http://\(ip):\(DroneAPI.port)/api/wifi/status")
        async let metrics = fetchJSON("http://\(ip):8888/")
        let kind = DeviceKind.classify(wifiStatus: await status, metrics: await metrics)
        guard let idx = found.firstIndex(where: { $0.id == ip }), !found[idx].bonjour else { return }
        switch kind {
        case .drone(let id, let name):
            found[idx].isDrone = true
            found[idx].droneID = id
            if let name { found[idx].name = "\(name) (\(ip))" }
            if let id, found.contains(where: { $0.ip != ip && $0.droneID == id }) {
                found.remove(at: idx)            // the same drone is listed already
            }
        case .unknownDevice:
            found[idx].isDrone = false
        }
    }

    private func fetchJSON(_ url: String) async -> [String: Any]? {
        guard let u = URL(string: url) else { return nil }
        var req = URLRequest(url: u, timeoutInterval: 1.5)
        req.httpMethod = "GET"
        guard let (data, _) = try? await session.data(for: req) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    // MARK: - Liveness

    private func startLiveness() {
        guard livenessTimer == nil else { return }
        let t = Timer(timeInterval: Liveness.period, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.recheck() }
        }
        RunLoop.main.add(t, forMode: .common)
        livenessTimer = t
    }

    /// Probe every row once; rows found only by the subnet scan go after
    /// Liveness.goneAfter misses (Bonjour rows go when Bonjour says so).
    private func recheck() async {
        for row in found {
            let open = await isReachable(row.ip, timeout: 1.5)
            guard let idx = found.firstIndex(where: { $0.id == row.id }) else { continue }
            found[idx].misses = open ? 0 : found[idx].misses + 1
            if found[idx].liveness == .gone, !found[idx].bonjour { found.remove(at: idx) }
        }
    }

    // MARK: - TCP probe

    nonisolated private func probe(ip: String, port: UInt16, timeout: TimeInterval,
                                   completion: @escaping @Sendable (Bool) -> Void) {
        guard let nwPort = NWEndpoint.Port(rawValue: port) else { completion(false); return }
        let conn = NWConnection(host: NWEndpoint.Host(ip), port: nwPort, using: .tcp)
        // One serial queue per probe: the state handler and the timeout must
        // not race on `finished` (on the shared concurrent queue they could both
        // complete, and a double DispatchGroup.leave() in scan() crashes).
        let queue = DispatchQueue(label: "gcs.scan.probe", target: probeQueue)
        var finished = false
        let done: (Bool) -> Void = { ok in
            if finished { return }
            finished = true
            conn.cancel()
            completion(ok)
        }
        conn.stateUpdateHandler = { state in
            switch state {
            case .ready: done(true)
            case .failed, .cancelled: done(false)
            default: break
            }
        }
        conn.start(queue: queue)
        queue.asyncAfter(deadline: .now() + timeout) { done(false) }
    }

    // MARK: - Subnet discovery

    /// Returns "x.y.z." for the Mac's primary IPv4 interface, or nil.
    static func localSubnetPrefix() -> String? {
        var prefix: String?
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return nil }
        defer { freeifaddrs(ifaddr) }

        var ptr: UnsafeMutablePointer<ifaddrs>? = first
        while let cur = ptr {
            let flags = Int32(cur.pointee.ifa_flags)
            let addr = cur.pointee.ifa_addr
            if let addr = addr,
               addr.pointee.sa_family == UInt8(AF_INET),
               (flags & IFF_UP) == IFF_UP,
               (flags & IFF_LOOPBACK) == 0 {
                let name = String(cString: cur.pointee.ifa_name)
                // Prefer wifi (en0) / ethernet (enX) interfaces.
                if name.hasPrefix("en") {
                    var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                    if getnameinfo(addr, socklen_t(addr.pointee.sa_len),
                                   &host, socklen_t(host.count),
                                   nil, 0, NI_NUMERICHOST) == 0 {
                        let ip = String(cString: host)
                        let octets = ip.split(separator: ".")
                        if octets.count == 4 {
                            prefix = "\(octets[0]).\(octets[1]).\(octets[2])."
                            break
                        }
                    }
                }
            }
            ptr = cur.pointee.ifa_next
        }
        return prefix
    }
}

/// Bonjour/mDNS browser for the drone's `_bumblebee._tcp` service.
///
/// Resolves each discovered service to an IPv4 address and reads the friendly
/// `name` and hardware `id` from its TXT record. Scheduled on the main run
/// loop; results are forwarded via `onFound(ip, name, id)`.
final class BonjourDroneBrowser: NSObject, NetServiceBrowserDelegate, NetServiceDelegate {
    private let browser = NetServiceBrowser()
    private var resolving = Set<NetService>()      // retain services during resolve
    private var resolvedIP: [String: String] = [:] // service name -> IPv4
    private var retries: [String: Int] = [:]       // service name -> re-resolves left
    private let onFound: (String, String, String?) -> Void
    private let onLost: ((String) -> Void)?
    private let onError: ((String) -> Void)?
    private let accept: ((String) -> Bool)?

    /// - Parameter accept: return false for an address that must not be used
    ///   (e.g. a cached 10.42.x record from the drone's own hotspot); the
    ///   service is then resolved again a little later.
    init(onFound: @escaping (String, String, String?) -> Void,
         onLost: ((String) -> Void)? = nil,
         onError: ((String) -> Void)? = nil,
         accept: ((String) -> Bool)? = nil) {
        self.onFound = onFound
        self.onLost = onLost
        self.onError = onError
        self.accept = accept
        super.init()
        browser.delegate = self
    }

    func start() { browser.searchForServices(ofType: "_bumblebee._tcp.", inDomain: "local.") }

    /// Stops browsing and resolving. NetService/NetServiceBrowser delegates are
    /// `assign` (not weak), so they must be detached before this object goes away.
    func stop() {
        browser.stop()
        browser.delegate = nil
        for service in resolving {
            service.stop()
            service.delegate = nil
        }
        resolving.removeAll()
        retries.removeAll()
    }

    deinit { stop() }

    // MARK: NetServiceBrowserDelegate

    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        retries[service.name] = 30
        resolve(service)
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
        resolving = resolving.filter { $0.name != service.name }
        retries[service.name] = nil
        guard let ip = resolvedIP.removeValue(forKey: service.name) else { return }
        // Another advertised service may still live at the same address.
        if !resolvedIP.values.contains(ip) { onLost?(ip) }
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didNotSearch errorDict: [String: NSNumber]) {
        onError?("Bonjour discovery is blocked. Allow Bumblebee GCS in System Settings → "
                 + "Privacy & Security → Local Network, then restart the app.")
    }

    // MARK: NetServiceDelegate

    func netServiceDidResolveAddress(_ sender: NetService) {
        // The first callback may carry only the IPv6 address; keep the service
        // retained so the IPv4 one can still arrive in a later callback.
        guard let ip = Self.ipv4(from: sender) else { return }
        if let accept = accept, !accept(ip) {
            retryLater(sender)
            return
        }
        resolving.remove(sender)
        retries[sender.name] = nil
        resolvedIP[sender.name] = ip
        onFound(ip, Self.txt(sender, "name") ?? sender.name, Self.txt(sender, "id"))
    }

    /// Resolution ended (5 s timeout) without a usable IPv4 address — e.g. only
    /// IPv6 arrived. Try again while retries last instead of dropping the drone.
    func netServiceDidStop(_ sender: NetService) {
        guard resolving.contains(sender) else { return }
        if retries[sender.name] != nil {
            retryLater(sender)
        } else {
            resolving.remove(sender)
        }
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        if retries[sender.name] != nil, accept != nil {
            retryLater(sender)        // still waiting for a usable address
        } else {
            resolving.remove(sender)
        }
    }

    // MARK: Resolving

    private func resolve(_ service: NetService) {
        service.delegate = self
        resolving.insert(service)
        service.resolve(withTimeout: 5.0)
    }

    /// Resolve the same service again in 2 s with a fresh NetService (the old
    /// one keeps returning its cached address).
    private func retryLater(_ sender: NetService) {
        resolving.remove(sender)
        sender.stop()
        sender.delegate = nil
        let left = (retries[sender.name] ?? 0) - 1
        guard left > 0 else { retries[sender.name] = nil; return }
        retries[sender.name] = left
        let (domain, type, name) = (sender.domain, sender.type, sender.name)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            guard let self = self, self.retries[name] != nil else { return }
            self.resolve(NetService(domain: domain, type: type, name: name))
        }
    }

    // MARK: Parsing

    private static func txt(_ service: NetService, _ key: String) -> String? {
        guard let data = service.txtRecordData() else { return nil }
        let dict = NetService.dictionary(fromTXTRecord: data)
        guard let raw = dict[key], let s = String(data: raw, encoding: .utf8), !s.isEmpty else { return nil }
        return s
    }

    private static func ipv4(from service: NetService) -> String? {
        guard let addresses = service.addresses else { return nil }
        for data in addresses {
            let ip: String? = data.withUnsafeBytes { raw in
                guard let sa = raw.bindMemory(to: sockaddr.self).baseAddress,
                      sa.pointee.sa_family == UInt8(AF_INET),
                      let sin = raw.bindMemory(to: sockaddr_in.self).baseAddress else { return nil }
                var addr = sin.pointee.sin_addr
                var buf = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                inet_ntop(AF_INET, &addr, &buf, socklen_t(INET_ADDRSTRLEN))
                return String(cString: buf)
            }
            if let ip = ip { return ip }
        }
        return nil
    }
}
