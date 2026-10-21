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
using Windows.UI;

namespace BumblebeeGcs.Views;

/// <summary>Главный интерфейс после подключения: сайдбар + контент. Порт MainShell из ContentView.swift.</summary>
public sealed class MainShell : Grid
{
    private enum Section { Dashboard, Entertainment, Settings }

    private static readonly (Section Id, string Label, string Glyph)[] Sections =
    {
        (Section.Dashboard, "Dashboard", IconGlyphs.Dashboard),
        (Section.Entertainment, "Entertainment", IconGlyphs.Entertainment),
        (Section.Settings, "Settings", IconGlyphs.Wifi),
    };

    private readonly AppState _app;
    private Section _section = Section.Dashboard;

    private readonly Grid _pageHost = new();
    private readonly List<(Section Id, Border Row, FontIcon Icon, TextBlock Label)> _navRows = new();
    private readonly StatusDot _connDot;
    private readonly TextBlock _connLabel;
    private readonly Action _onConnChanged;

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

        var disconnect = Ui.GhostButton("Disconnect", () => _app.Disconnect(), IconGlyphs.Power);
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
        var title = Ui.Text(_app.DroneHost, Fonts.Title, Palette.Text);
        Grid.SetColumn(title, 0);
        var reconnect = Ui.ToolbarIconButton(IconGlyphs.Reconnect, "Reconnect", () => _app.Reconnect());
        Grid.SetColumn(reconnect, 1);
        var rescan = Ui.ToolbarIconButton(IconGlyphs.Rescan, "Rescan network", () => _app.Scanner.Scan());
        Grid.SetColumn(rescan, 2);
        header.Children.Add(title);
        header.Children.Add(reconnect);
        header.Children.Add(rescan);

        var contentCol = new Grid { Background = Palette.AppGradient() };
        contentCol.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        contentCol.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        Grid.SetRow(header, 0);
        Grid.SetRow(_pageHost, 1);
        contentCol.Children.Add(header);
        contentCol.Children.Add(_pageHost);
        Grid.SetColumn(contentCol, 1);
        Children.Add(contentCol);

        _onConnChanged = () =>
        {
            var ok = _app.Telemetry.RosConnected;
            _connDot.SetColor(ok ? Palette.Ok : Palette.Warn);
            _connDot.SetPulsing(!ok);
            _connLabel.Text = ok ? "linked" : "linking…";
        };
        _app.Telemetry.ConnectionChanged += _onConnChanged;
        Unloaded += (_, _) => _app.Telemetry.ConnectionChanged -= _onConnChanged;
        _onConnChanged();

        ShowSection(Section.Dashboard);
    }

    private Border NavRow(Section id, string label, string glyph)
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
        Ui.OnTap(row, () => ShowSection(id));
        Ui.OnHover(row, h =>
        {
            if (_section == id) return;
            row.Background = h ? Palette.Brush(Palette.HoverBg) : null;
        });
        _navRows.Add((id, row, icon, text));
        return row;
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
        _pageHost.Children.Clear();
        UIElement page = id switch
        {
            Section.Entertainment => new EntertainmentPage(_app),
            Section.Settings => new SettingsPage(_app),
            _ => new DashboardPage(_app),
        };
        _pageHost.Children.Add(page);
    }
}
