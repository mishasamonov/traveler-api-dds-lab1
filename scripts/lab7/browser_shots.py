"""Laboratory 7: real browser screenshots of Grafana and Prometheus (Playwright + Microsoft Edge).
Grafana is opened as the anonymous Viewer (no password is typed).

  python scripts/lab7/browser_shots.py grafana traveler-api g-api-load --from <ms> --to <ms> [--panel 14]
  python scripts/lab7/browser_shots.py prometheus /targets p-targets
"""
import argparse, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / 'evidence/lab7/screenshots'; SHOTS.mkdir(parents=True, exist_ok=True)
GRAFANA = 'http://127.0.0.1:3000'
PROM = 'http://127.0.0.1:9090'


def trim(path, margin=24):
    """Cut the empty white area under the page content."""
    from PIL import Image, ImageChops
    im = Image.open(path).convert('RGB')
    box = ImageChops.difference(im, Image.new('RGB', im.size, (255, 255, 255))).getbbox()
    if box: im.crop((0, 0, im.width, min(im.height, box[3] + margin))).save(path, optimize=True)


class Browser:
    def __init__(self, width=1600, height=1000, scale=1.25):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(channel='msedge', headless=True)
        self.ctx = self.browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=scale,
                                            locale='uk-UA', color_scheme='light')
        self.page = self.ctx.new_page()

    def close(self):
        self.ctx.close(); self.browser.close(); self.pw.stop()

    def resize(self, width, height):
        self.page.set_viewport_size({'width': width, 'height': height})

    def grafana(self, uid, name, start=None, end=None, panel=None, height=None, width=1600, kiosk=False, wait=6.0, refresh=False):
        """Whole dashboard (tall viewport so every panel is rendered) or one panel in view mode."""
        self.resize(width, height or (1000 if panel else 2400))
        params = ['orgId=1', 'timezone=browser']
        params += [f'from={start}', f'to={end}'] if start else ['from=now-15m', 'to=now']
        if not refresh: params.append('refresh=')
        if panel: params.append(f'viewPanel=panel-{panel}')
        if kiosk: params.append('kiosk')
        self.page.goto(f'{GRAFANA}/d/{uid}/?{"&".join(params)}', wait_until='networkidle')
        time.sleep(wait)
        out = SHOTS / f'{name}.png'
        self.page.screenshot(path=str(out), full_page=False)
        print('shot', out.name)
        return out

    def prometheus(self, path, name, height=1000, width=1600, wait=3.0, clip_selector=None):
        self.resize(width, height)
        self.page.goto(f'{PROM}{path}', wait_until='load')
        time.sleep(wait)
        out = SHOTS / f'{name}.png'
        if clip_selector:
            self.page.locator(clip_selector).first.screenshot(path=str(out))
        else:
            self.page.screenshot(path=str(out), full_page=True)
            trim(out)
        print('shot', out.name)
        return out

    def alerts(self, name, width=1500, expand=True, query='?state=firing&state=pending'):
        """Prometheus alerts page with every firing/pending rule expanded (labels, annotations, active since)."""
        self.resize(width, 2600)  # tall viewport instead of full_page: the sticky header is not repeated
        self.page.goto(f'{PROM}/alerts{query}', wait_until='load')
        time.sleep(3)
        if expand:
            for control in self.page.locator('.mantine-Accordion-control').all():
                control.click(); time.sleep(0.4)
        self.page.evaluate('window.scrollTo(0, 0)')
        time.sleep(1)
        out = SHOTS / f'{name}.png'
        self.page.screenshot(path=str(out), full_page=False)
        trim(out)
        print('shot', out.name)
        return out

    def url(self, url, name, height=1000, width=1600, wait=2.0, full=True):
        self.resize(width, height)
        self.page.goto(url, wait_until='networkidle')
        time.sleep(wait)
        out = SHOTS / f'{name}.png'
        self.page.screenshot(path=str(out), full_page=full)
        print('shot', out.name)
        return out


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('kind'); p.add_argument('target'); p.add_argument('name')
    p.add_argument('--from', dest='start'); p.add_argument('--to', dest='end'); p.add_argument('--panel', type=int)
    p.add_argument('--height', type=int)
    a = p.parse_args()
    b = Browser()
    try:
        if a.kind == 'grafana': b.grafana(a.target, a.name, a.start, a.end, a.panel, a.height)
        else: b.prometheus(a.target, a.name, a.height or 1000)
    finally:
        b.close()
