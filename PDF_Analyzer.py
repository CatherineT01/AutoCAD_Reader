#PDF_Analyzer.py
#**************************************************************************************************
#   Refactored PDF_Analyzer with config integration
#   Extracts text from PDF files, adds files to semantic database, and enables Q&A
#**************************************************************************************************
import os
import json
from colorama import init, Fore, Style
init(autoreset=True)
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import numpy as np
import cv2

# Import configuration
from config import (
    TESSERACT_PATH, POPPLER_PATH, OCR_DPI, OCR_LANG, 
    OCR_PSM, OCR_OEM, GROK_MODEL, OPENAI_MODEL,
    DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS, ENABLE_OCR
)
from utils import grok_client, openai_client, chat_with_ai, clean_specs
from semanticMemory import add_to_database, file_exists_in_database, list_database_files

# Set Tesseract path from config
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def is_poppler_available():
    """Check if Poppler is available for PDF to image conversion."""
    pdfinfo_exe = os.path.join(POPPLER_PATH, "pdfinfo.exe")
    return os.path.exists(pdfinfo_exe) and os.access(pdfinfo_exe, os.X_OK)

# Check OCR availability
OCR_AVAILABLE = (
    ENABLE_OCR and 
    TESSERACT_PATH is not None and 
    os.path.exists(TESSERACT_PATH) and 
    is_poppler_available()
)

if not OCR_AVAILABLE:
    print(Fore.RED + "⚠ OCR dependencies missing! Check config.py" + Style.RESET_ALL)
else:
    print(Fore.GREEN + "✓ OCR dependencies recognized" + Style.RESET_ALL)

def extract_text(pdf_path, silent=False):
    """Extract embedded text from PDF using multiple methods."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text() or "" for page in doc])
        if text.strip():
            if not silent: 
                print(Fore.GREEN + "✓ Text extracted via PyMuPDF" + Style.RESET_ALL)
            return text
    except Exception as e:
        if not silent:
            print(Fore.YELLOW + f"PyMuPDF failed: {e}" + Style.RESET_ALL)
    
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            if text.strip():
                if not silent: 
                    print(Fore.GREEN + "✓ Text extracted via pdfplumber" + Style.RESET_ALL)
                return text
    except Exception as e:
        if not silent:
            print(Fore.YELLOW + f"pdfplumber failed: {e}" + Style.RESET_ALL)
    
    if not silent: 
        print(Fore.YELLOW + "⚠ No embedded text found" + Style.RESET_ALL)
    return ""

def _preprocess_page(img):
    """Preprocess image for better OCR results."""
    img = img.convert("L")
    arr = np.array(img)
    arr = cv2.bilateralFilter(arr, 15, 25, 25)
    arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 15, 5)
    arr = cv2.equalizeHist(arr)
    return Image.fromarray(arr)

def ocr_full_document(pdf_path, silent=False):
    """Perform OCR on entire PDF document."""
    if not OCR_AVAILABLE:
        if not silent: 
            print(Fore.YELLOW + "[!] OCR skipped (not configured)" + Style.RESET_ALL)
        return ""
    try:
        pages = convert_from_path(pdf_path, dpi=OCR_DPI, poppler_path=POPPLER_PATH)
        all_text = ""
        for i, page in enumerate(pages, 1):
            processed = _preprocess_page(page)
            config_str = f'--psm {OCR_PSM} --oem {OCR_OEM}'
            text = pytesseract.image_to_string(processed, lang=OCR_LANG, config=config_str)
            all_text += text + "\n"
            if not silent: 
                print(Fore.CYAN + f"  ✓ OCR page {i}/{len(pages)}" + Style.RESET_ALL)
        return all_text
    except Exception as e:
        if not silent: 
            print(Fore.RED + f"✗ OCR failed: {e}" + Style.RESET_ALL)
        return ""

def is_autocad_drawing_with_ai_fallback(pdf_path, text, silent=False):
    """Use AI to determine if PDF contains an AutoCAD drawing."""
    if not text.strip(): 
        return False
    
    prompt = f"""Is this text from a technical AutoCAD/CAD drawing?

Text: {text[:3000]}

