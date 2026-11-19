// fake_scp.cs (Claude, 09.11.2026) - ТОЛЬКО ДЛЯ ТЕСТОВ: подделка scp.exe. Сеть не открывает.
// Загрузка (источник локальный): записывает в calls.log SHA256 файла. Скачивание (источник lb@...): создаёт локальный файл-заглушку.
// mode.txt: normal | scp_fail
using System;
using System.IO;
using System.Text;
using System.Security.Cryptography;

public static class FakeScp
{
    static string Dir { get { return AppDomain.CurrentDomain.BaseDirectory; } }
    public static int Main(string[] args)
    {
        string mode = "normal";
        try { mode = File.ReadAllText(Path.Combine(Dir, "mode.txt")).Trim(); } catch { }
        StringBuilder sb = new StringBuilder();
        sb.Append(DateTime.Now.ToString("HH:mm:ss")).Append(" SCP exe=").Append(System.Reflection.Assembly.GetExecutingAssembly().Location).Append(" args=");
        foreach (string a in args) sb.Append("[").Append(a).Append("] ");
        string src = null, dst = null;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "-o") { i++; continue; }
            if (args[i].StartsWith("-")) continue;
            if (src == null) src = args[i]; else dst = args[i];
        }
        string sha = "none";
        if (src != null && !src.StartsWith("lb@") && File.Exists(src))
            using (SHA256 s = SHA256.Create()) sha = BitConverter.ToString(s.ComputeHash(File.ReadAllBytes(src))).Replace("-", "").ToLowerInvariant();
        sb.Append("upload_sha=").Append(sha);
        File.AppendAllText(Path.Combine(Dir, "calls.log"), sb.ToString() + Environment.NewLine);
        if (mode == "scp_fail") { Console.Error.WriteLine("scp: connection failed"); return 1; }
        if (src != null && src.StartsWith("lb@") && dst != null) File.WriteAllText(dst, "fake pi output\nBB_PORT_RESTART_DONE\n");
        return 0;
    }
}
