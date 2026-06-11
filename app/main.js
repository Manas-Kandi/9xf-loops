// 9xf desktop app: a thin Electron shell around the `9xf app` server.
// It spawns `python -m ninexf app` (the same zero-dependency server the
// browser UI uses), waits for it to come up, and hosts it in a dark native
// window with a native folder picker bridged via preload.js.

const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

const PORT = process.env.NINEXF_PORT || 9118;
const PYTHON = process.env.NINEXF_PYTHON || 'python3';
const URL = `http://127.0.0.1:${PORT}`;

let server = null;
let win = null;
let spawnedHere = false;

function ping(cb) {
  http.get(`${URL}/api/runs`, res => cb(res.statusCode === 200))
    .on('error', () => cb(false));
}

function startServer() {
  // repo root is one level up from app/; works for a git checkout. If ninexf
  // is pip-installed, the cwd doesn't matter.
  server = spawn(PYTHON, ['-m', 'ninexf', 'app', '--port', String(PORT), '--no-browser'], {
    cwd: path.join(__dirname, '..'),
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  spawnedHere = true;
  server.on('exit', code => {
    if (win && !win.isDestroyed() && code !== 0 && code !== null) {
      dialog.showErrorBox('9xf server stopped',
        `The python server exited (code ${code}).\n` +
        'Check that python3 can import ninexf (pip install -e . in the repo).');
    }
  });
}

function waitForServer(retries, cb) {
  ping(ok => {
    if (ok) return cb(true);
    if (retries <= 0) return cb(false);
    setTimeout(() => waitForServer(retries - 1, cb), 250);
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 980,
    minHeight: 600,
    backgroundColor: '#07090d',
    title: '9xf',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadURL(URL);
}

ipcMain.handle('pick-folder', async () => {
  const res = await dialog.showOpenDialog(win, {
    title: 'Choose a folder for this session',
    properties: ['openDirectory', 'createDirectory'],
  });
  return res.canceled ? null : res.filePaths[0];
});

app.whenReady().then(() => {
  // reuse an already-running `9xf app` (e.g. started from the CLI) if present
  ping(alreadyUp => {
    if (!alreadyUp) startServer();
    waitForServer(60, ok => {
      if (!ok) {
        dialog.showErrorBox('9xf could not start',
          `No server at ${URL}.\nIs python3 installed and ninexf importable?\n` +
          '(from the repo: pip install -e .)');
        app.quit();
        return;
      }
      createWindow();
    });
  });
});

app.on('window-all-closed', () => {
  if (server && spawnedHere) server.kill();
  app.quit();
});
