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

using System.Net;
using BumblebeeGcs.Logic;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text.Json;
using Microsoft.UI.Dispatching;

namespace BumblebeeGcs.Services;

/// <summary>
/// Обнаружение дронов Bumblebee в локальной сети.
///
/// Основной путь — zero-config DNS-SD (`_bumblebee._tcp`): имя и id из TXT-записи.
/// Фолбэк — брутфорс-скан /24 подсети (проба rosbridge :9090). Хост с открытым 9090
/// считается дроном, только если REST или метрики дрона отвечают как у дрона
/// (DeviceKind); иначе он показан отдельно как неизвестное устройство. Каждая строка
/// перепроверяется раз в 10 с: выключенный дрон сереет и уходит из списка (Liveness).
/// Все мутации `Found` — на UI-потоке.
/// </summary>
public sealed class DroneScanner
{
    public sealed class Drone
    {
        public required string Ip { get; init; }
        public required string Name { get; set; }
        /// <summary>Имя пришло из Bonjour TXT — субнет-скан не должен его затирать.</summary>
        public bool Bonjour { get; set; }
        /// <summary>Аппаратный id дрона (TXT id или /api/wifi/status), если известен.</summary>
        public string? DroneId { get; set; }
        /// <summary>false у хоста с открытым 9090, который не отвечает как дрон.</summary>
        public bool IsDrone { get; set; } = true;
        /// <summary>Подряд пропущенные пробы :9090.</summary>
        public int Misses { get; set; }
        public Liveness Liveness => LivenessRule.Of(Misses);
    }

    public readonly List<Drone> Found = new();
    public bool Scanning { get; private set; }
    /// <summary>true после первого завершённого скана — отличает «ещё не искали» от «не нашли».</summary>
    public bool HasScanned { get; private set; }

    public IEnumerable<Drone> Drones => Found.Where(d => d.IsDrone);
    public IEnumerable<Drone> UnknownDevices => Found.Where(d => !d.IsDrone);
    /// <summary>Ids дронов, видимых в сети сейчас.</summary>
    public ISet<string> VisibleIds => Found.Where(d => d.DroneId is not null).Select(d => d.DroneId!).ToHashSet();
    public IEnumerable<(string Ip, string? DroneId)> FoundIds => Found.Select(d => (d.Ip, d.DroneId));

    public event Action? Changed;

    /// <summary>Мимо системного прокси: дрон в локальной сети, школьный прокси до него не дотянется.</summary>
    private static readonly HttpClient Http = new(new SocketsHttpHandler { UseProxy = false })
    {
        Timeout = TimeSpan.FromSeconds(1.5),
    };

    private readonly DispatcherQueue _dq;
    private DnssdBrowser? _bonjour;
    private DispatcherQueueTimer? _liveness;
    private readonly Dictionary<string, double> _lostAt = new();   // ip -> DNS-SD сказал «пропал»

    public DroneScanner(DispatcherQueue dq) => _dq = dq;

    /// <summary>Непрерывное Bonjour-обнаружение и перепроверка строк. Повторный вызов безопасен.</summary>
    public void StartDiscovery()
    {
        StartLiveness();
        if (_bonjour is not null) return;
        _bonjour = new DnssdBrowser(
            (ip, name, id) => _dq.TryEnqueue(() => UpsertBonjour(ip, name, id)),
            ip => _dq.TryEnqueue(() => BonjourLost(ip)));
        _bonjour.Start();
    }

    /// <summary>Дрон, переехавший на новый адрес, теряет старую строку.</summary>
    private void UpsertBonjour(string ip, string name, string? droneId)
    {
        var display = string.IsNullOrEmpty(name) ? ip : name;
        var id = droneId?.ToUpperInvariant();
        _lostAt.Remove(ip);
        if (id is not null) Found.RemoveAll(d => d.Ip != ip && d.DroneId == id);
        var existing = Found.FirstOrDefault(d => d.Ip == ip);
        if (existing is not null)
        {
            existing.Name = display;
            existing.Bonjour = true;
            existing.IsDrone = true;
            existing.Misses = 0;
            if (id is not null) existing.DroneId = id;
        }
        else
        {
            Found.Add(new Drone { Ip = ip, Name = display, Bonjour = true, DroneId = id });
            SortFound();
        }
        Changed?.Invoke();
    }

    /// <summary>DNS-SD говорит «пропал» и при коротком сбое Wi-Fi: строка уходит, только если
    /// не вернулась за LostGraceSeconds.</summary>
    private void BonjourLost(string ip)
    {
        var at = MonoClock.Now;
        _lostAt[ip] = at;
        var t = _dq.CreateTimer();
        t.Interval = TimeSpan.FromSeconds(LivenessRule.LostGraceSeconds);
        t.IsRepeating = false;
        t.Tick += (_, _) =>
        {
            if (!_lostAt.TryGetValue(ip, out var when) || when != at) return;
            _lostAt.Remove(ip);
            if (Found.RemoveAll(d => d.Ip == ip && d.Bonjour) > 0) Changed?.Invoke();
        };
        t.Start();
    }

    /// <summary>Rescan стирает только строки субнет-скана: DNS-SD-записи остаются (наблюдатель
    /// не сообщает их повторно, раньше они пропадали до следующего Updated).</summary>
    public void Scan()
    {
        if (Scanning) return;
        var prefix = LocalSubnetPrefix();
        if (prefix is null)
        {
            HasScanned = true;
            Changed?.Invoke();
            return;
        }
        Scanning = true;
        Found.RemoveAll(d => !d.Bonjour);
        Changed?.Invoke();

        _ = Task.Run(async () =>
        {
            using var gate = new SemaphoreSlim(48); // потолок одновременных сокетов
            var tasks = new List<Task>(254);
            for (var i = 1; i <= 254; i++)
            {
                var ip = $"{prefix}{i}";
                await gate.WaitAsync();
                tasks.Add(Task.Run(async () =>
                {
                    try
                    {
                        if (await ProbeAsync(ip, 9090, TimeSpan.FromMilliseconds(600)))
                            _dq.TryEnqueue(() => Add(ip));
                    }
                    finally { gate.Release(); }
                }));
            }
            await Task.WhenAll(tasks);
            _dq.TryEnqueue(() =>
            {
                Scanning = false;
                HasScanned = true;
                Changed?.Invoke();
            });
        });
    }

