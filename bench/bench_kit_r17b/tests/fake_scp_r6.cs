// fake_scp_r6.cs (Claude, 12.11.2026, набор r6) - ТОЛЬКО ДЛЯ ТЕСТОВ: подделка scp.exe. Сеть не открывает.
// Загрузка (источники локальные): пишет в calls.log имена и sha256 файлов (для папки - число файлов). Скачивание (источник lb@...): с -r создаёт
// в папке назначения подпапку с именем последней части удалённого пути и файл FAKE_DOWNLOADED.txt; без -r - файл-заглушку.
// mode.txt: normal | scp_fail (код 1).
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Security.Cryptography;

public static class FakeScpR6
{
    static string Dir { get { return AppDomain.CurrentDomain.BaseDirectory; } }
    static string Sha(string p) { using (SHA256 s = SHA256.Create()) return BitConverter.ToString(s.ComputeHash(File.ReadAllBytes(p))).Replace("-", "").ToLowerInvariant(); }
    public static int Main(string[] args)
    {
        string mode = "normal";
        try { mode = File.ReadAllText(Path.Combine(Dir, "mode.txt")).Trim(); } catch { }
        bool rec = false;
        List<string> paths = new List<string>();
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "-o") { i++; continue; }
            if (args[i] == "-r") { rec = true; continue; }
            if (args[i].StartsWith("-")) continue;
            paths.Add(args[i]);
        }
        StringBuilder sb = new StringBuilder();
        sb.Append(DateTime.Now.ToString("HH:mm:ss")).Append(" SCP rec=").Append(rec).Append(" args=");
        foreach (string a in args) sb.Append("[").Append(a).Append("] ");
        string dst = paths.Count > 0 ? paths[paths.Count - 1] : "";
        for (int i = 0; i + 1 < paths.Count; i++)
        {
            string s = paths[i];
            if (s.StartsWith("lb@")) { sb.Append(" download=").Append(s); continue; }
            if (File.Exists(s)) sb.Append(" upload=").Append(Path.GetFileName(s)).Append(":").Append(Sha(s));
            else if (Directory.Exists(s)) sb.Append(" upload_dir=").Append(Path.GetFileName(s)).Append(":files=").Append(Directory.GetFiles(s, "*", SearchOption.AllDirectories).Length);
            else sb.Append(" missing=").Append(s);
        }
        File.AppendAllText(Path.Combine(Dir, "calls.log"), sb.ToString() + Environment.NewLine);
        if (mode == "scp_fail") { Console.Error.WriteLine("scp: connection failed"); return 1; }
        if (paths.Count >= 2 && paths[0].StartsWith("lb@") && dst != "")
        {
            string remote = paths[0].Substring(paths[0].IndexOf(':') + 1).TrimEnd('/');
            string name = remote.Substring(remote.LastIndexOf('/') + 1);
            if (rec) { string d = Path.Combine(dst, name); Directory.CreateDirectory(d); File.WriteAllText(Path.Combine(d, "FAKE_DOWNLOADED.txt"), "fake copy of " + remote + "\n"); }
            else File.WriteAllText(dst, "fake pi output\n");
        }
        return 0;
    }
}
