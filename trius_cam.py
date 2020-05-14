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

def connect_to_ccd(indiclient):
    # Let's take some pictures
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
 
    # Ensure the CCD simulator snoops the telescope simulator
    # otherwise you may not have a picture of vega
    # ccd_active_devices=device_ccd.getText("ACTIVE_DEVICES")
    # while not(ccd_active_devices):
    #     time.sleep(0.5)
    #     ccd_active_devices=device_ccd.getText("ACTIVE_DEVICES")
    # ccd_active_devices[0].text="Telescope Simulator"
    # indiclient.sendNewText(ccd_active_devices)
 
    # we should inform the indi server that we want to receive the
    # "CCD1" blob from this device
    indiclient.setBLOBMode(PyIndi.B_ALSO, ccd, "CCD1")
 
    ccd_ccd1=device_ccd.getBLOB("CCD1")
    while not(ccd_ccd1):
        time.sleep(0.5)
        ccd_ccd1=device_ccd.getBLOB("CCD1")

    return ccd_exposure, ccd_ccd1

def exposure(indiclient, blobEvent, ccd_exposure, ccd_ccd1, exposures):
    i=0
    ccd_exposure[0].value=exposures[i]
    indiclient.sendNewNumber(ccd_exposure)
    while (i < len(exposures)):
        name = str(exposures[i])
        # wait for the ith exposure
        blobEvent.wait()
        # we can start immediately the next one
        if (i + 1 < len(exposures)):
            ccd_exposure[0].value=exposures[i+1]
            blobEvent.clear()
            indiclient.sendNewNumber(ccd_exposure)
        # and meanwhile process the received one
        for blob in ccd_ccd1:
            print("name: ", blob.name," size: ", blob.size," format: ", blob.format)
            # pyindi-client adds a getblobdata() method to IBLOB item
            # for accessing the contents of the blob, which is a bytearray in Python
            image_data=blob.getblobdata()
            print("fits data type: ", type(image_data))

            image2D = blob.processblob()
            
            #image2D.shape = (2200, 2750)
            hdu = fits.PrimaryHDU()
            hdu.data = image2D
            hdu.writeto('/home/vncuser/Pictures/SX CCD/SX-CCD-Test-'+name+'.fits')
        # and perform some computations while the ccd is exposing
        # but this is outside the scope of this tutorial
        i+=1

if __name__ == "__main__":
    
    indiclient = connect_to_indi()
    ccd_exposure, ccd_ccd1 = connect_to_ccd(indiclient)
    
    # a list of our exposure times
    exposures=[0.1, 0.5, 1.0, 1.5]
    
    # we use here the threading.Event facility of Python
    # we define an event for newBlob event
    blobEvent=threading.Event()
    blobEvent.clear()    

    exposure(indiclient, blobEvent, ccd_exposure, ccd_ccd1, exposures)
