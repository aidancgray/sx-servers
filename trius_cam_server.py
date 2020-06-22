#! /usr/bin/env python3
# trius_cam_server.py
# 4/27/2020
# Aidan Gray
# aidan.gray@idg.jhu.edu
# 
# This is an Indi Client for testing the Trius Cam on Indi Server.

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
    log = logging.getLogger('cam_server')
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

    # get access to setting the CCD's binning value
    ccd_bin=device_ccd.getNumber("CCD_BINNING")
    while not(ccd_bin):
        time.sleep(0.5)
        ccd_bin=device_ccd.getNumber("CCD_BINNING")

    # get access to aborting the CCD's exposure
    ccd_abort=device_ccd.getSwitch("CCD_ABORT_EXPOSURE")
    while not(ccd_abort):
        time.sleep(0.5)
        ccd_abort=device_ccd.getSwitch("CCD_ABORT_EXPOSURE")

    # get access to the CCD's temperature value
    ccd_temp=device_ccd.getNumber("CCD_TEMPERATURE")
    while not(ccd_temp):
        time.sleep(0.5)
        ccd_temp=device_ccd.getNumber("CCD_TEMPERATURE")

    # get access to switching the CCD's cooler on/off
    ccd_cooler=device_ccd.getSwitch("CCD_COOLER")
    while not(ccd_cooler):
        time.sleep(0.5)
        ccd_cooler=device_ccd.getSwitch("CCD_COOLER")
    
    return ccd_exposure, ccd_ccd1, ccd_bin, ccd_abort, ccd_temp, ccd_cooler

def last_image(fileDir):
    lastNum = 0
    lastImg = ''
    
    for f in os.listdir(fileDir):
        if os.path.isfile(os.path.join(fileDir, f)):
            file_name = os.path.splitext(f)[0]
            file_name2 = file_name[4:]
            try:
                file_num = int(file_name2)
                if file_num > lastNum:
                    lastNum = file_num
                    lastImg = os.path.join(fileDir, f)
            except ValueError:
                'The file name "%s" is not an integer. Skipping' % file_name

    return lastNum, lastImg

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
        global imgNum
        global imgName
        imgNum += 1
        fileName = fileDir+'fsc-'+str(imgNum).zfill(8)+'.fits'
        f = open(fileName, 'wb')
        f.write(image_data)
        f.close()
        imgName = fileName
        
        # edit the FITS header
        fitsFile = fits.open(fileName, 'update')
        hdr = fitsFile[0].header
        hdr.set('expType', expType)
        fitsFile.close()
        
    return fileName

# change the CCD's parameters based on what the client provides
def setParams(commandList):

    for i in commandList:
        # set the bin mode (1x1 or 2x2)
        if 'bin=' in i:
            try:
                bin = int(i.replace('bin=',''))
                if bin >= 1 and bin <= 2:
                    ccd_bin[0].value = bin
                    ccd_bin[1].value = bin
                    indiclient.sendNewNumber(ccd_bin)
                    response = 'OK: Bin mode set to '+str(bin)+'x'+str(bin)
                else:
                    response = 'BAD: Invalid Bin Mode'
            except ValueError:
                response = 'BAD: Invalid Bin Mode'

        # turn the cooler on/off
        elif 'cooler=' in i:
            cooler = i.replace('cooler=','')

            if cooler.lower() == 'on':
                ccd_cooler[0].s=PyIndi.ISS_ON  # the "COOLER_ON" switch
                ccd_cooler[1].s=PyIndi.ISS_OFF # the "COOLER_OFF" switch
                indiclient.sendNewSwitch(ccd_cooler)
                response = 'OK: Cooler turned '+cooler
            elif cooler.lower() == 'off':
                ccd_cooler[0].s=PyIndi.ISS_OFF  # the "COOLER_ON" switch
                ccd_cooler[1].s=PyIndi.ISS_ON   # the "COOLER_OFF" switch
                indiclient.sendNewSwitch(ccd_cooler)
                response = 'OK: Cooler turned '+cooler
            else:
                response = 'BAD: Invalid cooler set'
                
        # set the temperature setpoint (-40C - 0C)
        elif 'temp=' in i:
            try:
                temp = float(i.replace('temp=',''))
                if temp >= -40 and temp <= 0:
                    response = 'OK: Setting temperature setpoint to '+str(temp)
                    ccd_temp[0].value = temp
                    indiclient.sendNewNumber(ccd_temp)
                else:
                    response = 'BAD: Invalid temperature setpoint'
            except ValueError:
                response = 'BAD: Invalid temperature setpoint'
                
        # set the image output directory
        elif 'fileDir=' in i:
            try:
                global imgNum
                global imgName
                global fileDir
                global p
                tempFileDir = i.replace('fileDir=','')
                imgNum, imgName = last_image(tempFileDir)
                fileDir = tempFileDir
                response = 'OK: File directory set to '+fileDir
                #p.kill()
                #p = subprocess.Popen([sys.executable, 'file_watcher.py', fileDir], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            except FileNotFoundError:
                response = 'BAD: Directory does not exist'
        else:
            response = 'BAD: Invalid Set'+'\n'+response

    return response

