# semanticMemory.py
import chromadb
import json
from colorama import Fore, Style

# Initialize ChromaDB client and collection
client = chromadb.Client()
collection = client.get_or_create_collection("drawing_memory")

def add_to_database(filename, description, specs, silent=False):
    """Add or update a drawing entry in ChromaDB."""
    try:
        try:
            collection.delete(ids=[filename])
        except:
            pass
        
        collection.add(
            ids=[filename],
            documents=[description],
            metadatas=[{"specs": json.dumps(specs)}]
        )
        if not silent:
            print(Fore.GREEN + f"Added to database: {filename}" + Style.RESET_ALL)
        return True
    except Exception as e:
        if not silent:
            print(Fore.RED + f"Error adding {filename} to database: {e}" + Style.RESET_ALL)
        return False

def list_database_files():
    """Return all stored files without showing all data unless requested."""
    try:
        results = collection.get()
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        if not ids:
            print(Fore.YELLOW + "No files in database." + Style.RESET_ALL)
            return []

        # Print only the file list
        print(Fore.CYAN + "\nFiles currently in database:" + Style.RESET_ALL)
        for i, fid in enumerate(ids, 1):
            print(f"{i}) {fid}")

        # Return structured data for interactive_qa()
        return list(zip(ids, docs, [m.get("specs", "{}") for m in metas]))

    except Exception as e:
        print(Fore.RED + f"Error listing database files: {e}" + Style.RESET_ALL)
        return []

def remove_from_database(filename):
    """Remove a file by its filename."""
    try:
        collection.delete(ids=[filename])
        print(Fore.GREEN + f"Removed {filename} from database." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"Error removing {filename}: {e}" + Style.RESET_ALL)

def search_similar_files(query):
    """Search ChromaDB for drawings similar to a given query."""
    try:
        results = collection.query(query_texts=[query], n_results=5)
        matches = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        if not matches:
            print(Fore.YELLOW + "No similar files found." + Style.RESET_ALL)
            return
        print(Fore.CYAN + f"\nTop matches for '{query}':" + Style.RESET_ALL)
        for i, (fid, desc) in enumerate(zip(matches, docs), 1):
            print(f"{i}) {fid} — {desc[:100]}...")
    except Exception as e:
        print(Fore.RED + f"Error during search: {e}" + Style.RESET_ALL)
