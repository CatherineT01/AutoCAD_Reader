# semanticMemory.py
#**************************************************************************************************
#   Refactored with config integration
#   Stores and retrieves AutoCAD drawing descriptions using ChromaDB
#**************************************************************************************************
import os
import json
import hashlib
from typing import Dict, List, Optional
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from colorama import Fore, Style
import logging

# Import configuration
from config import CHROMA_PERSIST_DIR, COLLECTION_NAME

# Silence ChromaDB logging noise
logging.getLogger("chromadb").setLevel(logging.ERROR)

# Ensure persist directory exists
CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)

# Initialize persistent client
client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))

# Default embedding function
default_ef = embedding_functions.DefaultEmbeddingFunction()

# Get or create collection
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=default_ef
)

def generate_embedding_id(file_path: str) -> str:
    """
    Generate stable unique ID based on absolute file path.
    
    Args:
        file_path: Path to file
        
    Returns:
        SHA256 hash of absolute path
    """
    abs_path = os.path.abspath(file_path)
    return hashlib.sha256(abs_path.encode("utf-8")).hexdigest()

def file_exists_in_database(file_path: str) -> bool:
    """
    Check if a file exists in the database by its stable ID.
    
    Args:
        file_path: Path to file
        
    Returns:
        True if file exists in database
    """
    try:
        embedding_id = generate_embedding_id(file_path)
        results = collection.get(ids=[embedding_id])
        return bool(results and results.get("ids"))
    except Exception:
        return False

def add_to_database(file_path: str, description: str, specs: Dict, silent: bool = False) -> bool:
    """
    Add a file to the collection if not already present.
    
    Args:
        file_path: Path to file (PDF or DWG)
        description: Natural language description
        specs: Dictionary of specifications
        silent: Suppress output messages
        
    Returns:
        True if successful
    """
    try:
        filename = os.path.basename(file_path)

        # Skip if already in DB
        if file_exists_in_database(file_path):
            if not silent:
                print(Fore.YELLOW + f"⚠ Already in DB: {filename}" + Style.RESET_ALL)
            return True

        embedding_id = generate_embedding_id(file_path)
        
        # Determine file type
        file_type = 'dwg' if file_path.lower().endswith('.dwg') else 'pdf'
        
        metadata = {
            "filename": filename,
            "filepath": os.path.abspath(file_path),
            "file_type": file_type,
            "description": description or "",
            "specs": json.dumps(specs or {})  # store as JSON string
        }

        collection.add(
            ids=[embedding_id],
            documents=[description or ""],
            metadatas=[metadata]
        )

        if not silent:
            file_emoji = "📐" if file_type == 'dwg' else "📄"
            print(Fore.GREEN + f"✓ {file_emoji} Added: {filename}" + Style.RESET_ALL)
        return True

    except Exception as e:
        if not silent:
            print(Fore.RED + f"✗ Error adding {os.path.basename(file_path)}: {e}" + Style.RESET_ALL)
        return False

def get_from_database(filename_or_path: str) -> Optional[Dict]:
    """
    Retrieve a single file's data.
    
    Args:
        filename_or_path: Absolute path or filename
        
    Returns:
        Dict with file information or None
    """
    try:
        # Prefer absolute path
        abs_path = filename_or_path
        if not os.path.isabs(filename_or_path):
            abs_path = filename_or_path

        embedding_id = generate_embedding_id(abs_path)
        results = collection.get(ids=[embedding_id])

        if results and results.get("ids"):
            meta = results.get("metadatas", [{}])[0] or {}
            specs_raw = meta.get("specs", "{}")
            specs = specs_raw if isinstance(specs_raw, dict) else json.loads(specs_raw)

            return {
                "filename": meta.get("filename", os.path.basename(filename_or_path)),
                "filepath": meta.get("filepath", filename_or_path),
                "file_type": meta.get("file_type", "pdf"),
                "description": results.get("documents", [""])[0],
                "specs": specs
            }
    except Exception as e:
        print(Fore.RED + f"✗ Error retrieving {filename_or_path}: {e}" + Style.RESET_ALL)

    return None

