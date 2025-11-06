import os
import json
from colorama import init, Fore, Style
from PDF_Analyzer import find_pdf, is_autocad_pdf, answer_question, extract_text, ocr_full_document, extract_specs_from_text, generate_description
from semanticMemory import add_to_database, list_database_files, remove_from_database, search_similar_files
from utils import load_cache, save_cache, get_file_hash, CACHE_FILE, is_valid_specs

init(autoreset=True)
LAST_DIR_FILE = "last_dir.txt"

def load_last_directory():
    try:
        with open(LAST_DIR_FILE, "r") as f:
            return f.read().strip()
    except:
        return None

def save_last_directory(directory):
    try:
        with open(LAST_DIR_FILE, "w") as f:
            f.write(directory)
    except:
        pass

def prompt_directory(default_dir):
    dir_input = input(f"Enter directory (press Enter for '{default_dir}'): ").strip()
    return dir_input or default_dir

# --- Process a single PDF file ---
def process_pdf_file(file_path, silent=False, show_progress=False, current=0, total=0):
    """Process a single PDF file and add to database."""
    if not os.path.exists(file_path):
        if not silent:
            print(Fore.RED + f"File does not exist: {file_path}" + Style.RESET_ALL)
        return False

    if show_progress:
        print(Fore.BLUE + f"\r[{current}/{total}] Processing... " + Style.RESET_ALL, end='', flush=True)

    # Extract text and specs
    text = extract_text(file_path, silent=True)
    if text is None:
        text = ""
    
    if not text.strip():
        ocr_text = ocr_full_document(file_path, silent=True)
        if ocr_text is None:
            text = ""
        else:
            text = ocr_text
    
    specs = extract_specs_from_text(text)
    
    if not is_valid_specs(specs):
        # Always show skip messages during batch processing for debugging
        if show_progress:
            print(Fore.YELLOW + f"\n  → Skipped: No valid specs found in {os.path.basename(file_path)}" + Style.RESET_ALL)
        elif not silent:
            print(Fore.YELLOW + f"Skipped: No valid specs found in {os.path.basename(file_path)}" + Style.RESET_ALL)
        return False
    
    # Generate description
    desc = generate_description(text, specs)
    if not desc:
        desc = "AutoCAD drawing (no description generated)"

    # Add to database
    if add_to_database(file_path, desc, specs, silent=True):
        if not silent and not show_progress:
            print(Fore.GREEN + f"✔ Added to database: {os.path.basename(file_path)}" + Style.RESET_ALL)
        return True
    else:
        if not silent and not show_progress:
            print(Fore.RED + f"Failed to save {os.path.basename(file_path)} to database." + Style.RESET_ALL)
        return False

# --- Interactive Q&A ---
def interactive_qa():
    rows = list_database_files()
    if not rows:
        print(Fore.YELLOW + "No files in database to query." + Style.RESET_ALL)
        return

    print(Fore.CYAN + "\nAvailable files for Q&A:" + Style.RESET_ALL)
    for i, (fname, _, _) in enumerate(rows, 1):
        print(f"{i}) {fname}")

    choice = input("\nSelect file number to query (or press Enter to return): ").strip()
    if not choice:
        return

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(rows)):
            print(Fore.RED + "Invalid selection." + Style.RESET_ALL)
            return
        
        fname, desc, specs_json = rows[idx]
        specs = json.loads(specs_json)
        cache = load_cache()
        last_dir = load_last_directory() or "C:\\"
        file_hash = get_file_hash(os.path.join(last_dir, fname))
        text = cache.get(file_hash, {}).get("text", "")

        print(Fore.CYAN + f"\nSelected file: {fname}" + Style.RESET_ALL)
        while True:
            question = input("\nAsk a question (or 'exit' to return): ").strip()
            if question.lower() == "exit":
                break
            answer = answer_question(question, text, specs, desc)
            print(Fore.GREEN + "Answer:" + Style.RESET_ALL)
            print(answer)
    except ValueError:
        print(Fore.RED + "Invalid input." + Style.RESET_ALL)

