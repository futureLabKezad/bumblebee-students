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

using System.Globalization;
using System.Text;

namespace BumblebeeGcs.Logic;

// The Settings screen's decisions, without WinUI so the tests can check them:
// what an error reply means, whether a password can be sent, which networks must
// not be touched, whether we still talk to the same drone and what to do after
// "Apply Now". Same rules as the Mac app (SettingsLogic.swift).

/// <summary>Plain words for an error reply. Drones from 1.0.2 send a stable code; older ones only "error".</summary>
public static class DroneErrorText
{
    public static string Text(string? code, string? error, int status) => code switch
    {
        "armed" => "Refused: the drone is ARMED. Disarm it first.",
        "fc_unknown" => "Refused: the flight controller is not answering, so the drone counts as armed. " +
                        "Check that the flight controller is powered and connected.",
        "protected_network" => "That is a drone's own setup hotspot: it cannot be saved, joined or removed here.",
        "bad_password_length" => PasswordCheck.Text(PasswordResult.Length),
        "unknown_network" => "The drone has no saved network with that name.",
        "nmcli_timeout" => "The drone's network manager did not answer in time. Try again.",
        "nmcli_failed" => "The drone's network manager reported an error (details in the drone's log).",
        "led_unavailable" => "The drone's LED driver is not running.",
        "drone_unavailable" => "The drone's flight library did not load (see the drone's log).",
        "tts_unavailable" => "Speech is not installed on this drone.",
        _ => string.IsNullOrEmpty(error) ? $"HTTP {status}" : error,
    };

    /// <summary>The request never got an answer (drone off, out of range, other network).</summary>
    public static string NoAnswer(string detail) => $"No answer from the drone ({detail}).";
}

/// <summary>Why the drone's last requested Wi-Fi join failed (last_error.reason).</summary>
public static class JoinReasonText
{
    public static string Text(string reason, string ssid) => reason switch
    {
        "wrong_password" => $"wrong password for {ssid}",
        "not_found" => $"the drone can't see {ssid}",
        "no_ip" => $"{ssid} didn't give the drone an address",
        "timeout" => $"joining {ssid} took too long",
        "armed" or "fc_unknown" => $"not switched to {ssid}: the drone counted as armed",
        _ => $"the drone couldn't join {ssid}",
    };

    /// <summary>
    /// Banner for a recorded failure, or null when it is older than maxAge (the drone keeps it
    /// until the next Apply Now). Drones before 1.0.1 send no time: shown without one.
    /// </summary>
    public static string? Banner(string ssid, string reason, DateTime? timeUtc, DateTime nowUtc, TimeSpan? maxAge = null)
    {
        var limit = maxAge ?? TimeSpan.FromMinutes(30);
        if (timeUtc is DateTime t && nowUtc - t > limit) return null;
        var what = Text(reason, ssid);
        return timeUtc is DateTime at
            ? $"Last Wi-Fi change at {at.ToLocalTime().ToString("HH:mm", CultureInfo.InvariantCulture)} failed: {what}."
            : $"Last Wi-Fi change failed: {what}.";
    }
}

public static class WifiNames
{
    public const string HotspotProfile = "bumblebee-hotspot";

    /// <summary>A drone's own setup hotspot (any drone's) or a drone-side pending profile.</summary>
    public static bool IsProtected(string name)
    {
        var n = name.Trim().ToLowerInvariant();
        return n == HotspotProfile || n.StartsWith("bumblebee-", StringComparison.Ordinal)
               || n.EndsWith(".bb-pending", StringComparison.Ordinal);
    }

    /// <summary>nmcli reports an open network's security as "" or "--".</summary>
    public static bool IsSecured(string security)
    {
        var s = security.Trim();
        return s.Length > 0 && s != "--";
    }

    /// <summary>A scan SSID and a NetworkManager profile name (status.ssid) of the same network;
    /// the image's netplan profiles are named "netplan-wlan0-SSID".</summary>
    public static bool Same(string ssid, string profile) =>
        ssid.Length > 0 && profile.Length > 0 && (profile == ssid || profile == "netplan-wlan0-" + ssid);
}

public enum PasswordResult { Ok, Missing, Length, Spaces }

