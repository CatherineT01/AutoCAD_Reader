# drawingSystem.py
#*************************************************************************************************************
#   Updated drawingSystem.py with DWG support and config integration
#   Provides an interactive command-line interface for managing and analyzing AutoCAD PDF and DWG files
#*************************************************************************************************************
import os
import json
import io
from contextlib import redirect_stdout, redirect_stderr
from colorama import init, Fore, Style

# Import config first
from config import DEFAULT_SCAN_DIR, validate_config, get_config_summary

# Existing imports
from PDF_Analyzer import (
    find_pdf, answer_question, extract_text, ocr_full_document,
    extract_specs_with_ai, generate_description, process_pdf
)
from semanticMemory import (
    add_to_database, list_database_files, remove_from_database,
    search_similar_files, file_exists_in_database
)
from utils import load_cache, save_cache, get_file_hash, CACHE_FILE, is_valid_specs

# NEW: DWG imports
from DWG_Processor import (
    process_dwg_file, 
    batch_process_dwg_folder,
    export_dwg_to_csv,
    DWGProcessor,
    find_dwg_files
)

init(autoreset=True)

LAST_DIR_FILE = "last_dir.txt"
PDF_CACHE_FILE = "pdf_scan_cache.json"

def load_last_directory():
    try:
        with open(LAST_DIR_FILE, "r") as f:
            content = f.read().strip()
            if os.path.exists(content) and os.path.isdir(content):
                return content
            else:
                if os.path.exists(LAST_DIR_FILE):
                    os.remove(LAST_DIR_FILE)
                return None
    except:
        return None

def save_last_directory(directory):
    try:
        if os.path.exists(directory) and os.path.isdir(directory):
            with open(LAST_DIR_FILE, "w") as f:
                f.write(directory)
    except:
        pass

