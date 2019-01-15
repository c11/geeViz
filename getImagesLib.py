from pyMapViewerLib import *

######################################################################
#Module for getting Landsat, Sentinel 2 and MODIS images/composites
#Define visualization parameters
vizParamsFalse = { \
  'min': 0.1, \
  'max': [0.5,0.6,0.6], \
  'bands': 'swir2,nir,red', \
  'gamma': 1.6\
}

vizParamsTrue = { \
  'min': 0, \
  'max': [0.2,0.2,0.2], \
  'bands': 'red,green,blue', \
}

#Direction of  a decrease in photosynthetic vegetation- add any that are missing
changeDirDict = {\
"blue":1,"green":-1,"red":1,"nir":-1,"swir1":1,"swir2":1,"temp":1,\
"NDVI":-1,"NBR":-1,"NDMI":-1,"NDSI":1,\
"brightness":1,"greenness":-1,"wetness":-1,"fourth":-1,"fifth":1,"sixth":-1,\
"ND_blue_green":-1,"ND_blue_red":-1,"ND_blue_nir":1,"ND_blue_swir1":-1,"ND_blue_swir2":-1,\
"ND_green_red":-1,"ND_green_nir":1,"ND_green_swir1":-1,"ND_green_swir2":-1,"ND_red_swir1":-1,\
"ND_red_swir2":-1,"ND_nir_red":-1,"ND_nir_swir1":-1,"ND_nir_swir2":-1,"ND_swir1_swir2":-1,\
"R_swir1_nir":1,"R_red_swir1":-1,"EVI":-1,"SAVI":-1,"IBI":1,\
"tcAngleBG":-1,"tcAngleGW":-1,"tcAngleBW":-1,"tcDistBG":1,"tcDistGW":1,"tcDistBW":1,\
'NIRv':-1\
}

######################################################################
#FUNCTIONS
######################################################################
######################################################################
#Function to set null value for export or conversion to arrays
def setNoData(image,noDataValue):
  m = image.mask()
  image = image.mask(ee.Image(1))
  image = image.where(m.Not(),noDataValue)
  return image

######################################################################
######################################################################
#Functions to perform basic clump and elim
def sieve(image,mmu):
  connected = image.connectedPixelCount(mmu+20)
  Map.addLayer(connected,{'min':1,'max':mmu},'connected')
  elim = connected.gt(mmu)
  mode = image.focal_mode(mmu/2,'circle')
  mode = mode.mask(image.mask())
  filled = image.where(elim.Not(),mode)
  return filled


#Written by Yang Z.
#------ L8 to L7 HARMONIZATION FUNCTION -----
# slope and intercept citation: Roy, D.P., Kovalskyy, V., Zhang, H.K., Vermote, E.F., Yan, L., Kumar, S.S, Egorov, A., 2016, Characterization of Landsat-7 to Landsat-8 reflective wavelength and normalized difference vegetation index continuity, Remote Sensing of Environment, 185, 57-70.(http://dx.doi.org/10.1016/j.rse.2015.12.024); Table 2 - reduced major axis (RMA) regression coefficients
def harmonizationRoy(oli):
  slopes = ee.Image.constant([0.9785, 0.9542, 0.9825, 1.0073, 1.0171, 0.9949])#create an image of slopes per band for L8 TO L7 regression line - David Roy
  itcp = ee.Image.constant([-0.0095, -0.0016, -0.0022, -0.0021, -0.0030, 0.0029])#create an image of y-intercepts per band for L8 TO L7 regression line - David Roy
  y = oli.select(['B2','B3','B4','B5','B6','B7'],['B1', 'B2', 'B3', 'B4', 'B5', 'B7']).resample('bicubic').subtract(itcp.multiply(10000)).divide(slopes).set('system:time_start', oli.get('system:time_start'))
   #select OLI bands 2-7 and rename them to match L7 band names
   #...resample the L8 bands using bicubic
   #...multiply the y-intercept bands by 10000 to match the scale of the L7 bands then apply the line equation - subtract the intercept and divide by the slope
   # ...set the output system:time_start metadata to the input image time_start otherwise it is null
  return y.toShort()  #return the image as short to match the type of the other data


####################################################################
#Code to implement OLI/ETM/MSI regression
#Chastain et al 2018 coefficients
#Empirical cross sensor comparison of Sentinel-2A and 2B MSI, Landsat-8 OLI, and Landsat-7 ETM+ top of atmosphere spectral characteristics over the conterminous United States
#https://www.sciencedirect.com/science/article/pii/S0034425718305212#t0020
#Left out 8a coefficients since all sensors need to be cross- corrected with bands common to all sensors
#Dependent and Independent variables can be switched since Major Axis (Model 2) linear regression was used
chastainBandNames = ['blue','green','red','nir','swir1','swir2']

#From Table 4
# msi = oli*slope+intercept
# oli = (msi-intercept)/slope
msiOLISlopes = [1.0946,1.0043,1.0524,0.8954,1.0049,1.0002]
msiOLIIntercepts = [-0.0107,0.0026,-0.0015,0.0033,0.0065,0.0046]

#From Table 5
# msi = etm*slope+intercept
# etm = (msi-intercept)/slope
msiETMSlopes = [1.10601,0.99091,1.05681,1.0045,1.03611,1.04011]
msiETMIntercepts = [-0.0139,0.00411,-0.0024,-0.0076,0.00411,0.00861]

#From Table 6
# oli = etm*slope+intercept
# etm = (oli-intercept)/slope
oliETMSlopes =[1.03501,1.00921,1.01991,1.14061,1.04351,1.05271]
oliETMIntercepts = [-0.0055,-0.0008,-0.0021,-0.0163,-0.0045,0.00261]

#Construct dictionary to handle all pairwise combos 
chastainCoeffDict = {'MSI_OLI':[msiOLISlopes,msiOLIIntercepts,1],\
                         'MSI_ETM':[msiETMSlopes,msiETMIntercepts,1],\
                         'OLI_ETM':[oliETMSlopes,oliETMIntercepts,1],\
                         'OLI_MSI':[msiOLISlopes,msiOLIIntercepts,0],\
                         'ETM_MSI':[msiETMSlopes,msiETMIntercepts,0],\
                         'ETM_OLI':[oliETMSlopes,oliETMIntercepts,0]\
}




#Function to apply model in one direction
def dir0Regression(img,slopes,intercepts):
  return img.select(chastainBandNames).multiply(slopes).add(intercepts)

#Applying the model in the opposite direction
def dir1Regression(img,slopes,intercepts):
  return img.select(chastainBandNames).subtract(intercepts).divide(slopes)

#Function to correct one sensor to another
def harmonizationChastain(img, fromSensor,toSensor):
  #Get the model for the given from and to sensor
  comboKey = fromSensor.upper()+'_'+toSensor.upper()
  coeffList = chastainCoeffDict[comboKey]
  slopes = coeffList[0]
  intercepts = coeffList[1]
  direction = ee.Number(coeffList[2])
  
  #Apply the model in the respective direction
  out = ee.Algorithms.If(direction.eq(0),dir0Regression(img,slopes,intercepts),dir1Regression(img,slopes,intercepts))
  return ee.Image(out).copyProperties(img).copyProperties(img,['system:time_start'])


####################################################################
#Function to create a multiband image from a collection
def collectionToImage(collection):
  def cIterator(img,prev):
    return ee.Image(prev).addBands(img)
  stack = ee.Image(collection.iterate(cIterator, ee.Image(1)))
  stack = stack.select(ee.List.sequence(1, stack.bandNames().size().subtract(1)))
  return stack

# i = ee.ImageCollection([ee.Image(3).byte(),ee.Image(3).byte(),ee.Image(1).byte(),])
# out = ee.Image(collectionToImage(i))

# Map.addLayer(out,{'min':1,'max':3})
# Map.launchGEEVisualization()

#Function to handle empty collections that will cause subsequent processes to fail
#If the collection is empty, will fill it with an empty image
def fillEmptyCollections(inCollection,dummyImage):                       
  dummyCollection = ee.ImageCollection([dummyImage.mask(ee.Image(0))])
  imageCount = inCollection.toList(1).length()
  return ee.ImageCollection(ee.Algorithms.If(imageCount.gt(0),inCollection,dummyCollection))


############################################################################
############################################################################
#Adds the float year with julian proportion to image
def addDateBand(img,maskTime = False):
  d = ee.Date(img.get('system:time_start'))
  y = d.get('year')
  d = y.add(d.getFraction('year'))
  #d=d.getFraction('year')
  db = ee.Image.constant(d).rename(['year']).float()
  if(maskTime):db = db.updateMask(img.select([0]).mask())
  
  return img.addBands(db)

def addYearFractionBand(img):
  d = ee.Date(img.get('system:time_start'))
  y = d.get('year')
  #d = y.add(d.getFraction('year'));
  d=d.getFraction('year')
  db = ee.Image.constant(d).rename(['year']).float()
  db = db#.updateMask(img.select([0]).mask())
  return img.addBands(db)

def addYearBand(img):
  d = ee.Date(img.get('system:time_start'))
  y = d.get('year')
  
  db = ee.Image.constant(y).rename(['year']).float()
  db = db#.updateMask(img.select([0]).mask())
  return img.addBands(db)

################################################################
################################################################
fringeCountThreshold = 279#Define number of non null observations for pixel to not be classified as a fringe
################################################################
#Kernel used for defringing
k = ee.Kernel.fixed(41, 41, \
[[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],\
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],\
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], \
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]\
)

################################################################
#Algorithm to defringe Landsat scenes
def defringeLandsat(img):
  #Find any pixel without sufficient non null pixels (fringes)
  m = img.mask().reduce(ee.Reducer.min())
  
  #Apply kernel
  sum = m.reduceNeighborhood(ee.Reducer.sum(), k, 'kernel')
  #Map.addLayer(img,vizParams,'with fringes')
  #Map.addLayer(sum,{'min':20,'max':241},'sum41',false)
  
  #Mask pixels w/o sufficient obs
  sum = sum.gte(fringeCountThreshold);
  img = img.mask(sum);
  #Map.addLayer(img,vizParams,'defringed')
  return img


################################################################
#Function to find unique values of a field in a collection
def uniqueValues(collection,field):
  values  =ee.Dictionary(collection.reduceColumns(ee.Reducer.frequencyHistogram(),[field]).get('histogram')).keys();
  return values

###############################################################
#Function to simplify data into daily mosaics
#This procedure must be used for proper processing of S2 imagery
def dailyMosaics(imgs):
  #Simplify date to exclude time of day
  def dateSimplifier(img):
    d = ee.Date(img.get('system:time_start'))
    day = d.get('day')
    m = d.get('month')
    y = d.get('year')
    simpleDate = ee.Date.fromYMD(y,m,day)
    return img.set('simpleTime',simpleDate.millis())
  
  imgs = imgs.map(dateSimplifier)

  #Find the unique days
  days = uniqueValues(imgs,'simpleTime')
  
  def dayWrapper(d):
    d = ee.Number.parse(d)
    d = ee.Date(d)
    t = imgs.filterDate(d,d.advance(1,'day'))
    f = ee.Image(t.first())
    t = t.mosaic()
    t = t.set('system:time_start',d.millis())
    t = t.copyProperties(f)
    return t
  imgs = days.map(dayWrapper)
  imgs = ee.ImageCollection.fromImages(imgs)
    
  return imgs

################################################################
def getS2(studyArea,startDate,endDate,startJulian,endJulian):

  def multS2(img):
    t = img.select([ 'B1','B2','B3','B4','B5','B6','B7','B8','B8A', 'B9','B10', 'B11','B12']).divide(10000)#Rescale to 0-1
    t = t.addBands(img.select(['QA60']))
    out = t.copyProperties(img).copyProperties(img,['system:time_start'])
    return out

  #Get some s2 data
  s2s = ee.ImageCollection('COPERNICUS/S2')\
            .filterDate(startDate,endDate)\
            .filter(ee.Filter.calendarRange(startJulian,endJulian))\
            .filterBounds(studyArea)\
            .map(multS2).select(['QA60', 'B1','B2','B3','B4','B5','B6','B7','B8','B8A', 'B9','B10', 'B11','B12'],['QA60','cb', 'blue', 'green', 'red', 're1','re2','re3','nir', 'nir2', 'waterVapor', 'cirrus','swir1', 'swir2'])\
            .map(lambda img: img.resample('bicubic'))
  
  #Convert to daily mosaics to avoid redundent observations in MGRS overlap areas and edge artifacts for shadow masking
  s2s = dailyMosaics(s2s)
  return s2s


