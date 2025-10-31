import os
import re
import time
import json
import base64
import numpy as np
from io import BytesIO

import pdfplumber
import pytesseract
import platform
import shutil
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter

import cv2  
from colorama import init, Fore, Style

from utils import client, grok_client
# --------------------------------------------------------------
#  AUTO-DETECT TESSERACT & POPPLER (PORTABLE)
# --------------------------------------------------------------
def _find_tesseract():
    exe = "tesseract.exe" if platform.system() == "Windows" else "tesseract"
    path = shutil.which(exe)
    if path:
        return path
    local = os.path.join(os.path.dirname(__file__), "tesseract", exe)
    if os.path.exists(local):
        return local
    raise FileNotFoundError("Tesseract not found. Place tesseract.exe in /tesseract/")

def _find_poppler():
    local = os.path.join(os.path.dirname(__file__), "poppler", "bin")
    if os.path.exists(local):
        return local
    raise FileNotFoundError("Poppler not found. Place bin/ in /poppler/")

pytesseract.pytesseract.tesseract_cmd = _find_tesseract()
POPPLER_PATH = _find_poppler()

# --------------------------------------------------------------
#  1. TYPEWRITER EFFECT
# --------------------------------------------------------------
def print_typed(text, delay=0.01):
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()

# --------------------------------------------------------------
#  2. DETECTION + DEBUG
# --------------------------------------------------------------
def debug_why(path):
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return "Skip (no pages)"
            page = pdf.pages[0]
            lines = len(page.objects.get("line", []))
            rects = len(page.objects.get("rect", []))
            total_vectors = lines + rects
            if total_vectors >= 1800:
                return f"AutoCAD! (vector: {total_vectors} lines/rects)"
        return "Skip (raster, low vectors)"
    except Exception as e:
        return f"Skip (error: {str(e)[:30]})"

def is_autocad_drawing(path):
    try:
        with pdfplumber.open(path) as pdf:
            if pdf.pages:
                page = pdf.pages[0]
                lines = len(page.objects.get("line", []))
                rects = len(page.objects.get("rect", []))
                if lines + rects >= 1800:
                    return True
        return False
    except Exception:
        return False

