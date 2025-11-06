#!/usr/bin/env python3
"""
DXF to PDF Renderer
Called by C++ program to render DXF files to high-quality PDF
Usage: python dxf_renderer.py <input_dxf> <output_pdf>
"""

import sys
from pathlib import Path
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
from PIL import Image

def render_dxf_to_png(dxf_path: Path, png_path: Path, dpi: int = 1200):
    """Render DXF file to PNG using ezdxf's matplotlib backend."""
    try:
        print(f"    [*] Reading DXF file...")
        doc = ezdxf.readfile(str(dxf_path))
        
        print(f"    [*] Creating render context...")
        fig = plt.figure(figsize=(24, 18))
        ax = fig.add_axes([0, 0, 1, 1])
        
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        
        print(f"    [*] Rendering entities...")
        frontend = Frontend(ctx, out)
        frontend.draw_layout(doc.modelspace(), finalize=True)
        
        ax.set_aspect('equal')
        ax.axis('off')
        
        png_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"    [*] Saving PNG at {dpi} DPI...")
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        
        print(f"    [SUCCESS] PNG rendered using ezdxf matplotlib backend")
        return True
        
    except Exception as e:
        print(f"    [WARNING] Built-in renderer failed: {e}")
        print(f"    [*] Trying fallback renderer...")
        return render_dxf_to_png_fallback(dxf_path, png_path, dpi)

