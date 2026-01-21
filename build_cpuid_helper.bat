@echo off
REM Build script for cpuid_helper.exe on Windows
REM Requirements: Microsoft Visual C++ Build Tools or Visual Studio

echo Building cpuid_helper.exe...

REM Try to use MSVC compiler if available
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
    cl.exe /O2 /EHsc cpuid_helper.cpp /link kernel32.lib ole32.lib oleaut32.lib wbemuuid.lib && (
        echo.
        echo Build successful! cpuid_helper.exe created.
        exit /b 0
    ) || (
        echo.
        echo Build failed with Visual Studio 2022.
        exit /b 1
    )
)

REM Try Visual Studio 2019
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat" (
    call "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"
    cl.exe /O2 /EHsc cpuid_helper.cpp /link kernel32.lib ole32.lib oleaut32.lib wbemuuid.lib && (
        echo.
        echo Build successful! cpuid_helper.exe created.
        exit /b 0
    ) || (
        echo.
        echo Build failed with Visual Studio 2019.
        exit /b 1
    )
)

REM Fallback to MinGW if available
if exist "C:\Program Files\mingw-w64\x86_64-8.1-posix-seh-rt_v6-rev0\mingw64\bin\g++.exe" (
    set PATH=C:\Program Files\mingw-w64\x86_64-8.1-posix-seh-rt_v6-rev0\mingw64\bin;%PATH%
    g++ -O2 cpuid_helper.cpp -o cpuid_helper.exe -lwbemuuid -lole32 -loleaut32 && (
        echo.
        echo Build successful with MinGW! cpuid_helper.exe created.
        exit /b 0
    ) || (
        echo.
        echo Build failed with MinGW.
        exit /b 1
    )
)

echo.
echo ERROR: No suitable C++ compiler found.
echo Please install:
echo  - Microsoft Visual Studio 2022/2019, or
echo  - MinGW-w64
echo Then run this script again.
exit /b 1
