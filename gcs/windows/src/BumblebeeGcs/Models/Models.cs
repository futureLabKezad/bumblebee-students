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

using BumblebeeGcs.Logic;

namespace BumblebeeGcs.Models;


/// <summary>Системные метрики Raspberry Pi (:8888 JSON).</summary>
public struct SystemMetrics
{
    public double? CpuTemp, CpuPct, Load1, Load5, Load15, MemPct;
    public int? CpuCount, MemUsed, MemTotal;
}

public readonly record struct Euler(double Roll, double Pitch, double Yaw); // degrees

/// <summary>Точка трека позиции (м, локальная ENU); без WinUI-типов, чтобы стор тестировался.</summary>
public readonly record struct TrailPoint(double X, double Y);

public static class MathUtil
{
    /// <summary>Кватернион → углы Эйлера в градусах (та же формула, что в Models.swift).
    /// ROS-конвенция (REP-103): +pitch = нос вниз.</summary>
    public static Euler QuatToEuler(double x, double y, double z, double w)
    {
        var roll = Math.Atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
        var sp = Math.Max(-1, Math.Min(1, 2 * (w * y - z * x)));
        var pitch = Math.Asin(sp);
        var yaw = Math.Atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
        const double r = 180.0 / Math.PI;
        return new Euler(roll * r, pitch * r, yaw * r);
    }

    public static double PctOf(double v, double max) => Math.Min(100, Math.Abs(v) / max * 100);
}

/// <summary>
/// Хранилище телеметрии — наполняется RosbridgeClient на UI-потоке.
/// Порт TelemetryStore из Models.swift (лимиты: trail 200, chart 120).
/// Без WinUI: решения экрана (Link, armed, батарея, журнал, тревога FC) проверяются
/// юнит-тестами в gcs/windows/tests. Время — монотонные секунды (MonoClock.Now).
/// Значение null = ещё не приходило: экран показывает «—», а не 0.
/// </summary>
public sealed class TelemetryStore
{
    // Connection: rosbridge socket + /mavros/state
    public bool RosConnected;              // socket open
    public double? SocketOpenedAt;         // null = no open socket
    public double? StateAt;                // last /mavros/state (may be from an earlier socket)
    public bool? StateConnected, StateArmed;
    /// <summary>Last armed value a connected FC reported; kept over reconnects, null after a drone switch.</summary>
    public bool? LastKnownArmed;
    /// <summary>PX4 mode of the last state; null = no state on this connection yet, "" = MAVROS sent none.</summary>
    public string? Mode;

    // Derived by Evaluate()
    public LinkState Link { get; private set; } = LinkState.NoDrone;
    /// <summary>Tri-state armed the screen may show (null = unknown).</summary>
    public bool? Armed { get; private set; }
    public Controller InControl { get; private set; } = Controller.Unknown;
    public readonly FcLostAlarm FcAlarm = new();
    public readonly ControlEvents Events = new();

    // Battery
    public BatteryReading Battery = BatteryReading.NoData;
    public double? BatteryAt;
    public readonly LowBatteryLatch LowBattery = new();
    /// <summary>Red banner text while the charge is low (below 15 % until above 20 %); null = no banner.</summary>
    public string? LowBatteryBanner { get; private set; }

    // Pose (X/Y/Z, trail) and attitude (from IMU orientation when valid, else from pose)
    public double? PosX, PosY, PosZ;
    public double? PoseAt;
    public double? Roll, Pitch, Yaw;
    public double? AttitudeAt;
    public bool AttitudeFromImu;
    private double? _imuAttitudeAt;

    // Velocity
    public double? Vx, Vy, Vz;
    public double? VelocityAt;
    public double? SpeedH => Vx is double x && Vy is double y ? Math.Sqrt(x * x + y * y) : null;
    public double? SpeedV => Vz is double z ? Math.Abs(z) : null;

    // IMU
    public double? GyroMag;   // deg/s
    public double? AccelMag;  // m/s^2
    public double? ImuAt;

    // Trails / charts
    public readonly List<TrailPoint> PosTrail = new();
    public readonly List<double> ChartAlt = new(), ChartSpd = new(), ChartBat = new();

    public readonly MessageLog Messages = new();
    public readonly LinkLog LinkLog = new();

    const int PosMax = 200, ChartMax = 120;

    /// <summary>Любое значение изменилось — панели перечитывают свои поля.</summary>
    public event Action? Updated;
    /// <summary>RosConnected изменился.</summary>
    public event Action? ConnectionChanged;
    /// <summary>Link изменился (точка в сайдбаре).</summary>
    public event Action? LinkChanged;
    /// <summary>FC lost while armed: play the alert sound (once per loss).</summary>
    public event Action? AlarmRaised;

    public void NotifyUpdated() => Updated?.Invoke();

    // MARK: - Connection

    public void SocketOpened(string host, double now)
    {
        RosConnected = true;
        SocketOpenedAt = now;
        var (text, key) = LinkLog.Connected(host);
        Messages.AddApp(text, TimeString(), key);
        ConnectionChanged?.Invoke();
        Evaluate(now);
    }

    /// <summary>The socket dropped or a connect attempt failed (one collapsing log line, with why).</summary>
    public void SocketLost(double now, string? reason = null)
    {
        var wasOpen = RosConnected;
        RosConnected = false;
        SocketOpenedAt = null;
        var (text, key) = LinkLog.Failed(reason);
        Messages.AddApp(text, TimeString(), key);
        if (wasOpen) ConnectionChanged?.Invoke();
        Evaluate(now);
    }