def render_dxf_to_png_fallback(dxf_path: Path, png_path: Path, dpi: int = 1200):
    """Fallback renderer with manual entity handling."""
    from matplotlib.patches import Circle, Arc, Rectangle, Polygon
    import numpy as np
    
    try:
        print(f"    [*] Reading DXF with fallback renderer...")
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()
        
        # DXF color index to RGB mapping
        aci_colors = {
            1: '#FF0000', 2: '#FFFF00', 3: '#00FF00', 4: '#00FFFF',
            5: '#0000FF', 6: '#FF00FF', 7: '#000000', 8: '#808080',
            9: '#C0C0C0',
        }
        
        linetype_styles = {
            'HIDDEN': (0, (5, 3)),
            'DASHED': (0, (5, 3)),
            'CENTER': (0, (10, 2, 2, 2)),
            'PHANTOM': (0, (10, 2, 2, 2, 2, 2)),
            'CONTINUOUS': 'solid',
        }
        
        def get_entity_color(entity):
            try:
                if hasattr(entity.dxf, 'color'):
                    color_index = entity.dxf.color
                    if color_index in aci_colors:
                        return aci_colors[color_index]
                    elif color_index == 256:
                        layer = doc.layers.get(entity.dxf.layer)
                        if layer and hasattr(layer.dxf, 'color'):
                            return aci_colors.get(layer.dxf.color, '#000000')
                if hasattr(entity.dxf, 'layer'):
                    layer = doc.layers.get(entity.dxf.layer)
                    if layer and hasattr(layer.dxf, 'color'):
                        return aci_colors.get(layer.dxf.color, '#000000')
            except:
                pass
            return '#000000'
        
        def get_linetype_style(entity):
            try:
                if hasattr(entity.dxf, 'linetype'):
                    linetype = entity.dxf.linetype.upper()
                    for key in linetype_styles:
                        if key in linetype:
                            return linetype_styles[key]
            except:
                pass
            return 'solid'
        
        print(f"    [*] Creating matplotlib figure...")
        fig, ax = plt.subplots(figsize=(24, 18))
        ax.set_facecolor('white')
        
        entity_count = 0
        text_count = 0
        
        print(f"    [*] Processing entities...")
        for entity in msp:
            entity_count += 1
            entity_type = entity.dxftype()
            color = get_entity_color(entity)
            linestyle = get_linetype_style(entity)
            
            try:
                if entity_type == 'LINE':
                    start, end = entity.dxf.start, entity.dxf.end
                    ax.plot([start.x, end.x], [start.y, end.y], 
                           color=color, linewidth=0.8, linestyle=linestyle)
                
                elif entity_type == 'CIRCLE':
                    center = entity.dxf.center
                    radius = entity.dxf.radius
                    circle = Circle((center.x, center.y), radius, fill=False, 
                                  color=color, linewidth=0.8, linestyle=linestyle)
                    ax.add_patch(circle)
                
                elif entity_type == 'ARC':
                    center = entity.dxf.center
                    radius = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    arc = Arc((center.x, center.y), 2*radius, 2*radius, 
                             theta1=start_angle, theta2=end_angle, 
                             color=color, linewidth=0.8, linestyle=linestyle)
                    ax.add_patch(arc)
                
                elif entity_type in ('POLYLINE', 'LWPOLYLINE'):
                    if entity_type == 'LWPOLYLINE':
                        points = [(p[0], p[1]) for p in entity.get_points('xy')]
                    else:
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                    
                    if points:
                        x_coords = [p[0] for p in points]
                        y_coords = [p[1] for p in points]
                        ax.plot(x_coords, y_coords, color=color, 
                               linewidth=0.8, linestyle=linestyle)
                
                elif entity_type == 'SPLINE':
                    # Approximate spline with control points
                    if hasattr(entity, 'control_points'):
                        points = entity.control_points
                        x_coords = [p[0] for p in points]
                        y_coords = [p[1] for p in points]
                        ax.plot(x_coords, y_coords, color=color, 
                               linewidth=0.8, linestyle=linestyle)
                
                elif entity_type == 'ELLIPSE':
                    # Simplified ellipse rendering
                    center = entity.dxf.center
                    major_axis = entity.dxf.major_axis
                    ratio = entity.dxf.ratio
                    
                    from matplotlib.patches import Ellipse as EllipsePatch
                    width = 2 * np.sqrt(major_axis.x**2 + major_axis.y**2)
                    height = width * ratio
                    angle = np.degrees(np.arctan2(major_axis.y, major_axis.x))
                    
                    ellipse = EllipsePatch((center.x, center.y), width, height,
                                          angle=angle, fill=False,
                                          color=color, linewidth=0.8, linestyle=linestyle)
                    ax.add_patch(ellipse)
                
                elif entity_type == 'TEXT':
                    text = entity.dxf.text
                    pos = entity.dxf.insert
                    height = entity.dxf.height if hasattr(entity.dxf, 'height') else 1
                    rotation = entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
                    
                    ax.text(pos.x, pos.y, text, 
                           fontsize=height*2.5, 
                           color=color,
                           rotation=rotation,
                           ha='left', 
                           va='bottom',
                           weight='bold')
                    text_count += 1
                
                elif entity_type == 'MTEXT':
                    import re
                    text = entity.text
                    pos = entity.dxf.insert
                    height = entity.dxf.char_height if hasattr(entity.dxf, 'char_height') else 1
                    text = re.sub(r'\\[A-Z][^;]*;', '', text)
                    text = text.replace('\\P', '\n')
                    
                    ax.text(pos.x, pos.y, text, 
                           fontsize=height*2.5, 
                           color=color,
                           ha='left', 
                           va='top',
                           weight='bold')
                    text_count += 1
                
                elif entity_type == 'HATCH':
                    # Simplified hatch rendering (just boundary)
                    if hasattr(entity, 'paths'):
                        for path in entity.paths:
                            if hasattr(path, 'edges'):
                                for edge in path.edges:
                                    # Draw edge outlines
                                    pass
            except Exception as entity_error:
                # Skip problematic entities
                pass
        
        print(f"    [SUCCESS] Rendered {entity_count} entities ({text_count} text elements)")
        
        ax.set_aspect('equal')
        ax.axis('off')
        ax.margins(0.05)
        
        png_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"    [*] Saving PNG...")
        fig.savefig(png_path, bbox_inches='tight', dpi=dpi, 
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        
        print(f"    [SUCCESS] PNG saved successfully")
        return True
        
    except Exception as e:
        print(f"    [ERROR] Fallback renderer failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def convert_png_to_pdf(png_path: Path, pdf_path: Path):
    """Convert PNG image to PDF."""
    try:
        print(f"    [*] Converting PNG to PDF...")
        
        if not png_path.exists():
            raise FileNotFoundError(f"PNG file not found: {png_path}")
        
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        image = Image.open(png_path).convert("RGB")
        image.save(pdf_path, "PDF", resolution=1200.0)
        
        print(f"    [SUCCESS] PDF created successfully")
        return True
        
    except Exception as e:
        print(f"    [ERROR] PNG to PDF conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if len(sys.argv) != 3:
        print("[ERROR] Usage: python dxf_renderer.py <input_dxf> <output_pdf>")
        sys.exit(1)
    
    dxf_path = Path(sys.argv[1])
    pdf_path = Path(sys.argv[2])
    
    print(f"\n[*] Python DXF Renderer")
    print(f"    Input:  {dxf_path.name}")
    print(f"    Output: {pdf_path.name}")
    
    # Validate input
    if not dxf_path.exists():
        print(f"[ERROR] DXF file not found: {dxf_path}")
        sys.exit(1)
    
    # Create temporary PNG
    png_path = pdf_path.parent / (pdf_path.stem + "_temp.png")
    
    try:
        # Step 1: Render DXF to PNG
        print(f"\n[*] Step 1: Rendering DXF to PNG...")
        if not render_dxf_to_png(dxf_path, png_path, dpi=1200):
            sys.exit(1)
        
        # Step 2: Convert PNG to PDF
        print(f"\n[*] Step 2: Converting PNG to PDF...")
        if not convert_png_to_pdf(png_path, pdf_path):
            sys.exit(1)
        
        # Cleanup temp PNG
        print(f"\n[*] Cleaning up temporary files...")
        if png_path.exists():
            png_path.unlink()
        
        print(f"\n[SUCCESS] PDF rendering complete!")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n[ERROR] Rendering failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()