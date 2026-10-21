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
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Windows.UI;

namespace BumblebeeGcs.Views;

/// <summary>
/// Экран подключения — единая панель. Дроны появляются сами по имени через
/// DNS-SD (без ручного «скана»); футер объединяет два фолбэка — ручной IP и
/// настройку нового дрона через его хотспот. Порт LaunchView.swift.
/// </summary>
public sealed class LaunchView : Grid
{
    private readonly AppState _app;

    private readonly StackPanel _lastSlot = new() { Spacing = 0 };
    private readonly StackPanel _dronesList = new() { Spacing = 9 };
    private readonly ProgressRing _scanSpinner = new() { Width = 14, Height = 14, IsActive = true, Visibility = Visibility.Collapsed };
    private readonly TextBox _manualIp;
    private readonly Border _connectBtn;
    private readonly TextBlock _connectBtnText;

    private bool _lastPingOk;
    private readonly Action _onChanged;

    public LaunchView(AppState app)
    {
        _app = app;
        Background = ConnectPalette.Background();

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
        var logo = Ui.AppLogo(72, 18);
        logo.HorizontalAlignment = HorizontalAlignment.Center;
        var header = Ui.VStack(16, logo, Ui.VStack(7, title, subtitle, version));

        // MARK: Drones panel
        var panelHeader = new Grid { ColumnSpacing = 8 };
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        panelHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var panelTitle = Ui.Text("AVAILABLE DRONES", Fonts.Label with { Mono = true }, ConnectPalette.Faint, tracking: 1.4);
        Grid.SetColumn(panelTitle, 0);
        Grid.SetColumn(_scanSpinner, 1);
        var rescan = Ui.Icon(IconGlyphs.Refresh, 12, ConnectPalette.BlueSoft);
        var rescanBtn = new Button
        {
            Content = rescan,
            Padding = new Thickness(4),
            BorderThickness = new Thickness(0),
            Background = Palette.Brush(Colors.Transparent),
        };
        rescanBtn.Resources["ButtonBackground"] = Palette.Brush(Colors.Transparent);
        rescanBtn.Resources["ButtonBackgroundPointerOver"] = Palette.Brush(Palette.WithAlpha(ConnectPalette.Blue, 0.15));
        rescanBtn.Resources["ButtonBackgroundPressed"] = Palette.Brush(Palette.WithAlpha(ConnectPalette.Blue, 0.25));
        ToolTipService.SetToolTip(rescanBtn, "Rescan the network");
        rescanBtn.Click += (_, _) =>
        {
            _app.Scanner.Scan();
            _ = _app.Handoff.ScanHotspotsAsync();
        };
        Grid.SetColumn(rescanBtn, 3);
        panelHeader.Children.Add(panelTitle);
        panelHeader.Children.Add(_scanSpinner);
        panelHeader.Children.Add(rescanBtn);
        panelHeader.Margin = new Thickness(0, 0, 0, 10);

        var dronesPanel = Ui.VStack(0, panelHeader, _dronesList);

        // MARK: Footer — manual IP
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
        foreach (var state in new[] { "", "PointerOver", "Focused" })
        {
            _manualIp.Resources[$"TextControlBackground{state}"] = Palette.Brush(Colors.Transparent);
            _manualIp.Resources[$"TextControlBorderBrush{state}"] = Palette.Brush(Colors.Transparent);
        }
        _manualIp.Resources["TextControlForegroundFocused"] = Palette.Brush(ConnectPalette.Text);
        _manualIp.Resources["TextControlForegroundPointerOver"] = Palette.Brush(ConnectPalette.Text);
        _manualIp.Resources["TextControlPlaceholderForeground"] = Palette.Brush(ConnectPalette.Faint);
        _manualIp.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) ConnectManual(); };
        _manualIp.TextChanged += (_, _) => UpdateConnectBtn();

        _connectBtnText = Ui.Text("Connect", Fonts.Button, ConnectPalette.Faint);
        _connectBtn = new Border
        {
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(18, 9, 18, 9),
            Child = _connectBtnText,
            Background = Palette.Brush(Palette.WithAlpha(Colors.White, 0.06)),
        };
        Ui.OnTap(_connectBtn, ConnectManual);
        Ui.OnHover(_connectBtn, h =>
        {
            if (string.IsNullOrWhiteSpace(_manualIp.Text)) return;
            _connectBtn.Background = Palette.Brush(h ? ConnectPalette.BlueHover : ConnectPalette.Blue);
        });

        var footerRow = new Grid { ColumnSpacing = 10 };
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        footerRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var ipLabel = Ui.Text("IP", Fonts.Label with { Mono = true }, ConnectPalette.Faint, tracking: 1.3);
        Grid.SetColumn(ipLabel, 0);
        Grid.SetColumn(_manualIp, 1);
        Grid.SetColumn(_connectBtn, 2);
        footerRow.Children.Add(ipLabel);
        footerRow.Children.Add(_manualIp);
        footerRow.Children.Add(_connectBtn);

        var footer = new Border
        {
            Background = Palette.Brush(ConnectPalette.RowBg),
            BorderBrush = Palette.Brush(ConnectPalette.Hairline),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(12),
            Padding = new Thickness(16, 10, 6, 10),
            Child = footerRow,
        };

        var content = Ui.VStack(22, header, _lastSlot, dronesPanel, footer);
        content.MaxWidth = 560;
        content.HorizontalAlignment = HorizontalAlignment.Stretch;
        content.VerticalAlignment = VerticalAlignment.Center;

        var scroll = new ScrollViewer
        {
            Content = new Grid
            {
                Padding = new Thickness(24, 24, 24, 24),
                Children = { content },
            },
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        ((Grid)scroll.Content).MinHeight = 0;
        content.HorizontalAlignment = HorizontalAlignment.Center;
        content.Width = 560;
        Children.Add(scroll);

        _onChanged = Rebuild;
        _app.Scanner.Changed += _onChanged;
        _app.Handoff.Changed += _onChanged;
        Unloaded += (_, _) =>
        {
            _app.Scanner.Changed -= _onChanged;
            _app.Handoff.Changed -= _onChanged;
        };
        Loaded += async (_, _) =>
        {
            Rebuild();
            _ = _app.Handoff.ScanHotspotsAsync(); // хотспоты дронов в общий список
            if (_app.LastHost is string last)
            {
                _lastPingOk = false;
                _lastPingOk = await DroneScanner.IsReachableAsync(last);
                Rebuild();
            }
        };
    }

    private void UpdateConnectBtn()
    {
        var empty = string.IsNullOrWhiteSpace(_manualIp.Text);
        _connectBtn.Background = Palette.Brush(empty ? Palette.WithAlpha(Colors.White, 0.06) : ConnectPalette.Blue);
        _connectBtnText.Foreground = Palette.Brush(empty ? ConnectPalette.Faint : Colors.White);
    }

    private void ConnectManual()
    {
        var ip = _manualIp.Text.Trim();
        if (ip.Length == 0) return;
        _app.Connect(ip);
    }

    // MARK: - Rebuild lists

    private void Rebuild()
    {
        _scanSpinner.Visibility = _app.Scanner.Scanning ? Visibility.Visible : Visibility.Collapsed;

        _lastSlot.Children.Clear();
        if (_app.LastHost is string last)
        {
            var reachable = _app.Scanner.Found.Any(d => d.Ip == last) || _lastPingOk;
            _lastSlot.Children.Add(LastDroneCard(last, reachable));
        }

        _dronesList.Children.Clear();
        var scanner = _app.Scanner;
        var hotspots = _app.Handoff.Hotspots;
        if (scanner.Found.Count > 0 || hotspots.Count > 0)
        {
            foreach (var d in scanner.Found)
                _dronesList.Children.Add(DiscoveredRow(d));
            // Дроны, доступные только через собственный setup-хотспот (вне этой сети).
            foreach (var h in hotspots)
                _dronesList.Children.Add(HotspotRow(h));
        }
        else
        {
            var titleTxt = scanner.Scanning || !scanner.HasScanned ? "Looking for drones…" : "No drones found";
            var t1 = Ui.Text(titleTxt, Fonts.BodyStrong, ConnectPalette.Text);
            t1.HorizontalAlignment = HorizontalAlignment.Center;
            var t2 = Ui.Text("Drones on this WiFi appear here automatically. Or use the options below.",
                new FontSpec(11.5, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Muted);
            t2.TextWrapping = TextWrapping.Wrap;
            t2.TextAlignment = TextAlignment.Center;
            t2.HorizontalAlignment = HorizontalAlignment.Center;
            var empty = Ui.VStack(6, t1, t2);
            empty.Padding = new Thickness(15, 22, 15, 22);
            _dronesList.Children.Add(empty);
        }
    }

    private static Windows.UI.Color Dot => ConnectPalette.Green;

    private static Microsoft.UI.Xaml.Shapes.Ellipse DotEl(Windows.UI.Color color, double size = 8) => new()
    {
        Width = size,
        Height = size,
        Fill = Palette.Brush(color),
        VerticalAlignment = VerticalAlignment.Center,
    };

    // MARK: - Last drone (hero action)

    private UIElement LastDroneCard(string ip, bool reachable)
    {
        var left = Ui.HStack(14,
            DotEl(reachable ? ConnectPalette.Green : ConnectPalette.Faint, 10),
            Ui.VStack(4,
                Ui.Text("Last drone", new FontSpec(16, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
                Ui.Text($"{ip} · last connection", Fonts.BodyMed with { Mono = true }, ConnectPalette.Muted2)));
        var right = Ui.HStack(7,
            Ui.Text("Connect", new FontSpec(14, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Orange),
            Ui.Text("→", new FontSpec(14, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Orange));

        var content = Ui.SpaceBetween(left, right, 8);
        content.Margin = new Thickness(20, 18, 20, 18);

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
        var row = new Border
        {
            Background = grad,
            BorderBrush = Palette.Brush(Palette.WithAlpha(ConnectPalette.Orange, 0.4)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(14),
            Child = content,
        };
        Ui.OnHover(row, h => row.BorderBrush = Palette.Brush(Palette.WithAlpha(ConnectPalette.Orange, h ? 0.7 : 0.4)));
        Ui.OnTap(row, () => _app.Connect(ip));
        return row;
    }

    // MARK: - Discovered drone row

    private UIElement DiscoveredRow(DroneScanner.Drone drone)
    {
        var name = drone.Name == drone.Ip ? "Drone" : drone.Name;
        var left = Ui.HStack(14,
            DotEl(ConnectPalette.Green),
            Ui.VStack(3,
                Ui.Text(name, new FontSpec(14.5, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
                Ui.Text($"{drone.Ip} · rosbridge :9090", new FontSpec(11.5, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Muted2)));

        var btnText = Ui.Text("Connect", Fonts.Button, ConnectPalette.BlueSoft);
        var btn = new Border
        {
            Background = Palette.Brush(Palette.WithAlpha(ConnectPalette.Blue, 0.1)),
            BorderBrush = Palette.Brush(Palette.WithAlpha(ConnectPalette.Blue, 0.5)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(9),
            Padding = new Thickness(16, 9, 16, 9),
            Child = btnText,
        };
        Ui.OnHover(btn, h =>
        {
            btn.Background = Palette.Brush(h ? ConnectPalette.Blue : Palette.WithAlpha(ConnectPalette.Blue, 0.1));
            btn.BorderBrush = Palette.Brush(h ? ConnectPalette.Blue : Palette.WithAlpha(ConnectPalette.Blue, 0.5));
            btnText.Foreground = Palette.Brush(h ? Colors.White : ConnectPalette.BlueSoft);
        });
        Ui.OnTap(btn, () => _app.Connect(drone.Ip));

        var content = Ui.SpaceBetween(left, btn, 8);
        content.Margin = new Thickness(15, 13, 15, 13);
        return new HoverRow(content, 12,
            ConnectPalette.RowBg, Palette.WithAlpha(ConnectPalette.Blue, 0.05),
            ConnectPalette.Hairline, Palette.WithAlpha(ConnectPalette.Blue, 0.45));
    }

    // MARK: - Drone-hotspot row (нужна настройка)

    private UIElement HotspotRow(WifiHandoff.Hotspot hotspot)
    {
        var icon = Ui.Icon(IconGlyphs.Antenna, 13, ConnectPalette.Orange);
        icon.Width = 12;
        var left = Ui.HStack(14,
            icon,
            Ui.VStack(3,
                Ui.Text(hotspot.Ssid, new FontSpec(14.5, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
                Ui.Text("new drone · tap to add", new FontSpec(11.5, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Muted2)));

        var right = Ui.HStack(10,
            Ui.Text($"{hotspot.Rssi} dBm", Fonts.Label with { Mono = true }, ConnectPalette.Faint),
            Ui.HStack(6,
                Ui.Text("Add", Fonts.Button, ConnectPalette.Orange),
                Ui.Text("→", new FontSpec(13, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Orange)));

        var content = Ui.SpaceBetween(left, right, 8);
        content.Margin = new Thickness(15, 13, 15, 13);
        return new HoverRow(content, 12,
            ConnectPalette.RowBg, Palette.WithAlpha(ConnectPalette.Orange, 0.06),
            ConnectPalette.Hairline, Palette.WithAlpha(ConnectPalette.Orange, 0.5),
            onTap: () => OpenSetup(hotspot.Ssid));
    }

    /// <summary>Окно «Добавить дрон»; с preselected — сразу этот дрон.</summary>
    private async void OpenSetup(string? preselected = null)
    {
        var dlg = new ProvisioningDialog(_app, preselected) { XamlRoot = XamlRoot };
        try { await dlg.ShowAsync(); } catch { }
    }
}
