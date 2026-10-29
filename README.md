# TravelerAPI laboratory 4

PostgreSQL replication experiments built on the existing laboratory 3 API.

See [README-LAB4.md](README-LAB4.md) for setup, all seven topologies, tests,
security decisions, consistency guarantees, and sources.

```powershell
python scripts/lab4/bootstrap-env.py
python scripts/lab4/lab.py up logical
python scripts/lab4/lab.py functional logical
```

Measured results and screenshots are in `evidence/lab4/`.
Secrets are excluded from Git and archives.