##################################################################
#Function for acquiring Landsat TOA image collection
def getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,toaOrSR,includeSLCOffL7,defringeL5 = False,addPixelQA = False):
  
  #Set up bands and corresponding band names
  sensorBandDict = {\
    'L8TOA': ee.List([1,2,3,4,5,9,6,'BQA']),\
    'L7TOA': ee.List([0,1,2,3,4,5,7,'BQA']),\
    'L5TOA': ee.List([0,1,2,3,4,5,6,'BQA']),\
    'L4TOA': ee.List([0,1,2,3,4,5,6,'BQA']),\
    'L8SR': ee.List([1,2,3,4,5,7,6,'pixel_qa']),\
    'L7SR': ee.List([0,1,2,3,4,5,6,'pixel_qa']),\
    'L5SR': ee.List([0,1,2,3,4,5,6,'pixel_qa']),\
    'L4SR': ee.List([0,1,2,3,4,5,6,'pixel_qa']),\
    'L8SRFMASK': ee.List(['pixel_qa']),\
    'L7SRFMASK': ee.List(['pixel_qa']),\
    'L5SRFMASK': ee.List(['pixel_qa']),\
    'L4SRFMASK': ee.List(['pixel_qa'])\
    }
  
  sensorBandNameDict = {\
    'TOA': ee.List(['blue','green','red','nir','swir1','temp','swir2','BQA']),\
    'SR': ee.List(['blue','green','red','nir','swir1','temp', 'swir2','pixel_qa']),\
    'SRFMASK': ee.List(['pixel_qa'])\
    }
  
  #Set up collections
  collectionDict = {
    'L8TOA': 'LANDSAT/LC08/C01/T1_TOA',\
    'L7TOA': 'LANDSAT/LE07/C01/T1_TOA',\
    'L5TOA': 'LANDSAT/LT05/C01/T1_TOA',\
    'L4TOA': 'LANDSAT/LT04/C01/T1_TOA',\
    'L8SR': 'LANDSAT/LC08/C01/T1_SR',\
    'L7SR': 'LANDSAT/LE07/C01/T1_SR',\
    'L5SR': 'LANDSAT/LT05/C01/T1_SR',\
    'L4SR': 'LANDSAT/LT04/C01/T1_SR'\
    };
  
  multImageDict = {\
      'TOA': ee.Image([1,1,1,1,1,1,1,1]),\
      'SR': ee.Image([0.0001,0.0001,0.0001,0.0001,0.0001,0.1,0.0001,1])}

  def getLandsat(toaOrSR):
    #Get Landsat data
    l4s = ee.ImageCollection(collectionDict['L4'+ toaOrSR])\
      .filterDate(startDate,endDate)\
      .filter(ee.Filter.calendarRange(startJulian,endJulian))\
      .filterBounds(studyArea)\
      .filter(ee.Filter.lte('WRS_ROW',120))\
      .select(sensorBandDict['L4'+ toaOrSR],sensorBandNameDict[toaOrSR])
      
    

    l5s = ee.ImageCollection(collectionDict['L5'+ toaOrSR])\
      .filterDate(startDate,endDate)\
      .filter(ee.Filter.calendarRange(startJulian,endJulian))\
      .filterBounds(studyArea)\
      .filter(ee.Filter.lte('WRS_ROW',120))\
      .select(sensorBandDict['L5'+ toaOrSR],sensorBandNameDict[toaOrSR])
      
    if defringeL5:
      print('Defringing L4 and L5')
      l4s = l4s.map(defringeLandsat)
      l5s = l5s.map(defringeLandsat)

    l8s = ee.ImageCollection(collectionDict['L8'+ toaOrSR])\
      .filterDate(startDate,endDate)\
      .filter(ee.Filter.calendarRange(startJulian,endJulian))\
      .filterBounds(studyArea)\
      .filter(ee.Filter.lte('WRS_ROW',120))\
      .select(sensorBandDict['L8'+ toaOrSR],sensorBandNameDict[toaOrSR])
    
  #   var ls; var l7s;
    if includeSLCOffL7:
      print('Including All Landsat 7')
      l7s = ee.ImageCollection(collectionDict['L7'+toaOrSR])\
        .filterDate(startDate,endDate)\
        .filter(ee.Filter.calendarRange(startJulian,endJulian))\
        .filterBounds(studyArea)\
        .filter(ee.Filter.lte('WRS_ROW',120))\
        .select(sensorBandDict['L7'+ toaOrSR],sensorBandNameDict[ toaOrSR])
    else:
      print('Only including SLC On Landat 7');
      l7s = ee.ImageCollection(collectionDict['L7'+toaOrSR])\
        .filterDate(ee.Date.fromYMD(1998,1,1),ee.Date.fromYMD(2003,5,31))\
        .filterDate(startDate,endDate)\
        .filter(ee.Filter.calendarRange(startJulian,endJulian))\
        .filterBounds(studyArea)\
        .filter(ee.Filter.lte('WRS_ROW',120))\
        .select(sensorBandDict['L7'+ toaOrSR],sensorBandNameDict[toaOrSR]);

    
    #Merge collections
    ls = ee.ImageCollection(l4s.merge(l5s).merge(l7s).merge(l8s))
    return ls
  ls = getLandsat(toaOrSR)
  #If TOA and Fmask need to merge Fmask qa bits with toa- this gets the qa band from the sr collections
  if toaOrSR.lower() == 'toa' and addPixelQA:
    print('Acquiring SR qa bands for applying Fmask to TOA data')
    
    lsTOAFMASK = getLandsat('SR').select(['pixel_qa']) 
    #Join the TOA with SR QA bands
    print('Joining TOA with SR QA bands')
    ls = joinCollections(ls.select([0,1,2,3,4,5,6]),lsTOAFMASK)
    

  def dataInAllBands(img):
    img = img.updateMask(img.mask().reduce(ee.Reducer.min()))
    return img.multiply(multImageDict[toaOrSR]).copyProperties(img,['system:time_start']).copyProperties(img)

  #Make sure all bands have data
  ls = ls.map(dataInAllBands)

  
  return ls;

###########################################################################
#Helper function to apply an expression and linearly rescale the output.
#Used in the landsatCloudScore function below.
def rescale(img, exp, thresholds):
    return img.expression(exp, {'img': img}).subtract(thresholds[0]).divide(thresholds[1] - thresholds[0])
###########################################################################
# /***
#  * Implementation of Basic cloud shadow shift
#  * 
#  * Author: Gennadii Donchyts
#  * License: Apache 2.0
#  */
#Cloud heights added by Ian Housman
# yMult bug fix adapted from code written by Noel Gorelick by Ian Housman
def projectShadows(cloudMask,image,irSumThresh,contractPixels,dilatePixels,cloudHeights,yMult = None):
  if(yMult == None):
    yMult = ee.Algorithms.If(ee.Algorithms.IsEqual(image.select([3]).projection(), ee.Projection("EPSG:4326")),1,-1)

  meanAzimuth = image.get('MEAN_SOLAR_AZIMUTH_ANGLE')
  meanZenith = image.get('MEAN_SOLAR_ZENITH_ANGLE')
  ##################################################
  #print('a',meanAzimuth)
  #print('z',meanZenith)
  
  #Find dark pixels
  darkPixels = image.select(['nir','swir1','swir2']).reduce(ee.Reducer.sum()).lt(irSumThresh)\
    .focal_min(contractPixels).focal_max(dilatePixels)
    #.gte(1)
  
  
  #Get scale of image
  nominalScale = cloudMask.projection().nominalScale()
  #Find where cloud shadows should be based on solar geometry
  #Convert to radians
  azR =ee.Number(meanAzimuth).add(180).multiply(Math.PI).divide(180.0)
  zenR  =ee.Number(meanZenith).multiply(Math.PI).divide(180.0)
  
  
  def castShadows(cloudHeight):
    cloudHeight = ee.Number(cloudHeight)
    shadowCastedDistance = zenR.tan().multiply(cloudHeight)#Distance shadow is cast
    x = azR.sin().multiply(shadowCastedDistance).divide(nominalScale)#X distance of shadow
    y = azR.cos().multiply(shadowCastedDistance).divide(nominalScale).multiply(yMult);#Y distance of shadow
    return cloudMask.changeProj(cloudMask.projection(), cloudMask.projection().translate(x, y))
    
    
  #Find the shadows
  shadows = cloudHeights.map(castShadows)
  
  shadowMask = ee.ImageCollection.fromImages(shadows).max()
  
  #Create shadow mask
  shadowMask = shadowMask.And(cloudMask.Not())
  shadowMask = shadowMask.And(darkPixels).focal_min(contractPixels).focal_max(dilatePixels)
  #Map.addLayer(cloudMask.updateMask(cloudMask),{'min':1,'max':1,'palette':'88F'},'Cloud mask')
  #Map.addLayer(shadowMask.updateMask(shadowMask),{'min':1,'max':1,'palette':'880'},'Shadow mask')
  
  cloudShadowMask = shadowMask.Or(cloudMask)
  
  image = image.updateMask(cloudShadowMask.Not()).addBands(shadowMask.rename(['cloudShadowMask']))
  return image

def projectShadowsWrapper(img,cloudThresh,irSumThresh,contractPixels,dilatePixels,cloudHeights):
  cloudMask = sentinel2CloudScore(img).gt(cloudThresh)\
    .focal_min(contractPixels).focal_max(dilatePixels)

  img = projectShadows(cloudMask,img,irSumThresh,contractPixels,dilatePixels,cloudHeights)

  return img

#########################################################################
#########################################################################
#Function to mask clouds using the Sentinel-2 QA band.
def maskS2clouds(image):
  qa = image.select('QA60').int16()
  
  #Bits 10 and 11 are clouds and cirrus, respectively.
  cloudBitMask = Math.pow(2, 10)
  cirrusBitMask = Math.pow(2, 11)
  
  #Both flags should be set to zero, indicating clear conditions.
  mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(\
              qa.bitwiseAnd(cirrusBitMask).eq(0))

  #Return the masked and scaled data.
  return image.updateMask(mask)

#########################################################################
#########################################################################
#Compute a cloud score and adds a band that represents the cloud mask.  
#This expects the input image to have the common band names: 
#["red", "blue", etc], so it can work across sensors.
def landsatCloudScore(img):
  #Compute several indicators of cloudiness and take the minimum of them.
  score = ee.Image(1.0)
  #Clouds are reasonably bright in the blue band.
  score = score.min(rescale(img, 'img.blue', [0.1, 0.3]))
 
  #Clouds are reasonably bright in all visible bands.
  score = score.min(rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8]))
   
  #Clouds are reasonably bright in all infrared bands.
  score = score.min(rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8]))

  #Clouds are reasonably cool in temperature.
  score = score.min(rescale(img,'img.temp', [300, 290]))

  #However, clouds are not snow.
  ndsi = img.normalizedDifference(['green', 'swir1'])
  score = score.min(rescale(ndsi, 'img', [0.8, 0.6]))
  
  #ss = snowScore(img).select(['snowScore'])
  #score = score.min(rescale(ss, 'img', [0.3, 0]))
  
  score = score.multiply(100).byte()
  score = score.clamp(0,100)
  return score

#########################################################################
#########################################################################
#Wrapper for applying cloudScore function
def applyCloudScoreAlgorithm(collection,cloudScoreFunction,cloudScoreThresh = 10,cloudScorePctl = 10,contractPixels = 1.5,dilatePixels = 2.5,performCloudScoreOffset = True):
  #Add cloudScore
  
  def cloudScoreWrapper(img):
    img = ee.Image(img)
    cs = cloudScoreFunction(img).rename(["cloudScore"])
    return img.addBands(cs)

  collection = collection.map(cloudScoreWrapper)
 
  if performCloudScoreOffset:
    print('Computing cloudScore offset')
    #Find low cloud score pctl for each pixel to avoid comission errors
    minCloudScore = collection.select(['cloudScore'])\
      .reduce(ee.Reducer.percentile([cloudScorePctl]))
    #Map.addLayer(minCloudScore,{'min':0,'max':30},'minCloudScore',false)
  else:
    print('Not computing cloudScore offset')
    minCloudScore = ee.Image(0).rename(['cloudScore'])

  
  #Apply cloudScore
  def cloudScoreBusterWrapper(img):
    cloudMask = img.select(['cloudScore']).subtract(minCloudScore)\
      .lt(cloudScoreThresh)\
      .focal_max(contractPixels).focal_min(dilatePixels).rename('cloudMask')
    return img.updateMask(cloudMask)

  collection = collection.map(cloudScoreBusterWrapper)
  return collection

#########################################################################
#########################################################################
#Functions for applying fmask to SR data
fmaskBitDict = {'cloud' : 32, 'shadow': 8,'snow':16}

def cFmask(img,fmaskClass):
  m = img.select('pixel_qa').bitwiseAnd(fmaskBitDict[fmaskClass]).neq(0)
  return img.updateMask(m.Not())


def cFmaskCloud(img):
  return cFmask(img,'cloud')

def cFmaskCloudShadow(img):
  return cFmask(img,'shadow')

#########################################################################
#########################################################################
#Function for finding dark outliers in time series.
#Original concept written by Carson Stam and adapted by Ian Housman.
#Adds a band that is a mask of pixels that are dark, and dark outliers.
def simpleTDOM2(collection,zScoreThresh = -1,shadowSumThresh = 0.35,contractPixels = 1.5,dilatePixels = 2.5):
  shadowSumBands = ['nir','swir1']
  
  #Get some pixel-wise stats for the time series
  irStdDev = collection.select(shadowSumBands).reduce(ee.Reducer.stdDev())
  irMean = collection.select(shadowSumBands).mean()
  
  def zThresholder(img):
    zScore = img.select(shadowSumBands).subtract(irMean).divide(irStdDev)
    irSum = img.select(shadowSumBands).reduce(ee.Reducer.sum())
    TDOMMask = zScore.lt(zScoreThresh).reduce(ee.Reducer.sum()).eq(2).And(irSum.lt(shadowSumThresh))
    TDOMMask = TDOMMask.focal_min(contractPixels).focal_max(dilatePixels)
    return img.updateMask(TDOMMask.Not())

  #Mask out dark dark outliers
  collection = collection.map(zThresholder)
  return collection


