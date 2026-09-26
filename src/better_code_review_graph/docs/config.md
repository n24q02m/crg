# config Tool Documentation

Server configuration, status, cache management, and credential setup.

## Config Actions

### status
Show current server status including graph counts and the selected embedding
backend, model, selected storage dimensions, and fallback result. Status resolves
configuration only; it does not load the embedding model.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "status"}
```

**Returns:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "graph_path": "/path/to/.better-code-review-graph/graph.db",
  "embedding_backend": "local",
  "embedding_model": "n24q02m/Qwen3-Embedding-0.6B-ONNX",
  "embedding_dimensions": 768,
  "embedding_fallback": "none",
  "total_nodes": 1234,
  "total_edges": 5678,
  "files_count": 42,
  "languages": ["Python", "TypeScript"],
  "embeddings_count": 890,
  "last_updated": "2026-03-20T12:00:00"
}
```

---

### set
Update a runtime setting.

**Parameters:**
- `key` (required): Setting key
- `value` (required): New value

**Valid keys:**
- `log_level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**Example:**
```json
{"action": "set", "key": "log_level", "value": "DEBUG"}
```

---

### cache_clear
Remove all computed embeddings from the graph database. After clearing, run `graph action=embed` to recompute.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "cache_clear"}
```

**Returns:**
```json
{
  "status": "cache cleared",
  "embeddings_removed": 890
}
```

---

## Setup Actions

Setup actions manage host-owned model cells — there is no browser or relay
flow; the host owns all credential material.

### setup_status
Show current credential state and which model cells have keys.

**Example:**
```json
{"action": "setup_status"}
```

---

### setup_start
Explain where the host configures API keys.

**Parameters:**
- `force`: If true, reconfigure even when already configured (default: false)

**Example:**
```json
{"action": "setup_start"}
```

---

### setup_skip
Set local mode — local ONNX embedding, no cloud cells.

**Example:**
```json
{"action": "setup_skip"}
```

---

### setup_reset
Reset state to local; the host config re-resolves on next call.

**Example:**
```json
{"action": "setup_reset"}
```

---

### setup_complete
Re-resolve credential state from the host configuration.

**Example:**
```json
{"action": "setup_complete"}
```
