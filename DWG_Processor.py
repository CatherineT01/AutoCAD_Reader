# DWG_Processor.py
#**************************************************************************************************
#   Processes DWG files by extracting entity data, converting to CSV, creating embeddings,
#   and storing in ChromaDB vector database.
#**************************************************************************************************
import os
import csv
import json
import hashlib
import shutil
import subprocess
import tempfile
import string
from typing import Dict, List, Optional, Tuple
from io import StringIO
from pathlib import Path

import ezdxf
from colorama import Fore, Style
import logging

from semanticMemory import (
    collection, generate_embedding_id, file_exists_in_database,
    default_ef
)
from utils import grok_client, openai_client
from config import ENABLE_DWG_CONVERSION

# Silence noisy ezdxf logging
logging.getLogger("ezdxf").setLevel(logging.ERROR)

def find_oda_converter() -> Optional[str]:
    """
    Automatically search for ODA File Converter across all drives and common paths.
    Returns path if found, None otherwise.
    """
    # Common installation folder names
    search_dirs = [
        "ODA",
        "ODAFileConverter", 
        "AutoCAD_Reader",
        "CAD",
        "DWG",
    ]
    
    # Get all available drives
    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    
    # Common base paths to check on each drive
    base_paths = [
        "",  # Root of drive
        "Program Files\\ODA\\ODAFileConverter",
        "Program Files (x86)\\ODA\\ODAFileConverter",
        "ODA\\ODAFileConverter",
    ]
    
    # Quick check: common locations first
    for drive in drives:
        for base in base_paths:
            check_path = os.path.join(drive, base, "ODAFileConverter.exe")
            if os.path.exists(check_path):
                return check_path
    
    # If not found in common locations, search in common directories
    for drive in drives:
        for search_dir in search_dirs:
            search_path = os.path.join(drive, search_dir)
            if os.path.exists(search_path):
                # Look for ODAFileConverter.exe in this directory and subdirectories
                for root, dirs, files in os.walk(search_path):
                    if "ODAFileConverter.exe" in files:
                        return os.path.join(root, "ODAFileConverter.exe")
                    # Don't go too deep (max 2 levels)
                    if root.count(os.sep) - search_path.count(os.sep) >= 2:
                        del dirs[:]
    
    return None

# Find ODA File Converter automatically
ODA_CONVERTER_PATH = find_oda_converter()
DWG_CONVERSION_AVAILABLE = ENABLE_DWG_CONVERSION and ODA_CONVERTER_PATH is not None


