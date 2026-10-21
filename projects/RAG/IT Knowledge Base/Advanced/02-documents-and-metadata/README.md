# 02 · Documents and Metadata (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 02 · Documents and Metadata](../../Basic/02-documents-and-metadata/README.md)

The basic version splits each article into text (title, problem, resolution, notes) and labels (system, category,
priority, tags), trusting every value. This version makes the labels reliable enough to filter, cite and update by:
each article is validated against a schema, its labels are typed and normalized, it gets an ID that never changes,
and a re-run loads only what changed.

---

## 🎯 What This Project Will Do

- **Validate every article against a schema** before it becomes a Document, and report what fails, as Advanced/01 does
- **Type and normalize the labels**: `priority` as one of four values, `tags` as a list, `system` and `category`
  mapped to one spelling each
- **Give each article a stable ID** that survives re-ordering the file, so it can be updated or deleted later
- **Record provenance**: which file, its checksum, when it was loaded, and by which version of the loader
- **Load only what changed** since the last run: added, edited and removed articles, each listed

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Schema validation** | A Pydantic model for an article: required fields, lengths, allowed values; one report line per failure | Bad rows are caught at the door, with a reason, not found later as odd answers |
| 2 | **Column mapping as configuration** | Which columns are text and which are labels, read from a settings file rather than written in the code | A new export with renamed columns needs a config change, not a code change |
| 3 | **Typed labels** | `priority` as an enum, `tags` split on `;` into a list, empty values as `None` | Filters like "priority is High" and "tag is vpn" work exactly, not by text matching |
| 4 | **Normalized values** | One spelling per system and category (`Wi-Fi`, `WiFi`, `wifi` become `WiFi`), with a table of synonyms | The same system isn't split across three labels |
| 5 | **Stable document IDs** | An ID from the article's source key (or a hash of its title and system), not its row number | Re-sorting the file doesn't change IDs, so updates and deletes hit the right article |
| 6 | **Provenance** | `source`, file checksum, `loaded_at` and loader version in each Document's metadata | Any answer can be traced to the exact file and load it came from |
| 7 | **Incremental loading** | A manifest of IDs and content hashes from the last run; only added and changed articles are passed on, removed ones are listed for deletion | Re-loading 10,000 articles to change one is slow and costly further down the line |
| 8 | **Access labels** | An optional `visibility` or `team` label per article | Later steps can show each user only the articles they may see |

---

## 🏗️ Planned Architecture

```text
CSV export ──→ read rows ──→ validate (schema) ──→ normalize labels ──→ stable ID + provenance
                                   │                                          │
                                   └──→ report: failed rows, and why           ↓
                                                              compare with the last run's manifest
                                                                             │
                                                   ┌─────────────────────────┼──────────────────────┐
                                                   ↓                         ↓                      ↓
                                               added                     changed                 removed
                                                   └──────────→ Documents passed on ←──────────┘   (listed for deletion)
```

---

## ✅ Done When

- A data file with one row for each problem: a missing field, an unknown priority, three spellings of one system,
  a re-ordered copy of the file, an edited article and a removed one
- Tests for each case, and for IDs staying the same when the file is re-sorted
- A report listing every article that failed, was normalized, added, changed or removed, and why

---

## 📚 Next Steps

**[03 · Chunking (Advanced)](../03-chunking/README.md)**: chunks cut along the article's sections, sized in tokens,
with stable IDs.
