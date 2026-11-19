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

using System.Reflection;
using System.Security.Cryptography;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Web.WebView2.Core;

namespace BumblebeeGcs.Views;

/// <summary>
/// «Полёт»: the marker map, the Python flight program and its simulation -- the web module
/// gcs/web (Web\flight_embedded.html next to the exe) inside WebView2. The page is served
/// from a virtual host, cannot navigate away and has no network to the drone (its
/// Content-Security-Policy); it talks to the drone only through Logic/FlightBridge.cs.
/// A takeoff is confirmed in the app's own dialog here, which page code cannot press.
/// MainShell keeps one instance per connection (the editor and Python stay loaded) and has
/// its own STOP FLIGHT button, which does not depend on this page.
/// </summary>
public sealed class FlightPage : Grid
{
    private const string VirtualHost = "bbflight.example";
    private const string Origin = "https://" + VirtualHost;
    private const string PageUrl = Origin + "/flight_embedded.html";
    private const string HashPrefix = "FlightWeb:";      // assembly metadata: the files this app was built with
    private const int DialogSeconds = 60;                // an unanswered «Взлёт?» closes as «no»
    private const double YesAfterSeconds = 1.5;          // a window that pops up under the cursor is not a «yes»
    private const int UnresponsiveLimit = 3;             // «the page does not answer» that many times in a row

    private readonly AppState _app;
    private readonly WebView2 _web = new();
    private readonly TextBlock _note;
    private readonly FlightBridge _bridge;
    private bool _started;
    // The page left the window (Disconnect, another drone): no dialog, no replies, no takeoff.
    private bool _closed;
    private ContentDialog? _dialog;
    private int _unresponsive;

    /// <summary>A flight program this app started (or saw running) is on the drone.</summary>
    public bool MissionActive => _bridge.MissionActive;
    public event Action? MissionActiveChanged
    {
        add => _bridge.MissionActiveChanged += value;
        remove => _bridge.MissionActiveChanged -= value;
    }

    /// <summary>«Взлететь» was clicked and the start request is on its way to the drone.</summary>
    public bool TakeoffInFlight => _bridge.TakeoffInFlight;
    public event Action? TakeoffInFlightChanged
    {
        add => _bridge.TakeoffInFlightChanged += value;
        remove => _bridge.TakeoffInFlightChanged -= value;
    }

    /// <summary>The shell's STOP FLIGHT was pressed: a takeoff still on its way must not win.</summary>
    public void NoteStop() => _bridge.NoteStop();

    public FlightPage(AppState app)
    {
        _app = app;
        _bridge = new FlightBridge(new MissionApi(), ConfirmTakeoffAsync, () => (_app.DroneHost, _app.DroneName));
        _note = Ui.Text("Loading the Flight module…", Fonts.Body, Palette.Muted);
        _note.HorizontalAlignment = HorizontalAlignment.Center;
        _note.VerticalAlignment = VerticalAlignment.Center;
        _note.TextWrapping = TextWrapping.Wrap;
        _note.Margin = new Thickness(Palette.S4);
        _web.Visibility = Visibility.Collapsed;
        Children.Add(_note);
        Children.Add(_web);
        Loaded += async (_, _) => await StartAsync();
        // MainShell keeps this page in the tree while another section is shown (only collapsed),
        // so Unloaded means the shell itself is gone: close an open «Взлёт?» as «no» and stop
        // the page (its Python and its status polling) instead of waiting for the collector.
        Unloaded += (_, _) =>
        {
            _closed = true;
            try { _dialog?.Hide(); } catch { }
            try { _web.Close(); } catch { }
        };
    }

    private void Say(string text)
    {
        _note.Text = text;
        _note.Visibility = Visibility.Visible;
        _web.Visibility = Visibility.Collapsed;
    }