# --------------------------------------------------------------
#  FULL-PAGE OCR – works on any layout, no title-block assumption
# --------------------------------------------------------------
def _preprocess_full_page(pil_image):
    img = pil_image.convert('L')
    img = ImageEnhance.Contrast(img).enhance(5.0)
    img_np = np.array(img)
    binary = cv2.adaptiveThreshold(
        img_np, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 12
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    h, w = binary.shape
    binary = cv2.resize(binary, (w*2, h*2), interpolation=cv2.INTER_LANCZOS4)

    processed = Image.fromarray(binary)
    return processed

def ocr_full_document(pdf_path, max_pages=5):
    pages = convert_from_path(
        pdf_path,
        first_page=1,
        last_page=max_pages,
        dpi=500,
        poppler_path=POPPLER_PATH
    )

    best_text = ""
    best_score = -1

    psm_configs = [
        '--psm 6',
        '--psm 11',
        '--psm 3',
        '--psm 4',
    ]

    whitelist = ('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                 'abcdefghijklmnopqrstuvwxyz./-#:"()[] ')

    for idx, page in enumerate(pages, 1):
        processed = _preprocess_full_page(page)

        for cfg in psm_configs:
            try:
                txt = pytesseract.image_to_string(
                    processed,
                    config=f'{cfg} -c tessedit_char_whitelist={whitelist}'
                )
                score = (
                    len(re.findall(r'\bBORE\b', txt, re.I)) * 5 +
                    len(re.findall(r'\bROD\b', txt, re.I)) * 5 +
                    len(re.findall(r'\bSTROKE\b', txt, re.I)) * 5 +
                    len(re.findall(r'\bIP\d+\b', txt)) * 3 +
                    len(re.findall(r'\d+\.?\d*', txt))
                )
                if score > best_score:
                    best_score, best_text = score, txt
            except Exception:
                continue

        if best_score > 20:
            break

    return best_text

# --------------------------------------------------------------
#  4. TEXT EXTRACTION (vector first → OCR fallback)
# --------------------------------------------------------------
def extract_text(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_parts = []
            for page in pdf.pages[:3]:
                page_text = page.extract_text(
                    x_tolerance=3,
                    y_tolerance=3,
                    use_text_flow=True,
                    keep_blank_chars=True
                )
                if page_text:
                    text_parts.append(page_text)
            full_text = "\n".join(text_parts)
            if full_text.strip() and len(full_text) > 50:
                return full_text
    except Exception as e:
        print(Fore.YELLOW + f"[Vector extraction failed: {e}]" + Style.RESET_ALL)

    try:
        ocr_text = ocr_full_document(pdf_path, max_pages=5)
        return ocr_text
    except Exception as e:
        print(Fore.RED + f"[OCR failed: {e}]" + Style.RESET_ALL)
        return ""

# --------------------------------------------------------------
#  5. SPECS EXTRACTION USING GROK (JSON OUTPUT)
# --------------------------------------------------------------
def extract_specs_with_grok(text):
    prompt = f"""
You are a hydraulic cylinder expert. Extract ONLY these specs from the drawing text below.
Return ONLY valid JSON (no extra text):

{{
    "Bore": "2.00 in",
    "Rod": "1.375 in",
    "Stroke": "4.00 in",
    "Part": "IP-12345",
    "Rev": "B",
    "Date": "10/15/2024",
    "Mounting": "11 holes",
    "Port": "#10 O-ring",
    "Pressure": "3000 PSI",
    "Spring Probe": "Yes or No",
    "Transducer": "Yes or No",
    "Title": "H-ME5-2.00 X 1.375 X 4.00"
}}
If a value is missing, use "?".

Drawing text:
{text[:4000]}
"""

    try:
        resp = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300
        )
        raw = resp.choices[0].message.content.strip()

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]

        specs = json.loads(raw)

        for k in ["Spring Probe", "Transducer"]:
            if specs.get(k, "?").lower() in ["yes", "y", "true"]:
                specs[k] = "Yes"
            elif specs.get(k, "?").lower() in ["no", "n", "false", ""]:
                specs[k] = "??"

        return specs

    except Exception as e:
        print(Fore.RED + f"[Grok spec extraction failed: {e}]" + Style.RESET_ALL)
        return {k: "??" for k in [
            "Bore", "Rod", "Stroke", "Part", "Rev", "Date",
            "Mounting", "Port", "Pressure", "Spring Probe", "Transducer", "Title"
        ]}

# --------------------------------------------------------------
#  6. CLEAN DESCRIPTION (Grok)
# --------------------------------------------------------------
def generate_description(text, specs):
    prompt = f"""
    Describe this hydraulic cylinder in plain English (max 200 words). Use ONLY these specs:

    Bore: {specs.get('Bore', '??')}
    Rod: {specs.get('Rod', '??')}
    Stroke: {specs.get('Stroke', '??')}
    Part: {specs.get('Part', '??')}
    Mounting: {specs.get('Mounting', '??')}
    Ports: {specs.get('Port', '??')}
    Pressure: {specs.get('Pressure', '??')}

    Drawing text (first 2000 chars):
    {text[:2000]}

    DO NOT guess missing values. Be friendly and accurate.
    """
    try:
        resp = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Grok error: {e}]\nA hydraulic cylinder."

# --------------------------------------------------------------
#  7. SEAMLESS Q&A (auto-returns to main menu)
# --------------------------------------------------------------
def ask_follow_up(description, specs, on_exit_callback=None):
    print(Fore.CYAN + "\nAsk questions about this drawing (or press Enter to continue):" + Style.RESET_ALL)
    while True:
        q = input(Fore.YELLOW + "→ " + Style.RESET_ALL).strip()
        if not q:
            print(Fore.GREEN + "Returning to main menu..." + Style.RESET_ALL)
            if on_exit_callback:
                on_exit_callback(skip_plain=True)
            break
            
        if q.lower() in {"exit", "quit", "bye", "goodbye"}:
            print(Fore.GREEN + "Goodbye! Have a great day!" + Style.RESET_ALL)
            if on_exit_callback:
                on_exit_callback(skip_plain=True)
            return "EXIT_PROGRAM"
            
        if q.lower() in {"thank you", "thanks", "ty", "thankyou"}:
            print(Fore.GREEN + "You're very welcome! Press Enter to continue..." + Style.RESET_ALL)
            continue

        prompt = f"""
Drawing:
{description}

Specs: {specs}

Answer in 1-3 short sentences:
{q}
"""
        try:
            ans = grok_client.chat.completions.create(
                model="grok-3",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            ).choices[0].message.content.strip()
            print(Fore.GREEN + f"→ {ans}" + Style.RESET_ALL)
        except Exception:
            print(Fore.RED + "Sorry, I couldn't answer that." + Style.RESET_ALL)

