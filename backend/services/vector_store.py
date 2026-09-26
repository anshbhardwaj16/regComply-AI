import chromadb
from chromadb.config import Settings

_client = None


def get_client() -> chromadb.Client:
    global _client
    if _client is None:
        _client = chromadb.Client(Settings(anonymized_telemetry=False))
    return _client


def store_chunks(collection_name: str, chunks: list[str], metadata_prefix: str = "") -> None:
    client = get_client()
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(collection_name)
    collection.add(
        documents=chunks,
        ids=[f"{metadata_prefix}chunk_{i}" for i in range(len(chunks))],
        metadatas=[{"source": metadata_prefix, "chunk_index": i} for i in range(len(chunks))],
    )


def query_chunks(collection_name: str, query: str, n_results: int = 5) -> list[str]:
    client = get_client()
    collection = client.get_collection(collection_name)
    results = collection.query(query_texts=[query], n_results=min(n_results, collection.count()))
    return results["documents"][0] if results["documents"] else []


def reset_store(session_id: str) -> None:
    client = get_client()
    for suffix in ["_regulations", "_controls"]:
        try:
            client.delete_collection(f"{session_id}{suffix}")
        except Exception:
            pass