Answer ONLY 'Yes' or 'No'."""

    if grok_client:
        try:
            if not silent: 
                print(Fore.BLUE + "→ Validating with Grok..." + Style.RESET_ALL, end=' ')
            resp = grok_client.chat(
                [{"role": "user", "content": prompt}], 
                model=GROK_MODEL
            )
            if resp and "choices" in resp:
                result = resp["choices"][0]["message"]["content"].strip().lower()
                if not silent: 
                    print(Fore.GREEN + ("✓ Yes" if "yes" in result else "✗ No") + Style.RESET_ALL)
                return "yes" in result
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"Grok error: {e}" + Style.RESET_ALL)
    
    if openai_client:
        try:
            if not silent: 
                print(Fore.BLUE + "→ Validating with OpenAI..." + Style.RESET_ALL, end=' ')
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0, 
                max_tokens=10
            )
            result = resp.choices[0].message.content.strip().lower()
            if not silent: 
                print(Fore.GREEN + ("✓ Yes" if "yes" in result else "✗ No") + Style.RESET_ALL)
            return "yes" in result
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"OpenAI error: {e}" + Style.RESET_ALL)
    
    return False

def extract_specs_with_ai(text, silent=False):
    """Extract technical specifications from text using AI."""
    if not text.strip(): 
        return {}
    
    prompt = f"""Extract technical specifications from this AutoCAD drawing text into a JSON object.
Include fields like: title, drawing_number, scale, dimensions, materials, notes, revisions, etc.

Text: {text[:4000]}

Return ONLY valid JSON, no markdown formatting."""

    if grok_client:
        try:
            if not silent: 
                print(Fore.BLUE + "→ Extracting specs with Grok..." + Style.RESET_ALL, end=' ')
            resp = grok_client.chat(
                [{"role": "user", "content": prompt}], 
                model=GROK_MODEL
            )
            if resp and "choices" in resp:
                result = resp["choices"][0]["message"]["content"].strip()
                # Remove markdown code blocks
                if result.startswith("```"):
                    result = '\n'.join([line for line in result.split('\n') 
                                      if not line.strip().startswith("```")])
                specs = clean_specs(json.loads(result))
                if not silent: 
                    print(Fore.GREEN + f"✓ {len(specs)} fields" + Style.RESET_ALL)
                return specs
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"Grok parse error: {e}" + Style.RESET_ALL)
    
    if openai_client:
        try:
            if not silent: 
                print(Fore.BLUE + "→ Extracting specs with OpenAI..." + Style.RESET_ALL, end=' ')
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE, 
                max_tokens=DEFAULT_MAX_TOKENS
            )
            result = resp.choices[0].message.content.strip()
            # Remove markdown code blocks
            if result.startswith("```"):
                result = '\n'.join([line for line in result.split('\n') 
                                  if not line.strip().startswith("```")])
            specs = clean_specs(json.loads(result))
            if not silent: 
                print(Fore.GREEN + f"✓ {len(specs)} fields" + Style.RESET_ALL)
            return specs
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"OpenAI parse error: {e}" + Style.RESET_ALL)
    
    return {}

def generate_description(specs, text, pdf_path=None, silent=False):
    """Generate natural language description using AI."""
    prompt = f"""Create a brief technical description (2-3 sentences) of this AutoCAD drawing.

Specifications: {json.dumps(specs)}
Text sample: {text[:500]}

