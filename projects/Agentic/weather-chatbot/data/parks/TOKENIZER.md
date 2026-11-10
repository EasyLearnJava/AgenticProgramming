# Park preparation tokenizer

`tokenizer.json` is the tokenizer from
[`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.

SHA-256: `be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037`.

The preparation command verifies these bytes before counting tokens. It reserves the title, section and special
tokens inside the 256-token input limit. It loads no model weights, generates no embeddings and makes no network
requests. The separate Qdrant publisher generates the dense embeddings once with hosted MiniLM.

The migration preserves all 40 approved passages, including their IDs and source metadata. The compact runtime
catalog contains identities and provenance only; the text-only prepared artifact is publication input, not the
application's serving database. Rebuild both with `uv run python -m tools.build_park_index` after reviewing changes
to source snapshots, then publish and verify the corresponding Qdrant version before deploying its catalog.