/// <summary>What may be sent as a Wi-Fi password. The drone strips spaces at both ends, so such a
/// password would silently change: refused here with a reason.</summary>
public static class PasswordCheck
{
    public static PasswordResult Check(string password, bool needsPassword)
    {
        if (password.Length == 0) return needsPassword ? PasswordResult.Missing : PasswordResult.Ok;
        if (password[0] == ' ' || password[^1] == ' ') return PasswordResult.Spaces;
        var size = Encoding.UTF8.GetByteCount(password);
        if (size == 64) return password.All(Uri.IsHexDigit) ? PasswordResult.Ok : PasswordResult.Length;
        return size is >= 8 and <= 63 ? PasswordResult.Ok : PasswordResult.Length;
    }

    /// <summary>A network not in the scan and not saved is taken as protected.</summary>
    public static bool NeedsPassword(bool saved, bool? secured) => !saved && (secured ?? true);

    public static string? Text(PasswordResult r) => r switch
    {
        PasswordResult.Missing => "This network needs a password.",
        PasswordResult.Length => "A Wi-Fi password has 8 to 63 characters (or exactly 64 hex digits).",
        PasswordResult.Spaces => "The password starts or ends with a space; the drone cannot use such a password.",
        _ => null,
    };
}

public enum IdentityKind { Same, Unknown, Different }

/// <summary>
/// Settings changes the drone at the address it connected to; the id it reports there must
/// still be the one seen at the start (10.42.0.1 is every drone's hotspot address, DHCP can
/// give an address to another drone).
/// </summary>
public readonly record struct DroneIdentity(IdentityKind Kind, string? Now = null)
{
    public bool Blocks => Kind == IdentityKind.Different;

    public static DroneIdentity Check(string? expected, string? reported)
    {
        if (string.IsNullOrEmpty(expected) || string.IsNullOrEmpty(reported)) return new(IdentityKind.Unknown);
        return string.Equals(expected, reported, StringComparison.OrdinalIgnoreCase)
            ? new(IdentityKind.Same)
            : new(IdentityKind.Different, reported.ToUpperInvariant());
    }

    public static string DifferentText(string now, string expected) =>
        $"This address now answers as Bumblebee-{now}, not Bumblebee-{expected}. " +
        "Nothing was changed. Reconnect from the drone list.";
}

public enum FollowUpKind { WaitHere, OtherNetwork, NoId }

/// <summary>The drone leaves its network for the target one. Where to look for it.</summary>
public readonly record struct ApplyFollowUp(FollowUpKind Kind, string? ComputerSsid = null)
{
    public static ApplyFollowUp Decide(string target, string computerSsid, string? droneId)
    {
        if (string.IsNullOrEmpty(droneId)) return new(FollowUpKind.NoId);
        if (computerSsid.Length == 0 || WifiNames.Same(computerSsid, target)) return new(FollowUpKind.WaitHere);
        return new(FollowUpKind.OtherNetwork, computerSsid);
    }

    public string Text(string drone, string target) => Kind switch
    {
        FollowUpKind.WaitHere => $"{drone} is switching to {target}… looking for it there.",
        FollowUpKind.OtherNetwork => $"{drone} is switching to {target}. This PC is on {ComputerSsid}: " +
                                     $"connect it to {target} and pick the drone in the list.",
        _ => $"{drone} is switching to {target}. Its software is too old to be found " +
             "automatically: pick it in the drone list once it is there.",
    };

    public static string NotFoundText(string drone, string id, string target) =>
        $"{drone} did not show up on {target}. If the password was wrong it goes back to its " +
        "previous network within about 2 minutes; if it cannot, it shows its own hotspot " +
        $"Bumblebee-{id} in the drone list.";
}

/// <summary>One read of the drone's status while an Apply Now is followed (Answered false: no reply).</summary>
public readonly record struct ApplyPoll(bool Answered, string Mode = "", string Ssid = "",
                                        string? ErrorReason = null, string? ErrorSsid = null)
{
    public static readonly ApplyPoll NoAnswer = new(false);
}

public enum ApplyVerdictKind { Waiting, Joined, Failed, NotFound }

public readonly record struct ApplyVerdict(ApplyVerdictKind Kind, string? Reason = null,
                                           string? TriedSsid = null, string? CurrentSsid = null);

