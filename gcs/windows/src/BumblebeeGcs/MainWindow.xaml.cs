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

using System.Runtime.InteropServices;
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using BumblebeeGcs.Views;
using Microsoft.UI.Windowing;
using BumblebeeGcs.Logic;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Input;
using Windows.System;

namespace BumblebeeGcs;

public sealed partial class MainWindow : Window
{
    private bool _booted;

    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(nint hwnd);

    public MainWindow()
    {
        InitializeComponent();
        Title = $"Bumblebee GCS {AppVersion.Short}";
        SetupWindowChrome();
        SetupShortcuts();

        App.State.ConnectedChanged += RefreshRoot;
        Closed += (_, _) =>
        {
            App.State.ConnectedChanged -= RefreshRoot;
            // A show this session started stops with the app (the drone's 2-minute limit is the backstop).
            App.State.StopOwnLedAnimation(waitMs: 1500);
        };

        // Короткий статичный boot-экран; скан сети уже запущен в App.OnLaunched,
        // так что дроны успевают появиться, пока висит сплэш.
        RefreshRoot();
        var timer = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        timer.Interval = TimeSpan.FromSeconds(1.3);
        timer.IsRepeating = false;
        timer.Tick += (_, _) =>
        {
            _booted = true;
            RefreshRoot();
        };
        timer.Start();
    }

    private void SetupWindowChrome()
    {
        var appWindow = AppWindow;
        try { appWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico")); } catch { }

        var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var scale = GetDpiForWindow(hwnd) / 96.0;
        try
        {
            // Fit the screen without the taskbar (150 % on 1920x1080, a 1366x768 projector).
            var work = DisplayArea.GetFromWindowId(appWindow.Id, DisplayAreaFallback.Primary).WorkArea;
            var (w, h, minW, minH) = WindowFit.Size(1280, 820, 1100, 720, scale, work.Width, work.Height);
            appWindow.Resize(new Windows.Graphics.SizeInt32(w, h));
            appWindow.Move(new Windows.Graphics.PointInt32(work.X + (work.Width - w) / 2, work.Y + (work.Height - h) / 2));
            if (appWindow.Presenter is OverlappedPresenter presenter)
            {
                presenter.PreferredMinimumWidth = minW;
                presenter.PreferredMinimumHeight = minH;
            }
        }
        catch { }

        // Тёмный титлбар в тон фону приложения.
        try
        {
            if (AppWindowTitleBar.IsCustomizationSupported())
            {
                var tb = appWindow.TitleBar;
                tb.BackgroundColor = Palette.Bg;
                tb.InactiveBackgroundColor = Palette.Bg;
                tb.ForegroundColor = Palette.Text;
                tb.InactiveForegroundColor = Palette.Muted;
                tb.ButtonBackgroundColor = Palette.Bg;
                tb.ButtonInactiveBackgroundColor = Palette.Bg;
                tb.ButtonForegroundColor = Palette.Text;
                tb.ButtonInactiveForegroundColor = Palette.Muted;
                tb.ButtonHoverBackgroundColor = Palette.SurfaceRaised;
                tb.ButtonHoverForegroundColor = Palette.Text;
            }
        }
        catch { }
    }

    private void SetupShortcuts()
    {
        AddShortcut(VirtualKey.R, VirtualKeyModifiers.Control, () => App.State.Reconnect());
        AddShortcut(VirtualKey.K, VirtualKeyModifiers.Control, () => App.State.Scanner.Scan());
        AddShortcut(VirtualKey.D, VirtualKeyModifiers.Control | VirtualKeyModifiers.Shift, () => App.State.Disconnect());
    }

    private void AddShortcut(VirtualKey key, VirtualKeyModifiers mods, Action action)
    {
        var acc = new KeyboardAccelerator { Key = key, Modifiers = mods };
        acc.Invoked += (_, e) =>
        {
            action();
            e.Handled = true;
        };
        Root.KeyboardAccelerators.Add(acc);
    }

    private void RefreshRoot()
    {
        Title = App.State.Connected ? $"{App.State.DroneHost} — Bumblebee GCS {AppVersion.Short}" : $"Bumblebee GCS {AppVersion.Short}";
        Root.Children.Clear();
        if (!_booted)
            Root.Children.Add(new SplashView());
        else if (App.State.Connected)
            Root.Children.Add(new MainShell(App.State));
        else
            Root.Children.Add(new LaunchView(App.State));
    }
}
