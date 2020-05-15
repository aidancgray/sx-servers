#!/usr/bin/python3.8
# trius_cam.py
# 4/27/2020
# Aidan Gray
# aidan.gray@idg.jhu.edu
# 
# This is an Indi Client for testing the Trius Cam on Indi Server.

import socketserver
import asyncio
import PyIndi
import time
import sys
import threading
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
    
def handle_command(data):
    response = 'BAD: Invalid Command'
    commandList = data.split()

    if commandList[0] == 'Expose':
        if len(commandList) == 3:
            if commandList[1] == 'object' or commandList[1] == 'flat' or commandList[1] == 'dark' or commandList[1] == 'bias':
                expType = commandList[1]
                expTime = commandList[2]
                try:
                    float(expTime)
                    if float(expTime) >= 0:
                        expTime = float(expTime)
                        fileName = exposure(expType, expTime)
                        response = 'OK'+'FILENAME: '+fileName
                except ValueError:
                    response = 'BAD: Invalid Exposure Time'

    return response
            
# class MyTCPHandler(socketserver.StreamRequestHandler,):

#     #def setup():
#     #    print('Setup handle')
        
#     def handle(self):
#         # self.rfile is a file-like object created by the handler;
#         # we can now use e.g. readline() instead of raw recv() calls
#         self.data = self.rfile.readline().strip()
#         print("{} wrote:".format(self.client_address[0]))
#         print(self.data)

#         # Likewise, self.wfile is a file-like object used to write back
#         # to the client
#         #self.wfile.write(self.data.upper())
        
#         dataDec = self.data.decode('utf-8')
#         if dataDec == 'q':
#             response = 'Client Disconnected'
#             print(response)
#         else:
#             response = handle_command(dataDec)

#         # Likewise, self.wfile is a file-like object used to write back
#         # to the client
#         self.wfile.write(str.encode('COM: '+dataDec+'\nRESP: '+response))

async def handle_client(reader, writer):
    request = None
    while request != 'quit':
        request = (await reader.read(255)).decode('utf8')
        response = str(eval(request)) + '\n'
        writer.write(response.encode('utf8'))
        await writer.drain()
    writer.close()

if __name__ == "__main__":
    pictureLocation = '/home/vncuser/Pictures/SX-CCD/'
    
    # connect to the local indiserver
    indiclient = connect_to_indi()
    ccd_exposure, ccd_ccd1 = connect_to_ccd()

    # create a thread event for blobs
    blobEvent=threading.Event()

    # setup Remote TCP Server
    HOST, PORT = "192.168.1.85", 9998
    #socketserver.TCPServer.allow_reuse_address = True
    print("Opening connection @"+HOST+":"+str(PORT))
    
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.start_server(handle_client, HOST, PORT))
    loop.run_forever()
    # # Create the server
    # server = socketserver.TCPServer((HOST, PORT), MyTCPHandler)
    
    # # Activate the server; this will keep running until you
    # # interrupt the program with Ctrl-C
    # try:
    #     server.serve_forever()
    # except KeyboardInterrupt:
    #     print('...Closing server...')
    #     server.shutdown()
    # except:
    #     print('Unknown Error')