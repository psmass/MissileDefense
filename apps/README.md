# Ship Defense Demo (Apps Folder)

This folder contains the Ship Defense demonstration applications using SDL2 and RTI Connext DDS.

## What is included
- `command_control/main.cpp`: Threat publisher and command/control UI.
- `sensor/main.cpp`: Threat subscriber and sensor detection publisher.
- `effector/main.cpp`: Threat subscriber and effector action publisher.

## DDS Type Generation
This project is based on the IDL file at `../idl/ShipThreat.idl`.

### Generate Connext types
From this folder run:

```bat
cd apps
generate_rtiddsgen.bat
```

The script will use `RTIDDSGEN_OUTPUT_DIR` if set, otherwise it generates directly into `../idl/generated`.

## Build Notes
- Ensure `RTI_CONNEXTDDS_DIR` points to your RTI Connext DDS installation root.
- Ensure `nddscpp` is available on `PATH` or use the Connext `bin` folder.
- `SDL2` must be installed and discoverable by CMake.

## Project layout expectations
- `idl/ShipThreat.idl` contains the IDL definitions.
- `idl/generated` should contain the RTI generated type support files.
- `CMakeLists.txt` should copy `RTIDDSGEN_OUTPUT_DIR` contents to `idl/generated`.
