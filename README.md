# Page 47

Page 47 helps residents see how a public matter was presented across the meetings where it appeared. It compares the public record over time and links every reported fact back to the city record.

The named primitive is **presentation drift**: the gap between how a matter is described to the public and what the matter actually does, measured across every appearance.

This repository is currently at Phase 0. Run the live discovery before adding city-specific behavior:

```bash
python3 scripts/preflight.py \
  --config config/preflight.json \
  --output docs/preflight.json
```

The discovery records the city API responses it used, the fields that were populated, the oldest sampled records, bounded request behavior, and AWS permission results. It does not invent unavailable values.

Page 47 reports public records. It does not determine why a change was made or make a legal finding. A record that was never published is outside what this tool can see.
