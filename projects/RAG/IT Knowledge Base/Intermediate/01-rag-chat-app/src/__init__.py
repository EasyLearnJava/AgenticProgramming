"""
IT Knowledge Base: The RAG Chat App
===================================

The application, one package per layer, each with one job:

    config         every setting, from config.yaml; the API key, from the environment
    observability  logging, trace IDs and timed spans
    ingestion      the knowledge base file -> Documents
    chunking       Documents -> chunks, each with a stable ID
    embeddings     texts -> vectors
    vectordb       vectors stored and searched
    retrieval      a question -> the closest chunks
    prompts        the prompt the model answers from
    llm            the chat model's calls
    pipeline       the parts wired into one RAGEngine
    api            the HTTP API and the chat page
    utils          small helpers

exceptions.py holds the errors every layer raises.
"""
