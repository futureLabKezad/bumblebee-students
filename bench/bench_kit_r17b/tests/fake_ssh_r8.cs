// fake_ssh_r8.cs (Claude, 13.11.2026, набор r8) - ТОЛЬКО ДЛЯ ТЕСТОВ: подделка ssh.exe для песочницы шагов 25 и 01 (сверка params_check v3). Сеть не открывает, к дрону не подключается.
// Поведение берёт из файлов рядом с exe (как fake_ssh_r7.cs):
//   mode.txt : normal | wrong_host | fail | nodone
//   canned_<ключ>.txt : путь к файлу ответа «дрона» (или несколько путей через |, по очереди, последний повторяется); rc_<ключ>.txt : код выхода (по умолчанию 0)
// Ключ: скрипт с меткой BB_R8MN_MARK -> w8_<метка точки> (предпоследнее слово команды: pre, p00cm, p05cm, p10cm, p15cm);
//       скрипт с BB_PI_STATE_DONE (pi_state.sh шага 01) -> pi_state; скрипт с BB_PARAMS_READ_DONE (params_read.sh) -> params:
//       stdout - ответ canned_params, stderr - «TABLE_READ ...» и BB_PARAMS_READ_DONE (так run_params_check.ps1 узнаёт конец чтения).
// Каждый вызов дописывается в calls.log (время, режим, ключ, sha256 декодированного скрипта, аргументы); скрипт сохраняется в sent_<n>.sh.
using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

public static class FakeSshR8
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
    static string NextCanned(string key)
    {
        string ptr = ReadOr("canned_" + key + ".txt", "");
        if (ptr == "") return "";
        string[] parts = ptr.Split('|');
        int n = IntOr("count_" + key + ".txt", 0);
        File.WriteAllText(Path.Combine(Dir, "count_" + key + ".txt"), (n + 1).ToString());
        string p = parts[Math.Min(n, parts.Length - 1)];
        return File.Exists(p) ? File.ReadAllText(p) : "";
    }
    public static int Main(string[] args)
    {
        string mode = ReadOr("mode.txt", "normal");
        string last = args.Length > 0 ? args[args.Length - 1] : "";
        string sha = "none", shown = last, decoded = "", key = "";
        Match m = Regex.Match(last, @"echo (\S+) \| base64 -d");
        if (m.Success)
        {
            try
            {
                byte[] raw = Convert.FromBase64String(m.Groups[1].Value);
                decoded = Encoding.UTF8.GetString(raw);
                using (SHA256 s = SHA256.Create()) sha = BitConverter.ToString(s.ComputeHash(raw)).Replace("-", "").ToLowerInvariant();
                shown = last.Replace(m.Groups[1].Value, "<b64:" + m.Groups[1].Value.Length + ">");
                int sn = IntOr("sent_count.txt", 0) + 1;
                File.WriteAllText(Path.Combine(Dir, "sent_count.txt"), sn.ToString());
                File.WriteAllBytes(Path.Combine(Dir, "sent_" + sn + ".sh"), raw);
            }
            catch { sha = "bad_base64"; }
        }
        string[] words = last.TrimEnd().Split(' ');
        string label = words.Length > 1 ? words[words.Length - 2].Trim('"') : "";
        if (decoded.Contains("BB_R8MN_MARK")) key = "w8_" + label;
        else if (decoded.Contains("BB_PI_STATE_DONE")) key = "pi_state";
        else if (decoded.Contains("BB_PARAMS_READ_DONE")) key = "params";
        StringBuilder sb = new StringBuilder();
        sb.Append(DateTime.Now.ToString("HH:mm:ss")).Append(" mode=").Append(mode).Append(" key=").Append(key).Append(" payload_sha=").Append(sha).Append(" exe=").Append(System.Reflection.Assembly.GetExecutingAssembly().Location).Append(" args=");
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
            Console.Out.Write(NextCanned(key));
            if (key == "params" && mode != "nodone") Console.Error.Write("TABLE_READ 1107 of 1107\nBB_PARAMS_READ_DONE\n");
            if (mode == "nodone") return 1;
            return IntOr("rc_" + key + ".txt", 0);
        }
        Console.Error.WriteLine("fake_ssh_r8: unexpected command");
        return 3;
    }
}
