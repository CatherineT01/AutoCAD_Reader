import os
import json
import fitz 
import pdfplumber
from pdf2image import convert_from_path
from utils import openai_client, grok_client, load_cache, save_cache, get_file_hash, CACHE_FILE, is_valid_specs,is_poppler_available,chat_with_ai

# --- Paths ---
BASE_DIR = os.path.dirname(__file__)
POPPLER_PATH = os.path.join(BASE_DIR, "poppler", "bin")
TESSERACT_PATH = os.path.join(BASE_DIR, "tesseract", "tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def find_pdf(list_all=False, root="."):
    """
    Scan the given directory (and subfolders) for likely AutoCAD PDFs.
    Only PDFs that pass is_autocad_pdf() are returned.
    """
    # First, count all PDFs
    all_pdfs = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".pdf"):
                all_pdfs.append(os.path.join(dirpath, f))
    
    total_pdfs = len(all_pdfs)
    print(Fore.CYAN + f"\nScanning {total_pdfs} PDF files in directory..." + Style.RESET_ALL)
    
    matches = []
    for idx, path in enumerate(all_pdfs, 1):
        f = os.path.basename(path)
        try:
            # Show progress on same line
            print(Fore.BLUE + f"\r[{idx}/{total_pdfs}] Processing... {len(matches)} AutoCAD PDFs found" + Style.RESET_ALL, end='', flush=True)
            
            if is_autocad_pdf(path, silent=True):
                matches.append(path)
        except Exception as e:
            pass  # Silent error handling
    
    # Clear the progress line and show final result
    print(Fore.GREEN + f"\r[{total_pdfs}/{total_pdfs}] Complete! Found {len(matches)} AutoCAD PDFs" + Style.RESET_ALL + " " * 20)
    
    if list_all:
        print(Fore.CYAN + f"\n{'='*60}" + Style.RESET_ALL)
        print(Fore.CYAN + f"Verified AutoCAD PDFs:" + Style.RESET_ALL)
        print(Fore.CYAN + f"{'='*60}" + Style.RESET_ALL)
        for i, m in enumerate(matches, 1):
            print(f"{i}) {m}")
    
    return matches

def is_autocad_pdf(pdf_path, silent=False):
    """Use AI to determine if a PDF is an AutoCAD drawing with robust fallback."""
    text = extract_text(pdf_path, silent=True)
    
    # Handle None returns from extract_text
    if text is None:
        text = ""
    
    if not text.strip():
        ocr_text = ocr_full_document(pdf_path, silent=True)
        # Handle None returns from OCR
        if ocr_text is None:
            text = ""
        else:
            text = ocr_text

    # If still no text, assume it might be AutoCAD (images/drawings often have no text)
    if not text.strip():
        if not silent:
            print(Fore.YELLOW + f"[!] No text extracted from {os.path.basename(pdf_path)} - treating as potential AutoCAD drawing." + Style.RESET_ALL)
        return True  # Many AutoCAD PDFs are image-based

    prompt = f"""
You are an AutoCAD expert.
The following text was extracted from a PDF document:

{text[:3000]}

Determine if this PDF contains a technical AutoCAD drawing.
Answer ONLY 'Yes' or 'No' with no additional text.
"""
    
    # Try with Grok/OpenAI fallback
    answer = chat_with_ai(prompt, temperature=0, silent=True)
    
    if not answer:
        if not silent:
            print(Fore.YELLOW + f"[!] AI unavailable for {os.path.basename(pdf_path)} - including by default." + Style.RESET_ALL)
        return True  # Include file if AI check fails
    
    answer = answer.strip().lower()
    
    # More flexible answer parsing
    if "yes" in answer or answer.startswith("y"):
        return True
    elif "no" in answer or answer.startswith("n"):
        return False
    else:
        # If unclear response, be permissive and include it
        if not silent:
            print(Fore.YELLOW + f"[!] Unclear AI response for {os.path.basename(pdf_path)}: '{answer}' - including by default." + Style.RESET_ALL)
        return True
