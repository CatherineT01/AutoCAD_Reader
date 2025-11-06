# config.py
#**************************************************************************************************
#   Configuration file for AutoCAD PDF/DWG Analyzer
#   Works across different systems - configure via .env file
#**************************************************************************************************
import os
from pathlib import Path
import platform

# Base directory (directory containing this config file)
BASE_DIR = Path(__file__).parent

#==================================================================================================
# PATH DETECTION AND CONFIGURATION
#==================================================================================================

def find_tesseract():
    """Try to find Tesseract installation automatically."""
    system = platform.system()
    
    # Common installation paths by OS
    common_paths = {
        'Windows': [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        ],
        'Linux': [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ],
        'Darwin': [  # macOS
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
        ]
    }
    
    # Try paths for current OS
    for path in common_paths.get(system, []):
        path = Path(path)
        if path.exists():
            return str(path)
    
    # Try which/where command
    try:
        import shutil
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            return tesseract_path
    except:
        pass
    
    return None

def find_poppler():
    """Try to find Poppler installation automatically."""
    system = platform.system()
    
    if system == 'Windows':
        # Common Windows paths
        common_paths = [
            r"C:\Program Files\poppler\Library\bin",
            r"C:\Program Files (x86)\poppler\Library\bin",
            Path.home() / "poppler" / "Library" / "bin",
        ]
        
        for path in common_paths:
            path = Path(path)
            if (path / "pdfinfo.exe").exists():
                return str(path)
    else:
        # On Linux/Mac, poppler is usually in PATH
        try:
            import shutil
            if shutil.which("pdfinfo"):
                # Return None to use system PATH
                return None
        except:
            pass
    
    return None

#==================================================================================================
# EXTERNAL TOOLS CONFIGURATION
#==================================================================================================

# Tesseract OCR - Check environment variable first, then auto-detect
TESSERACT_PATH = os.getenv("TESSERACT_PATH")
if not TESSERACT_PATH:
    TESSERACT_PATH = find_tesseract()

# Poppler - Check environment variable first, then auto-detect
POPPLER_PATH = os.getenv("POPPLER_PATH")
if not POPPLER_PATH:
    POPPLER_PATH = find_poppler()

#==================================================================================================
# API KEYS (from environment variables)
#==================================================================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")

#==================================================================================================
# DATABASE CONFIGURATION
#==================================================================================================

# ChromaDB persistent storage
CHROMA_PERSIST_DIR = BASE_DIR / "chroma_persist"

# Collection name for AutoCAD drawings
COLLECTION_NAME = "autocad_drawings"

#==================================================================================================
# CACHE CONFIGURATION
#==================================================================================================

# Description cache file
CACHE_FILE = BASE_DIR / "description_cache.json"

# PDF scan cache file
PDF_CACHE_FILE = BASE_DIR / "pdf_scan_cache.json"

# Last directory used
LAST_DIR_FILE = BASE_DIR / "last_dir.txt"

# Default directory for file scanning (defaults to user's home directory)
DEFAULT_SCAN_DIR = os.getenv("DEFAULT_SCAN_DIR", str(Path.home()))

#==================================================================================================
# OCR SETTINGS
#==================================================================================================

OCR_DPI = int(os.getenv("OCR_DPI", "300"))  # DPI for PDF to image conversion
OCR_LANG = os.getenv("OCR_LANG", "eng")     # Tesseract language
OCR_PSM = int(os.getenv("OCR_PSM", "6"))    # Page segmentation mode
OCR_OEM = int(os.getenv("OCR_OEM", "1"))    # OCR Engine mode

#==================================================================================================
# AI MODEL SETTINGS
#==================================================================================================

GROK_MODEL = os.getenv("GROK_MODEL", "grok-3-fast-beta")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.3"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "800"))

#==================================================================================================
# FEATURE FLAGS
#==================================================================================================

ENABLE_OCR = os.getenv("ENABLE_OCR", "True").lower() in ("true", "1", "yes")
ENABLE_AI_VALIDATION = os.getenv("ENABLE_AI_VALIDATION", "True").lower() in ("true", "1", "yes")
ENABLE_CACHING = os.getenv("ENABLE_CACHING", "True").lower() in ("true", "1", "yes")
ENABLE_DWG_CONVERSION = os.getenv("ENABLE_DWG_CONVERSION", "True").lower() in ("true", "1", "yes")

