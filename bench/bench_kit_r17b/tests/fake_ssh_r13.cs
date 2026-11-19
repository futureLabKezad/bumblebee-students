// fake_ssh_r13.cs (Claude, 17.11.2026, набор r13) - ТОЛЬКО ДЛЯ ТЕСТОВ: подделка ssh.exe. Сеть не открывает, к дрону не подключается.
// Копия tests\fake_ssh_r12.cs набора r12 с отличиями: метка Marker (её ищет страж tests\run_tests_r13.ps1 перед каждым запуском шага: ssh, который найдёт BB-FindSsh, должен быть этой подделкой; метка пишется и в calls.log).
// Поведение берёт из файлов рядом с exe:
//   mode.txt     : normal | wrong_host | fail
//   exec_wsl.txt : путь (в WSL) к runner13.sh тестовой песочницы WSL (tests/r13_wsl_tree.sh). Если файл есть, декодированный скрипт Pi (base64 из команды) подаётся на stdin
//                  «wsl.exe -e bash <runner.sh> <аргументы после _>», runner запускает его в поддельном доме (HOME, hostname, ros2 - подделки песочницы);
//                  stdout и код выхода возвращаются как от «дрона». Так проверяется вся цепочка: скрипт ПК -> скрипт Pi -> вывод -> вердикт ПК.
//   иначе canned_<ключ>.txt : путь к файлу ответа (ключ по метке скрипта: BB_INSTALL_MARK -> install, BB_FP_MARK -> fp_<цель>, BB_LATLIVE_MARK -> lat, BB_FG_MARK -> fg).
//   sha_out.txt  : ответ на «sha256sum ...»; «python3 /home/lb/...» -> FAKE_FLIGHT (код flight_rc.txt).
// Каждый вызов дописывается в calls.log; декодированный скрипт сохраняется в sent_<n>.sh.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Security.Cryptography;
using System.Threading;

public static class FakeSshR13
{
    public const string Marker = "BB_FAKE_SSH_R13_NO_NETWORK";
    static string Dir { get { return AppDomain.CurrentDomain.BaseDirectory; } }
    static string ReadOr(string name, string def) { try { return File.ReadAllText(Path.Combine(Dir, name)).Trim(); } catch { return def; } }
    static int IntOr(string name, int def) { int v; return int.TryParse(ReadOr(name, def.ToString()), out v) ? v : def; }
    static void Out(byte[] b) { using (Stream o = Console.OpenStandardOutput()) { o.Write(b, 0, b.Length); o.Flush(); } }
    static void OutS(string s) { Out(new UTF8Encoding(false).GetBytes(s)); }
    public static int Main(string[] args)
    {
        string mode = ReadOr("mode.txt", "normal");
        string last = args.Length > 0 ? args[args.Length - 1] : "";
        string sha = "none", shown = last, key = "", tail = "";
        byte[] raw = null;
        Match m = Regex.Match(last, @"echo (\S+) \| base64 -d\)"" _(.*)$");
        if (m.Success)
        {
            try
            {
                raw = Convert.FromBase64String(m.Groups[1].Value);
                using (SHA256 s = SHA256.Create()) sha = BitConverter.ToString(s.ComputeHash(raw)).Replace("-", "").ToLowerInvariant();
                shown = last.Replace(m.Groups[1].Value, "<b64:" + m.Groups[1].Value.Length + ">");
                tail = m.Groups[2].Value.Trim();
                int sn = IntOr("sent_count.txt", 0) + 1;
                File.WriteAllText(Path.Combine(Dir, "sent_count.txt"), sn.ToString());
                File.WriteAllBytes(Path.Combine(Dir, "sent_" + sn + ".sh"), raw);
            }
            catch { sha = "bad_base64"; raw = null; }
        }
        string decoded = raw == null ? "" : Encoding.UTF8.GetString(raw);
        if (decoded.Contains("BB_INSTALL_MARK")) key = "install";
        else if (decoded.Contains("BB_FP_MARK")) key = "fp_" + tail;
        else if (decoded.Contains("BB_LATLIVE_MARK")) key = "lat";
        else if (decoded.Contains("BB_FG_MARK")) key = "fg";
        StringBuilder sb = new StringBuilder();
        sb.Append(DateTime.Now.ToString("HH:mm:ss")).Append(" ").Append(Marker).Append(" mode=").Append(mode).Append(" exe=").Append(System.Reflection.Assembly.GetExecutingAssembly().Location).Append(" key=").Append(key).Append(" payload_sha=").Append(sha).Append(" args=");
        for (int i = 0; i < args.Length; i++) sb.Append("[").Append(i == args.Length - 1 ? shown : args[i]).Append("] ");
        File.AppendAllText(Path.Combine(Dir, "calls.log"), sb.ToString() + Environment.NewLine);

        if (mode == "fail") { Console.Error.WriteLine("ssh: connect to host fake-drone port 22: Connection timed out"); return 255; }
        if (last.Contains("HOST_OK")) { if (mode == "wrong_host") return 1; OutS("HOST_OK\n"); return 0; }
        if (raw != null)
        {
            string runner = ReadOr("exec_wsl.txt", "");
            if (runner != "")
            {
                if (!Regex.IsMatch(tail, @"^[A-Za-z0-9_. -]*$") || !Regex.IsMatch(runner, @"^/[A-Za-z0-9_./-]+$")) { Console.Error.WriteLine("fake_ssh_r13: bad args"); return 3; }
                ProcessStartInfo psi = new ProcessStartInfo("wsl.exe", "-e bash " + runner + (tail == "" ? "" : " " + tail));
                psi.UseShellExecute = false; psi.RedirectStandardInput = true; psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
                Process p = Process.Start(psi);
                MemoryStream so = new MemoryStream(), se = new MemoryStream();
                Thread t1 = new Thread(() => p.StandardOutput.BaseStream.CopyTo(so)); Thread t2 = new Thread(() => p.StandardError.BaseStream.CopyTo(se));
                t1.Start(); t2.Start();
                p.StandardInput.BaseStream.Write(raw, 0, raw.Length); p.StandardInput.BaseStream.Flush(); p.StandardInput.Close();
                p.WaitForExit(); t1.Join(); t2.Join();
                Out(so.ToArray());
                byte[] eb = se.ToArray(); if (eb.Length > 0) { using (Stream e = Console.OpenStandardError()) { e.Write(eb, 0, eb.Length); } }
                return p.ExitCode;
            }
            string ptr = ReadOr("canned_" + key + ".txt", "");
            if (ptr != "" && File.Exists(ptr)) Out(File.ReadAllBytes(ptr));
            return IntOr("rc_" + key + ".txt", 0);
        }
        if (last.StartsWith("sha256sum ")) { OutS(ReadOr("sha_out.txt", "") + "\n"); return 0; }
        if (last.Contains("python3 /home/lb/")) { OutS("FAKE_FLIGHT_START\nFAKE_FLIGHT_END\n"); return IntOr("flight_rc.txt", 0); }
        Console.Error.WriteLine("fake_ssh_r13: unexpected command");
        return 3;
    }
}
