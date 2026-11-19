// fake_ssh.cs (Claude, 10.11.2026) - ТОЛЬКО ДЛЯ ТЕСТОВ: подделка ssh.exe для песочницы стенда. Не открывает сеть.
// Поведение берёт из файлов рядом с exe:
//   mode.txt        : normal | wrong_host | fail | nodone | refuse
//   canned_pi_state.txt, canned_measure.txt, events.txt : что "дрон" печатает в stdout для скриптов pi_state.sh / vision_measure.sh / прочих (по меткам в тексте скрипта)
//   measure_rc.txt  : код выхода для vision_measure.sh (по умолчанию 0)
//   sha_out.txt     : ответ на команду sha256sum (по умолчанию пусто); если mode.txt = sha_missing, команда sha256sum возвращает код 1
//   flight_rc.txt   : код выхода "скрипта полёта" (по умолчанию 0)
// Каждый вызов дописывается в calls.log: время, режим, путь exe, аргументы (base64 сокращён), SHA256 декодированного скрипта.
using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

public static class FakeSsh
{
    static string Dir { get { return AppDomain.CurrentDomain.BaseDirectory; } }
    static string ReadOr(string name, string def)
    {
        try { return File.ReadAllText(Path.Combine(Dir, name)).Trim(); } catch { return def; }
    }
    static int IntOr(string name, int def)
    {
        int v; return int.TryParse(ReadOr(name, def.ToString()), out v) ? v : def;
    }
    public static int Main(string[] args)
    {
        string mode = ReadOr("mode.txt", "normal");
        string last = args.Length > 0 ? args[args.Length - 1] : "";
        string sha = "none";
        string shown = last;
        string decoded = "";
        Match m = Regex.Match(last, @"echo (\S+) \| base64 -d");
        if (m.Success)
        {
            try
            {
                byte[] raw = Convert.FromBase64String(m.Groups[1].Value);
                decoded = Encoding.UTF8.GetString(raw);
                using (SHA256 s = SHA256.Create())
                    sha = BitConverter.ToString(s.ComputeHash(raw)).Replace("-", "").ToLowerInvariant();
                shown = last.Replace(m.Groups[1].Value, "<b64:" + m.Groups[1].Value.Length + ">");
            }
            catch { sha = "bad_base64"; }
        }
        StringBuilder sb = new StringBuilder();
        sb.Append(DateTime.Now.ToString("HH:mm:ss")).Append(" mode=").Append(mode).Append(" exe=").Append(System.Reflection.Assembly.GetExecutingAssembly().Location).Append(" payload_sha=").Append(sha).Append(" args=");
        for (int i = 0; i < args.Length; i++) sb.Append("[").Append(i == args.Length - 1 ? shown : args[i]).Append("] ");
        File.AppendAllText(Path.Combine(Dir, "calls.log"), sb.ToString() + Environment.NewLine);

        if (mode == "fail") { Console.Error.WriteLine("ssh: connect to host fake-drone port 22: Connection timed out"); return 255; }
        if (last.Contains("HOST_OK"))
        {
            if (mode == "wrong_host") return 1;
            Console.Out.Write("HOST_OK\n"); return 0;
        }
        if (m.Success)
        {
            string file = "events.txt";
            int rc = 0;
            if (decoded.Contains("BB_PI_STATE_MARK")) file = "canned_pi_state.txt";
            else if (decoded.Contains("BB_ARM_STATE_MARK")) { file = "canned_arm.txt"; rc = IntOr("arm_rc.txt", 0); }
            else if (decoded.Contains("BB_BENCH_PY_BEGIN")) { file = "canned_measure.txt"; rc = IntOr("measure_rc.txt", 0); }
            else if (decoded.Contains("BB_BATT_PY_BEGIN")) { file = "canned_battery.txt"; rc = IntOr("battery_rc.txt", 0); }
            else if (decoded.Contains("BB_JOURNAL_MARK")) { file = "canned_journal.txt"; rc = IntOr("journal_rc.txt", 0); }
            else if (decoded.Contains("BB_INSTALL_MARK")) { file = "canned_install.txt"; rc = IntOr("install_rc.txt", 0); }
            else if (decoded.Contains("BB_MAVROS_MARK")) { file = "canned_mavros.txt"; rc = IntOr("mavros_rc.txt", 0); }
            else if (decoded.Contains("BB_MBPRE_MARK")) { file = "canned_mbpre.txt"; rc = IntOr("mbpre_rc.txt", 0); }
            else if (decoded.Contains("BB_ASIDE_MARK")) { file = "canned_aside.txt"; rc = IntOr("aside_rc.txt", 0); }
            else if (decoded.Contains("BB_BBPRE_MARK")) { file = "canned_bbpre.txt"; rc = IntOr("bbpre_rc.txt", 0); }
            else if (decoded.Contains("BB_BBBUILD_MARK")) { file = "canned_bbbuild.txt"; rc = IntOr("bbbuild_rc.txt", 0); }
            else if (decoded.Contains("BB_BBASIDE_MARK")) { file = "canned_bbaside.txt"; rc = IntOr("bbaside_rc.txt", 0); }
            else if (decoded.Contains("BB_FP_MARK")) { file = last.EndsWith(" mavros") ? "canned_fp_mavros.txt" : "canned_fp_bumblebee.txt"; rc = IntOr("fp_rc.txt", 0); }
            else if (decoded.Contains("BB_CONN_MARK")) { file = "canned_conn.txt"; rc = IntOr("conn_rc.txt", 0); }
            else if (decoded.Contains("BB_DISC_MARK")) { file = "canned_disc.txt"; rc = IntOr("disc_rc.txt", 0); }
            else if (decoded.Contains("BB_FG_MARK")) { file = "canned_fg.txt"; rc = IntOr("fg_rc.txt", 0); }
            else if (decoded.Contains("BB_SSC_MARK")) { file = "canned_ssc.txt"; rc = IntOr("ssc_rc.txt", 0); }
            else if (decoded.Contains("BB_SVC_MARK")) { file = "canned_svc.txt"; rc = IntOr("svc_rc.txt", 0); }
            string path = ReadOr(file, "");
            if (path != "" && File.Exists(path)) Console.Out.Write(File.ReadAllText(path));
            if (mode == "nodone") return 1;
            return rc;
        }
        if (last.Contains("mkdir -p /home/lb/bench_ws/incoming")) { if (mode == "mkdir_fail") return 1; Console.Out.Write("MKDIR_OK\n"); return 0; }
        if (last.Contains("m1_unpack.sh")) { if (mode == "m1_fail") { Console.Out.Write("M1 STOP\n"); return 1; } Console.Out.Write("=== M1\nRC3M_M1_OK\n"); return 0; }
        if (last.Contains("m2_build.sh")) { if (mode == "m2_fail") { Console.Out.Write("M2 STOP\n"); return 1; } Console.Out.Write("=== M2\nRC3M_M2_OK\n"); return 0; }
        if (last.StartsWith("sha256sum "))
        {
            if (mode == "sha_missing") { Console.Error.WriteLine("sha256sum: No such file"); return 1; }
            Console.Out.Write(ReadOr("sha_out.txt", "") + "\n"); return 0;
        }
        if (last.Contains("python3 /home/lb/"))
        {
            Console.Out.Write("FAKE_FLIGHT_START\nFAKE_FLIGHT_END\n");
            return IntOr("flight_rc.txt", 0);
        }
        if (last.Contains("image_install.sh")) { if (mode != "nodone") Console.Out.Write("BB_IMAGE_INSTALL_DONE 20261110_100000 files=1\n"); return mode == "nodone" ? 3 : 0; }
        if (last.Contains("image_rollback.sh")) { if (mode != "nodone") Console.Out.Write("BB_IMAGE_ROLLBACK_DONE 20261110_100000\n"); return mode == "nodone" ? 3 : 0; }
        Console.Error.WriteLine("fake_ssh: unexpected command");
        return 3;
    }
}
