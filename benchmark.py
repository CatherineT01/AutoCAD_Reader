# comprehensive_test.py
#**************************************************************************************************
#   Comprehensive System Test - Analyzes all valid PDF files in database
#   Tests search accuracy, processing performance, and provides detailed statistics
#**************************************************************************************************
import os
import time
import json
import statistics
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime
from colorama import init, Fore, Style
init(autoreset=True)

# Import only what we need from semanticMemory to avoid PDF_Analyzer import issues
from semanticMemory import (
    search_similar_files, 
    get_database_stats, 
    list_database_files,
    collection
)

# Import hash function directly to avoid PDF_Analyzer import
import hashlib

def get_file_hash(filepath):
    """Calculate MD5 hash of file."""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

#==================================================================================================
# CONFIGURATION
#==================================================================================================
OUTPUT_FILE = Path("comprehensive_test_results.json")
DETAILED_LOG = Path("comprehensive_test_detailed.log")

#==================================================================================================
# FILE ANALYSIS
#==================================================================================================

def analyze_database_files():
    """Analyze all files in the database for duplicates and statistics."""
    print(Fore.CYAN + "="*80)
    print(Fore.GREEN + "📊 Comprehensive Database Analysis")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    
    files = list_database_files()
    
    # Track files by hash to detect duplicates
    files_by_hash = {}
    files_by_name = {}
    duplicate_hashes = []
    duplicate_names = []
    
    print(f"\n{Fore.CYAN}Analyzing {len(files)} database entries...{Style.RESET_ALL}")
    
    for filepath, description, specs in files:
        filename = os.path.basename(filepath)
        
        # Check for duplicate filenames
        if filename in files_by_name:
            duplicate_names.append((filename, filepath, files_by_name[filename]))
        else:
            files_by_name[filename] = filepath
        
        # Check for duplicate file content by hash
        if os.path.exists(filepath):
            file_hash = get_file_hash(filepath)
            if file_hash in files_by_hash:
                duplicate_hashes.append((filename, filepath, files_by_hash[file_hash]))
            else:
                files_by_hash[file_hash] = filepath
    
    # Count unique files
    unique_files = len(files_by_hash)
    unique_names = len(files_by_name)
    
    # File type breakdown
    pdf_count = sum(1 for f, _, _ in files if f.lower().endswith('.pdf'))
    dwg_count = sum(1 for f, _, _ in files if f.lower().endswith(('.dwg', '.dxf')))
    
    # Report duplicates
    print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}File Analysis Results:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"Total database entries:        {len(files)}")
    print(f"Unique files (by content):     {unique_files}")
    print(f"Unique filenames:              {unique_names}")
    print(f"PDF files:                     {pdf_count}")
    print(f"DWG files:                     {dwg_count}")
    print(f"Duplicate content detected:    {len(duplicate_hashes)}")
    print(f"Duplicate filenames:           {len(duplicate_names)}")
    
    if duplicate_hashes:
        print(f"\n{Fore.YELLOW}⚠ Duplicate Files (Same Content):{Style.RESET_ALL}")
        for i, (name, path, orig_path) in enumerate(duplicate_hashes[:10], 1):
            print(f"  {i}. {name}")
            print(f"     Duplicate: {path}")
            print(f"     Original:  {orig_path}")
        if len(duplicate_hashes) > 10:
            print(f"  ... and {len(duplicate_hashes) - 10} more duplicates")
    
    if duplicate_names:
        print(f"\n{Fore.YELLOW}⚠ Duplicate Filenames (Different Paths):{Style.RESET_ALL}")
        for i, (name, path, orig_path) in enumerate(duplicate_names[:10], 1):
            print(f"  {i}. {name}")
            print(f"     Path 1: {path}")
            print(f"     Path 2: {orig_path}")
        if len(duplicate_names) > 10:
            print(f"  ... and {len(duplicate_names) - 10} more duplicates")
    
    return {
        'total_entries': len(files),
        'unique_files': unique_files,
        'unique_names': unique_names,
        'pdf_count': pdf_count,
        'dwg_count': dwg_count,
        'duplicate_content': len(duplicate_hashes),
        'duplicate_names': len(duplicate_names),
        'duplicate_list': duplicate_hashes,
        'files_list': files
    }

#==================================================================================================
# SEARCH TESTING
#==================================================================================================

