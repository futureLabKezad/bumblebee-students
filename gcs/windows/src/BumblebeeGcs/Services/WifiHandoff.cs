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

using System.Security;
using ManagedNativeWifi;
using Microsoft.UI.Dispatching;
using Windows.Devices.Geolocation;

namespace BumblebeeGcs.Services;

/// <summary>
/// «Добавить дрон»: найти setup-хотспот дрона в эфире, подключиться к нему,
/// передать дрону WiFi этого ПК, вернуть ПК в его сеть и найти там именно этот
/// дрон (по его id). Если дрон не появился — спросить у него, почему, и
/// объяснить понятными словами. Порт WifiHandoff.swift (CoreWLAN → wlanapi
/// через ManagedNativeWifi, CoreLocation → Geolocator: Windows 11 требует
/// геолокацию для скана WiFi). Все публичные члены — UI-поток.
/// </summary>
public sealed class WifiHandoff
{
    /// <summary>Общий PSK setup-хотспота дрона (SSID "Bumblebee-XXXX").</summary>
    public const string HotspotPsk = "12345678";
    /// <summary>Префикс каждого setup-хотспота.</summary>
    public const string HotspotPrefix = "Bumblebee-";
    /// <summary>Дрон в режиме AP (NetworkManager shared) — шлюз по этому адресу.</summary>
    public const string HotspotGatewayHost = "10.42.0.1";

    public enum PhaseKind
    {
        Idle,
        NeedLocationPermission,
        Scanning,
        Picking,           // хотспоты показаны, ждём выбора
        // шаги настройки по порядку
        JoiningHotspot,    // 1. говорим с новым дроном через его WiFi (Arg = SSID)
        PushingCreds,      // 2. отдаём ему имя и пароль нашей WiFi
        WaitingForDrone,   // 3. дрон уходит в нашу WiFi, ПК возвращается, ищем дрон
        Diagnosing,        // не появился: спрашиваем дрон, почему
        Done,              // Arg = хост дрона
        Failed,            // см. LastFailure
    }

    public enum FailureKind { WrongPassword, NotFound, NoAddress, Isolated, DroneSilent, Other }

    /// <summary>Неудачная настройка, объяснённая для пользователя.</summary>
    public sealed record Failure(FailureKind Kind, string Title, string Detail)
    {
        /// <summary>Предлагать «подключиться к дрону напрямую» (без общей WiFi).</summary>
        public bool OfferDirect => Kind != FailureKind.WrongPassword;
    }

    public PhaseKind Phase { get; private set; } = PhaseKind.Idle;
    /// <summary>SSID для JoiningHotspot, хост для Done.</summary>
    public string PhaseArg { get; private set; } = "";
    /// <summary>Причина для Phase == Failed.</summary>
    public Failure? LastFailure { get; private set; }

    /// <summary>Идёт настройка дрона (не фоновое сканирование: оно не мешает
    /// ни кнопкам, ни закрытию окна).</summary>
    public bool IsBusy => Phase is PhaseKind.JoiningHotspot
        or PhaseKind.PushingCreds or PhaseKind.WaitingForDrone or PhaseKind.Diagnosing;

    public sealed record Hotspot(string Ssid, int Rssi);

    public List<Hotspot> Hotspots { get; private set; } = new();
    /// <summary>Текущий SSID этого ПК. Может оказаться хотспотом дрона.</summary>
    public string CurrentSsid { get; private set; } = "";
    /// <summary>ПК сейчас подключён к WiFi самого дрона.</summary>
    public bool OnDroneHotspot => CurrentSsid.StartsWith(HotspotPrefix, StringComparison.Ordinal);
    /// <summary>
    /// Сеть, которую отдаём дрону: WiFi этого ПК, но никогда не хотспот дрона.
    /// Пока ПК на хотспоте — сеть, где он был до этого (и куда вернётся);
    /// пусто, если предложить нечего.
    /// </summary>
    public string HomeSsid => OnDroneHotspot ? (_settings.LastHomeSsid ?? "") : CurrentSsid;
    /// <summary>Система окончательно запретила геолокацию — шлём в Настройки.</summary>
    public bool LocationBlocked { get; private set; }

