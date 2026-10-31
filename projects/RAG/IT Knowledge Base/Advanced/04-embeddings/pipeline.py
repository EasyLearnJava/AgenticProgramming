"""
IT Knowledge Base: The Pipeline So Far
======================================

Runs the steps in order, each in its own file: read the knowledge base (knowledge_base_loader.py), compare it with
the last run (manifest.py), cut the articles passed on into chunks (chunking.py), and embed the chunks
(embedding.py). It handles:
  1. The command line: which file, which settings, the manifest, --full, and the log level
  2. The key, checked first when the embedding model needs one (config.py); it's never printed
  3. Each step in order; a missing or bad file, a missing key or a failed embedding ends the run with one error line
     and exit code 1, not a traceback
  4. Saving the manifest only once every step has succeeded, so a failed run is run again in full (the vectors made
     before a failure are cached, so that costs little)
  5. Printing the articles passed on, their chunks and vectors, then what each step's checks found, then what changed

Usage:
    python pipeline.py                                                # reads data/sample_it_kb.csv
    python pipeline.py --data-path data/sample_it_kb_chunking.csv     # an article for each chunking case
    python pipeline.py --full                                         # pass on every article, not only changes
    python pipeline.py --log-level DEBUG                              # also logs each row and each issue
"""
import argparse
import logging
import sys
from pathlib import Path

from chunking import KBTextSplitter
from config import MissingKeyError, load_api_key
from embedding import ChunkEmbedder, EmbeddingCache, EmbeddingError, make_embedding_model
from knowledge_base_loader import KB_FILE, MANIFEST_FILE, SETTINGS_FILE, KBLoader
from manifest import Manifest
from settings import EmbeddingSettings, load_settings
from utils import print_changes, print_chunk_report, print_chunks, print_documents, print_report, print_vectors

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command-line options; with none, the sample file is read."""
    parser = argparse.ArgumentParser(description="Read the IT knowledge base, pass on what changed since the last "
                                                 "run, cut it into chunks and embed them.")
    parser.add_argument("--data-path", type=Path, default=KB_FILE,
                        help="the CSV file to read (default: data/sample_it_kb.csv, next to this script)")
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE,
                        help="the export's columns, the spellings, the chunk sizes, the embedding model "
                             "(default: kb_settings.toml)")
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_FILE,
                        help="the last run's articles, compared with this run's (default: data/manifest.json)")
    parser.add_argument("--full", action="store_true",
                        help="pass on every article, not only the ones added or changed since the last run")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="the least serious log messages to show; DEBUG adds one line per row (default: INFO)")
    return parser.parse_args(argv)


def make_embedder(settings: EmbeddingSettings, settings_file: Path) -> ChunkEmbedder:
    """The ChunkEmbedder kb_settings.toml describes: its model, its cache (from the settings file's folder) and its
    limits. Gemini needs the key: it's read here, before anything else is done."""
    api_key = load_api_key() if settings.provider == "google" else None
    cache_path = settings.cache_path if settings.cache_path.is_absolute() else \
        settings_file.resolve().parent / settings.cache_path
    model = make_embedding_model(provider=settings.provider, model=settings.model, dimensions=settings.dimensions,
                                 timeout_seconds=settings.timeout_seconds, api_key=api_key)
    return ChunkEmbedder(model, model_name=settings.model_name, dimensions=settings.dimensions,
                         cache=EmbeddingCache(cache_path, model=settings.model_name, dimensions=settings.dimensions),
                         batch_size=settings.batch_size, batch_tokens=settings.batch_tokens,
                         max_concurrency=settings.max_concurrency, max_attempts=settings.max_attempts,
                         timeout_seconds=settings.timeout_seconds, backoff_seconds=settings.backoff_seconds,
                         backoff_max_seconds=settings.backoff_max_seconds)


def main(argv: list[str] | None = None) -> int:
    """Run every step, save the manifest, then print what each step did. Returns the exit code: 0 if it ran."""
    args = parse_args(argv)

    # Step 1: Set up logging (stderr)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)

    try:
        # Step 2: The settings, then the embedder and its key: a typo or a missing key stops the run here
        settings = load_settings(args.settings)
        embedder = make_embedder(settings.embeddings, args.settings)

        # Step 3: Read the knowledge base, and compare it with the last run
        loader = KBLoader(args.data_path, settings=settings)
        docs = loader.load()
        manifest = Manifest(args.manifest_path)
        changes = manifest.compare(docs, loader.fingerprints, held=loader.report.held, full=args.full)

        # Step 4: Cut the articles passed on into chunks
        splitter = KBTextSplitter(**settings.chunking.model_dump())
        chunks = splitter.split_documents(changes.passed_on())
        logger.info("Cut %d articles into %d chunks", splitter.report.articles, len(chunks))

        # Step 5: Embed the chunks: through the gate, from the cache when it can, the rest by the model
        vectors = embedder.embed(chunks)

        # Step 6: Save the manifest, now that every step has succeeded, keeping each held article's last version
        manifest.write(docs, loader.fingerprints, keep=() if args.full else tuple(loader.report.held))
    except (FileNotFoundError, ValueError, MissingKeyError, EmbeddingError) as err:
        logger.error("%s", err)
        return 1
    logger.info("Manifest saved: %s (%d articles)", manifest.path.name, len(docs) + len(changes.held))
    if changes.removed and loader.report.unidentified:
        logger.warning("%d skipped row%s had no ID to tell which article it was: an article listed as removed may "
                       "be one; look before deleting it", loader.report.unidentified,
                       "s" if loader.report.unidentified > 1 else "")

    # Step 7: Print the articles passed on, their chunks and vectors, the checks, then what changed
    print_documents(changes.passed_on(), "Documents passed on to the next step")
    print()
    print_chunks(chunks, parents=len(splitter.parents), ceiling=splitter.max_tokens)
    print()
    print_vectors(vectors, embedder.report, model=embedder.model_name, dimensions=embedder.dimensions)
    print()
    print_report(loader.report)
    print()
    print_chunk_report(splitter.report)
    print()
    print_changes(changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
