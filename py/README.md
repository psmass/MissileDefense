# Python example using XML Application Creation and **Compiled Types**

This directory mirrors `python/` but replaces **DynamicData** with
**compiled Python types** — `@idl.struct` classes generated from
`tmsExampleApp.idl` by `rtiddsgen` and stored in `python/tmsConstants.py`.

---

## What changed vs. `python/`

| Area | `python/` (DynamicData) | `pyCompiledTypes/` (compiled types) |
|---|---|---|
| Sample creation | `dds.DynamicData(type_from_qos_provider)` | `TypeClass()` — plain Python dataclass |
| Field write | `sample["fieldName"] = val` | `sample.fieldName = val` |
| Nested field write | `sample["a.b"] = val` | `sample.a.b = val` |
| Field read | `data["fieldName"]` | `data.fieldName` |
| DataWriter lookup | `dds.DynamicData.DataWriter.find_by_name(p, name)` | `dds.DataWriter(participant.find_datawriter(name))` |
| DataReader lookup | `dds.DynamicData.DataReader.find_by_name(p, name)` | `dds.DataReader(participant.find_datareader(name))` |
| Listener base | `dds.DynamicData.NoOpDataWriterListener` | `dds.NoOpDataWriterListener` |
| CFT find | `dds.DynamicData.ContentFilteredTopic.find(p, name)` | `dds.ContentFilteredTopic.find(p, name)` |
| Type registration | Not needed (QosProvider resolves from XML) | `dds.DomainParticipant.register_idl_type(TypeClass, "tms::TypeName")` called **before** `create_participant_from_config()` |

### Key files

| File | Purpose |
|---|---|
| `ddsEntities.py` | Base `Writer` / `Reader` thread classes — compiled-types version |
| `topics.py` | Concrete topic classes (all `sample["field"]` → `sample.field`) |
| `controller.py` | Master Controller application — registers types, runs state machine |
| `device.py` | Generator Device application — registers types, runs state machine |
| `constants.py` | Application constants (identical to `python/constants.py`) |
| `tmsConstants.py` | Thin shim that re-exports the auto-generated compiled types from `python/tmsConstants.py` |
| `application.py` | Signal-handler / run-flag (identical to `python/application.py`) |

---

## Prerequisites

Same as `python/` — install the RTI Connext DDS Python binding:

```
pip install rti.connextdds
```

See the full setup instructions in `python/README.md`.

---

## Type registration

The critical difference is the call to `ddsEntities.register_tms_types()` at
the top of both `controller_main()` and `device_main()`, **before**
`qos_provider.create_participant_from_config()`:

```python
ddsEntities.register_tms_types()                          # <-- new step
qos_provider = dds.QosProvider(constants.QOS_URL)
participant  = qos_provider.create_participant_from_config(...)
```

`register_tms_types()` calls `dds.DomainParticipant.register_idl_type()` for
each compiled type, binding the XML `<register_type name="tms::XYZ">` entries
in `tmsExampleApp.xml` to the corresponding Python `@idl.struct` classes in
`tmsConstants.py`.

---

## Running

```bash
cd pyCompiledTypes
python3 device.py
```

```bash
cd pyCompiledTypes
python3 controller.py
```

Both applications must be run from the `pyCompiledTypes/` directory so the
relative path `../model_distroA/tmsExampleApp.xml` resolves correctly.

---

## Environment

Tested with:

* macOS / Ubuntu 20.04
* RTI Connext DDS Professional 7.x
* Python 3.10+