# command handler, to parse the client's data more precisely
def handle_command(log, writer, data): 
    response = 'BAD: Invalid Command'
    commandList = data.split()

    try:
        # check if command is Expose, Set, or Get
        if commandList[0] == 'expose':
            if len(commandList) == 3:
                if commandList[1] == 'object' or commandList[1] == 'flat' or commandList[1] == 'dark' or commandList[1] == 'bias':
                    expType = commandList[1]
                    expTime = commandList[2]
                    try:
                        float(expTime)
                        if float(expTime) > 0:                    
                            expTime = float(expTime)
                            fileName = exposure(expType, expTime)
                            response = 'OK\n'+'FILENAME: '+fileName
                        else:
                            response = 'BAD: Invalid Exposure Time'
                    except ValueError:
                        response = 'BAD: Invalid Exposure Time'
        elif commandList[0] == 'set':
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
                '\nBIN MODE: '+str(ccd_bin[0].value)+'x'+str(ccd_bin[1].value)+\
                '\nCCD TEMP: '+str(ccd_temp[0].value)+\
                'C\nFILE DIR: '+str(fileDir)+\
                '\nLAST IMAGE: '+str(imgName)

            # send current status to open connection & log it
            log.info('RESPONSE: '+response)
            writer.write((response+'\n').encode('utf-8'))
            
        elif 'stop' in dataDec.lower():
            # check if the command thread is running
            try:
                if comThread.is_alive():
                    response = 'OK: aborting exposure'
                    ccd_abort[0].s=PyIndi.ISS_ON 
                    indiclient.sendNewSwitch(ccd_abort)
                    blobEvent.set() #Ends the currently running thread.
                    response = response+'\nExposure Aborted'
                else:
                    response = 'BAD: idle'
            except:
                response = 'BAD: idle'

            # send current status to open connection & log it
            log.info('RESPONSE: '+response)
	    
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
    fileDir = os.path.expanduser('~')+'/Pictures/'    
    imgNum, imgName = last_image(fileDir)
    log = log_start()

    p = subprocess.Popen([sys.executable, 'file_watcher.py', fileDir], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    
    # connect to the local indiserver
    indiclient = connect_to_indi()
    ccd_exposure, ccd_ccd1, ccd_bin, ccd_abort, ccd_temp, ccd_cooler = connect_to_ccd()

    # initialize ccd cooler on and temperature setpoint = -10C
    ccd_cooler[0].s=PyIndi.ISS_ON  # the "COOLER_ON" switch
    ccd_cooler[1].s=PyIndi.ISS_OFF # the "COOLER_OFF" switch
    indiclient.sendNewSwitch(ccd_cooler)

    ccd_temp[0].value = -10
    indiclient.sendNewNumber(ccd_temp)
    
    # create a thread event for blobs
    blobEvent=threading.Event()
    
    # setup Remote TCP Server
    HOST, PORT = "192.168.1.29", 9998

    try:
        asyncio.run(main(HOST,PORT))
    except KeyboardInterrupt:
        print('...Closing server...')
    except:
        print('Unknown error')
