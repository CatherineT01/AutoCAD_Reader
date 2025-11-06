# main.py
#**************************************************************************************************
#   Main Command-Line Interface for AutoCAD Drawing Processing System
#   Provides interactive menu for all system operations
#**************************************************************************************************
import os
import sys
from pathlib import Path
from colorama import init, Fore, Style
init(autoreset=True)

# Import all modules
from config import validate_config
from DWG_Processor import DWGProcessor, batch_process_dwg_folder, export_dwg_to_csv
from PDF_Analyzer import process_pdf, find_pdf, answer_question
from semanticMemory import (
    search_similar_files, list_database_files, get_from_database,
    remove_from_database, get_database_stats, clear_database
)

#==================================================================================================
# DISPLAY FUNCTIONS
#==================================================================================================
def print_header():
    """Print application header."""
    print(Fore.CYAN + "="*80)
    print(Fore.GREEN + "   🏗️  AutoCAD Drawing Processing System v1.0")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)

def print_menu():
    """Print main menu."""
    print("\n" + Fore.CYAN + "📋 MAIN MENU" + Style.RESET_ALL)
    print(Fore.YELLOW + "─" * 40)
    print(Fore.GREEN + "1)" + Style.RESET_ALL + " Process DWG File")
    print(Fore.GREEN + "2)" + Style.RESET_ALL + " Process PDF File")
    print(Fore.GREEN + "3)" + Style.RESET_ALL + " Batch Process Folder")
    print(Fore.GREEN + "4)" + Style.RESET_ALL + " Search Database")
    print(Fore.GREEN + "5)" + Style.RESET_ALL + " List All Files")
    print(Fore.GREEN + "6)" + Style.RESET_ALL + " View File Details")
    print(Fore.GREEN + "7)" + Style.RESET_ALL + " Ask Question About Drawing")
    print(Fore.GREEN + "8)" + Style.RESET_ALL + " Export DWG to CSV")
    print(Fore.GREEN + "9)" + Style.RESET_ALL + " Database Statistics")
    print(Fore.GREEN + "10)" + Style.RESET_ALL + " Remove File from Database")
    print(Fore.GREEN + "11)" + Style.RESET_ALL + " Clear Database")
    print(Fore.RED + "0)" + Style.RESET_ALL + " Exit")
    print(Fore.YELLOW + "─" * 40)

def print_stats():
    """Print database statistics."""
    stats = get_database_stats()
    print(Fore.CYAN + "\n📊 DATABASE STATISTICS" + Style.RESET_ALL)
    print(Fore.YELLOW + "─" * 40)
    print(f"Total Files: {stats['total_files']}")
    print(f"  📐 DWG Files: {stats['dwg_files']}")
    print(f"  📄 PDF Files: {stats['pdf_files']}")
    print(f"Storage: {stats['persist_directory']}")
    print(Fore.YELLOW + "─" * 40)

#==================================================================================================
# MENU FUNCTIONS
#==================================================================================================
def process_dwg_menu():
    """Process a single DWG file."""
    print(Fore.CYAN + "\n📐 PROCESS DWG FILE" + Style.RESET_ALL)
    file_path = input("Enter DWG file path: ").strip().strip('"')
    
    if not os.path.exists(file_path):
        print(Fore.RED + "✗ File not found!" + Style.RESET_ALL)
        return
    
    if not file_path.lower().endswith(('.dwg', '.dxf')):
        print(Fore.RED + "✗ Not a DWG/DXF file!" + Style.RESET_ALL)
        return
    
    processor = DWGProcessor()
    print(Fore.YELLOW + "\nProcessing..." + Style.RESET_ALL)
    success = processor.add_to_database(file_path, silent=False)
    
    if success:
        print(Fore.GREEN + "\n✓ Successfully processed and added to database!" + Style.RESET_ALL)
    else:
        print(Fore.RED + "\n✗ Failed to process file" + Style.RESET_ALL)

def process_pdf_menu():
    """Process a single PDF file."""
    print(Fore.CYAN + "\n📄 PROCESS PDF FILE" + Style.RESET_ALL)
    file_path = input("Enter PDF file path: ").strip().strip('"')
    
    if not os.path.exists(file_path):
        print(Fore.RED + "✗ File not found!" + Style.RESET_ALL)
        return
    
    if not file_path.lower().endswith('.pdf'):
        print(Fore.RED + "✗ Not a PDF file!" + Style.RESET_ALL)
        return
    
    print(Fore.YELLOW + "\nProcessing..." + Style.RESET_ALL)
    success = process_pdf(file_path, silent=False)
    
    if success:
        print(Fore.GREEN + "\n✓ Successfully processed and added to database!" + Style.RESET_ALL)
    else:
        print(Fore.RED + "\n✗ Failed to process file (may not be an AutoCAD drawing)" + Style.RESET_ALL)

