# Original evidence before the AST portability adaptation

These files preserve their original bytes and historical meaning. They are
inputs to `scripts/adapt_acs_code_identity.py`; that script never writes here.
The original ACS component is stored with lossless gzip compression (mtime=0).
Its decompressed SHA-256 is
`8ad5edcd82c9535e9a8170539f55ce21474245d69f09775d9c0cd9a49f0cda20`.

The source snapshot is the actual original `acs_forecast_sources.py` bytes,
stored with a `.txt` suffix to avoid importing historical code. The original
normalization receipt records the earlier 616,858-record raw-source reparse
under that source identity. The original scientific-refresh receipt records
its earlier comparisons and final artifact, without attributing those runs to
the later portability fix.

The full original forecast remains available byte-for-byte at
`web/public/data/canonical/rolling-forecast-76ab8435f087f167ad01b8495ebd016415ba8086f32bfbd3dab961dcc8976c0a.json`.
The current operation receipt in `data/current/acs_code_identity_adaptation.json`
links these archives, the current source bytes, and unchanged normalization
identities. The current `scientific_refresh_receipt.json` links that operation
to the resulting artifact and new exact-equivalence checks. No historical
acceptance evidence is replaced by this chain.
