"""
IT Knowledge Base: The Pipeline So Far
======================================

Runs the steps in order, each in its own file: read the knowledge base (knowledge_base_loader.py), compare it with
the last run (manifest.py), cut the articles passed on into chunks (chunking.py), embed the chunks (embedding.py),
write them to Qdrant (vector_store.py), then search for each question asked (retriever.py). The parts are built from
kb_settings.toml in wiring.py. It handles:
  1. The command line: which file, which settings, the manifest, --full, --rebuild, --rollback and the log level
  2. The key, checked first when the embedding model needs one (config.py); it's never printed
  3. Each step in order; a missing or bad file, a missing key, a failed embedding or a failed check on the store ends
     the run with one error line and exit code 1, not a traceback
  4. Saving the manifest only once every step has succeeded, so a failed run is run again in full (the vectors made
     before a failure are cached, and the store's writes can be repeated, so that costs little)
  5. Printing the articles passed on, their chunks, vectors and points, what each question finds, then each step's
     checks, then what changed

Usage:
    python pipeline.py                                                # reads data/sample_it_kb.csv
    python pipeline.py --data-path data/sample_it_kb_next.csv         # the next export: only its changes are written
    python pipeline.py --rebuild                                      # every article, into a new collection
    python pipeline.py --rollback                                     # the alias back to the collection before
    python pipeline.py --question "Which ports does the VPN need?" --question "VPN problems with High priority"
"""
import argparse
import logging
import sys
from pathlib import Path

from chunking import KBTextSplitter
from config import MissingKeyError
from embedding import EmbeddingError
from knowledge_base_loader import KB_FILE, MANIFEST_FILE, SETTINGS_FILE, KBLoader
from manifest import Manifest
from retriever import RetrievalError
from settings import load_settings
from utils import (
    print_changes,
    print_chunk_report,
    print_chunks,
    print_documents,
    print_report,
    print_results,
    print_store,
    print_vectors,
)
from vector_store import StoreError
from wiring import make_embedder, make_query_cache, make_reranker, make_retriever, make_store

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

# Searched after each run, unless --question names others
QUESTIONS = ("My VPN keeps timing out when I work from home",)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command-line options; with none, the sample file is read."""
    parser = argparse.ArgumentParser(description="Read the IT knowledge base, pass on what changed since the last "
                                                 "run, cut it into chunks, embed them and store them in Qdrant.")
    parser.add_argument("--data-path", type=Path, default=KB_FILE,
                        help="the CSV file to read (default: data/sample_it_kb.csv, next to this script)")
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE,
                        help="the export's columns, the spellings, the chunk sizes, the embedding model, the store "
                             "(default: kb_settings.toml)")
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_FILE,
                        help="the last run's articles, compared with this run's (default: data/manifest.json)")
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--full", action="store_true",
                      help="pass on every article, not only the ones added or changed since the last run")
    what.add_argument("--rebuild", action="store_true",
                      help="write every article into a new collection, check it, then move the alias to it")
    what.add_argument("--rollback", action="store_true",
                      help="move the alias back to the collection before the current one, and do nothing else")
    parser.add_argument("--question", action="append", default=None,
                        help="a question to search for after the run; give it again for more (default: one about VPN)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="the least serious log messages to show; DEBUG adds one line per row (default: INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run every step, save the manifest, then print what each step did. Returns the exit code: 0 if it ran."""
    args = parse_args(argv)

    # Step 1: Set up logging (stderr)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)

    store = None
    try:
        # Step 2: The settings and the store; --rollback only moves the alias
        settings = load_settings(args.settings)
        store = make_store(settings.vectorstore, settings.embeddings.dimensions, args.settings)
        if args.rollback:
            back = store.rollback()
            print(f"The alias {store.alias} now points at {back}. Its points may be older than the manifest: run "
                  "with --full next, to write every article into it.")
            return 0

        # Step 3: The embedder and its key: a missing key stops the run before anything is read
        embedder = make_embedder(settings.embeddings, args.settings)

        # Step 4: Read the knowledge base, and compare it with the last run (--rebuild: every article)
        loader = KBLoader(args.data_path, settings=settings)
        docs = loader.load()
        manifest = Manifest(args.manifest_path)
        changes = manifest.compare(docs, loader.fingerprints, held=loader.report.held,
                                   full=args.full or args.rebuild)

        # Step 5: Cut the articles passed on into chunks
        splitter = KBTextSplitter(**settings.chunking.model_dump())
        chunks = splitter.split_documents(changes.passed_on())
        logger.info("Cut %d articles into %d chunks", splitter.report.articles, len(chunks))

        # Step 6: Embed the chunks: through the gate, from the cache when it can, the rest by the model
        vectors = embedder.embed(chunks)

        # Step 7: Store them: into a new collection behind the alias (--rebuild), or added and updated in place,
        # with the removed articles' points deleted
        if args.rebuild:
            stored = store.rebuild(chunks, vectors)
        else:
            current = {doc.metadata["doc_id"] for doc in docs} | set(loader.report.held)
            stored = store.write(chunks, vectors, removed=[the_id for the_id, _ in changes.removed], current=current)

        # Step 8: Save the manifest, now that every step has succeeded, keeping each held article's last version
        full = args.full or args.rebuild
        manifest.write(docs, loader.fingerprints, keep=() if full else tuple(loader.report.held))

        # Step 9: Search for each question: the retriever's parts are the store's client and the embedding model
        retriever = make_retriever(settings, store.client, embedder.model, reranker=make_reranker(settings.retrieval),
                                   query_cache=make_query_cache(settings.embeddings, args.settings)).build()
        results = [retriever.search(question) for question in args.question or QUESTIONS]
    except (FileNotFoundError, ValueError, MissingKeyError, EmbeddingError, StoreError, RetrievalError) as err:
        logger.error("%s", err)
        return 1
    finally:
        if store is not None:
            store.client.close()
    logger.info("Stored: %d added, %d updated, %d deleted; %d points in %s", stored.added, stored.updated,
                stored.deleted_stale + stored.deleted_removed, stored.points, stored.collection)
    if stored.orphans:
        logger.warning("%d article%s not in the knowledge base still %s points: run with --rebuild to clear them",
                       len(stored.orphans), "s" if len(stored.orphans) > 1 else "",
                       "have" if len(stored.orphans) > 1 else "has")
    logger.info("Manifest saved: %s (%d articles)", manifest.path.name, len(docs) + len(changes.held))
    if changes.removed and loader.report.unidentified:
        logger.warning("%d skipped row%s had no ID to tell which article it was: an article listed as removed may "
                       "be one; look before deleting it", loader.report.unidentified,
                       "s" if loader.report.unidentified > 1 else "")

    # Step 10: Print the articles passed on, their chunks, vectors and points, what each question found, the
    # checks, then what changed
    print_documents(changes.passed_on(), "Documents passed on to the next step")
    print()
    print_chunks(chunks, parents=len(splitter.parents), ceiling=splitter.max_tokens)
    print()
    print_vectors(vectors, embedder.report, model=embedder.model_name, dimensions=embedder.dimensions)
    print()
    print_store(stored, alias=store.alias, location=settings.vectorstore.location)
    print()
    print_results(results, retriever=retriever)
    print()
    print_report(loader.report)
    print()
    print_chunk_report(splitter.report)
    print()
    print_changes(changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
