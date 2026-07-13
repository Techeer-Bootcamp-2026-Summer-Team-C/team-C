# MITRE ATT&CK catalog

`mitre_attack.yaml` is a compact, generated catalog for Enterprise ATT&CK RuleV1 validation. It contains active
tactics, active techniques and sub-techniques, and each technique's valid tactic relationships. It is not a claim
that every catalog entry is detected by this PoC.

The catalog is generated from the pinned MITRE ATT&CK STIX 2.1 v19.1 bundle. The source URL, source SHA-256, ATT&CK
version, and STIX bundle ID are recorded in the generated YAML.

Regenerate it from the network:

```bash
python -m tools.sync_mitre_attack
```

Regenerate it from an already downloaded pinned bundle:

```bash
python -m tools.sync_mitre_attack --source path/to/enterprise-attack-19.1.json
```

Updating to another ATT&CK release requires changing the pinned version, URL, and SHA-256 in
`tools/sync_mitre_attack.py`, regenerating the catalog, and running the RuleV1/detection tests.