/// <summary>
/// What happened after Apply Now, read from the drone's own status rather than from DNS-SD:
/// the drone answers its reply first and switches 1.5 s later, and its DNS-SD record stays
/// cached, so "found it" right after the reply only meant "it has not left yet".
/// The drone deletes last_error when it gets an Apply Now, so a last_error in any later status
/// belongs to this attempt (a wrong password: it came back on its saved one and says why).
/// Without one it counts as joined once it is on the target after having been away, or after
/// SettleSeconds if it never dropped (a fast re-join can stay unnoticed between two polls).
/// Same rules as the Mac app (ApplyWatch).
/// </summary>
public sealed class ApplyWatch
{
    public const double FirstCheckSeconds = 5;   // reply, 1.5 s, then the join starts
    public const double IntervalSeconds = 3;
    public const double SettleSeconds = 20;
    public const double TimeoutSeconds = 150;    // wrong password: ~40 s join, hotspot, ≤ 60 s, back

    public bool SawGone { get; private set; }

    public ApplyVerdict Step(ApplyPoll poll, double elapsed, string target)
    {
        if (elapsed < FirstCheckSeconds) return new(ApplyVerdictKind.Waiting);
        if (!poll.Answered)
        {
            SawGone = true;
        }
        else if (poll.ErrorReason is string reason)
        {
            var current = poll.Mode == "client" && poll.Ssid.Length > 0 ? poll.Ssid : null;
            var tried = string.IsNullOrEmpty(poll.ErrorSsid) ? target : poll.ErrorSsid;
            return new(ApplyVerdictKind.Failed, reason, tried, current);
        }
        else if (poll.Mode == "client" && WifiNames.Same(target, poll.Ssid)    // status.ssid is a profile name
                 && (SawGone || elapsed >= SettleSeconds))
        {
            return new(ApplyVerdictKind.Joined);
        }
        return new(elapsed >= TimeoutSeconds ? ApplyVerdictKind.NotFound : ApplyVerdictKind.Waiting);
    }

    public static string JoinedText(string drone, string target, string host) => $"{drone} is on {target} ({host}).";

    public static string FailedText(string drone, string reason, string triedSsid, string? currentSsid)
    {
        var why = JoinReasonText.Text(reason, triedSsid);
        return currentSsid is null
            ? $"{drone} did not switch: {why}."
            : $"{drone} did not switch: {why}. It kept its saved settings and is on {currentSsid}.";
    }
}

/// <summary>
/// A refusal shown in Settings that only held while the flight controller was armed or unknown:
/// cleared once the drone is linked and disarmed again (same rule as the Mac app).
/// </summary>
public static class RefusalBanner
{
    public static bool StillTrue(string? code, LinkState link, bool? armed) =>
        code is not ("armed" or "fc_unknown") || !(link == LinkState.Ok && armed == false);
}

/// <summary>
/// Whether a drone DNS-SD reports is the one we wait for. With an id only that id counts.
/// Without one (drone software before 1.0.1) a drone without an id counts only after
/// SettleSeconds: the browser first reports every drone already on the network.
/// </summary>
public static class DroneMatch
{
    public const double SettleSeconds = 5;

    public static bool Accepts(string? expectedId, string? foundId, double secondsSinceStart)
    {
        if (!string.IsNullOrEmpty(expectedId))
            return string.Equals(foundId, expectedId, StringComparison.OrdinalIgnoreCase);
        return string.IsNullOrEmpty(foundId) && secondsSinceStart >= SettleSeconds;
    }
}

public enum PasswordMemory { Save, Forget, Keep }

/// <summary>
/// What happens to the remembered Wi-Fi password once an "Add drone" setup ended: saved only
/// when it worked (or the drone got far enough to show it is right), forgotten after "wrong
/// password" so a typo is not offered again. failureKind: WifiHandoff.FailureKind as text,
/// null when the setup succeeded.
/// </summary>
public static class PasswordMemoryRule
{
    public static PasswordMemory After(string? failureKind) => failureKind switch
    {
        null => PasswordMemory.Save,
        "WrongPassword" => PasswordMemory.Forget,
        "Isolated" or "NotFound" or "NoAddress" => PasswordMemory.Save,
        _ => PasswordMemory.Keep,
    };
}