    public event Action? Changed;

    private readonly DispatcherQueue _dq;
    private readonly AppSettings _settings;

    public WifiHandoff(DispatcherQueue dq, AppSettings settings)
    {
        _dq = dq;
        _settings = settings;
    }

    private void SetPhase(PhaseKind phase, string arg = "")
    {
        Phase = phase;
        PhaseArg = arg;
        if (phase != PhaseKind.Failed) LastFailure = null;
        Changed?.Invoke();
    }

    private void Fail(Failure failure)
    {
        LastFailure = failure;
        SetPhase(PhaseKind.Failed);
    }

    private static Failure Explain(FailureKind kind, string title, string detail) => new(kind, title, detail);

    public void Reset() => SetPhase(PhaseKind.Idle);

    public void RefreshCurrentSsid()
    {
        string ssid;
        try { ssid = NativeWifi.EnumerateConnectedNetworkSsids().FirstOrDefault()?.ToString() ?? ""; }
        catch { ssid = ""; }
        CurrentSsid = ssid;
        if (ssid.Length > 0 && !ssid.StartsWith(HotspotPrefix, StringComparison.Ordinal)
            && ssid != _settings.LastHomeSsid)
        {
            _settings.LastHomeSsid = ssid;
            _settings.Save();
        }
        Changed?.Invoke();
    }

    // MARK: - Location (нужна для скана WiFi на Windows 11)

    /// <summary>
    /// Разово запросить доступ к геолокации при старте, чтобы разрешение было
    /// выяснено до настройки дрона (аналог requestLocation на маке).
    /// </summary>
    public async Task RequestLocationAsync()
    {
        try
        {
            var access = await Geolocator.RequestAccessAsync();
            LocationBlocked = access == GeolocationAccessStatus.Denied;
        }
        catch { }
        Changed?.Invoke();
    }

    private static Guid? PrimaryInterfaceId()
    {
        try { return NativeWifi.EnumerateInterfaces().FirstOrDefault()?.Id; }
        catch { return null; }
    }

    // MARK: - Scan for drone hotspots

    public async Task ScanHotspotsAsync()
    {
        if (IsBusy) return;                 // скан не должен перебить идущую настройку
        if (PrimaryInterfaceId() is null)
        {
            Fail(Explain(FailureKind.Other, "This PC has no WiFi", "Turn WiFi on and try again."));
            return;
        }
        try
        {
            var access = await Geolocator.RequestAccessAsync();
            LocationBlocked = access == GeolocationAccessStatus.Denied;
            if (access != GeolocationAccessStatus.Allowed)
            {
                if (!IsBusy) SetPhase(PhaseKind.NeedLocationPermission);
                return;
            }
        }
        catch { }

        if (IsBusy) return;                 // настройку начали, пока ждали разрешения
        SetPhase(PhaseKind.Scanning);
        RefreshCurrentSsid();
        try
        {
            var list = await Task.Run(async () =>
            {
                try { await NativeWifi.ScanNetworksAsync(TimeSpan.FromSeconds(6)); } catch { }
                return NativeWifi.EnumerateBssNetworks()
                    .Where(n => n.Ssid.ToString().StartsWith(HotspotPrefix, StringComparison.Ordinal))
                    .GroupBy(n => n.Ssid.ToString())
                    .Select(g => new Hotspot(g.Key, g.Max(n => n.SignalStrength)))
                    .OrderByDescending(h => h.Rssi)
                    .ToList();
            });
            Hotspots = list;
            // Пока сканировали, могли нажать «Add»: не затираем начатую настройку.
            if (Phase == PhaseKind.Scanning) SetPhase(PhaseKind.Picking);
            else Changed?.Invoke();
        }
        catch (Exception ex)
        {
            if (Phase == PhaseKind.Scanning) Fail(Explain(FailureKind.Other, "WiFi scan failed", ex.Message));
        }
    }

    // MARK: - Full hand-off