    /// <summary>
    /// Reconnect or disconnect, same drone (as the Mac app): the socket and the State of the old
    /// connection are gone, so armed and the mode are unknown until a new State arrives. The log,
    /// the last known armed value and the other values stay (they show greyed as stale).
    /// </summary>
    public void ResetForReconnect(double now)
    {
        var wasOpen = RosConnected;
        RosConnected = false;
        SocketOpenedAt = null;
        StateAt = null;
        StateConnected = StateArmed = null;
        Mode = null;
        LinkLog.Reset();
        if (wasOpen) ConnectionChanged?.Invoke();
        Evaluate(now);
    }

    /// <summary>Another drone: nothing of the previous one may stay on screen.</summary>
    public void ResetAll(double now)
    {
        RosConnected = false;
        SocketOpenedAt = null;
        StateAt = null;
        StateConnected = StateArmed = LastKnownArmed = null;
        Mode = null;
        Battery = BatteryReading.NoData;
        BatteryAt = null;
        LowBattery.Reset();
        LowBatteryBanner = null;
        PosX = PosY = PosZ = null;
        PoseAt = null;
        Roll = Pitch = Yaw = null;
        AttitudeAt = null;
        AttitudeFromImu = false;
        _imuAttitudeAt = null;
        Vx = Vy = Vz = null;
        VelocityAt = null;
        GyroMag = AccelMag = null;
        ImuAt = null;
        PosTrail.Clear();
        ChartAlt.Clear();
        ChartSpd.Clear();
        ChartBat.Clear();
        Messages.Clear();
        LinkLog.Reset();
        Events.Reset();
        FcAlarm.Reset();
        ConnectionChanged?.Invoke();
        Evaluate(now);
    }

    /// <summary>
    /// Recompute link, armed, who is in control and the FC-lost alarm. Called on every
    /// /mavros/state, on socket changes and by a 500 ms timer (staleness needs no message).
    /// </summary>
    public void Evaluate(double now)
    {
        var link = LinkLogic.Compute(SocketOpenedAt, StateAt, StateConnected, now);
        var linkChanged = link != Link;
        Link = link;
        Armed = ArmedLogic.Effective(link, StateArmed);
        InControl = ModeLogic.WhoIsInControl(Armed, Mode);
        // The event also goes into the Messages panel (newest first: after its "mode → X").
        if (Events.Update(InControl, Mode, TimeString()) is string ev) Log(ev);
        if (FcAlarm.Update(link, LastKnownArmed))
        {
            Log(FcLostAlarm.Text);
            AlarmRaised?.Invoke();
        }
        if (linkChanged) LinkChanged?.Invoke();
        Updated?.Invoke();
    }

    // MARK: - Data (called by RosMessages on the UI thread)

    public void ApplyState(bool? connected, bool? armed, string? mode, double now)
    {
        StateAt = now;
        StateConnected = connected;
        StateArmed = armed;
        // MAVROS reports armed=false when the FC is gone: only a connected FC sets the last known value.
        if (connected == true && armed is bool a) LastKnownArmed = a;
        if (mode is not null) mode = ModeLogic.Normalize(mode);
        if (mode is not null && mode != Mode)
        {
            Mode = mode;
            Log($"mode → {(mode.Length == 0 ? "unknown" : mode)}");
        }
        Evaluate(now);
    }

    public void ApplyBattery(BatteryReading r, double now)
    {
        Battery = r;
        BatteryAt = now;
        // Only a measured charge moves the chart and the LOW BATTERY latch; a not-measured
        // message keeps the banner as it was.
        if (r.Pct is not double p) return;
        PushChart(ChartBat, p);
        if (LowBattery.Update(p)) Log(r.LowLogLine);
        LowBatteryBanner = LowBattery.IsLow ? r.LowBannerText : null;
    }

    public void ApplyPose(double x, double y, double z, Euler? attitude, double now)
    {
        PosX = x;
        PosY = y;
        PosZ = z;
        PoseAt = now;
        PushTrail(x, y);
        PushChart(ChartAlt, z);
        // The pose's orientation is used only while the IMU gives none.
        var imuFresh = _imuAttitudeAt is double t && now - t <= Freshness.Limit(TelemetrySource.Imu);
        if (attitude is Euler e && !imuFresh) SetAttitude(e, now, fromImu: false);
    }

    public void ApplyVelocity(double vx, double vy, double vz, double now)
    {
        Vx = vx;
        Vy = vy;
        Vz = vz;
        VelocityAt = now;
        if (SpeedH is double h) PushChart(ChartSpd, h);
    }

    public void ApplyImu(double gyroDegS, double accel, Euler? attitude, double now)
    {
        GyroMag = gyroDegS;
        AccelMag = accel;
        ImuAt = now;
        if (attitude is Euler e)
        {
            _imuAttitudeAt = now;
            SetAttitude(e, now, fromImu: true);
        }
    }

    private void SetAttitude(Euler e, double now, bool fromImu)
    {
        Roll = e.Roll;
        Pitch = e.Pitch;
        Yaw = e.Yaw;
        AttitudeAt = now;
        AttitudeFromImu = fromImu;
    }

    // MARK: - Log

    /// <summary>App line (connection, mode, warnings) — its own ring, never pushes out PX4 lines.</summary>
    public void Log(string msg) => Messages.AddApp(msg, TimeString());

    /// <summary>PX4 statustext line.</summary>
    public void LogFcu(string msg) => Messages.AddFcu(msg, TimeString());

    public void PushTrail(double x, double y)
    {
        PosTrail.Add(new TrailPoint(x, y));
        if (PosTrail.Count > PosMax) PosTrail.RemoveRange(0, PosTrail.Count - PosMax);
    }

    public static void PushChart(List<double> chart, double v)
    {
        chart.Add(v);
        if (chart.Count > ChartMax) chart.RemoveRange(0, chart.Count - ChartMax);
    }

    public static string TimeString() => DateTime.Now.ToString("HH:mm:ss");
}
