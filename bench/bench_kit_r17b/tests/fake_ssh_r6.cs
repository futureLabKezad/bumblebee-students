// fake_ssh_r6.cs (Claude, 12.11.2026, набор r6) - ТОЛЬКО ДЛЯ ТЕСТОВ: подделка ssh.exe для песочницы шагов r6. Сеть не открывает, к дрону не подключается.
// Поведение берёт из файлов рядом с exe:
//   mode.txt : normal | wrong_host | fail | nodone
//   canned_<ключ>.txt : путь к файлу ответа «дрона» или несколько путей через | (берутся по очереди, последний повторяется; счётчик count_<ключ>.txt)
//   rc_<ключ>.txt : код выхода для этого ключа (по умолчанию 0)
// Ключ выбирается по метке в декодированном скрипте: BB_R6LOAD_MARK -> load, BB_R6SC_MARK -> sc, BB_R6SYS_MARK -> sys, BB_R6CI_MARK -> ci, BB_R6MK_MARK -> mk,
//   BB_R6K1_MARK -> k1, BB_R6COST_MARK -> cost_<фаза: последнее слово>, BB_R6END_MARK -> end, BB_R6CP_MARK -> cp_<режим: последнее слово>, BB_R6CV_MARK -> cv,
//   BB_INSTALL_MARK -> install, BB_FP_MARK -> fp.
// Каждый вызов дописывается в calls.log (время, режим, аргументы, sha256 декодированного скрипта, ключ); декодированный скрипт сохраняется в sent_<n>.sh.
// Команды без base64: HOST_OK (проверка имени), mkdir /tmp/img..., image_install.sh, image_rollback.sh (как в fake_ssh.cs r5).
using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

public static class FakeSshR6
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
        string lastWord = words.Length > 0 ? words[words.Length - 1].Trim('"') : "";
        if (decoded.Contains("BB_R6LOAD_MARK")) key = "load";
        else if (decoded.Contains("BB_R6SC_MARK")) key = "sc";
        else if (decoded.Contains("BB_R6SYS_MARK")) key = "sys";
        else if (decoded.Contains("BB_R6CI_MARK")) key = "ci";
        else if (decoded.Contains("BB_R6MK_MARK")) key = "mk";
        else if (decoded.Contains("BB_R6K1_MARK")) key = "k1";
        else if (decoded.Contains("BB_R6COST_MARK")) key = "cost_" + lastWord;
        else if (decoded.Contains("BB_R6END_MARK")) key = "end";
        else if (decoded.Contains("BB_R6CP_MARK")) key = "cp_" + lastWord;
        else if (decoded.Contains("BB_R6CV_MARK")) key = "cv";
        else if (decoded.Contains("BB_INSTALL_MARK")) key = "install";
        else if (decoded.Contains("BB_FP_MARK")) key = "fp";
        StringBuilder sb = new StringBuilder();
        sb.Append(DateTime.Now.ToString("HH:mm:ss")).Append(" mode=").Append(mode).Append(" key=").Append(key).Append(" payload_sha=").Append(sha).Append(" args=");
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
            if (mode == "nodone") return 1;
            return IntOr("rc_" + key + ".txt", 0);
        }
        if (last.Contains("image_install.sh")) { if (mode == "install_fail") { Console.Out.Write("=== STOP: sha256 mismatch in upload\n"); return 1; } Console.Out.Write("=== backup /home/lb/bb_backup/20261113_100000: 4 old files, 0 new files\nBB_IMAGE_INSTALL_DONE 20261113_100000 files=4\n"); return 0; }
        if (last.Contains("image_rollback.sh")) { if (mode == "install_fail") { Console.Out.Write("=== STOP: no usable backup\n"); return 1; } Console.Out.Write("BB_IMAGE_ROLLBACK_DONE 20261113_100000 restored=4 moved_aside=0\n"); return 0; }
        Console.Error.WriteLine("fake_ssh_r6: unexpected command");
        return 3;
    }
}
