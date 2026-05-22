$libs = Get-ChildItem -Path 'C:\RTI\rti_connext_dds-7.7.0\lib\x64Win64VS2017' -Filter *.lib
$symbols = @(
    'DDS_HANDLE_NIL', 'DDS_LENGTH_UNLIMITED', 'DDS_DATAWRITER_QOS_DEFAULT',
    'DDS_ANY_SAMPLE_STATE', 'DDS_ANY_VIEW_STATE', 'DDS_ANY_INSTANCE_STATE',
    'DDS_DATAREADER_QOS_DEFAULT', 'DDS_TOPIC_QOS_DEFAULT', 'DDS_PUBLISHER_QOS_DEFAULT',
    'DDS_SUBSCRIBER_QOS_DEFAULT', 'DDS_PARTICIPANT_QOS_DEFAULT', 'DDS_TYPE_ALLOCATION_PARAMS_DEFAULT',
    'DDS_TYPE_DEALLOCATION_PARAMS_DEFAULT', 'DDS_g_tc_long_w_new', 'DDS_g_tc_double_w_new',
    'DDS_g_tc_boolean_w_new', 'DDS_LOG_BAD_PARAMETER_s', 'DDS_LOG_SEQUENCE_NOT_OWNER',
    'DDS_LOG_GET_FAILURE_s', 'DDS_LOG_SET_FAILURE_s', 'DDS_LOG_LOCK_ENTITY_FAILURE',
    'DDS_LOG_UNLOCK_ENTITY_FAILURE', 'DDS_AUTO_DATA_REPRESENTATION', 'DDS_DYNAMIC_DATA_PROPERTY_DEFAULT'
)
$out = @()
foreach ($sym in $symbols) {
    foreach ($lib in $libs) {
        $dump = & 'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64\dumpbin.exe' /symbols $lib.FullName 2>$null
        if ($dump -match $sym) {
            $matches = $dump -split "\r?\n" | Where-Object { $_ -match $sym } | Select-Object -First 5
            foreach ($m in $matches) {
                $out += "${sym} -> $($lib.Name): $m"
            }
        }
    }
}
if ($out.Count -eq 0) { Write-Output "No matches found" } else { $out | Out-File -FilePath map_rti_symbols_result.txt -Encoding utf8; Write-Output "Wrote map_rti_symbols_result.txt" }