def list_database_files() -> List[tuple]:
    """
    List all files in the database.
    
    Returns:
        List of tuples: (filepath, description, specs_json)
    """
    try:
        if collection.count() == 0:
            return []

        results = collection.get(include=["metadatas", "documents"])
        metadatas = results.get("metadatas", [])
        documents = results.get("documents", [])

        output = []
        for i, meta in enumerate(metadatas):
            filepath = meta.get("filepath", meta.get("filename", ""))
            description = documents[i] if i < len(documents) else ""
            specs_json = meta.get("specs", "{}")
            output.append((filepath, description, specs_json))

        return output

    except Exception as e:
        print(Fore.RED + f"✗ Error listing database: {e}" + Style.RESET_ALL)
        return []

def remove_from_database(filename_or_path: str) -> bool:
    """
    Remove a file from the database using its stable ID.
    
    Args:
        filename_or_path: Path to file
        
    Returns:
        True if successful
    """
    try:
        abs_path = filename_or_path
        if not os.path.isabs(filename_or_path):
            abs_path = filename_or_path

        embedding_id = generate_embedding_id(abs_path)
        collection.delete(ids=[embedding_id])
        print(Fore.GREEN + f"✓ Removed: {os.path.basename(filename_or_path)}" + Style.RESET_ALL)
        return True
    except Exception as e:
        print(Fore.RED + f"✗ Error removing file: {e}" + Style.RESET_ALL)
        return False

def search_similar_files(query: str, n_results: int = 5, file_type: Optional[str] = None) -> List[Dict]:
    """
    Semantic search over descriptions.
    
    Args:
        query: Search query
        n_results: Number of results to return
        file_type: Optional filter ('pdf' or 'dwg')
        
    Returns:
        List of matching files with metadata
    """
    try:
        results = collection.query(query_texts=[query], n_results=n_results * 2)  # Get extra for filtering
        matches = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not matches:
            print(Fore.YELLOW + "⚠ No similar files found" + Style.RESET_ALL)
            return []

        # Filter by file type if specified
        filtered_results = []
        for fid, desc, meta in zip(matches, docs, metas):
            if file_type and meta.get('file_type') != file_type:
                continue
            filtered_results.append((fid, desc, meta))
            if len(filtered_results) >= n_results:
                break

        print(Fore.CYAN + f"\n🔍 Top {len(filtered_results)} matches for '{query}':" + Style.RESET_ALL)
        results_list = []
        for i, (fid, desc, meta) in enumerate(filtered_results, 1):
            display_name = meta.get("filename", os.path.basename(meta.get("filepath", fid)))
            filepath = meta.get("filepath", fid)
            ftype = meta.get("file_type", "pdf")
            emoji = "📐" if ftype == 'dwg' else "📄"
            
            print(f"{i}) {emoji} {display_name}")
            print(f"   {desc[:120]}...")
            
            results_list.append({
                "filename": display_name,
                "filepath": filepath,
                "file_type": ftype,
                "description": desc
            })

        return results_list

    except Exception as e:
        print(Fore.RED + f"✗ Error during search: {e}" + Style.RESET_ALL)
        return []

def get_database_stats() -> Dict:
    """
    Return collection statistics.
    
    Returns:
        Dict with file counts by type
    """
    try:
        files = list_database_files()
        pdf_count = sum(1 for f, _, _ in files if not f.lower().endswith('.dwg'))
        dwg_count = sum(1 for f, _, _ in files if f.lower().endswith('.dwg'))
        
        return {
            "total_files": len(files),
            "pdf_files": pdf_count,
            "dwg_files": dwg_count,
            "collection_name": COLLECTION_NAME,
            "persist_directory": str(CHROMA_PERSIST_DIR)
        }
    except Exception:
        return {
            "total_files": 0,
            "pdf_files": 0,
            "dwg_files": 0
        }

def clear_database(confirm: bool = False) -> bool:
    """
    Clear all entries from the database.
    
    Args:
        confirm: Must be True to proceed (safety check)
        
    Returns:
        True if successful
    """
    if not confirm:
        print(Fore.RED + "⚠ Must confirm to clear database" + Style.RESET_ALL)
        return False
    
    try:
        client.delete_collection(name=COLLECTION_NAME)
        # Recreate empty collection
        global collection
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=default_ef
        )
        print(Fore.GREEN + "✓ Database cleared" + Style.RESET_ALL)
        return True
    except Exception as e:
        print(Fore.RED + f"✗ Error clearing database: {e}" + Style.RESET_ALL)
        return False