class DWGProcessor:
    """Handles DWG file processing and conversion to vector embeddings."""

    def __init__(self):
        self.supported_entities = [
            'LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE',
            'TEXT', 'MTEXT', 'INSERT', 'DIMENSION', 'HATCH'
        ]
        self.temp_dir = None

    def _convert_dwg_to_dxf(self, dwg_path: str, silent: bool = False) -> Optional[str]:
        """
        Convert DWG to DXF using ODA File Converter.
        Returns path to temporary DXF file or None if conversion fails.
        """
        if not DWG_CONVERSION_AVAILABLE:
            return None

        try:
            if not self.temp_dir:
                self.temp_dir = tempfile.mkdtemp()

            output_dir = tempfile.mkdtemp(dir=self.temp_dir)
            input_folder = os.path.dirname(dwg_path)
            input_file = os.path.basename(dwg_path)

            # Build command - NO shell quoting needed when using list
            cmd = [
                ODA_CONVERTER_PATH,
                input_folder,
                output_dir,
                "ACAD2018",
                "DXF",
                "0",
                "1",
                input_file
            ]

            # Run converter
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90
            )

            # Check for output file
            expected_dxf = os.path.join(output_dir, os.path.splitext(input_file)[0] + ".dxf")
            
            if os.path.exists(expected_dxf):
                if not silent:
                    print(Fore.GREEN + "✓ Converted" + Style.RESET_ALL, end=' ')
                return expected_dxf
            else:
                if result.returncode != 0:
                    if not silent:
                        print(Fore.RED + f"✗ ODA Error (code {result.returncode})" + Style.RESET_ALL)
                else:
                    if not silent:
                        print(Fore.YELLOW + "✗ DXF not created" + Style.RESET_ALL)
                return None

        except subprocess.TimeoutExpired:
            if not silent:
                print(Fore.RED + "✗ Timeout" + Style.RESET_ALL)
            return None
        except Exception as e:
            if not silent:
                print(Fore.RED + f"✗ Error: {str(e)[:30]}" + Style.RESET_ALL)
            return None

    def __del__(self):
        """Cleanup temporary directories."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except:
                pass

    def extract_dwg_data(self, dwg_path: str, silent: bool = False) -> Optional[Dict]:
        """
        Extract structured data from DWG file.
        
        Returns:
            Dict with keys: entities, layers, blocks, metadata, text_content
        """
        dxf_path = None
        
        try:
            # First try to read as DXF directly
            try:
                doc = ezdxf.readfile(dwg_path)
            except ezdxf.DXFError:
                # Not a DXF, try to convert from DWG
                if not silent:
                    print(Fore.YELLOW + "Converting..." + Style.RESET_ALL, end=' ')
                
                dxf_path = self._convert_dwg_to_dxf(dwg_path, silent=silent)
                if not dxf_path:
                    if not silent:
                        print(Fore.RED + "✗ Conversion failed" + Style.RESET_ALL)
                    return None
                
                doc = ezdxf.readfile(dxf_path)
            
            modelspace = doc.modelspace()
            
            # Extract entities
            entities = []
            text_elements = []
            layers_used = set()
            
            for entity in modelspace:
                if entity.dxftype() not in self.supported_entities:
                    continue
                
                entity_data = self._extract_entity_data(entity)
                if entity_data:
                    entities.append(entity_data)
                    layers_used.add(entity.dxf.layer)
                    
                    # Collect text content for semantic search
                    if entity.dxftype() in ['TEXT', 'MTEXT']:
                        text_elements.append(entity.dxf.text)
            
            # Extract blocks (component definitions)
            blocks = self._extract_blocks(doc)
            
            # Extract layers with properties
            layers = self._extract_layers(doc, layers_used)
            
            # Document metadata
            metadata = {
                'filename': os.path.basename(dwg_path),
                'filepath': os.path.abspath(dwg_path),
                'dxf_version': doc.dxfversion,
                'entity_count': len(entities),
                'layer_count': len(layers),
                'block_count': len(blocks)
            }
            
            # Concatenate all text for embedding
            text_content = ' '.join(text_elements) if text_elements else ''
            
            if not silent:
                print(Fore.GREEN + f"✓ {len(entities)} entities" + Style.RESET_ALL)
            
            return {
                'entities': entities,
                'layers': layers,
                'blocks': blocks,
                'metadata': metadata,
                'text_content': text_content
            }
            
        except ezdxf.DXFError as e:
            if not silent:
                print(Fore.RED + f"✗ Invalid file format: {str(e)[:50]}" + Style.RESET_ALL)
            return None
        except Exception as e:
            if not silent:
                print(Fore.RED + f"✗ Error: {str(e)[:50]}" + Style.RESET_ALL)
            return None
        finally:
            # Always cleanup temporary converted DXF file
            if dxf_path and os.path.exists(dxf_path):
                try:
                    os.remove(dxf_path)
                except:
                    pass

    def _extract_entity_data(self, entity) -> Optional[Dict]:
        """Extract relevant data from a single entity."""
        try:
            base_data = {
                'type': entity.dxftype(),
                'layer': entity.dxf.layer,
                'color': entity.dxf.color if hasattr(entity.dxf, 'color') else None,
            }
            
            # Entity-specific data extraction
            if entity.dxftype() == 'LINE':
                base_data.update({
                    'start': f"{entity.dxf.start.x:.2f},{entity.dxf.start.y:.2f}",
                    'end': f"{entity.dxf.end.x:.2f},{entity.dxf.end.y:.2f}",
                    'length': f"{entity.dxf.start.distance(entity.dxf.end):.2f}"
                })
            
            elif entity.dxftype() == 'CIRCLE':
                base_data.update({
                    'center': f"{entity.dxf.center.x:.2f},{entity.dxf.center.y:.2f}",
                    'radius': f"{entity.dxf.radius:.2f}",
                    'diameter': f"{entity.dxf.radius * 2:.2f}"
                })
            
            elif entity.dxftype() == 'ARC':
                base_data.update({
                    'center': f"{entity.dxf.center.x:.2f},{entity.dxf.center.y:.2f}",
                    'radius': f"{entity.dxf.radius:.2f}",
                    'start_angle': f"{entity.dxf.start_angle:.2f}",
                    'end_angle': f"{entity.dxf.end_angle:.2f}"
                })
            
            elif entity.dxftype() in ['TEXT', 'MTEXT']:
                base_data.update({
                    'text': entity.dxf.text,
                    'height': f"{entity.dxf.height:.2f}" if hasattr(entity.dxf, 'height') else None,
                    'position': f"{entity.dxf.insert.x:.2f},{entity.dxf.insert.y:.2f}" if hasattr(entity.dxf, 'insert') else None
                })
            
            elif entity.dxftype() == 'INSERT':  # Block reference
                base_data.update({
                    'block_name': entity.dxf.name,
                    'position': f"{entity.dxf.insert.x:.2f},{entity.dxf.insert.y:.2f}",
                    'scale': f"{entity.dxf.xscale:.2f},{entity.dxf.yscale:.2f}" if hasattr(entity.dxf, 'xscale') else None
                })
            
            elif entity.dxftype().startswith('DIMENSION'):
                base_data.update({
                    'measurement': f"{entity.get_measurement():.2f}" if hasattr(entity, 'get_measurement') else None,
                    'text': entity.dxf.text if hasattr(entity.dxf, 'text') else None
                })
            
            return base_data
            
        except Exception:
            return None
    
    def _extract_blocks(self, doc) -> List[Dict]:
        """Extract block definitions from document."""
        blocks = []
        for block in doc.blocks:
            if not block.name.startswith('*'):  # Skip model/paper space
                blocks.append({
                    'name': block.name,
                    'entity_count': len(list(block))
                })
        return blocks
    
    def _extract_layers(self, doc, used_layers: set) -> List[Dict]:
        """Extract layer information."""
        layers = []
        for layer_name in used_layers:
            if layer_name in doc.layers:
                layer = doc.layers.get(layer_name)
                layers.append({
                    'name': layer.dxf.name,
                    'color': layer.dxf.color,
                    'linetype': layer.dxf.linetype,
                    'on': not layer.is_off()
                })
        return layers
    
    def convert_to_csv(self, dwg_data: Dict, output_path: Optional[str] = None) -> str:
        """
        Convert extracted DWG data to CSV format.
        
        Args:
            dwg_data: Dictionary from extract_dwg_data()
            output_path: Optional file path to save CSV
            
        Returns:
            CSV content as string
        """
        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        
        # Write header
        writer.writerow(['Type', 'Layer', 'Color', 'Property', 'Value'])
        
        # Write entities
        for entity in dwg_data['entities']:
            entity_type = entity.pop('type')
            layer = entity.pop('layer')
            color = entity.pop('color', '')
            
            for key, value in entity.items():
                if value is not None:
                    writer.writerow([entity_type, layer, color, key, value])
        
        # Write layer info
        for layer in dwg_data['layers']:
            writer.writerow(['LAYER', layer['name'], layer['color'], 'linetype', layer['linetype']])
            writer.writerow(['LAYER', layer['name'], layer['color'], 'visible', layer['on']])
        
        # Write block info
        for block in dwg_data['blocks']:
            writer.writerow(['BLOCK', '', '', 'name', block['name']])
            writer.writerow(['BLOCK', '', '', 'entities', block['entity_count']])
        
        csv_content = csv_buffer.getvalue()
        
        # Save to file if path provided
        if output_path:
            try:
                with open(output_path, 'w', newline='') as f:
                    f.write(csv_content)
                print(Fore.GREEN + f"CSV saved to {output_path}" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"Error saving CSV: {e}" + Style.RESET_ALL)
        
        return csv_content
    def csv_to_natural_language(self, dwg_data: Dict) -> str:
        """
        Convert entity data to searchable natural language.
        Enhances embeddings with dimensional and structural information.
        """
        nl_descriptions = []
    
        # Count entities by type
        entity_counts = {}
        for entity in dwg_data['entities']:
            etype = entity['type']
            entity_counts[etype] = entity_counts.get(etype, 0) + 1
    
        # Describe counts in natural language
        for etype, count in sorted(entity_counts.items()):
            nl_descriptions.append(f"{count} {etype.lower()} elements")
    
        # Extract specific dimensions from circles
        circle_radii = []
        for entity in dwg_data['entities']:
            if entity['type'] == 'CIRCLE':
                radius = entity.get('radius', '').replace('f', '')
                try:
                    circle_radii.append(float(radius))
                except (ValueError, AttributeError):
                    pass
    
        if circle_radii:
            min_r = min(circle_radii)
            max_r = max(circle_radii)
            nl_descriptions.append(f"circles with radii from {min_r:.2f} to {max_r:.2f}")
    
        # Extract line lengths
        line_lengths = []
        for entity in dwg_data['entities']:
            if entity['type'] == 'LINE':
                length = entity.get('length', '').replace('f', '')
                try:
                    line_lengths.append(float(length))
                except (ValueError, AttributeError):
                    pass
    
        if line_lengths:
            min_l = min(line_lengths)
            max_l = max(line_lengths)
            nl_descriptions.append(f"lines ranging from {min_l:.2f} to {max_l:.2f} in length")
    
        # Extract text content (important labels, notes, dimensions)
        text_items = []
        for entity in dwg_data['entities']:
            if entity['type'] in ['TEXT', 'MTEXT']:
                text = entity.get('text', '')
                if text and len(text.strip()) > 0:
                    text_items.append(text.strip())
    
        if text_items:
            # Limit to first 5 text items to avoid overwhelming the description
            text_sample = ', '.join(text_items[:5])
            nl_descriptions.append(f"text labels: {text_sample}")
    
        # Layer information
        layers = dwg_data.get('layers', [])
        if layers:
            layer_names = [l['name'] for l in layers[:5]]
            nl_descriptions.append(f"layers: {', '.join(layer_names)}")
    
        # Block information (component references)
        blocks = dwg_data.get('blocks', [])
        if blocks:
            block_names = [b['name'] for b in blocks[:5]]
            nl_descriptions.append(f"components: {', '.join(block_names)}")
    
        return ". ".join(nl_descriptions) + "."
    
    def create_description(self, dwg_data: Dict) -> str:
        """Generate a natural language description of the DWG file using AI."""
        meta = dwg_data['metadata']
        entities = dwg_data['entities']
        
        # Count entity types
        entity_counts = {}
        for entity in entities:
            etype = entity['type']
            entity_counts[etype] = entity_counts.get(etype, 0) + 1
        
        # Build structured data for AI
        structured_summary = {
            'filename': meta['filename'],
            'total_entities': meta['entity_count'],
            'layers': [layer['name'] for layer in dwg_data['layers']],
            'entity_breakdown': entity_counts,
            'blocks': [block['name'] for block in dwg_data['blocks']],
            'text_content': dwg_data['text_content'][:500] if dwg_data['text_content'] else ''
        }
        
        # Try AI-powered description first
        ai_description = self._generate_ai_description(structured_summary, dwg_data)
        if ai_description:
            return ai_description
        
        # Fallback to template-based description
        desc_parts = [
            f"AutoCAD drawing: {meta['filename']}",
            f"Contains {meta['entity_count']} entities across {meta['layer_count']} layers"
        ]
        
        if entity_counts:
            entity_summary = ', '.join([f"{count} {etype}(s)" for etype, count in sorted(entity_counts.items())])
            desc_parts.append(f"Entities: {entity_summary}")
        
        if dwg_data['blocks']:
            block_names = ', '.join([b['name'] for b in dwg_data['blocks'][:5]])
            desc_parts.append(f"Blocks: {block_names}")
        
        if dwg_data['text_content']:
            desc_parts.append(f"Text content: {dwg_data['text_content'][:200]}")
        
        return '. '.join(desc_parts) + '.'
    
    def _generate_ai_description(self, summary: Dict, dwg_data: Dict) -> Optional[str]:
        """Use AI to generate intelligent description of DWG content."""
        prompt = f"""Analyze this AutoCAD DWG file and create a concise technical description (2-3 sentences).

