# 01 · Read the Knowledge Base, in Real Time (Expert)

> **Status:** 📝 Planned: [TODO.md](TODO.md) is the plan; there's no code yet.
> **Expert version of:** [Advanced · 01](../../Advanced/01-read-the-knowledge-base/README.md)

The Advanced version reads one CSV file, once, and checks every row. A production RAG application reads many systems
(files, Salesforce, SharePoint, databases, APIs, streams), keeps up with every change they make, and reads some
values only when a question is asked. This project plans that.

![How production RAG reads its data](images/ingestion.svg)

---

## 🗺️ The Plan, in TODO.md

1. [How many ways? The short answer](TODO.md#1-how-many-ways-the-short-answer): 11 ways to read the data, which come
   down to 4: read it all, ask on a schedule, be told, or read it at question time
2. [The 11 ways](TODO.md#2-the-11-ways): how each one reads, notices a change and notices a delete, its sources, and
   how fresh it is
3. [Which way for which source](TODO.md#3-which-way-for-which-source): a recommendation for 19 kinds of source
4. [Salesforce](TODO.md#4-salesforce): Bulk API, SOQL, Change Data Capture, Platform Events and question time, and
   what a Salesforce sync must handle
5. [What real time adds](TODO.md#5-what-real-time-adds-scenarios-to-handle): deletes, repeats, order, missed
   changes, scale, cost, permissions and security, and running it
6. [Evals](TODO.md#6-evals): freshness, completeness, deletes, canary documents, permission leaks and failures on
   purpose
7. [What to learn first](TODO.md#7-what-to-learn-first): five patterns, in order, and why not all data should be
   embedded
8. [The build plan](TODO.md#8-the-build-plan): 14 steps, each on top of the one before

---

## 📁 Project Structure

```text
01-read-the-knowledge-base/
├── TODO.md                               # the plan: every way to read the data, and what real time needs
├── images/
│   ├── ingestion.svg                     # how production RAG reads its data: ingestion, and question time
│   └── salesforce.svg                    # Salesforce: bulk load, CDC, reconcile, live values
└── README.md                             # you are here
```
