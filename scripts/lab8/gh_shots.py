"""Laboratory 8: GitHub screenshots of the public repository (Playwright + Edge, not signed in).

  python scripts/lab8/gh_shots.py <run_id> <job_id>
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_shots import Browser, SHOTS, trim

REPO = 'https://github.com/mishasamonov/traveler-api-dds-lab1'


def page(b, url, name, height=1100, width=1400, wait=3.0):
    b.resize(width, height)
    b.page.goto(url, wait_until='load')
    time.sleep(wait)
    out = SHOTS / f'{name}.png'
    b.page.screenshot(path=str(out), full_page=False)
    trim(out)
    print('shot', out.name)


if __name__ == '__main__':
    run_id, job_id = sys.argv[1], sys.argv[2]
    b = Browser(width=1400, height=1100, scale=1.25)
    try:
        page(b, f'{REPO}/tree/lab8-jsonb', 'gh-branch', 1250)
        page(b, f'{REPO}/commits/lab8-jsonb', 'gh-commits', 1000)
        page(b, f'{REPO}/tree/lab8-jsonb/sql', 'gh-sql', 900)
        page(b, f'{REPO}/actions?query=branch%3Alab8-jsonb', 'gh-actions', 900)
        page(b, f'{REPO}/actions/runs/{run_id}/job/{job_id}', 'gh-actions-steps', 1100, wait=5.0)
    finally:
        b.close()
