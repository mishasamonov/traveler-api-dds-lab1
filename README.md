# TravelerAPI laboratory 6

Sharding of TravelerAPI: 16 virtual nodes (databases `db_0..db_f`) on four
PostgreSQL services, CLI tools for distributed DDL/DML and rebalancing, and a
shared shard registry.

See [README-LAB6.md](README-LAB6.md). Previous laboratory: branch `lab4-replication`
([README-LAB4.md](README-LAB4.md)).

```powershell
python scripts/lab6/bootstrap-env.py
python scripts/lab6/lab6.py up sharded
python scripts/lab6/lab6.py seed sharded
```

Measured results and screenshots are in `evidence/lab6/`.
Secrets are excluded from Git and archives.
