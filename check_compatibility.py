# check_compatibility.py
#**************************************************************************************************
#   Compatibility Checker - Verifies your files match the new integration code
#**************************************************************************************************
import os
import sys
from colorama import init, Fore, Style
init(autoreset=True)

def check_file_exists(filename):
    """Check if file exists and return status."""
    exists = os.path.exists(filename)
    status = Fore.GREEN + "✓ Found" if exists else Fore.RED + "✗ Missing"
    print(f"{status} {filename}" + Style.RESET_ALL)
    return exists

def check_function_exists(filename, function_name):
    """Check if a function exists in a file."""
    if not os.path.exists(filename):
        print(f"  {Fore.YELLOW}⚠ Can't check - file doesn't exist{Style.RESET_ALL}")
        return False
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            exists = f"def {function_name}" in content or f"class {function_name}" in content
            status = Fore.GREEN + "✓" if exists else Fore.RED + "✗"
            print(f"  {status} {function_name}()" + Style.RESET_ALL)
            return exists
    except Exception as e:
        print(f"  {Fore.RED}✗ Error reading file: {e}{Style.RESET_ALL}")
        return False

print(Fore.CYAN + "="*80)
print(Fore.GREEN + "🔍 Checking File Compatibility")
print(Fore.CYAN + "="*80 + Style.RESET_ALL)

# Check core files
print(Fore.CYAN + "\n📋 Core Files:" + Style.RESET_ALL)
core_files = {
    'DWG_Processor.py': ['DWGProcessor', 'find_dwg_files', 'batch_process_dwg_folder'],
    'PDF_Analyzer.py': ['process_pdf', 'find_pdf', 'answer_question', 'extract_text'],
    'semanticMemory.py': ['add_to_database', 'get_from_database', 'search_similar_files'],
    'utils.py': ['GrokClient', 'chat_with_ai', 'clean_specs']
}

all_good = True
for filename, functions in core_files.items():
    exists = check_file_exists(filename)
    if exists:
        for func in functions:
            if not check_function_exists(filename, func):
                all_good = False
    else:
        all_good = False

# Check new integration files
print(Fore.CYAN + "\n🆕 New Integration Files:" + Style.RESET_ALL)
integration_files = [
    'config.py',
    'api_server.py',
    'test_system.py',
    'benchmark.py'
]

for filename in integration_files:
    if not check_file_exists(filename):
        all_good = False

# Check optional files
print(Fore.CYAN + "\n📄 Optional Files:" + Style.RESET_ALL)
optional_files = [
    'Main.py',
    'drawingSystem.py',
    'requirements.txt',
    '.env'
]

for filename in optional_files:
    check_file_exists(filename)

# Check imports
print(Fore.CYAN + "\n🔗 Checking Imports:" + Style.RESET_ALL)
try:
    print("Testing imports...")
    
    # Try importing config
    try:
        import config
        print(f"{Fore.GREEN}✓ config.py imports successfully{Style.RESET_ALL}")
    except ImportError as e:
        print(f"{Fore.RED}✗ config.py import failed: {e}{Style.RESET_ALL}")
        all_good = False
    
    # Try importing your core modules
    try:
        # These will fail if files don't exist or have syntax errors
        import DWG_Processor
        print(f"{Fore.GREEN}✓ DWG_Processor.py imports successfully{Style.RESET_ALL}")
    except ImportError as e:
        print(f"{Fore.RED}✗ DWG_Processor.py import failed: {e}{Style.RESET_ALL}")
        all_good = False
    
    try:
        import PDF_Analyzer
        print(f"{Fore.GREEN}✓ PDF_Analyzer.py imports successfully{Style.RESET_ALL}")
    except ImportError as e:
        print(f"{Fore.RED}✗ PDF_Analyzer.py import failed: {e}{Style.RESET_ALL}")
        all_good = False
    
    try:
        import semanticMemory
        print(f"{Fore.GREEN}✓ semanticMemory.py imports successfully{Style.RESET_ALL}")
    except ImportError as e:
        print(f"{Fore.RED}✗ semanticMemory.py import failed: {e}{Style.RESET_ALL}")
        all_good = False
    
    try:
        import utils
        print(f"{Fore.GREEN}✓ utils.py imports successfully{Style.RESET_ALL}")
    except ImportError as e:
        print(f"{Fore.RED}✗ utils.py import failed: {e}{Style.RESET_ALL}")
        all_good = False

except Exception as e:
    print(f"{Fore.RED}✗ Import test failed: {e}{Style.RESET_ALL}")
    all_good = False

# Summary
print(Fore.CYAN + "\n" + "="*80)
if all_good:
    print(Fore.GREEN + "✓ All checks passed! Your system is compatible." + Style.RESET_ALL)
else:
    print(Fore.YELLOW + "⚠ Some issues found. See details above." + Style.RESET_ALL)
    print(Fore.CYAN + "\nCommon fixes:")
    print("1. Install missing dependencies: pip install -r requirements.txt")
    print("2. Make sure file names match (DWG_Process.py vs DWG_Processor.py)")
    print("3. Check that required functions exist in your files")
    print("4. Create .env file from .env.example")
print(Fore.CYAN + "="*80 + Style.RESET_ALL)
