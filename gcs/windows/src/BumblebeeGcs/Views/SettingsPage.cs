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

/// <summary>
/// WiFi дрона: статус, скан, сохранённые сети, добавление. Порт SettingsView.swift.
/// Перед каждым изменением заново читается id дрона, и если по адресу отвечает другой
/// дрон, изменение не отправляется. Решения — в Logic/SettingsLogic.cs.
/// </summary>
public sealed class SettingsPage : Grid
{
    private readonly AppState _app;

    private DroneApi.WifiStatus? _status;
    private DateTime? _statusAt;
    private string? _statusError;
    private DroneApi.DroneInfo? _info;
    private List<DroneApi.ScanNet> _scan = new();
    private bool _scanned;
    private List<string>? _saved;
    private string? _savedError;
    private bool _busy;
    private string? _msgCode;   // the drone's code behind the error banner
    private bool _scanning;

    private readonly StatusBanner _identityBanner = new();
    private readonly PanelCard _statusPanel;
    private readonly StackPanel _statusRows = new() { Spacing = Palette.S3 };
    private readonly StackPanel _scanRows = new() { Spacing = Palette.S3 };
    private readonly StackPanel _savedRows = new() { Spacing = Palette.S3 };
    private readonly ProgressRing _scanRing = new() { Width = 14, Height = 14, IsActive = true, Visibility = Visibility.Collapsed };
    private readonly ProgressRing _busyRing = new() { Width = 14, Height = 14, IsActive = true, Visibility = Visibility.Collapsed };
    private readonly Button _scanBtn, _applyNow, _applyBoot;
    private readonly GlassTextField _addSsid, _addPass;
    private readonly TextBlock _formNote;
    private readonly StatusBanner _msg = new();

    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _statusTimer;

    private string DroneLabel => _info?.Name ?? _app.DroneName;
    private string? DroneId => _app.DroneId ?? _status?.Id;
    private DroneIdentity Identity => DroneIdentity.Check(_app.DroneId, _status?.Id);

