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

using Microsoft.UI;
using BumblebeeGcs.Controls;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Windows.UI;

namespace BumblebeeGcs.Views;

/// <summary>
/// Экран подключения — единая панель. Дроны в сети появляются сами по имени через
/// DNS-SD, хотспоты дронов рядом — каждые ~12 с; выключенные дроны сереют и уходят.
/// Последний дрон находится по id. Ручной адрес проверяется: дрон должен ответить,
/// прежде чем открыть дашборд. Все действия — настоящие кнопки (Tab, Enter, диктор).
/// Порт LaunchView.swift; решения — в Logic/DiscoveryLogic.cs.
/// </summary>
public sealed class LaunchView : Grid
{
    private readonly AppState _app;

    private readonly StackPanel _bannerSlot = new() { Spacing = 10 };
    private readonly StackPanel _lastSlot = new() { Spacing = 0 };
    private readonly StackPanel _dronesList = new() { Spacing = 9 };
    private readonly ProgressRing _scanSpinner = new() { Width = 14, Height = 14, IsActive = true, Visibility = Visibility.Collapsed };
    private readonly TextBox _manualIp;
    private readonly Button _connectBtn;
    private readonly ProgressRing _manualRing = new() { Width = 14, Height = 14, IsActive = true, Visibility = Visibility.Collapsed };
    private readonly StackPanel _manualNote = new() { Spacing = 4 };

    private bool _lastPingOk;
    private bool _setupOpen;
    private bool _checkingManual;
    private readonly Action _onChanged;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _hotspotTimer, _lastTimer;

    private static readonly FontSpec Small = new(11.5, new Windows.UI.Text.FontWeight(400), Mono: true);

    public LaunchView(AppState app)
    {
        _app = app;
        Background = ConnectPalette.Background();
        var dq = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();

        // MARK: Header
        var title = new TextBlock
        {
            FontSize = 26,
            FontWeight = new Windows.UI.Text.FontWeight(700),
            FontFamily = Fonts.UiFamily,
            CharacterSpacing = -12,
            HorizontalAlignment = HorizontalAlignment.Center,
        };
        title.Inlines.Add(new Run { Text = "Bumblebee ", Foreground = Palette.Brush(ConnectPalette.Text) });
        title.Inlines.Add(new Run { Text = "GCS", Foreground = Palette.Brush(ConnectPalette.Orange) });
        var subtitle = Ui.Text("Select a drone to connect", Fonts.BodyMed with { Mono = true }, ConnectPalette.Muted);
        subtitle.HorizontalAlignment = HorizontalAlignment.Center;
        var version = Ui.Text(AppVersion.Label, Fonts.Label with { Mono = true }, ConnectPalette.Muted);
        version.HorizontalAlignment = HorizontalAlignment.Center;
        var logo = Ui.AppLogo(64, 16);
        logo.HorizontalAlignment = HorizontalAlignment.Center;
        var header = Ui.VStack(14, logo, Ui.VStack(6, title, subtitle, version));

        // MARK: Drones panel header: title, spinner, Add drone, Rescan
        var panelHeader = new Grid { ColumnSpacing = 8 };
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var panelTitle = Ui.Text("AVAILABLE DRONES", Fonts.Label with { Mono = true }, ConnectPalette.Faint, tracking: 1.4);
        panelTitle.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(panelTitle, 0);
        Grid.SetColumn(_scanSpinner, 1);
        var addBtn = Ui.FlatButton(
            Ui.HStack(5, Ui.Icon(IconGlyphs.Add, 11, ConnectPalette.Orange), Ui.Text("Add drone", Fonts.ButtonSm, ConnectPalette.Orange)),
            () => OpenSetup(), "Add drone", Colors.Transparent, Palette.WithAlpha(ConnectPalette.Orange, 0.12),
            ConnectPalette.Orange, padding: new Thickness(6, 3, 6, 3));
        ToolTipService.SetToolTip(addBtn, "Set up a new drone so it joins this PC's WiFi");
        Grid.SetColumn(addBtn, 3);
        var rescanBtn = Ui.FlatButton(Ui.Icon(IconGlyphs.Refresh, 12, ConnectPalette.BlueSoft), () =>
        {
            _app.Scanner.Scan();
            _ = _app.Handoff.ScanHotspotsAsync();
        }, "Rescan the network", Colors.Transparent, Palette.WithAlpha(ConnectPalette.Blue, 0.15),
            ConnectPalette.BlueSoft, padding: new Thickness(4));
        ToolTipService.SetToolTip(rescanBtn, "Rescan the network");
        Grid.SetColumn(rescanBtn, 4);
        panelHeader.Children.Add(panelTitle);
        panelHeader.Children.Add(_scanSpinner);
        panelHeader.Children.Add(addBtn);
        panelHeader.Children.Add(rescanBtn);
        panelHeader.Margin = new Thickness(0, 0, 0, 10);

        var dronesPanel = Ui.VStack(0, panelHeader, _dronesList);

        // MARK: Footer — manual address
        _manualIp = new TextBox
        {
            PlaceholderText = "172.20.10.4",
            FontSize = 14,
            FontFamily = Fonts.MonoFamily,
            Foreground = Palette.Brush(ConnectPalette.Text),
            BorderThickness = new Thickness(0),
            Padding = new Thickness(0),
            MinHeight = 0,
            VerticalAlignment = VerticalAlignment.Center,
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(_manualIp, "Drone address");
        foreach (var state in new[] { "", "PointerOver", "Focused" })
        {
            _manualIp.Resources[$"TextControlBackground{state}"] = Palette.Brush(Colors.Transparent);
            _manualIp.Resources[$"TextControlBorderBrush{state}"] = Palette.Brush(Colors.Transparent);
        }
        _manualIp.Resources["TextControlForegroundFocused"] = Palette.Brush(ConnectPalette.Text);
        _manualIp.Resources["TextControlForegroundPointerOver"] = Palette.Brush(ConnectPalette.Text);
        _manualIp.Resources["TextControlPlaceholderForeground"] = Palette.Brush(ConnectPalette.Faint);
        _manualIp.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) ConnectManual(); };
        _manualIp.TextChanged += (_, _) => { _manualNote.Children.Clear(); _connectBtn!.IsEnabled = CanConnectManual; };

