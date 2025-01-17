# The MIT License (MIT)

# Copyright (c) 2015 Michael Caverley

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

#Version 1.1
import math
import numpy as np
import hp816x_instr

class fineAlign(object):
    
    wavelength = 1550e-9; # Fine align wavelength
    laserPower = 0; # Laser power for fine align
    laserOutput = 'highpower' # Which laser output to use
    laserSlot = 'auto' # Which laser slot to use. Default to first found laser
    
    # A list containing the detectors which will be used for fine align. It will use the detector in
    # the first index, then the second etc..
    detectorPriority = [0] 
    
    stepSize = 2 # Stage step size in microns
    
    scanWindowSize = 50; # Size of square window which will be searched by fine align
    
    threshold = -50 # Spiral search will stop once power is greater than the threshold
    
    numGradientIter = 50;
    
    useCrosshair = 0 # Set to 1 to use crosshair search after gradient. Doesn't work very well.

    useDebugStep = 0 #set to 1 to turn on tracking of power and steps
    
    useFineGradient = True; #Secondary Gradient Search
    
    UltraFineAlign = True; #Sets pwm avging time to 0.01 sec. Accuracy and scan time are increased
    
    abort = False # Can set to true to self.abort a fine align
    
    NO_ERROR = 0
    DEVICE_NOT_FOUND = 1
    FINE_ALIGN_ABORTED = 2
    
    
    
    def __init__(self, laser, stage):
        self.laser = laser
        self.stage = stage
    
    def doFineAlign(self):
        xStartPos = self.stage.getPosition()[0];
        yStartPos = self.stage.getPosition()[1];
        
        ##Debug##
        if self.useDebugStep == 1:
            #Logfile Section## Another Section below as well##
            self.logfileSpiral = open('Logfile_Spiral'+str(self.stepSize)+'um.txt','w+')#For Analytical Purposes 
            self.logfileRGrad = open('Logfile_RGrad'+str(self.stepSize)+'um.txt','w+')
            if self.useFineGradient == True:
                self.logfileFGrad = open('Logfile_FGrad'+str(self.stepSize)+'um.txt','w+')
        #/Debug#
                
        for det in self.detectorPriority:
            maxSteps = math.ceil(self.scanWindowSize/float(self.stepSize))
            # Get the detector slot number and channel for the chosen detector index
            detSlot = self.laser.pwmSlotMap[det][0]
            detChan = self.laser.pwmSlotMap[det][1]
            
            self.laser.setPWMPowerUnit(detSlot, detChan, 'dBm')
            self.laser.setPWMPowerRange(detSlot, detChan, 'auto', 0)
            # Try to set laser output. If the laser only has one output, an error is thrown
            # which will be ignored here
            
            if self.UltraFineAlign == True:
                self.laser.setPWMAveragingTime(detSlot,detChan,(0.01))
            else:
                self.laser.setPWMAveragingTime(detSlot,detChan,(0.0001))
            #Sets the PWMAveraging Time    
            
            try:
                self.laser.setTLSOutput(self.laserOutput, slot=self.laserSlot)
            except hp816x_instr.InstrumentError:
                pass
            self.laser.setTLSWavelength(self.wavelength, slot=self.laserSlot)
            self.laser.setTLSPower(self.laserPower, slot=self.laserSlot)
            self.laser.setTLSState('on', slot=self.laserSlot)
                  
            
            # Spiral search method
            res =  self.spiralSearch(maxSteps, detSlot, detChan)
            if res == self.DEVICE_NOT_FOUND:
                xStopPos = self.stage.getPosition()[0];
                yStopPos = self.stage.getPosition()[1];
                self.stage.moveRelative(xStartPos-xStopPos, yStartPos-yStopPos)
                print ('Could not find a device using this detector.')
                continue
            elif res == self.FINE_ALIGN_ABORTED:
                print ('Fine align self.aborted.')
                break
            print ('Found a device. Optimizing power...')   
            
            # Gradient search stage      
            res = self.gradientSearchRough(detSlot, detChan)
            
            if self.useFineGradient == True:
                res = self.gradientSearchFine(detSlot, detChan)
              
            # Crosshair method
            if self.useCrosshair:
                res = self.crosshairSearch(maxSteps, detSlot, detChan)
            self.laser.setAutorangeAll()
            print ('Fine align completed.')
            #Debug#
            if self.useDebugStep ==1:
                self.logfileSpiral.close() 
                self.logfileRGrad.close()
                if self.useFineGradient == True:
                    self.logfileFGrad.close()
            #/Debug#
            return res
            
        # Fine align failed  
        print ('Fine align failed.')
        xStopPos = self.stage.getPosition()[0];
        yStopPos = self.stage.getPosition()[1];
        self.stage.moveRelative(xStartPos-xStopPos, yStartPos-yStopPos)
        self.laser.setAutorangeAll()
        return res    
            
    def spiralSearch(self, maxSteps, detSlot, detChan):
        numSteps = 1
        
        power = self.laser.readPWM(detSlot, detChan)
    
        direction = 1;
        
        # If threshold already met return right away
        if power > self.threshold:
            return self.NO_ERROR
    
        # Spiral search stage
        while power <= self.threshold and numSteps < maxSteps:
            
            # X movement
            for ii in range(1, numSteps+1):
                self.stage.moveRelative(self.stepSize*direction,0)
                power = self.laser.readPWM(detSlot, detChan)
                if self.abort:
                    return self.FINE_ALIGN_ABORTED
                elif power > self.threshold:
                    return self.NO_ERROR
                    if self.useDebugStep == 1:
                        self.logfileSpiral.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
   
                    
            # Y movement
            for ii in range(1, numSteps+1):
                self.stage.moveRelative(0,self.stepSize*direction)
                power = self.laser.readPWM(detSlot, detChan)
                if self.abort:
                    return self.FINE_ALIGN_ABORTED
                elif power > self.threshold:
                    return self.NO_ERROR
                    if self.useDebugStep == 1:
                        self.logfileSpiral.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                    
            numSteps += 1
            
            # Swap sweep direction
            if direction == 1:
                direction = -1
            else:
                direction = 1
                
        
        return self.DEVICE_NOT_FOUND # Return error    
            
            
    def gradientSearchRough(self, detSlot, detChan):
        peakFoundCount = 0; # Count how many consective peaks are found
        numConsecutivePeaks = 1; # Need this many consecutive peaks to conclude the peak was found  
        for ii in range(self.numGradientIter):
            if self.abort:
                return self.FINE_ALIGN_ABORTED
            # Always move in the direction of increasing power
            power = self.laser.readPWM(detSlot, detChan)
            
            self.stage.moveRelative(self.stepSize,0)
            power_posx = self.laser.readPWM(detSlot, detChan)
            
            if power_posx > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(-2*self.stepSize,0)
            power_negx = self.laser.readPWM(detSlot, detChan)

                    
            if power_negx > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(self.stepSize,self.stepSize)
            power_posy = self.laser.readPWM(detSlot, detChan)
                     
                    
            if power_posy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(0,-2*self.stepSize)
            power_negy = self.laser.readPWM(detSlot, detChan)
                      
            
            if power_negy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            
         #8 Axis#   
            #XX
            self.stage.moveRelative(self.stepSize,0)
            power_xnegy = self.laser.readPWM(detSlot, detChan)
                      
            if power_xnegy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            #XY
            self.stage.moveRelative(0,2*self.stepSize)            
            power_xy = self.laser.readPWM(detSlot, detChan)
                      
            if power_xy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            #negXY
            self.stage.moveRelative(-2*self.stepSize,0)
            power_negxy = self.laser.readPWM(detSlot, detChan)
                      
            if power_negxy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            #negXnegY
            self.stage.moveRelative(0,-2*self.stepSize)
            power_negxnegy = self.laser.readPWM(detSlot, detChan)
                      
            if power_negxnegy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileRGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(self.stepSize,self.stepSize)
            if peakFoundCount == numConsecutivePeaks:
                return self.NO_ERROR
            
            peakFoundCount += 1

            
        return self.NO_ERROR
        
    def gradientSearchFine(self, detSlot, detChan):
        peakFoundCount = 0; # Count how many consective peaks are found
        numConsecutivePeaks = 1; # Need this many consecutive peaks to conclude the peak was found  
        for ii in range(self.numGradientIter):
            if self.abort:
                return self.FINE_ALIGN_ABORTED
            # Always move in the direction of increasing power
            power = self.laser.readPWM(detSlot, detChan)
            
            self.stage.moveRelative(0.5,0)
            power_posx = self.laser.readPWM(detSlot, detChan)
            
            if power_posx > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(-2*0.5,0)
            power_negx = self.laser.readPWM(detSlot, detChan)

                    
            if power_negx > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(0.5,0.5)
            power_posy = self.laser.readPWM(detSlot, detChan)
                     
                    
            if power_posy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(0,-2*0.5)
            power_negy = self.laser.readPWM(detSlot, detChan)
                      
            
            if power_negy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            
         #8 axis#   
            #XX
            self.stage.moveRelative(0.5,0)
            power_xnegy = self.laser.readPWM(detSlot, detChan)
                      
            if power_xnegy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            #XY
            self.stage.moveRelative(0,2*0.5)
            power_xy = self.laser.readPWM(detSlot, detChan)
                      
            if power_xy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            #negXY
            self.stage.moveRelative(-2*0.5,0)
            power_negxy = self.laser.readPWM(detSlot, detChan)
                      
            if power_negxy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            #negXnegY
            self.stage.moveRelative(0,-2*0.5)
            power_negxnegy = self.laser.readPWM(detSlot, detChan)
                      
            if power_negxnegy > power:
                peakFoundCount = 0
                #Debug
                if self.useDebugStep == 1:
                   self.logfileFGrad.write(str(self.stage.getPosition()[0])+","+str(self.stage.getPosition()[1])+","+str(power)+"\n")
                 #
                continue
            
            self.stage.moveRelative(0.5,0.5)
            if peakFoundCount == numConsecutivePeaks:
                return 0
            
            peakFoundCount += 1

            
        return self.NO_ERROR
            
    def crosshairSearch(self, maxSteps, detSlot, detChan):
        # Search X direction
        self.stage.moveRelative(-self.scanWindowSize/2.0,0)
        xStartPos = self.stage.getPosition()[0];
        yStartPos = self.stage.getPosition()[1];
        numSteps = int(self.scanWindowSize/float(self.stepSize))
        powerXVals = np.zeros(numSteps)    
        sweepXCoords = np.zeros(numSteps)  
        
        for ii in range(numSteps):
            if self.abort:
                return self.FINE_ALIGN_ABORTED
            powerXVals[ii] = self.laser.readPWM(detSlot, detChan)
            sweepXCoords[ii] = self.stage.getPosition()[0]
            self.stage.moveRelative(self.stepSize,0)

        maxPowerXIdx = np.argmax(powerXVals)
        maxPowerXPos = sweepXCoords[maxPowerXIdx]
        
        xStopPos = self.stage.getPosition()[0];
        yStopPos = self.stage.getPosition()[1];
        self.stage.moveRelative(maxPowerXPos-xStopPos, yStartPos-yStopPos)

        # Search Y direction
        self.stage.moveRelative(0, -self.scanWindowSize/2.0)
        xStartPos = self.stage.getPosition()[0];
        yStartPos = self.stage.getPosition()[1];
        powerYVals = np.zeros(numSteps)  
        sweepYCoords = np.zeros(numSteps)    
        
        for ii in range(numSteps):
           if self.abort:
              return self.FINE_ALIGN_ABORTED
           powerYVals[ii] = self.laser.readPWM(detSlot, detChan)
           sweepYCoords[ii] = self.stage.getPosition()[1]
           self.stage.moveRelative(0,self.stepSize)

        maxPowerYIdx = np.argmax(powerYVals)
        maxPowerYPos = sweepYCoords[maxPowerYIdx]
        
        xStopPos = self.stage.getPosition()[0];
        yStopPos = self.stage.getPosition()[1];
        self.stage.moveRelative(maxPowerXPos-xStopPos, maxPowerYPos-yStopPos)
        

        return self.NO_ERROR        