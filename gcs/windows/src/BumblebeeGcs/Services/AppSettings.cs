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

using System.Text.Json;
using BumblebeeGcs.Models;

namespace BumblebeeGcs.Services;

/// <summary>Персистентные настройки (замена UserDefaults): lastHost и «флот» знакомых дронов.</summary>
public sealed class AppSettings
{
    public string? LastHost { get; set; }
    /// <summary>Последняя обычная (не `Bumblebee-*`) WiFi этого ПК — её отдаём дрону,
    /// даже если ПК сейчас сидит на хотспоте дрона.</summary>
    public string? LastHomeSsid { get; set; }
    public List<KnownDrone> KnownDrones { get; set; } = new();

    private static string Dir =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BumblebeeGCS");
    private static string FilePath => Path.Combine(Dir, "settings.json");

    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
                return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(FilePath)) ?? new AppSettings();
        }
        catch { }
        return new AppSettings();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Dir);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(this, JsonOpts));
        }
        catch { }
    }
}