        _connectBtn = Ui.FlatButton(Ui.Text("Connect", Fonts.Button, Colors.White), ConnectManual, "Connect to this address",
            ConnectPalette.Blue, ConnectPalette.BlueHover, Colors.White, padding: new Thickness(18, 9, 18, 9));
        _connectBtn.IsEnabled = false;

        var footerRow = new Grid { ColumnSpacing = 10 };
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var ipLabel = Ui.Text("IP", Fonts.Label with { Mono = true }, ConnectPalette.Faint, tracking: 1.3);
        ipLabel.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(ipLabel, 0);
        Grid.SetColumn(_manualIp, 1);
        Grid.SetColumn(_manualRing, 2);
        Grid.SetColumn(_connectBtn, 3);
        footerRow.Children.Add(ipLabel);
        footerRow.Children.Add(_manualIp);
        footerRow.Children.Add(_manualRing);
        footerRow.Children.Add(_connectBtn);

        var footer = Ui.VStack(6, new Border
        {
            Background = Palette.Brush(ConnectPalette.RowBg),
            BorderBrush = Palette.Brush(ConnectPalette.Hairline),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(12),
            Padding = new Thickness(16, 10, 6, 10),
            Child = footerRow,
        }, _manualNote);

        var content = Ui.VStack(18, header, _bannerSlot, _lastSlot, dronesPanel, footer);
        content.HorizontalAlignment = HorizontalAlignment.Center;
        content.VerticalAlignment = VerticalAlignment.Center;
        content.Width = 560;

        var scroll = new ScrollViewer
        {
            Content = new Grid { Padding = new Thickness(24), Children = { content } },
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        Children.Add(scroll);

        // New drone hotspots show up by themselves: a WiFi scan every 12 s while this screen is
        // shown and no setup runs. The last drone's dot is re-checked every 10 s.
        _hotspotTimer = dq.CreateTimer();
        _hotspotTimer.Interval = TimeSpan.FromSeconds(12);
        _hotspotTimer.Tick += (_, _) => { if (!_setupOpen && !_app.Handoff.IsBusy) _ = _app.Handoff.ScanHotspotsAsync(); };
        _lastTimer = dq.CreateTimer();
        _lastTimer.Interval = TimeSpan.FromSeconds(LivenessRule.PeriodSeconds);
        _lastTimer.Tick += (_, _) => _ = PingLastAsync();

        _onChanged = () => dq.TryEnqueue(Rebuild);
        _app.Scanner.Changed += _onChanged;
        _app.Handoff.Changed += _onChanged;
        _app.FleetChanged += _onChanged;
        Unloaded += (_, _) =>
        {
            _app.Scanner.Changed -= _onChanged;
            _app.Handoff.Changed -= _onChanged;
            _app.FleetChanged -= _onChanged;
            _hotspotTimer.Stop();
            _lastTimer.Stop();
        };
        Loaded += (_, _) =>
        {
            Rebuild();
            _ = _app.Handoff.ScanHotspotsAsync(); // хотспоты дронов в общий список
            _ = PingLastAsync();
            _hotspotTimer.Start();
            _lastTimer.Start();
        };
    }

