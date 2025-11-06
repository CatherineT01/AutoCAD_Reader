// Dwg_to_hybrid.cpp
#include <iostream>
#include <filesystem>
#include <vector>
#include <string>
#include <windows.h>
#include <algorithm>
#include <map>

namespace fs = std::filesystem;

// ANSI color codes for Windows
void enableVirtualTerminal() {
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD dwMode = 0;
    GetConsoleMode(hOut, &dwMode);
    dwMode |= ENABLE_VIRTUAL_TERMINAL_PROCESSING;
    SetConsoleMode(hOut, dwMode);
}

class DWGConverter {
private:
    fs::path oda_converter_path;
    fs::path python_renderer_path;
    fs::path output_dxf_dir;
    fs::path output_pdf_dir;
    std::vector<fs::path> all_dwg_files;

    // Get all available drives
    std::vector<std::string> getAvailableDrives() {
        std::vector<std::string> drives;
        DWORD drives_mask = GetLogicalDrives();

        for (char drive = 'A'; drive <= 'Z'; ++drive) {
            if (drives_mask & 1) {
                std::string drive_path = std::string(1, drive) + ":\\";
                UINT drive_type = GetDriveTypeA(drive_path.c_str());

                if (drive_type == DRIVE_FIXED || drive_type == DRIVE_REMOVABLE) {
                    DWORD sectors_per_cluster, bytes_per_sector, free_clusters, total_clusters;
                    if (GetDiskFreeSpaceA(drive_path.c_str(), &sectors_per_cluster,
                        &bytes_per_sector, &free_clusters, &total_clusters)) {
                        drives.push_back(drive_path);
                    }
                }
            }
            drives_mask >>= 1;
        }

        return drives;
    }

    // Search for ODA File Converter
    bool findODAConverter() {
        std::cout << "\n[*] Searching for ODA File Converter...\n";

        fs::path exe_dir = fs::current_path();
        fs::path parent_dir = exe_dir.parent_path();

        std::cout << "    [*] Quick check in parent directory...\n";

        // Check grandparent directory
        if (parent_dir.has_parent_path()) {
            fs::path grandparent = parent_dir.parent_path();
            fs::path oda_in_grandparent = grandparent / "ODAFileConverter.exe";

            if (fs::exists(oda_in_grandparent)) {
                oda_converter_path = oda_in_grandparent;
                std::cout << "    [SUCCESS] Found ODA Converter: " << oda_converter_path << "\n";
                return true;
            }
        }

        // Check parent directory
        fs::path oda_in_parent = parent_dir / "ODAFileConverter.exe";
        if (fs::exists(oda_in_parent)) {
            oda_converter_path = oda_in_parent;
            std::cout << "    [SUCCESS] Found ODA Converter: " << oda_converter_path << "\n";
            return true;
        }

        // Check current directory
        fs::path oda_in_current = exe_dir / "ODAFileConverter.exe";
        if (fs::exists(oda_in_current)) {
            oda_converter_path = oda_in_current;
            std::cout << "    [SUCCESS] Found ODA Converter: " << oda_converter_path << "\n";
            return true;
        }

        std::cout << "    [*] Not found nearby, searching all drives...\n";
        auto drives = getAvailableDrives();

        for (const auto& drive : drives) {
            std::cout << "    [*] Searching " << drive << "...\r" << std::flush;

            try {
                for (const auto& entry : fs::recursive_directory_iterator(
                    drive,
                    fs::directory_options::skip_permission_denied)) {

                    if (entry.is_regular_file() &&
                        entry.path().filename() == "ODAFileConverter.exe") {

                        fs::path parent = entry.path().parent_path();
                        bool has_dlls = fs::exists(parent / "TD_Db.dll") ||
                            fs::exists(parent / "TG_Db.dll") ||
                            fs::exists(parent / "TD_Root.dll");

                        if (has_dlls) {
                            oda_converter_path = entry.path();
                            std::cout << "\n    [SUCCESS] Found ODA Converter: " << oda_converter_path << "\n";
                            return true;
                        }
                    }
                }
            }
            catch (const fs::filesystem_error&) {
                continue;
            }
        }

        return false;
    }

