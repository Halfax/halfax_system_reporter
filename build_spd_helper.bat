@echo off
REM Build script for spd_helper.exe on Windows
REM Requirements: Microsoft Visual C++ Build Tools or Visual Studio

echo Building spd_helper.exe...

REM Try to use MSVC compiler if available
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
    cl.exe /O2 spd_helper.c /link kernel32.lib && (
        echo.
        echo Build successful! spd_helper.exe created.
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
    cl.exe /O2 spd_helper.c /link kernel32.lib && (
        echo.
        echo Build successful! spd_helper.exe created.
        exit /b 0
    ) || (
        echo.
        echo Build failed with Visual Studio 2019.
        exit /b 1
    )
)

REM Fallback to MinGW if available
if exist "C:\Program Files\mingw-w64\x86_64-8.1-posix-seh-rt_v6-rev0\mingw64\bin\gcc.exe" (
    set PATH=C:\Program Files\mingw-w64\x86_64-8.1-posix-seh-rt_v6-rev0\mingw64\bin;%PATH%
    gcc -O2 spd_helper.c -o spd_helper.exe && (
        echo.
        echo Build successful with MinGW! spd_helper.exe created.
        exit /b 0
    ) || (
        echo.
        echo Build failed with MinGW.
        exit /b 1
    )
)

echo.
echo ERROR: No suitable C compiler found.
echo Please install:
echo  - Microsoft Visual Studio 2022/2019, or
echo  - MinGW-w64
echo Then run this script again.
exit /b 1
