"""
application.py — VectorNav / HSMST applications
=================================================
Provides the global ``run_flag`` boolean and a SIGINT handler so that all
Writer and Reader threads can poll ``application.run_flag`` to know when to
exit cleanly.

Pattern mirrors pyCompiledTypes/application.py from the TMS example.
"""

import signal


def signal_handler(sig, frame):
    print('\nCtrl+C received — signalling all threads to stop.')
    global run_flag
    run_flag = False


signal.signal(signal.SIGINT, signal_handler)

run_flag = True
print("Enter Ctrl+C to quit")
