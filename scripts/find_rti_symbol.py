import os, subprocess, sys
root = r'C:\RTI\rti_connext_dds-7.7.0\lib\x64Win64VS2017'
dumpbin = r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64\dumpbin.exe'
symbol = 'DDS_LENGTH_UNLIMITED'
found = []
for fn in sorted(os.listdir(root)):
    if fn.lower().endswith('.lib'):
        path = os.path.join(root, fn)
        try:
            out = subprocess.check_output([dumpbin, '/symbols', path], stderr=subprocess.DEVNULL, text=True)
        except subprocess.CalledProcessError:
            continue
        if symbol in out:
            print(fn)
            for line in out.splitlines():
                if symbol in line:
                    print('  ', line)
            found.append(fn)
if not found:
    print('NOT FOUND')
else:
    print('\nTotal:', len(found))
