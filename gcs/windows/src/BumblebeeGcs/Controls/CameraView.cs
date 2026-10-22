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
using System.Runtime.InteropServices.WindowsRuntime;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;
using Windows.UI;

namespace BumblebeeGcs.Controls;

/// <summary>
/// Нативная MJPEG-камера. Владеет MjpegStream, пересобирает URL при смене
/// хоста/топика. Поддерживает переворот на 180°. Порт CameraView.swift.
/// Кадр старше 3 с накрывается «Video lost»; на ArUco-топиках без кадров 3 с —
/// подсказка вместо вечного спиннера (дрон публикует их только в ARMED/OFFBOARD).
/// </summary>
public sealed class CameraView : Grid
{
    public string Host = "";
    public string Topic = "";
    public int Quality = 60, Fps = 12, StreamWidth = 320, StreamHeight = 240;
    /// <summary>The small picture-in-picture: short ArUco hint, no hint under "Video lost" (as on the Mac).</summary>
    public bool Compact;

    private readonly MjpegStream _stream = new();
    private readonly Image _image;
    private readonly StackPanel _placeholder;
    private readonly ProgressRing _spinner;
    private readonly TextBlock _placeholderText;
    private readonly Grid _lostOverlay;
    private readonly TextBlock _lostCaption, _lostHint;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _statusTimer;
    private bool _flipped;
    private bool _decoding;
    private byte[]? _pendingFrame;
    private int _pendingId;
    private Uri? _startedUrl;
    private double? _lastFrameAt;
    private double _startedAt;

    public CameraView(bool showFlipButton = true)
    {
        Background = Palette.Brush(Colors.Black);

        _image = new Image
        {
            Stretch = Stretch.Uniform,
            RenderTransformOrigin = new Windows.Foundation.Point(0.5, 0.5),
        };
        Children.Add(_image);

        _spinner = new ProgressRing { IsActive = true, Width = 20, Height = 20 };
        _placeholderText = Ui.Text("waiting for video…", Fonts.MonoSmall, Palette.Muted);
        _placeholderText.TextWrapping = TextWrapping.Wrap;
        _placeholderText.TextAlignment = TextAlignment.Center;
        _placeholder = Ui.VStack(Palette.S2, _spinner, _placeholderText);
        _placeholder.HorizontalAlignment = HorizontalAlignment.Center;
        _placeholder.VerticalAlignment = VerticalAlignment.Center;
        _placeholder.Margin = new Thickness(Palette.S2);
        _placeholderText.HorizontalAlignment = HorizontalAlignment.Center;
        Children.Add(_placeholder);

        // «Video lost» поверх застывшего кадра.
        _lostCaption = Ui.Text("", Fonts.MonoSmall, Palette.Text);
        _lostCaption.HorizontalAlignment = HorizontalAlignment.Center;
        _lostHint = Ui.Text("", Fonts.MonoSmall, Palette.Muted);
        _lostHint.HorizontalAlignment = HorizontalAlignment.Center;
        _lostHint.TextAlignment = TextAlignment.Center;
        _lostHint.TextWrapping = TextWrapping.Wrap;
        var lostTitle = Ui.Text("Video lost", Fonts.BodyStrong, Palette.Caution);
        lostTitle.HorizontalAlignment = HorizontalAlignment.Center;
        var lostStack = Ui.VStack(Palette.S1, lostTitle, _lostCaption, _lostHint);
        lostStack.HorizontalAlignment = HorizontalAlignment.Center;
        lostStack.VerticalAlignment = VerticalAlignment.Center;
        lostStack.Margin = new Thickness(Palette.S2);
        _lostOverlay = new Grid
        {
            Background = Palette.Brush(Palette.WithAlpha(Colors.Black, 0.6)),
            Visibility = Visibility.Collapsed,
        };
        _lostOverlay.Children.Add(lostStack);
        Children.Add(_lostOverlay);

        if (showFlipButton)
        {
            var flip = Ui.OverlayIconButton(IconGlyphs.Flip, "Flip 180°", () =>
            {
                _flipped = !_flipped;
                _image.RenderTransform = _flipped ? new RotateTransform { Angle = 180 } : null;
            });
            flip.HorizontalAlignment = HorizontalAlignment.Right;
            flip.VerticalAlignment = VerticalAlignment.Top;
            flip.Margin = new Thickness(Palette.S1 + 2);
            Children.Add(flip);
        }

        var dq = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        _stream.FrameReady += (id, bytes) => dq.TryEnqueue(() => OnFrame(id, bytes));

        _statusTimer = dq.CreateTimer();
        _statusTimer.Interval = TimeSpan.FromMilliseconds(500);
        _statusTimer.Tick += (_, _) => UpdateStatus();

        Loaded += (_, _) => { Restart(); _statusTimer.Start(); };
        Unloaded += (_, _) => { _statusTimer.Stop(); _stream.Stop(); _startedUrl = null; };
    }