File: {summary['filename']}
Entities: {summary['total_entities']} total
Breakdown: {json.dumps(summary['entity_breakdown'])}
Layers: {', '.join(summary['layers'][:10])}
Blocks: {', '.join(summary['blocks'][:10])}
Text Content: {summary['text_content']}

Provide a brief technical summary that describes:
1. What type of drawing this appears to be (e.g., floor plan, electrical schematic, mechanical part)
2. Key features or components
3. Any notable specifications or dimensions found in text

Keep it concise and technical."""

        # Try Grok first
        if grok_client:
            try:
                resp = grok_client.chat(
                    [{"role": "user", "content": prompt}],
                    model="grok-3-fast-beta"
                )
                if resp and "choices" in resp:
                    return resp["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
        
        # Fallback to OpenAI
        if openai_client:
            try:
                resp = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=200
                )
                return resp.choices[0].message.content.strip()
            except Exception:
                pass
        
        return None
    
    def extract_specs_with_ai(self, dwg_data: Dict) -> Dict:
        """Extract technical specifications using AI analysis."""
        # Prepare data for AI
        sample_entities = dwg_data['entities'][:50]  # Sample first 50 entities
        
        prompt = f"""Extract technical specifications from this AutoCAD DWG file data.

Filename: {dwg_data['metadata']['filename']}
Entity Count: {dwg_data['metadata']['entity_count']}
Layers: {', '.join([l['name'] for l in dwg_data['layers']])}