#########################################################################
#########################################################################
#Function to add common (and less common) spectral indices to an image.
#Includes the Normalized Difference Spectral Vector from (Angiuli and Trianni, 2014)
def addIndices(img):
  #Add Normalized Difference Spectral Vector (NDSV)
  img = img.addBands(img.normalizedDifference(['blue','green']).rename('ND_blue_green'))
  img = img.addBands(img.normalizedDifference(['blue','red']).rename('ND_blue_red'))
  img = img.addBands(img.normalizedDifference(['blue','nir']).rename('ND_blue_nir'))
  img = img.addBands(img.normalizedDifference(['blue','swir1']).rename('ND_blue_swir1'))
  img = img.addBands(img.normalizedDifference(['blue','swir2']).rename('ND_blue_swir2'))

  img = img.addBands(img.normalizedDifference(['green','red']).rename('ND_green_red'))
  img = img.addBands(img.normalizedDifference(['green','nir']).rename('ND_green_nir'))#NDWBI
  img = img.addBands(img.normalizedDifference(['green','swir1']).rename('ND_green_swir1'))#NDSI, MNDWI
  img = img.addBands(img.normalizedDifference(['green','swir2']).rename('ND_green_swir2'))

  img = img.addBands(img.normalizedDifference(['red','swir1']).rename('ND_red_swir1'))
  img = img.addBands(img.normalizedDifference(['red','swir2']).rename('ND_red_swir2'))


  img = img.addBands(img.normalizedDifference(['nir','red']).rename('ND_nir_red'))#NDVI
  img = img.addBands(img.normalizedDifference(['nir','swir1']).rename('ND_nir_swir1'))#NDWI, LSWI, -NDBI
  img = img.addBands(img.normalizedDifference(['nir','swir2']).rename('ND_nir_swir2'))#NBR, MNDVI

  img = img.addBands(img.normalizedDifference(['swir1','swir2']).rename('ND_swir1_swir2'));

  #Add ratios
  img = img.addBands(img.select('swir1').divide(img.select('nir')).rename('R_swir1_nir'))#ratio 5/4
  img = img.addBands(img.select('red').divide(img.select('swir1')).rename('R_red_swir1'))#ratio 3/5

  #Add Enhanced Vegetation Index (EVI)
  evi = img.expression(\
    '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {\
      'NIR': img.select('nir'),\
      'RED': img.select('red'),\
      'BLUE': img.select('blue')\
  }).float()
  img = img.addBands(evi.rename('EVI'))
  
  #Add Soil Adjust Vegetation Index (SAVI)
  #using L = 0.5;
  savi = img.expression(\
    '(NIR - RED) * (1 + 0.5)/(NIR + RED + 0.5)', {\
      'NIR': img.select('nir'),\
      'RED': img.select('red')\
  }).float()
  img = img.addBands(savi.rename('SAVI'))
  
  #Add Index-Based Built-Up Index (IBI)
  ibi_a = img.expression(\
    '2*SWIR1/(SWIR1 + NIR)', {\
      'SWIR1': img.select('swir1'),\
      'NIR': img.select('nir')\
    }).rename('IBI_A')

  ibi_b = img.expression(\
    '(NIR/(NIR + RED)) + (GREEN/(GREEN + SWIR1))', {\
      'NIR': img.select('nir'),\
      'RED': img.select('red'),\
      'GREEN': img.select('green'),\
      'SWIR1': img.select('swir1')\
    }).rename('IBI_B')

  ibi_a = ibi_a.addBands(ibi_b)
  ibi = ibi_a.normalizedDifference(['IBI_A','IBI_B'])
  img = img.addBands(ibi.rename('IBI'))
  
  return img
#########################################################################
#########################################################################
#Function to  add SAVI and EVI
def addSAVIandEVI(img):
  #Add Enhanced Vegetation Index (EVI)
  evi = img.expression(\
    '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {\
      'NIR': img.select('nir'),\
      'RED': img.select('red'),\
      'BLUE': img.select('blue')\
  }).float()
  img = img.addBands(evi.rename('EVI'))
  
  #Add Soil Adjust Vegetation Index (SAVI)
  #using L = 0.5
  savi = img.expression(\
    '(NIR - RED) * (1 + 0.5)/(NIR + RED + 0.5)', {\
      'NIR': img.select('nir'),\
      'RED': img.select('red')\
  }).float()

  
  #########################################################################
  #NIRv: Badgley, G., Field, C. B., & Berry, J. A. (2017). Canopy near-infrared reflectance and terrestrial photosynthesis. Science Advances, 3, e1602244.
  #https://www.researchgate.net/publication/315534107_Canopy_near-infrared_reflectance_and_terrestrial_photosynthesis
  #NIRv function: ‘image’ is a 2 band stack of NDVI and NIR
  #########################################################################
  NIRv =  img.select(['NDVI']).subtract(0.08).multiply(img.select(['nir']))#.multiply(0.0001))

  img = img.addBands(savi.rename('SAVI')).addBands(NIRv.rename('NIRv'))
  return img

#########################################################################
#########################################################################
#Function for only adding common indices
def simpleAddIndices(in_image):
  in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'red']).select([0],['NDVI']))
  in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir2']).select([0],['NBR']))
  in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir1']).select([0],['NDMI']))
  in_image = in_image.addBands(in_image.normalizedDifference(['green', 'swir1']).select([0],['NDSI']))
  
  return in_image

#########################################################################
#########################################################################
#Function for adding common indices
#########################################################################
def addSoilIndices(img):
  img = img.addBands(img.normalizedDifference(['red','green']).rename('NDCI'))
  img = img.addBands(img.normalizedDifference(['red','swir2']).rename('NDII'))
  img = img.addBands(img.normalizedDifference(['swir1','nir']).rename('NDFI'))
  
  bsi = img.expression(\
  '((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))', {\
    'BLUE': img.select('blue'),\
    'RED': img.select('red'),\
    'NIR': img.select('nir'),\
    'SWIR1': img.select('swir1')\
  }).float()

  img = img.addBands(bsi.rename('BSI'))
  
  hi = img.expression(\
    'SWIR1 / SWIR2',{\
      'SWIR1': img.select('swir1'),\
      'SWIR2': img.select('swir2')\
    }).float()
  img = img.addBands(hi.rename('HI'))  
  return img

#########################################################################
#########################################################################
#Function to compute the Tasseled Cap transformation and return an image
#with the following bands added: ['brightness', 'greenness', 'wetness', 
#'fourth', 'fifth', 'sixth']
def getTasseledCap(image):
   
  bands = ee.List(['blue','green','red','nir','swir1','swir2'])
  #   // // Kauth-Thomas coefficients for Thematic Mapper data
  #   // var coefficients = ee.Array([
  #   //   [0.3037, 0.2793, 0.4743, 0.5585, 0.5082, 0.1863],
  #   //   [-0.2848, -0.2435, -0.5436, 0.7243, 0.0840, -0.1800],
  #   //   [0.1509, 0.1973, 0.3279, 0.3406, -0.7112, -0.4572],
  #   //   [-0.8242, 0.0849, 0.4392, -0.0580, 0.2012, -0.2768],
  #   //   [-0.3280, 0.0549, 0.1075, 0.1855, -0.4357, 0.8085],
  #   //   [0.1084, -0.9022, 0.4120, 0.0573, -0.0251, 0.0238]
  #   // ]);
    
  #Crist 1985 coeffs - TOA refl (http://www.gis.usu.edu/~doug/RS5750/assign/OLD/RSE(17)-301.pdf)
  coefficients = ee.Array([[0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2303],\
                      [-0.1603, -0.2819, -0.4934, 0.7940, -0.0002, -0.1446],\
                      [0.0315, 0.2021, 0.3102, 0.1594, -0.6806, -0.6109],\
                      [-0.2117, -0.0284, 0.1302, -0.1007, 0.6529, -0.7078],\
                      [-0.8669, -0.1835, 0.3856, 0.0408, -0.1132, 0.2272],\
                     [0.3677, -0.8200, 0.4354, 0.0518, -0.0066, -0.0104]])
  #Make an Array Image, with a 1-D Array per pixel.
  arrayImage1D = image.select(bands).toArray()
  
  #Make an Array Image with a 2-D Array per pixel, 6x1.
  arrayImage2D = arrayImage1D.toArray(1)
  
  componentsImage = ee.Image(coefficients).matrixMultiply(arrayImage2D)\
  .arrayProject([0])\
  .arrayFlatten([['brightness', 'greenness', 'wetness', 'fourth', 'fifth', 'sixth']]).float()
  
  return image.addBands(componentsImage)

#########################################################################
#########################################################################
def simpleGetTasseledCap(image):
 
  bands = ee.List(['blue','green','red','nir','swir1','swir2'])
  #   // // Kauth-Thomas coefficients for Thematic Mapper data
  #   // var coefficients = ee.Array([
  #   //   [0.3037, 0.2793, 0.4743, 0.5585, 0.5082, 0.1863],
  #   //   [-0.2848, -0.2435, -0.5436, 0.7243, 0.0840, -0.1800],
  #   //   [0.1509, 0.1973, 0.3279, 0.3406, -0.7112, -0.4572],
  #   //   [-0.8242, 0.0849, 0.4392, -0.0580, 0.2012, -0.2768],
  #   //   [-0.3280, 0.0549, 0.1075, 0.1855, -0.4357, 0.8085],
  #   //   [0.1084, -0.9022, 0.4120, 0.0573, -0.0251, 0.0238]
  #   // ]);
    
  #Crist 1985 coeffs - TOA refl (http://www.gis.usu.edu/~doug/RS5750/assign/OLD/RSE(17)-301.pdf)
  coefficients = ee.Array([[0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2303],\
                      [-0.1603, -0.2819, -0.4934, 0.7940, -0.0002, -0.1446],\
                      [0.0315, 0.2021, 0.3102, 0.1594, -0.6806, -0.6109]])
  #Make an Array Image, with a 1-D Array per pixel.
  arrayImage1D = image.select(bands).toArray()
  
  #Make an Array Image with a 2-D Array per pixel, 6x1.
  arrayImage2D = arrayImage1D.toArray(1)
  
  componentsImage = ee.Image(coefficients).matrixMultiply(arrayImage2D)\
  .arrayProject([0])\
  .arrayFlatten([['brightness', 'greenness', 'wetness']]).float()
  
  return image.addBands(componentsImage)

#########################################################################
#########################################################################
#Function to add Tasseled Cap angles and distances to an image.
#Assumes image has bands: 'brightness', 'greenness', and 'wetness'.
def addTCAngles(image):
  #Select brightness, greenness, and wetness bands
  brightness = image.select(['brightness'])
  greenness = image.select(['greenness'])
  wetness = image.select(['wetness'])
  
  #Calculate Tasseled Cap angles and distances
  tcAngleBG = brightness.atan2(greenness).divide(Math.PI).rename('tcAngleBG')
  tcAngleGW = greenness.atan2(wetness).divide(Math.PI).rename('tcAngleGW')
  tcAngleBW = brightness.atan2(wetness).divide(Math.PI).rename('tcAngleBW')
  tcDistBG = brightness.hypot(greenness).rename('tcDistBG')
  tcDistGW = greenness.hypot(wetness).rename('tcDistGW')
  tcDistBW = brightness.hypot(wetness).rename('tcDistBW')
  image = image.addBands(tcAngleBG).addBands(tcAngleGW)\
    .addBands(tcAngleBW).addBands(tcDistBG).addBands(tcDistGW)\
    .addBands(tcDistBW)
  return image

#########################################################################
#########################################################################
#Only adds tc bg angle as in Powell et al 2009
#https://www.sciencedirect.com/science/article/pii/S0034425709003745?via%3Dihub
def simpleAddTCAngles(image):
  #Select brightness, greenness, and wetness bands
  brightness = image.select(['brightness'])
  greenness = image.select(['greenness'])
  wetness = image.select(['wetness'])
  
  #Calculate Tasseled Cap angles and distances
  tcAngleBG = brightness.atan2(greenness).divide(Math.PI).rename('tcAngleBG')
  
  return image.addBands(tcAngleBG)

#########################################################################
#########################################################################
#Function to add solar zenith and azimuth in radians as bands to image
def addZenithAzimuth(img,toaOrSR,zenithDict = None,azimuthDict = None):
  if zenithDict == None:
    zenithDict = {\
    'TOA': 'SUN_ELEVATION',\
    'SR': 'SOLAR_ZENITH_ANGLE'}
  
  if azimuthDict == None:
    azimuthDict = {\
    'TOA': 'SUN_AZIMUTH',\
    'SR': 'SOLAR_AZIMUTH_ANGLE'}
   
  zenith = ee.Image.constant(img.get(zenithDict[toaOrSR]))\
          .multiply(math.pi).divide(180).float().rename('zenith')
  
  azimuth = ee.Image.constant(img.get(azimuthDict[toaOrSR]))\
          .multiply(math.pi).divide(180).float().rename('azimuth')
    
  return img.addBands(zenith).addBands(azimuth)

#########################################################################
#########################################################################
#Function for computing the mean squared difference medoid from an image collection
def medoidMosaicMSD(inCollection,medoidIncludeBands = None):
  #Find band names in first image
  f = ee.Image(inCollection.first())
  bandNames = f.bandNames()
  bandNumbers = ee.List.sequence(1,bandNames.length())
  
  if medoidIncludeBands == None:
    medoidIncludeBands = bandNames

  #Find the median
  median = inCollection.select(medoidIncludeBands).median()
  
  #Find the squared difference from the median for each image
  def msdGetter(img):
    diff = ee.Image(img).select(medoidIncludeBands).subtract(median).pow(ee.Image.constant(2))
    return diff.reduce('sum').addBands(img)
  
  medoid = inCollection.map(msdGetter)
    
  
  #Minimize the distance across all bands
  medoid = ee.ImageCollection(medoid)\
    .reduce(ee.Reducer.min(bandNames.length().add(1)))\
    .select(bandNumbers,bandNames)

  return medoid


#########################################################################
#########################################################################
#Function to export a provided image to an EE asset
def exportToAssetWrapper(imageForExport,assetName,assetPath,pyramidingPolicy = None,roi = None,scale = None,crs = None,transform = None):
  #Make sure image is clipped to roi in case it's a multi-part polygon
  imageForExport = imageForExport.clip(roi)
  assetName = assetName.replace("/\s+/g",'-')#Get rid of any spaces
  t = ee.batch.Export.image.toAsset(imageForExport, assetName, assetPath + '/'+assetName,  {'.default': pyramidingPolicy}, None, roi, scale, crs, crsTransform, 1e13)
  t.start()

def exportToAssetWrapper2(imageForExport,assetName,assetPath,pyramidingPolicyObject = None,roi= None,scale= None,crs = None,transform = None):
  #Make sure image is clipped to roi in case it's a multi-part polygon
  imageForExport = imageForExport.clip(roi)
  assetName = assetName.replace("/\s+/g",'-')#Get rid of any spaces
  t = ee.batch.Export.image.toAsset(imageForExport, assetName, assetPath + '/'+assetName,  pyramidingPolicyObject, None, roi, scale, crs, crsTransform, 1e13)
  t.start()