    /// <summary>
    /// Настроить новый дрон: войти в его WiFi (hotspotSsid), передать ему
    /// targetSsid/targetPassword, вернуть ПК в targetSsid и найти там именно
    /// этот дрон. Если не появился — узнать у дрона причину (после неудачи он
    /// через ~45 с снова поднимает свой WiFi) и объяснить её.
    /// </summary>
    public async Task ProvisionAsync(string hotspotSsid, string targetSsid, string targetPassword,
                                     Action<string> onDrone)
    {
        // Задача запускается без await (`_ =`): любое исключение должно стать
        // понятной ошибкой, а не оставить окно «занятым» навсегда.
        try { await ProvisionCoreAsync(hotspotSsid, targetSsid, targetPassword, onDrone); }
        catch (Exception ex) { Fail(Explain(FailureKind.Other, "Setup stopped", ex.Message)); }
    }

    private async Task ProvisionCoreAsync(string hotspotSsid, string targetSsid, string targetPassword,
                                          Action<string> onDrone)
    {
        if (PrimaryInterfaceId() is not Guid iface)
        {
            Fail(Explain(FailureKind.Other, "This PC has no WiFi", "Turn WiFi on and try again."));
            return;
        }

        // 1) Войти в WiFi дрона.
        SetPhase(PhaseKind.JoiningHotspot, hotspotSsid);
        if (await JoinHotspotAsync(iface, hotspotSsid) is string joinErr)
        {
            Fail(Explain(FailureKind.DroneSilent, $"Couldn't reach {hotspotSsid}",
                $"{joinErr}. Make sure the drone is on and glowing blue, then try again."));
            await ReturnHomeAsync(iface, targetSsid);
            return;
        }

        // 2) Поговорить с ним и передать нашу WiFi.
        SetPhase(PhaseKind.PushingCreds);
        var api = new DroneApi { Host = HotspotGatewayHost };
        if (await WaitForBackendAsync(api) is not DroneApi.WifiStatus status)
        {
            Fail(Explain(FailureKind.DroneSilent, "The drone didn't answer",
                $"The PC joined {hotspotSsid} but the drone's software didn't respond. Wait a minute after power-on and try again."));
            await ReturnHomeAsync(iface, targetSsid);
            return;
        }
        // Дрон сообщает свой id — по нему узнаем именно его в общей сети.
        var expectedId = status.Id;
        try
        {
            await api.SaveNetworkAsync(targetSsid, targetPassword);
        }
        catch (Exception ex)
        {
            Fail(Explain(FailureKind.Other, "Couldn't send the WiFi settings", ex.Message));
            await ReturnHomeAsync(iface, targetSsid);
            return;
        }
        try
        {
            await api.ApplyNowAsync(targetSsid);
        }
        catch (DroneApi.ApiException ex) when (ex.Transport)
        {
            // Старое ПО дрона переключает WiFi раньше, чем отвечает, — это ожидаемо.
        }
        catch (Exception ex)
        {
            Fail(Explain(FailureKind.Other, "Couldn't send the WiFi settings", ex.Message));
            await ReturnHomeAsync(iface, targetSsid);
            return;
        }

        // 3) Дрон уходит в нашу WiFi; возвращаем ПК и ищем дрон.
        SetPhase(PhaseKind.WaitingForDrone);
        await ReturnHomeAsync(iface, targetSsid);
        if (await WaitForDroneAsync(expectedId) is string host)
        {
            SetPhase(PhaseKind.Done, host);
            onDrone(host);
            return;
        }

        // 4) Не появился — выясняем почему.
        SetPhase(PhaseKind.Diagnosing);
        Fail(await DiagnoseAsync(iface, hotspotSsid, targetSsid));
    }

    /// <summary>
    /// Работать с дроном через его собственную WiFi (без общей сети; у ПК
    /// в это время нет интернета).
    /// </summary>
    public async Task ConnectDirectAsync(string hotspotSsid, Action<string> onDrone)
    {
        try { await ConnectDirectCoreAsync(hotspotSsid, onDrone); }
        catch (Exception ex) { Fail(Explain(FailureKind.Other, "Couldn't connect", ex.Message)); }
    }

