#!/usr/bin/python3.8
# file_watcher.py
# 5/21/2020
# Aidan Gray
# aidan.gray@idg.jhu.edu
#
# This Python script uses the Watchdog library to monitor the selected directory
# for newly created FITS files

import time
import logging
import sys
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from trius_cam_server import *

# create log
def log_start():
    scriptDir = os.path.dirname(os.path.abspath(__file__))
    scriptName = os.path.splitext(os.path.basename(__file__))[0]
    log = logging.getLogger('file-watch')
    hdlr = logging.FileHandler(scriptDir+'/'+scriptName+'.log')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    hdlr.setFormatter(formatter)
    log.addHandler(hdlr)
    log.setLevel(logging.INFO)
    return log

def on_created(event):
    log.info(f"Created: {event.src_path}")

if __name__ == "__main__":
    path = sys.argv[1]
    log = log_start()
 
    patterns = "*.fits"
    ignore_patterns = ""
    ignore_directories = True
    case_sensitive = True

    my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)
    my_event_handler.on_created = on_created
    go_recursively = True

    my_observer = Observer()
    my_observer.schedule(my_event_handler, path, recursive=go_recursively)

    my_observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        my_observer.stop()
        my_observer.join()