#########################################################################
#########################################################################
#Function for wrapping dates when the startJulian < endJulian
#Checks for year with majority of the days and the wrapOffset
def wrapDates(startJulian,endJulian):
  #Set up date wrapping
  wrapOffset = 0
  yearWithMajority = 0
  if startJulian > endJulian:
    wrapOffset = 365
    y1NDays = 365-startJulian
    y2NDays = endJulian
    if y2NDays > y1NDays:yearWithMajority = 1
  
  return [wrapOffset,yearWithMajority]

#########################################################################
#########################################################################
#Create composites for each year within startYear and endYear range
def compositeTimeSeries(ls,startYear,endYear,startJulian,endJulian,timebuffer = 0,weights = [1],compositingMethod = 'medoid',compositingReducer = None):
  dummyImage = ee.Image(ls.first())
  
  dateWrapping = wrapDates(startJulian,endJulian)
  wrapOffset = dateWrapping[0]
  yearWithMajority = dateWrapping[1]
  


  def yearCompositeGetter(year):
   
    #Set up dates
    startYearT = year-timebuffer
    endYearT = year+timebuffer
    startDateT = ee.Date.fromYMD(startYearT,1,1).advance(startJulian-1,'day')
    endDateT = ee.Date.fromYMD(endYearT,1,1).advance(endJulian-1+wrapOffset,'day')
 
  
    #print(year,startDateT,endDateT)
    
    #Set up weighted moving widow
    yearsT = ee.List.sequence(startYearT,endYearT)
    
    def zipper(i):
      i = ee.List(i)
      return ee.List.repeat(i.get(0),i.get(1))

    z = yearsT.zip(weights)

    yearsTT = z.map(zipper).flatten()

    print('Weighted composite years for year:',year,yearsTT.getInfo())
    
    #Iterate across each year in list
    def yrGetter(yr):
      #Set up dates
      startDateT = ee.Date.fromYMD(yr,1,1).advance(startJulian-1,'day')
      endDateT = ee.Date.fromYMD(yr,1,1).advance(endJulian-1+wrapOffset,'day')

      #Filter images for given date range
      lsT = ls.filterDate(startDateT,endDateT)
      lsT = fillEmptyCollections(lsT,dummyImage)
      return lsT
    images = yearsTT.map(yrGetter)
    
    
    lsT = ee.ImageCollection(ee.FeatureCollection(images).flatten())
   
    #Compute median or medoid or apply reducer
    if compositingReducer != None:
      composite = lsT.reduce(compositingReducer)
    elif compositingMethod.lower() == 'median':
      composite = lsT.median()
    else:
      composite = medoidMosaicMSD(lsT,['blue','green','red','nir','swir1','swir2'])
    # Map.addLayer(composite,vizParamsFalse,str(year))

    return composite.set({'system:time_start':ee.Date.fromYMD(year+ yearWithMajority,6,1).millis(),\
                        'startDate':startDateT.millis(),\
                        'endDate':endDateT.millis(),\
                        'startJulian':startJulian,\
                        'endJulian':endJulian,\
                        'yearBuffer':timebuffer,\
                        'yearWeights': '[1,2,1]',\
                        'yrOriginal':year,\
                        'yrUsed': year + yearWithMajority})

  #Iterate across each year
  ts = [yearCompositeGetter(yr) for yr in ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()]
  ts = ee.ImageCollection(ts)
  
  return ts

# ////////////////////////////////////////////////////////////////////////////////
# // Function to calculate illumination condition (IC). Function by Patrick Burns 
# // (pb463@nau.edu) and Matt Macander 
# // (mmacander@abrinc.com)
# function illuminationCondition(img){
#   // Extract solar zenith and azimuth bands
#   var SZ_rad = img.select('zenith');
#   var SA_rad = img.select('azimuth');
  
#   // Creat terrain layers
#   // var dem = ee.Image('CGIAR/SRTM90_V4');
#   var dem = ee.Image('USGS/NED');
#   var slp = ee.Terrain.slope(dem);
#   var slp_rad = ee.Terrain.slope(dem).multiply(Math.PI).divide(180);
#   var asp_rad = ee.Terrain.aspect(dem).multiply(Math.PI).divide(180);
  
#   // Calculate the Illumination Condition (IC)
#   // slope part of the illumination condition
#   var cosZ = SZ_rad.cos();
#   var cosS = slp_rad.cos();
#   var slope_illumination = cosS.expression("cosZ * cosS", 
#                                           {'cosZ': cosZ,
#                                            'cosS': cosS.select('slope')});
#   // aspect part of the illumination condition
#   var sinZ = SZ_rad.sin(); 
#   var sinS = slp_rad.sin();
#   var cosAziDiff = (SA_rad.subtract(asp_rad)).cos();
#   var aspect_illumination = sinZ.expression("sinZ * sinS * cosAziDiff", 
#                                            {'sinZ': sinZ,
#                                             'sinS': sinS,
#                                             'cosAziDiff': cosAziDiff});
#   // full illumination condition (IC)
#   var ic = slope_illumination.add(aspect_illumination);

#   // Add IC to original image
#   return img.addBands(ic.rename('IC'))
#     .addBands(cosZ.rename('cosZ'))
#     .addBands(cosS.rename('cosS'))
#     .addBands(slp.rename('slope'));
# }

# ////////////////////////////////////////////////////////////////////////////////
# // Function to apply the Sun-Canopy-Sensor + C (SCSc) correction method to each 
# // image. Function by Patrick Burns (pb463@nau.edu) and Matt Macander 
# // (mmacander@s.com)
# function illuminationCorrection(img, scale,studyArea,bandList){
#   if(bandList === null || bandList === undefined){
#     bandList = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'temp']; 
#   }
  
#   var props = img.toDictionary();
#   var st = img.get('system:time_start');
#   var img_plus_ic = img;
#   var mask2 = img_plus_ic.select('slope').gte(5)
#     .and(img_plus_ic.select('IC').gte(0))
#     .and(img_plus_ic.select('nir').gt(-0.1));
#   var img_plus_ic_mask2 = ee.Image(img_plus_ic.updateMask(mask2));
  
#   // Specify Bands to topographically correct  
#   var compositeBands = img.bandNames();
#   var nonCorrectBands = img.select(compositeBands.removeAll(bandList));
  
#   function apply_SCSccorr(bandList){
#     var method = 'SCSc';
#     var out = img_plus_ic_mask2.select('IC', bandList).reduceRegion({
#       reducer: ee.Reducer.linearFit(),
#       geometry: studyArea,
#       scale: scale,
#       maxPixels: 1e13
#     }); 
#     var out_a = ee.Number(out.get('scale'));
#     var out_b = ee.Number(out.get('offset'));
#     var out_c = out_b.divide(out_a);
#     // Apply the SCSc correction
#     var SCSc_output = img_plus_ic_mask2.expression(
#       "((image * (cosB * cosZ + cvalue)) / (ic + cvalue))", {
#       'image': img_plus_ic_mask2.select(bandList),
#       'ic': img_plus_ic_mask2.select('IC'),
#       'cosB': img_plus_ic_mask2.select('cosS'),
#       'cosZ': img_plus_ic_mask2.select('cosZ'),
#       'cvalue': out_c
#     });
    
#     return SCSc_output;
#   }
  
#   var img_SCSccorr = ee.Image(bandList.map(apply_SCSccorr))
#     .addBands(img_plus_ic.select('IC'));
#   var bandList_IC = ee.List([bandList, 'IC']).flatten();
#   img_SCSccorr = img_SCSccorr.unmask(img_plus_ic.select(bandList_IC)).select(bandList);
  
#   return img_SCSccorr.addBands(nonCorrectBands)
#     .setMulti(props)
#     .set('system:time_start',st);
# }
#########################################################################
#########################################################################
#Function for converting an array to a string delimited by the space parameter
def listToString(list,space = ' '):
  out = ''
  for s in list:
    out += str(s) +space
  out = out[0:len(out)-len(space)]
  return out
#########################################################################
#########################################################################
#A function to mask out pixels that did not have observations for MODIS.
def maskEmptyPixels(image):
  #Find pixels that had observations.
  withObs = image.select('num_observations_1km').gt(0)
  return image.mask(image.mask().And(withObs))

#########################################################################
#########################################################################
# A function that returns an image containing just the specified QA bits.
# 
# Args:
#   image - The QA Image to get bits from.
#   start - The first bit position, 0-based.
#   end   - The last bit position, inclusive.
#   name  - A name for the output image.
 
def getQABits(image, start, end, newName):
  #Compute the bits we need to extract.
  pattern = 0
  for i in range(start,end+1):
    pattern += Math.pow(2, i)
  
  #Return a single band image of the extracted QA bits, giving the band a new name.
  return image.select([0], [newName]).bitwiseAnd(pattern).rightShift(start)

#########################################################################
#########################################################################
#A function to mask out cloudy pixels.
def maskCloudsWQA(image):
  #Select the QA band.
  QA = image.select('state_1km')
  #Get the internal_cloud_algorithm_flag bit.
  internalCloud = getQABits(QA, 10, 10, 'internal_cloud_algorithm_flag')
  #Return an image masking out cloudy areas.
  return image.mask(image.mask().And(internalCloud.eq(0)))

#########################################################################
#########################################################################
#Source: code.earthengine.google.com
#Compute a cloud score.  This expects the input image to have the common
#band names: ["red", "blue", etc], so it can work across sensors.
def modisCloudScore(img):

  useTempInCloudMask = True
  #Compute several indicators of cloudyness and take the minimum of them.
  score = ee.Image(1.0);

  #Clouds are reasonably bright in the blue band.
  score = score.min(rescale(img, 'img.blue', [0.1, 0.3]))
  #Clouds are reasonably bright in all visible bands.
  vizSum = rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8])
  score = score.min(vizSum)

  #Clouds are reasonably bright in all infrared bands.
  irSum =rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8])
  score = score.min(irSum)



  #However, clouds are not snow.
  ndsi = img.normalizedDifference(['green', 'swir1'])
  snowScore = rescale(ndsi, 'img', [0.8, 0.6])
  score =score.min(snowScore)

  #For MODIS, provide the option of not using thermal since it introduces
  #a precomputed mask that may or may not be wanted
  if useTempInCloudMask:
      #Clouds are reasonably cool in temperature.
      tempScore = rescale(img, 'img.temp', [305, 300])
      score = score.min(tempScore)

  score = score.multiply(100)
  score = score.clamp(0,100);
  return score;

#########################################################################
#########################################################################
#Cloud masking algorithm for Sentinel2
#Built on ideas from Landsat cloudScore algorithm
#Currently in beta and may need tweaking for individual study areas
def sentinel2CloudScore(img):
  #Compute several indicators of cloudyness and take the minimum of them.
  score = ee.Image(1)
  blueCirrusScore = ee.Image(0)

  #Clouds are reasonably bright in the blue or cirrus bands.
  #Use .max as a pseudo OR conditional
  blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.blue', [0.1, 0.5]))
  blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cb', [0.1, 0.5]))
  blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cirrus', [0.1, 0.3]))

  reSum = rescale(img,'(img.re1+img.re2+img.re3)/3',[0.5, 0.7])

  score = score.min(blueCirrusScore)

  #Clouds are reasonably bright in all visible bands.
  score = score.min(rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8]))

  #Clouds are reasonably bright in all infrared bands.
  score = score.min(rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8]))

  #However, clouds are not snow.
  ndsi =  img.normalizedDifference(['green', 'swir1'])
  score=score.min(rescale(ndsi, 'img', [0.8, 0.6]))

  score = score.multiply(100).byte().rename(['cloudScore'])
  return score
#########################################################################
#########################################################################
#MODIS processing
#########################################################################
#########################################################################
#Some globals to deal with multi-spectral MODIS
wTempSelectOrder = [2,3,0,1,4,6,5]#Band order to select to be Landsat 5-like if thermal is included
wTempStdNames = ['blue', 'green', 'red', 'nir', 'swir1','temp','swir2']

woTempSelectOrder = [2,3,0,1,4,5]#Band order to select to be Landsat 5-like if thermal is excluded
woTempStdNames = ['blue', 'green', 'red', 'nir', 'swir1','swir2']

#Band names from different MODIS resolutions
#Try to take the highest spatial res for a given band
modis250SelectBands = ['sur_refl_b01','sur_refl_b02']
modis250BandNames = ['red','nir']

modis500SelectBands = ['sur_refl_b03','sur_refl_b04','sur_refl_b06','sur_refl_b07']
modis500BandNames = ['blue','green','swir1','swir2']

combinedModisBandNames = ['red','nir','blue','green','swir1','swir2']


#Dictionary of MODIS collections
modisCDict = {\
  'eightDayNDVIA' : 'MODIS/006/MYD13Q1',\
  'eightDayNDVIT' : 'MODIS/006/MOD13Q1',\
  'eightDaySR250A' : 'MODIS/006/MYD09Q1',\
  'eightDaySR250T' : 'MODIS/006/MOD09Q1',\
  'eightDaySR500A' : 'MODIS/006/MYD09A1',\
  'eightDaySR500T' : 'MODIS/006/MOD09A1',\
  'eightDayLST1000A' : 'MODIS/006/MYD11A2',\
  'eightDayLST1000T' : 'MODIS/006/MOD11A2',\
  'dailySR250A' : 'MODIS/006/MYD09GQ',\
  'dailySR250T' : 'MODIS/006/MOD09GQ',\
  'dailySR500A' : 'MODIS/006/MYD09GA',\
  'dailySR500T' : 'MODIS/006/MOD09GA',\
  'dailyLST1000A' : 'MODIS/006/MYD11A1',\
  'dailyLST1000T' : 'MODIS/006/MOD11A1'}