    private Uri? StreamUrl =>
        Uri.TryCreate($"http://{Host}:8080/stream?topic={Topic}&type=mjpeg&quality={Quality}&fps={Fps}&width={StreamWidth}&height={StreamHeight}",
            UriKind.Absolute, out var u) ? u : null;

    /// <param name="force">Reopen the stream even for the same URL (Reconnect).</param>
    public void Restart(bool force = false)
    {
        if (StreamUrl is not Uri url || string.IsNullOrEmpty(Host)) return;
        if (!force && _startedUrl == url) return;
        _startedUrl = url;
        // Новый топик/соединение: старый кадр и кадр в очереди декодера не показываем.
        _image.Source = null;
        _pendingFrame = null;
        _lastFrameAt = null;
        _startedAt = MonoClock.Now;
        _stream.Start(url, force);   // cancels the previous connection first: one stream per view
        UpdateStatus();
    }

    public void SetTopic(string topic)
    {
        if (Topic == topic) return;
        Topic = topic;
        Restart();
    }

    private void UpdateStatus()
    {
        var now = MonoClock.Now;
        var aruco = VideoLogic.IsArucoTopic(Topic);
        var hint = Compact ? VideoLogic.ArucoHintShort : VideoLogic.ArucoHint;
        var state = _startedUrl is null ? VideoState.Waiting : VideoLogic.Compute(_lastFrameAt, _startedAt, now, aruco);
        switch (state)
        {
            case VideoState.Live:
                _placeholder.Visibility = Visibility.Collapsed;
                _lostOverlay.Visibility = Visibility.Collapsed;
                break;
            case VideoState.Lost:
                _placeholder.Visibility = Visibility.Collapsed;
                _lostCaption.Text = VideoLogic.LostCaption(now - (_lastFrameAt ?? now));
                var showHint = aruco && !Compact;
                _lostHint.Text = showHint ? hint : "";
                _lostHint.Visibility = showHint ? Visibility.Visible : Visibility.Collapsed;
                _lostOverlay.Visibility = Visibility.Visible;
                break;
            case VideoState.NoArucoFrames:
                _lostOverlay.Visibility = Visibility.Collapsed;
                _spinner.Visibility = Visibility.Collapsed;
                _spinner.IsActive = false;
                _placeholderText.Text = hint;
                _placeholder.Visibility = Visibility.Visible;
                break;
            default:
                _lostOverlay.Visibility = Visibility.Collapsed;
                _spinner.Visibility = Visibility.Visible;
                _spinner.IsActive = true;
                _placeholderText.Text = "waiting for video…";
                _placeholder.Visibility = Visibility.Visible;
                break;
        }
    }

    /// <summary>Декодируем только свежайший кадр: если декодер занят — кадр ждёт (и замещается).</summary>
    private async void OnFrame(int id, byte[] jpeg)
    {
        if (id != _stream.CurrentId) return;   // кадр прошлого топика/соединения
        _lastFrameAt = MonoClock.Now;
        if (_decoding)
        {
            _pendingFrame = jpeg;
            _pendingId = id;
            return;
        }
        _decoding = true;
        try
        {
            while (true)
            {
                using var ms = new InMemoryRandomAccessStream();
                await ms.WriteAsync(jpeg.AsBuffer());
                ms.Seek(0);
                var bmp = new BitmapImage();
                await bmp.SetSourceAsync(ms);
                // Топик могли сменить, пока шло декодирование.
                if (id == _stream.CurrentId)
                {
                    _image.Source = bmp;
                    UpdateStatus();
                }
                if (_pendingFrame is null) break;
                jpeg = _pendingFrame;
                id = _pendingId;
                _pendingFrame = null;
            }
        }
        catch { /* битый кадр — ждём следующий */ }
        finally { _decoding = false; }
    }
}