    private async Task PingLastAsync()
    {
        if (_app.LastDrone is not KnownDrone last) return;
        var ip = KnownFleet.CurrentIp(last, _app.Scanner.FoundIds);
        var ok = await DroneScanner.IsReachableAsync(ip);
        if (ok != _lastPingOk) { _lastPingOk = ok; Rebuild(); }
    }

    // MARK: - Manual address

    private bool CanConnectManual => !string.IsNullOrWhiteSpace(_manualIp.Text) && !_checkingManual;

    /// <summary>A typed address goes to the dashboard only when something answers on :9090 there
    /// (else a message and "Connect anyway"): a typo never becomes the remembered drone.</summary>
    private async void ConnectManual()
    {
        var ip = _manualIp.Text.Trim();
        if (ip.Length == 0 || _checkingManual) return;
        _manualNote.Children.Clear();
        if (ManualAddress.Problem(ip) is string problem)
        {
            _manualNote.Children.Add(Note(problem));
            return;
        }
        _checkingManual = true;
        _manualRing.Visibility = Visibility.Visible;
        _connectBtn.IsEnabled = false;
        var open = await DroneScanner.IsReachableAsync(ip, 1.5);
        _checkingManual = false;
        _manualRing.Visibility = Visibility.Collapsed;
        _connectBtn.IsEnabled = CanConnectManual;
        if (open) { _app.Connect(ip); return; }
        var anyway = Ui.FlatButton(Ui.Text("Connect anyway", Fonts.ButtonSm, ConnectPalette.BlueSoft), () => _app.Connect(ip),
            "Connect anyway", Colors.Transparent, Palette.WithAlpha(ConnectPalette.Blue, 0.12), ConnectPalette.BlueSoft,
            padding: new Thickness(6, 3, 6, 3));
        _manualNote.Children.Add(Ui.SpaceBetween(Note(ManualAddress.NoAnswer(ip)), anyway));
    }

    private static TextBlock Note(string text)
    {
        var t = Ui.Text(text, Small, ConnectPalette.Orange);
        t.TextWrapping = TextWrapping.Wrap;
        return t;
    }

    // MARK: - Rebuild

    private void Rebuild()
    {
        _scanSpinner.Visibility = _app.Scanner.Scanning ? Visibility.Visible : Visibility.Collapsed;
        RebuildBanners();

        _lastSlot.Children.Clear();
        if (_app.LastDrone is KnownDrone last)
        {
            var ip = KnownFleet.CurrentIp(last, _app.Scanner.FoundIds);
            var reachable = (last.Verified && _app.Scanner.VisibleIds.Contains(last.DroneId)) || _lastPingOk;
            _lastSlot.Children.Add(LastDroneCard(last, ip, reachable));
        }

        _dronesList.Children.Clear();
        var scanner = _app.Scanner;
        var drones = scanner.Drones.ToList();
        var unknown = scanner.UnknownDevices.ToList();
        var visible = scanner.VisibleIds;
        var hotspots = _app.Handoff.Hotspots
            .Select(h => (Hotspot: h, Row: Logic.HotspotRow.Of(h.Ssid, _app.KnownDrones, visible)))
            .Where(x => x.Row.Kind != HotspotKind.Hidden)
            .ToList();
        if (drones.Count > 0 || hotspots.Count > 0 || unknown.Count > 0)
        {
            foreach (var d in drones) _dronesList.Children.Add(DiscoveredRow(d));
            // Дроны, доступные только через собственный хотспот (вне этой сети).
            foreach (var (h, row) in hotspots) _dronesList.Children.Add(HotspotRowView(h, row));
            foreach (var d in unknown) _dronesList.Children.Add(UnknownDeviceRow(d));
        }
        else
        {
            var titleTxt = scanner.Scanning || !scanner.HasScanned ? "Looking for drones…" : "No drones found";
            var t1 = Ui.Text(titleTxt, Fonts.BodyStrong, ConnectPalette.Text);
            t1.HorizontalAlignment = HorizontalAlignment.Center;
            var t2 = Ui.Text("Drones on this WiFi appear here by themselves. A new drone shows up about 30 s after power-on — then press Add.",
                Small, ConnectPalette.Muted);
            t2.TextWrapping = TextWrapping.Wrap;
            t2.TextAlignment = TextAlignment.Center;
            t2.HorizontalAlignment = HorizontalAlignment.Center;
            var empty = Ui.VStack(6, t1, t2);
            empty.Padding = new Thickness(15, 22, 15, 22);
            _dronesList.Children.Add(empty);
        }
    }