    private async Task ConnectDirectCoreAsync(string hotspotSsid, Action<string> onDrone)
    {
        if (PrimaryInterfaceId() is not Guid iface) return;
        SetPhase(PhaseKind.JoiningHotspot, hotspotSsid);
        if (await JoinHotspotAsync(iface, hotspotSsid) is string err)
        {
            Fail(Explain(FailureKind.DroneSilent, $"Couldn't reach {hotspotSsid}", err));
            return;
        }
        var api = new DroneApi { Host = HotspotGatewayHost };
        if (await WaitForBackendAsync(api) is null)
        {
            Fail(Explain(FailureKind.DroneSilent, "The drone didn't answer", "Wait a minute after power-on and try again."));
            return;
        }
        SetPhase(PhaseKind.Done, HotspotGatewayHost);
        onDrone(HotspotGatewayHost);
    }

    /// <summary>
    /// После неудачной настройки дрон снова поднимает свой WiFi: читаем
    /// записанную им причину и возвращаем ПК в targetSsid.
    /// </summary>
    private async Task<Failure> DiagnoseAsync(Guid iface, string hotspotSsid, string targetSsid)
    {
        var visible = false;
        var deadline = DateTime.UtcNow.AddSeconds(75);
        while (DateTime.UtcNow < deadline)
        {
            visible = await Task.Run(async () =>
            {
                try
                {
                    try { await NativeWifi.ScanNetworksAsync(TimeSpan.FromSeconds(5)); } catch { }
                    return NativeWifi.EnumerateBssNetworks().Any(n => n.Ssid.ToString() == hotspotSsid);
                }
                catch { return false; }
            });
            if (visible) break;
            await Task.Delay(3000);
        }
        if (!visible)
        {
            // WiFi дрона не вернулся — скорее всего, дрон в targetSsid, но
            // этот ПК его там не видит.
            return Explain(FailureKind.Isolated, $"The drone joined {targetSsid}, but this PC can't see it",
                "Some networks keep devices apart (guest WiFi, \"AP isolation\"). Use another network — for example a phone hotspot — or connect directly to the drone.");
        }

        DroneApi.JoinError? reason = null;
        if (await JoinHotspotAsync(iface, hotspotSsid) is null)
        {
            var api = new DroneApi { Host = HotspotGatewayHost };
            reason = (await WaitForBackendAsync(api, 20))?.LastError;
        }
        await ReturnHomeAsync(iface, targetSsid);

        return reason?.Reason switch
        {
            "wrong_password" => Explain(FailureKind.WrongPassword, $"Wrong password for {targetSsid}",
                $"The drone couldn't log in to {targetSsid}. Check the password and try again."),
            "not_found" => Explain(FailureKind.NotFound, $"The drone can't see {targetSsid}",
                $"Move the drone closer to the router. If {targetSsid} is a 5 GHz-only network, use one that also has 2.4 GHz."),
            "no_ip" => Explain(FailureKind.NoAddress, $"{targetSsid} didn't give the drone an address",
                "The router didn't respond (DHCP). Restart the router or use another network."),
            _ => Explain(FailureKind.Other, $"The drone couldn't join {targetSsid}",
                reason is null ? "Try again, or connect directly to the drone."
                    : (reason.Message.Length == 0 ? "Try again." : reason.Message)),
        };
    }

    // MARK: - Helpers

