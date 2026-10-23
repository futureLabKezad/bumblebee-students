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
/// LED, шоу, зуммер и TTS. Порт EntertainmentView.swift. Что идёт на дроне, берётся из
/// GET /api/led/status (опрос, пока страница открыта), а не из того, что страница отправила
/// последним: переход между разделами, другой ноутбук и 2-минутный лимит дрона видны здесь.
/// Решения — в Logic/EntertainmentLogic.cs.
/// </summary>
public sealed class EntertainmentPage : Grid
{
    private enum LedKind { Color, Anim, None }

    private readonly AppState _app;

    private Color _color = Colors.White;
    private bool _isOn = true;
    private (LedKind Kind, Color Color, string Anim) _lastState = (LedKind.Color, Colors.White, "");
    private DroneApi.LedStatus? _led;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _colorDebounce, _ledPoll;

    private readonly TextBlock _hexLabel;
    private readonly Button _onOffBtn;
    private readonly StatusBanner _ledBanner = new();
    private readonly List<(string Name, ChipButton Chip)> _chips = new();
    private readonly PanelCard _animPanel, _showsPanel;
    private readonly Button _stopAnimBtn, _stopShowBtn;
    private readonly List<Button> _soundButtons = new();
    private readonly StatusBanner _soundGate = new(), _ttsGate = new();
    private readonly GlassTextField _customTune;
    private readonly SegmentedTabs _fmtTabs;
    private readonly Button _playBtn;
    private readonly StatusBanner _soundBanner = new();
    private readonly GlassTextField _ttsText;
    private readonly SegmentedTabs _langTabs;
    private readonly Button _speakBtn;
    private readonly StatusBanner _ttsBanner = new();
    private readonly Action _onTelemetry;
    private string? _gateShown = "\0";   // reason the sound buttons last showed (sentinel: never)

    private static readonly (string Name, string Tune, string Fmt)[] Presets =
    {
        ("beep", "MFT100L16O5C", "QBASIC"),
        ("ok", "MFT180L8O5CEG", "QBASIC"),
        ("error", "MFT180L8O5GEC<G", "QBASIC"),
        ("notify", "MFT180L8O5E4C4", "QBASIC"),
        ("arming", "MFT180L8O4G4O5C4", "QBASIC"),
        ("imperial", "MFT120L4O4GGGL8E<L16B>L4GL8E<L16B>L2G", "QBASIC"),
        ("mario", "MFT200L8O5EEP8EP8CEP8GP8P4<GP4", "QBASIC"),
        ("tetris", "MFT160L4O5EL8BL8>CL4DL8>CL8<BL4AL8AL8>CL4EL8DL8>C", "QBASIC"),
    };

    private static readonly string[] Languages = { "en", "ru", "de", "fr", "es" };

    private string? Running => _led?.Animation;
    private string? SoundBlocked => SoundGate.BlockedReason(_app.Telemetry.Armed);

