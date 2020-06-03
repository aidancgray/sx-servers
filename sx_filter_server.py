#!/usr/bin/python3.8
# sx_filter_server.py
# 4/27/2020
# Aidan Gray
# aidan.gray@idg.jhu.edu
# 
# This is an Indi Client for running/controlling the SX Filter Wheel on Indi Server.

import asyncio
import PyIndi
import time
import sys
import os
import threading
import logging
import subprocess
import numpy as np
from astropy.io import fits

class IndiClient(PyIndi.BaseClient):
    def __init__(self):
        super(IndiClient, self).__init__()
    def newDevice(self, d):
        pass
    def newProperty(self, p):
        pass
    def removeProperty(self, p):
        pass
    def newBLOB(self, bp):
        global blobEvent
        #print("new BLOB ", bp.name)
        blobEvent.set()
        pass
    def newSwitch(self, svp):
        pass
    def newNumber(self, nvp):
        pass
    def newText(self, tvp):
        pass
    def newLight(self, lvp):
        pass
    def newMessage(self, d, m):
        pass
    def serverConnected(self):
        pass
    def serverDisconnected(self, code):
        pass

# create log
def log_start():
    scriptDir = os.path.dirname(os.path.abspath(__file__))
    scriptName = os.path.splitext(os.path.basename(__file__))[0]
    log = logging.getLogger('filter_server')
    hdlr = logging.FileHandler(scriptDir+'/'+scriptName+'.log')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    hdlr.setFormatter(formatter)
    log.addHandler(hdlr)
    log.setLevel(logging.INFO)
    return log
    
def connect_to_indi():
    # connect the server
    indiclient=IndiClient()
    indiclient.setServer("localhost",7624)
     
    if (not(indiclient.connectServer())):
         print("No indiserver running on "+indiclient.getHost()+":"+str(indiclient.getPort())+" - Try to run")
         print("  indiserver indi_sx_ccd indi_sx_wheel")
         sys.exit(1)

    return indiclient

def connect_to_wheel():
    filter="SX Wheel"
    device_filter=indiclient.getDevice(filter)
    while not(device_filter):
        time.sleep(0.5)
        device_filter=indiclient.getDevice(filter)
        print("Searching for device...")

    print("Found device")
     
    # connect to the filter wheel device
    filter_connect=device_filter.getSwitch("CONNECTION")
    while not(filter_connect):
        time.sleep(0.5)
        filter_connect=device_filter.getSwitch("CONNECTION")
    if not(device_filter.isConnected()):
        filter_connect[0].s=PyIndi.ISS_ON  # the "CONNECT" switch
        filter_connect[1].s=PyIndi.ISS_OFF # the "DISCONNECT" switch
        indiclient.sendNewSwitch(filter_connect)
 
 	# get the current slot number
    filter_slot=device_filter.getNumber("FILTER_SLOT")
    while not(filter_slot):
        time.sleep(0.5)
        filter_slot=device_filter.getNumber("FILTER_SLOT")

    # get the current slot name
    filter_name=device_filter.getText("FILTER_NAME")
    while not(filter_name):
    	time.sleep(0.5)
    	filter_name=device_filter.getText("FILTER_NAME")

    return filter_slot, filter_name

# change the filter wheel's parameters based on what the client provides
def setParams(commandList):
	response = ''
	
	for i in commandList:
		# set the filter slot
		if 'slot=' in i:
			try:
				slot = int(i.replace('slot=',''))
				if slot >= 1 and slot <= 5:
					filter_slot[0].value = slot
					indiclient.sendNewNumber(filter_slot)
					response = 'OK: Filter Slot set to '+str(slot)
				else:
					response = 'BAD: Invalid Filter Slot'
			except ValueError:
				response = 'BAD: Invalid Filter Slot'
                
		# set the slot name
		elif 'slotName=' in i:
			try:
				slotName = str(i.replace('slotName=',''))
				if len(slotName) <= 50:
					response = 'OK: Setting current filter name to '+slotName
					filter_name[int(filter_slot[0].value)-1].text = slotName
					indiclient.sendNewText(filter_name)
				else:
					response = 'BAD: Invalid filter name'
			except ValueError:
				response = 'BAD: Invalid filter name'
                
		else:
			response = 'BAD: Invalid Set'+'\n'+response

	return response

# command handler, to parse the client's data more precisely
def handle_command(log, writer, data): 
    response = 'BAD: Invalid Command'
    commandList = data.split()

    try:
        # check if command is Expose, Set, or Get
        if commandList[0] == 'set':
            if len(commandList) >= 1:
                response = setParams(commandList[1:])
    except IndexError:
        response = 'BAD: Invalid Command'
        
    # tell the client the result of their command & log it
    log.info('RESPONSE: '+response)
    writer.write((response+'\n').encode('utf-8'))
    writer.write(('---------------------------------------------------\n').encode('utf-8'))                          

# async client handler, for multiple connections
async def handle_client(reader, writer):
    request = None
    
    # loop to continually handle incoming data
    while request != 'quit':        
        request = (await reader.read(255)).decode('utf8')
        print(request.encode('utf8'))
        log.info('COMMAND: '+request)
        writer.write(('COMMAND: '+request.upper()).encode('utf8'))    

        response = 'BAD'
        # check if data is empty, a status query, or potential command
        dataDec = request
        if dataDec == '':
            break
        elif 'status' in dataDec.lower():
            # check if the command thread is running
            try:
                if comThread.is_alive():
                    response = 'BUSY'
                else:
                    response = 'IDLE'
            except:
                response = 'IDLE'

            response = response+\
                '\nSLOT #: '+str(filter_slot[0].value)+\
                '\nSLOT NAME: '+str(filter_name[int(filter_slot[0].value)-1].text)

            # send current status to open connection & log it
            log.info('RESPONSE: '+response)
            writer.write((response+'\n').encode('utf-8'))
        else:
            # check if the command thread is running, may fail if not created yet, hence try/except
            try:
                if comThread.is_alive():
                    response = 'BAD: busy'
                    # send current status to open connection & log it
                    log.info('RESPONSE: '+response)
                    writer.write((response+'\n').encode('utf-8'))
                else:
                    # create a new thread for the command
                    comThread = threading.Thread(target=handle_command, args=(log, writer, dataDec,))
                    comThread.start()
            except:
                # create a new thread for the command
                comThread = threading.Thread(target=handle_command, args=(log, writer, dataDec,))
                comThread.start()

        writer.write(('---------------------------------------------------\n').encode('utf-8'))                          
        await writer.drain()
    writer.close()

async def main(HOST, PORT):
    print("Opening connection @"+HOST+":"+str(PORT))
    server = await asyncio.start_server(handle_client, HOST, PORT)
    await server.serve_forever()
    
if __name__ == "__main__":
    fileDir = '/home/vncuser/Pictures/SX-CCD/'    
    log = log_start()
    
    # connect to the local indiserver
    indiclient = connect_to_indi()
    filter_slot, filter_name = connect_to_wheel()
    
    # setup Remote TCP Server
    HOST, PORT = "192.168.1.14", 9997

    try:
        asyncio.run(main(HOST,PORT))
    except KeyboardInterrupt:
        print('...Closing server...')
    except:
        print('Unknown error')