def batch_process_menu():
    """Batch process all files in a folder."""
    print(Fore.CYAN + "\n📁 BATCH PROCESS FOLDER" + Style.RESET_ALL)
    folder_path = input("Enter folder path: ").strip().strip('"')
    
    if not os.path.exists(folder_path):
        print(Fore.RED + "✗ Folder not found!" + Style.RESET_ALL)
        return
    
    print(Fore.YELLOW + "\nScanning and processing..." + Style.RESET_ALL)
    
    # Process DWG files
    print(Fore.CYAN + "\n🔧 Processing DWG Files..." + Style.RESET_ALL)
    dwg_success, dwg_failed = batch_process_dwg_folder(folder_path, silent=False)
    
    # Process PDF files
    print(Fore.CYAN + "\n📄 Processing PDF Files..." + Style.RESET_ALL)
    pdf_files = find_pdf(list_all=False, root=folder_path)
    pdf_success = 0
    pdf_failed = 0
    for pdf_path in pdf_files:
        if process_pdf(pdf_path, silent=True):
            pdf_success += 1
        else:
            pdf_failed += 1
    
    # Summary
    print(Fore.CYAN + f"\n{'='*60}" + Style.RESET_ALL)
    print(Fore.GREEN + f"✓ Total Processed: {dwg_success + pdf_success}" + Style.RESET_ALL)
    print(f"  📐 DWG: {dwg_success}")
    print(f"  📄 PDF: {pdf_success}")
    if dwg_failed + pdf_failed > 0:
        print(Fore.RED + f"✗ Total Failed: {dwg_failed + pdf_failed}" + Style.RESET_ALL)
    print(Fore.CYAN + f"{'='*60}" + Style.RESET_ALL)

def search_menu():
    """Search database with semantic query."""
    print(Fore.CYAN + "\n🔍 SEARCH DATABASE" + Style.RESET_ALL)
    query = input("Enter search query: ").strip()
    
    if not query:
        print(Fore.RED + "✗ Query cannot be empty!" + Style.RESET_ALL)
        return
    
    try:
        n_results = int(input("Number of results (default 5): ").strip() or "5")
    except ValueError:
        n_results = 5
    
    file_type = input("Filter by type (dwg/pdf/all) [all]: ").strip().lower()
    if file_type not in ['dwg', 'pdf']:
        file_type = None
    
    print(Fore.YELLOW + "\nSearching..." + Style.RESET_ALL)
    results = search_similar_files(query, n_results=n_results, file_type=file_type)
    
    if not results:
        print(Fore.YELLOW + "⚠ No results found" + Style.RESET_ALL)

def list_files_menu():
    """List all files in database."""
    print(Fore.CYAN + "\n📂 FILES IN DATABASE" + Style.RESET_ALL)
    files = list_database_files()
    
    if not files:
        print(Fore.YELLOW + "⚠ Database is empty" + Style.RESET_ALL)
        return
    
    print(Fore.YELLOW + f"\nTotal: {len(files)} files" + Style.RESET_ALL)
    print(Fore.YELLOW + "─" * 80)
    
    for i, (filepath, description, specs) in enumerate(files, 1):
        filename = os.path.basename(filepath)
        file_type = "📐 DWG" if filepath.lower().endswith('.dwg') else "📄 PDF"
        print(f"{i}. {file_type} {Fore.GREEN}{filename}{Style.RESET_ALL}")
        print(f"   {description[:100]}...")
        print()

def view_file_menu():
    """View detailed information about a file."""
    print(Fore.CYAN + "\n📋 VIEW FILE DETAILS" + Style.RESET_ALL)
    filepath = input("Enter file path or name: ").strip().strip('"')
    
    data = get_from_database(filepath)
    
    if not data:
        print(Fore.RED + "✗ File not found in database!" + Style.RESET_ALL)
        return
    
    print(Fore.CYAN + "\n" + "="*80 + Style.RESET_ALL)
    print(Fore.GREEN + f"📄 {data['filename']}" + Style.RESET_ALL)
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    print(f"Type: {data['file_type'].upper()}")
    print(f"Path: {data['filepath']}")
    print(f"\nDescription:\n{data.get('description', 'N/A')}")
    
    specs = data.get('specs', {})
    if specs:
        print(Fore.CYAN + "\n📊 Specifications:" + Style.RESET_ALL)
        import json
        print(json.dumps(specs, indent=2))
    
    # DWG-specific data
    if data['file_type'] == 'dwg':
        print(Fore.CYAN + "\n🔧 DWG Data:" + Style.RESET_ALL)
        print(f"Entities: {data.get('entity_count', 'N/A')}")
        print(f"Layers: {data.get('layer_count', 'N/A')}")
        print(f"Blocks: {data.get('block_count', 'N/A')}")
        
        csv_data = data.get('csv_data', '')
        if csv_data:
            print(Fore.CYAN + "\n📊 CSV Preview:" + Style.RESET_ALL)
            print(csv_data[:500] + "..." if len(csv_data) > 500 else csv_data)
    
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)

