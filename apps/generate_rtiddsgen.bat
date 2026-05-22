@echo off
setlocal enabledelayedexpansion

rem Helper script to generate RTI Connext C++ types from idl/ShipThreat.idl
rem Place this script in the apps folder of the project.

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..\
set IDL_FILE=%PROJECT_ROOT%idl\ShipThreat.idl
set GENERATED_DIR=%PROJECT_ROOT%idl\generated

if not exist "%IDL_FILE%" (
    echo ERROR: IDL file not found: "%IDL_FILE%"
    goto :EOF
)

if "%RTI_CONNEXTDDS_DIR%"=="" (
    if not "%NDDSHOME%"=="" (
        set RTI_CONNEXTDDS_DIR=%NDDSHOME%
        echo Using NDDSHOME for RTI Connext: %RTI_CONNEXTDDS_DIR%
    ) else (
        echo ERROR: RTI_CONNEXTDDS_DIR is not set and NDDSHOME is not set.
        echo Please set NDDSHOME or RTI_CONNEXTDDS_DIR to the RTI Connext DDS installation root.
        goto :EOF
    )
    where rtiddsgen.exe >nul 2>&1
    if %ERRORLEVEL%==0 (
        set NDDSCMD=rtiddsgen
        set NDDSARGS=-ppDisable -d "%RTIDDSGEN_OUTPUT_DIR%" -language C++ -namespace -create typefiles
    ) else (
        where rtiddsgen.bat >nul 2>&1
        if %ERRORLEVEL%==0 (
            set NDDSCMD=rtiddsgen
            set NDDSARGS=-ppDisable -d "%RTIDDSGEN_OUTPUT_DIR%" -language C++ -namespace -create typefiles
        ) else (
            if exist "%RTI_CONNEXTDDS_DIR%\bin\rtiddsgen.bat" (
                set NDDSCMD="%RTI_CONNEXTDDS_DIR%\bin\rtiddsgen.bat"
                set NDDSARGS=-ppDisable -d "%RTIDDSGEN_OUTPUT_DIR%" -language C++ -namespace -create typefiles
            ) else if exist "%RTI_CONNEXTDDS_DIR%\bin\rtiddsgen.exe" (
                set NDDSCMD="%RTI_CONNEXTDDS_DIR%\bin\rtiddsgen.exe"
                set NDDSARGS=-ppDisable -d "%RTIDDSGEN_OUTPUT_DIR%" -language C++ -namespace -create typefiles
            ) else if exist "%RTI_CONNEXTDDS_DIR%\bin\nddscpp.exe" (
                set NDDSCMD="%RTI_CONNEXTDDS_DIR%\bin\nddscpp.exe"
                set NDDSARGS=-language C++ -example none -outputDir "%RTIDDSGEN_OUTPUT_DIR%"
            ) else (
                echo ERROR: neither rtiddsgen nor nddscpp found. Ensure RTI Connext bin is on PATH or set RTI_CONNEXTDDS_DIR/NDDSHOME.
                goto :EOF
            )
        )
    )
)

if not exist "%GENERATED_DIR%" (
    echo Creating generated directory "%GENERATED_DIR%"...
    mkdir "%GENERATED_DIR%"
)

rem Prefer rtiddsgen if available on PATH, otherwise check RTI bin for rtiddsgen or nddscpp
where rtiddsgen.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    set NDDSCMD=rtiddsgen
    set NDDSARGS=-ppDisable -d "%RTIDDSGEN_OUTPUT_DIR%" -language C++ -namespace -create typefiles
) else if exist "%RTI_CONNEXTDDS_DIR%\bin\rtiddsgen.exe" (
    set NDDSCMD="%RTI_CONNEXTDDS_DIR%\bin\rtiddsgen.exe"
    set NDDSARGS=-ppDisable -d "%RTIDDSGEN_OUTPUT_DIR%" -language C++ -namespace -create typefiles
) else if exist "%RTI_CONNEXTDDS_DIR%\bin\nddscpp.exe" (
    set NDDSCMD="%RTI_CONNEXTDDS_DIR%\bin\nddscpp.exe"
    set NDDSARGS=-language C++ -example none -outputDir "%RTIDDSGEN_OUTPUT_DIR%"
) else (
    echo ERROR: neither rtiddsgen nor nddscpp found. Ensure RTI Connext bin is on PATH or set RTI_CONNEXTDDS_DIR/NDDSHOME.
    goto :EOF
)

echo Generating RTI Connext types for %IDL_FILE%...
%NDDSCMD% %NDDSARGS% "%IDL_FILE%"
if errorlevel 1 (
    echo ERROR: nddscpp failed.
    goto :EOF
)

if /I "%RTIDDSGEN_OUTPUT_DIR%" NEQ "%GENERATED_DIR%" (
    echo Copying generated files into %GENERATED_DIR%...
    robocopy "%RTIDDSGEN_OUTPUT_DIR%" "%GENERATED_DIR%" *.h *.c *.cpp *.hpp /NFL /NDL /NJH /NJS /nc /ns /np >nul
    if errorlevel 8 (
        echo ERROR: robocopy failed to copy generated files.
        goto :EOF
    )
)

echo Generation complete.
if /I "%RTIDDSGEN_OUTPUT_DIR%" NEQ "%GENERATED_DIR%" (
    echo Generated files copied from %RTIDDSGEN_OUTPUT_DIR% to %GENERATED_DIR%.
) else (
    echo Generated files created directly in %GENERATED_DIR%.
)
endlocal