def generate_test_queries(files_info: Dict) -> List[Dict]:
    """Generate test queries based on actual files in database."""
    
    print(f"\n{Fore.CYAN}Generating test queries from file content...{Style.RESET_ALL}")
    
    # Get sample of filenames to generate queries
    files = files_info['files_list']
    unique_files = {}
    
    # Deduplicate by filename
    for filepath, description, specs in files:
        filename = os.path.basename(filepath)
        if filename not in unique_files:
            unique_files[filename] = (filepath, description, specs)
    
    queries = []
    
    # Generate queries from filenames and descriptions
    for filename, (filepath, description, specs) in list(unique_files.items())[:20]:
        # Extract key terms from filename
        name_parts = filename.replace('.pdf', '').replace('.dwg', '').replace('-', ' ').split()
        
        # Query 1: Based on filename keywords
        if len(name_parts) >= 2:
            query_text = ' '.join(name_parts[:3])
            queries.append({
                'query': query_text,
                'relevant_files': [filename],
                'source': 'filename'
            })
        
        # Query 2: Based on description (first few words)
        if description:
            desc_words = description.split()[:5]
            if len(desc_words) >= 3:
                query_text = ' '.join(desc_words)
                queries.append({
                    'query': query_text,
                    'relevant_files': [filename],
                    'source': 'description'
                })
    
    # Add manual high-quality queries if they match database content
    manual_queries = [
        {
            'query': 'coast guard barrel component',
            'relevant_files': ['COAST GUARD 8.0 BARREL 7-15-22.pdf'],
            'source': 'manual'
        },
        {
            'query': 'USCG clevis mechanical part',
            'relevant_files': ['USCG-R0817230713 CLEVIS.pdf'],
            'source': 'manual'
        },
        {
            'query': 'hydraulic cylinder',
            'relevant_files': [
                'COAST GUARD 8.0 BARREL 7-15-22.pdf',
                'COAST GUARD 8.0 BARREL HYDROLINE 7-27-22.pdf'
            ],
            'source': 'manual'
        },
        {
            'query': 'piston assembly',
            'relevant_files': [
                'USCG-3721-PIS-1.pdf',
                'USCG-3721-PIS-2.pdf'
            ],
            'source': 'manual'
        },
    ]
    
    # Only add manual queries if relevant files exist in database
    all_filenames = set(unique_files.keys())
    for mq in manual_queries:
        if any(rf in all_filenames for rf in mq['relevant_files']):
            # Filter to only include files that actually exist
            mq['relevant_files'] = [rf for rf in mq['relevant_files'] if rf in all_filenames]
            if mq['relevant_files']:  # Only add if at least one relevant file exists
                queries.append(mq)
    
    print(f"{Fore.GREEN}✓ Generated {len(queries)} test queries{Style.RESET_ALL}")
    
    return queries

def test_search_accuracy(queries: List[Dict], unique_file_count: int) -> Dict:
    """Test search accuracy with generated queries."""
    
    print(f"\n{Fore.CYAN}Testing Search Accuracy ({len(queries)} queries)...{Style.RESET_ALL}")
    
    k_values = [1, 3, 5, 10]
    precision_at_k = {k: [] for k in k_values}
    recall_at_k = {k: [] for k in k_values}
    mrr_scores = []
    
    detailed_results = []
    
    for i, test in enumerate(queries, 1):
        query = test['query']
        relevant = set(test['relevant_files'])
        source = test.get('source', 'unknown')
        
        if i % 10 == 0 or i == 1:
            print(f"  Query {i}/{len(queries)}: {query[:50]}...")
        
        try:
            # Get search results
            results = search_similar_files(query, n_results=max(k_values), file_type=None)
            retrieved_files = [os.path.basename(r['filename']) for r in results]
            
            # Calculate metrics for each k
            for k in k_values:
                top_k = retrieved_files[:k]
                relevant_in_k = len([f for f in top_k if f in relevant])
                
                # Precision@k
                precision = relevant_in_k / k if k > 0 else 0
                precision_at_k[k].append(precision)
                
                # Recall@k
                recall = relevant_in_k / len(relevant) if len(relevant) > 0 else 0
                recall_at_k[k].append(recall)
            
            # Mean Reciprocal Rank
            reciprocal_rank = 0
            for rank, filename in enumerate(retrieved_files, 1):
                if filename in relevant:
                    reciprocal_rank = 1.0 / rank
                    break
            mrr_scores.append(reciprocal_rank)
            
            # Store detailed result
            detailed_results.append({
                'query': query,
                'source': source,
                'relevant_files': list(relevant),
                'retrieved_files': retrieved_files[:10],
                'found_at_rank': rank if reciprocal_rank > 0 else None,
                'precision_at_5': precision_at_k[5][-1],
                'recall_at_5': recall_at_k[5][-1]
            })
            
        except Exception as e:
            print(f"{Fore.RED}  Error on query '{query}': {e}{Style.RESET_ALL}")
            continue
    
    # Calculate averages
    results = {
        'num_queries': len(queries),
        'precision_at_k': {k: statistics.mean(scores) if scores else 0 
                          for k, scores in precision_at_k.items()},
        'recall_at_k': {k: statistics.mean(scores) if scores else 0 
                       for k, scores in recall_at_k.items()},
        'mrr': statistics.mean(mrr_scores) if mrr_scores else 0,
        'detailed_results': detailed_results
    }
    
    # Print summary
    print(f"\n{Fore.GREEN}✓ Search Accuracy Results:{Style.RESET_ALL}")
    for k in k_values:
        print(f"  P@{k}: {results['precision_at_k'][k]:.3f}, "
              f"R@{k}: {results['recall_at_k'][k]:.3f}")
    print(f"  MRR: {results['mrr']:.3f}")
    
    return results