# ============================================================
# TEXT EXTRACTION
# ============================================================
def extract_text(pdf_path, silent=False):
    """Try to extract text from the PDF using pdfplumber and PyMuPDF."""
    text = ""
    # Try pdfplumber
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            if not silent:
                print(Fore.GREEN + "[✓] Text extracted with pdfplumber." + Style.RESET_ALL)
            return text
    except Exception as e:
        if not silent:
            print(Fore.YELLOW + f"[!] pdfplumber failed: {e}. Trying PyMuPDF..." + Style.RESET_ALL)
    
    # Fallback to PyMuPDF
    try:
        with fitz.open(pdf_path) as doc:
            text = "\n".join(page.get_text() or "" for page in doc)
        if text.strip():
            if not silent:
                print(Fore.GREEN + "[✓] Text extracted with PyMuPDF." + Style.RESET_ALL)
            return text
        else:
            if not silent:
                print(Fore.YELLOW + "[!] No embedded text found. Switching to OCR..." + Style.RESET_ALL)
            return ""  # Changed from None to empty string
    except Exception as e:
        if not silent:
            print(Fore.RED + f"[✗] PyMuPDF failed: {e}. Switching to OCR..." + Style.RESET_ALL)
        return ""

# ============================================================
# OCR EXTRACTION
# ============================================================
def _preprocess_page(img, pdf_path):
    """Enhance image for OCR with multiple preprocessing techniques."""
    try:
        img = img.convert("L")  # Convert to grayscale
        arr = np.array(img)
        # Apply bilateral filter for noise reduction
        arr = cv2.bilateralFilter(arr, 11, 17, 17)
        # Adaptive thresholding
        arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        # Additional contrast enhancement
        arr = cv2.equalizeHist(arr)
        return Image.fromarray(arr)
    except Exception as e:
        print(Fore.RED + f"[✗] Preprocessing failed for {os.path.basename(pdf_path)}: {e}" + Style.RESET_ALL)
        return img

def ocr_full_document(pdf_path, silent=False):
    """Run OCR on all pages with enhanced preprocessing."""
    if not is_poppler_available():
        if not silent:
            print(Fore.YELLOW + "[!] OCR skipped: Poppler not installed or not in PATH." + Style.RESET_ALL)
        return ""  # Changed from None to empty string

    try:
        pages = convert_from_path(pdf_path, dpi=300)
        all_text = ""
        for i, page in enumerate(pages, 1):
            processed = _preprocess_page(page, pdf_path)
            text = pytesseract.image_to_string(processed, lang="eng", config='--psm 6')
            all_text += text + "\n"
            if not silent:
                print(Fore.CYAN + f"OCR processed page {i}/{len(pages)}" + Style.RESET_ALL)
        if all_text.strip():
            if not silent:
                print(Fore.GREEN + "[✓] OCR completed successfully." + Style.RESET_ALL)
        else:
            if not silent:
                print(Fore.YELLOW + "[!] OCR found no readable text." + Style.RESET_ALL)
        return all_text
    except Exception as e:
        if not silent:
            print(Fore.RED + f"[✗] OCR failed: {e}" + Style.RESET_ALL)
        return ""

# ============================================================
# SPECIFICATION PARSING
# ============================================================
def extract_specs_from_text(text):
    """Extract structured data from text (dimensions, scale, title, etc.)."""
    specs = {}
    if not text.strip():
        return specs
    try:
        import re
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Scale
            if re.search(r"\bscale\b.*?\b\d+[:]\d+\b", line, re.I) or "scale" in line.lower():
                specs["Scale"] = line
            # Dimensions
            if re.search(r"\b\d+(\.\d+)?\s*(mm|cm|m|in|ft)\b", line, re.I):
                specs.setdefault("Dimensions", []).append(line)
            # Revision
            if re.search(r"\brev(ision)?\b.*?\d+", line, re.I):
                specs["Revision"] = line
            # Title or Drawing Number
            if re.search(r"\b(title|drawing no\.|dwg no\.)\b", line, re.I):
                specs["Title"] = line
            # Common AutoCAD metadata
            if re.search(r"\b(project|sheet|drawn by|checked by|date)\b", line, re.I):
                key = line.split(":")[0].strip().title()
                specs[key] = line
    except Exception as e:
        print(Fore.RED + f"[✗] Spec extraction failed: {e}" + Style.RESET_ALL)
    return specs