#########################################################################
#########################################################################
#Helper function to join two collections- Source: code.earthengine.google.com
def joinCollections(c1,c2, maskAnyNullValues = True):
  def MergeBands(element):
    #A function to merge the bands together.
    #After a join, results are in 'primary' and 'secondary' properties.
    return ee.Image.cat(element.get('primary'), element.get('secondary'))


  join = ee.Join.inner()
  filter = ee.Filter.equals('system:time_start', None, 'system:time_start')
  joined = ee.ImageCollection(join.apply(c1, c2, filter))
     
  joined = ee.ImageCollection(joined.map(MergeBands))
  if maskAnyNullValues:
    joined = joined.map(lambda: img, img.mask(img.mask().And(img.reduce(ee.Reducer.min()).neq(0))));

  return joined;



# ls = getImageCollection(ee.Geometry.Polygon(\
#          [[[-107.65431394109078, 39.088573472024486],\
#            [-109.36818112859078, 35.5781084059458],\
#            [-108.64308347234078, 35.16602548916899],\
#            [-107.08302487859078, 38.575083190487966]]]),ee.Date.fromYMD(2014,7,1),ee.Date.fromYMD(2018,10,1),190,250,'SR',False)
# print(ee.Image(ls.first()).bandNames().getInfo())
# print(ee.Image(joinCollections(ls,ls,False).first()).bandNames().getInfo())
# Map.addLayer(ls.median(),vizParamsFalse,'median before masking')
# # medoid = medoidMosaicMSD(ls,['blue','green','red','nir','swir1','swir2'])
# # Map.addLayer(medoid,vizParamsFalse,'medoid before masking')

# # ls = ls.map(simpleAddIndices)
# # ls = ls.map(addSAVIandEVI)
# # ls = ls.map(simpleGetTasseledCap)
# # Map.addLayer(ls.select(['brightness','greenness','wetness']).median())
# # # ls = applyCloudScoreAlgorithm(ls,landsatCloudScore,10,0,1.5,3.5,performCloudScoreOffset = True)


# # # Map.addLayer(ls.median(),vizParamsFalse,'after cloud masking')
# # # ls = simpleTDOM2(ls,-1,0.35,1.5,3.5)
# # # Map.addLayer(ls.median(),vizParamsFalse,'after cloud/shadow masking')
# # # # ls = getImageCollection(ee.Geometry.Polygon(\
# # # #          [[[-107.65431394109078, 39.088573472024486],\
# # # #            [-109.36818112859078, 35.5781084059458],\
# # # #            [-108.64308347234078, 35.16602548916899],\
# # # #            [-107.08302487859078, 38.575083190487966]]]),ee.Date.fromYMD(2018,7,1),ee.Date.fromYMD(2018,10,1),190,250,'SR',False)
# ls = ls.map(cFmaskCloud)
# ls = ls.map(cFmaskCloudShadow)
# compositeTimeSeries(ls,2014,2018,190,250,1,[1,5,1],'medoid')

# # # # Map.addLayer(ls,vizParamsFalse)

# Map.launchGEEVisualization()
#########################################################################
#########################################################################
#Method for removing spikes in time series
def despikeCollection(c,absoluteSpike,bandNo):
  c = c.toList(10000,0)
  
  #Get book ends for adding back at the end
  first = c.slice(0,1)
  last = c.slice(-1,None)
  
  #Slice the left, center, and right for the moving window
  left = c.slice(0,-2)
  center = c.slice(1,-1)
  right = c.slice(2,None)
  
  #Find how many images there are to compare
  seq = ee.List.sequence(0,left.length().subtract(1))
  
  #Compare the center to the left and right images
#   var outCollection = seq.map(function(i){
#     var lt = ee.Image(left.get(i));
#     var rt = ee.Image(right.get(i));
    
#     var ct = ee.Image(center.get(i));
#     var time_start = ct.get('system:time_start');
#     var time_end = ct.get('system:time_end');
#     var si = ct.get('system:index');
   
    
    
#     var diff1 = ct.select([bandNo]).add(1).subtract(lt.select([bandNo]).add(1));
#     var diff2 = ct.select([bandNo]).add(1).subtract(rt.select([bandNo]).add(1));
    
#     var highSpike = diff1.gt(absoluteSpike).and(diff2.gt(absoluteSpike));
#     var lowSpike = diff1.lt(- absoluteSpike).and(diff2.lt(- absoluteSpike));
#     var BinarySpike = highSpike.or(lowSpike);
    
#     //var originalMask = ct.mask();
#     // ct = ct.mask(BinarySpike.eq(0));
    
#     var doNotMask = lt.mask().not().or(rt.mask().not());
#     var lrMean = lt.add(rt);
#     lrMean = lrMean.divide(2);
#     // var out = ct.mask(doNotMask.not().and(ct.mask()))
#     var out = ct.where(BinarySpike.eq(1).and(doNotMask.not()),lrMean);
#     return out.set('system:index',si).set('system:time_start', time_start).set('system:time_end', time_end);
    
    
#   });
#   //Add the bookends back on
#   outCollection =  ee.List([first,outCollection,last]).flatten();
   
#   return ee.ImageCollection.fromImages(outCollection);
  
# }


# ///////////////////////////////////////////////////////////
# //Function to get MODIS data from various collections
# //Will pull from daily or 8-day composite collections based on the boolean variable "daily"
# function getModisData(startYear,endYear,startJulian,endJulian,daily,maskWQA,zenithThresh,useTempInCloudMask){
#     var a250C;var t250C;var a500C;var t500C;var a1000C;var t1000C;
#     var a250CV6;var t250CV6;var a500CV6;var t500CV6;var a1000CV6;var t1000CV6;
    
#       //Find which collections to pull from based on daily or 8-day
#       if(daily === false){
#         a250C = modisCDict.eightDaySR250A;
#         t250C = modisCDict.eightDaySR250T;
#         a500C = modisCDict.eightDaySR500A;
#         t500C = modisCDict.eightDaySR500T;
#         a1000C = modisCDict.eightDayLST1000A;
#         t1000C = modisCDict.eightDayLST1000T;
        
      
#       }
#      else{
#         a250C = modisCDict.dailySR250A;
#         t250C = modisCDict.dailySR250T;
#         a500C = modisCDict.dailySR500A;
#         t500C = modisCDict.dailySR500T;
#         a1000C = modisCDict.dailyLST1000A;
#         t1000C = modisCDict.dailyLST1000T;
        
        
#       }
      
#     //Pull images from each of the collections  
#     var a250 = ee.ImageCollection(a250C)
#               .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
#               .filter(ee.Filter.calendarRange(startJulian,endJulian))
#               .select(modis250SelectBands,modis250BandNames);
    
            
#     var t250 = ee.ImageCollection(t250C)
#               .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
#               .filter(ee.Filter.calendarRange(startJulian,endJulian))
#               .select(modis250SelectBands,modis250BandNames);
    
    
#     function get500(c){
#        var images = ee.ImageCollection(c)
#               .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
#               .filter(ee.Filter.calendarRange(startJulian,endJulian));
              
#               //Mask pixels above a certain zenith
#               if(daily === true){
#                 if(maskWQA === true){print('Masking with QA band:',c)}
#                 images = images
#               .map(function(img){
#                 img = img.mask(img.mask().and(img.select(['SensorZenith']).lt(zenithThresh*100)));
#                 if(maskWQA === true){
                  
#                   img = maskCloudsWQA (img);
#                 }
#                 return img;
#               });
#               }
#               images = images
#               .select(modis500SelectBands,modis500BandNames);
#               return images;
#     }         
#     var a500 = get500(a500C);
#     var t500 = get500(t500C);
    
    
#     //If thermal collection is wanted, pull it as well
#     if(useTempInCloudMask === true){
#        var t1000 = ee.ImageCollection(t1000C)
#               .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
#               .filter(ee.Filter.calendarRange(startJulian,endJulian))
#               .select([0]);
            
#       var a1000 = ee.ImageCollection(a1000C)
#               .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
#               .filter(ee.Filter.calendarRange(startJulian,endJulian))
#               .select([0]);        
#     }
    
#     //Now all collections are pulled, start joining them
#     //First join the 250 and 500 m Aqua
#       var a;var t;var tSelectOrder;var tStdNames;
#       a = joinCollections(a250,a500);
      
#       //Then Terra
#       t = joinCollections(t250,t500);
      
#       //If temp was pulled, join that in as well
#       //Also select the bands in an L5-like order and give descriptive names
#       if(useTempInCloudMask === true){
#         a = joinCollections(a,a1000);
#         t = joinCollections(t,t1000);
#         tSelectOrder = wTempSelectOrder;
#         tStdNames = wTempStdNames;
#       }
#       //If no thermal was pulled, leave that out
#       else{
#         tSelectOrder = woTempSelectOrder;
#         tStdNames = woTempStdNames;
#       }
      
#       //Join Terra and Aqua 
#       var joined = ee.ImageCollection(a.merge(t)).select(tSelectOrder,tStdNames);
     
#       //Divide by 10000 to make it work with cloud masking algorithm out of the box
#       joined = joined.map(function(img){return img.divide(10000).float()
#         .copyProperties(img,['system:time_start','system:time_end']);
        
#       });
#       // print('Collection',joined);
#       //Since MODIS thermal is divided by 0.02, multiply it by that and 10000 if it was included
#       if(useTempInCloudMask === true){
#       joined = joined.map(function(img){
#         var t = img.select(['temp']).multiply(0.02*10000);
#         return img.select(['blue','green','red','nir','swir1','swir2'])
#         .addBands(t).select([0,1,2,3,4,6,5]);
      
#       });
#       }
    
#   //   //Get some descriptive names for displaying layers
#   //   var name = 'surRefl';
#   //   if(daily === true){
#   //     name = name + '_daily';
#   //   }
#   //   else{name = name + '8DayComposite'}
#   //   if(maskWQA === true){
#   //     name = name + '_WQAMask';
#   //   }
    
#   // //Add first image as well as median for visualization
#   //   // Map.addLayer(ee.Image(joined.first()),vizParams,name+'_singleFirstImageBeforeMasking',false);
#   //   // Map.addLayer(ee.Image(joined.median()),vizParams,name+'_CompositeBeforeMasking',false);
    
#   //   if(applyCloudScore === true){
#   // //Compute cloud score and mask cloudy pixels
#   //     print('Applying Google cloudScore algorithm');
#   //     // var joined = joined.map(function(img,useTempInCloudMask){
#   //     //   var cs = modisCloudScore(img);
#   //     //   return img.mask(img.mask().and(cs.lt(cloudThresh)))//.addBands(cs.select([0],['cloudScore']))
        
#   //     // });
#   //   //Add first image as well as median for visualization
#   //   // Map.addLayer(ee.Image(joined.first()),vizParams,name+'_singleFirstImageAfterMasking',false);
#   //   // Map.addLayer(ee.Image(joined.median()),vizParams,name+'_CompositeAfterMasking',false);
#   //   joined = joined.map(function(img){return getCloudMask(img,modisCloudScore,cloudThresh,useTempInCloudMask,contractPixels,dilatePixels)});
      
#   //   }
    
#   // //   //If cloud shadow masking is chosen, run it
#   // //   if(runTDOM === true){
#   // //     print('Running TDOM');
#   // //     joined = simpleTDOM(joined,zShadowThresh,zCloudThresh,maskAllDarkPixels)
    
#   // //   //Add first image as well as median for visualization after TDOM
#   // // // Map.addLayer(ee.Image(joined.first()),vizParams,name+'_singleFirstImageAfterMaskingWTDOM',false);
#   // // // Map.addLayer(ee.Image(joined.median()),vizParams,name+'_CompositeAfterMaskingWTDOM',false);
  
      
#   // //   };
  
  
#   // // //Add indices and select them
#   // // joined = joined.map(addIndices);
#   // joined = joined.map(addIndices);
#   // var indicesAdded = true;
#   // if(despikeMODIS){
#   //   print('Despiking MODIS');
#   //   joined = despikeCollection(joined,modisSpikeThresh,indexName);
#   // }
  
#   return ee.ImageCollection(joined);//.map(function(img){return img.resample('bicubic') }) );
    
#   }
  
# ////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////
# function exportCollection(exportPathRoot,outputName,studyArea, crs,transform,scale,
# collection,startYear,endYear,startJulian,endJulian,compositingReducer,timebuffer,exportBands){
  
#   //Take care of date wrapping
#   var dateWrapping = wrapDates(startJulian,endJulian);
#   var wrapOffset = dateWrapping[0];
#   var yearWithMajority = dateWrapping[1];
  
#   //Clean up output name
#   outputName = outputName.replace(/\s+/g,'-');
#   outputName = outputName.replace(/\//g,'-');
  
#   //Select bands for export
#   collection = collection.select(exportBands);
  
#   //Iterate across each year and export image
#   ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()
#     .map(function(year){
#       print('Exporting:',year);
#     // Set up dates
#     var startYearT = year-timebuffer;
#     var endYearT = year+timebuffer+yearWithMajority;
    
#     // Get yearly composite
#     var composite = collection.filter(ee.Filter.calendarRange(year+yearWithMajority,year+yearWithMajority,'year'));
#     composite = ee.Image(composite.first()).clip(studyArea);
    
#     // Display the Landsat composite
#     Map.addLayer(composite, vizParamsTrue, year.toString() + ' True Color ' , false);
#     Map.addLayer(composite, vizParamsFalse, year.toString() + ' False Color ', false);
#     // Add metadata, cast to integer, and export composite
#     composite = composite.set({
#       'system:time_start': ee.Date.fromYMD(year,6,1).millis(),
#       'yearBuffer':timebuffer
#     });
  
#     // Export the composite 
#     // Set up export name and path
#     var exportName = outputName  +'_'  + startYearT + '_' + endYearT+'_' + 
#       startJulian + '_' + endJulian ;
   
    
#     var exportPath = exportPathRoot + '/' + exportName;
#     // print('Write down the Asset ID:', exportPath);
  
#     exportToAssetWrapper(composite,exportName,exportPath,'mean',
#       studyArea.bounds(),null,crs,transform);
#     });
# }