def load_pdf_cache():
    try:
        with open(PDF_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_pdf_cache(cache):
    try:
        with open(PDF_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except:
        pass

def get_directory_hash(directory):
    try:
        pdf_files = []
        for dirpath, _, files in os.walk(directory):
            for f in files:
                if f.lower().endswith(".pdf"):
                    full_path = os.path.join(dirpath, f)
                    pdf_files.append((full_path, os.path.getmtime(full_path)))
        pdf_files.sort()
        cache_key = f"{directory}::{len(pdf_files)}"
        return cache_key, [p[0] for p in pdf_files]
    except Exception as e:
        print(Fore.RED + f"Error scanning directory: {e}" + Style.RESET_ALL)
        return None, []

def prompt_directory(default_dir):
    dir_input = input(f"Enter directory (press Enter for '{default_dir}'): ").strip()
    return dir_input or default_dir

def reprocess_database_files():
    files = list_database_files()
    if not files:
        print(Fore.YELLOW + "No files in database to reprocess." + Style.RESET_ALL)
        return

    print(Fore.CYAN + f"\nFound {len(files)} files in database" + Style.RESET_ALL)
    print(Fore.CYAN + "This will re-analyze them with Grok->OpenAI pipeline" + Style.RESET_ALL)
    confirm = input(f"\nReprocess all {len(files)} files? (y/N): ").strip().lower()
    if confirm != "y":
        print(Fore.YELLOW + "Reprocessing cancelled." + Style.RESET_ALL)
        return

    print(Fore.CYAN + f"\n{'='*60}" + Style.RESET_ALL)
    print(Fore.CYAN + f"REPROCESSING {len(files)} FILES" + Style.RESET_ALL)
    print(Fore.CYAN + f"{'='*60}\n" + Style.RESET_ALL)

    success_count = 0
    failed_count = 0

    for idx, (filepath, old_desc, old_specs) in enumerate(files, 1):
        filename = os.path.basename(filepath)
        print(Fore.BLUE + f"[{idx}/{len(files)}] Reprocessing: {filename}" + Style.RESET_ALL)
        if not os.path.exists(filepath):
            print(Fore.RED + f"File not found: {filename}" + Style.RESET_ALL)
            failed_count += 1
            continue

        try:
            # Handle both PDF and DWG
            if filepath.lower().endswith('.dwg'):
                result = process_dwg_file(filepath, silent=True)
            else:
                result = process_pdf(filepath, silent=True)
                
            if result:
                success_count += 1
                print(Fore.GREEN + f"✓ Updated: {filename}" + Style.RESET_ALL)
            else:
                failed_count += 1
                print(Fore.YELLOW + f"⚠ Issues with: {filename}" + Style.RESET_ALL)
        except Exception as e:
            failed_count += 1
            print(Fore.RED + f"✗ Failed: {filename} - {e}" + Style.RESET_ALL)

    print(Fore.CYAN + f"\n{'='*60}" + Style.RESET_ALL)
    print(Fore.GREEN + "REPROCESSING COMPLETE" + Style.RESET_ALL)
    print(Fore.CYAN + f"{'='*60}" + Style.RESET_ALL)
    print(Fore.WHITE + f"Success: {success_count} | Failed: {failed_count}" + Style.RESET_ALL)

def process_file(file_path, silent=False, show_progress=False, current=0, total=0):
    """Unified file processing for both PDF and DWG"""
    if not os.path.exists(file_path):
        if not silent:
            print(Fore.RED + f"File not found: {os.path.basename(file_path)}" + Style.RESET_ALL)
        return False

    filename = os.path.basename(file_path)
    if show_progress:
        print(Fore.BLUE + f"\r[{current}/{total}] Processing {filename[:40]}..." + Style.RESET_ALL, end='', flush=True)
    
    # Route to appropriate processor
    if file_path.lower().endswith('.dwg'):
        return process_dwg_file(file_path, silent=silent)
    else:
        return process_pdf(file_path, silent=silent)

def remove_duplicate_files():
    files = list_database_files()
    seen = set()
    removed = 0

    for filepath, *_ in files:
        fname = os.path.basename(filepath)
        if fname in seen:
            with io.StringIO() as buf, redirect_stdout(buf), redirect_stderr(buf):
                remove_from_database(filepath)
            removed += 1
        else:
            seen.add(fname)

    updated_files = list_database_files()
    db_count = len(updated_files)

    print(Fore.GREEN + f"{removed} duplicate(s) deleted" + Style.RESET_ALL)
    print(Fore.CYAN + f"AutoCAD PDF/DWG Analyzer [{db_count} files in database]" + Style.RESET_ALL)

def interactive_qa():
    """Enhanced Q&A supporting both PDF and DWG files"""
    rows = list_database_files()
    if not rows:
        print(Fore.YELLOW + "No files in database." + Style.RESET_ALL)
        return

    print(Fore.CYAN + "\nFiles in database:" + Style.RESET_ALL)
    for i, (fname, _, _) in enumerate(rows, 1):
        file_type = "DWG" if fname.lower().endswith('.dwg') else "PDF"
        print(f"{i}) [{file_type}] {os.path.basename(fname)}")

    choice = input("\nSelect file number (or Enter to return): ").strip()
    if not choice:
        return

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(rows)):
            print(Fore.RED + "Invalid selection." + Style.RESET_ALL)
            return

        fname, desc, specs_json = rows[idx]
        specs = json.loads(specs_json) if specs_json else {}

        # Get text content based on file type
        if fname.lower().endswith('.dwg'):
            processor = DWGProcessor()
            dwg_info = processor.get_from_database(fname)
            text = dwg_info.get('csv_data', '') if dwg_info else ''
        else:
            cache = load_cache()
            file_hash = get_file_hash(fname)
            text = cache.get(file_hash, {}).get("text", "")
            if not text:
                text = extract_text(fname, silent=True) or ""

        print(Fore.CYAN + f"\nSelected: {os.path.basename(fname)}" + Style.RESET_ALL)
        print(Fore.CYAN + f"Description: {desc}" + Style.RESET_ALL)

        while True:
            question = input("\nQuestion (or 'exit'): ").strip()
            if question.lower() == "exit":
                break
            answer = answer_question(question, text, specs, desc)
            print(Fore.GREEN + "\nAnswer:" + Style.RESET_ALL)
            print(answer)
    except ValueError:
        print(Fore.RED + "Invalid input." + Style.RESET_ALL)

def view_dwg_details():
    """View detailed information about DWG files in database"""
    processor = DWGProcessor()
    files = list_database_files()
    dwg_files = [(f, d, s) for f, d, s in files if f.lower().endswith('.dwg')]
    
    if not dwg_files:
        print(Fore.YELLOW + "No DWG files in database." + Style.RESET_ALL)
        return
    
    print(Fore.CYAN + f"\n{len(dwg_files)} DWG files in database:" + Style.RESET_ALL)
    for i, (fname, _, _) in enumerate(dwg_files, 1):
        print(f"{i}) {os.path.basename(fname)}")
    
    choice_input = input("\nSelect file number (or Enter to return): ").strip()
    if not choice_input:
        return
        
    try:
        idx = int(choice_input) - 1
        if 0 <= idx < len(dwg_files):
            dwg_info = processor.get_from_database(dwg_files[idx][0])
            if dwg_info:
                print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}File: {dwg_info['filename']}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                print(f"Path: {dwg_info['filepath']}")
                print(f"Description: {dwg_info['description']}")
                print(f"\nStatistics:")
                print(f"  Entities: {dwg_info['entity_count']}")
                print(f"  Layers: {dwg_info['layer_count']}")
                print(f"  Blocks: {dwg_info['block_count']}")
                print(f"\nCSV Preview (first 1000 chars):")
                print(f"{Fore.WHITE}{dwg_info['csv_data']}{Style.RESET_ALL}")
                
                # Ask if user wants to export full CSV
                export = input("\nExport full CSV? (y/N): ").strip().lower()
                if export == 'y':
                    csv_name = os.path.splitext(dwg_info['filename'])[0] + "_export.csv"
                    export_dwg_to_csv(dwg_info['filepath'], csv_name)
        else:
            print(Fore.RED + "Invalid selection." + Style.RESET_ALL)
    except ValueError:
        print(Fore.RED + "Invalid input." + Style.RESET_ALL)