    /// <summary>Разовая проверка доступности хоста — открыт ли rosbridge (:9090)?</summary>
    public static Task<bool> IsReachableAsync(string ip, double timeoutSeconds = 1.0) =>
        ProbeAsync(ip, 9090, TimeSpan.FromSeconds(timeoutSeconds));

    /// <summary>Находка субнет-скана: показана сразу, потом подтверждается как дрон (или нет).</summary>
    private void Add(string ip)
    {
        if (Found.Any(d => d.Ip == ip)) return;
        Found.Add(new Drone { Ip = ip, Name = ip });
        SortFound();
        Changed?.Invoke();
        _ = ClassifyAsync(ip);
    }

    private async Task ClassifyAsync(string ip)
    {
        var status = FetchJsonAsync($"http://{ip}:{DroneApi.Port}/api/wifi/status");
        var metrics = FetchJsonAsync($"http://{ip}:8888/");
        var kind = DeviceKind.Classify(await status, await metrics);
        _dq.TryEnqueue(() =>
        {
            var d = Found.FirstOrDefault(d => d.Ip == ip);
            if (d is null || d.Bonjour) return;
            d.IsDrone = kind.IsDrone;
            d.DroneId = kind.DroneId;
            if (kind.Name is string name) d.Name = $"{name} ({ip})";
            if (kind.DroneId is string id && Found.Any(o => o.Ip != ip && o.DroneId == id)) Found.Remove(d);
            Changed?.Invoke();
        });
    }

    private static async Task<JsonElement?> FetchJsonAsync(string url)
    {
        try
        {
            var data = await Http.GetByteArrayAsync(url);
            using var doc = JsonDocument.Parse(data);
            return doc.RootElement.Clone();
        }
        catch { return null; }
    }

    private void SortFound()
    {
        Found.Sort((a, b) => CompareIps(a.Ip, b.Ip));
        static int CompareIps(string x, string y)
        {
            if (IPAddress.TryParse(x, out var ax) && IPAddress.TryParse(y, out var ay))
            {
                var bx = ax.GetAddressBytes();
                var by = ay.GetAddressBytes();
                for (var i = 0; i < Math.Min(bx.Length, by.Length); i++)
                    if (bx[i] != by[i]) return bx[i].CompareTo(by[i]);
                return bx.Length.CompareTo(by.Length);
            }
            return string.CompareOrdinal(x, y);
        }
    }

    // MARK: - Liveness

    private void StartLiveness()
    {
        if (_liveness is not null) return;
        _liveness = _dq.CreateTimer();
        _liveness.Interval = TimeSpan.FromSeconds(LivenessRule.PeriodSeconds);
        _liveness.Tick += (_, _) => _ = RecheckAsync();
        _liveness.Start();
    }

    /// <summary>Пробуем каждую строку; строки только субнет-скана уходят после GoneAfter промахов
    /// (DNS-SD-строки уходят, когда так скажет DNS-SD).</summary>
    private async Task RecheckAsync()
    {
        var rows = Found.Select(d => d.Ip).ToList();
        var results = await Task.WhenAll(rows.Select(ip => IsReachableAsync(ip, 1.5)));
        var changed = false;
        for (var i = 0; i < rows.Count; i++)
        {
            var d = Found.FirstOrDefault(d => d.Ip == rows[i]);
            if (d is null) continue;
            var misses = results[i] ? 0 : d.Misses + 1;
            if (misses != d.Misses) { d.Misses = misses; changed = true; }
            if (d.Liveness == Liveness.Gone && !d.Bonjour) { Found.Remove(d); changed = true; }
        }
        if (changed) Changed?.Invoke();
    }

    // MARK: - TCP probe

    private static async Task<bool> ProbeAsync(string ip, int port, TimeSpan timeout)
    {
        using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
        using var cts = new CancellationTokenSource(timeout);
        try
        {
            await socket.ConnectAsync(ip, port, cts.Token);
            return true;
        }
        catch { return false; }
    }

    // MARK: - Subnet discovery

    /// <summary>«x.y.z.» адаптера, в чьей сети ПК на самом деле (с default gateway), без
    /// виртуальных (WSL2/Hyper-V vEthernet, VirtualBox, VMware), или null. См. ScanAdapter.</summary>
    public static string? LocalSubnetPrefix()
    {
        var candidates = new List<ScanAdapter.Candidate>();
        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (nic.OperationalStatus != OperationalStatus.Up ||
                nic.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel) continue;
            var props = nic.GetIPProperties();
            var hasGateway = props.GatewayAddresses.Any(g =>
                g.Address.AddressFamily == AddressFamily.InterNetwork && !g.Address.Equals(IPAddress.Any));
            foreach (var addr in props.UnicastAddresses)
            {
                if (addr.Address.AddressFamily != AddressFamily.InterNetwork) continue;
                candidates.Add(new ScanAdapter.Candidate(nic.Name, nic.Description,
                    nic.NetworkInterfaceType == NetworkInterfaceType.Wireless80211, hasGateway, addr.Address.ToString()));
            }
        }
        return ScanAdapter.Prefix(candidates);
    }
}
