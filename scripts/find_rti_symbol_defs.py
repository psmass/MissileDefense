import os, subprocess
root = r'C:\RTI\rti_connext_dds-7.7.0\lib\x64Win64VS2017'
dumpbin = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64\dumpbin.exe'
symbols = ['DDS_LENGTH_UNLIMITED','DDS_TOPIC_QOS_DEFAULT','DDS_HANDLE_NIL','DDS_DATAWRITER_QOS_DEFAULT','DDS_TYPE_ALLOCATION_PARAMS_DEFAULT']
res = {s:[] for s in symbols}
for fn in sorted(os.listdir(root)):
    if fn.lower().endswith('.lib'):
        path = os.path.join(root, fn)
        try:
            out = subprocess.check_output([dumpbin, '/symbols', path], stderr=subprocess.DEVNULL, text=True)
        except subprocess.CalledProcessError:
            continue
        for s in symbols:
            for line in out.splitlines():
                if s in line and 'UNDEF' not in line:
                    res[s].append((fn,line.strip()))
                    break
for s in symbols:
    print('==',s,'==')
    if res[s]:
        for fn,line in res[s]:
            print(fn,':',line)
    else:
        print('  (none)')