# --------------------------------------------------------------
#  8. FIND PDFs
# --------------------------------------------------------------
def find_pdf(filename=None, list_all=False):
    root = os.getcwd()
    all_pdfs = [
        os.path.join(dp, f)
        for dp, _, fs in os.walk(root)
        for f in fs if f.lower().endswith(".pdf")
    ]

    if list_all:
        print(Fore.CYAN + f"Scanning {len(all_pdfs)} PDFs..." + Style.RESET_ALL)
        matches = []
        for i, p in enumerate(all_pdfs, 1):
            name = os.path.basename(p)
            print(f"\r{i}/{len(all_pdfs)} – {name}", end="", flush=True)
            reason = debug_why(p)
            if is_autocad_drawing(p):
                matches.append(p)
                print(f"  → {Fore.GREEN}{reason}{Style.RESET_ALL}")
            else:
                print(f"  → {Fore.YELLOW}{reason}{Style.RESET_ALL}")
        print(f"\n{Fore.GREEN}Done – {len(matches)} AutoCAD drawings found.{Style.RESET_ALL}")
        return matches

    else:
        name_lower = filename.lower()
        for p in all_pdfs:
            if os.path.basename(p).lower() == name_lower:
                if is_autocad_drawing(p):
                    return p
                else:
                    print(Fore.RED + f"'{filename}' is not an AutoCAD drawing." + Style.RESET_ALL)
                    return None
        print(Fore.RED + f"File not found: {filename}" + Style.RESET_ALL)
        return None

# --------------------------------------------------------------
#  9. PROCESS PDF
# --------------------------------------------------------------
def process_pdf(pdf_path, skip_plain_english=False):
    name = os.path.basename(pdf_path)
    print(Fore.CYAN + f"\nProcessing: {name}" + Style.RESET_ALL)

    text = extract_text(pdf_path)
    specs = extract_specs_with_grok(text)
    description = generate_description(text, specs)

    print(Fore.MAGENTA + "\nSPECIFICATIONS" + Style.RESET_ALL)
    print("─" * 50)
    found_specs = False
    for k, v in specs.items():
        if v not in ["??", "?", "", "No"]:
            print(f"{k:<12}: {v}")
            found_specs = True
    if not found_specs:
        print("No specifications found in drawing.")
    else:
        print(f"({len([v for v in specs.values() if v not in ['??', '?', '', 'No']])} specs extracted)")
    print("─" * 50)

    print(Fore.CYAN + "\nDESCRIPTION" + Style.RESET_ALL)
    print(description)

    def on_exit(skip_plain):
        nonlocal skip_plain_english
        skip_plain_english = skip_plain

    result = ask_follow_up(description, specs, on_exit_callback=on_exit)
    if result == "EXIT_PROGRAM":
        return None

    if not skip_plain_english:
        print("\n" + "="*70)
        print("Plain English Explanation:")
        print(description)
        print("="*70 + "\n")

    return description

# --------------------------------------------------------------
#  10. Q&A ABOUT LAST DESCRIPTION
# --------------------------------------------------------------
def ask_question_about_description(description, question):
    if question.lower() in ["thank you", "thanks", "ty"]:
        return "You're very welcome!"
    prompt = f"""
Drawing:
{description}

Answer in 1-3 short sentences:
{question}
"""
    try:
        ans = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        ).choices[0].message.content.strip()
        return ans
    except Exception:
        return "Sorry, I couldn't answer."

# --------------------------------------------------------------
#  11. EXPORTED API
# --------------------------------------------------------------
__all__ = [
    'find_pdf',
    'process_pdf',
    'print_typed',
    'ask_question_about_description',
    'extract_text',
    'extract_specs_with_grok',
]