# semanticMemory.py
import os
import json
import base64
import numpy as np
from io import BytesIO
from utils import client, load_cache, save_cache, CACHE_FILE, INDEX_FILE, META_FILE

# ----------------------------------------------------------------------
# 1. Text embedding (used for description + OCR fallback)
# ----------------------------------------------------------------------
def get_text_embedding(text: str):
    try:
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return resp.data[0].embedding
    except Exception as e:
        print(f"[Embedding error] {e}")
        return None

# ----------------------------------------------------------------------
# 2. OPTIONAL: Vision embedding (gpt-4o) 
# ----------------------------------------------------------------------
def get_image_embedding(pdf_path: str):
    """
    Sends the **first page** of the PDF to gpt-4o (vision) and returns the
    embedding that OpenAI returns for that image.
    """
    try:
        # Convert first page to base64 PNG
        from pdf2image import convert_from_path
        from PDF_Analyzer import POPPLER_PATH
        pages = convert_from_path(pdf_path, first_page=1, last_page=1,
                                  dpi=300, poppler_path=POPPLER_PATH)
        img = pages[0]
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        b64 = base64.b64encode(buffered.getvalue()).decode()

        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return an embedding for this technical drawing."},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }],
            # OpenAI returns an embedding when you ask for it in the response format
            extra_body={"response_format": {"type": "json_object"}}
        )
        # The embedding is under resp.choices[0].message.content (JSON string)
        data = json.loads(resp.choices[0].message.content)
        return data.get("embedding")
    except Exception as e:
        print(f"[Vision embedding error] {e}")
        return None

# ----------------------------------------------------------------------
# 3. Build the FAISS-style JSON index
# ----------------------------------------------------------------------
def build_index():
    cache = load_cache()
    embeddings = []          
    metadata   = []          

    for file_hash, entry in cache.items():
        # --------------------------------------------------------------
        # 3a – Text vector (description + optional OCR)
        # --------------------------------------------------------------
        if "embedding" not in entry:
            txt = entry.get("description", "")
            ocr = entry.get("ocr_text", "")
            full_txt = txt + "\n" + ocr
            vec = get_text_embedding(full_txt)
            if vec:
                entry["embedding"] = vec

        # --------------------------------------------------------------
        # 3b – OPTIONAL Vision vector (adds a second vector per file)
        # --------------------------------------------------------------
        if "vision_embedding" not in entry and "path" in entry:
            v_vec = get_image_embedding(entry["path"])
            if v_vec:
                entry["vision_embedding"] = v_vec

        # --------------------------------------------------------------
        # 3c – Store the *primary* text embedding
        # --------------------------------------------------------------
        if "embedding" in entry:
            embeddings.append(np.array(entry["embedding"], dtype="float32"))
            metadata.append((file_hash, entry.get("path", "")))

    # Save updated cache (now contains embeddings)
    save_cache(cache)

    if not embeddings:
        print("Nothing to index.")
        return

    # ------------------------------------------------------------------
    # Write a simple JSON index (you can replace this with FAISS later)
    # ------------------------------------------------------------------
    index_data = {
        "embeddings": [e.tolist() for e in embeddings],
        "metadata": metadata
    }
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)

    print(f"Index built – {len(embeddings)} text vectors (vision vectors stored in cache)")

# ----------------------------------------------------------------------
# 4. Search – text query against text embeddings
# ----------------------------------------------------------------------
def search_similar_files(query: str, top_k: int = 3):
    if not os.path.exists(INDEX_FILE):
        print("Run 'build index' first.")
        return []

    q_vec = get_text_embedding(query)
    if not q_vec:
        return []

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    embeddings = np.array(data["embeddings"], dtype="float32")
    metadata   = data["metadata"]

    q_vec = np.array(q_vec, dtype="float32").reshape(1, -1)
    distances = np.linalg.norm(embeddings - q_vec, axis=1)
    top_idx   = np.argsort(distances)[:top_k]

    return [metadata[i] for i in top_idx]

# ----------------------------------------------------------------------
# 5. Vision-only search 
# ----------------------------------------------------------------------
def search_by_image(pdf_path: str, top_k: int = 3):
    """Search using the *vision* embedding of the supplied PDF."""
    cache = load_cache()
    q_vec = get_image_embedding(pdf_path)
    if not q_vec:
        return []

    matches = []
    for h, entry in cache.items():
        v_vec = entry.get("vision_embedding")
        if v_vec:
            dist = np.linalg.norm(np.array(v_vec) - np.array(q_vec))
            matches.append((dist, h, entry.get("path", "")))

    matches.sort(key=lambda x: x[0])
    return [(h, path) for _, h, path in matches[:top_k]]