# // Function to export composite collection
# function exportCompositeCollection(exportPathRoot,outputName,studyArea, crs,transform,scale,
# collection,startYear,endYear,startJulian,endJulian,compositingMethod,timebuffer,exportBands,toaOrSR,weights,
# applyCloudScore, applyFmaskCloudMask,applyTDOM,applyFmaskCloudShadowMask,applyFmaskSnowMask,includeSLCOffL7,correctIllumination,nonDivideBands){
#   if(nonDivideBands === undefined){
#     nonDivideBands = ['temp'];
#   }
#   collection = collection.select(exportBands);
#   var years = ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()
#     .map(function(year){
      
#     // Set up dates
#     var startYearT = year-timebuffer;
#     var endYearT = year+timebuffer;
    
#     // Get yearly composite
#     var composite = collection.filter(ee.Filter.calendarRange(year,year,'year'));
#     composite = ee.Image(composite.first());
    
#     // Display the Landsat composite
#     Map.addLayer(composite, vizParamsTrue, year.toString() + ' True Color ' + 
#       toaOrSR, false);
#     Map.addLayer(composite, vizParamsFalse, year.toString() + ' False Color ' + 
#       toaOrSR, false);
  
#     // Reformat data for export
#     var compositeBands = composite.bandNames();
#     if(nonDivideBands != null){
#       var composite10k = composite.select(compositeBands.removeAll(nonDivideBands))
#       .multiply(10000);
#       composite = composite10k.addBands(composite.select(nonDivideBands))
#       .select(compositeBands).int16();
#     }
#     else{
#       composite = composite.multiply(10000).int16();
#     }
    
    

#     // Add metadata, cast to integer, and export composite
#     composite = composite.set({
#       'system:time_start': ee.Date.fromYMD(year,6,1).millis(),
#       'source': toaOrSR,
#       'yearBuffer':timebuffer,
#       'yearWeights': listToString(weights),
#       'startJulian': startJulian,
#       'endJulian': endJulian,
#       'applyCloudScore':applyCloudScore.toString(),
#       'applyFmaskCloudMask' :applyFmaskCloudMask.toString(),
#       'applyTDOM' :applyTDOM.toString(),
#       'applyFmaskCloudShadowMask' :applyFmaskCloudShadowMask.toString(),
#       'applyFmaskSnowMask': applyFmaskSnowMask.toString(),
#       'compositingMethod': compositingMethod,
#       'includeSLCOffL7': includeSLCOffL7.toString(),
#       'correctIllumination':correctIllumination.toString()
#     });
  
#     // Export the composite 
#     // Set up export name and path
#     var exportName = outputName  + toaOrSR + '_' + compositingMethod + 
#       '_'  + startYearT + '_' + endYearT+'_' + 
#       startJulian + '_' + endJulian ;
   
    
#     var exportPath = exportPathRoot + '/' + exportName;
#     // print('Write down the Asset ID:', exportPath);
  
#     exportToAssetWrapper(composite,exportName,exportPath,'mean',
#       studyArea,scale,crs,transform);
#     });
# }
# /////////////////////////////////////////////////////////////////////
# /////////////////////////////////////////////////////////////////////
# //Wrapper function for getting Landsat imagery
# function getLandsatWrapper(studyArea,startYear,endYear,startJulian,endJulian,
#   timebuffer,weights,compositingMethod,
#   toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
#   applyFmaskCloudShadowMask,applyFmaskSnowMask,
#   cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,
#   zScoreThresh,shadowSumThresh,
#   contractPixels,dilatePixels,
#   correctIllumination,correctScale,
#   exportComposites,outputName,exportPathRoot,crs,transform,scale){
  
#   // Prepare dates
#   //Wrap the dates if needed
#   var wrapOffset = 0;
#   if (startJulian > endJulian) {
#     wrapOffset = 365;
#   }
   
#   var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
#   var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1+wrapOffset,'day');
#   print('Start and end dates:', startDate, endDate);

#   //Do some error checking
#   toaOrSR = toaOrSR.toUpperCase();
#   var addPixelQA;
#   if(toaOrSR === 'TOA' && (applyFmaskCloudMask === true ||  applyFmaskCloudShadowMask === true || applyFmaskSnowMask === true)){
#       addPixelQA = true;
#       // applyFmaskCloudMask = false;
  
#       // applyFmaskCloudShadowMask = false;
  
#       // applyFmaskSnowMask = false;
#     }else{addPixelQA = false;}
#   // Get Landsat image collection
#   var ls = getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
#     toaOrSR,includeSLCOffL7,defringeL5,addPixelQA);
  
#   // Apply relevant cloud masking methods
#   if(applyCloudScore){
#     print('Applying cloudScore');
#     ls = applyCloudScoreAlgorithm(ls,landsatCloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,performCloudScoreOffset); 
#   }
  
#   if(applyFmaskCloudMask){
#     print('Applying Fmask cloud mask');
#     ls = ls.map(function(img){return cFmask(img,'cloud')});
#     //Experimenting on how to reduce commission errors over bright cool areas
#     // var preCount = ls.count();
#     // var cloudFreeCount = ls.map(function(img){return cFmask(img,'cloud')}).count().unmask();
#     // // var ls = ls.map(function(img){return cFmask(img,'cloud')})
#     // var fmaskCloudFreeProp = cloudFreeCount.divide(preCount);
#     // var alwaysCloud = fmaskCloudFreeProp.lte(0.1);
#     // var ls = ls.map(function(img){
#     //   var m = img.select('pixel_qa').bitwiseAnd(fmaskBitDict['cloud']).neq(0).and(alwaysCloud.not());
#     //   return img.updateMask(m.not());
#     // })
   
#     // Map.addLayer(alwaysCloud,{min:0,max:1},'Fmask cloud prop',false);
#   }
  
#   if(applyTDOM){
#     print('Applying TDOM');
#     //Find and mask out dark outliers
#     ls = simpleTDOM2(ls,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);
#   }
#   if(applyFmaskCloudShadowMask){
#     print('Applying Fmask shadow mask');
#     ls = ls.map(function(img){return cFmask(img,'shadow')});
#   }
#   if(applyFmaskSnowMask){
#     print('Applying Fmask snow mask');
#     ls = ls.map(function(img){return cFmask(img,'snow')});
#   }
  
  
#   // Add zenith and azimuth
#   if (correctIllumination){
#     ls = ls.map(function(img){
#       return addZenithAzimuth(img,toaOrSR);
#     });
#   }
  
#   // Add common indices- can use addIndices for comprehensive indices 
#   //or simpleAddIndices for only common indices
#   ls = ls.map(simpleAddIndices)
#           .map(getTasseledCap)
#           .map(simpleAddTCAngles);
          
#   //Set to appropriate resampling method for any reprojection
#   // ls = ls.map(function(img){return img.resample('bicubic') })    
#   // Create composite time series
#   var ts = compositeTimeSeries(ls,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingMethod);
  
  
#   // Correct illumination
#   if (correctIllumination){
#     var f = ee.Image(ts.first());
#     Map.addLayer(f,vizParamsFalse,'First-non-illuminated',false);
  
#     print('Correcting illumination');
#     ts = ts.map(illuminationCondition)
#       .map(function(img){
#         return illuminationCorrection(img, correctScale,studyArea);
#       });
#     var f = ee.Image(ts.first());
#     Map.addLayer(f,vizParamsFalse,'First-illuminated',false);
#   }
  
#   //Export composites
#   if(exportComposites){// Export composite collection
#     var exportBands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'temp'];
#     exportCompositeCollection(exportPathRoot,outputName,studyArea,crs,transform,scale,
#     ts,startYear,endYear,startJulian,endJulian,compositingMethod,timebuffer,exportBands,toaOrSR,weights,
#                   applyCloudScore, applyFmaskCloudMask,applyTDOM,applyFmaskCloudShadowMask,applyFmaskSnowMask,includeSLCOffL7,correctIllumination);
#   }
  
#   return [ls,ts];
# }
# //Wrapper function for getting Landsat imagery
# function getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian,
#   toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
#   applyFmaskCloudShadowMask,applyFmaskSnowMask,
#   cloudScoreThresh,cloudScorePctl,
#   zScoreThresh,shadowSumThresh,
#   contractPixels,dilatePixels
#   ){
  
#   // Prepare dates
#   //Wrap the dates if needed
#   var wrapOffset = 0;
#   if (startJulian > endJulian) {
#     wrapOffset = 365;
#   }
#   var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
#   var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1+wrapOffset,'day');
#   print('Start and end dates:', startDate, endDate);

#   //Do some error checking
#   toaOrSR = toaOrSR.toUpperCase();
#   var addPixelQA;
#   if(toaOrSR === 'TOA' && (applyFmaskCloudMask === true ||  applyFmaskCloudShadowMask === true || applyFmaskSnowMask === true)){
#       addPixelQA = true;
#       // applyFmaskCloudMask = false;
  
#       // applyFmaskCloudShadowMask = false;
  
#       // applyFmaskSnowMask = false;
#     }else{addPixelQA = false;}
#   // Get Landsat image collection
#   var ls = getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
#     toaOrSR,includeSLCOffL7,defringeL5,addPixelQA);
  
#   // Apply relevant cloud masking methods
#   if(applyCloudScore){
#     print('Applying cloudScore');
#     ls = applyCloudScoreAlgorithm(ls,landsatCloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels); 
    
#   }
  
#   if(applyFmaskCloudMask){
#     print('Applying Fmask cloud mask');
#     ls = ls.map(function(img){return cFmask(img,'cloud')});
#   }
  
#   if(applyTDOM){
#     print('Applying TDOM');
#     //Find and mask out dark outliers
#     ls = simpleTDOM2(ls,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);
#   }
#   if(applyFmaskCloudShadowMask){
#     print('Applying Fmask shadow mask');
#     ls = ls.map(function(img){return cFmask(img,'shadow')});
#   }
#   if(applyFmaskSnowMask){
#     print('Applying Fmask snow mask');
#     ls = ls.map(function(img){return cFmask(img,'snow')});
#   }
  
  
  
  
#   // Add common indices- can use addIndices for comprehensive indices 
#   //or simpleAddIndices for only common indices
#   ls = ls.map(simpleAddIndices)
#           .map(getTasseledCap)
#           .map(simpleAddTCAngles);
  
  
  
#   return ls;
# }
# ///////////////////////////////////////////////////////////////////
# //Wrapper function for getting Sentinel2 imagery
# function getProcessedSentinel2Scenes(studyArea,startYear,endYear,startJulian,endJulian,
#   applyQABand,applyCloudScore,applyShadowShift,applyTDOM,
#   cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,
#   cloudHeights,
#   zScoreThresh,shadowSumThresh,
#   contractPixels,dilatePixels
#   ){
  
#   // Prepare dates
#   //Wrap the dates if needed
#   var wrapOffset = 0;
#   if (startJulian > endJulian) {
#     wrapOffset = 365;
#   }
#   var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
#   var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1+wrapOffset,'day');
#   print('Start and end dates:', startDate, endDate);

  
#   // Get Sentinel2 image collection
#   var s2s = getS2(studyArea,startDate,endDate,startJulian,endJulian)
#   // Map.addLayer(s2s.median().reproject('EPSG:32612',null,30),{min:0.05,max:0.4,bands:'swir1,nir,red'});
  
#   if(applyQABand){
#     print('Applying QA band cloud mask');
#     s2s = s2s.map(maskS2clouds);
#     // Map.addLayer(s2s.mosaic(),{min:0.05,max:0.4,bands:'swir1,nir,red'},'QA cloud masked');
  
#   }
#   if(applyCloudScore){
#     print('Applying cloudScore');
#      s2s = applyCloudScoreAlgorithm(s2s,sentinel2CloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,performCloudScoreOffset);
#     // Map.addLayer(s2s.mosaic(),{min:0.05,max:0.4,bands:'swir1,nir,red'},'Cloud score cloud masked');
#   }
#   if(applyShadowShift){
#     print('Applying shadow shift');
#     s2s = s2s.map(function(img){return projectShadowsWrapper(img,cloudScoreThresh,shadowSumThresh,contractPixels,dilatePixels,cloudHeights)});
#     // Map.addLayer(s2s.mosaic(),{min:0.05,max:0.4,bands:'swir1,nir,red'},'shadow shift shadow masked');
#   }
#   if(applyTDOM){
#     print('Applying TDOM');
#     s2s = simpleTDOM2(s2s,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);
#     // Map.addLayer(s2s.mosaic(),{min:0.05,max:0.4,bands:'swir1,nir,red'},'TDOM shadow masked');
#   }
  
  
 
  
  
#   // Add common indices- can use addIndices for comprehensive indices 
#   //or simpleAddIndices for only common indices
#   // s2s = s2s.map(simpleAddIndices)
#   //         .map(getTasseledCap)
#   //         .map(simpleAddTCAngles);
  
  
  
#   return s2s;
# }
# /////////////////////////////////////////////////////////////////////
# //Wrapper function for getting Landsat imagery
# function getSentinel2Wrapper(studyArea,startYear,endYear,startJulian,endJulian,
#   timebuffer,weights,compositingMethod,
#   applyQABand,applyCloudScore,applyShadowShift,applyTDOM,
#   cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,
#   cloudHeights,
#   zScoreThresh,shadowSumThresh,
#   contractPixels,dilatePixels,
#   correctIllumination,correctScale,
#   exportComposites,outputName,exportPathRoot,crs,transform,scale){
  
#   var s2s = getProcessedSentinel2Scenes(studyArea,startYear,endYear,startJulian,endJulian,
#   applyQABand,applyCloudScore,applyShadowShift,applyTDOM,
#   cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,
#   cloudHeights,
#   zScoreThresh,shadowSumThresh,
#   contractPixels,dilatePixels
#   );
  
  
  