    /// <summary>Location off (WiFi names hidden), no WiFi adapter, a direct connection under way
    /// or failed, or this PC sitting on a drone's hotspot.</summary>
    private void RebuildBanners()
    {
        _bannerSlot.Children.Clear();
        var h = _app.Handoff;
        if (h.Phase == WifiHandoff.PhaseKind.NeedLocationPermission)
        {
            var open = Ui.FlatButton(Ui.Text("Open Settings", Fonts.ButtonSm, ConnectPalette.Orange),
                () => _ = Windows.System.Launcher.LaunchUriAsync(new Uri("ms-settings:privacy-location")),
                "Open location settings", Colors.Transparent, Palette.WithAlpha(ConnectPalette.Orange, 0.12),
                ConnectPalette.Orange, padding: new Thickness(6, 3, 6, 3));
            _bannerSlot.Children.Add(Banner("Allow Location to see new drones",
                "Windows shows WiFi names only to apps with Location on (Settings → Privacy & security → Location). Drones already on your WiFi are listed anyway.",
                open));
        }
        else if (h.Phase == WifiHandoff.PhaseKind.Failed && h.LastFailure?.Title == "This PC has no WiFi" && !_setupOpen)
        {
            _bannerSlot.Children.Add(Banner("This PC has no WiFi",
                "New drones cannot be added from this PC (that needs WiFi). Drones on its network are listed anyway.", null));
        }
        if (h.Phase == WifiHandoff.PhaseKind.JoiningHotspot && !_setupOpen)
            _bannerSlot.Children.Add(Note($"Joining {h.PhaseArg}… this PC leaves its WiFi meanwhile."));
        if (h.Phase == WifiHandoff.PhaseKind.Failed && h.LastFailure is { Kind: WifiHandoff.FailureKind.DroneSilent } f && !_setupOpen)
            _bannerSlot.Children.Add(Note($"{f.Title}. {f.Detail}"));
        if (h.OnDroneHotspot && _app.DroneHost != WifiHandoff.HotspotGatewayHost)
            _bannerSlot.Children.Add(Banner($"This PC is on {h.CurrentSsid}, a drone's own WiFi",
                "Pick your classroom WiFi in the taskbar to see the drones on it.", null));
    }