    /// <summary>
    /// Войти в setup-WiFi дрона; null при успехе, иначе короткая причина.
    /// Первая попытка может упасть, пока адаптер переключается, — до 4 попыток
    /// со свежим сканом.
    /// </summary>
    private static async Task<string?> JoinHotspotAsync(Guid iface, string hotspotSsid)
    {
        var lastErr = "its WiFi is not in range";
        for (var attempt = 1; attempt <= 4; attempt++)
        {
            try
            {
                var joined = await Task.Run(async () =>
                {
                    var inRange = NativeWifi.EnumerateBssNetworks().Any(n => n.Ssid.ToString() == hotspotSsid);
                    if (!inRange)
                    {
                        try { await NativeWifi.ScanNetworksAsync(TimeSpan.FromSeconds(5)); } catch { }
                        inRange = NativeWifi.EnumerateBssNetworks().Any(n => n.Ssid.ToString() == hotspotSsid);
                    }
                    if (!inRange) throw new InvalidOperationException("its WiFi is not in range");
                    NativeWifi.SetProfile(iface, ProfileType.AllUser,
                        Wpa2PskProfileXml(hotspotSsid, HotspotPsk), null, overwrite: true);
                    return await NativeWifi.ConnectNetworkAsync(iface, hotspotSsid, BssType.Infrastructure,
                        TimeSpan.FromSeconds(15));
                });
                if (joined) return null;
                lastErr = "Windows couldn't connect to it";
            }
            catch (Exception ex)
            {
                lastErr = ex.Message;
            }
            if (attempt < 4) await Task.Delay(2000);
        }
        return lastErr;
    }

    /// <summary>
    /// Вернуть ПК в его сеть (профиль уже есть в Windows — ПК в ней был;
    /// Windows вернулась бы и сама, но медленнее).
    /// </summary>
    private static async Task ReturnHomeAsync(Guid iface, string homeSsid)
    {
        if (string.IsNullOrEmpty(homeSsid)) return;
        try
        {
            var current = NativeWifi.EnumerateConnectedNetworkSsids().FirstOrDefault()?.ToString();
            if (current == homeSsid) return;
            await Task.Run(() =>
                NativeWifi.ConnectNetworkAsync(iface, homeSsid, BssType.Infrastructure, TimeSpan.FromSeconds(20)));
        }
        catch { }
    }

    /// <summary>Поллим бэкенд дрона, пока не ответит (или таймаут).</summary>
    private static async Task<DroneApi.WifiStatus?> WaitForBackendAsync(DroneApi api, double timeoutSeconds = 25)
    {
        var deadline = DateTime.UtcNow.AddSeconds(timeoutSeconds);
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                return await api.WifiStatusAsync();
            }
            catch { }
            await Task.Delay(1000);
        }
        return null;
    }

    /// <summary>
    /// Ждём настроенный дрон по DNS-SD и возвращаем его IP. С id (текущее ПО
    /// дрона) подходит только этот самый дрон — никогда не дрон соседней
    /// команды. Без id (старое ПО: нет id ни в статусе, ни в TXT) берём первый
    /// дрон без id, как раньше.
    /// </summary>
    private static async Task<string?> WaitForDroneAsync(string? expectedId, double timeoutSeconds = 60)
    {
        var tcs = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var browser = new DnssdBrowser((ip, _, id) =>
        {
            // Адрес хотспота — устаревшая запись дрона до переключения.
            if (ip == HotspotGatewayHost) return;
            if (id == expectedId) tcs.TrySetResult(ip);
        });
        browser.Start();
        var done = await Task.WhenAny(tcs.Task, Task.Delay(TimeSpan.FromSeconds(timeoutSeconds)));
        return done == tcs.Task ? tcs.Task.Result : null;
    }

    /// <summary>Профиль WPA2-PSK для временного подключения к хотспоту.</summary>
    internal static string Wpa2PskProfileXml(string ssid, string psk)
    {
        var name = SecurityElement.Escape(ssid);
        var key = SecurityElement.Escape(psk);
        return $"""
            <?xml version="1.0"?>
            <WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
                <name>{name}</name>
                <SSIDConfig><SSID><name>{name}</name></SSID></SSIDConfig>
                <connectionType>ESS</connectionType>
                <connectionMode>manual</connectionMode>
                <MSM>
                    <security>
                        <authEncryption>
                            <authentication>WPA2PSK</authentication>
                            <encryption>AES</encryption>
                            <useOneX>false</useOneX>
                        </authEncryption>
                        <sharedKey>
                            <keyType>passPhrase</keyType>
                            <protected>false</protected>
                            <keyMaterial>{key}</keyMaterial>
                        </sharedKey>
                    </security>
                </MSM>
            </WLANProfile>
            """;
    }
}