Sample Entities (first 50):
{json.dumps(sample_entities, indent=2)[:2000]}

Text Content:
{dwg_data['text_content'][:1000]}

Extract and return ONLY a JSON object with specifications like:
{{
  "drawing_type": "...",
  "scale": "...",
  "units": "...",
  "dimensions": [...],
  "materials": [...],
  "standards": [...],
  "notes": [...]
}}

Return ONLY valid JSON, no markdown formatting."""

        # Try Grok first
        if grok_client:
            try:
                resp = grok_client.chat(
                    [{"role": "user", "content": prompt}],
                    model="grok-3-fast-beta"
                )
                if resp and "choices" in resp:
                    result = resp["choices"][0]["message"]["content"].strip()
                    # Remove markdown code blocks if present
                    if result.startswith("```"):
                        result = '\n'.join([line for line in result.split('\n') 
                                          if not line.strip().startswith("```")])
                    return json.loads(result)
            except Exception:
                pass
        
        # Fallback to OpenAI
        if openai_client:
            try:
                resp = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=600
                )
                result = resp.choices[0].message.content.strip()
                # Remove markdown code blocks if present
                if result.startswith("```"):
                    result = '\n'.join([line for line in result.split('\n') 
                                      if not line.strip().startswith("```")])
                return json.loads(result)
            except Exception:
                pass
        
        return {}

    def add_to_database(self, dwg_path: str, silent: bool = False) -> bool:
        """
        Process DWG file and add to vector database.
        
        Args:
            dwg_path: Path to DWG file
            silent: Suppress output messages
            
        Returns:
            True if successful, False otherwise
        """
        try:
            filename = os.path.basename(dwg_path)
            
            # Check if already in database
            if file_exists_in_database(dwg_path):
                if not silent:
                    print(Fore.YELLOW + f"⚠ Already in DB" + Style.RESET_ALL)
                return True
            
            # Extract DWG data
            if not silent:
                print(Fore.BLUE + f"[{filename}] " + Style.RESET_ALL, end='')
            
            dwg_data = self.extract_dwg_data(dwg_path, silent=silent)
            if not dwg_data:
                return False
            
            # Convert to CSV
            csv_content = self.convert_to_csv(dwg_data)
            
            # Generate description for embedding
            description = self.create_description(dwg_data)
            
            # Extract specs using AI (only if not silent and entities found)
            ai_specs = {}
            if dwg_data['metadata']['entity_count'] > 0:
                ai_specs = self.extract_specs_with_ai(dwg_data)
            
            # Merge with metadata
            combined_specs = {**dwg_data['metadata'], **ai_specs}
            
            # Create unique ID
            embedding_id = generate_embedding_id(dwg_path)
            
            # Prepare metadata
            metadata = {
                'filename': filename,
                'filepath': os.path.abspath(dwg_path),
                'file_type': 'dwg',
                'description': description,
                'entity_count': dwg_data['metadata']['entity_count'],
                'layer_count': dwg_data['metadata']['layer_count'],
                'block_count': dwg_data['metadata']['block_count'],
                'csv_data': csv_content[:1000],  # Store first 1000 chars of CSV
                'specs': json.dumps(combined_specs),
                'ai_analyzed': bool(ai_specs)  # Flag if AI analysis was successful
            }
            
            # Generate natural language from CSV entity data
            nl_from_entities = self.csv_to_natural_language(dwg_data)

            # Combine everything for rich embeddings
            searchable_text = f"{description} {nl_from_entities} {dwg_data['text_content']}"

            collection.add(
                ids=[embedding_id],
                documents=[searchable_text],
                metadatas=[metadata]
            )
            
            if not silent:
                print(Fore.GREEN + f"✓ Added to DB" + Style.RESET_ALL)
            
            return True
            
        except Exception as e:
            if not silent:
                print(Fore.RED + f"✗ Failed: {str(e)[:30]}" + Style.RESET_ALL)
            return False
    
    def get_from_database(self, filename_or_path: str) -> Optional[Dict]:
        """
        Retrieve DWG data from database.
        
        Returns:
            Dict with filename, filepath, description, csv_data, specs
        """
        try:
            abs_path = filename_or_path if os.path.isabs(filename_or_path) else filename_or_path
            embedding_id = generate_embedding_id(abs_path)
            
            results = collection.get(ids=[embedding_id])
            
            if results and results.get("ids"):
                meta = results.get("metadatas", [{}])[0] or {}
                
                return {
                    'filename': meta.get('filename', os.path.basename(filename_or_path)),
                    'filepath': meta.get('filepath', filename_or_path),
                    'description': results.get('documents', [''])[0],
                    'csv_data': meta.get('csv_data', ''),
                    'entity_count': meta.get('entity_count', 0),
                    'layer_count': meta.get('layer_count', 0),
                    'block_count': meta.get('block_count', 0),
                    'specs': json.loads(meta.get('specs', '{}'))
                }
        except Exception as e:
            print(Fore.RED + f"Error retrieving DWG {filename_or_path}: {e}" + Style.RESET_ALL)
        
        return None


# Convenience functions for easy integration
def find_dwg_files(directory: str, silent: bool = False) -> List[str]:
    """
    Recursively find all DWG files in a directory.
    
    Args:
        directory: Root directory to search
        silent: Suppress output
        
    Returns:
        List of absolute paths to DWG files
    """
    dwg_files = []
    
    try:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.dwg'):
                    full_path = os.path.join(root, file)
                    dwg_files.append(full_path)
        
        if not silent and dwg_files:
            print(Fore.GREEN + f"Found {len(dwg_files)} DWG files" + Style.RESET_ALL)
        
        return dwg_files
        
    except Exception as e:
        if not silent:
            print(Fore.RED + f"Error scanning directory: {e}" + Style.RESET_ALL)
        return []


def process_dwg_file(dwg_path: str, silent: bool = False) -> bool:
    """Process a single DWG file and add to database."""
    processor = DWGProcessor()
    return processor.add_to_database(dwg_path, silent=silent)


def batch_process_dwg_folder(folder_path: str, silent: bool = False) -> Tuple[int, int]:
    """
    Process all DWG files in a folder.
    
    Returns:
        Tuple of (success_count, failure_count)
    """
    processor = DWGProcessor()
    dwg_files = []
    
    # Find all DWG files
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith('.dwg'):
                dwg_files.append(os.path.join(root, file))
    
    if not dwg_files:
        print(Fore.YELLOW + "No DWG files found" + Style.RESET_ALL)
        return 0, 0
    
    print(Fore.CYAN + f"Found {len(dwg_files)} DWG files\n" + Style.RESET_ALL)
    
    if not DWG_CONVERSION_AVAILABLE:
        print(Fore.YELLOW + "⚠ ODA File Converter not found - only DXF files will process" + Style.RESET_ALL)
        print(Fore.YELLOW + "  Download from: https://www.opendesign.com/guestfiles/oda_file_converter\n" + Style.RESET_ALL)
    
    success = 0
    failed = 0
    skipped = 0
    
    for idx, dwg_path in enumerate(dwg_files, 1):
        # Check if already in DB
        if file_exists_in_database(dwg_path):
            skipped += 1
            continue
        
        # Show minimal progress
        print(f"[{idx}/{len(dwg_files)}] ", end='')
        
        if processor.add_to_database(dwg_path, silent=False):
            success += 1
        else:
            failed += 1
    
    # Summary
    print(Fore.CYAN + f"\n{'='*60}" + Style.RESET_ALL)
    print(Fore.GREEN + f"✓ Success: {success}" + Style.RESET_ALL)
    if failed > 0:
        print(Fore.RED + f"✗ Failed: {failed}" + Style.RESET_ALL)
    if skipped > 0:
        print(Fore.YELLOW + f"⊘ Skipped (in DB): {skipped}" + Style.RESET_ALL)
    print(Fore.CYAN + f"{'='*60}" + Style.RESET_ALL)
    
    return success, failed


def export_dwg_to_csv(dwg_path: str, output_csv_path: Optional[str] = None) -> bool:
    """
    Export a DWG file to CSV format.
    
    Args:
        dwg_path: Path to DWG file
        output_csv_path: Where to save CSV
        
    Returns:
        True if successful
    """
    if not os.path.exists(dwg_path):
        print(Fore.RED + f"✗ File not found: {dwg_path}" + Style.RESET_ALL)
        return False
    
    processor = DWGProcessor()
    
    print(Fore.CYAN + f"Processing: {os.path.basename(dwg_path)}" + Style.RESET_ALL)
    
    data = processor.extract_dwg_data(dwg_path, silent=False)
    
    if not data:
        print(Fore.RED + "✗ Failed to extract data from DWG" + Style.RESET_ALL)
        return False
    
    # Generate output path if not provided
    if not output_csv_path:
        output_csv_path = f"{os.path.splitext(dwg_path)[0]}_export.csv"
    
    processor.convert_to_csv(data, output_csv_path)
    return True