#==================================================================================================
# LOGGING
#==================================================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
QUIET_MODE = os.getenv("QUIET_MODE", "False").lower() in ("true", "1", "yes")

#==================================================================================================
# VALIDATION
#==================================================================================================

def validate_config():
    """Validate configuration and check dependencies."""
    issues = []
    
    if ENABLE_OCR:
        if not TESSERACT_PATH or not os.path.exists(TESSERACT_PATH):
            issues.append(
                f"Tesseract not found. Install from: https://github.com/tesseract-ocr/tesseract\n"
                f"  Then set TESSERACT_PATH in .env file"
            )
        
        if POPPLER_PATH:
            pdfinfo_path = Path(POPPLER_PATH) / ("pdfinfo.exe" if platform.system() == "Windows" else "pdfinfo")
            if not pdfinfo_path.exists():
                issues.append(
                    f"Poppler not found at: {POPPLER_PATH}\n"
                    f"  Install from: https://poppler.freedesktop.org/\n"
                    f"  Then set POPPLER_PATH in .env file"
                )
        elif platform.system() == "Windows":
            issues.append(
                f"Poppler not configured. Install from: https://poppler.freedesktop.org/\n"
                f"  Then set POPPLER_PATH in .env file"
            )
    
    if not OPENAI_API_KEY and not GROK_API_KEY:
        issues.append("No API keys configured. Set OPENAI_API_KEY or GROK_API_KEY in .env file")
    
    return issues

def get_config_summary():
    """Get a summary of current configuration for display."""
    # Import here to avoid circular dependency
    try:
        from utils import grok_client, openai_client
        
        return {
            "OCR Enabled": "✓ Yes" if ENABLE_OCR else "✗ No",
            "AI Validation": "✓ Yes" if ENABLE_AI_VALIDATION else "✗ No",
            "Grok Available": "✓ Yes" if grok_client is not None else "✗ No",
            "OpenAI Available": "✓ Yes" if openai_client is not None else "✗ No",
            "Tesseract Path": str(TESSERACT_PATH) if TESSERACT_PATH else "Not found",
            "Poppler Path": str(POPPLER_PATH) if POPPLER_PATH else "System PATH",
            "Cache Directory": str(CHROMA_PERSIST_DIR),
            "Default Scan Dir": DEFAULT_SCAN_DIR,
        }
    except ImportError:
        return {
            "OCR Enabled": "✓ Yes" if ENABLE_OCR else "✗ No",
            "AI Validation": "✓ Yes" if ENABLE_AI_VALIDATION else "✗ No",
            "Grok Available": "✓ Yes" if GROK_API_KEY else "✗ No (Check .env)",
            "OpenAI Available": "✓ Yes" if OPENAI_API_KEY else "✗ No (Check .env)",
            "Tesseract Path": str(TESSERACT_PATH) if TESSERACT_PATH else "Not found",
            "Poppler Path": str(POPPLER_PATH) if POPPLER_PATH else "System PATH",
            "Cache Directory": str(CHROMA_PERSIST_DIR),
            "Default Scan Dir": DEFAULT_SCAN_DIR,
        }

#==================================================================================================
# TESTING
#==================================================================================================

if __name__ == "__main__":
    # Test configuration when run directly
    from colorama import init, Fore, Style
    init(autoreset=True)
    
    print(Fore.CYAN + "=" * 60)
    print(Fore.CYAN + "Configuration Validation")
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    
    print(f"\n{Fore.YELLOW}System: {platform.system()} {platform.release()}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Python: {platform.python_version()}{Style.RESET_ALL}")
    
    issues = validate_config()
    if issues:
        print(f"\n{Fore.RED}⚠ Issues found:{Style.RESET_ALL}")
        for issue in issues:
            print(f"{Fore.YELLOW}  • {issue}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.GREEN}✓ Configuration is valid{Style.RESET_ALL}")
    
    print(f"\n{Fore.CYAN}Configuration Summary:{Style.RESET_ALL}")
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
    for key, value in get_config_summary().items():
        # Truncate long paths for display
        display_value = str(value)
        if len(display_value) > 40:
            display_value = "..." + display_value[-37:]
        
        status_color = Fore.GREEN if "✓" in str(value) else (Fore.RED if "✗" in str(value) else Fore.WHITE)
        print(f"{key:.<30} {status_color}{display_value}{Style.RESET_ALL}")
    
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)