Be concise and technical."""

    if grok_client:
        try:
            if not silent: 
                print(Fore.BLUE + "→ Generating description with Grok..." + Style.RESET_ALL)
            resp = grok_client.chat(
                [{"role": "user", "content": prompt}], 
                model=GROK_MODEL
            )
            if resp and "choices" in resp:
                return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"Grok error: {e}" + Style.RESET_ALL)
    
    if openai_client:
        try:
            if not silent: 
                print(Fore.BLUE + "→ Generating description with OpenAI..." + Style.RESET_ALL)
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE, 
                max_tokens=200
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"OpenAI error: {e}" + Style.RESET_ALL)
    
    # Fallback description
    return f"AutoCAD drawing: {os.path.basename(pdf_path) if pdf_path else 'Unknown'}"

def process_pdf(pdf_path, silent=False):
    """Main PDF processing pipeline."""
    if not os.path.exists(pdf_path):
        if not silent: 
            print(Fore.RED + f"✗ File not found: {pdf_path}" + Style.RESET_ALL)
        return False
    
    if file_exists_in_database(pdf_path):
        if not silent: 
            print(Fore.YELLOW + "⚠ Already in database, skipping" + Style.RESET_ALL)
        return True
    
    # Extract text
    text = extract_text(pdf_path, silent=silent)
    if not text.strip() and OCR_AVAILABLE:
        if not silent:
            print(Fore.CYAN + "→ Attempting OCR..." + Style.RESET_ALL)
        text = ocr_full_document(pdf_path, silent=silent)
    
    if not text.strip():
        if not silent: 
            print(Fore.RED + "✗ No text extracted" + Style.RESET_ALL)
        return False
    
    # Validate it's an AutoCAD drawing
    if not is_autocad_drawing_with_ai_fallback(pdf_path, text, silent=silent):
        if not silent: 
            print(Fore.YELLOW + "⚠ Not an AutoCAD drawing" + Style.RESET_ALL)
        return False
    
    # Extract specifications
    specs = extract_specs_with_ai(text, silent=silent)
    
    # Generate description
    description = generate_description(specs, text, pdf_path, silent=silent)
    
    # Add to database
    success = add_to_database(pdf_path, description, specs, silent=silent)
    if success and not silent: 
        print(Fore.GREEN + f"✓ {os.path.basename(pdf_path)} added to database" + Style.RESET_ALL)
    
    return success

def find_pdf(list_all=False, root="."):
    """Find PDF files that contain AutoCAD drawings."""
    all_pdfs = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".pdf"):
                full_path = os.path.join(dirpath, f)
                if not file_exists_in_database(full_path):
                    all_pdfs.append(full_path)
    
    total = len(all_pdfs)
    print(Fore.CYAN + f"\n→ Scanning {total} PDF files..." + Style.RESET_ALL)
    
    autocad_pdfs = []
    for idx, pdf_path in enumerate(all_pdfs, 1):
        text = extract_text(pdf_path, silent=True)
        if not text.strip() and OCR_AVAILABLE:
            text = ocr_full_document(pdf_path, silent=True)
        if text.strip() and is_autocad_drawing_with_ai_fallback(pdf_path, text, silent=True):
            autocad_pdfs.append(pdf_path)
    
    print(Fore.GREEN + f"✓ Found {len(autocad_pdfs)} AutoCAD PDFs" + Style.RESET_ALL)
    
    if list_all:
        for i, pdf in enumerate(autocad_pdfs, 1):
            print(f"{i}) {os.path.basename(pdf)}")
    
    return autocad_pdfs

def answer_question(question, text="", specs=None, description="", silent=False):
    """
    Answer questions about a drawing using AI.
    
    Args:
        question: Question to ask
        text: Extracted text from drawing
        specs: Specifications dict
        description: Generated description
        silent: Suppress output
        
    Returns:
        Answer string or "Unknown"
    """
    if not question or not isinstance(question, str):
        return "Invalid question."

    # Ensure text is always a string
    pdf_text = text if isinstance(text, str) else ""
    if not pdf_text.strip():
        pdf_text = (description or "") + "\n" + json.dumps(specs or {}, indent=2)

    # Ensure specs is always a dict
    if not isinstance(specs, dict):
        try:
            specs = json.loads(specs) if specs else {}
        except Exception:
            specs = {}

    # Ensure description is a string
    if not isinstance(description, str):
        description = str(description)

    # Build prompt
    prompt = f"""You are an expert analyzing technical AutoCAD drawings.
Answer the following question based ONLY on the provided content.

Drawing Content (first 3000 chars):
{pdf_text[:3000]}

Specifications:
{json.dumps(specs, indent=2)}

Description:
{description}

Question:
{question}

If the answer is not present in the content, reply ONLY with "Unknown".
Be specific and reference the document details."""

    try:
        if grok_client:
            resp = grok_client.chat(
                [{"role": "user", "content": prompt}], 
                model=GROK_MODEL
            )
            return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        if not silent:
            print(Fore.RED + f"Grok failed: {e}" + Style.RESET_ALL)

    try:
        if openai_client:
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=400
            )
            return resp.choices[0].message.content.strip()
    except Exception as e:
        if not silent:
            print(Fore.RED + f"OpenAI failed: {e}" + Style.RESET_ALL)

    return "Unknown"