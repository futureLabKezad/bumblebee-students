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
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml.Controls;

namespace BumblebeeGcs.Views;

/// <summary>«Copy diagnostics»: кладёт отчёт в буфер обмена и на пару секунд пишет «Copied».</summary>
public static class DiagnosticsButton
{
    public const string Tip = "Copies app and drone versions, connection state and recent messages (no passwords)";

    public static Button Create(AppState app, bool compact)
    {
        const string idle = "Copy diagnostics";
        var label = Ui.Text(idle, compact ? Fonts.Label with { Mono = true } : Fonts.ButtonSm,
            compact ? Palette.Muted : Palette.Text);
        Button b = compact
            ? Ui.FlatButton(label, () => { }, idle, Colors.Transparent, Palette.WithAlpha(Colors.White, 0.06),
                Palette.Muted, padding: new Microsoft.UI.Xaml.Thickness(6, 3, 6, 3))
            : Ui.GhostButton(idle, () => { });
        if (!compact) label = (TextBlock)b.Content;
        ToolTipService.SetToolTip(b, Tip);
        b.Click += async (_, _) =>
        {
            var ok = await app.CopyDiagnosticsAsync();
            label.Text = ok ? "Copied — paste it into a message" : "Couldn't use the clipboard";
            await Task.Delay(2500);
            label.Text = idle;
        };
        return b;
    }
}