    // Find Python renderer script
    bool findPythonRenderer() {
        std::cout << "\n[*] Searching for Python renderer...\n";

        fs::path exe_dir = fs::current_path();

        // Check current directory
        fs::path renderer_in_current = exe_dir / "dxf_renderer.py";
        if (fs::exists(renderer_in_current)) {
            python_renderer_path = renderer_in_current;
            std::cout << "    [SUCCESS] Found Python renderer: " << python_renderer_path << "\n";
            return true;
        }

        // Check parent directory
        fs::path parent = exe_dir.parent_path();
        fs::path renderer_in_parent = parent / "dxf_renderer.py";
        if (fs::exists(renderer_in_parent)) {
            python_renderer_path = renderer_in_parent;
            std::cout << "    [SUCCESS] Found Python renderer: " << python_renderer_path << "\n";
            return true;
        }

        std::cout << "    [ERROR] Python renderer not found!\n";
        std::cout << "    Expected: " << renderer_in_current << "\n";
        return false;
    }

    // Search for DWG files
    void findAllDWGFiles() {
        std::cout << "\n[*] Searching for DWG files...\n";

        auto drives = getAvailableDrives();
        all_dwg_files.clear();

        int total_found = 0;

        for (const auto& drive : drives) {
            std::cout << "    [*] Scanning " << drive << "..." << std::flush;
            int count = searchDWGInDrive(drive);
            total_found += count;
            std::cout << "\r    [+] " << drive << " - Found " << count << " DWG file(s)\n";
        }

        std::sort(all_dwg_files.begin(), all_dwg_files.end(),
            [](const fs::path& a, const fs::path& b) {
                return a.filename() < b.filename();
            });

        std::cout << "\n[INFO] Total DWG files found: " << total_found << "\n";
    }

    int searchDWGInDrive(const std::string& drive) {
        int count = 0;

        try {
            std::vector<std::string> skip_folders = {
                "Windows", "ProgramData", "$Recycle.Bin",
                "System Volume Information", "Recovery"
            };

            for (const auto& entry : fs::recursive_directory_iterator(
                drive,
                fs::directory_options::skip_permission_denied)) {

                std::string folder_name = entry.path().filename().string();
                bool should_skip = false;
                for (const auto& skip : skip_folders) {
                    if (folder_name == skip) {
                        should_skip = true;
                        break;
                    }
                }
                if (should_skip) continue;

                if (entry.is_regular_file() &&
                    entry.path().extension() == ".dwg") {
                    all_dwg_files.push_back(entry.path());
                    count++;
                }
            }
        }
        catch (const fs::filesystem_error&) {
        }

        return count;
    }

    void displayDWGFiles() {
        if (all_dwg_files.empty()) {
            std::cout << "\n[ERROR] No DWG files found.\n";
            return;
        }

        std::map<fs::path, std::vector<fs::path>> grouped;
        for (const auto& file : all_dwg_files) {
            grouped[file.parent_path()].push_back(file);
        }

        std::cout << "\n[FILES] DWG Files by Directory:\n";
        std::cout << "==================================================\n";

        int file_num = 1;
        for (const auto& [dir, files] : grouped) {
            std::cout << "\n[DIR] " << dir << "\n";
            for (const auto& file : files) {
                std::cout << "   " << file_num << ". " << file.filename() << "\n";
                file_num++;
            }
        }
        std::cout << "\n";
    }

    // Convert DWG to DXF using ODA
    bool convertDWGtoDXF(const fs::path& dwg_file, fs::path& output_dxf) {
        std::cout << "\n[STEP 1] Converting DWG to DXF...\n";
        std::cout << "    File: " << dwg_file.filename() << "\n";

        // Create output directory
        output_dxf_dir = dwg_file.parent_path() / "convertedDXF";
        fs::create_directories(output_dxf_dir);

        // Build ODA command
        std::wstring cmd = L"\"" + oda_converter_path.wstring() + L"\" ";
        cmd += L"\"" + dwg_file.parent_path().wstring() + L"\" ";
        cmd += L"\"" + output_dxf_dir.wstring() + L"\" ";
        cmd += L"ACAD2010 DXF 0 1 ";
        cmd += L"\"" + dwg_file.filename().wstring() + L"\"";

        std::cout << "    [*] Running ODA converter...\n";

        STARTUPINFOW si = { sizeof(si) };
        PROCESS_INFORMATION pi;
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;

        if (!CreateProcessW(
            NULL,
            const_cast<LPWSTR>(cmd.c_str()),
            NULL, NULL, FALSE,
            0, NULL, oda_converter_path.parent_path().wstring().c_str(), &si, &pi)) {
            std::cerr << "    [ERROR] Failed to start ODA converter\n";
            return false;
        }

        WaitForSingleObject(pi.hProcess, 120000); // 2 min timeout

        DWORD exit_code;
        GetExitCodeProcess(pi.hProcess, &exit_code);

        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);

