# api_server.py
#**************************************************************************************************
#   FastAPI REST API Server for AutoCAD Drawing Processing System
#   Provides endpoints for file upload, processing, search, and retrieval
#**************************************************************************************************
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import os
import tempfile
import shutil
from pathlib import Path

from colorama import init, Fore, Style
init(autoreset=True)

# Import our modules
from config import API_HOST, API_PORT, API_CORS_ORIGINS, MAX_FILE_SIZE_MB
from DWG_Processor import DWGProcessor, find_dwg_files, batch_process_dwg_folder
from PDF_Analyzer import process_pdf, find_pdf
from semanticMemory import (
    search_similar_files, list_database_files, get_from_database,
    remove_from_database, get_database_stats, file_exists_in_database
)
from utils import chat_with_ai

#==================================================================================================
# FASTAPI APP INITIALIZATION
#==================================================================================================
app = FastAPI(
    title="AutoCAD Drawing Processing API",
    description="REST API for processing, storing, and querying AutoCAD drawings (DWG/PDF)",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#==================================================================================================
# PYDANTIC MODELS
#==================================================================================================
class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    file_type: Optional[str] = None  # 'pdf', 'dwg', or None for all

class QuestionRequest(BaseModel):
    filename: str
    question: str

class ProcessResponse(BaseModel):
    success: bool
    filename: str
    message: str
    file_type: Optional[str] = None
    entity_count: Optional[int] = None
    description: Optional[str] = None

#==================================================================================================
# HELPER FUNCTIONS
#==================================================================================================
def save_upload_file(upload_file: UploadFile) -> str:
    """Save uploaded file to temporary location."""
    try:
        suffix = Path(upload_file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(upload_file.file, tmp)
            return tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

def check_file_size(file: UploadFile):
    """Check if file size is within limits."""
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()  # Get position (size)
    file.file.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB"
        )

#==================================================================================================
# API ENDPOINTS
#==================================================================================================

@app.get("/")
async def root():
    """API health check."""
    return {
        "status": "online",
        "message": "AutoCAD Drawing Processing API",
        "version": "1.0.0"
    }

@app.get("/api/stats")
async def get_stats():
    """Get database statistics."""
    stats = get_database_stats()
    return stats

@app.post("/api/upload/dwg", response_model=ProcessResponse)
async def upload_dwg(file: UploadFile = File(...)):
    """Upload and process a DWG file."""
    check_file_size(file)
    
    if not file.filename.lower().endswith(('.dwg', '.dxf')):
        raise HTTPException(status_code=400, detail="Only DWG/DXF files are supported")
    
    temp_path = save_upload_file(file)
    
    try:
        # Check if already in database
        if file_exists_in_database(temp_path):
            os.unlink(temp_path)
            return ProcessResponse(
                success=True,
                filename=file.filename,
                message="File already exists in database",
                file_type="dwg"
            )
        
        # Process DWG
        processor = DWGProcessor()
        success = processor.add_to_database(temp_path, silent=True)
        
        if success:
            # Get the processed data
            data = get_from_database(temp_path)
            return ProcessResponse(
                success=True,
                filename=file.filename,
                message="DWG file processed successfully",
                file_type="dwg",
                entity_count=data.get('entity_count') if data else None,
                description=data.get('description') if data else None
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to process DWG file")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

@app.post("/api/upload/pdf", response_model=ProcessResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """Upload and process a PDF file."""
    check_file_size(file)
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    temp_path = save_upload_file(file)
    
    try:
        # Check if already in database
        if file_exists_in_database(temp_path):
            os.unlink(temp_path)
            return ProcessResponse(
                success=True,
                filename=file.filename,
                message="File already exists in database",
                file_type="pdf"
            )
        
        # Process PDF
        success = process_pdf(temp_path, silent=True)
        
        if success:
            # Get the processed data
            data = get_from_database(temp_path)
            return ProcessResponse(
                success=True,
                filename=file.filename,
                message="PDF file processed successfully",
                file_type="pdf",
                description=data.get('description') if data else None
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to process PDF file or not an AutoCAD drawing")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

@app.post("/api/search")
async def search_drawings(request: SearchRequest):
    """Search for drawings using semantic similarity."""
    try:
        results = search_similar_files(
            query=request.query,
            n_results=request.n_results,
            file_type=request.file_type
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files")
async def list_files():
    """List all files in the database."""
    try:
        files = list_database_files()
        formatted_files = []
        for filepath, description, specs_json in files:
            formatted_files.append({
                "filepath": filepath,
                "filename": os.path.basename(filepath),
                "description": description,
                "file_type": "dwg" if filepath.lower().endswith('.dwg') else "pdf"
            })
        return {"files": formatted_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/file/{filename:path}")
async def get_file_details(filename: str):
    """Get detailed information about a specific file."""
    try:
        data = get_from_database(filename)
        if not data:
            raise HTTPException(status_code=404, detail="File not found in database")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/file/{filename:path}")
async def delete_file(filename: str):
    """Remove a file from the database."""
    try:
        success = remove_from_database(filename)
        if success:
            return {"success": True, "message": "File removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/question")
async def ask_question(request: QuestionRequest):
    """Ask a question about a specific drawing."""
    try:
        # Get file data from database
        data = get_from_database(request.filename)
        if not data:
            raise HTTPException(status_code=404, detail="File not found in database")
        
        # Import answer_question function
        from PDF_Analyzer import answer_question
        
        answer = answer_question(
            question=request.question,
            text=data.get('description', ''),
            specs=data.get('specs'),
            description=data.get('description', ''),
            silent=True
        )
        
        return {
            "question": request.question,
            "answer": answer,
            "filename": request.filename
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/batch/process")
async def batch_process_folder(folder_path: str = Query(...)):
    """Process all DWG and PDF files in a folder."""
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=404, detail="Folder not found")
    
    try:
        # Process DWG files
        dwg_success, dwg_failed = batch_process_dwg_folder(folder_path, silent=True)
        
        # Process PDF files
        pdf_files = find_pdf(list_all=False, root=folder_path)
        pdf_success = sum(1 for pdf in pdf_files if process_pdf(pdf, silent=True))
        pdf_failed = len(pdf_files) - pdf_success
        
        return {
            "dwg_processed": dwg_success,
            "dwg_failed": dwg_failed,
            "pdf_processed": pdf_success,
            "pdf_failed": pdf_failed,
            "total_processed": dwg_success + pdf_success,
            "total_failed": dwg_failed + pdf_failed
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#==================================================================================================
# SERVER STARTUP
#==================================================================================================
if __name__ == "__main__":
    import uvicorn
    
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    print(Fore.GREEN + "🚀 Starting AutoCAD Drawing Processing API Server" + Style.RESET_ALL)
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    print(f"📡 Server: http://{API_HOST}:{API_PORT}")
    print(f"📚 Docs: http://{API_HOST}:{API_PORT}/docs")
    print(f"🔍 Redoc: http://{API_HOST}:{API_PORT}/redoc")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    
    uvicorn.run(
        "api_server:app",
        host=API_HOST,
        port=API_PORT,
        reload=True
    )
