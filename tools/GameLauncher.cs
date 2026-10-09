using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

class GameLauncher
{
    [STAThread]
    static int Main(string[] args)
    {
        bool created;
        using (var mutex = new Mutex(true, "Local\\SignsDesktopGame", out created)) {
            if (!created) {
                MessageBox.Show("Signs is already open. Switch to its window to play.", "Signs");
                return 0;
            }
            string root = AppDomain.CurrentDomain.BaseDirectory;
            try {
                string python = Path.Combine(root, ".venv", "Scripts", "python.exe");
                string desktop = Path.Combine(root, "desktop.py");
                if (!File.Exists(python) || !File.Exists(desktop))
                    throw new Exception("Keep Signs.exe in the gesture game folder, alongside desktop.py and .venv.");
                string logs = Path.Combine(root, "logs");
                Directory.CreateDirectory(logs);
                object logLock = new object();
                bool smoke = args.Length > 0 && args[0] == "--smoke-test";
                var info = new ProcessStartInfo(python, "-u \"" + desktop + "\"" + (smoke ? " --smoke-test" : "")) {
                    WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardOutput = true, RedirectStandardError = true
                };
                using (var app = new Process { StartInfo = info }) {
                    DataReceivedEventHandler log = delegate(object sender, DataReceivedEventArgs e) {
                        if (e.Data == null) return;
                        try { lock (logLock) File.AppendAllText(Path.Combine(logs, "launcher.log"), DateTime.Now.ToString("s") + " " + e.Data + Environment.NewLine); } catch { }
                    };
                    app.OutputDataReceived += log;
                    app.ErrorDataReceived += log;
                    app.Start();
                    app.BeginOutputReadLine();
                    app.BeginErrorReadLine();
                    app.WaitForExit();
                    if (app.ExitCode != 0 && !smoke)
                        MessageBox.Show("Signs could not start. See logs\\launcher.log for details.\n\nIf dependencies are missing, run .venv\\Scripts\\python -m pip install -r requirements.txt.", "Signs", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return app.ExitCode;
                }
            } catch (Exception error) {
                MessageBox.Show(error.Message, "Signs", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }
    }
}
