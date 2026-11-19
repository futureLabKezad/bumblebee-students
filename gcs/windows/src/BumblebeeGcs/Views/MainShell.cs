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
using Windows.UI;

namespace BumblebeeGcs.Views;

/// <summary>Главный интерфейс после подключения: сайдбар + контент. Порт MainShell из ContentView.swift.</summary>
public sealed class MainShell : Grid
{
    private enum Section { Dashboard, Flight, Entertainment, Settings }

    private static readonly (Section Id, string Label, string Glyph)[] Sections =
    {
        (Section.Dashboard, "Dashboard", IconGlyphs.Dashboard),
        (Section.Flight, "Flight", IconGlyphs.Flight),
        (Section.Entertainment, "Entertainment", IconGlyphs.Entertainment),
        (Section.Settings, "Settings", IconGlyphs.Wifi),
    };

    private readonly AppState _app;
    private Section _section = Section.Dashboard;

    private readonly Grid _pageHost = new();
    // «Полёт» (WebView2 with the map, the program and Python) is made once per connection and
    // only hidden when another section is shown: the editor's text and the loaded Python stay.
    private FlightPage? _flightPage;
    // The app's own Stop for a flight program, in the header of every section once «Полёт» was
    // opened: it does not depend on the web page (hidden, busy, broken or under a dialog).
    private readonly MissionApi _missionApi = new();
    private readonly StackPanel _stopGroup;
    private readonly TextBlock _stopNote;
    private bool _gone;                          // this shell left the window
    private readonly List<(Section Id, Border Row, FontIcon Icon, TextBlock Label)> _navRows = new();
    private readonly StatusDot _connDot;
    private readonly TextBlock _connLabel;
    private readonly Action _onConnChanged, _onTelemetry, _onMismatch;
    // Тревоги поверх любой страницы (как AlarmBanner на Mac): FC потерян у армленного дрона, низкий заряд.
    private readonly AlarmBanner _fcLostBanner = new(IconGlyphs.Error), _lowBatteryBanner = new(IconGlyphs.BatteryUnknown),
        _hotspotBanner = new(IconGlyphs.Wifi);