    public EntertainmentPage(AppState app)
    {
        _app = app;
        var dq = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();

        // MARK: LED panel
        var picker = new ColorPicker
        {
            IsAlphaEnabled = false,
            Color = Colors.White,
            IsColorChannelTextInputVisible = false,
            IsHexInputVisible = false,
            IsColorSliderVisible = true,
            IsColorPreviewVisible = false,
            Width = 260,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        _colorDebounce = dq.CreateTimer();
        _colorDebounce.Interval = TimeSpan.FromMilliseconds(120);
        _colorDebounce.IsRepeating = false;
        _colorDebounce.Tick += (_, _) =>
        {
            var (r, g, b) = Rgb;
            Led(async () =>
            {
                await _app.Api.LedColorAsync(r, g, b);
                _app.StartedLedAnimation = false;     // a colour replaces the animation on the drone
                _lastState = (LedKind.Color, _color, "");
                _isOn = true;
            });
        };
        picker.ColorChanged += (_, e) =>
        {
            _color = e.NewColor;
            _hexLabel!.Text = HexString;
            _colorDebounce.Stop();
            _colorDebounce.Start();
        };

        _hexLabel = Ui.Text("#FFFFFF", Fonts.Mono, Palette.Muted);
        _onOffBtn = Ui.GhostButton("Off", ToggleOnOff);
        var resetBtn = Ui.GhostButton("Reset", Stop);
        ToolTipService.SetToolTip(resetBtn, "Stop colours and animations; the drone shows its own status lights again");
        var ledRow = Ui.SpaceBetween(_hexLabel, Ui.HStack(Palette.S2, _onOffBtn, resetBtn));
        var ledPanel = new PanelCard("LED Color", IconGlyphs.LedColor, picker, ledRow, _ledBanner);

        // MARK: Animations and shows
        _stopAnimBtn = Ui.GhostButton("Stop", Stop);
        _stopShowBtn = Ui.GhostButton("Stop", Stop);
        _animPanel = new PanelCard("Animations", IconGlyphs.Sparkles, ChipGrid(LedCatalog.Animations, false), _stopAnimBtn);
        _showsPanel = new PanelCard("Shows (Light + Sound)", IconGlyphs.Speaker, ChipGrid(LedCatalog.Shows, true), _stopShowBtn);

        // MARK: Buzzer panel
        var presetGrid = new AdaptiveGridPanel { MinItemWidth = 80, Spacing = Palette.S2 };
        foreach (var (name, tune, fmt) in Presets)
        {
            var b = Ui.GhostButton(name, () => Sound(_soundBanner, async () =>
            {
                await _app.Api.PlayTuneAsync(tune, fmt);
                return LedText.Sent(name);
            }));
            b.HorizontalAlignment = HorizontalAlignment.Stretch;
            b.HorizontalContentAlignment = HorizontalAlignment.Center;
            _soundButtons.Add(b);
            presetGrid.Children.Add(b);
        }
        _customTune = new GlassTextField("Custom tune");
        _fmtTabs = new SegmentedTabs(new[] { ("QBASIC", "QBASIC"), ("MML", "MML") }, "QBASIC");
        _playBtn = Ui.AccentButton("Play Tune", () => Sound(_soundBanner, async () =>
        {
            await _app.Api.PlayTuneAsync(_customTune.Text, _fmtTabs.Selection);
            return LedText.Sent("custom tune");
        }));
        _customTune.TextChanged += RefreshSoundGate;
        var playRow = Ui.HStack(Palette.S2, _fmtTabs, _playBtn);
        var soundsPanel = new PanelCard("Buzzer", IconGlyphs.Speaker, _soundGate, presetGrid, _customTune, playRow, _soundBanner);

        // MARK: TTS panel
        _ttsText = new GlassTextField("Text to speak");
        _langTabs = new SegmentedTabs(Languages.Select(l => (l.ToUpperInvariant(), l)), "en");
        _speakBtn = Ui.AccentButton("Speak", () =>
        {
            var text = _ttsText.Text;
            Sound(_ttsBanner, async () =>
            {
                await _app.Api.TtsAsync(text, _langTabs.Selection);
                return LedText.Sent($"\"{text}\"");
            });
        });
        _ttsText.TextChanged += RefreshSoundGate;
        var ttsPanel = new PanelCard("Speech (TTS)", IconGlyphs.Tts, _ttsGate, _ttsText, _langTabs, _speakBtn);
        ttsPanel.Add(_ttsBanner);

        // MARK: Layout
        var grid = new AdaptiveGridPanel { MinItemWidth = 320, Spacing = Palette.S4, MaxWidth = 980 };
        grid.Children.Add(ledPanel);
        grid.Children.Add(_animPanel);
        grid.Children.Add(_showsPanel);
        grid.Children.Add(soundsPanel);
        grid.Children.Add(ttsPanel);
        grid.HorizontalAlignment = HorizontalAlignment.Center;

        var host = new Grid { Padding = new Thickness(Palette.S4) };
        host.Children.Add(grid);
        var scroll = new ScrollViewer { Content = host, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Children.Add(scroll);

        // What runs on the drone, every 2.5 s while the page is open.
        _ledPoll = dq.CreateTimer();
        _ledPoll.Interval = TimeSpan.FromMilliseconds(2500);
        _ledPoll.Tick += (_, _) => _ = PollLedAsync();

        // Sound buttons follow armed/unknown from the telemetry (Updated: every message and
        // the 500 ms clock; redrawn only when the reason changes).
        _onTelemetry = () => { if (SoundBlocked != _gateShown) RefreshSoundGate(); };
        Loaded += (_, _) =>
        {
            _app.Telemetry.Updated += _onTelemetry;
            _ledPoll.Start();
            _ = PollLedAsync();
        };
        Unloaded += (_, _) =>
        {
            _app.Telemetry.Updated -= _onTelemetry;
            _colorDebounce.Stop();
            _ledPoll.Stop();
        };

        RefreshLed();
        RefreshSoundGate();
    }

    private AdaptiveGridPanel ChipGrid(string[] names, bool sound)
    {
        var grid = new AdaptiveGridPanel { MinItemWidth = 90, Spacing = Palette.S2 };
        foreach (var name in names)
        {
            var label = LedCatalog.Label(name) + (sound ? " ♪" : "");
            // A second click on the running one stops it.
            var chip = new ChipButton(label, false, () => { if (Running == name) Stop(); else Start(name); }, fullWidth: true);
            _chips.Add((name, chip));
            grid.Children.Add(chip);
        }
        return grid;
    }

    // MARK: - LED state from the drone

    private async Task PollLedAsync()
    {
        try
        {
            _led = await _app.Api.LedStatusAsync();
            if (_led?.Animation is null) _app.StartedLedAnimation = false;
        }
        catch { /* keep the last known state; errors show on actions */ }
        RefreshLed();
    }

    private void RefreshLed()
    {
        var running = Running;
        foreach (var (name, chip) in _chips) chip.SetSelected(name == running);
        SetRunning(_animPanel, _stopAnimBtn, LedCatalog.Animations, running);
        SetRunning(_showsPanel, _stopShowBtn, LedCatalog.Shows, running);
        ((TextBlock)_onOffBtn.Content).Text = _isOn ? "Off" : "On";
    }

    /// <summary>"Rainbow · stops by itself in 1:45" and a Stop button while one of names runs.</summary>
    private void SetRunning(PanelCard panel, Button stop, string[] names, string? running)
    {
        var here = running is not null && names.Contains(running);
        if (here)
        {
            var parts = new[] { LedCatalog.Label(running!), LedText.Remaining(_led?.Remaining) }.Where(p => p is not null);
            panel.SetNote(string.Join(" · ", parts));
            ((TextBlock)stop.Content).Text = "Stop " + LedCatalog.Label(running!);
        }
        else
        {
            panel.SetNote(null);
        }
        stop.Visibility = here ? Visibility.Visible : Visibility.Collapsed;
    }

    // MARK: - LED actions

    private (int R, int G, int B) Rgb => (_color.R, _color.G, _color.B);
    private string HexString => $"#{_color.R:X2}{_color.G:X2}{_color.B:X2}";

    /// <summary>An LED request; its error shows in the LED panel, then the drone's state is re-read.</summary>
    private void Led(Func<Task> op)
    {
        _ = Core();
        async Task Core()
        {
            try { await op(); _ledBanner.Hide(); }
            catch (Exception ex) { _ledBanner.Show(DroneApi.Describe(ex), StatusBanner.Kind.Error); }
            await PollLedAsync();
        }
    }

    private void Start(string name) => Led(async () =>
    {
        await _app.Api.LedAnimationAsync(name);
        _app.StartedLedAnimation = true;
        _lastState = (LedKind.Anim, default, name);
        _isOn = true;
    });

    /// <summary>Reset: stops any animation or colour; the drone's status lights return.</summary>
    private void Stop() => Led(async () =>
    {
        await _app.Api.LedResetAsync();
        _app.StartedLedAnimation = false;
        _lastState = (LedKind.None, default, "");
    });

    private void ToggleOnOff()
    {
        if (_isOn)
        {
            Led(async () =>
            {
                await _app.Api.LedColorAsync(0, 0, 0);
                _app.StartedLedAnimation = false;
                _isOn = false;
            });
        }
        else
        {
            var (kind, color, anim) = _lastState;
            Led(async () =>
            {
                switch (kind)
                {
                    case LedKind.Anim:
                        await _app.Api.LedAnimationAsync(anim);
                        _app.StartedLedAnimation = true;
                        break;
                    case LedKind.Color: await _app.Api.LedColorAsync(color.R, color.G, color.B); break;
                    default: await _app.Api.LedResetAsync(); break;
                }
                _isOn = true;
            });
        }
    }

    // MARK: - Sounds

    private void RefreshSoundGate()
    {
        var why = SoundBlocked;
        _gateShown = why;
        foreach (var gate in new[] { _soundGate, _ttsGate })
        {
            if (why is null) gate.Hide(); else gate.Show(why, StatusBanner.Kind.Caution);
        }
        foreach (var b in _soundButtons) b.IsEnabled = why is null;
        _playBtn.IsEnabled = why is null && _customTune.Text.Length > 0;
        _speakBtn.IsEnabled = why is null && _ttsText.Text.Length > 0;
    }

    /// <summary>A tune or speech request; "Sent to the drone" on success, the reason otherwise.</summary>
    private void Sound(StatusBanner banner, Func<Task<string>> op)
    {
        _ = Core();
        async Task Core()
        {
            try { banner.Show(await op(), StatusBanner.Kind.Success); }
            catch (Exception ex) { banner.Show(DroneApi.Describe(ex), StatusBanner.Kind.Error); }
        }
    }
}
