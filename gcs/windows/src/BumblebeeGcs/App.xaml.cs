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

using BumblebeeGcs.Services;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;

namespace BumblebeeGcs;

public partial class App : Application
{
    public static AppState State { get; private set; } = null!;
    public static MainWindow? Window { get; private set; }

    public App()
    {
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        CrashLog.Install(this);               // журнал падений для «Скопировать диагностику»
        State = new AppState(DispatcherQueue.GetForCurrentThread());
        State.Scanner.StartDiscovery();       // непрерывный DNS-SD
        State.Scanner.Scan();                 // разовый субнет-фолбэк
        _ = State.Handoff.RequestLocationAsync(); // выяснить разрешение на WiFi-скан заранее

        Window = new MainWindow();
        Window.Activate();

        // Тестовый хук: BumblebeeGcs.exe --connect <host> подключается сразу
        // (используется для end-to-end прогонов с SimDrone).
        var cli = Environment.GetCommandLineArgs();
        var idx = Array.IndexOf(cli, "--connect");
        if (idx >= 0 && idx + 1 < cli.Length)
            State.Connect(cli[idx + 1]);
    }
}
