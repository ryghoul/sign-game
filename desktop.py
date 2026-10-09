"""Native desktop host; local game services live inside this application."""
import json
import os
from pathlib import Path
import sys
import threading
import time
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8765'


def existing_game():
    try:
        with build_opener(ProxyHandler({})).open(URL, timeout=.7) as response:
            return b'Hand gesture rhythm' in response.read()
    except OSError:
        return False


class GameServices:
    def __init__(self):
        self.http = None
        self.thread = None
        self.backend = None

    def start(self):
        if existing_game():
            return
        import server
        self.backend = server
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 8765), server.Handler)
        server.music.start_watching()
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if self.http is None:
            return
        self.backend.music.stop_watching()
        self.backend.running.clear()
        with self.backend.lock:
            self.backend.calibration.finish(cancelled=True)
        self.http.shutdown()
        self.http.server_close()
        if self.backend.worker is not None:
            self.backend.worker.join(timeout=3)
        self.thread.join(timeout=3)


def main():
    smoke = '--smoke-test' in sys.argv
    if smoke:
        # Automated clicks lack real user activation.
        os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (
            os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '') +
            ' --autoplay-policy=no-user-gesture-required')
    import webview
    os.chdir(ROOT)
    services = GameServices()
    result = {'ok': False}
    try:
        services.start()
        window = webview.create_window('Signs', URL, width=1280, height=800,
                                      min_size=(780, 560), background_color='#08090b')

        def check_window():
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if window.evaluate_js("document.querySelector('#play')?.onclick != null"):
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('Game scripts did not initialize in the desktop window.')
                window.evaluate_js("document.querySelector('#play').click()")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if window.evaluate_js("[...document.querySelectorAll('.track-option')].some(b=>b.querySelector('small')?.textContent.includes('MP3'))"):
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('Song list did not load.')
                window.evaluate_js("const originalPlay=HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play=function(){window.testSong=this;return originalPlay.call(this)}; [...document.querySelectorAll('.track-option')].find(b=>b.querySelector('small')?.textContent.includes('MP3')).click(); document.querySelector('#play').click()")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if window.evaluate_js("!document.querySelector('#countdown').hidden"):
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Song loading/countdown failed.')
                result.update(ok=True, title=window.evaluate_js('document.title'),
                              countdown=window.evaluate_js("document.querySelector('#countdownNumber').textContent"))
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if window.evaluate_js("window.testSong && !window.testSong.paused && window.testSong.currentTime > .2"):
                        break
                    time.sleep(.1)
                else:
                    detail = window.evaluate_js("JSON.stringify({song:window.testSong && {paused:window.testSong.paused,time:window.testSong.currentTime,error:window.testSong.error?.message},overlay:document.querySelector('#overlayText').textContent,countdown:document.querySelector('#countdownNumber').textContent})")
                    raise RuntimeError('MP3 playback failed in the desktop window: ' + detail)
                window.evaluate_js("document.querySelector('#mapEditorButton').click()")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if window.evaluate_js("document.querySelector('#editorSong').options.length > 0 && !document.querySelector('#mapEditor').hidden"):
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('Map editor did not load.')
                result.update(playback=True, editor=True)
            except Exception as error:
                result['ok'] = False
                result['error'] = str(error)
            finally:
                print(json.dumps(result), flush=True)
                window.destroy()

        profile = ROOT / ('.test-tools/desktop-profile' if smoke else '.desktop-profile')
        webview.start(check_window if smoke else None, gui='edgechromium',
                      private_mode=False, storage_path=str(profile))
    finally:
        services.close()
    return 0 if not smoke or result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
