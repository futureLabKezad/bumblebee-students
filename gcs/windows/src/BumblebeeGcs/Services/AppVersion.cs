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

namespace BumblebeeGcs.Services;

/// <summary>The app version shown on screen, so a teacher can tell which build a
/// laptop runs. Comes from &lt;Version&gt; in the csproj (gcs/VERSION is the source;
/// check_versions.py keeps them equal); the "+commit" suffix the SDK adds is dropped.</summary>
public static class AppVersion
{
    public static string Short { get; } = Read();
    public static string Label => "GCS " + Short;

    private static string Read()
    {
        var asm = typeof(AppVersion).Assembly;
        var v = asm.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
                ?? asm.GetName().Version?.ToString(3)
                ?? "dev";
        var plus = v.IndexOf('+');
        return plus >= 0 ? v[..plus] : v;
    }
}
