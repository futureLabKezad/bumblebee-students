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
using BumblebeeGcs.Logic;
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace BumblebeeGcs.Views;

/// <summary>
/// «Добавить дрон»: выбрать новый дрон рядом, подтвердить пароль WiFi этого ПК
/// (вводится один раз, запоминается в PasswordVault) — остальное программа
/// делает сама: говорит с дроном через его WiFi, отдаёт ему сеть ПК, возвращает
/// ПК и подключается. WiFi самого дрона — деталь реализации; он виден только
/// как запасной вариант «подключиться напрямую». Порт ProvisioningView.swift.
/// </summary>
public sealed class ProvisioningDialog : ContentDialog
{
    private enum View { Pick, Progress, Failure, Permission }

    private readonly AppState _app;
    private readonly WifiHandoff _handoff;
    /// <summary>Дрон, выбранный на стартовом экране: добавляется сразу, если пароль WiFi уже известен.</summary>
    private readonly string? _preselected;
    private readonly Grid _body = new();
    private readonly TextBlock _subtitle;
    private readonly DispatcherTimer _rescan = new() { Interval = TimeSpan.FromSeconds(5) };
    private readonly Action _onChanged;

    // Экран выбора живёт всё время диалога: перестраивается только список
    // дронов, поэтому поле пароля не теряет фокус при пересканировании.
    private readonly StackPanel _pickView = new() { Spacing = 14 };
    private readonly StackPanel _droneList = new() { Spacing = 8 };
    private readonly Border _pickWifiSlot = new();
    private readonly Border _addPreselectedSlot = new();

    // Карточка «ваша WiFi» (одна на диалог, переезжает между экранами).
    private readonly Border _wifiCard;
    private readonly TextBlock _wifiName;
    private readonly TextBlock _wifiHint;
    private readonly PasswordBox _password = new();

    private View? _shown;
    private string? _lastDrone;            // SSID хотспота последней попытки
    private bool _needPassword;
    private string? _passwordFor;          // сеть, для которой загружен пароль
    private WifiHandoff.Failure? _failureShown;
    private bool _closed;                  // window gone: never start a setup

    public ProvisioningDialog(AppState app, string? preselected = null)
    {
        _app = app;
        _handoff = app.Handoff;
        _preselected = preselected;

        Background = ConnectPalette.Background();
        Foreground = Palette.Brush(ConnectPalette.Text);
        BorderBrush = Palette.Brush(ConnectPalette.Hairline);
        CornerRadius = new CornerRadius(12);
        Resources["ContentDialogMaxWidth"] = 640.0;
        Resources["ContentDialogMinWidth"] = 560.0;

        StylePassword();
        (_wifiCard, _wifiName, _wifiHint) = BuildWifiCard();
        BuildPickView();

        var root = new Grid
        {
            Width = 520,
            Height = 500,
            RowSpacing = 18,
        };
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

        _subtitle = Ui.Text("", Fonts.BodyMed with { Mono = true }, ConnectPalette.Muted);
        _subtitle.TextWrapping = TextWrapping.Wrap;
        var headerLeft = Ui.VStack(4,
            Ui.Text("Add a drone", new FontSpec(20, new Windows.UI.Text.FontWeight(700)), ConnectPalette.Text),
            _subtitle);
        var closeText = Ui.Text("Close", Fonts.Body, ConnectPalette.Muted);
        var close = new Border { Child = closeText, Padding = new Thickness(6, 4, 6, 4) };
        Ui.OnHover(close, h => closeText.Foreground = Palette.Brush(h ? ConnectPalette.Text : ConnectPalette.Muted));
        Ui.OnTap(close, () =>
        {
            if (_handoff.IsBusy) return;
            _closed = true;                // before Hide(): Closed comes only after the hide animation
            _handoff.Reset();
            Hide();
        });
        var header = Ui.SpaceBetween(headerLeft, close);
        Grid.SetRow(header, 0);
        root.Children.Add(header);

        var divider = new Border { Height = 1, Background = Palette.Brush(ConnectPalette.Hairline) };
        Grid.SetRow(divider, 1);
        root.Children.Add(divider);

        Grid.SetRow(_body, 2);
        root.Children.Add(_body);

        Content = root;

        // Пока идёт настройка, диалог нельзя закрыть (Esc / клик мимо).
        Closing += (_, e) =>
        {
            if (_handoff.IsBusy) e.Cancel = true;
            else _closed = true;           // Esc / programmatic Hide(): closing has begun
        };

        // Новые дроны появляются через ~30 с после включения — держим список свежим.
        _rescan.Tick += (_, _) =>
        {
            if (_handoff.Phase is WifiHandoff.PhaseKind.Picking or WifiHandoff.PhaseKind.Idle)
                _ = _handoff.ScanHotspotsAsync();
        };

        _onChanged = () =>
        {
            SyncPassword();
            RefreshBody();
            if (_handoff.Phase == WifiHandoff.PhaseKind.Done && _handoff.PhaseArg is string host && host.Length > 0)
            {
                _app.Connect(host);
                _handoff.Reset();
                Hide();
            }
        };
        _handoff.Changed += _onChanged;
        Closed += (_, _) =>
        {
            _closed = true;
            _handoff.Changed -= _onChanged;
            _rescan.Stop();
        };

        Opened += async (_, _) =>
        {
            _handoff.Reset();
            _handoff.RefreshCurrentSsid();
            SyncPassword(force: true);
            _rescan.Start();
            await _handoff.ScanHotspotsAsync();
            if (_closed) return;           // closed during the first scan
            if (_preselected is string drone && _handoff.HomeSsid.Length > 0)
            {
                if (_password.Password.Length == 0)
                {
                    _needPassword = true;
                    _lastDrone = drone;
                    RefreshBody();
                    _password.Focus(FocusState.Programmatic);
                }
                else
                {
                    Add(drone);
                }
            }
        };
        RefreshBody();
    }

