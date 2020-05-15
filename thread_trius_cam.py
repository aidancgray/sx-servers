#!/usr/bin/python3.8
# trius_cam.py
# 4/27/2020
# Aidan Gray
# aidan.gray@idg.jhu.edu
# 
# This is an Indi Client for testing the Trius Cam on Indi Server.

import socketserver
import queue
import asyncio
import PyIndi
import time
import sys
import threading
import numpy as np
from astropy.io import fits
from concurrent.futures import ProcessPoolExecutor

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
        print("new BLOB ", bp.name)
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

def connect_to_indi():
    # connect the server
    indiclient=IndiClient()
    indiclient.setServer("localhost",7624)
     
    if (not(indiclient.connectServer())):
         print("No indiserver running on "+indiclient.getHost()+":"+str(indiclient.getPort())+" - Try to run")
         print("  indiserver indi_sx_ccd")
         sys.exit(1)

    return indiclient

def connect_to_ccd():
    ccd="SX CCD SXVR-H694"
    device_ccd=indiclient.getDevice(ccd)
    while not(device_ccd):
        time.sleep(0.5)
        device_ccd=indiclient.getDevice(ccd)
        print("Searching for device...")

    print("Found device")
     
    ccd_connect=device_ccd.getSwitch("CONNECTION")
    while not(ccd_connect):
        time.sleep(0.5)
        ccd_connect=device_ccd.getSwitch("CONNECTION")
    if not(device_ccd.isConnected()):
        ccd_connect[0].s=PyIndi.ISS_ON  # the "CONNECT" switch
        ccd_connect[1].s=PyIndi.ISS_OFF # the "DISCONNECT" switch
        indiclient.sendNewSwitch(ccd_connect)

 
    ccd_exposure=device_ccd.getNumber("CCD_EXPOSURE")
    while not(ccd_exposure):
        time.sleep(0.5)
        ccd_exposure=device_ccd.getNumber("CCD_EXPOSURE")
  
    # inform the indi server that we want to receive the
    # "CCD1" blob from this device
    indiclient.setBLOBMode(PyIndi.B_ALSO, ccd, "CCD1")
    ccd_ccd1=device_ccd.getBLOB("CCD1")
    while not(ccd_ccd1):
        time.sleep(0.5)
        ccd_ccd1=device_ccd.getBLOB("CCD1")
        
    return ccd_exposure, ccd_ccd1

def exposure(expType, expTime):
    blobEvent.clear()    

    # set the value for the next exposure
    ccd_exposure[0].value=expTime

    indiclient.sendNewNumber(ccd_exposure)

    name = str(expTime)

    # wait for the exposure
    blobEvent.wait()

    for blob in ccd_ccd1:
        #print("name: ", blob.name," size: ", blob.size," format: ", blob.format)
        # pyindi-client adds a getblobdata() method to IBLOB item
        # for accessing the contents of the blob, which is a bytearray in Python
        image_data=blob.getblobdata()
        
        #print("fits data type: ", type(image_data))

        # write the byte array out to a FITS file
        fileName = pictureLocation+'fsc-'+name+'.fits'
        f = open(fileName, 'wb')
        f.write(image_data)
        f.close()
        
        # edit the FITS header
        fitsFile = fits.open(fileName, 'update')
        hdr = fitsFile[0].header
        hdr.set('expType', expType)
        fitsFile.close()
    return fileName

# command handler, to parse the client's data more precisely
def handle_command(writer, data): 
    response = 'BAD: Invalid Command'
    commandList = data.split()

    # check if command is Expose or Set
    if commandList[0] == 'expose':
        if len(commandList) == 3:
            if commandList[1] == 'object' or commandList[1] == 'flat' or commandList[1] == 'dark' or commandList[1] == 'bias':
                expType = commandList[1]
                expTime = commandList[2]
                try:
                    float(expTime)
                    if float(expTime) >= 0:                    
                        expTime = float(expTime)
                        fileName = exposure(expType, expTime)
                        response = 'OK\n'+'FILENAME: '+fileName
                except ValueError:
                    response = 'BAD: Invalid Exposure Time'

    # tell the client what file was created
    writer.write((response+'\n').encode('utf-8'))    

# async client handler, for multiple connections
async def handle_client(reader, writer):
    request = None

    # loop to continually handle incoming data
    while request != 'quit':
        request = (await reader.read(255)).decode('utf8')
        print(request)
        writer.write(('COMMAND: '+request.upper()).encode('utf8'))    

        # check if data is empty, a status query, or potential command
        dataDec = request
        if dataDec == '':
            break
        elif 'status' in dataDec.lower():
            # check if the command thread is running
            try:
                if comThread.is_alive():
                    response = 'busy'
                else:
                    response = 'idle'
            except:
                response = 'idle'
            # send current status to open connection
            writer.write((response+'\n').encode('utf-8'))
        
        else:
            # check if the command thread is running, may fail if not created yet, hence try/except
            try:
                if comThread.is_alive():
                    response = 'BAD: busy'
                else:
                    # create a new thread for the command
                    comThread = threading.Thread(target=handle_command, args=(writer, dataDec,))
                    comThread.start()
            except:
                # create a new thread for the command
                comThread = threading.Thread(target=handle_command, args=(writer, dataDec,))
                comThread.start()
        
        await writer.drain()
    writer.close()

async def main(HOST, PORT):
    print("Opening connection @"+HOST+":"+str(PORT))
    server = await asyncio.start_server(handle_client, HOST, PORT)
    await server.serve_forever()
    
if __name__ == "__main__":
    pictureLocation = '/home/vncuser/Pictures/SX-CCD/'

    executor = ProcessPoolExecutor(max_workers=5)
    
    # connect to the local indiserver
    indiclient = connect_to_indi()
    ccd_exposure, ccd_ccd1 = connect_to_ccd()

    # create a thread event for blobs
    blobEvent=threading.Event()
    
    # setup Remote TCP Server
    HOST, PORT = "192.168.1.85", 9998

    try:
        asyncio.run(main(HOST,PORT))
    except KeyboardInterrupt:
        print('...Closing server...')
    except:
        print('Unknown error')