def test_search_speed(num_queries: int = 100) -> Dict:
    """Test search response time."""
    
    print(f"\n{Fore.CYAN}Testing Search Speed ({num_queries} queries)...{Style.RESET_ALL}")
    
    sample_queries = [
        "hydraulic cylinder",
        "mechanical assembly",
        "coast guard",
        "piston",
        "barrel",
        "clevis",
        "technical drawing",
        "engineering diagram",
        "component specification",
        "structural detail"
    ]
    
    times = []
    
    for i in range(num_queries):
        query = sample_queries[i % len(sample_queries)]
        
        start = time.time()
        try:
            results = search_similar_files(query, n_results=5, file_type=None)
            elapsed = (time.time() - start) * 1000  # Convert to milliseconds
            times.append(elapsed)
        except Exception as e:
            print(f"{Fore.YELLOW}  Warning: Query failed: {e}{Style.RESET_ALL}")
            continue
        
        if (i + 1) % 20 == 0:
            print(f"  Completed {i + 1}/{num_queries} queries")
    
    if not times:
        return {'error': 'All queries failed'}
    
    results = {
        'count': len(times),
        'avg_time_ms': statistics.mean(times),
        'std_dev_ms': statistics.stdev(times) if len(times) > 1 else 0,
        'min_time_ms': min(times),
        'max_time_ms': max(times),
        'median_time_ms': statistics.median(times)
    }
    
    print(f"{Fore.GREEN}✓ Average: {results['avg_time_ms']:.2f}ms ± {results['std_dev_ms']:.2f}ms{Style.RESET_ALL}")
    
    return results

def test_memory_usage(file_count: int) -> Dict:
    """Test memory usage."""
    
    print(f"\n{Fore.CYAN}Measuring Memory Usage...{Style.RESET_ALL}")
    
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        
        results = {
            'rss_mb': mem_info.rss / (1024 * 1024),
            'vms_mb': mem_info.vms / (1024 * 1024),
            'total_files': file_count,
            'mb_per_file': (mem_info.rss / (1024 * 1024)) / file_count if file_count > 0 else 0
        }
        
        print(f"{Fore.GREEN}✓ RSS: {results['rss_mb']:.2f}MB, Per File: {results['mb_per_file']:.3f}MB{Style.RESET_ALL}")
        
        return results
    except ImportError:
        print(f"{Fore.YELLOW}⚠ psutil not installed, skipping memory test{Style.RESET_ALL}")
        return {'error': 'psutil not available'}

def test_database_size() -> Dict:
    """Measure database storage size."""
    
    print(f"\n{Fore.CYAN}Measuring Database Size...{Style.RESET_ALL}")
    
    from config import CHROMA_PERSIST_DIR
    
    total_size = 0
    if CHROMA_PERSIST_DIR.exists():
        for path in CHROMA_PERSIST_DIR.rglob('*'):
            if path.is_file():
                total_size += path.stat().st_size
    
    stats = get_database_stats()
    
    results = {
        'total_size_mb': total_size / (1024 * 1024),
        'total_files': stats['total_files'],
        'mb_per_file': (total_size / (1024 * 1024)) / stats['total_files'] if stats['total_files'] > 0 else 0
    }
    
    print(f"{Fore.GREEN}✓ Total: {results['total_size_mb']:.2f}MB, Per File: {results['mb_per_file']:.3f}MB{Style.RESET_ALL}")
    
    return results

#==================================================================================================
# MAIN TEST RUNNER
#==================================================================================================