    // MARK: - State → screen

    private void RefreshBody()
    {
        _subtitle.Text = HeaderSubtitle();
        View view;
        if (_handoff.IsBusy) view = View.Progress;
        else if (_handoff.Phase == WifiHandoff.PhaseKind.Failed && _handoff.LastFailure is not null) view = View.Failure;
        else if (_handoff.Phase == WifiHandoff.PhaseKind.NeedLocationPermission) view = View.Permission;
        else view = View.Pick;

        switch (view)
        {
            case View.Pick:
                UpdatePickView();
                if (_shown != View.Pick)
                {
                    Mount(_pickWifiSlot);
                    Show(_pickView);
                }
                break;
            case View.Progress:
                Show(ProgressView());
                break;
            case View.Failure:
                var failure = _handoff.LastFailure!;
                if (_shown != View.Failure || !ReferenceEquals(failure, _failureShown))
                {
                    _failureShown = failure;
                    Show(FailureView(failure));
                }
                break;
            case View.Permission:
                Show(PermissionView());
                break;
        }
        _shown = view;
    }

    private void Show(UIElement content)
    {
        _body.Children.Clear();
        _body.Children.Add(content);
    }

    private string HeaderSubtitle()
    {
        var home = _handoff.HomeSsid;
        if (home.Length == 0)
            return _handoff.OnDroneHotspot
                ? "This PC is on a drone's WiFi — connect it to your WiFi first"
                : "Connect this PC to WiFi first";
        return _handoff.OnDroneHotspot
            ? $"It will join {home}; this PC goes back to it afterwards"
            : $"It will join {home}, the same WiFi as this PC";
    }

    /// <summary>Пароль хранится для каждой сети: подгрузить, если сеть ПК сменилась.</summary>
    private void SyncPassword(bool force = false)
    {
        var home = _handoff.HomeSsid;
        if (!force && (home == _passwordFor || _handoff.IsBusy)) return;
        _passwordFor = home;
        _password.Password = CredentialStore.Password(home) ?? "";
    }

    // MARK: - Picking a drone

    private void BuildPickView()
    {
        _pickView.Children.Add(SectionLabel("NEW DRONES NEARBY"));
        _pickView.Children.Add(new ScrollViewer { Content = _droneList, MaxHeight = 200 });
        _pickView.Children.Add(SectionLabel("YOUR WIFI"));
        _pickView.Children.Add(_pickWifiSlot);
        _addPreselectedSlot.HorizontalAlignment = HorizontalAlignment.Right;
        _pickView.Children.Add(_addPreselectedSlot);
    }