def scan_mixed_directory():
    """Scan directory for both PDFs and DWGs"""
    last_dir = load_last_directory() or DEFAULT_SCAN_DIR
    directory = prompt_directory(last_dir)
    
    if not os.path.exists(directory):
        print(Fore.RED + "Directory not found." + Style.RESET_ALL)
        return
    
    save_last_directory(directory)
    
    print(Fore.CYAN + "\nScanning directory for AutoCAD files..." + Style.RESET_ALL)
    
    # Scan for PDFs
    pdf_list = find_pdf(list_all=False, root=directory)
    
    # Scan for DWGs
    dwg_list = find_dwg_files(directory)
    
    total = len(pdf_list) + len(dwg_list)
    
    print(Fore.GREEN + f"\nFound {len(pdf_list)} PDFs and {len(dwg_list)} DWGs ({total} total)" + Style.RESET_ALL)
    
    if total == 0:
        print(Fore.YELLOW + "No AutoCAD files found." + Style.RESET_ALL)
        return
    
    # Show breakdown
    print(Fore.CYAN + "\nBreakdown:" + Style.RESET_ALL)
    if pdf_list:
        print(f"  PDF files: {len(pdf_list)}")
        show_pdfs = input("    List PDF files? (y/N): ").strip().lower()
        if show_pdfs == 'y':
            for i, pdf in enumerate(pdf_list[:10], 1):
                print(f"      {i}) {os.path.basename(pdf)}")
            if len(pdf_list) > 10:
                print(f"      ... and {len(pdf_list) - 10} more")
    
    if dwg_list:
        print(f"  DWG files: {len(dwg_list)}")
        show_dwgs = input("    List DWG files? (y/N): ").strip().lower()
        if show_dwgs == 'y':
            for i, dwg in enumerate(dwg_list[:10], 1):
                print(f"      {i}) {os.path.basename(dwg)}")
            if len(dwg_list) > 10:
                print(f"      ... and {len(dwg_list) - 10} more")
    
    # Option to add all
    add_all = input(f"\nAdd all {total} files to database? (y/N): ").strip().lower()
    if add_all == 'y':
        added = 0
        issues = 0
        already_in_db = 0
        
        all_files = pdf_list + dwg_list
        
        for idx, file_path in enumerate(all_files, 1):
            if file_exists_in_database(file_path):
                already_in_db += 1
                print(Fore.YELLOW + f"[{idx}/{total}] Already in DB: {os.path.basename(file_path)}" + Style.RESET_ALL)
                continue
            
            file_type = "DWG" if file_path.lower().endswith('.dwg') else "PDF"
            print(Fore.BLUE + f"[{idx}/{total}] Processing {file_type}: {os.path.basename(file_path)}" + Style.RESET_ALL)
            
            success = process_file(file_path, silent=True)
            if success:
                added += 1
                print(Fore.GREEN + "✓ Success" + Style.RESET_ALL)
            else:
                issues += 1
                print(Fore.YELLOW + "⚠ Issues" + Style.RESET_ALL)
        
        print(Fore.GREEN + f"\n{'='*60}" + Style.RESET_ALL)
        print(Fore.GREEN + "BATCH PROCESSING COMPLETE" + Style.RESET_ALL)
        print(Fore.GREEN + f"{'='*60}" + Style.RESET_ALL)
        print(Fore.WHITE + f"Added: {added} | Issues: {issues} | Already in DB: {already_in_db}" + Style.RESET_ALL)

