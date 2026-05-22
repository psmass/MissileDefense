import subprocess
lib = r'C:\RTI\Demos\MissileDefense\build\Debug\ship_types.lib'
dumpbin = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64\dumpbin.exe'
keys = ['SensorDetectionSeq','EffectorActionSeq','ThreatTypeSupport','DDS_LENGTH_UNLIMITED']
try:
    out = subprocess.check_output([dumpbin,'/symbols',lib], stderr=subprocess.DEVNULL, text=True)
except Exception as e:
    print('ERROR', e)
    raise
for line in out.splitlines():
    for k in keys:
        if k in line:
            print(k,':',line)