# ============================================================
# DESCRIPTION GENERATION
# ============================================================
def generate_description(text, specs):
    """Generate human-readable description using OpenAI or Grok."""
    if not text.strip() and not specs:
        return "No text or specs extracted from the drawing."

    prompt = f"""
You are an expert AutoCAD drawing summarizer.
Extracted text (first 3000 characters):
{text[:3000]}
Extracted specifications:
{json.dumps(specs, indent=2)}
Write a concise, plain English summary (100-200 words) explaining what this AutoCAD drawing represents. 
Include key details such as the type of drawing, main components, dimensions, scale, and any relevant metadata (e.g., project, revision, or title).
If specific details are missing, note that and provide a general description only based on available information.
"""
    desc = chat_with_ai(prompt, temperature=0.4, max_tokens=300)
    if desc:
        print(Fore.GREEN + "[✓] Description generated successfully." + Style.RESET_ALL)
        return desc
    else:
        print(Fore.YELLOW + "[!] No AI provider available for description generation." + Style.RESET_ALL)
        return "Unable to generate description: No API available."
 
# ============================================================
# QUESTION ANSWERING
# ============================================================
def answer_question(question, text, specs, description):
    """Answer user questions about a specific drawing using OpenAI or Grok."""
    if not text.strip() and not specs and not description:
        return "No data available to answer questions about this drawing."
    prompt = f"""
You are an AutoCAD drawing analysis assistant.
Drawing details:
- Extracted text: {text[:3000]}
- Specifications: {json.dumps(specs, indent=2)}
- Description: {description}
User question: {question}
Provide a concise and accurate answer based on the available drawing details. If the information is insufficient, state so clearly.
"""

    if openai_client:
        try:
            print(Fore.BLUE + "[→] Answering question using OpenAI..." + Style.RESET_ALL)
            completion = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an AutoCAD drawing analysis assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=200
            )
            answer = completion.choices[0].message.content.strip()
            print(Fore.GREEN + "[✓] Answer generated successfully." + Style.RESET_ALL)
            return answer
        except Exception as e:
            print(Fore.RED + f"[✗] OpenAI question answering failed: {e}" + Style.RESET_ALL)
    if grok_client:
        try:
            print(Fore.BLUE + "[→] Falling back to Grok for question answering..." + Style.RESET_ALL)
            completion = grok_client.chat.completions.create(
                model="grok-3-fast-beta",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=200
            )
            answer = completion.choices[0].message.content.strip()
            print(Fore.GREEN + "[✓] Answer generated via Grok." + Style.RESET_ALL)
            return answer
        except Exception as e:
            print(Fore.RED + f"[✗] Grok question answering failed: {e}" + Style.RESET_ALL)
    
    return "Unable to answer question: No API available."

# ============================================================
# PROCESSING PIPELINE
# ============================================================
def process_pdf(file_path):
    """
    Extract text/specs from PDF and add to database if valid AutoCAD PDF.
    Returns True if successfully added, False otherwise.
    """
    if not os.path.exists(file_path):
        print(Fore.RED + f"File does not exist: {file_path}" + Style.RESET_ALL)
        return False
    if not is_autocad_pdf(file_path):
        print(Fore.YELLOW + f"Skipped: Not a valid AutoCAD PDF -> {os.path.basename(file_path)}" + Style.RESET_ALL)
        return False

    from PDF_Analyzer import extract_text, ocr_full_document, extract_specs_from_text, generate_description
    text = extract_text(file_path)
    if not text.strip():
        text = ocr_full_document(file_path)

    specs = extract_specs_from_text(text)
    if not is_valid_specs(specs):
        print(Fore.YELLOW + f"Skipped: No valid specs found in {os.path.basename(file_path)}" + Style.RESET_ALL)
        return False
    desc = generate_description(text, specs) #generate description 

    from semanticMemory import add_to_database
    if add_to_database(file_path, desc, specs):
        print(Fore.GREEN + f"Completed and saved: {os.path.basename(file_path)}" + Style.RESET_ALL)
        return True
    else:
        print(Fore.RED + f"Failed to save to database: {os.path.basename(file_path)}" + Style.RESET_ALL)
        return False