    private void UpdatePickView()
    {
        _droneList.Children.Clear();
        if (_handoff.Hotspots.Count == 0)
        {
            var title = Ui.HStack(10,
                new ProgressRing { IsActive = true, Width = 16, Height = 16 },
                Ui.Text("Looking for drones…", Fonts.BodyStrong, ConnectPalette.Text));
            var hint = Ui.Text("Turn the drone on. In about 30 seconds its lights breathe blue and it shows up here.",
                new FontSpec(12, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Muted);
            hint.TextWrapping = TextWrapping.Wrap;
            _droneList.Children.Add(Card(Ui.VStack(8, title, hint), new Thickness(16)));
        }
        else
        {
            foreach (var h in _handoff.Hotspots) _droneList.Children.Add(DroneRow(h));
        }

        UpdateWifiCard();
        // Кнопка держится, пока выбранный на стартовом экране дрон ждёт пароля
        // (не пропадает на первой набранной букве).
        _addPreselectedSlot.Child = _preselected is string drone && _lastDrone == drone
            ? Ui.AccentButton($"Add {drone}", () => Add(drone))
            : null;
    }

    private UIElement DroneRow(WifiHandoff.Hotspot h)
    {
        var icon = Ui.Icon(IconGlyphs.Mode, 18, ConnectPalette.Orange);
        var text = Ui.VStack(2,
            Ui.Text(h.Ssid, new FontSpec(14.5, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text),
            Ui.Text($"new drone · {SignalWord(h.Rssi)} signal",
                new FontSpec(11.5, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Muted2));
        var add = Ui.AccentButton("Add", () => Add(h.Ssid));
        add.IsEnabled = _handoff.HomeSsid.Length > 0;
        return Card(Ui.SpaceBetween(Ui.HStack(12, icon, text), add, 8), new Thickness(14, 10, 14, 10));
    }

    private static string SignalWord(int rssi) => rssi >= -55 ? "strong" : rssi >= -70 ? "good" : "weak";

    // MARK: - "Your WiFi" card

    private void StylePassword()
    {
        _password.PlaceholderText = "WiFi password";
        _password.FontSize = 14;
        _password.FontFamily = Fonts.MonoFamily;
        _password.BorderThickness = new Thickness(0);
        _password.Padding = new Thickness(0);
        _password.MinHeight = 0;
        _password.VerticalAlignment = VerticalAlignment.Center;
        foreach (var state in new[] { "", "PointerOver", "Focused" })
        {
            _password.Resources[$"TextControlBackground{state}"] = Palette.Brush(Colors.Transparent);
            _password.Resources[$"TextControlBorderBrush{state}"] = Palette.Brush(Colors.Transparent);
        }
        _password.Resources["TextControlForegroundFocused"] = Palette.Brush(ConnectPalette.Text);
        _password.Resources["TextControlForegroundPointerOver"] = Palette.Brush(ConnectPalette.Text);
        _password.Resources["TextControlPlaceholderForeground"] = Palette.Brush(ConnectPalette.Faint);
        _password.PasswordChanged += (_, _) =>
        {
            if (_needPassword && _password.Password.Length > 0) _needPassword = false;
            if (_shown == View.Pick) UpdatePickView();
        };
    }

    private (Border Card, TextBlock Name, TextBlock Hint) BuildWifiCard()
    {
        var name = Ui.Text("", new FontSpec(14, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text);
        var top = Ui.HStack(10, Ui.Icon(IconGlyphs.Wifi, 14, ConnectPalette.BlueSoft), name);
        var field = new Border
        {
            Background = Palette.Brush(Palette.WithAlpha(Colors.White, 0.04)),
            BorderBrush = Palette.Brush(ConnectPalette.Hairline),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(12, 8, 12, 8),
            Child = _password,
        };
        var hint = Ui.Text("", new FontSpec(10.5, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Faint);
        hint.TextWrapping = TextWrapping.Wrap;
        var card = Card(Ui.VStack(10, top, field, hint), new Thickness(14));
        return (card, name, hint);
    }

    private void UpdateWifiCard()
    {
        var home = _handoff.HomeSsid;
        _wifiName.Text = home.Length == 0 ? "Not connected" : home;
        _password.PlaceholderText = $"Password for {(home.Length == 0 ? "your WiFi" : home)}";
        _wifiHint.Text = _needPassword
            ? $"Enter the password first — the drone needs it to join {home}."
            : "The drone needs it to join this network. Saved on this PC.";
        _wifiHint.Foreground = Palette.Brush(_needPassword ? ConnectPalette.Orange : ConnectPalette.Faint);
        if (_password.Parent is Border field)
            field.BorderBrush = Palette.Brush(_needPassword ? ConnectPalette.Orange : ConnectPalette.Hairline);
    }

    /// <summary>Переставить карточку WiFi в slot (элемент XAML может иметь одного родителя).</summary>
    private void Mount(Border slot)
    {
        if (_wifiCard.Parent is Border old && !ReferenceEquals(old, slot)) old.Child = null;
        if (!ReferenceEquals(slot.Child, _wifiCard)) slot.Child = _wifiCard;
    }

    // MARK: - Live checklist while the app works

    private UIElement ProgressView()
    {
        var step = _handoff.Phase switch
        {
            WifiHandoff.PhaseKind.JoiningHotspot => 1,
            WifiHandoff.PhaseKind.PushingCreds => 2,
            WifiHandoff.PhaseKind.WaitingForDrone => 3,
            WifiHandoff.PhaseKind.Diagnosing => 4,
            _ => 0,
        };
        var drone = _lastDrone ?? "the drone";
        var home = _handoff.HomeSsid;
        var rows = Ui.VStack(12,
            CheckRow($"Connecting to {drone}", 1, step),
            CheckRow($"Sending your WiFi {home}", 2, step),
            CheckRow($"Drone joins {home}, PC comes back", 3, step),
            CheckRow(step == 4 ? "Checking what went wrong…" : $"Finding the drone on {home}", 4, step));
        var note = Ui.Text($"Usually under a minute; if something goes wrong, up to about 3 minutes while the app finds out why. The PC briefly leaves {home} and comes back on its own — keep this window open.",
            new FontSpec(11.5, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Muted);
        note.TextWrapping = TextWrapping.Wrap;
        return Ui.VStack(14,
            SectionLabel($"ADDING {drone.ToUpperInvariant()}"),
            Card(rows, new Thickness(16)),
            note);
    }

    private static UIElement CheckRow(string text, int index, int current)
    {
        FrameworkElement mark;
        if (index < current)
            mark = Ui.Icon(IconGlyphs.Success, 15, ConnectPalette.Green);
        else if (index == current)
            mark = new ProgressRing { IsActive = true, Width = 15, Height = 15 };
        else
            mark = new Ellipse
            {
                Width = 13, Height = 13,
                Stroke = Palette.Brush(ConnectPalette.Faint),
                StrokeThickness = 1.5,
            };
        var slot = new Grid { Width = 18 };
        mark.HorizontalAlignment = HorizontalAlignment.Center;
        mark.VerticalAlignment = VerticalAlignment.Center;
        slot.Children.Add(mark);
        var label = Ui.Text(text,
            new FontSpec(13.5, new Windows.UI.Text.FontWeight((ushort)(index == current ? 600 : 400))),
            index > current ? ConnectPalette.Muted : ConnectPalette.Text);
        label.TextWrapping = TextWrapping.Wrap;
        return Ui.HStack(10, slot, label);
    }

    // MARK: - Failure: the reason the drone reported, and what to do

    private UIElement FailureView(WifiHandoff.Failure f)
    {
        var title = Ui.Text(f.Title, new FontSpec(15, new Windows.UI.Text.FontWeight(600)), ConnectPalette.Text);
        title.TextWrapping = TextWrapping.Wrap;
        var detail = Ui.Text(f.Detail, new FontSpec(12.5, new Windows.UI.Text.FontWeight(400)), ConnectPalette.Muted2);
        detail.TextWrapping = TextWrapping.Wrap;
        var texts = Ui.VStack(6, title, detail);
        var head = new Grid { ColumnSpacing = 12 };
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var icon = Ui.Icon(IconGlyphs.Caution, 22, ConnectPalette.Orange);
        icon.VerticalAlignment = VerticalAlignment.Top;
        Grid.SetColumn(texts, 1);
        head.Children.Add(icon);
        head.Children.Add(texts);

        var stack = new StackPanel { Spacing = 16 };
        stack.Children.Add(head);

        if (f.Kind == WifiHandoff.FailureKind.WrongPassword)
        {
            var slot = new Border();
            Mount(slot);
            stack.Children.Add(slot);
            _password.Password = "";
            _needPassword = false;
            UpdateWifiCard();
            // поле ещё не в дереве — фокус после показа экрана
            DispatcherQueue.TryEnqueue(() => _password.Focus(FocusState.Programmatic));
        }

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        if (_lastDrone is string drone)
        {
            buttons.Children.Add(Ui.AccentButton("Try again", () => Add(drone)));
            if (f.OfferDirect)
                buttons.Children.Add(Ui.GhostButton("Connect directly to the drone", () => Direct(drone)));
        }
        var backText = Ui.Text("Back", Fonts.Body, ConnectPalette.Muted);
        var back = new Border { Child = backText, Padding = new Thickness(6, 4, 6, 4) };
        Ui.OnHover(back, h => backText.Foreground = Palette.Brush(h ? ConnectPalette.Text : ConnectPalette.Muted));
        Ui.OnTap(back, () =>
        {
            _handoff.Reset();
            _ = _handoff.ScanHotspotsAsync();
        });
        stack.Children.Add(Ui.SpaceBetween(buttons, back));

        if (f.OfferDirect)
        {
            var note = Ui.Text("Directly: the PC joins the drone's own WiFi. Works anywhere, but the PC has no internet while connected.",
                new FontSpec(11, new Windows.UI.Text.FontWeight(400), Mono: true), ConnectPalette.Faint);
            note.TextWrapping = TextWrapping.Wrap;
            stack.Children.Add(note);
        }
        return stack;
    }

    // MARK: - Location permission

    private UIElement PermissionView()
    {
        var icon = Ui.Icon(IconGlyphs.LocationOff, 34, ConnectPalette.Orange);
        icon.HorizontalAlignment = HorizontalAlignment.Center;
        var t1 = Ui.Text("Allow WiFi access to find drones", Fonts.Title, ConnectPalette.Text);
        t1.HorizontalAlignment = HorizontalAlignment.Center;
        var msg = _handoff.LocationBlocked
            ? "Windows blocked Location for apps, so WiFi networks can't be read. Enable it in Settings ▸ Privacy & security ▸ Location, then Rescan."
            : "Windows needs Location access to read nearby WiFi. Allow it in Settings if scanning stays empty.";
        var t2 = Ui.Text(msg, Fonts.BodyMed with { Mono = true }, ConnectPalette.Muted);
        t2.TextWrapping = TextWrapping.Wrap;
        t2.TextAlignment = TextAlignment.Center;

        var openBtn = Ui.Text("Open Windows Settings", Fonts.Button, ConnectPalette.Orange);
        var open = new Border { Child = openBtn, Padding = new Thickness(6, 4, 6, 4) };
        Ui.OnTap(open, () => _ = Windows.System.Launcher.LaunchUriAsync(new Uri("ms-settings:privacy-location")));
        var rescanBtn = Ui.Text("Rescan", Fonts.Button, ConnectPalette.BlueSoft);
        var rescanB = new Border { Child = rescanBtn, Padding = new Thickness(6, 4, 6, 4) };
        Ui.OnTap(rescanB, () => _ = _handoff.ScanHotspotsAsync());
        var buttons = Ui.HStack(10, open, rescanB);
        buttons.HorizontalAlignment = HorizontalAlignment.Center;

        var stack = Ui.VStack(14, icon, t1, t2, buttons);
        stack.VerticalAlignment = VerticalAlignment.Center;
        return stack;
    }

    // MARK: - Actions

    private void Add(string drone)
    {
        if (_closed) return;
        var home = _handoff.HomeSsid;
        if (home.Length == 0 || _handoff.IsBusy) return;
        if (_password.Password.Length == 0)
        {
            _needPassword = true;
            _lastDrone = drone;
            if (_shown != View.Pick) _handoff.Reset();   // с экрана ошибки — назад к форме
            RefreshBody();
            _password.Focus(FocusState.Programmatic);
            return;
        }
        _needPassword = false;
        _lastDrone = drone;
        _ = ProvisionAndRememberAsync(drone, home, _password.Password);
    }

    /// <summary>The password is remembered only once the drone has shown it is right.</summary>
    private async Task ProvisionAndRememberAsync(string drone, string home, string password)
    {
        await _handoff.ProvisionAsync(drone, home, password, _ => { });
        string? failure;
        if (_handoff.Phase == WifiHandoff.PhaseKind.Done) failure = null;
        else if (_handoff.Phase == WifiHandoff.PhaseKind.Failed && _handoff.LastFailure is { } f) failure = f.Kind.ToString();
        else return;
        switch (PasswordMemoryRule.After(failure))
        {
            case PasswordMemory.Save: CredentialStore.SetPassword(password, home); break;
            case PasswordMemory.Forget: CredentialStore.SetPassword("", home); break;
        }
    }

    private void Direct(string drone) => _ = _handoff.ConnectDirectAsync(drone, _ => { });

    // MARK: - Bits

    private static TextBlock SectionLabel(string text) =>
        Ui.Text(text, Fonts.Label with { Mono = true }, ConnectPalette.Faint, tracking: 1.2);

    private static Border Card(UIElement content, Thickness padding) => new()
    {
        Background = Palette.Brush(ConnectPalette.RowBg),
        BorderBrush = Palette.Brush(ConnectPalette.Hairline),
        BorderThickness = new Thickness(1),
        CornerRadius = new CornerRadius(12),
        Padding = padding,
        Child = content,
    };
}