# --- Main Menu ---
def main():
    last_dir = load_last_directory() or "C:\\"

    while True:
        print("\nAutoCAD PDF Finder & Explainer")
        print("=" * 60)
        print(" 1) List/scan PDFs in directory")
        print(" 2) View database (filenames only)")
        print(" 3) Search similar files")
        print(" 4) Clear cache")
        print(" 5) Remove file from database")
        print(" 6) Process a single PDF")
        print(" 7) Add all AutoCAD PDFs in directory")
        print(" 8) Ask questions about a drawing")
        print(" 9) Exit")
        print("=" * 60)

        choice = input("Select option (1-9): ").strip()

        if choice == "1":
            directory = prompt_directory(last_dir)
            if not os.path.exists(directory):
                print(Fore.RED + f"Directory not found: {directory}" + Style.RESET_ALL)
                continue
            save_last_directory(directory)
            pdf_list = find_pdf(list_all=True, root=directory)

        elif choice == "2":
            files = list_database_files()
            if not files:
                print(Fore.YELLOW + "No files in database." + Style.RESET_ALL)
            else:
                print(Fore.CYAN + "\nFiles in database:" + Style.RESET_ALL)
                for i, (fname, _, _) in enumerate(files, 1):
                    print(f"{i}) {fname}")

        elif choice == "3":
            query = input("Enter search query: ").strip()
            if query:
                search_similar_files(query)
            else:
                print(Fore.YELLOW + "No query entered." + Style.RESET_ALL)

        elif choice == "4":
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
                print(Fore.GREEN + "Cache cleared." + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + "No cache file found." + Style.RESET_ALL)

        elif choice == "5":
            files = list_database_files()
            if not files:
                print(Fore.YELLOW + "Database empty." + Style.RESET_ALL)
                continue
            filename = input("Enter filename to remove: ").strip()
            if filename:
                remove_from_database(filename)

        elif choice == "6":
            directory = prompt_directory(last_dir)
            if not os.path.exists(directory):
                print(Fore.RED + "Invalid directory." + Style.RESET_ALL)
                continue
            fname = input("Enter PDF filename (full or partial): ").strip()
            pdfs = find_pdf(list_all=True, root=directory)
            match = next((f for f in pdfs if fname.lower() in os.path.basename(f).lower()), None)
            if match:
                process_pdf_file(match, silent=False)
            else:
                print(Fore.RED + "File not found or not AutoCAD." + Style.RESET_ALL)

        elif choice == "7":
            directory = prompt_directory(last_dir)
            if not os.path.exists(directory):
                print(Fore.RED + "Invalid directory." + Style.RESET_ALL)
                continue
            save_last_directory(directory)
            pdf_list = find_pdf(list_all=True, root=directory)
            
            if not pdf_list:
                print(Fore.YELLOW + "No verified AutoCAD PDFs found." + Style.RESET_ALL)
                continue
            
            confirm = input(f"Add all {len(pdf_list)} PDFs to database? (y/N): ").strip().lower()
            if confirm == "y":
                print(Fore.CYAN + f"\nProcessing {len(pdf_list)} files..." + Style.RESET_ALL)
                added = 0
                skipped = 0
                
                for idx, f in enumerate(pdf_list, 1):
                    if process_pdf_file(f, silent=True, show_progress=True, current=idx, total=len(pdf_list)):
                        added += 1
                    else:
                        skipped += 1
                
                # Clear progress line and show final result
                print(Fore.GREEN + f"\r[{len(pdf_list)}/{len(pdf_list)}] Complete!" + Style.RESET_ALL + " " * 50)
                print(Fore.CYAN + f"Summary: {added} added, {skipped} skipped" + Style.RESET_ALL)
                
                if skipped > 0:
                    print(Fore.YELLOW + f"Tip: Run option 6 on individual files to see why they were skipped." + Style.RESET_ALL)
        
        elif choice == "8":
            interactive_qa()
        
        elif choice == "9":
            print("Goodbye!")
            break
        
        else:
            print(Fore.RED + "Invalid selection (1-9)." + Style.RESET_ALL)

if __name__ == "__main__":
    main()