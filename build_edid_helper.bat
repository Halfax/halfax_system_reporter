@echo off
REM Build script for edid_helper.exe on Windows
REM Requirements: Microsoft Visual C++ Build Tools or Visual Studio

echo Building edid_helper.exe...

REM Try to use MSVC compiler if available
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
    cl.exe /O2 edid_helper.c /link kernel32.lib setupapi.lib cfgmgr32.lib advapi32.lib && (
        echo.
        echo Build successful! edid_helper.exe created.
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
    cl.exe /O2 edid_helper.c /link kernel32.lib setupapi.lib cfgmgr32.lib advapi32.lib && (
        echo.
        echo Build successful! edid_helper.exe created.
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
    gcc -O2 edid_helper.c -o edid_helper.exe -lkernel32 -lsetupapi -lcfgmgr32 -ladvapi32 && (
        echo.
        echo Build successful with MinGW! edid_helper.exe created.
        exit /b 0
    ) || (
        echo.
        echo Build failed with MinGW.
        exit /b 1
    )
)

echo.
echo ERROR: No suitable C compiler found.