    public MainShell(AppState app)
    {
        _app = app;

        ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(224) });
        ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        // MARK: - Sidebar

        _connDot = new StatusDot(Palette.Warn, pulsing: true);
        _connLabel = Ui.Text("linking…", Fonts.SectionLbl, Palette.Muted);

        var connCard = new Border
        {
            Background = Ui.GlassBrush(),
            BorderBrush = Palette.EdgeStroke(),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(Palette.RControl),
            Padding = new Thickness(Palette.S3),
            Child = Ui.HStack(Palette.S2,
                _connDot,
                Ui.VStack(Palette.S0 - 1,
                    Ui.Text(_app.DroneHost, Fonts.HostMono, Palette.Text),
                    _connLabel)),
        };

        var brand = Ui.HStack(Palette.S2, Ui.AppLogo(22, Palette.RMedia), Ui.Text("Bumblebee GCS", Fonts.Brand, Palette.Text),
            Ui.Text(AppVersion.Short, Fonts.Label, Palette.Muted));
        brand.Margin = new Thickness(Palette.S4, Palette.S5, Palette.S4, Palette.S3);

        var nav = new StackPanel { Spacing = 2, Margin = new Thickness(Palette.S2, 0, Palette.S2, 0) };
        foreach (var (id, label, glyph) in Sections)
        {
            var row = NavRow(id, label, glyph);
            nav.Children.Add(row);
        }

        var disconnect = Ui.GhostButton("Disconnect", () => _ = DisconnectAsync(), IconGlyphs.Power);
        disconnect.HorizontalAlignment = HorizontalAlignment.Stretch;
        disconnect.HorizontalContentAlignment = HorizontalAlignment.Center;
        disconnect.Margin = new Thickness(Palette.S3);

        var sidebarStack = new Grid();
        sidebarStack.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        sidebarStack.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        sidebarStack.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        sidebarStack.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        Grid.SetRow(brand, 0);
        var connWrap = new Border { Child = connCard, Margin = new Thickness(Palette.S3, 0, Palette.S3, Palette.S4) };
        Grid.SetRow(connWrap, 1);
        Grid.SetRow(nav, 2);
        nav.VerticalAlignment = VerticalAlignment.Top;
        Grid.SetRow(disconnect, 3);
        sidebarStack.Children.Add(brand);
        sidebarStack.Children.Add(connWrap);
        sidebarStack.Children.Add(nav);
        sidebarStack.Children.Add(disconnect);

        var sidebar = new Border
        {
            Background = new Microsoft.UI.Xaml.Media.AcrylicBrush
            {
                TintColor = Palette.BgDeep,
                TintOpacity = 0.4,
                TintLuminosityOpacity = 0.8,
                FallbackColor = Palette.Surface,
            },
            BorderBrush = Palette.Brush(Palette.Hairline),
            BorderThickness = new Thickness(0, 0, 1, 0),
            Child = sidebarStack,
        };
        Grid.SetColumn(sidebar, 0);
        Children.Add(sidebar);

        // MARK: - Content column: заголовок + страница

        var header = new Grid { Padding = new Thickness(Palette.S4, Palette.S3, Palette.S4, Palette.S3), ColumnSpacing = Palette.S2 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var title = Ui.Text(_app.DroneHost, Fonts.Title, Palette.Text);
        Grid.SetColumn(title, 0);
        _stopNote = Ui.Text("", Fonts.Label, Palette.Muted);
        _stopNote.VerticalAlignment = VerticalAlignment.Center;
        var stopFlight = Ui.FlatButton(
            new Border
            {
                Padding = new Thickness(Palette.S3, Palette.S2, Palette.S3, Palette.S2),
                Child = Ui.Text("STOP FLIGHT", Fonts.BodyStrong, Colors.White),
            },
            () => _ = StopFlightAsync(), "Stop the flight program", Palette.Danger, Palette.Danger, Colors.White,
            radius: Palette.RControl);
        // Always there, in every section: a program may be flying that this window did not start
        // (the app was restarted or connected again).
        _stopGroup = Ui.HStack(Palette.S2, _stopNote, stopFlight);
        Grid.SetColumn(_stopGroup, 1);
        var reconnect = Ui.ToolbarIconButton(IconGlyphs.Reconnect, "Reconnect", () => _app.Reconnect());
        Grid.SetColumn(reconnect, 2);
        var rescan = Ui.ToolbarIconButton(IconGlyphs.Rescan, "Rescan network", () => _app.Scanner.Scan());
        Grid.SetColumn(rescan, 3);
        header.Children.Add(title);
        header.Children.Add(_stopGroup);
        header.Children.Add(reconnect);
        header.Children.Add(rescan);

        var banners = Ui.VStack(0, _fcLostBanner, _lowBatteryBanner, _hotspotBanner);

        var contentCol = new Grid { Background = Palette.AppGradient() };
        contentCol.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        contentCol.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        contentCol.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        Grid.SetRow(header, 0);
        Grid.SetRow(banners, 1);
        Grid.SetRow(_pageHost, 2);
        contentCol.Children.Add(header);
        contentCol.Children.Add(banners);
        contentCol.Children.Add(_pageHost);
        Grid.SetColumn(contentCol, 1);
        Children.Add(contentCol);

        // Точка и подпись в сайдбаре следуют за Link (а не только за сокетом), как на Mac.
        _onConnChanged = () =>
        {
            var t = _app.Telemetry;
            _connDot.SetColor(Palette.ForTone(LinkLogic.ToneOf(t.Link)));
            _connDot.SetPulsing(t.Link != LinkState.Ok);
            _connLabel.Text = LinkLogic.SidebarText(t.Link, t.RosConnected);
        };
        _onTelemetry = RefreshBanners;
        _onMismatch = () => DispatcherQueue.TryEnqueue(() => _ = AskIdentityAsync());
        _app.IdentityMismatchFound += _onMismatch;
        _app.Telemetry.LinkChanged += _onConnChanged;
        _app.Telemetry.ConnectionChanged += _onConnChanged;
        _app.Telemetry.Updated += _onTelemetry;
        Unloaded += (_, _) =>
        {
            _app.Telemetry.LinkChanged -= _onConnChanged;
            _app.Telemetry.ConnectionChanged -= _onConnChanged;
            _app.Telemetry.Updated -= _onTelemetry;
            _app.IdentityMismatchFound -= _onMismatch;
        };
        // The PC's WiFi name, for the drone-hotspot banner (read every 15 s, not per message).
        var ssidTimer = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        ssidTimer.Interval = TimeSpan.FromSeconds(15);
        ssidTimer.Tick += (_, _) => { _app.Handoff.RefreshCurrentSsid(); RefreshBanners(); };
        ssidTimer.Start();
        Unloaded += (_, _) => { ssidTimer.Stop(); _gone = true; };
        _app.Handoff.RefreshCurrentSsid();
        _onConnChanged();
        RefreshBanners();

        // Тестовый хук рядом с --connect: BumblebeeGcs.exe --connect <host> --section flight
        // открывает раздел «Полёт» сразу (end-to-end прогоны со встроенной страницей).
        var cli = Environment.GetCommandLineArgs();
        var idx = Array.IndexOf(cli, "--section");
        ShowSection(idx >= 0 && idx + 1 < cli.Length && cli[idx + 1] == "flight" ? Section.Flight : Section.Dashboard);
    }

    private void RefreshBanners()
    {
        var t = _app.Telemetry;
        _fcLostBanner.Set(t.FcAlarm.BannerVisible ? FcLostAlarm.Text : null);
        _lowBatteryBanner.Set(t.LowBatteryBanner);
        // On a drone's hotspot by choice ("Connect directly") is fine; Windows staying on one is not.
        var h = _app.Handoff;
        _hotspotBanner.Set(h.OnDroneHotspot && _app.DroneHost != WifiHandoff.HotspotGatewayHost
            ? $"This PC is on {h.CurrentSsid}, a drone's own WiFi: pick your classroom WiFi in the taskbar" : null);
    }

    /// <summary>The drone answering at the address is not the one picked: stay or disconnect.</summary>
    private async Task AskIdentityAsync()
    {
        if (_app.IdentityMismatch is not string text || XamlRoot is null) return;
        var dlg = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "Not the drone you picked",
            Content = text,
            PrimaryButtonText = "Stay connected",
            CloseButtonText = "Disconnect",
            DefaultButton = ContentDialogButton.Close,
            RequestedTheme = ElementTheme.Dark,
        };
        ContentDialogResult r;
        try { r = await dlg.ShowAsync(); }
        catch
        {
            // Another window of the app is open. The question must not be lost (no takeoff is
            // allowed while it is unanswered): ask again shortly.
            await Task.Delay(1500);
            if (!_gone && _app.IdentityMismatch is not null) DispatcherQueue.TryEnqueue(() => _ = AskIdentityAsync());
            return;
        }
        if (r == ContentDialogResult.Primary) _app.IdentityMismatch = null; else _app.Disconnect();
    }

    /// <summary>The app's own Stop for a flight program: one click, no questions; tried again if the drone is silent.</summary>
    private async Task StopFlightAsync()
    {
        _flightPage?.NoteStop();                 // a takeoff request that is still on its way must not win
        _stopNote.Text = "sending STOP…";
        var reply = await _missionApi.StopAsync(_app.DroneHost);
        _stopNote.Text = reply.Code == 200 ? "STOP sent " + DateTime.Now.ToString("HH:mm:ss")
                                           : "STOP did not reach the drone: use the RC (CH8)";
    }

    /// <summary>Disconnect takes the Flight page and STOP FLIGHT off the screen while the program
    /// on the drone flies on: ask first, and offer the stop right there.</summary>
    private async Task DisconnectAsync()
    {
        if (_flightPage?.MissionActive == true && XamlRoot is not null)
        {
            var dlg = new ContentDialog
            {
                XamlRoot = XamlRoot,
                Title = "A flight program is running",
                Content = "Disconnecting does not stop it, and the app cannot stop a drone it is not connected to. "
                        + "The RC (CH8) always stops it.",
                PrimaryButtonText = "Stop the flight",
                SecondaryButtonText = "Disconnect anyway",
                CloseButtonText = "Stay connected",
                DefaultButton = ContentDialogButton.Close,
                RequestedTheme = ElementTheme.Dark,
            };
            ContentDialogResult answer;
            try { answer = await dlg.ShowAsync(); }
            catch { return; }
            if (answer == ContentDialogResult.Primary) { await StopFlightAsync(); return; }
            if (answer != ContentDialogResult.Secondary) return;
        }
        _app.Disconnect();
    }

    /// <summary>A sidebar entry: a real Button around the styled row (Tab, Enter, Narrator).</summary>
    private Button NavRow(Section id, string label, string glyph)
    {
        var icon = Ui.Icon(glyph, Palette.IconLg, Palette.Muted);
        icon.Width = Palette.IconLg;
        var text = Ui.Text(label, Fonts.Body, Palette.Muted);
        var row = new Border
        {
            CornerRadius = new CornerRadius(Palette.RControl),
            Padding = new Thickness(Palette.S2, Palette.S2 + 1, Palette.S2, Palette.S2 + 1),
            Child = Ui.HStack(Palette.S2, icon, text),
        };
        Ui.OnHover(row, h =>
        {
            if (_section == id) return;
            row.Background = h ? Palette.Brush(Palette.HoverBg) : null;
        });
        _navRows.Add((id, row, icon, text));
        return Ui.FlatButton(row, () => ShowSection(id), label, Colors.Transparent, Colors.Transparent, Palette.Text,
            radius: Palette.RControl);
    }

    private void ShowSection(Section id)
    {
        _section = id;
        foreach (var (rid, row, icon, label) in _navRows)
        {
            var active = rid == id;
            row.Background = active ? Palette.Brush(Palette.SelectionBg) : null;
            icon.Foreground = Palette.Brush(active ? Palette.Text : Palette.Muted);
            label.Foreground = Palette.Brush(active ? Palette.Text : Palette.Muted);
            label.FontWeight = active ? Fonts.BodyStrong.Weight : Fonts.Body.Weight;
        }
        // Every page but «Полёт» is made anew; «Полёт» stays in the tree, shown or collapsed.
        for (var i = _pageHost.Children.Count - 1; i >= 0; i--)
            if (!ReferenceEquals(_pageHost.Children[i], _flightPage)) _pageHost.Children.RemoveAt(i);
        if (id == Section.Flight)
        {
            if (_flightPage is null)
            {
                var flight = new FlightPage(_app);
                _flightPage = flight;
                _pageHost.Children.Add(flight);
                flight.MissionActiveChanged += () => _stopNote.Text = flight.MissionActive ? "flight program running" : "";
                flight.TakeoffInFlightChanged += () =>
                {
                    if (flight.TakeoffInFlight) _stopNote.Text = "takeoff sent, waiting for the drone…";
                };
            }
            _flightPage.Visibility = Visibility.Visible;
            return;
        }
        if (_flightPage is not null) _flightPage.Visibility = Visibility.Collapsed;
        UIElement page = id switch
        {
            Section.Entertainment => new EntertainmentPage(_app),
            Section.Settings => new SettingsPage(_app),
            _ => new DashboardPage(_app),
        };
        _pageHost.Children.Add(page);
    }
}
