# drawingSystem.py
import os
from PDF_Analyzer import find_pdf, process_pdf, print_typed, ask_question_about_description
from colorama import init, Fore, Style
from semanticMemory import build_index, search_similar_files
from utils import load_cache, save_cache, get_file_hash, CACHE_FILE

# Initialize colorama
init(autoreset=True)

class AutoCADFinder:
    def __init__(self):
        self.file_cache = []
        self.last_description = ""

    def run(self):
        print_typed("AutoCAD PDF Finder & Explainer", delay=0.02)
        print("Options: [1] List PDFs, [2] Exit, [3] Search Similar, [4] Clear Cache, or enter a PDF filename.")
        print("=" * 70)

        while True:
            user_input = input(">>> ").strip()
            if user_input in {"2", "exit", "quit"}:
                print_typed("Goodbye!", delay=0.02)
                break
            elif user_input in {"1", "list"}:
                self.list_pdfs()
            elif user_input in {"3", "search"}:
                query = input("Search query: ").strip()
                if query:
                    self.search_drawings(query)
                else:
                    print(Fore.YELLOW + "Please enter a search term." + Style.RESET_ALL)
            elif user_input in {"4", "clear"}:
                self.clear_cache()
            elif user_input.lower().endswith(".pdf"):
                result = self.process_pdf_file(user_input)
                if result == "EXIT":  # User quit during Q&A
                    break
            elif user_input.lower() == "build index":
                print("Building vector index...")
                build_index()
                print(Fore.GREEN + "Index built successfully!" + Style.RESET_ALL)
            else:
                self.ask_about_last(user_input)

    def list_pdfs(self):
        print("Scanning current folder + ALL subfolders...")
        self.file_cache = find_pdf(list_all=True)
        if self.file_cache:
            print(f"\nFound {len(self.file_cache)} AutoCAD-style PDFs:")
            for i, f in enumerate(self.file_cache, 1):
                print(f"  {i:2d}. {os.path.basename(f)}")
            print()
        else:
            print(Fore.YELLOW + "No AutoCAD-style PDFs found.\n" + Style.RESET_ALL)

    def process_pdf_file(self, filename):
        pdf_path = find_pdf(filename=filename)
        if not pdf_path:
            return  # Error already printed

        result = process_pdf(pdf_path)  # Now returns None on EXIT_PROGRAM
        if result is None:  # User wants to quit
            return "EXIT"  # Signal to main loop
    
        description = result
        self.last_description = description

        # Cache it
        cache = load_cache()
        file_hash = get_file_hash(pdf_path)
        cache[file_hash] = {"description": description, "path": pdf_path}
        save_cache(cache)

    def search_drawings(self, query):
        print(f"Searching for: '{query}'")
        results = search_similar_files(query)
        if not results:
            print(Fore.YELLOW + "No similar drawings found.\n" + Style.RESET_ALL)
            return

        cache = load_cache()
        print(f"\n{Fore.GREEN}Found {len(results)} similar drawing(s):{Style.RESET_ALL}")
        for file_hash, path in results:
            desc = cache.get(file_hash, {}).get("description", "No description cached")
            print(f"\n  File: {os.path.basename(path)}")
            print(f"  {desc[:400]}{'...' if len(desc) > 400 else ''}")
        print()

    def clear_cache(self):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(Fore.GREEN + "Cache cleared.\n" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + "No cache to clear.\n" + Style.RESET_ALL)

    def ask_about_last(self, question):
        if not self.last_description:
            print(Fore.YELLOW + "No description yet. Process a PDF first.\n" + Style.RESET_ALL)
            return
        answer = ask_question_about_description(self.last_description, question)
        print("\n" + "="*70)
        print("Answer:")
        print(answer)
        print("="*70 + "\n")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("GROK_API_KEY"):
        print(Fore.RED + "Missing API keys! Please set OPENAI_API_KEY and GROK_API_KEY as environment variables." + Style.RESET_ALL)
        print("Example (Windows): setx OPENAI_API_KEY your-key")
        exit(1)

    system = AutoCADFinder()
    system.run()