        output_dxf = output_dxf_dir / (dwg_file.stem().string() + ".dxf");

        if (fs::exists(output_dxf)) {
            std::cout << "    [SUCCESS] DXF created: " << output_dxf.filename() << "\n";
            std::cout << "    Size: " << fs::file_size(output_dxf) / 1024 << " KB\n";
            return true;
        }

        std::cerr << "    [ERROR] DXF file not created (exit code: " << exit_code << ")\n";
        return false;
    }

    // Call Python renderer
    bool renderDXFtoPDF(const fs::path& dxf_file, const fs::path& dwg_file) {
        std::cout << "\n[STEP 2] Rendering DXF to PDF using Python...\n";

        // Create PDF output directory
        output_pdf_dir = dwg_file.parent_path() / "convertedPDF";
        fs::create_directories(output_pdf_dir);

        fs::path output_pdf = output_pdf_dir / (dwg_file.stem().string() + ".pdf");

        // Build Python command
        std::wstring cmd = L"python \"";
        cmd += python_renderer_path.wstring();
        cmd += L"\" \"";
        cmd += dxf_file.wstring();
        cmd += L"\" \"";
        cmd += output_pdf.wstring();
        cmd += L"\"";

        std::cout << "    [*] Running Python renderer...\n";

        STARTUPINFOW si = { sizeof(si) };
        PROCESS_INFORMATION pi;
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_NORMAL; // Show Python output

        if (!CreateProcessW(
            NULL,
            const_cast<LPWSTR>(cmd.c_str()),
            NULL, NULL, FALSE,
            0, NULL, NULL, &si, &pi)) {
            std::cerr << "    [ERROR] Failed to start Python renderer\n";
            std::cerr << "    Make sure Python is installed and in PATH\n";
            return false;
        }

        WaitForSingleObject(pi.hProcess, 300000); // 5 min timeout

        DWORD exit_code;
        GetExitCodeProcess(pi.hProcess, &exit_code);

        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);

        if (exit_code == 0 && fs::exists(output_pdf)) {
            std::cout << "    [SUCCESS] PDF created: " << output_pdf.filename() << "\n";
            std::cout << "    Location: " << output_pdf << "\n";
            std::cout << "    Size: " << fs::file_size(output_pdf) / 1024 << " KB\n";
            return true;
        }

        std::cerr << "    [ERROR] PDF rendering failed (exit code: " << exit_code << ")\n";
        return false;
    }

public:
    DWGConverter() {}

    bool run() {
        enableVirtualTerminal();

        std::cout << "\n";
        std::cout << "========================================\n";
        std::cout << "  DWG to PDF Converter (C++ + Python)\n";
        std::cout << "========================================\n";

        // Step 1: Find ODA Converter
        if (!findODAConverter()) {
            std::cerr << "\n[ERROR] ODA File Converter not found!\n";
            return false;
        }

        // Step 2: Find Python renderer
        if (!findPythonRenderer()) {
            std::cerr << "\n[ERROR] Python renderer not found!\n";
            std::cerr << "Please ensure dxf_renderer.py is in the same directory.\n";
            return false;
        }

        // Step 3: Find DWG files
        findAllDWGFiles();

        if (all_dwg_files.empty()) {
            return false;
        }

        // Step 4: Display files
        displayDWGFiles();

        // Step 5: Get user selection
        std::cout << "[INPUT] Enter file number to convert (or 0 to exit): ";
        int choice;
        std::cin >> choice;

        if (choice <= 0 || choice > all_dwg_files.size()) {
            std::cout << "\n[ERROR] Invalid selection.\n";
            return false;
        }

        // Step 6: Process conversion
        fs::path selected_file = all_dwg_files[choice - 1];

        std::cout << "\n========================================\n";
        std::cout << "Processing: " << selected_file.filename() << "\n";
        std::cout << "========================================\n";

        // Convert DWG to DXF
        fs::path dxf_file;
        if (!convertDWGtoDXF(selected_file, dxf_file)) {
            return false;
        }

        // Render DXF to PDF
        if (!renderDXFtoPDF(dxf_file, selected_file)) {
            return false;
        }

        return true;
    }
};

int main() {
    DWGConverter converter;

    if (converter.run()) {
        std::cout << "\n========================================\n";
        std::cout << "[SUCCESS] Conversion complete!\n";
        std::cout << "========================================\n";
    }
    else {
        std::cout << "\n[INFO] Conversion failed or cancelled.\n";
    }

    std::cout << "\nPress any key to exit...";
    std::cin.ignore();
    std::cin.get();

    return 0;
}