#   // // Add zenith and azimuth
#   // if (correctIllumination){
#   //   s2s = s2s.map(function(img){
#   //     return addZenithAzimuth(img,'TOA',{'TOA':'MEAN_SOLAR_ZENITH_ANGLE'},{'TOA':'MEAN_SOLAR_AZIMUTH_ANGLE'});
#   //   });
#   // }
 
#   // Add common indices- can use addIndices for comprehensive indices 
#   //or simpleAddIndices for only common indices
#   s2s = s2s.map(simpleAddIndices)
#           .map(getTasseledCap)
#           .map(simpleAddTCAngles);
  
#   // Create composite time series
#   var ts = compositeTimeSeries(s2s,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingMethod);
  
  
#   // Correct illumination
#   // if (correctIllumination){
#   //   var f = ee.Image(ts.first());
#   //   Map.addLayer(f,vizParamsFalse,'First-non-illuminated',false);
  
#   //   print('Correcting illumination');
#   //   ts = ts.map(illuminationCondition)
#   //     .map(function(img){
#   //       return illuminationCorrection(img, correctScale,studyArea,[ 'blue', 'green', 'red','nir','swir1', 'swir2']);
#   //     });
#   //   var f = ee.Image(ts.first());
#   //   Map.addLayer(f,vizParamsFalse,'First-illuminated',false);
#   // }
  
#   //Export composites
#   if(exportComposites){// Export composite collection
  
#     var exportBands = ['cb', 'blue', 'green', 'red', 're1','re2','re3','nir', 'nir2', 'waterVapor', 'cirrus','swir1', 'swir2'];
#     exportCompositeCollection(exportPathRoot,outputName,studyArea,crs,transform,scale,
#     ts,startYear,endYear,startJulian,endJulian,compositingMethod,timebuffer,exportBands,'TOA',weights,
#                   applyCloudScore, 'NA',applyTDOM,'NA','NA','NA',correctIllumination,null);
#   }
  
#   return [s2s,ts];
# }
# //////////////////////////////////////////////////////////
# //Harmonic regression
# ////////////////////////////////////////////////////////////////////
# //Function to give year.dd image and harmonics list (e.g. [1,2,3,...])
# function getHarmonicList(yearDateImg,transformBandName,harmonicList){
#     var t= yearDateImg.select([transformBandName]);
#     var selectBands = ee.List.sequence(0,harmonicList.length-1);
    
#     var sinNames = harmonicList.map(function(h){
#       var ht = h*100;
#       return ee.String('sin_').cat(ht.toString()).cat('_').cat(transformBandName);
#     });
#     var cosNames = harmonicList.map(function(h){
#       var ht =h*100;
#       return ee.String('cos_').cat(ht.toString()).cat('_').cat(transformBandName);
#     });
    
#     // var sinCosNames = harmonicList.map(function(h){
#     //   var ht =h*100
#     //   return ee.String('sin_x_cos_').cat(ht.toString()).cat('_').cat(transformBandName)
#     // })
    
#     var multipliers = ee.Image(harmonicList).multiply(ee.Number(Math.PI).float()) 
#     var sinInd = (t.multiply(ee.Image(multipliers))).sin().select(selectBands,sinNames).float()
#     var cosInd = (t.multiply(ee.Image(multipliers))).cos().select(selectBands,cosNames).float();
#     // var sinCosInd = sinInd.multiply(cosInd).select(selectBands,sinCosNames);
    
#     return yearDateImg.addBands(sinInd.addBands(cosInd));//.addBands(sinCosInd)
#   }
# //////////////////////////////////////////////////////
# //Takes a dependent and independent variable and returns the dependent, 
# // sin of ind, and cos of ind
# //Intended for harmonic regression
# function getHarmonics2(collection,transformBandName,harmonicList,detrend){
#   if(detrend === undefined || detrend === null){detrend = false}
  
#   var depBandNames = ee.Image(collection.first()).bandNames().remove(transformBandName);
#   var depBandNumbers = depBandNames.map(function(dbn){
#     return depBandNames.indexOf(dbn);
#   });
  
#   var out = collection.map(function(img){
#     var outT = getHarmonicList(img,transformBandName,harmonicList)
#     .copyProperties(img,['system:time_start','system:time_end']);
#     return outT;
#   });
  
#   if(!detrend){
#     var outBandNames = ee.Image(out.first()).bandNames().removeAll(['year'])
#     out = out.select(outBandNames)
#   }
  
#   // Map.addLayer(out)
#   var indBandNames = ee.Image(out.first()).bandNames().removeAll(depBandNames);
#   var indBandNumbers = indBandNames.map(function(ind){
#     return ee.Image(out.first()).bandNames().indexOf(ind);
#   });
  
#   out = out.set({'indBandNames':indBandNames,'depBandNames':depBandNames,
#                 'indBandNumbers':indBandNumbers,'depBandNumbers':depBandNumbers
#   });
  
#   return out;
# }
# ////////////////////////////////////////////////////////
# ////////////////////////////////////////////////////////////////
# //Simplifies the use of the robust linear regression reducer
# //Assumes the dependent is the first band and all subsequent bands are independents
# function newRobustMultipleLinear2(dependentsIndependents){//,dependentBands,independentBands){
#   //Set up the band names

#   var dependentBands = ee.List(dependentsIndependents.get('depBandNumbers'));
#   var independentBands = ee.List(dependentsIndependents.get('indBandNumbers'));
#   var bns = ee.Image(dependentsIndependents.first()).bandNames();
#   var dependents = ee.List(dependentsIndependents.get('depBandNames'));
#   var independents = ee.List(dependentsIndependents.get('indBandNames'));
  
#   // var dependent = bns.slice(0,1);
#   // var independents = bns.slice(1,null)
#   var noIndependents = independents.length().add(1);
#   var noDependents = dependents.length();
  
#   var outNames = ee.List(['intercept']).cat(independents);
 
#   //Add constant band for intercept and reorder for 
#   //syntax: constant, ind1,ind2,ind3,indn,dependent
#   var forFit = dependentsIndependents.map(function(img){
#     var out = img.addBands(ee.Image(1).select([0],['constant']));
#     out = out.select(ee.List(['constant',independents]).flatten());
#     return out.addBands(img.select(dependents));
#   });
  
#   //Apply reducer, and convert back to image with respective bandNames
#   var reducerOut = forFit.reduce(ee.Reducer.linearRegression(noIndependents,noDependents));
#   // var test = forFit.reduce(ee.Reducer.robustLinearRegression(noIndependents,noDependents,0.2))
#   // var resids = test
#   // .select([1],['residuals']).arrayFlatten([dependents]);
#   // Map.addLayer(resids,{},'residsImage');
#   // Map.addLayer(reducerOut.select([0]),{},'coefficients');
#   // Map.addLayer(test.select([1]),{},'tresiduals');
#   // Map.addLayer(reducerOut.select([1]),{},'roresiduals');
#   reducerOut = reducerOut
#   .select([0],['coefficients']).arrayTranspose().arrayFlatten([dependents,outNames]);
#   reducerOut = reducerOut
#   .set({'noDependents':ee.Number(noDependents),
#   'modelLength':ee.Number(noIndependents)
    
#   });
  
#   return reducerOut;
# };


# /////////////////////////////////////////////////////////////////
# //Code for finding the date of peak of green
# //Also converts it to Julian day, month, and day of month
# var monthRemap =[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12 ];
# var monthDayRemap = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31 ];
# var julianDay = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 295, 296, 297, 298, 299, 300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 331, 332, 333, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 365 ];


# //Function for getting the date of the peak of veg vigor- can handle bands negatively correlated to veg in
# //changeDirDict dictionary above
# function getPeakDate(coeffs,peakDirection){
#   if(peakDirection === null || peakDirection === undefined){peakDirection = 1};
  
#   var sin = coeffs.select([0]);
#   var cos = coeffs.select([1]);
  
#   //Find where in cycle slope is zero
#   var greenDate = ((sin.divide(cos)).atan()).divide(2*Math.PI).rename(['peakDate']);
#   var greenDateLater = greenDate.add(0.5);
#   //Check which d1 slope = 0 is the max by predicting out the value
#   var predicted1 = coeffs.select([0])
#                   .add(sin.multiply(greenDate.multiply(2*Math.PI).sin()))
#                   .add(cos.multiply(greenDate.multiply(2*Math.PI).cos()))
#                   .rename('predicted')
#                   .multiply(ee.Image.constant(peakDirection))
#                   .addBands(greenDate);
#   var predicted2 = coeffs.select([0])
#                   .add(sin.multiply(greenDateLater.multiply(2*Math.PI).sin()))
#                   .add(cos.multiply(greenDateLater.multiply(2*Math.PI).cos()))
#                   .rename('predicted')
#                   .multiply(ee.Image.constant(peakDirection))
#                   .addBands(greenDateLater);
#   var finalGreenDate = ee.ImageCollection([predicted1,predicted2]).qualityMosaic('predicted').select(['peakDate']).rename(['peakJulianDay']);
  
#   finalGreenDate = finalGreenDate.where(finalGreenDate.lt(0), greenDate.add(1)).multiply(365).int16();
  
#   //Convert to month and day of month
#   var greenMonth = finalGreenDate.remap(julianDay,monthRemap).rename(['peakMonth']);
#   var greenMonthDay = finalGreenDate.remap(julianDay,monthDayRemap).rename(['peakDayOfMonth']);
#   var greenStack = finalGreenDate.addBands(greenMonth).addBands(greenMonthDay);
#   return greenStack;
#   // Map.addLayer(greenStack,{'min':1,'max':12},'greenMonth',false);
# }
# //Function for getting left sum under the curve for a single growing season
# //Takes care of normalization by forcing the min value along the curve 0
# //by taking the amplitude as the intercept
# //Assumes the sin and cos coeffs are the harmCoeffs
# //t0 is the start time (defaults to 0)(min value should be but doesn't have to be 0)
# //t1 is the end time (defaults to 1)(max value should be but doesn't have to be 1)
# //
# //Example of what this code is doing can be found here:
# //  http://www.wolframalpha.com/input/?i=integrate+0.15949074923992157+%2B+-0.08287599*sin(2+PI+T)+%2B+-0.11252010613*cos(2+PI+T)++from+0+to+1
# function getAreaUnderCurve(harmCoeffs,t0,t1){
#   if(t0 === null || t0 === undefined){t0 = 0}
#   if(t1 === null || t1 === undefined){t1 = 1}
  
#   //Pull apart the model
#   var amplitude = harmCoeffs.select([1]).hypot(harmCoeffs.select([0]));
#   var intereceptNormalized = amplitude;//When making the min 0, the intercept becomes the amplitude (the hypotenuse)
#   var sin = harmCoeffs.select([0]);
#   var cos = harmCoeffs.select([1]);
  
#   //Find the sum from - infinity to 0
#   var sum0 = intereceptNormalized.multiply(t0)
#             .subtract(sin.divide(2*Math.PI).multiply(Math.sin(2*Math.PI*t0)))
#             .add(cos.divide(2*Math.PI).multiply(Math.cos(2*Math.PI*t0)));
#   //Find the sum from - infinity to 1
#   var sum1 = intereceptNormalized.multiply(t1)
#             .subtract(sin.divide(2*Math.PI).multiply(Math.sin(2*Math.PI*t1)))
#             .add(cos.divide(2*Math.PI).multiply(Math.cos(2*Math.PI*t1)));
#   //Find the difference
#   var leftSum = sum1.subtract(sum0).rename(['AUC']);
#   return leftSum;
# }
# ///////////////////////////////////////////////
# function getPhaseAmplitudePeak(coeffs,t0,t1){
#   if(t0 === null || t0 === undefined){t0 = 0}
#   if(t1 === null || t1 === undefined){t1 = 1}
#   //Parse the model
#   var bandNames = coeffs.bandNames();
#   var bandNumber = bandNames.length();
#   var noDependents = ee.Number(coeffs.get('noDependents'));
#   var modelLength = ee.Number(coeffs.get('modelLength'));
#   var interceptBands = ee.List.sequence(0,bandNumber.subtract(1),modelLength);
  
#   var models = ee.List.sequence(0,noDependents.subtract(1));
  
#   var parsedModel =models.map(function(mn){
#     mn = ee.Number(mn);
#     return bandNames.slice(mn.multiply(modelLength),mn.multiply(modelLength).add(modelLength));
#   });
  
#   // print('Parsed harmonic regression model',parsedModel);

#   //Iterate across models to convert to phase, amplitude, and peak
#   var phaseAmplitude =parsedModel.map(function(pm){
#       pm = ee.List(pm);
#       var modelCoeffs = coeffs.select(pm);
      
#       var intercept = modelCoeffs.select('.*_intercept');
#       var harmCoeffs = modelCoeffs.select('.*_200_year');
#       var outName = ee.String(ee.String(pm.get(1)).split('_').get(0));
#       var sign = ee.Dictionary(changeDirDict).get(outName);
      
 
  
#       var amplitude = harmCoeffs.select([1]).hypot(harmCoeffs.select([0]))
#                     .multiply(2)
#                     .rename([outName.cat('_amplitude')]);
#       var phase = harmCoeffs.select([0]).atan2(harmCoeffs.select([1]))
#                     .unitScale(-Math.PI, Math.PI)
#                     .rename([outName.cat('_phase')]);
      
#       //Get peak date info
#       var peakDate = getPeakDate(harmCoeffs,sign);
#       var peakDateBandNames = peakDate.bandNames();
#       peakDateBandNames = peakDateBandNames.map(function(bn){return outName.cat(ee.String('_').cat(ee.String(bn)))});
      
#       //Get the left sum
#       var leftSum = getAreaUnderCurve(harmCoeffs,t0,t1);
#       var leftSumBandNames = leftSum.bandNames();
#       leftSumBandNames = leftSumBandNames.map(function(bn){return outName.cat(ee.String('_').cat(ee.String(bn)))});
     
#       return amplitude
#             .addBands(phase)
#             .addBands(peakDate.rename(peakDateBandNames))
#             .addBands(leftSum.rename(leftSumBandNames));
    
#     });
  