    public SettingsPage(AppState app)
    {
        _app = app;

        // MARK: Panels
        _statusPanel = new PanelCard("WiFi Status", IconGlyphs.Wifi, _statusRows);

        _scanBtn = Ui.GhostButton("Scan", DoScan);
        var scanHeader = Ui.HStack(Palette.S2, _scanBtn, _scanRing);
        var scanPanel = new PanelCard("Available Networks", IconGlyphs.Antenna, scanHeader, _scanRows);

        var savedPanel = new PanelCard("Saved Networks", IconGlyphs.Bookmark, _savedRows);

        _addSsid = new GlassTextField("SSID", IconGlyphs.Wifi);
        _addPass = new GlassTextField("Password", IconGlyphs.Key, secure: true);
        _formNote = Ui.Text("", Fonts.MonoSmall, Palette.Caution);
        _formNote.TextWrapping = TextWrapping.Wrap;
        _applyNow = Ui.AccentButton("Save + Apply Now", ApplyNow);
        _applyBoot = Ui.GhostButton("Save for next boot", ApplyBoot);
        _addSsid.TextChanged += RefreshForm;
        _addPass.TextChanged += RefreshForm;
        var addButtons = Ui.HStack(Palette.S2, _applyNow, _applyBoot, _busyRing);
        var hint = Ui.Text("A new password is tried first: if it is wrong, the drone keeps its old one and comes back.",
            Fonts.MonoSmall, Palette.Muted);
        hint.TextWrapping = TextWrapping.Wrap;
        var addPanel = new PanelCard("Add / Update Network", IconGlyphs.Add, _addSsid, _addPass, _formNote, addButtons, hint);

        var diagHint = Ui.Text("For a message when something goes wrong: versions, connection, recent messages. No passwords.",
            Fonts.MonoSmall, Palette.Muted);
        diagHint.TextWrapping = TextWrapping.Wrap;
        var diagPanel = new PanelCard("Diagnostics", IconGlyphs.Info, diagHint, DiagnosticsButton.Create(app, compact: false));

        var stack = Ui.VStack(Palette.S3, _identityBanner, _statusPanel, scanPanel, savedPanel, addPanel, _msg, diagPanel);
        stack.MaxWidth = 640;
        stack.HorizontalAlignment = HorizontalAlignment.Center;
        stack.Width = 640;

        var host = new Grid { Padding = new Thickness(Palette.S4) };
        host.Children.Add(stack);
        var scroll = new ScrollViewer { Content = host, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Children.Add(scroll);

        RefreshStatus();
        RefreshSaved();
        RefreshForm();

        // Автообновление статуса каждые 15 с (порт refreshStatusLoop).
        _statusTimer = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        _statusTimer.Interval = TimeSpan.FromSeconds(15);
        _statusTimer.Tick += (_, _) => _ = RefreshStatusAsync();
        _statusTimer.Start();
        Unloaded += (_, _) => _statusTimer.Stop();
        // An old "refused: counts as armed" goes once the drone is linked and disarmed again.
        _app.Telemetry.LinkChanged += OnLinkChanged;
        Unloaded += (_, _) => _app.Telemetry.LinkChanged -= OnLinkChanged;

        _ = RefreshStatusAsync();
        _ = LoadInfoAndSavedAsync();
    }

    private async Task LoadInfoAndSavedAsync()
    {
        _info = await _app.Api.InfoAsync();
        RefreshStatus();
        await LoadSavedAsync();
    }

    // MARK: - Status

    private void ApplyStatus(DroneApi.WifiStatus s)
    {
        _status = s;
        _statusAt = DateTime.Now;
        _statusError = null;
        if (_app.DroneId is null && s.Id is not null) _app.DroneId = s.Id;
    }

    private async Task RefreshStatusAsync()
    {
        try { ApplyStatus(await _app.Api.WifiStatusAsync()); }
        catch (Exception ex) { _statusError = DroneApi.Describe(ex); }
        RefreshStatus();
        RefreshSaved();
    }

    private void RefreshStatus()
    {
        if (Identity.Blocks)
            _identityBanner.Show(DroneIdentity.DifferentText(Identity.Now!, _app.DroneId ?? "?"), StatusBanner.Kind.Error);
        else
            _identityBanner.Hide();

        _statusRows.Children.Clear();
        var drone = new ReadoutRow("Drone");
        drone.Set(DroneLabel + (DroneId is string id ? $" · id {id}" : " · id unknown"));
        _statusRows.Children.Add(drone);

        var stale = _statusError is not null && _status is not null;
        _statusPanel.SetNote(stale ? $"no answer since {_statusAt:HH:mm:ss}" : null);
        Stale.Dim(_statusRows, stale);

        if (_status is not DroneApi.WifiStatus s)
        {
            if (_statusError is string err)
            {
                var t = Ui.Text(err, Fonts.MonoSmall, Palette.Caution);
                t.TextWrapping = TextWrapping.Wrap;
                _statusRows.Children.Add(t);
                _statusRows.Children.Add(Ui.GhostButton("Retry", () => _ = RefreshStatusAsync(), IconGlyphs.Refresh));
            }
            else
            {
                _statusRows.Children.Add(Ui.Text("loading…", Fonts.MonoSmall, Palette.Muted));
            }
            return;
        }
        var mode = new ReadoutRow("Mode", s.Mode == "client" ? Palette.Ok : Palette.Warn);
        mode.Set(s.Mode.ToUpperInvariant(), s.Mode == "client" ? Palette.Ok : Palette.Warn);
        var net = new ReadoutRow("Network");
        net.Set(s.Ssid.Length == 0 ? Format.Dash : s.Ssid);
        var ip = new ReadoutRow("IP");
        ip.Set(s.Ip.Length == 0 ? Format.Dash : s.Ip);
        var signal = new LabeledBarRow("Signal",
            s.Signal > 60 ? Palette.Ok : (s.Signal > 30 ? Palette.Warn : Palette.Danger));
        signal.Set($"{s.Signal}%", s.Signal);
        _statusRows.Children.Add(mode);
        _statusRows.Children.Add(net);
        _statusRows.Children.Add(ip);
        _statusRows.Children.Add(signal);

        if (s.LastError is DroneApi.JoinError e &&
            JoinReasonText.Banner(e.Ssid, e.Reason, e.TimeUtc, DateTime.UtcNow) is string banner)
        {
            var b = new StatusBanner();
            b.Show(banner, StatusBanner.Kind.Caution);
            _statusRows.Children.Add(b);
        }

        var refresh = Ui.GhostButton("Refresh", () => _ = RefreshStatusAsync(), IconGlyphs.Refresh);
        var switchMode = Ui.AccentButton("Switch Mode", () => _ = ConfirmSwitchModeAsync(s.Mode == "client" ? "hotspot" : "client"));
        switchMode.IsEnabled = !_busy && !Identity.Blocks;
        _statusRows.Children.Add(Ui.HStack(Palette.S2, refresh, switchMode));
    }

    // MARK: - Scan

    private void DoScan()
    {
        if (_scanning) return;
        _scanning = true;
        _scanRing.Visibility = Visibility.Visible;
        _scanBtn.IsEnabled = false;
        _ = ScanCore();
        async Task ScanCore()
        {
            try { _scan = await _app.Api.WifiScanAsync(); }
            catch (Exception ex) { Show("Scan failed: " + DroneApi.Describe(ex), StatusBanner.Kind.Error); }
            finally
            {
                _scanning = false;
                _scanned = true;
                _scanRing.Visibility = Visibility.Collapsed;
                _scanBtn.IsEnabled = true;
                RefreshScan();
                RefreshForm();
            }
        }
    }

    private void RefreshScan()
    {
        _scanRows.Children.Clear();
        if (_scanned && _scan.Count == 0)
            _scanRows.Children.Add(Ui.Text("no networks found", Fonts.MonoSmall, Palette.Muted));
        foreach (var n in _scan)
        {
            var otherDrone = WifiNames.IsProtected(n.Ssid);
            var dot = new Microsoft.UI.Xaml.Shapes.Ellipse
            {
                Width = 7, Height = 7,
                Fill = Palette.Brush(n.InUse ? Palette.Ok : Palette.Muted),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var lockIcon = Ui.Icon(n.Secured ? IconGlyphs.Lock : IconGlyphs.Unlock, Palette.IconSm, Palette.Muted);
            ToolTipService.SetToolTip(lockIcon, n.Secured ? $"Protected ({n.Security})" : "Open network");
            var left = Ui.HStack(Palette.S2, dot, lockIcon,
                Ui.Text(n.Ssid, Fonts.MonoSmall, otherDrone ? Palette.Muted : Palette.Text));
            var sigColor = n.Signal > 60 ? Palette.Ok : (n.Signal > 30 ? Palette.Warn : Palette.Danger);
            UIElement action = otherDrone
                ? Ui.Text("a drone's hotspot", Fonts.MonoSmall, Palette.Muted)
                : Ui.GhostButton("Connect", () => { _addSsid.Text = n.Ssid; _addPass.Text = ""; RefreshForm(); });
            var right = Ui.HStack(Palette.S2,
                Ui.Text($"{n.Signal}%", Fonts.MonoSmall, sigColor),
                BadgeFactory.Badge(n.Band + "G", BandColor(n.Band)),
                action);
            _scanRows.Children.Add(Ui.SpaceBetween(left, right));
        }
    }

    // MARK: - Saved

    private async Task LoadSavedAsync()
    {
        try { _saved = await _app.Api.SavedNetworksAsync(); _savedError = null; }
        catch (Exception ex) { _savedError = DroneApi.Describe(ex); }
        RefreshSaved();
        RefreshForm();
    }

    private bool IsInUse(string name) => _status is { Mode: "client" } s && s.Ssid == name;

    private void RefreshSaved()
    {
        _savedRows.Children.Clear();
        if (_saved is null)
        {
            if (_savedError is string err)
            {
                var t = Ui.Text("Couldn't load the saved networks: " + err, Fonts.MonoSmall, Palette.Caution);
                t.TextWrapping = TextWrapping.Wrap;
                _savedRows.Children.Add(t);
                _savedRows.Children.Add(Ui.GhostButton("Retry", () => _ = LoadSavedAsync()));
            }
            else
            {
                _savedRows.Children.Add(Ui.Text("loading…", Fonts.MonoSmall, Palette.Muted));
            }
            return;
        }
        if (_saved.Count == 0)
        {
            _savedRows.Children.Add(Ui.Text("none", Fonts.MonoSmall, Palette.Muted));
            return;
        }
        foreach (var name in _saved)
        {
            var label = Ui.HStack(Palette.S2, Ui.Text(name, Fonts.MonoSmall, Palette.Text));
            if (IsInUse(name)) label.Children.Add(BadgeFactory.Badge("IN USE", Palette.Ok));
            var remove = Ui.GhostButton("Remove", () => _ = AskRemoveAsync(name));
            ((TextBlock)remove.Content).Foreground = Palette.Brush(Palette.Danger);
            remove.IsEnabled = !_busy && !Identity.Blocks;
            _savedRows.Children.Add(Ui.SpaceBetween(label, remove));
        }
    }

    // MARK: - Add / update form

    private DroneApi.ScanNet? SelectedScan
    {
        get
        {
            foreach (var n in _scan) if (n.Ssid == _addSsid.Text) return n;
            return null;
        }
    }

    private bool AddIsSaved
    {
        get
        {
            var name = _addSsid.Text.Trim();
            return _saved?.Any(p => p == name || WifiNames.Same(name, p)) ?? false;
        }
    }

    private string? FormProblem
    {
        get
        {
            var name = _addSsid.Text.Trim();
            if (name.Length == 0) return null;
            if (WifiNames.IsProtected(name))
                return "That is a drone's own hotspot: it cannot be used as the drone's network.";
            var needs = PasswordCheck.NeedsPassword(AddIsSaved, SelectedScan?.Secured);
            return PasswordCheck.Text(PasswordCheck.Check(_addPass.Text, needs));
        }
    }

    private void RefreshForm()
    {
        var open = SelectedScan is { Secured: false };
        _addPass.Visibility = open ? Visibility.Collapsed : Visibility.Visible;
        if (open && _addPass.Text.Length > 0) _addPass.Text = "";
        var problem = FormProblem;
        if (problem is not null)
        {
            _formNote.Text = problem;
            _formNote.Foreground = Palette.Brush(Palette.Caution);
        }
        else
        {
            _formNote.Text = AddIsSaved && _addPass.Text.Length == 0 ? "Empty password: the saved one is kept." : "";
            _formNote.Foreground = Palette.Brush(Palette.Muted);
        }
        _formNote.Visibility = _formNote.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        var can = _addSsid.Text.Trim().Length > 0 && problem is null && !_busy && !Identity.Blocks;
        _applyNow.IsEnabled = can;
        _applyBoot.IsEnabled = can;
    }

    // MARK: - Actions

    private void Show(string text, StatusBanner.Kind kind)
    {
        _msg.Show(text, kind);
        _msgCode = null;
    }

    private void ShowError(Exception ex)
    {
        _msg.Show(DroneApi.Describe(ex), StatusBanner.Kind.Error);
        _msgCode = DroneApi.CodeOf(ex);
    }

    private void OnLinkChanged()
    {
        if (RefusalBanner.StillTrue(_msgCode, _app.Telemetry.Link, _app.Telemetry.StateArmed)) return;
        _msg.Hide();
        _msgCode = null;
    }

    /// <summary>One change at a time; the buttons stay disabled until it is over.</summary>
    private void Run(Func<Task> op)
    {
        if (_busy) return;
        _busy = true;
        _busyRing.Visibility = Visibility.Visible;
        _msg.Hide();
        _msgCode = null;
        RefreshAll();
        _ = Core();
        async Task Core()
        {
            try { await op(); }
            catch (Exception ex) { ShowError(ex); }
            finally
            {
                _busy = false;
                _busyRing.Visibility = Visibility.Collapsed;
                RefreshAll();
            }
        }
    }

    private void RefreshAll()
    {
        RefreshStatus();
        RefreshSaved();
        RefreshForm();
    }

    /// <summary>The status read right before a change; null (and a message) when the drone does
    /// not answer or another drone answers at this address.</summary>
    private async Task<DroneApi.WifiStatus?> StatusForChangeAsync()
    {
        try
        {
            var s = await _app.Api.WifiStatusAsync();
            ApplyStatus(s);
            var check = DroneIdentity.Check(_app.DroneId, s.Id);
            if (check.Blocks)
            {
                Show(DroneIdentity.DifferentText(check.Now!, _app.DroneId ?? "?"), StatusBanner.Kind.Error);
                return null;
            }
            return s;
        }
        catch (Exception ex)
        {
            _statusError = DroneApi.Describe(ex);
            ShowError(ex);
            return null;
        }
    }

    private async Task<bool> ConfirmAsync(string title, string content, string primary)
    {
        var dlg = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = title,
            Content = content,
            PrimaryButtonText = primary,
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            RequestedTheme = ElementTheme.Dark,
        };
        try { return await dlg.ShowAsync() == ContentDialogResult.Primary; }
        catch { return false; }
    }

    private async Task ConfirmSwitchModeAsync(string mode)
    {
        var id = DroneId ?? "XXXX";
        var ok = await ConfirmAsync($"Switch {DroneLabel} to {mode}?",
            mode == "hotspot"
                ? $"{DroneLabel} will show its own hotspot Bumblebee-{id}; this PC loses it until it joins that hotspot."
                : $"{DroneLabel} drops its hotspot and joins a saved network (~60 s).",
            $"Switch to {mode}");
        if (!ok) return;
        Run(async () =>
        {
            if (await StatusForChangeAsync() is null) return;
            await _app.Api.WifiSetModeAsync(mode);
            Show(mode == "hotspot"
                ? $"{DroneLabel} is switching to its hotspot Bumblebee-{id}."
                : $"{DroneLabel} is leaving its hotspot for a saved network (~60 s).", StatusBanner.Kind.Success);
        });
    }

    private async Task AskRemoveAsync(string name)
    {
        if (!IsInUse(name)) { Remove(name, confirmActive: false); return; }
        await ConfirmRemoveAsync(name);
    }

    private async Task ConfirmRemoveAsync(string name)
    {
        var ok = await ConfirmAsync($"Remove {name} from {DroneLabel}?",
            $"{DroneLabel} is using {name} right now. Removing it disconnects the drone: it joins another " +
            $"saved network, or shows its own hotspot Bumblebee-{DroneId ?? "XXXX"}.",
            "Remove and disconnect");
        if (ok) Remove(name, confirmActive: true);
    }

    private void Remove(string name, bool confirmActive)
    {
        Run(async () =>
        {
            if (await StatusForChangeAsync() is null) return;
            try
            {
                await _app.Api.RemoveNetworkAsync(name, confirmActive);
            }
            catch (DroneApi.ApiException ex) when (ex.Code == "active_network")
            {
                // The drone says it is in use: ask first (after this change has finished).
                DispatcherQueue.TryEnqueue(() => _ = ConfirmRemoveAsync(name));
                return;
            }
            if (confirmActive)
            {
                Show($"Removing {name}: {DroneLabel} disconnects now.", StatusBanner.Kind.Success);
            }
            else
            {
                Show($"Removed {name}.", StatusBanner.Kind.Success);
                await LoadSavedAsync();
            }
        });
    }

    private void ApplyBoot()
    {
        var ssid = _addSsid.Text.Trim();
        var pass = _addPass.Text;
        Run(async () =>
        {
            if (await StatusForChangeAsync() is null) return;
            await _app.Api.SaveNetworkAsync(ssid, pass);
            await _app.Api.ApplyBootAsync(ssid);
            Show($"Saved {ssid} on {DroneLabel}: it is used at the next start-up, or when the current " +
                 "network goes away. This password could not be tested now.", StatusBanner.Kind.Success);
            await LoadSavedAsync();
        });
    }

    private void ApplyNow()
    {
        var ssid = _addSsid.Text.Trim();
        var pass = _addPass.Text;
        Run(async () =>
        {
            if (await StatusForChangeAsync() is not DroneApi.WifiStatus s) return;
            var id = _app.DroneId ?? s.Id;
            var drone = DroneLabel;
            try
            {
                await _app.Api.SaveNetworkAsync(ssid, pass);
                await _app.Api.ApplyNowAsync(ssid);
            }
            catch (DroneApi.ApiException ex) when (ex.Transport)
            {
                // Drone software before 1.0.1 switches before replying: it is on its way.
            }
            _app.Handoff.RefreshCurrentSsid();
            var next = ApplyFollowUp.Decide(ssid, _app.Handoff.CurrentSsid, id);
            Show(next.Text(drone, ssid), StatusBanner.Kind.Info);
            if (next.Kind != FollowUpKind.WaitHere || id is null) return;
            await WatchApplyAsync(ssid, id, drone);
        });
    }

    /// <summary>
    /// Follows an Apply Now through the drone's status until it is decided (ApplyWatch); the
    /// buttons stay disabled meanwhile, so a second press cannot meet the drone while it switches.
    /// </summary>
    private async Task WatchApplyAsync(string target, string id, string drone)
    {
        var started = MonoClock.Now;
        var watch = new ApplyWatch();
        var host = _app.DroneHost;
        while (true)
        {
            var elapsed = MonoClock.Now - started;
            if (elapsed >= ApplyWatch.FirstCheckSeconds)
            {
                var poll = await PollStatusAsync(host);
                var v = watch.Step(poll, elapsed, target);
                switch (v.Kind)
                {
                    case ApplyVerdictKind.Joined:
                        if (host != _app.DroneHost) _app.Connect(host);   // same address: rosbridge reconnects by itself
                        _app.DroneId = id;
                        Show(ApplyWatch.JoinedText(drone, target, host), StatusBanner.Kind.Success);
                        await RefreshStatusAsync();
                        await LoadSavedAsync();
                        return;
                    case ApplyVerdictKind.Failed:
                        Show(ApplyWatch.FailedText(drone, v.Reason!, v.TriedSsid!, v.CurrentSsid), StatusBanner.Kind.Caution);
                        await RefreshStatusAsync();
                        return;
                    case ApplyVerdictKind.NotFound:
                        Show(ApplyFollowUp.NotFoundText(drone, id, target), StatusBanner.Kind.Caution);
                        return;
                }
                if (watch.SawGone && !poll.Answered && await WifiHandoff.WaitForDroneAsync(id, 2) is string h)
                    host = h;                                    // it may have a new address on the target
            }
            await Task.Delay(TimeSpan.FromSeconds(ApplyWatch.IntervalSeconds));
        }
    }

    private static async Task<ApplyPoll> PollStatusAsync(string host)
    {
        try
        {
            var s = await new DroneApi { Host = host }.WifiStatusAsync();
            return new ApplyPoll(true, s.Mode, s.Ssid, s.LastError?.Reason, s.LastError?.Ssid);
        }
        catch
        {
            return ApplyPoll.NoAnswer;
        }
    }

    private static Color BandColor(string b) =>
        b == "5" ? Palette.Ok : (b == "6" ? Palette.Accent2 : Palette.Warn);
}