    private static UIElement Banner(string title, string detail, UIElement? action)
    {
        var text = Ui.VStack(2, Ui.Text(title, Fonts.BodyStrong, ConnectPalette.Text), Wrap(Ui.Text(detail, Small, ConnectPalette.Muted2)));
        UIElement content = action is null ? text : Ui.SpaceBetween(text, action);
        return new Border
        {
            Background = Palette.Brush(Palette.WithAlpha(ConnectPalette.Orange, 0.07)),
            BorderBrush = Palette.Brush(Palette.WithAlpha(ConnectPalette.Orange, 0.4)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(12),
            Padding = new Thickness(14, 10, 14, 10),
            Child = content,
        };
    }

    private static TextBlock Wrap(TextBlock t) { t.TextWrapping = TextWrapping.Wrap; return t; }

    private static Microsoft.UI.Xaml.Shapes.Ellipse DotEl(Color color, double size = 8) => new()
    {
        Width = size,
        Height = size,
        Fill = Palette.Brush(color),
        VerticalAlignment = VerticalAlignment.Center,
    };

    // MARK: - Last drone (hero action)

    private UIElement LastDroneCard(KnownDrone drone, string ip, bool reachable)
    {
        var name = drone.Name == ip ? "Last drone" : drone.Name;
        var detail = $"{ip} · {(reachable ? "last connection" : "not answering")}" + (drone.Verified ? "" : " · unverified");
        var left = Ui.HStack(14,
            DotEl(reachable ? ConnectPalette.Green : ConnectPalette.Faint, 10),
            Ui.VStack(4,
                Ui.Text(name, new FontSpec(16, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
                Ui.Text(detail, Fonts.BodyMed with { Mono = true }, ConnectPalette.Muted2)));
        var right = Ui.HStack(7,
            Ui.Text("Connect", new FontSpec(14, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Orange),
            Ui.Text("→", new FontSpec(14, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Orange));
        var inner = Ui.SpaceBetween(left, right, 8);
        inner.Margin = new Thickness(20, 16, 12, 16);
        var connect = Ui.FlatButton(inner, () => _app.Connect(ip, drone.Verified ? drone.DroneId : null),
            $"Connect to {name}", Colors.Transparent, Palette.WithAlpha(ConnectPalette.Orange, 0.06), ConnectPalette.Text,
            radius: 14);

        var forget = Ui.FlatButton(Ui.Text("Forget", Fonts.Label with { Mono = true }, ConnectPalette.Faint),
            () => _app.Forget(drone), $"Forget {name}", Colors.Transparent, Palette.WithAlpha(Colors.White, 0.06),
            ConnectPalette.Faint, padding: new Thickness(8, 4, 8, 4));
        ToolTipService.SetToolTip(forget, "Remove this drone from the remembered list");
        forget.VerticalAlignment = VerticalAlignment.Center;
        forget.Margin = new Thickness(0, 0, 12, 0);

        var row = new Grid();
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn(forget, 1);
        row.Children.Add(connect);
        row.Children.Add(forget);

        var grad = new Microsoft.UI.Xaml.Media.LinearGradientBrush
        {
            StartPoint = new Windows.Foundation.Point(0, 0.5),
            EndPoint = new Windows.Foundation.Point(1, 0.5),
            GradientStops =
            {
                new Microsoft.UI.Xaml.Media.GradientStop { Color = Palette.WithAlpha(ConnectPalette.Orange, 0.12), Offset = 0 },
                new Microsoft.UI.Xaml.Media.GradientStop { Color = Palette.WithAlpha(ConnectPalette.Orange, 0.02), Offset = 1 },
            },
        };
        return new Border
        {
            Background = grad,
            BorderBrush = Palette.Brush(Palette.WithAlpha(ConnectPalette.Orange, 0.4)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(14),
            Child = row,
        };
    }

    // MARK: - Discovered drone row

    private UIElement DiscoveredRow(DroneScanner.Drone drone)
    {
        var name = drone.Name == drone.Ip ? "Drone" : drone.Name;
        var parts = new List<string> { drone.Ip, drone.DroneId is string id ? $"id {id}" : "id unknown" };
        if (drone.Liveness == Liveness.Unsure) parts.Add("not answering");
        var live = drone.Liveness == Liveness.Live;
        var left = Ui.HStack(14,
            DotEl(live ? ConnectPalette.Green : ConnectPalette.Faint),
            Ui.VStack(3,
                Ui.Text(name, new FontSpec(14.5, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
                Ui.Text(string.Join(" · ", parts), Small, ConnectPalette.Muted2)));

        var btn = Ui.FlatButton(Ui.Text("Connect", Fonts.Button, ConnectPalette.BlueSoft), () => _app.Connect(drone.Ip, drone.DroneId),
            $"Connect to {name}", Palette.WithAlpha(ConnectPalette.Blue, 0.1), ConnectPalette.Blue, ConnectPalette.BlueSoft,
            Palette.WithAlpha(ConnectPalette.Blue, 0.5), new Thickness(16, 9, 16, 9), 9);

        var content = Ui.SpaceBetween(left, btn, 8);
        content.Margin = new Thickness(15, 13, 15, 13);
        var row = new HoverRow(content, 12,
            ConnectPalette.RowBg, Palette.WithAlpha(ConnectPalette.Blue, 0.05),
            ConnectPalette.Hairline, Palette.WithAlpha(ConnectPalette.Blue, 0.45));
        row.Opacity = live ? 1 : 0.6;
        return row;
    }

    // MARK: - A host with port 9090 open that does not answer like a drone

    private UIElement UnknownDeviceRow(DroneScanner.Drone device)
    {
        var anyway = Ui.FlatButton(Ui.Text("Connect anyway", Fonts.Label, ConnectPalette.Muted2), () => _app.Connect(device.Ip),
            $"Connect anyway to {device.Ip}", Colors.Transparent, Palette.WithAlpha(Colors.White, 0.06), ConnectPalette.Muted2,
            padding: new Thickness(6, 3, 6, 3));
        var row = Ui.SpaceBetween(
            Ui.HStack(10, DotEl(ConnectPalette.Faint, 6),
                Ui.Text($"Unknown device · {device.Ip} · port 9090 open, not a drone", Small, ConnectPalette.Faint)),
            anyway);
        row.Margin = new Thickness(15, 4, 15, 4);
        return row;
    }

    // MARK: - Drone-hotspot row (new drone, or a known one that lost its WiFi)

    private UIElement HotspotRowView(WifiHandoff.Hotspot hotspot, Logic.HotspotRow kind)
    {
        var lost = kind.Kind == HotspotKind.LostWifi;
        var icon = Ui.Icon(IconGlyphs.Antenna, 13, ConnectPalette.Orange);
        icon.Width = 12;
        var left = Ui.HStack(14,
            icon,
            Ui.VStack(3,
                Ui.Text(lost ? kind.Name! : hotspot.Ssid, new FontSpec(14.5, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
                Ui.Text(lost ? $"lost its WiFi · running its own hotspot {hotspot.Ssid}" : "new drone · not on your WiFi yet",
                    Small, ConnectPalette.Muted2)));

        var direct = Ui.FlatButton(Ui.Text("Direct", Fonts.ButtonSm, ConnectPalette.BlueSoft), () => ConnectDirect(hotspot.Ssid),
            $"Connect directly to {hotspot.Ssid}", Colors.Transparent, Palette.WithAlpha(ConnectPalette.Blue, 0.12),
            ConnectPalette.BlueSoft, padding: new Thickness(8, 4, 8, 4));
        ToolTipService.SetToolTip(direct, "Join this drone's own WiFi. The PC has no internet while connected directly.");
        var setup = Ui.FlatButton(
            Ui.HStack(6, Ui.Text(lost ? "Bring back" : "Add", Fonts.Button, ConnectPalette.Orange),
                Ui.Text("→", new FontSpec(13, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Orange)),
            () => OpenSetup(hotspot.Ssid), (lost ? "Bring back " : "Add ") + hotspot.Ssid,
            Colors.Transparent, Palette.WithAlpha(ConnectPalette.Orange, 0.12), ConnectPalette.Orange,
            padding: new Thickness(8, 4, 8, 4));
        var right = Ui.HStack(10,
            Ui.Text($"{hotspot.Rssi} dBm", Fonts.Label with { Mono = true }, ConnectPalette.Faint), direct, setup);
        right.VerticalAlignment = VerticalAlignment.Center;

        var content = Ui.SpaceBetween(left, right, 8);
        content.Margin = new Thickness(15, 11, 15, 11);
        return new HoverRow(content, 12,
            ConnectPalette.RowBg, Palette.WithAlpha(ConnectPalette.Orange, 0.06),
            ConnectPalette.Hairline, Palette.WithAlpha(ConnectPalette.Orange, 0.5));
    }

    /// <summary>Work with a drone over its own hotspot (no shared WiFi needed); its id must be the
    /// one in the hotspot's name.</summary>
    private void ConnectDirect(string ssid)
    {
        var expected = Logic.HotspotRow.IdOf(ssid);
        _ = _app.Handoff.ConnectDirectAsync(ssid,
            host => DispatcherQueue.TryEnqueue(() => _app.Connect(host, expected)));
    }

    /// <summary>Окно «Добавить дрон»; с preselected — сразу этот дрон.</summary>
    private async void OpenSetup(string? preselected = null)
    {
        _setupOpen = true;
        var dlg = new ProvisioningDialog(_app, preselected) { XamlRoot = XamlRoot };
        try { await dlg.ShowAsync(); } catch { }
        _setupOpen = false;
        Rebuild();
    }
}