#     //Convert to an image
#     phaseAmplitude = ee.ImageCollection.fromImages(phaseAmplitude);
    
#     phaseAmplitude = ee.Image(collectionToImage(phaseAmplitude)).float()
#           .copyProperties(coeffs,['system:time_start']);
#     // print('pa',phaseAmplitude);
#     return phaseAmplitude;


# }
# /////////////////////////////////////////////////////
# //Function for applying harmonic regression model to set of predictor sets
# function newPredict(coeffs,harmonics){
#   //Parse the model
#   var bandNames = coeffs.bandNames();
#   var bandNumber = bandNames.length();
#   var noDependents = ee.Number(coeffs.get('noDependents'));
#   var modelLength = ee.Number(coeffs.get('modelLength'));
#   var interceptBands = ee.List.sequence(0,bandNumber.subtract(1),modelLength);
#   var timeBand = ee.List(harmonics.get('indBandNames')).get(0);
#   var actualBands = harmonics.get('depBandNumbers');
#   var indBands = harmonics.get('indBandNumbers');
#   var indBandNames = ee.List(harmonics.get('indBandNames'));
#   var depBandNames = ee.List(harmonics.get('depBandNames'));
#   var predictedBandNames = depBandNames.map(function(depbnms){return ee.String(depbnms).cat('_predicted')});
#   var predictedBandNumbers = ee.List.sequence(0,predictedBandNames.length().subtract(1));

#   var models = ee.List.sequence(0,noDependents.subtract(1));
#   var parsedModel =models.map(function(mn){
#     mn = ee.Number(mn);
#     return bandNames.slice(mn.multiply(modelLength),mn.multiply(modelLength).add(modelLength));
#   });
#   // print('Parsed harmonic regression model',parsedModel,predictedBandNames);
  
#   //Apply parsed model
#   var predicted =harmonics.map(function(img){
#     var time = img.select(timeBand);
#     var actual = img.select(actualBands).float();
#     var predictorBands = img.select(indBandNames);
    
#     //Iterate across each model for each dependent variable
#     var predictedList =parsedModel.map(function(pm){
#       pm = ee.List(pm);
#       var modelCoeffs = coeffs.select(pm);
#       var outName = ee.String(pm.get(1)).cat('_predicted');
#       var intercept = modelCoeffs.select(modelCoeffs.bandNames().slice(0,1));
#       var others = modelCoeffs.select(modelCoeffs.bandNames().slice(1,null));
    
#       predicted = predictorBands.multiply(others).reduce(ee.Reducer.sum()).add(intercept).float();
#       return predicted.float();
    
#     });
#     //Convert to an image
#     predictedList = ee.ImageCollection.fromImages(predictedList);
#     var predictedImage = collectionToImage(predictedList).select(predictedBandNumbers,predictedBandNames);
    
#     //Set some metadata
#     var out = actual.addBands(predictedImage.float())
#     .copyProperties(img,['system:time_start','system:time_end']);
#     return out;
    
#   });
#   predicted = ee.ImageCollection(predicted);
#   // var g = Chart.image.series(predicted,plotPoint,ee.Reducer.mean(),90);
#   // print(g);
#   // Map.addLayer(predicted,{},'predicted',false);
  
#   return predicted;
# }
# //////////////////////////////////////////////////////
# //Function to get a dummy image stack for synthetic time series
# function getDateStack(startYear,endYear,startJulian,endJulian,frequency){
#   var years = ee.List.sequence(startYear,endYear);
#   var dates = ee.List.sequence(startJulian,endJulian,frequency);
#   //print(startYear,endYear,startJulian,endJulian)
#   var dateSets = years.map(function(yr){
#     var ds = dates.map(function(d){
#       return ee.Date.fromYMD(yr,1,1).advance(d,'day');
#     });
#     return ds;
#   });
#   var l = range(1,indexNames.length+1);
#   l = l.map(function(i){return i%i});
#   var c = ee.Image(l).rename(indexNames);
#   c = c.divide(c);
 
#   dateSets = dateSets.flatten();
#   var stack = dateSets.map(function(dt){
#     dt = ee.Date(dt);
#     var y = dt.get('year');
#     var d = dt.getFraction('year');
#     var i = ee.Image(y.add(d)).float().select([0],['year']);
    
#     i = c.addBands(i).float()
#     .set('system:time_start',dt.millis())
#     .set('system:time_end',dt.advance(frequency,'day').millis());
#     return i;
    
#   });
#   stack = ee.ImageCollection.fromImages(stack);
#   return stack;
# }



# ////////////////////////////////////////////////////////////////////
# function getHarmonicCoefficientsAndFit(allImages,indexNames,whichHarmonics,detrend){
#   if(detrend === undefined || detrend === null){detrend = false}
#   if(whichHarmonics === undefined || whichHarmonics === null){whichHarmonics = [2]}
  
#   //Select desired bands
#   var allIndices = allImages.select(indexNames);
  
#   //Add date band
#   if(detrend){
#     allIndices = allIndices.map(addDateBand);
#   }
#   else{
#     allIndices = allIndices.map(addYearFractionBand);
#   }
  
#   //Add independent predictors (harmonics)
#   var withHarmonics = getHarmonics2(allIndices,'year',whichHarmonics,detrend);
#   var withHarmonicsBns = ee.Image(withHarmonics.first()).bandNames().slice(indexNames.length+1,null);
  
#   //Optionally chart the collection with harmonics
#   // var g = Chart.image.series(withHarmonics.select(withHarmonicsBns),plotPoint,ee.Reducer.mean(),30);
#   // print(g);
  
#   //Fit a linear regression model
#   var coeffs = newRobustMultipleLinear2(withHarmonics);
  
#   //Can visualize the phase and amplitude if only the first ([2]) harmonic is chosen
#   // if(whichHarmonics == 2){
#   //   var pa = getPhaseAmplitude(coeffs);
#   // // Turn the HSV data into an RGB image and add it to the map.
#   // var seasonality = pa.select([1,0]).addBands(allIndices.select([indexNames[0]]).mean()).hsvToRgb();
#   // // Map.addLayer(seasonality, {}, 'Seasonality');
#   // }
  
  
  
#   // Map.addLayer(coeffs,{},'Harmonic Regression Coefficients',false);
#   var predicted = newPredict(coeffs,withHarmonics);
#   return [coeffs,predicted];
# }
# ///////////////////////////////////////////////////////////////
# // function getHarmonicFit(allImages,indexNames,whichHarmonics){
# //   getHarmonicCoefficients(allImages,indexNames,whichHarmonics)
# //   // newPredict(coeffs,withHarmonics)
  
# // //   var dateStack = getDateStack(startDate.get('year'),endDate.get('year'),startDate.getFraction('year').multiply(365),endDate.getFraction('year').multiply(365),syntheticFrequency);
# // //   var synthHarmonics = getHarmonics2(dateStack,'year',whichHarmonics)
# // //   var predictedBandNames = indexNames.map(function(nm){
# // //     return ee.String(nm).cat('_predicted')
# // //   })
# // //   var syntheticStack = ee.ImageCollection(newPredict(coeffs,synthHarmonics)).select(predictedBandNames,indexNames)
 
# // //   //Filter out and visualize synthetic test image
# // //   Map.addLayer(syntheticStack.median(),vizParams,'Synthetic All Images Composite',false);
# // //   var test1ImageSynth = syntheticStack.filterDate(test1Start,test1End);
# // //   Map.addLayer(test1ImageSynth,vizParams,'Synthetic Test 1 Composite',false);
# // //   var test2ImageSynth = syntheticStack.filterDate(test2Start,test2End);
# // //   Map.addLayer(test2ImageSynth,vizParams,'Synthetic Test 2 Composite',false);
  
  
# // //   //Export image for download
# // //   var forExport = setNoData(coeffs.clip(sa),outNoData);
# // //   Map.addLayer(forExport,vizParamsCoeffs,'For Export',false);
# // //   Export.image(forExport,exportName,{'crs':crs,'region':regionJSON,'scale':exportRes,'maxPixels':1e13})
  
# // //   Export.table(ee.FeatureCollection([metaData]),exportName + '_metadata');
# // //   return syntheticStack
# // }
# ////////////////////////////////////////////////////////////////////////////////
# //Wrapper function to get climate data
# // Supports:
# // NASA/ORNL/DAYMET_V3
# // UCSB-CHG/CHIRPS/DAILY (precipitation only)
# //and possibly others
# function getClimateWrapper(collectionName,studyArea,startYear,endYear,startJulian,endJulian,
#   timebuffer,weights,compositingReducer,
#   exportComposites,exportPathRoot,crs,transform,scale,exportBands){
    
#   // Prepare dates
#   //Wrap the dates if needed
#   var wrapOffset = 0;
#   if (startJulian > endJulian) {
#     wrapOffset = 365;
#   }
#   var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
#   var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1+wrapOffset,'day');
#   print('Start and end dates:', startDate, endDate);
#   print('Julian days are:',startJulian,endJulian);
#   //Get climate data
#   var c = ee.ImageCollection(collectionName)
#           .filterBounds(studyArea.bounds())
#           .filterDate(startDate,endDate)
#           .filter(ee.Filter.calendarRange(startJulian,endJulian));
  
#   // Create composite time series
#   var ts = compositeTimeSeries(c,startYear,endYear,startJulian,endJulian,timebuffer,weights,null,compositingReducer);
  
#   if(exportComposites){
#     //Set up export bands if not specified
#     if(exportBands === null || exportBands === undefined){
#       exportBands = ee.Image(ts.first()).bandNames();
#     }
#     print('Export bands are:',exportBands);
#     //Export collection
#     exportCollection(exportPathRoot,collectionName,studyArea, crs,transform,scale,
#       ts,startYear,endYear,startJulian,endJulian,compositingReducer,timebuffer,exportBands);
     
#   }
  
#   return ts;
#   }
# //////////////////////////////////////////
# /////////////////////////////////////////////////////////////////////
# //Adds absolute difference from a specified band summarized by a provided percentile
# //Intended for custom sorting across collections
# var addAbsDiff = function(inCollection, qualityBand, percentile,sign){
#   var bestQuality = inCollection.select([qualityBand]).reduce(ee.Reducer.percentile([percentile]));
#   var out = inCollection.map(function(image) {
#     var delta = image.select([qualityBand]).subtract(bestQuality).abs().multiply(sign);
#     return image.addBands(delta.select([0], ['delta']));
#   });
#   return out
# };
# ////////////////////////////////////////////////////////////
# //Method for applying the qualityMosaic function using a specified percentile
# //Useful when the max of the quality band is not what is wanted
# var customQualityMosaic = function(inCollection,qualityBand,percentile){
#   //Add an absolute difference from the specified percentile
#   //This is inverted for the qualityMosaic function to properly prioritize
#   var inCollectionDelta = addAbsDiff(inCollection, qualityBand, percentile,-1);
  
#   //Apply the qualityMosaic function
#   return inCollectionDelta.qualityMosaic('delta');

# };
# //////////////////////////////////////////////////////////////////////////
# // END FUNCTIONS
# ////////////////////////////////////////////////////////////////////////////////
# exports.sieve = sieve;
# exports.setNoDate = setNoData;
# exports.addYearBand = addYearBand;
# exports.addDateBand = addDateBand;
# exports.collectionToImage = collectionToImage;
# exports.getImageCollection = getImageCollection;
# exports.getS2 = getS2;
# exports.vizParamsFalse = vizParamsFalse;
# exports.vizParamsTrue = vizParamsTrue;
# exports.landsatCloudScore = landsatCloudScore;
# exports.sentinel2CloudScore = sentinel2CloudScore;
# exports.applyCloudScoreAlgorithm = applyCloudScoreAlgorithm;
# exports.cFmask = cFmask;
# exports.simpleTDOM2 = simpleTDOM2;
# exports.medoidMosaicMSD = medoidMosaicMSD;
# exports.addIndices = addIndices;
# exports.addSAVIandEVI = addSAVIandEVI;
# exports.simpleAddIndices = simpleAddIndices;
# exports.getTasseledCap = getTasseledCap;
# exports.simpleGetTasseledCap = simpleGetTasseledCap;
# exports.simpleAddTCAngles = simpleAddTCAngles;
# exports.compositeTimeSeries = compositeTimeSeries;
# exports.addZenithAzimuth = addZenithAzimuth;
# exports.illuminationCorrection = illuminationCorrection;
# exports.illuminationCondition = illuminationCondition;
# exports.addTCAngles = addTCAngles;
# exports.simpleAddTCAngles = simpleAddTCAngles;
# exports.exportCompositeCollection = exportCompositeCollection;
# exports.getLandsatWrapper = getLandsatWrapper;
# exports.getProcessedLandsatScenes = getProcessedLandsatScenes;

# exports.getProcessedSentinel2Scenes = getProcessedSentinel2Scenes;
# exports.getSentinel2Wrapper =getSentinel2Wrapper;
# exports.getModisData = getModisData;
# exports.modisCloudScore = modisCloudScore;
# exports.despikeCollection = despikeCollection;
# exports.exportToAssetWrapper = exportToAssetWrapper;
# exports.exportToAssetWrapper2 = exportToAssetWrapper2;
# exports.exportCollection = exportCollection;
# exports.joinCollections = joinCollections;
# exports.listToString = listToString;
# exports.harmonizationRoy = harmonizationRoy;
# exports.harmonizationChastain = harmonizationChastain;
# exports.fillEmptyCollections = fillEmptyCollections;

# exports.getHarmonicCoefficientsAndFit = getHarmonicCoefficientsAndFit;
# exports.getPhaseAmplitudePeak = getPhaseAmplitudePeak;
# exports.getAreaUnderCurve = getAreaUnderCurve;

# exports.getClimateWrapper = getClimateWrapper;
# exports.exportCollection = exportCollection;
# exports.changeDirDict = changeDirDict;
# exports.addSoilIndices = addSoilIndices;

# exports.customQualityMosaic  = customQualityMosaic;

