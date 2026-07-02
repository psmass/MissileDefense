"""
Re-exports the auto-generated tmsConstants module from the sibling python/ directory.

Uses importlib.util.spec_from_file_location to load python/tmsConstants.py by
its absolute path under a private module name (_tmsConstants_src), avoiding
any circular-import / name-collision issue caused by this file sharing the same
name as the module it re-exports.

tmsConstants.py was generated from tmsExampleApp.idl by rtiddsgen and contains:
  - Compiled IDL type classes decorated with @idl.struct / @idl.enum
  - DDS entity name constants for participants, publishers, subscribers,
    DataWriters and DataReaders
  - All TMS IDL constants, enumerations, and module-level aliases
"""

import importlib.util
import os
import sys

_src_path = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '..', 'python', 'tmsConstants.py')
)

_spec = importlib.util.spec_from_file_location("_tmsConstants_src", _src_path)
_mod  = importlib.util.module_from_spec(_spec)
sys.modules["_tmsConstants_src"] = _mod   # register before exec to handle any internal refs
_spec.loader.exec_module(_mod)

# Re-export every public attribute into this module's namespace so callers can do:
#   import tmsConstants
#   tmsConstants.tms_Heartbeat / tmsConstants.generator_device / etc.
globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith('__')})