def run_comprehensive_test():
    """Run all tests and generate detailed report."""
    
    print(Fore.CYAN + "="*80)
    print(Fore.GREEN + "🧪 COMPREHENSIVE SYSTEM TEST")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    print(f"\n{Fore.YELLOW}This test will:{Style.RESET_ALL}")
    print("  • Analyze all files in database")
    print("  • Detect and report duplicates")
    print("  • Test search accuracy")
    print("  • Measure search speed")
    print("  • Check system resource usage")
    print()
    
    start_time = datetime.now()
    
    # Stage 1: File Analysis
    files_info = analyze_database_files()
    
    # Stage 2: Generate test queries
    test_queries = generate_test_queries(files_info)
    
    # Stage 3: Search accuracy
    accuracy_results = test_search_accuracy(test_queries, files_info['unique_files'])
    
    # Stage 4: Search speed
    speed_results = test_search_speed(num_queries=50)
    
    # Stage 5: Resource usage
    memory_results = test_memory_usage(files_info['unique_files'])
    database_results = test_database_size()
    
    # Compile results
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    full_results = {
        'test_date': start_time.isoformat(),
        'test_duration_seconds': duration,
        'file_analysis': {
            'total_database_entries': files_info['total_entries'],
            'unique_files_by_content': files_info['unique_files'],
            'unique_filenames': files_info['unique_names'],
            'pdf_count': files_info['pdf_count'],
            'dwg_count': files_info['dwg_count'],
            'duplicate_content_count': files_info['duplicate_content'],
            'duplicate_names_count': files_info['duplicate_names']
        },
        'search_accuracy': accuracy_results,
        'search_speed': speed_results,
        'memory_usage': memory_results,
        'database_size': database_results
    }
    
    # Save results
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(full_results, f, indent=2)
    
    # Save detailed log
    with open(DETAILED_LOG, 'w') as f:
        f.write(f"Comprehensive System Test - {start_time}\n")
        f.write("="*80 + "\n\n")
        
        f.write("FILE ANALYSIS\n")
        f.write("-"*80 + "\n")
        f.write(f"Total Entries: {files_info['total_entries']}\n")
        f.write(f"Unique Files: {files_info['unique_files']}\n")
        f.write(f"Duplicates: {files_info['duplicate_content']}\n\n")
        
        if files_info['duplicate_list']:
            f.write("Duplicate Files:\n")
            for name, path, orig in files_info['duplicate_list']:
                f.write(f"  {name}\n")
                f.write(f"    Dup: {path}\n")
                f.write(f"    Orig: {orig}\n\n")
        
        f.write("\nSEARCH ACCURACY DETAILS\n")
        f.write("-"*80 + "\n")
        for result in accuracy_results.get('detailed_results', [])[:20]:
            f.write(f"\nQuery: {result['query']}\n")
            f.write(f"Source: {result['source']}\n")
            f.write(f"Relevant: {result['relevant_files']}\n")
            f.write(f"Found at rank: {result.get('found_at_rank', 'Not found')}\n")
            f.write(f"P@5: {result['precision_at_5']:.3f}, R@5: {result['recall_at_5']:.3f}\n")
    
    # Print final summary
    print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}✓ COMPREHENSIVE TEST COMPLETE{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}Summary for Paper:{Style.RESET_ALL}")
    print(f"  Test Corpus: {files_info['unique_files']} unique files")
    print(f"  File Types: {files_info['pdf_count']} PDFs, {files_info['dwg_count']} DWGs")
    print(f"  Search Speed: {speed_results.get('avg_time_ms', 'N/A'):.2f}ms avg")
    print(f"  Recall@5: {accuracy_results['recall_at_k'].get(5, 0):.3f}")
    print(f"  Recall@10: {accuracy_results['recall_at_k'].get(10, 0):.3f}")
    print(f"  MRR: {accuracy_results['mrr']:.3f}")
    print(f"  Memory: {memory_results.get('mb_per_file', 'N/A'):.2f}MB per file")
    print(f"  Storage: {database_results.get('mb_per_file', 'N/A'):.3f}MB per file")
    print(f"\n{Fore.GREEN}Results saved to:{Style.RESET_ALL}")
    print(f"  • {OUTPUT_FILE}")
    print(f"  • {DETAILED_LOG}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    
    return full_results

#==================================================================================================
# ENTRY POINT
#==================================================================================================

if __name__ == "__main__":
    try:
        results = run_comprehensive_test()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Test interrupted by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n\n{Fore.RED}Test failed with error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()