    /// <summary>Every file of the web module is the one this app was built with (their SHA-256
    /// are in the assembly): an edited page or Pyodide file next to the exe is not loaded.
    /// Null when all is well, else what to tell the person.</summary>
    private static async Task<string?> WebFilesProblemAsync(string folder)
    {
        var built = typeof(FlightPage).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
                                      .Where(a => a.Key.StartsWith(HashPrefix, StringComparison.Ordinal)).ToList();
        if (!built.Any(a => a.Key == HashPrefix + "flight_embedded.html"))
            return "This build has no checksum of the Flight page. Install Bumblebee GCS again.";
        foreach (var file in built)
        {
            var name = file.Key[HashPrefix.Length..];
            var path = Path.Combine(folder, name.Replace('/', Path.DirectorySeparatorChar));
            string onDisk;
            try { onDisk = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(path))); }
            catch (Exception ex) { return $"Web\\{name} cannot be read ({ex.GetType().Name}). Install Bumblebee GCS again."; }
            if (!string.Equals(file.Value, onDisk, StringComparison.OrdinalIgnoreCase))
                return $"Web\\{name} is not the file this app was built with. Install Bumblebee GCS again.";
        }
        return null;
    }

    private async Task StartAsync()
    {
        if (_started || _closed) return;
        _started = true;
        var folder = Path.Combine(AppContext.BaseDirectory, "Web");
        if (!File.Exists(Path.Combine(folder, "flight_embedded.html")))
        {
            Say("The Flight module files are missing (Web\\flight_embedded.html next to BumblebeeGcs.exe).");
            return;
        }
        var problem = await WebFilesProblemAsync(folder);
        if (_closed) return;
        if (problem is not null) { Say(problem); return; }
        try
        {
            // An unpackaged app: keep WebView2's profile with the app's other data, not next to the exe.
            // A folder the environment already names (a test run, a managed PC) is left as it is.
            if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER")))
                Environment.SetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER", Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BumblebeeGCS", "WebView2"));
            // No browser switches from the environment: a remote-debugging port would drive the page past DevTools being off.
            Environment.SetEnvironmentVariable("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", null);
            await _web.EnsureCoreWebView2Async();
        }
        catch (Exception ex)
        {
            Say("The Flight section needs the Microsoft Edge WebView2 Runtime (part of Windows 11; "
                + "for Windows 10 install it from microsoft.com). " + ex.Message);
            return;
        }
        var core = _web.CoreWebView2;
        if (_closed || core is null) return;
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.AreBrowserAcceleratorKeysEnabled = false;      // F12, F5, Ctrl+R...; typing and copy/paste stay
        core.Settings.AreHostObjectsAllowed = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.IsPasswordAutosaveEnabled = false;
        core.Settings.IsGeneralAutofillEnabled = false;
        core.SetVirtualHostNameToFolderMapping(VirtualHost, folder, CoreWebView2HostResourceAccessKind.DenyCors);
        // The page stays where it is. Its own blob: addresses are how it saves a map or a program to a file.
        core.NavigationStarting += (_, e) =>
        {
            if (e.Uri != PageUrl && !e.Uri.StartsWith("blob:" + Origin + "/", StringComparison.Ordinal)) e.Cancel = true;
        };
        core.NewWindowRequested += (_, e) => e.Handled = true;
        core.WebMessageReceived += OnWebMessage;
        core.ProcessFailed += OnProcessFailed;
        core.Navigate(PageUrl);
        _web.Visibility = Visibility.Visible;
        _note.Visibility = Visibility.Collapsed;
    }

    /// <summary>The page is hidden only when it is really gone: the browser or the page process
    /// exited, or the page did not answer several times in a row. The GPU and helper processes
    /// restart by themselves.</summary>
    private void OnProcessFailed(CoreWebView2 sender, CoreWebView2ProcessFailedEventArgs e)
    {
        if (_closed) return;
        var gone = e.ProcessFailedKind is CoreWebView2ProcessFailedKind.BrowserProcessExited
                                       or CoreWebView2ProcessFailedKind.RenderProcessExited;
        if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessUnresponsive)
            gone = ++_unresponsive >= UnresponsiveLimit;
        if (!gone) return;
        Say($"The Flight page stopped working ({e.ProcessFailedKind}). If a flight program is running, use STOP FLIGHT "
            + "at the top or the RC (CH8). Then press Disconnect and connect again.");
    }

    private async void OnWebMessage(CoreWebView2 sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            if (_closed || e.Source != PageUrl) return;
            _unresponsive = 0;                   // the page talks: it is alive
            var reply = await _bridge.HandleAsync(e.WebMessageAsJson);
            if (reply is not null && !_closed) sender.PostWebMessageAsJson(reply);
        }
        catch (Exception ex)
        {
            CrashLog.Write("FlightPage message", ex);
        }
    }

    /// <summary>Why «Взлёт?» cannot be asked now (the page gets these words), or null.</summary>
    private string? WhyNotAsk(TakeoffRequest r)
    {
        if (_closed || XamlRoot is null || !_app.Connected || _app.DroneHost != r.Host)
            return "the app is no longer connected to this drone: no takeoff";
        if (Visibility != Visibility.Visible) return "the Flight section is not shown now: open it and check the program again";
        if (_app.IdentityMismatch is not null)
            return "the app is asking whether this is the right drone: answer in its window and check the program again";
        return null;
    }

    /// <summary>The explicit human «yes» for a takeoff. Default button: Cancel; «Взлететь» wakes up
    /// after a moment; no answer in a minute is «no». «Yes» counts only while this page is still
    /// shown and the app is still connected to the drone the question names.</summary>
    private async Task<TakeoffAnswer> ConfirmTakeoffAsync(TakeoffRequest r)
    {
        if (WhyNotAsk(r) is { } early) return TakeoffAnswer.NotAsked(early);
        var dlg = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "Take off?",
            Content = TakeoffText.Body(r, _app.DroneName, LinkLogic.Text(_app.Telemetry.Link)),
            PrimaryButtonText = "Take off",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            IsPrimaryButtonEnabled = false,
            RequestedTheme = ElementTheme.Dark,
        };
        var expired = false;
        var wake = DispatcherQueue.CreateTimer();
        wake.Interval = TimeSpan.FromSeconds(YesAfterSeconds);
        wake.IsRepeating = false;
        wake.Tick += (_, _) => dlg.IsPrimaryButtonEnabled = true;
        var expire = DispatcherQueue.CreateTimer();
        expire.Interval = TimeSpan.FromSeconds(DialogSeconds);
        expire.IsRepeating = false;
        expire.Tick += (_, _) => { expired = true; try { dlg.Hide(); } catch { } };
        _dialog = dlg;
        try
        {
            wake.Start();
            expire.Start();
            ContentDialogResult result;
            try { result = await dlg.ShowAsync(); }
            catch { return TakeoffAnswer.NotAsked("another window of the app is open: close it and check the program again"); }
            if (result != ContentDialogResult.Primary)
                return TakeoffAnswer.Declined(expired ? $"the “Take off?” window closed by itself: no answer for {DialogSeconds} s" : "takeoff cancelled in the app’s window");
            return WhyNotAsk(r) is { } late ? TakeoffAnswer.Declined(late) : TakeoffAnswer.Go;
        }
        finally
        {
            _dialog = null;
            wake.Stop();
            expire.Stop();
        }
    }
}