def display_menu():
    db_files = len(list_database_files())
    
    # Count file types
    files = list_database_files()
    pdf_count = sum(1 for f, _, _ in files if not f.lower().endswith('.dwg'))
    dwg_count = sum(1 for f, _, _ in files if f.lower().endswith('.dwg'))
    
    print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}AutoCAD PDF/DWG Analyzer{Style.RESET_ALL}")
    print(f"{Fore.WHITE}[{db_files} files: {pdf_count} PDFs, {dwg_count} DWGs]{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    
    print(f"\n{Fore.YELLOW}📄 PDF Operations{Style.RESET_ALL}")
    print(" 1) Scan directory for AutoCAD PDFs")
    print(" 2) Add all PDFs to database")
    print(" 3) Process single PDF file")
    
    print(f"\n{Fore.BLUE}📐 DWG Operations{Style.RESET_ALL}")
    print(" 4) Scan directory for DWG files")
    print(" 5) Add all DWGs to database")
    print(" 6) Process single DWG file")
    print(" 7) View DWG details")
    print(" 8) Export DWG to CSV")
    
    print(f"\n{Fore.GREEN}🔍 Database Operations{Style.RESET_ALL}")
    print(" 9) View all database files")
    print("10) Search similar files (semantic)")
    print("11) Remove file from database")
    print("12) Remove duplicate entries")
    print("13) Clear all caches")
    
    print(f"\n{Fore.MAGENTA}🤖 AI Analysis{Style.RESET_ALL}")
    print("14) Ask questions about a drawing")
    print("15) Reprocess all files (re-analyze)")
    
    print(f"\n{Fore.WHITE}⚙️  System{Style.RESET_ALL}")
    print("16) Scan directory (PDFs + DWGs)")
    print("17) View configuration")
    print("18) Exit")
    
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    return input("Select option (1-18): ").strip()

def view_configuration():
    """Display current system configuration"""
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}System Configuration{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    config = get_config_summary()
    for key, value in config.items():
        status = Fore.GREEN + "✓" if value else Fore.RED + "✗"
        print(f"{status} {key:.<40} {value}{Style.RESET_ALL}")
    
    print(f"\n{Fore.YELLOW}Configuration Issues:{Style.RESET_ALL}")
    issues = validate_config()
    if issues:
        for issue in issues:
            print(f"  {Fore.RED}⚠{Style.RESET_ALL} {issue}")
    else:
        print(f"  {Fore.GREEN}✓ No issues found{Style.RESET_ALL}")
    
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

def main():
    last_dir = load_last_directory() or DEFAULT_SCAN_DIR
    pdf_cache = load_pdf_cache()
    
    # Show startup banner
    print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}AutoCAD PDF/DWG Analyzer - v2.0{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")

    while True:
        choice = display_menu()

        if choice == "1":  # Scan PDFs
            try:
                directory = prompt_directory(last_dir)
                if not os.path.exists(directory):
                    print(Fore.RED + "Directory not found." + Style.RESET_ALL)
                    continue

                save_last_directory(directory)
                cache_key, pdf_files = get_directory_hash(directory)

                if cache_key is None:
                    print(Fore.RED + "Failed to scan directory." + Style.RESET_ALL)
                    continue

                force_rescan = input(f"Force full re-scan? (y/N): ").strip().lower() == "y"
                if force_rescan or cache_key not in pdf_cache:
                    print(Fore.CYAN + "\nScanning directory..." + Style.RESET_ALL)
                    autocad_pdfs = find_pdf(list_all=False, root=directory)
                    pdf_cache[cache_key] = autocad_pdfs
                    save_pdf_cache(pdf_cache)
                else:
                    print(Fore.CYAN + f"\nUsing cached scan ({len(pdf_cache[cache_key])} PDFs)" + Style.RESET_ALL)
                    autocad_pdfs = pdf_cache[cache_key]

                print(Fore.CYAN + f"\nFound {len(autocad_pdfs)} AutoCAD PDFs:" + Style.RESET_ALL)
                for i, pdf in enumerate(autocad_pdfs[:20], 1):
                    print(f"{i}) {os.path.basename(pdf)}")
                if len(autocad_pdfs) > 20:
                    print(f"... and {len(autocad_pdfs) - 20} more")
                    
            except Exception as e:
                print(Fore.RED + f"Error during scan: {e}" + Style.RESET_ALL)

        elif choice == "2":  # Add all PDFs
            directory = prompt_directory(last_dir)
            if not os.path.exists(directory):
                print(Fore.RED + "Invalid directory." + Style.RESET_ALL)
                continue

            save_last_directory(directory)
            print(Fore.CYAN + f"\nScanning directory for AutoCAD PDFs..." + Style.RESET_ALL)
            pdf_list = find_pdf(list_all=False, root=directory)
            if not pdf_list:
                print(Fore.YELLOW + "No AutoCAD PDFs found." + Style.RESET_ALL)
                continue

            print(Fore.CYAN + f"Found {len(pdf_list)} AutoCAD PDFs" + Style.RESET_ALL)
            confirm = input(f"Add all to database? (y/N): ").strip().lower()
            if confirm == "y":
                added = 0
                issues = 0
                already_in_db = 0
                for idx, f in enumerate(pdf_list, 1):
                    if file_exists_in_database(f):
                        already_in_db += 1
                        print(Fore.YELLOW + f"[{idx}/{len(pdf_list)}] Already in DB: {os.path.basename(f)}" + Style.RESET_ALL)
                        continue

                    print(Fore.BLUE + f"[{idx}/{len(pdf_list)}] Processing: {os.path.basename(f)}" + Style.RESET_ALL)
                    success = process_pdf(f, silent=True)
                    if success:
                        added += 1
                        print(Fore.GREEN + "✓ Success" + Style.RESET_ALL)
                    else:
                        issues += 1
                        print(Fore.YELLOW + "⚠ Issues" + Style.RESET_ALL)

                print(Fore.GREEN + f"\n{'='*60}" + Style.RESET_ALL)
                print(Fore.GREEN + "BATCH PROCESSING COMPLETE" + Style.RESET_ALL)
                print(Fore.GREEN + f"{'='*60}" + Style.RESET_ALL)
                print(Fore.WHITE + f"Added: {added} | Issues: {issues} | Already in DB: {already_in_db}" + Style.RESET_ALL)

        elif choice == "3":  # Process single PDF
            filename = input("PDF filename to search: ").strip()
            if not filename:
                continue

            files = list_database_files()
            matches = [f for f in files if filename.lower() in os.path.basename(f[0]).lower() and not f[0].lower().endswith('.dwg')]

            if matches:
                print(Fore.CYAN + f"\nFound {len(matches)} in database:" + Style.RESET_ALL)
                for i, (fname, desc, _) in enumerate(matches, 1):
                    print(f"{i}) {os.path.basename(fname)}")
                    print(f"   {desc[:100]}...")
            else:
                directory = prompt_directory(last_dir)
                if not os.path.exists(directory):
                    print(Fore.RED + "Invalid directory." + Style.RESET_ALL)
                    continue

                cache_key, pdf_files = get_directory_hash(directory)
                autocad_pdfs = pdf_cache.get(cache_key) or find_pdf(list_all=False, root=directory)
                match = next((f for f in autocad_pdfs if filename.lower() in os.path.basename(f).lower()), None)
                if match:
                    process_file(match, silent=False)
                else:
                    print(Fore.RED + "File not found." + Style.RESET_ALL)

        elif choice == "4":  # Scan DWGs
            directory = prompt_directory(last_dir)
            if not os.path.exists(directory):
                print(Fore.RED + "Directory not found." + Style.RESET_ALL)
                continue
            
            save_last_directory(directory)
            print(Fore.CYAN + "\nScanning for DWG files..." + Style.RESET_ALL)
            dwg_list = find_dwg_files(directory)
            
            print(Fore.GREEN + f"Found {len(dwg_list)} DWG files" + Style.RESET_ALL)
            if dwg_list:
                for i, dwg in enumerate(dwg_list[:20], 1):
                    print(f"{i}) {os.path.basename(dwg)}")
                if len(dwg_list) > 20:
                    print(f"... and {len(dwg_list) - 20} more")

        elif choice == "5":  # Add all DWGs
            directory = prompt_directory(last_dir)
            if not os.path.exists(directory):
                print(Fore.RED + "Invalid directory." + Style.RESET_ALL)
                continue
            
            save_last_directory(directory)
            print(Fore.CYAN + "\nScanning for DWG files..." + Style.RESET_ALL)
            success, failed = batch_process_dwg_folder(directory)

        elif choice == "6":  # Process single DWG
            dwg_path = input("Enter DWG file path or filename: ").strip()
            
            # Try as full path first
            if os.path.exists(dwg_path):
                process_dwg_file(dwg_path)
            else:
                # Search in database
                files = list_database_files()
                matches = [f for f in files if dwg_path.lower() in os.path.basename(f[0]).lower() and f[0].lower().endswith('.dwg')]
                
                if matches:
                    print(Fore.CYAN + f"\nFound {len(matches)} matches:" + Style.RESET_ALL)
                    for i, (fname, desc, _) in enumerate(matches, 1):
                        print(f"{i}) {os.path.basename(fname)}")
                else:
                    # Search in directory
                    directory = prompt_directory(last_dir)
                    dwg_list = find_dwg_files(directory)
                    match = next((f for f in dwg_list if dwg_path.lower() in os.path.basename(f).lower()), None)
                    if match:
                        process_dwg_file(match)
                    else:
                        print(Fore.RED + "File not found." + Style.RESET_ALL)

        elif choice == "7":  # View DWG details
            view_dwg_details()

        elif choice == "8":  # Export DWG to CSV
            dwg_path = input("Enter DWG file path: ").strip()
            if os.path.exists(dwg_path):
                csv_name = os.path.splitext(os.path.basename(dwg_path))[0] + "_export.csv"
                csv_path = input(f"Output CSV path (Enter for '{csv_name}'): ").strip() or csv_name
                export_dwg_to_csv(dwg_path, csv_path)
            else:
                print(Fore.RED + "File not found." + Style.RESET_ALL)

        elif choice == "9":  # View database
            files = list_database_files()
            if not files:
                print(Fore.YELLOW + "No files in database." + Style.RESET_ALL)
            else:
                print(Fore.CYAN + f"\n{len(files)} files in database:" + Style.RESET_ALL)
                for i, (fname, desc, _) in enumerate(files, 1):
                    file_type = "DWG" if fname.lower().endswith('.dwg') else "PDF"
                    print(f"{i}) [{file_type}] {os.path.basename(fname)}")
                    print(f"   {desc[:80]}...")

        elif choice == "10":  # Search
            query = input("Search query: ").strip()
            if query:
                search_similar_files(query)
            else:
                print(Fore.YELLOW + "No query provided." + Style.RESET_ALL)

        elif choice == "11":  # Remove file
            files = list_database_files()
            if not files:
                print(Fore.YELLOW + "Database empty." + Style.RESET_ALL)
                continue

            print(Fore.CYAN + "\nFiles:" + Style.RESET_ALL)
            for i, (fname, _, _) in enumerate(files, 1):
                file_type = "DWG" if fname.lower().endswith('.dwg') else "PDF"
                print(f"{i}) [{file_type}] {os.path.basename(fname)}")

            choice_input = input("File number to remove: ").strip()
            try:
                idx = int(choice_input) - 1
                if 0 <= idx < len(files):
                    remove_from_database(files[idx][0])
                else:
                    print(Fore.RED + "Invalid selection." + Style.RESET_ALL)
            except ValueError:
                print(Fore.RED + "Invalid input." + Style.RESET_ALL)

        elif choice == "12":  # Remove duplicates
            print(Fore.CYAN + "\nChecking for duplicate database entries..." + Style.RESET_ALL)
            remove_duplicate_files()

        elif choice == "13":  # Clear caches
            from config import CACHE_FILE, PDF_CACHE_FILE
            for cache_file in [str(CACHE_FILE), PDF_CACHE_FILE]:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            pdf_cache = {}
            print(Fore.GREEN + "All caches cleared." + Style.RESET_ALL)

        elif choice == "14":  # Ask questions
            interactive_qa()

        elif choice == "15":  # Reprocess
            reprocess_database_files()

        elif choice == "16":  # Scan mixed directory
            scan_mixed_directory()

        elif choice == "17":  # View config
            view_configuration()

        elif choice == "18":  # Exit
            print(Fore.GREEN + "Goodbye!" + Style.RESET_ALL)
            break

        else:
            print(Fore.RED + "Invalid choice (1-18)." + Style.RESET_ALL)

if __name__ == "__main__":
    main()