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

using System.Text;
using BumblebeeGcs.Logic;

namespace BumblebeeGcs.Services;

/// <summary>
/// Журнал падений: %LOCALAPPDATA%\BumblebeeGCS\crash.log. Необработанные исключения UI-потока,
/// фоновых потоков и брошенных задач дописываются туда (новейшие 256 КБ); последняя запись
/// попадает в «Скопировать диагностику». Формат — Logic/Diagnostics.cs (CrashLogFormat).
/// </summary>
public static class CrashLog
{
    public static string FilePath =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BumblebeeGCS", "crash.log");

    private static readonly object Lock = new();

    public static void Install(Microsoft.UI.Xaml.Application app)
    {
        app.UnhandledException += (_, e) => Write("unhandled UI exception", e.Exception);
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            if (e.ExceptionObject is Exception ex) Write("unhandled exception", ex);
        };
        TaskScheduler.UnobservedTaskException += (_, e) => Write("unobserved task exception", e.Exception);
    }

    public static void Write(string kind, Exception ex)
    {
        try
        {
            lock (Lock)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
                var old = File.Exists(FilePath) ? File.ReadAllText(FilePath, Encoding.UTF8) : "";
                var entry = CrashLogFormat.Entry(DateTime.UtcNow, AppVersion.Label, kind, ex);
                File.WriteAllText(FilePath, CrashLogFormat.Append(old, entry), Encoding.UTF8);
            }
        }
        catch { /* the log must never crash the app itself */ }
    }

    /// <summary>The newest entry's first line and the file, or null if nothing was recorded.</summary>
    public static string? Last()
    {
        try
        {
            if (!File.Exists(FilePath)) return null;
            return CrashLogFormat.LastEntryHeader(File.ReadAllText(FilePath, Encoding.UTF8)) is string line
                ? $"{line} ({FilePath})" : null;
        }
        catch { return null; }
    }
}