def ask_question_menu():
    """Ask a question about a drawing."""
    print(Fore.CYAN + "\n❓ ASK QUESTION" + Style.RESET_ALL)
    filepath = input("Enter file path or name: ").strip().strip('"')
    
    data = get_from_database(filepath)
    
    if not data:
        print(Fore.RED + "✗ File not found in database!" + Style.RESET_ALL)
        return
    
    print(Fore.GREEN + f"📄 File: {data['filename']}" + Style.RESET_ALL)
    question = input("Your question: ").strip()
    
    if not question:
        print(Fore.RED + "✗ Question cannot be empty!" + Style.RESET_ALL)
        return
    
    print(Fore.YELLOW + "\nThinking..." + Style.RESET_ALL)
    
    answer = answer_question(
        question=question,
        text=data.get('description', ''),
        specs=data.get('specs'),
        description=data.get('description', ''),
        silent=False
    )
    
    print(Fore.CYAN + "\n💡 Answer:" + Style.RESET_ALL)
    print(answer)

def export_csv_menu():
    """Export DWG to CSV."""
    print(Fore.CYAN + "\n💾 EXPORT DWG TO CSV" + Style.RESET_ALL)
    dwg_path = input("Enter DWG file path: ").strip().strip('"')
    
    if not os.path.exists(dwg_path):
        print(Fore.RED + "✗ File not found!" + Style.RESET_ALL)
        return
    
    output_path = input("Output CSV path (press Enter for auto): ").strip().strip('"')
    if not output_path:
        output_path = f"{os.path.splitext(dwg_path)[0]}_export.csv"
    
    print(Fore.YELLOW + "\nExporting..." + Style.RESET_ALL)
    success = export_dwg_to_csv(dwg_path, output_path)
    
    if success:
        print(Fore.GREEN + f"\n✓ Exported to: {output_path}" + Style.RESET_ALL)

def remove_file_menu():
    """Remove a file from database."""
    print(Fore.CYAN + "\n🗑️  REMOVE FILE" + Style.RESET_ALL)
    filepath = input("Enter file path or name: ").strip().strip('"')
    
    confirm = input(Fore.YELLOW + "Are you sure? (yes/no): " + Style.RESET_ALL).strip().lower()
    
    if confirm == 'yes':
        success = remove_from_database(filepath)
        if not success:
            print(Fore.RED + "✗ File not found in database!" + Style.RESET_ALL)
    else:
        print(Fore.YELLOW + "⚠ Cancelled" + Style.RESET_ALL)

def clear_database_menu():
    """Clear entire database."""
    print(Fore.RED + "\n⚠️  CLEAR DATABASE" + Style.RESET_ALL)
    print(Fore.YELLOW + "This will delete ALL files from the database!" + Style.RESET_ALL)
    confirm = input(Fore.RED + "Type 'DELETE' to confirm: " + Style.RESET_ALL).strip()
    
    if confirm == 'DELETE':
        success = clear_database(confirm=True)
        if success:
            print(Fore.GREEN + "\n✓ Database cleared successfully" + Style.RESET_ALL)
    else:
        print(Fore.YELLOW + "⚠ Cancelled" + Style.RESET_ALL)

#==================================================================================================
# MAIN LOOP
#==================================================================================================
def main():
    """Main application loop."""
    print_header()
    
    # Validate configuration
    warnings = validate_config()
    if warnings:
        print(Fore.YELLOW + "\n⚠️  Configuration Warnings:" + Style.RESET_ALL)
        for warning in warnings:
            print(warning)
        input("\nPress Enter to continue...")
    
    # Show initial stats
    print_stats()
    
    # Main loop
    while True:
        print_menu()
        choice = input(Fore.CYAN + "\nEnter choice: " + Style.RESET_ALL).strip()
        
        try:
            if choice == '1':
                process_dwg_menu()
            elif choice == '2':
                process_pdf_menu()
            elif choice == '3':
                batch_process_menu()
            elif choice == '4':
                search_menu()
            elif choice == '5':
                list_files_menu()
            elif choice == '6':
                view_file_menu()
            elif choice == '7':
                ask_question_menu()
            elif choice == '8':
                export_csv_menu()
            elif choice == '9':
                print_stats()
            elif choice == '10':
                remove_file_menu()
            elif choice == '11':
                clear_database_menu()
            elif choice == '0':
                print(Fore.GREEN + "\n👋 Goodbye!" + Style.RESET_ALL)
                break
            else:
                print(Fore.RED + "✗ Invalid choice!" + Style.RESET_ALL)
        
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n\n⚠ Interrupted by user" + Style.RESET_ALL)
            continue
        except Exception as e:
            print(Fore.RED + f"\n✗ Error: {e}" + Style.RESET_ALL)
            import traceback
            traceback.print_exc()
        
        input(Fore.CYAN + "\nPress Enter to continue..." + Style.RESET_ALL)

if __name__ == "__main__":
    main()
