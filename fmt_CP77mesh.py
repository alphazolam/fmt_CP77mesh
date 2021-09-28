# fmt_cp77mesh.py
# CyberPunk 2077 mesh and texture import / export 
# Authors: alphaZomega, Joschka, Akderebur 
# Version 1.6a
# September 15, 2021

from inc_noesis import *
from collections import namedtuple
from ctypes import cdll, c_char_p, c_int64, c_long, create_string_buffer
import re
import math
import os
import copy
from shutil import copyfile


#									Location of Oodle DLL (will check next to this py file if not found):
dllLocation  = 						"C:\\GOG\\Cyberpunk 2077\\bin\x64\\oo2ext_7_win64.dll"
#									Set this to your folder containing basegame_4_gamedata and basegame_3_nightcity, or leave it blank to auto-detect:
extractedDir = 						""

#Mesh options:
meshScale = 100						#scale model to this size
bCompress = True					#If put to true, the model data will be compressed and decompressed with the Oodle DLL
bHighestLODOnly = True   	  		#if put to True, the low poly meshes will be loaded as separate models
bLoadRigFile = False 	       		#if put to True, enables user-selection of a paired rig file with the skeleton hierarchy info
bAutoDetectRig = True				#if put to True, the plugin will search for and load the closest-named .rig file to the mesh filename
bParentToRootIfNoParent = True		#if put to True, unparented bones will be parented to Root
bReadTangents = False				#if put to True, tangents are read from the file and applied to the model
bImportGarmentMesh = False			#if put to True, garment meshes will be imported along with the regular mesh
bImportExportDamageMeshes = True	#if put to True, vehicle damage meshes will be imported along with the regular mesh, and will be exported if they are detected in the fbx
bImportMorphtargets	= False			#if put to True, morphs will be imported with morphtarget files (currently broken)**
bVertexColors	= True				#if put to True, vertex colors will be read and applied to the model on import, and will be written on export
bExportAllBuffers = True			#if put to True, all buffers will be exported when saving meshes or textures, rather than just the ones modified
bConnectRigToRoot = False			#if put to True, rigs will be assembled in such a way that a connection is always made to the Noesis_Root bone

bFlipImage = False					#if put to True, textures and mesh UVs are flipped upright on imported textures and meshes, then flipped upside down again on export
bManualDimensions = False			#if put to True, the user can set their own texture resolution on import
bManualCompression = False			#if put to True, the user can set their own texture compression on import	
bReadAsSigned = True				#if put to True, textures will be decoded as signed data, making normal maps yellow instead of blue

try:
	lib = cdll.LoadLibrary(dllLocation)
except:
	try:
		dllLocation = noesis.getPluginsPath() + 'python\\oo2ext_7_win64.dll'
		lib = cdll.LoadLibrary(dllLocation) #look for Oodle DLL in Noesis plugins folder
	except:
		print ("Could not load Oodle DLL! Cyberpunk 2077 Compression is disabled")
		bCompress = False

def registerNoesisTypes():
	handle = noesis.register("CyberPunk 2077 mesh [PC]",".mesh;.cookedapp")
	noesis.setHandlerTypeCheck(handle, checkType)
	noesis.setHandlerLoadModel(handle, LoadModel)	
	noesis.setHandlerWriteModel(handle, meshWriteModel)
	noesis.setTypeExportOptions(handle, "-noanims")
	noesis.addOption(handle, "-cp77optimize", "Optimizes vertices and faces on mesh import", 0)
	noesis.addOption(handle, "-rig", "Exports new .rig file based on bones from your FBX", 0)
	noesis.addOption(handle, "-bones", "Create copy of picked mesh with skeleton from FBX", 0)
	noesis.addOption(handle, "-meshbones", "Writes new mesh with skeleton from FBX", 0)
	noesis.addOption(handle, "-meshfile", "Set mesh file to export over", noesis.OPTFLAG_WANTARG)
	handle = noesis.register("CyberPunk 2077 mesh [PC]",".morphtarget")
	noesis.setHandlerTypeCheck(handle, checkType)
	noesis.setHandlerLoadModel(handle, LoadModel)	
	noesis.setHandlerWriteModel(handle, meshWriteModel)
	noesis.setTypeExportOptions(handle, "-noanims")
	noesis.addOption(handle, "-cp77optimize", "Optimizes vertices and faces on morphtarget import", 0)
	noesis.addOption(handle, "-rig", "Exports new .rig file based on bones from your FBX", 0)
	noesis.addOption(handle, "-bones", "Create copy of picked mesh with skeleton from FBX", 0)
	noesis.addOption(handle, "-meshbones", "Writes new mesh with skeleton from FBX", 0)
	noesis.addOption(handle, "-meshfile", "Set mesh file to export over", noesis.OPTFLAG_WANTARG)
	noesis.addOption(handle, "-vf", "Saves morphtarget meshes using a specific vertex factory", noesis.OPTFLAG_WANTARG)
	handle = noesis.register("CyberPunk 2077 Texture [PC]", ".xbm;.mi;.cp77tex")
	noesis.setHandlerTypeCheck(handle, checkType)
	noesis.setHandlerLoadRGBA(handle, xbmLoadDDS)
	handle = noesis.register("CyberPunk 2077 Texture [PC]", ".cp77tex")
	noesis.addOption(handle, "-texfile", "Set CP77tex file to export over", noesis.OPTFLAG_WANTARG)
	noesis.setHandlerWriteRGBA(handle, xbmWriteRGBA)
	handle = noesis.register("CyberPunk 2077 Texture [PC]", ".mi")
	noesis.addOption(handle, "-texfile", "Set mi file to export over", noesis.OPTFLAG_WANTARG)
	noesis.setHandlerWriteRGBA(handle, xbmWriteRGBA)
	handle = noesis.register("CyberPunk 2077 Texture [PC]", ".xbm")
	noesis.addOption(handle, "-texfile", "Set xbm file to export over", noesis.OPTFLAG_WANTARG)
	noesis.setHandlerWriteRGBA(handle, xbmWriteRGBA)
	return 1

def checkType(data):
	bs = NoeBitStream(data)
	magic = bs.readUInt()
	if magic == 1462915651:
		return 1
	else: 
		print("Error: Unknown file magic: " + str(hex(magic) + " expected 'CR2W'!"))
		return 0

def readUShortAt(bs, readAt):
	pos = bs.tell()
	bs.seek(readAt)
	value = bs.readUShort()
	bs.seek(pos)
	return value
	
def readUIntAt(bs, readAt):
	pos = bs.tell()
	bs.seek(readAt)
	value = bs.readUInt()
	bs.seek(pos)
	return value
	
def readFloatAt(bs, readAt):
	pos = bs.tell()
	bs.seek(readAt)
	value = bs.readFloat()
	bs.seek(pos)
	return value
	
def writeFloatAt(bs, writeAt, float):
	pos = bs.tell()
	bs.seek(writeAt)
	bs.writeFloat(float)
	bs.seek(pos)
	
def writeUIntAt(bs, offset, value):
	pos = bs.tell()
	bs.seek(offset)
	bs.writeUInt(value)
	bs.seek(pos)
  
def magnitude(vector):  
    return math.sqrt(sum(pow(element, 2) for element in vector)) 

def copyBuffers(originalFile, ext, maxBuffers):
	#duplicates all buffers of mesh being modified for a complete export:
	for root, dirs, files in os.walk(os.path.dirname(originalFile)):
		for fileName in files:
			lowerName = fileName.lower()
			fileBufferNo = lowerName.split(".")
			try:
				fileBufferNo = int(fileBufferNo[len(fileBufferNo)-2])
				if fileBufferNo >= 0 and fileBufferNo <= maxBuffers and lowerName.endswith(".buffer") and os.path.join(root, lowerName.split(".")[0]) == "".join(originalFile.split(".")[:-1]) and lowerName.split(".")[1] == ext:
					bufferPath = os.path.join(root, lowerName)
					if (rapi.checkFileExists(bufferPath)):
						try:
							copyfile(bufferPath, bufferPath.replace(originalFile, rapi.getOutputName()))
							print ("Copied", rapi.getLocalFileName(bufferPath.replace(originalFile, rapi.getOutputName())))
						except:
							pass
			except:
				continue 
				


 
def GetCR2WBuffer(bs, buffers, ext="mesh", bufferNo=-1):
	
	def decompress(payload: bytes, size: int, output_size: int) -> bytes:
		oodle = cdll.LoadLibrary(dllLocation)
		output = create_string_buffer(output_size)
		#typedef long long (*OodleLZ_Decompress)(void* in, long long insz, void* out, long long outsz, long long a, long long b, long long c, void* d, void* e, void* f, void* g, void* h, void* i, long long j);
		ret = oodle.OodleLZ_Decompress( c_char_p(payload), c_int64(size), output, c_int64(output_size), c_int64(0), c_int64(0), c_int64(0), None, None, None, None, None, None, c_int64(3))
		
		if ret != output_size:
			print ("Buffer", bufferNo, "decompression failed! Returned size:", ret, "Actual size:", len(output))
		else:
			print ("Buffer", bufferNo, "decompression succeeded! Returned size:", ret, "Actual size:", len(output)) 
		return (ret, output.raw)
		
	if int(bufferNo) < 0:
		return NoeBitStream()
		
	output = (0, None)
	#Extract KARK buffer to create bitstream:
	if bCompress:
		if buffers[bufferNo].memSize == buffers[bufferNo].diskSize: #if already decompressed
			bs.seek(buffers[bufferNo].offset)
			output = (buffers[bufferNo].diskSize, bs.readBytes(buffers[bufferNo].diskSize))
			print ("Read already-decompressed Buffer", bufferNo)
		else:	
			payload_size = buffers[bufferNo].diskSize-8
			output_size = buffers[bufferNo].memSize
			bs.seek(buffers[bufferNo].offset+8)
			payload = bs.readBytes(payload_size)
			output = decompress(payload, payload_size, output_size)
		
	if output[0] == 0:
		#Grab correct paired buffer file
		thisName = rapi.getLocalFileName(rapi.getInputName()).lower()
		splits = thisName.split("__")
		dir = os.path.dirname(rapi.getInputName())
		for root, dirs, files in os.walk(dir):
			for fileName in files:
				lowerName = fileName.lower()
				if lowerName.endswith(ext + "." + str(bufferNo) + ".buffer") and lowerName.split(ext)[0] == thisName.split(ext)[0]:
					print("Detected Buffer: " + lowerName)
					return ( NoeBitStream(rapi.loadIntoByteArray(os.path.join(root, lowerName))))
	return NoeBitStream(output[1])
	
	
def WriteCR2WBuffer(buffers, buf, bufferNo):
	
	input_buffer = create_string_buffer(buf.getBuffer())
	input_size = buf.getSize()
	output_size = lib.OodleLZ_GetCompressedBufferSizeNeeded(c_int64(input_size))
	output = create_string_buffer(output_size)
	#typedef int WINAPI OodLZ_CompressFunc( int codec, uint8 *src_buf, size_t src_len, uint8 *dst_buf, int level, void *opts, size_t offs, size_t unused, void *scratch, size_t scratch_size);
	output_size = lib.OodleLZ_Compress( c_int64(8), input_buffer, c_int64(input_size), output, c_int64(9), None, None, None, None, None)
	compressedBytes = NoeBitStream()
	compressedBytes.writeUInt(1263681867) #KARK
	compressedBytes.writeUInt(input_size) #decompressed buffer size
	compressedBytes.writeBytes(bytes(output)[:output_size]) #crimp to size
	compressedBytes = compressedBytes.getBuffer()
	if output_size == 0:
		print ("Compression Failed! Reported Size: ", output_size, "Actual Size:", len(compressedBytes))
	else:
		print ("Compression Succeeded! Reported Size:", output_size, "Actual Size:", len(compressedBytes)-8)
	diff = output_size - (buffers[bufferNo].diskSize-8)
	
	buffers[bufferNo].data.writeBytes(compressedBytes)
	buffers[bufferNo].diskSize = buffers[bufferNo].data.getSize()
	buffers[bufferNo].memSize = buf.getSize()
	
	for i in range(len(buffers)):
		if buffers[i].offset > buffers[bufferNo].offset:
			buffers[i].offset += diff
	
	return buffers
	

def buildFlagFromNames(names, nameToIndex, padding, findSimilar=False, typeOrName=-1):
	flag = bytes()
	for n, name in enumerate(names):
		bFound = False
		if findSimilar and n == typeOrName:
			for cName in nameToIndex:
				if cName != "" and cName.lower().find(name) != -1 and cName.lower().find("\\") == -1:
					flag += (nameToIndex[cName]).to_bytes(2,byteorder='little')
					break
		if not bFound:
			try:
				flag += (nameToIndex[name]).to_bytes(2,byteorder='little')
			except:
				print(name, names)
	for i in range(padding):
		flag += b'\x00'
	return flag

def findFlag(bs, flag, maxOffset, skipFlag=0, skipFlag2=0):
	while bs.tell()+1 < bs.getSize()-1:
		checkPoint = bs.tell()
		temp = bs.readBytes(len(flag))
		if temp == flag:
			bs.seek(checkPoint)
			return True
		elif (temp == skipFlag or temp == skipFlag2) and readUIntAt(bs, bs.tell()+4) < bs.getSize() - bs.tell(): #(skipFlag != 0 and temp == skipFlag) or (skipFlag2 != 0 and temp == skipFlag2)
			skipSize = bs.readUInt()
			#print ("skipping", skipSize-4, "as read from", bs.tell()-4)
			bs.seek(skipSize-4, 1)
		else:
			bs.seek(checkPoint+1)
	return False
	
	
def ParseHeader(bs):
	bs.seek(0)
	magic = bs.readUInt()
	version = bs.readUInt()
	
	bs.readBytes(16)
	#bs.seek(24)
	dataOffset = bs.readUInt()
	maxOffset = dataOffset
	bs.readBytes(12)
	stringSectionOffset = bs.readUInt()
	stringSectionSize = bs.readUInt()
	bs.readBytes(4)
	stringSectionEndOffset = bs.readUInt()
	hashTableEntryCount = bs.readUInt()
	bs.readBytes(4)
	hashTableEndOffset = bs.readUInt()
	
	unkStruct1Count = bs.readUInt()
	bs.readBytes(4)
	unkStruct1SectionEndOffset = bs.readUInt()
	
	unkStruct2Count = bs.readUInt()
	bs.readBytes(4)
	unkStruct2SectionEndOffset = bs.readUInt()
	
	unkStruct3Count = bs.readUInt()
	bs.readBytes(4)
	unkStruct3SectionEndOffset = bs.readUInt()
	
	unkStruct4Count = bs.readUInt()
	bs.readBytes(4)
	unkStruct4SectionEndOffset = bs.readUInt()
	
	unkStruct5Count = bs.readUInt()
	bs.readBytes(4)
	
	bs.seek(stringSectionOffset)
	#grab names
	indexToName = []
	nameToIndex = {}
	index = 0
	while(bs.tell() < stringSectionEndOffset):
		name = bs.readString()
		indexToName.append(name)
		nameToIndex[name] = index
		index+=1
		
	bs.seek(88)
	exportsAddress = bs.readUInt()
	exportsCount = bs.readUInt()
	EXPORT = namedtuple("EXPORT", "name offset dataSize dataEnd exportOffset")
	EXPORTS = []
	exportNames = []
	bs.seek(exportsAddress)
	
	for i in range(exportsCount):
		offs = bs.tell()
		cName = indexToName[bs.readUShort()]
		bs.seek(6,1)
		cDataSize = bs.readUInt()
		cOffset = bs.readUInt()
		EXPORTS.append(EXPORT(name = cName, offset=cOffset, dataSize=cDataSize, dataEnd=cOffset+cDataSize, exportOffset=offs))
		exportNames.append(cName)
		bs.seek(8,1)
	
	bs.seek(100)
	buffersAddress = bs.readUInt()
	buffersCount = bs.readUInt()
	#BUFFER = namedtuple("BUFFER", "flags index offset diskSize memSize CRC32 bufferOffset")
	BUFFERS = []
	bs.seek(buffersAddress)
	for i in range(buffersCount):
		BUFFERS.append( CP77Buffer(bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.tell()-24, 0, NoeBitStream()) )
			
	bs.seek(unkStruct4SectionEndOffset + unkStruct5Count * 16)
	return [indexToName, nameToIndex, maxOffset, EXPORTS, exportNames, BUFFERS]

'''////////////////////////////////////////////////////////////////////////////////// TEXTURE IMPORT / EXPORT //////////////////////////////////////////////////////////////////////////////////'''

class CP77Buffer:
	def __init__(self, flags, index, offset, diskSize, memSize, CRC32, bufferOffset, origOffset, data):
		self.flags = flags
		self.index = index
		self.offset = offset
		self.diskSize = diskSize
		self.memSize = memSize
		self.CRC32 = CRC32
		self.bufferOffset = bufferOffset
		self.origOffset = offset
		self.data = data
	def __repr__(self):
		return "(CP77Buffer:" + self.flags + "," + repr(self.index) + "," + repr(self.offset) + "," + repr(self.diskSize) + repr(self.memSize) + repr(self.CRC32) + repr(self.bufferOffset) + ")"

class CP77Texture:
	def __init__(self, path, name, compression, size, width, height, bufferNo):
		self.path = path
		self.name = name
		self.compression = compression
		self.size = size
		self.width = width
		self.height = height
		self.bufferNo = bufferNo
		#self.exportIdx = exportIdx
	def __repr__(self):
		return "(CP77Texture:" + self.path + "," + repr(self.compression) + "," + repr(self.size) + "," + repr(self.width) + repr(self.height) + repr(self.bufferNo) + ")"

def xbmLoadDDS(data, texList):
	global bManualDimensions
	print (rapi.getInputName())
	f = NoeBitStream(data)
	
	if f.readUInt() != 1462915651:
		print ("Not a \"CR2W\" file \nPick a valid XBM, MI or other Cyberpunk file")
		return 0
	f.seek(0)
	
	if bFlipImage:
		print("Image/UVs Flip Enabled")
	
	TEXTURES = []
	numBuffers = readUShortAt(f, 104)
	strings, nameToIndex, maxOffset, EXPORTS, exportNames, buffers = ParseHeader(f)
	checkPoint = f.tell()	
	
	
	if not ("CBitmapTexture" in strings and "width" in strings and "height" in strings and "rendRenderTextureBlobSizeInfo" in strings):
		print ("Required CNames not found!\n")
	
	bIsMorphtarget = False
	if rapi.getInputName().lower().find("morphtarget") != -1:
		bIsMorphtarget = True
		dataBufferFlag = buildFlagFromNames(["textureDiffsBuffer", "serializationDeferredDataBuffer"], nameToIndex, 0)
		dimsFlag = buildFlagFromNames(["targetDiffsWidth","static:3,Uint16"], nameToIndex, 0)
	else:
		dataBufferFlag = buildFlagFromNames(["textureData", "serializationDeferredDataBuffer"], nameToIndex, 0)
		dimsFlag = buildFlagFromNames(["sizeInfo","rendRenderTextureBlobSizeInfo"], nameToIndex, 0)
		
	if "textureData" not in strings and "textureDiffsBuffer" not in strings: 
		print ("Texture data Buffer not found")
		return 0
		
	skipFlag = 0
	skipFlag2 = 0
	
	if rapi.getInputName().find("mesh") != -1:
		skipFlag = buildFlagFromNames(["topology","array:rendTopologyData"], nameToIndex, 0) 
		skipFlag2 = buildFlagFromNames(["simulation", "array:Uint16"],nameToIndex,0) 
	compressionFlag = buildFlagFromNames(["compression","ETextureCompression"], nameToIndex, 0) 
	
	name = rapi.getInputName()
	ext = os.path.splitext(name)
	if ext[1] == ".cp77tex":
		name = ext[0]
	bufferName = name + ".0.buffer"
	
	highestGoodIdx = 0
	buffCounter = 0
	
	
	for i in range(numBuffers):
		cWidth = 0
		cHeight = 0
		formatString = ""
		pos = f.tell()
		bufferIdx = -1
		
		if findFlag(f, dataBufferFlag, maxOffset, skipFlag, skipFlag2): #and readUShortAt(f, f.tell()+8) < numBuffers
			for e, export in enumerate(EXPORTS):
				if export.offset > pos and export.offset < f.tell():
					if EXPORTS[e-1].name == "CBitmapTexture":
						pos = EXPORTS[e-1].offset
					else:
						pos = export.offset
			f.seek(8,1)
			bufferIdx = f.readUShort()
			bufferMaxOffset = f.tell()
		else:
			print ("Texture data buffer not detected")
			break
		
		f.seek(pos)
		if findFlag(f, compressionFlag, bufferMaxOffset, skipFlag):
			f.seek(8,1)
			try:
				formatString = strings[f.readUShort()]	
			except:
				pass
			
		f.seek(pos)
		
		if findFlag(f, dimsFlag, bufferMaxOffset, skipFlag):
			if bIsMorphtarget:
				formatString = "TCM_QualityColor"
				f.seek(12,1)
			else: f.seek(17,1)
			cWidth = f.readUShort()
			if not bIsMorphtarget:
				f.seek(8,1)
				cHeight = f.readUShort()
			else: cHeight = cWidth
		else: 
			bManualDimensions = True
		f.seek(bufferMaxOffset + 2)
		
		ddsFmt = -1
		if formatString == "TCM_QualityR":
			ddsFmt = 4
		elif formatString ==  "TCM_QualityRG" or formatString == "TCM_Normalmap":
			ddsFmt = 5
		elif formatString ==  "TCM_QualityColor":
			ddsFmt = 7
		elif formatString ==  "TCM_DXTNoAlpha" or formatString == "TCM_Normals_DEPRECATED":
			ddsFmt = 1
		elif formatString ==  "TCM_DXTAlphaLinear" or formatString == "TCM_DXTAlpha":
			ddsFmt = 3
		else:
			formatString = "Unknown Encoding"
		
		if rapi.checkFileExists(rapi.getExtensionlessName(name) + ".dds"):
			TEXTURES.append(CP77Texture(rapi.getExtensionlessName(name) + ".dds", rapi.getExtensionlessName(rapi.getOutputName()) + "_" + str(bufferIdx), ddsFmt, os.path.getsize(rapi.getExtensionlessName(name) + ".dds"), cWidth, cHeight, bufferIdx))
			if ddsFmt > 0 and cWidth > 0 and cHeight > 0:
				highestGoodIdx = buffCounter
			bufferName = name + "." + str(bufferIdx-1) + ".buffer"
		else:
			TEXTURES.append(CP77Texture(name + "." + str(bufferIdx-1) + ".buffer", rapi.getExtensionlessName(rapi.getOutputName()) + "_" + str(bufferIdx), ddsFmt, 0, cWidth, cHeight, bufferIdx))
			if ddsFmt > 0 and cWidth > 0 and cHeight > 0:
				highestGoodIdx = buffCounter
			bufferName = name + "." + str(bufferIdx-1) + ".buffer"
			
		buffCounter += 1	
		
		print ("Image " + str(buffCounter-1) + ":\n	", rapi.getLocalFileName(bufferName))
		if bufferIdx != -1:
			print ("	 IMAGE	" + formatString + " (" + str(ddsFmt) + ")" )
			print ("	 " + str(cWidth) + "x" + str(cHeight))
		else:
			print ("	  (" + str(ddsFmt) + ")" )
	
	
	for theTexture in TEXTURES:
		#print (theTexture.compression)
		if theTexture.bufferNo == 0 or (rapi.checkFileExists(theTexture.path) == False and bCompress == False):
			continue
			
		if bCompress:
			texData = GetCR2WBuffer(f, buffers, ext, theTexture.bufferNo-1).getBuffer()
		else:
			if os.path.splitext(theTexture.path)[1] == ".dds":
				og = NoeBitStream(rapi.loadIntoByteArray(theTexture.path))
				if og.readUInt() == 542327876: #DDS
					og.seek(84)
					if og.readUInt() == 808540228: #DX10
						og.seek(148)
					else:
						og.seek(128)
				else:
					print ("Invalid DDS File!")
					return 0
				texData = og.readBytes(og.getSize() - og.tell())
			else:
				texData = rapi.loadIntoByteArray(theTexture.path)
			
			
		ddsFmt = theTexture.compression
		
		if bManualCompression or ddsFmt == -1:
			ddsFmt = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Enter Compression Type", "Enter 1-7 for the BC1-7 compression used, or enter a raw format string (r8g8b8a8):", str(ddsFmt), None)
			if ddsFmt == None:
				return 0
			if ddsFmt == "-1":
				ddsFmt = "r8g8b8a8"
		
		if bManualDimensions or theTexture.width == 0 or theTexture.height == 0:
			width = int(noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Enter width", "Enter the width of the texture:", str(theTexture.width), None))
			height = int(noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Enter height", "Enter the height of the texture:", str(theTexture.height), None))
			if width == None or height == None:
				return 0
		else:
			width = theTexture.width
			height = theTexture.height
		
		try: 
			ddsFmt = int(ddsFmt) #trips value error if ddsFmt is r8g8b8a8
			
			print ("BC" + str(ddsFmt))
			if ddsFmt == 1:
				ddsFmt = noesis.FOURCC_BC1
			elif ddsFmt == 2:
				ddsFmt = noesis.FOURCC_BC2
			elif ddsFmt == 3:
				ddsFmt = noesis.FOURCC_BC3
			elif ddsFmt == 4:
				ddsFmt = noesis.FOURCC_BC4
			elif ddsFmt == 5:
				ddsFmt = noesis.FOURCC_BC5
			elif ddsFmt == 6:
				ddsFmt = noesis.FOURCC_BC6H
			elif ddsFmt == -6:
				ddsFmt = noesis.FOURCC_BC6S
			elif ddsFmt == 7:
				ddsFmt = noesis.FOURCC_BC7
			if bReadAsSigned:
				texData = rapi.imageDecodeDXT(texData, width, height,  ddsFmt, 0, 1)
			else:
				texData = rapi.imageDecodeDXT(texData, width, height,  ddsFmt, 0, 0)
			#texData = rapi.imageToLinear(texData, width, height)
			
		except ValueError:
			print(ddsFmt)
			try:
				texData = rapi.imageDecodeRaw(texData, width, height,  ddsFmt, 0)
			except:
				print ("Image load failed")
				return 0
		
		if bFlipImage:
			texData = rapi.imageFlipRGBA32(texData, width, height, 0, 1)
			
		texList.append(NoeTexture(theTexture.name, width, height, texData, noesis.NOESISTEX_RGBA32))
		if not bCompress:
			print ("Loaded", theTexture.path)
	print ("\n")
	return 1
	

def xbmWriteRGBA(data, width, height, outfile):

	def getExportName(fileName):
		if fileName == None:
			textureName = (re.sub(r'out\w+\.', '.', rapi.getInputName().lower()).replace(".tga",".").replace(".png",".").replace(".cp77tex",".").replace("out.",".").replace("out.",".").replace(".xbm",".").replace(".mi",".").replace(".cp77tex",".") + os.path.splitext(rapi.getOutputName())[1]).replace("..",".")
			#textureName = rapi.getInputName().lower().replace(".xbmout","").replace("out.",".").replace(".xbm",".")
		else:
			textureName = fileName
		textureName = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Export over CP77 Texture", "Choose a texture file to export over", textureName, None)
		if textureName == None:
			print("Aborting...")
			return
		return textureName
		
	print ("\n		        ----Cyberpunk 2077 Texture Export----\n")
	if bFlipImage:
		print("Image/UVs Flip Enabled")
		
	fileName = None
	if noesis.optWasInvoked("-texfile"):
		textureName = noesis.optGetArg("-texfile")
	else:
		textureName = getExportName(fileName)
	
	if textureName == None:
		return 0
	while not (rapi.checkFileExists(textureName)):
		print ("File not found!")
		textureName = getExportName(fileName)	
		fileName = textureName
		if textureName == None:
			return 0
			
	isXBM = False
	if textureName.endswith(".xbm"):
		isXBM = True
		
	oldTex = rapi.loadIntoByteArray(textureName)
	f = NoeBitStream(oldTex)
	if f.readUInt() != 1462915651:
		print ("Not a \"CR2W\" file \nPick a valid XBM, MI or other Cyberpunk file")
		return 0
	f.seek(0)
	strings, nameToIndex, maxOffset, EXPORTS, exportNames, buffers = ParseHeader(f)
	checkPoint = f.tell()
	
	f.seek(0)
	bs = NoeBitStream()
	bs.writeBytes(f.readBytes(f.getSize())) #copy file
	bs.seek(0)
	f.seek(checkPoint)
	
	if not ("CBitmapTexture" in strings and "width" in strings and "height" in strings and "rendRenderTextureBlobSizeInfo" in strings):
		print ("Required CNames not found!\n")
	
	bIsMorphtarget = False
	if rapi.getInputName().lower().find("morphtarget") != -1:
		bIsMorphtarget = True
		dataBufferFlag = buildFlagFromNames(["textureDiffsBuffer", "serializationDeferredDataBuffer"], nameToIndex, 0)
		dimsFlag = buildFlagFromNames(["targetDiffsWidth","static:3,Uint16"], nameToIndex, 0)
	else:
		dataBufferFlag = buildFlagFromNames(["textureData", "serializationDeferredDataBuffer"], nameToIndex, 0)
		dimsFlag = buildFlagFromNames(["sizeInfo","rendRenderTextureBlobSizeInfo"], nameToIndex, 0)
	if not dataBufferFlag:
		print ("\nError: Texture data Buffer not found")
		return 0
	compressionFlag = buildFlagFromNames(["compression","ETextureCompression"], nameToIndex, 0) 
	skipFlag = 0
	skipFlag2 = 0
	if not isXBM:
		skipFlag = buildFlagFromNames(["topology","array:rendTopologyData"],nameToIndex,0) 
		skipFlag2 = buildFlagFromNames(["simulation", "array:Uint16"],nameToIndex,0) 
		
	name = textureName
	ext = os.path.splitext(name)
	if ext[1] == ".cp77tex":
		name = ext[0]
		
	highestGoodIdx = 0
	theTexture = CP77Texture("", 0, 0, (0,0), (0,0), 0, 0)
	buffCounter = 0
	numBuffers = readUShortAt(f, 104)
	TEXTURES = []
	
	for i in range(numBuffers):
		cWidth = 0
		cHeight = 0
		formatString = ""
		pos = f.tell()
		
		bufferIdx = -1
		if findFlag(f, dataBufferFlag, maxOffset, skipFlag, skipFlag2):
			for e, export in enumerate(EXPORTS):
				if export.offset > pos and export.offset < f.tell():
					if EXPORTS[e-1].name == "CBitmapTexture":
						pos = EXPORTS[e-1].offset
					else:
						pos = export.offset
			f.seek(8,1)
			bufferIdx = f.readUShort()
			bufferMaxOffset = f.tell()
		else:
			print ("Texture data buffer not detected")
			break
		
		f.seek(pos)
		if findFlag(f, compressionFlag, bufferMaxOffset, skipFlag):
			f.seek(8,1)
			try:
				formatString = strings[f.readUShort()]	
			except:
				pass
		f.seek(pos)
		
		if findFlag(f, dimsFlag, bufferMaxOffset, skipFlag):
			if bIsMorphtarget:
				formatString = "TCM_QualityColor"
				f.seek(12,1)
			else: f.seek(17,1)
			cWidth = f.readUShort(), f.tell()-2
			if not bIsMorphtarget:
				f.seek(8,1)
				cHeight = f.readUShort(), f.tell()-2
			else: cHeight = cWidth
		else: 
			bManualDimensions = True
		f.seek(bufferMaxOffset + 2)
		
		ddsFmt = -1
		if formatString == "TCM_QualityR":
			ddsFmt = 4
		elif formatString ==  "TCM_QualityRG" or formatString == "TCM_Normalmap":
			ddsFmt = 5
		elif formatString ==  "TCM_QualityColor":
			ddsFmt = 7
		elif formatString ==  "TCM_DXTNoAlpha" or formatString == "TCM_Normals_DEPRECATED":
			ddsFmt = 1
		elif formatString ==  "TCM_DXTAlphaLinear" or formatString == "TCM_DXTAlpha":
			ddsFmt = 3
		else:
			formatString = "Unknown Encoding"
			
		if rapi.checkFileExists(rapi.getExtensionlessName(name) + ".dds"):
			TEXTURES.append(CP77Texture(rapi.getExtensionlessName(name) + ".dds", rapi.getExtensionlessName(rapi.getOutputName()) + "_" + str(bufferIdx), ddsFmt, os.path.getsize(rapi.getExtensionlessName(name) + ".dds"), cWidth, cHeight, bufferIdx))
			buffCounter += 1
			break
		else:
			TEXTURES.append(CP77Texture(name + "." + str(bufferIdx) + ".buffer", rapi.getExtensionlessName(rapi.getOutputName()) + "_" + str(bufferIdx), ddsFmt, 0, cWidth, cHeight, bufferIdx))
			if ddsFmt > 0 and cWidth[0] > 0 and cHeight[0] > 0:
				highestGoodIdx = buffCounter
			bufferName = name + "." + str(bufferIdx-1) + ".buffer"
			
		buffCounter += 1
		
		print ("Buffer " + str(buffCounter-1) + ":\n	", rapi.getLocalFileName(bufferName))
		if bufferIdx != 0:
			print ("	 IMAGE	" + formatString + " (" + str(ddsFmt) + ")" )
			print ("	 " + str(cWidth[0]) + "x" + str(cHeight[0]))
		else:
			print ("	  (" + str(ddsFmt) + ")" )
	
	if buffCounter > 0:
		promptIdx = -999 
		while promptIdx == -999 or theTexture.bufferNo == 0 or theTexture.width[0] == 0 or theTexture.height[0] == 0:
			if buffCounter and not isXBM:
				promptIdx = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Export over texture", "Which file do you want to export over? [0-" + str(buffCounter-1) + "]", str(highestGoodIdx), None)
			else:
				promptIdx = buffCounter-1
				
			if promptIdx == None:
				return 0
			try:
				theTexture = TEXTURES[int(promptIdx)]
				if theTexture.bufferNo == 0:
					print ("Not an image file!")
			except:
				print ("No such buffer file!")
			#print (theTexture)
			if isXBM and theTexture.bufferNo == 0 or theTexture.width[0] == 0 or theTexture.height[0] == 0:
				break
		filepath = theTexture.path
		
	else:
		print ("No buffer file was found!")
		return 0
	
	ddsFmt = theTexture.compression
	nf = NoeBitStream()
	
	f.seek(0)	
	ddsFmt2 = 0
	if bManualCompression:
		ddsFmt = int(noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Enter Compression Type", "Enter 1-7 for the type of BC1-BC7 compression used:", str(ddsFmt), None))
	try:			
		ddsFmt = int(ddsFmt)
		if ddsFmt == 1:
			ddsFmt = noesis.NOE_ENCODEDXT_BC1
			ddsFmt2 = noesis.FOURCC_BC1
		elif ddsFmt == 2:
			ddsFmt = noesis.NOE_ENCODEDXT_BC2
			ddsFmt2 = noesis.FOURCC_BC2
		elif ddsFmt == 3:
			ddsFmt = noesis.NOE_ENCODEDXT_BC3
			ddsFmt2 = noesis.FOURCC_BC3
		elif ddsFmt == 4:
			ddsFmt = noesis.NOE_ENCODEDXT_BC4
			ddsFmt2 = noesis.FOURCC_BC4
		elif ddsFmt == 5:
			ddsFmt = noesis.NOE_ENCODEDXT_BC5
			ddsFmt2 = noesis.FOURCC_BC5
		elif ddsFmt == 6:
			ddsFmt = noesis.NOE_ENCODEDXT_BC6H
			ddsFmt2 = noesis.FOURCC_BC6H
		elif ddsFmt == -6:
			ddsFmt = noesis.NOE_ENCODEDXT_BC6S
			ddsFmt2 = noesis.FOURCC_BC6S
		elif ddsFmt == 7:
			ddsFmt = noesis.NOE_ENCODEDXT_BC7
			ddsFmt2 = noesis.FOURCC_BC7
	except:
		pass
	
	bs.seek(theTexture.height[1])
	bWriteMips = False
	mipFlag = buildFlagFromNames(["mipMapInfo","array:rendRenderTextureBlobMipMapInfo"],nameToIndex,0) 
	if (width != theTexture.width[0] or height != theTexture.height[0]) and findFlag(bs, mipFlag, maxOffset, 0): 
		bWriteMips = True
		bs.seek(8,1)
		maxMips = bs.readUInt()
		bs.seek(18,1)
		
	mipWidth = width
	mipHeight = height
	numMips = 0
	#encode image:
	while mipWidth > 0 and mipHeight > 0:
		mipData = rapi.imageResample(data, width, height, mipWidth, mipHeight)
		if bFlipImage:
			mipData = rapi.imageFlipRGBA32(mipData, mipWidth, mipHeight, 0, 1)
			
		try:
			imgData = rapi.imageEncodeDXT(mipData, 4, mipWidth, mipHeight, ddsFmt)
		except:
			imgData = rapi.imageEncodeRaw(mipData, 4, mipWidth, mipHeight)
		
		if bWriteMips and numMips < maxMips:
			bs.writeUInt(mipWidth*2)
			bs.seek(8,1)
			bs.writeUInt(len(imgData))
			bs.seek(19,1)
			if numMips == 0:
				bs.writeUInt(len(imgData))
			else:
				bs.writeUInt(nf.tell())
				bs.seek(8,1)
				bs.writeUInt(len(imgData))
			bs.seek(22,1)
		nf.writeBytes(imgData)
		
		print (mipWidth, mipHeight)
		if mipWidth == mipHeight and mipWidth == 1: break
		if mipWidth > 1: mipWidth = int(mipWidth / 2)
		if mipHeight > 1: mipHeight = int(mipHeight / 2)
		if mipWidth < 1: mipWidth = 1
		if mipHeight < 1: mipHeight = 1
		numMips += 1
		
	bs.seek(theTexture.width[1])
	bs.writeUShort(width)
	bs.seek(theTexture.height[1])
	bs.writeUShort(height)
	
	if bWriteMips:
		bs.seek(0)
		imgSizeFlag = buildFlagFromNames(["textureDataSize","Uint32"],nameToIndex,0) 
		if findFlag(bs, imgSizeFlag, maxOffset, 0):
			bs.seek(8,1)
			bs.writeUInt(nf.getSize()) #imgSize
			bs.seek(8,1)
			bs.writeUInt(nf.getSize()) #sliceSize
	
	if bCompress:
		buffers = WriteCR2WBuffer(buffers, nf, theTexture.bufferNo-1)
		bs.seek(0)
		outfile.writeBytes(bs.readBytes(buffers[0].offset)) #write CR2W part
		for buff in buffers:
			if buff.data.getSize() == 0:
				f.seek(buff.origOffset)
				buff.data.writeBytes(f.readBytes(buff.diskSize))
			buff.offset = outfile.tell()
			outfile.writeBytes(buff.data.getBuffer())
			buff.diskSize = buff.data.getSize()
		for buff in buffers:
			outfile.seek(buff.bufferOffset + 8)
			outfile.writeUInt(buff.offset)
			outfile.writeUInt(buff.diskSize)
			outfile.writeUInt(buff.memSize)
		outfile.seek(28)
		outfile.writeUInt(outfile.getSize()) #bufferSize
	else:
		newBufferName = (rapi.getOutputName().split("cp77tex")[0] + "." + str(theTexture.bufferNo-1) + ".buffer").replace("..", ".")
		if isXBM:
			ddsBytes = rapi.imageGetDDSFromDXT(nf.getBuffer(), width, height, numMips, ddsFmt2)
			newBufferName = newBufferName.replace("xbm.0.buffer", "dds")
			open(newBufferName, "wb").write(ddsBytes)
		else:
			open(newBufferName, "wb").write(nf.getBuffer())
		if bExportAllBuffers:
			copyBuffers(textureName, ext[1], readUIntAt(f, 104))
		print("Wrote", rapi.getLocalFileName(newBufferName), "\n")
	
	return 1

#////////////////////////////////////////////////////////////////////////////////// MESH IMPORT / EXPORT //////////////////////////////////////////////////////////////////////////////////
	
def parseGarmentMesh(f, indexToName, nameToIndex, gMesh, doGarmentMesh, doGarmentMesh2, skipFlag): #the worst part of making this tool

	f.seek(gMesh.offset)
	gm = NoeBitStream(f.readBytes(gMesh.dataSize))
	
	GMESH = namedtuple("GMESH", "offset vertices indices morphOffsets garmentFlags skinWeights skinIndices skinWeightsExt skinIndicesExt")
	GMESHES = []
	
	if doGarmentMesh2:
		gmFlag = buildFlagFromNames(["positions", "DataBuffer"],nameToIndex,0)  
		gmFlagSpcl = buildFlagFromNames(["chunks", "array:meshGfxClothChunkData"],nameToIndex,0) 
		skipFlag = buildFlagFromNames(["simulation", "array:Uint16"],nameToIndex,0) 
		findFlag(gm, gmFlagSpcl, gMesh.dataSize, skipFlag)
		gm.seek(-1,1)
	else:
		gmFlag = buildFlagFromNames(["vertices", "DataBuffer"],nameToIndex,0)  
	
	gm.seek(9,1)
	gMeshCount = gm.readUInt()
	gMeshIdx = 0
	while gMeshIdx < gMeshCount and findFlag(gm, gmFlag, gMesh.dataSize, skipFlag) is not False:
		try:
			pos = gm.tell()
			gOffset = -1
			gm.seek(pos + 8)
			if doGarmentMesh:
				gOffset = gm.tell() + gMesh.offset - 24 + 3 #vertex count write location
				
			vBufferNo = gm.readUShort()
			gm.seek(10, 1)
			iBufferNo = gm.readUShort()
			
			if doGarmentMesh2:
				gm.seek(10, 1)
				sIBufferNo1 = gm.readUShort()
				gm.seek(10, 1)
				sWBufferNo1 = gm.readUShort()
				
				#detect if extra weights are present in next gMesh:
				if readUShortAt(gm, gm.tell()+2) < len(indexToName) and indexToName[readUShortAt(gm, gm.tell()+2)] == "skinWeightsExt":
					gm.seek(10, 1)
					sIBufferNo2 = gm.readUShort()
					gm.seek(10, 1)
					sWBufferNo2 = gm.readUShort()
					GMESHES.append(GMESH(offset = gOffset, vertices=vBufferNo-1, indices=iBufferNo-1, morphOffsets = -1, garmentFlags = -1, skinWeights=sIBufferNo1-1, skinIndices=sWBufferNo1-1, skinWeightsExt=sIBufferNo2-1, skinIndicesExt=sWBufferNo2-1))
				else:
					GMESHES.append(GMESH(offset = gOffset, vertices=vBufferNo-1, indices=iBufferNo-1, morphOffsets = -1, garmentFlags = -1, skinWeights=sIBufferNo1-1, skinIndices=sWBufferNo1-1, skinWeightsExt=-1, skinIndicesExt=-1))
					
				if readUShortAt(gm, gm.tell()) < len(indexToName) and indexToName[readUShortAt(gm, gm.tell())] == "simulation": #skip simulation
					skipCount = readUIntAt(gm, gm.tell()+4) 
					gm.seek(skipCount+6,1)
			else:
				gm.seek(10, 1)
				mtBufferNo = gm.readUShort()
				gm.seek(10, 1)
				flagsBufferNo = gm.readUShort()
				GMESHES.append(GMESH(offset = gOffset, vertices=vBufferNo-1, indices=iBufferNo-1, morphOffsets = mtBufferNo-1, garmentFlags = flagsBufferNo-1, skinWeights=-1, skinIndices=-1, skinWeightsExt=-1, skinIndicesExt=-1))
			
			gMeshIdx += 1
		except:
			print ("Error reading garment meshes")
			break
		
	return GMESHES

def parseMorphs(mm, mMesh, nameToIndex, submeshCount, vCounts):
	numDiffsFlag = buildFlagFromNames(["numDiffs","Uint32"],nameToIndex,0)  
	numDiffsMappingFlag = buildFlagFromNames(["numDiffsMapping","Uint32"],nameToIndex,0)  
	numTargetsFlag = buildFlagFromNames(["numTargets","Uint32"],nameToIndex,0)  
	targetStartsDiffsFlag = buildFlagFromNames(["targetStartsInVertexDiffs","array:Uint32"],nameToIndex,0)  
	targetStartsDiffsMappingFlag = buildFlagFromNames(["targetStartsInVertexDiffsMapping","array:Uint32"],nameToIndex,0) 
	targetPositionDiffScaleFlag = buildFlagFromNames(["targetPositionDiffScale","array:Vector4"],nameToIndex,0)  
	targetPositionDiffOffsetFlag = buildFlagFromNames(["targetPositionDiffOffset","array:Vector4"],nameToIndex,0)  
	numVertexDiffsInEachChunkFlag = buildFlagFromNames(["numVertexDiffsInEachChunk","array:array:Uint32"],nameToIndex,0)  
	numVertexDiffsMappingInEachChunkFlag = buildFlagFromNames(["numVertexDiffsMappingInEachChunk","array:array:Uint32"],nameToIndex,0)  
	diffsBufferFlag = buildFlagFromNames(["diffsBuffer","DataBuffer"],nameToIndex,0)  
	if findFlag(mm, numDiffsFlag, mMesh.dataSize, 0):
		numDiffs = readUIntAt(mm, mm.tell()+8)
	if findFlag(mm, numDiffsMappingFlag, mMesh.dataSize, 0):
		numDiffsMapping = readUIntAt(mm, mm.tell()+8)
	if findFlag(mm, numTargetsFlag, mMesh.dataSize, 0):
		numTargets = readUIntAt(mm, mm.tell()+8)
		
	if findFlag(mm, targetStartsDiffsFlag, mMesh.dataSize, 0):
		numTargetStartsDiffs = readUIntAt(mm, mm.tell()+8)
		mm.seek(12,1)
		targetStartsDiffs = []
		for j in range(numTargetStartsDiffs):
			targetStartsDiffs.append(mm.readUInt())
	if findFlag(mm, targetStartsDiffsMappingFlag, mMesh.dataSize, 0):
		numTargetStartsDiffsMappings = readUIntAt(mm, mm.tell()+8)
		mm.seek(12,1)
		targetStartsDiffsMappings = []
		for j in range(numTargetStartsDiffsMappings):
			targetStartsDiffsMappings.append(mm.readUInt())
	if findFlag(mm, targetPositionDiffScaleFlag, mMesh.dataSize, 0):
		numTargetPositionDiffScales = readUIntAt(mm, mm.tell()+8)
		mm.seek(12,1)
		targetPositionDiffScales = []
		for j in range(numTargetPositionDiffScales):
			pos = mm.tell()
			targetPositionDiffScales.append(NoeVec3(((readFloatAt(mm, pos+9)), (readFloatAt(mm, pos+21)), (readFloatAt(mm, pos+33)))))
			mm.seek(pos+51)
			
	if findFlag(mm, targetPositionDiffOffsetFlag, mMesh.dataSize, 0):
		numTargetPositionDiffOffsets = readUIntAt(mm, mm.tell()+8)
		mm.seek(12,1)
		targetPositionDiffOffsets = []
		for j in range(numTargetPositionDiffOffsets):
			pos = mm.tell()
			targetPositionDiffOffsets.append(NoeVec3((readFloatAt(mm, pos+9), readFloatAt(mm, pos+21), (readFloatAt(mm, pos+33)))))
			mm.seek(pos+51)
	if findFlag(mm, numVertexDiffsInEachChunkFlag, mMesh.dataSize, 0):
		numElementsVertexDiffsInEachChunk = readUIntAt(mm, mm.tell()+8)
		mm.seek(12,1)
		numVertexDiffsInEachChunk = []
		for j in range(numElementsVertexDiffsInEachChunk):
			count = mm.readUInt()
			subArray = []
			for c in range(count):
				subArray.append(mm.readUInt())
			numVertexDiffsInEachChunk.append(subArray)
	if findFlag(mm, numVertexDiffsMappingInEachChunkFlag, mMesh.dataSize, 0):
		numElementsVertexDiffsMappingsInEachChunk = readUIntAt(mm, mm.tell()+8)
		mm.seek(12,1)
		numVertexDiffsMappingsInEachChunk = []
		for j in range(numElementsVertexDiffsMappingsInEachChunk):
			count = mm.readUInt()
			subArray = []
			for c in range(count):
				subArray.append(mm.readUInt())
			numVertexDiffsMappingsInEachChunk.append(subArray)
	if findFlag(mm, diffsBufferFlag, mMesh.dataSize, 0):
		diffsBuffer = readUShortAt(mm, mm.tell()+8) - 1
		mappingBuffer = readUShortAt(mm, mm.tell()+20) - 1
	mm.seek(0)
	
	diffsFile = rapi.getInputName().replace(".morphtarget", ".morphtarget." + str(diffsBuffer) + ".buffer")
	
	if rapi.checkFileExists(diffsFile):
		diffsBuff = rapi.loadIntoByteArray(diffsFile)
		diffsStream = NoeBitStream(diffsBuff)
		allPosDiffs = []
		allNrmDiffs = []
		allTanDiffs = []
		for t in range(numTargets):
			targetPosDiffs = []
			targetNrmDiffs = []
			targetTanDiffs = []
			diffsStream.seek(targetStartsDiffs[t] * 12)
				
			for c in range(len(numVertexDiffsInEachChunk[t])):
				chunkPosDiffs = []
				chunkNrmDiffs = []
				chunkTanDiffs = []
				for d in range(numVertexDiffsInEachChunk[t][c]):
					pos = diffsStream.tell()
					posDiff = diffsStream.readUInt()
					pdX = posDiff & 0x3ff
					pdY = (posDiff >> 10) & 0x3ff
					pdZ = (posDiff >> 20) & 0x3ff
					chunkPosDiffs.append(NoeVec3((((pdX - 511.00001) / 512.0) * targetPositionDiffScales[t][0] + targetPositionDiffOffsets[t][0], \
					((pdY - 511.00001) / 512.0) * targetPositionDiffScales[t][1] + targetPositionDiffOffsets[t][1], \
					((pdZ - 511.00001) / 512.0) * targetPositionDiffScales[t][2] + targetPositionDiffOffsets[t][2])))
					#if t == 1 and c == 0 and d <= 3:
					#	print (chunkPosDiffs[d], diffsStream.tell(), t, d)
						#print ("offs", targetPositionDiffOffsets[t])
						#print ("scale", targetPositionDiffScales[t])
					#pdX = ((diffsStream.readBits(10) - 511) / 512.0)
					#pdY = ((diffsStream.readBits(10) - 511) / 512.0)
					#pdZ = ((diffsStream.readBits(10) - 511) / 512.0)
					#diffsStream.readBits(2)
					#chunkPosDiffs.append(NoeVec3((pdX, pdZ, -pdY)))
					
					ndX = ((diffsStream.readBits(10) - 511.00001) / 512.0)
					ndY = ((diffsStream.readBits(10) - 511.00001) / 512.0)
					ndZ = ((diffsStream.readBits(10) - 511.00001) / 512.0)
					diffsStream.readBits(2)
					chunkNrmDiffs.append(NoeVec3((ndX, ndY, ndZ))) #chunkNrmDiffs.append(NoeVec3((ndX, ndZ, -ndY)))
					'''tdX = ((diffsStream.readBits(10) - 511) / 512.0)
					tdY = ((diffsStream.readBits(10) - 511) / 512.0)
					tdZ = ((diffsStream.readBits(10) - 511) / 512.0)
					diffsStream.readBits(2)
					chunkTanDiffs.append(NoeVec3((tdX, tdZ, -tdY)))'''
					diffsStream.seek(pos+12)
					
				targetPosDiffs.append(chunkPosDiffs)
				targetNrmDiffs.append(chunkNrmDiffs)
				targetTanDiffs.append(chunkTanDiffs)
			allPosDiffs.append(targetPosDiffs)
			allNrmDiffs.append(targetNrmDiffs)
			allTanDiffs.append(targetTanDiffs)
	
	mappingFile = rapi.getInputName().replace(".morphtarget", ".morphtarget." + str(mappingBuffer) + ".buffer")
	allMaps = []
	if rapi.checkFileExists(mappingFile):
		mappingBuff = rapi.loadIntoByteArray(mappingFile)
		mappingStream = NoeBitStream(mappingBuff)
		for t in range(numTargets):
			targetMaps = []
			mappingStream.seek(targetStartsDiffsMappings[t] * 4)
			#print (t, "seeked to mappingStream", mappingStream.tell())
			#if t > 0:
			#	for eye in range(0, t):
			#		mappingStream.seek(numVertexDiffsMappingsInEachChunk[t][eye] * 4, 1)
				
			for c in range(len(numVertexDiffsMappingsInEachChunk[t])):				
				chunkMaps = []
				for d in range(numVertexDiffsMappingsInEachChunk[t][c] * 2):
					chunkMaps.append(mappingStream.readUShort())
				targetMaps.append(chunkMaps)
			allMaps.append(targetMaps)
	
	#build list of diffs [vertexCount] long, with list[X] being diff[X] (if X is an index in the maps), and 0's for all verts not having a diff
	allDiffsList = []
	if allMaps and allPosDiffs:
		for t in range(numTargets):
			targDiffsList = []
			#print ("using scale:", targetPositionDiffScales[t])
			for c in range(len(numVertexDiffsInEachChunk[t])):
				#print ("morphtarget", t, "chunk", c, "diffCount", len(allMaps[t][c]))
				
				diffsList = [NoeVec3((0,0,0)) for k in range(vCounts[c])]
				nrmDiffsList = [NoeVec3((0,0,0)) for k in range(vCounts[c])]
				for m, map in enumerate(allMaps[t][c]):
					if m == len(allMaps[t][c])-1 and len(allPosDiffs[t][c]) % 2 != 0:
						break
					diffsList[map] = ((allPosDiffs[t][c][m])) 
					nrmDiffsList[map] = allNrmDiffs[t][c][m]  
					
				targDiffsList.append((diffsList, nrmDiffsList))
			allDiffsList.append(targDiffsList)
			
	return allDiffsList

bodyTypes = {
    "ma": "man_base",
    "mb": "man_big",
    "mc": "man_child",
    "mf": "man_fat",
    "mm": "man_massive",
    "ms": "man_small",
    "mt": "man_teen",
    "wa": "woman_base",
    "wb": "woman_big",
    "wc": "woman_child",
    "wf": "woman_fat",
    "ws": "woman_small",
    "wt": "woman_teen"
}

def getBaseRig(bodyType, basegameDir, deformRig = False):
	try:
		bodyType = bodyTypes[bodyType]
	except:
		#print ("Body type not found, loading base male rig")
		bodyType = "man_base"
		
	g = bodyType.split("_")[0]
	subType = bodyType.split("_")[1]
	
	if deformRig:
		rigD = extractedDir + basegameDir + "\\base\\characters\\base_entities\\" + bodyType + "\\deformations_rigs\\" + bodyType + "_deformations.rig"
		if rapi.checkFileExists(rigD) == False and subType != "base":
			rigD = getBaseRig(g+"_base", basegameDir, True)
		return rigD
	else:
		rigF = extractedDir + basegameDir + "\\base\\characters\\base_entities\\" + bodyType + "\\" + bodyType + ".rig" 
		if rapi.checkFileExists(rigF) == False and subType != "base":
			rigF = getBaseRig(g+"_base", basegameDir)
		return rigF


localMat = NoeMat43(((0, 1, 0), (0, 0, -1), (-1, 0, 0), (0, 0, 0))) #NoeMat43(((0, 0, -1), (1, 0, 0), (0, -1, 0), (0, 0, 0)))
globalMat = NoeMat43(((-1, 0, 0), (0,  0, 1), ( 0, 1, 0), (0, 0, 0))) 

def LoadRig(br, meshBones, bindMatrices, type=0):
	indexToName, nameToIndex, maxOffset, EXPORTS, exportNames, buffers = ParseHeader(br)
	checkPoint = br.tell()
	
	# Read bone names
	bNameFlag = buildFlagFromNames(["boneNames","array:CName"],nameToIndex,0)
	rigBones = []
	if findFlag(br, bNameFlag, maxOffset, 0):
		br.seek(8,1)
		boneC = br.readInt()
		for i in range(boneC):
			rigBones.append(indexToName[br.readUShort()])
	br.seek(checkPoint)
	
	# Get A-poseLS bones
	if "aPoseLS" in indexToName:
		aposeLSFlag = buildFlagFromNames(["aPoseLS","array:QsTransform"],nameToIndex,0)
		if findFlag(br, aposeLSFlag, maxOffset, 0):
			br.seek(8,1)
			apBoneCLS = br.readUInt()
			aPosesLS = []
			for i in range(apBoneCLS):
				pos = br.tell()
				boneTrans = NoeVec4((readFloatAt(br, pos+18), readFloatAt(br, pos+30), readFloatAt(br, pos+42), readFloatAt(br, pos+54))).toVec3()
				pos += 59
				boneRot = NoeQuat((readFloatAt(br, pos+18), readFloatAt(br, pos+30), readFloatAt(br, pos+42), readFloatAt(br, pos+54))).transpose()
				pos += 59
				boneScale = NoeVec4((readFloatAt(br, pos+18), readFloatAt(br, pos+30), readFloatAt(br, pos+42), readFloatAt(br, pos+54))).toVec3()
				aPosesLS.append((boneTrans, boneRot, boneScale))
				br.seek(pos + 62)
		br.seek(checkPoint)
		type = 1
	
	# Get A-poseMS bones
	if "aPoseMS" in indexToName:
		aposeMSFlag = buildFlagFromNames(["aPoseMS","array:QsTransform"],nameToIndex,0)
		if findFlag(br, aposeLSFlag, maxOffset, 0):
			br.seek(8,1)
			apBoneCMS = br.readInt()
			aPosesMS = []
			for i in range(apBoneCMS):
				pos = br.tell()
				boneTrans = NoeVec4((readFloatAt(br, pos+18), readFloatAt(br, pos+30), readFloatAt(br, pos+42), readFloatAt(br, pos+54))).toVec3()
				pos += 59
				boneRot = NoeQuat((readFloatAt(br, pos+18), readFloatAt(br, pos+30), readFloatAt(br, pos+42), readFloatAt(br, pos+54))).transpose()
				pos += 59
				boneScale = NoeVec4((readFloatAt(br, pos+18), readFloatAt(br, pos+30), readFloatAt(br, pos+42), readFloatAt(br, pos+54))).toVec3()
				aPosesMS.append((boneTrans, boneRot, boneScale))
				br.seek(pos + 62)
		br.seek(checkPoint)
		type = 2
	
	# Parenting info
	findFlag(br, b'\xFF\xFF\x00\x00', br.getSize(), 0)
	parIds = []
	for b in range(boneC):
		parIds.append(br.readShort())	
	
	#T-pose positions
	tPoses = []
	for b in range(boneC):
		boneName = rigBones[b]
		bonePos = NoeVec3.fromBytes(br.readBytes(12)); br.seek(4,1)
		boneRot = NoeQuat.fromBytes(br.readBytes(16)).transpose()
		boneScl = NoeVec3.fromBytes(br.readBytes(12)); br.seek(4,1)
		tPoses.append((bonePos, boneRot, boneScl))
	
	bnMatrices = tPoses
	if type == 1:
		bnMatrices = aPosesMS
	elif type == 2:
		bnMatrices = aPosesLS
	
	#Create Rig:
	bones = []
	for b in range(boneC):
		matrix = bnMatrices[b][1].toMat43() #rotation
		matrix[3] = (matrix[3] + bnMatrices[b][0]) * meshScale #translation
		matrix *= NoeMat43((NoeVec3((bnMatrices[b][2][0],0,0)), NoeVec3((0,bnMatrices[b][2][1],0)), NoeVec3((0,0,bnMatrices[b][2][2])), NoeVec3((0,0,0)))) #scale
		try:
			if b:
				if bindMatrices and bones[parIds[b]].name in meshBones:
					pmat = NoeMat44(bindMatrices[meshBones.index(bones[parIds[b]].name)]).toMat43().inverse()
					pmat[3] *= meshScale
					matrix *= pmat #multiply by mesh parent
				else:
					matrix = matrix * bones[parIds[b]].getMatrix() #multiply by rig parent
				bones.append(NoeBone(b, rigBones[b], matrix, bones[parIds[b]].name, rigBones.index(bones[parIds[b]].name)))
			else:
				bones.append(NoeBone(b, rigBones[b], matrix, None, -1))
		except:
			print ("Failed to build rig")
			return [],[]
	
	
	localMat = NoeMat43(((0, 1, 0), (0, 0, -1), (-1, 0, 0), (0, 0, 0)))
	globalMat = NoeMat43(((-1, 0, 0), (0,  0, 1), ( 0, 1, 0), (0, 0, 0))) 
	
	for b in range(1,len(bones)): 
		bones[b].setMatrix( (bones[b].getMatrix().inverse() * localMat).inverse()) 	#rotate upright in-place
		bones[b].setMatrix( bones[b].getMatrix() * globalMat ) 						#rotate upright in-world
		
	# Return bones and name list
	return [bones, rigBones]	
	
'''////////////////////////////////////////////////////////////////////////////////// MESH IMPORT //////////////////////////////////////////////////////////////////////////////////'''

def findNextOfUInt(bitStream, UIntToFind):
	originalPosition = bitStream.tell()
	finalPosition = -1
	test = bitStream.readUInt()
	while test != UIntToFind and bitStream.tell() + 1 != bitStream.getSize():
		bitStream.seek(-3, 1)
		test = bitStream.readUInt()
	if bitStream.tell() + 1 != bitStream.getSize():
		finalPosition = bitStream.tell() - 4
	bitStream.seek(originalPosition)
	return finalPosition

def LoadModel(data, mdlList):
	global extractedDir
	
	#Save/Load extracted directory
	if extractedDir == "" or not os.path.isdir(extractedDir):
		extractedPath = ""
		txtFile = (noesis.getPluginsPath() + 'python\\CP77ExtractedPath.txt')
		if rapi.checkFileExists(txtFile):
			extractedPath = open(txtFile, "rt").read()
		if (not os.path.isdir(extractedPath) or extractedPath == "") and ("basegame_4_gamedata" in rapi.getInputName() or "basegame_3_nightcity" in rapi.getInputName()) and os.path.isdir((rapi.getInputName().split("basegame_")[0])):
			extractedPath = (rapi.getInputName().split("basegame_")[0])
			print ("Writing extracted archives path to", txtFile)
			open(txtFile, "wt").write(str(extractedPath))
		if os.path.isdir(extractedPath):
			extractedDir = extractedPath
			
	ctx = rapi.rpgCreateContext()	
	#rapi.parseInstanceOptions("-killdupfaces")
	bs = NoeBitStream(data)
	
	foundOffset = findNextOfUInt(bs, 1263681867)
	if foundOffset != -1:
		bs.seek(foundOffset)
	bs.seek(0)
	
	if bFlipImage:
		print("Image/UVs Flip Enabled")
	
	#parse names and CR2W header:
	indexToName, nameToIndex, maxOffset, EXPORTS, exportNames, buffers = ParseHeader(bs)
	checkPoint = bs.tell()
	
	bIsMorphtarget = True if os.path.splitext(rapi.getInputName())[1] == ".morphtarget" else False
	bRiggedModel = True if "boneRigMatrices" in indexToName else False

	#open bitstreams of the main mesh classes inside the file:
	if bIsMorphtarget:
		ext = "morphtarget"
		cMesh = EXPORTS[exportNames.index("MorphTargetMesh")]
		skipFlag = buildFlagFromNames(["targets","array:MorphTargetMeshEntry"],nameToIndex,0)  #this property is sometimes over 1MB in size and must be skipped when scanning for flags, else execution takes 9-10x longer:
		rapi.rpgSetOption(noesis.RPGOPT_MORPH_RELATIVEPOSITIONS, 1)
		rapi.rpgSetOption(noesis.RPGOPT_MORPH_RELATIVENORMALS, 1)
	else:
		ext = "mesh"
		cMesh = EXPORTS[exportNames.index("CMesh")]
		skipFlag = buildFlagFromNames(["topology","array:rendTopologyData"],nameToIndex,0) 
		

	rMesh = EXPORTS[exportNames.index("rendRenderMeshBlob")]
	bs.seek(rMesh.offset)
	rm = NoeBitStream(bs.readBytes(rMesh.dataSize))
	
	if "garmentMeshParamGarment" in exportNames:
		gMesh = EXPORTS[exportNames.index("garmentMeshParamGarment")] 
	elif "meshMeshParamCloth_Graphical" in exportNames:
		gMesh = EXPORTS[exportNames.index("meshMeshParamCloth_Graphical")] 
		
	meshCount = 0
	bufferNo = -1
	
	uncompressedDataFlag = buildFlagFromNames(["renderBuffer","DataBuffer"],nameToIndex,0)
	for i in range(len(EXPORTS)):
		if EXPORTS[i].name == "CMesh":
			meshCount += 1
		if EXPORTS[i].name == "rendRenderMeshBlob" and bufferNo == -1:
			findFlag(rm, uncompressedDataFlag, rMesh.dataSize, skipFlag)
			rm.seek(4,1)
			bufferSize = rm.readUInt()
			rm.seek(4,1)
			if bufferSize > 8:
				bufferStart = rm.tell()
				bfs = NoeBitStream(rm.readBytes(rm.getSize()-rm.tell()))
				rm.seek(0)
				rm = NoeBitStream(rm.readBytes(bufferStart))
			else:
				bufferNo = readUShortAt(bs, EXPORTS[i].dataEnd-6) - 1
			rm.seek(0)
	#print(meshCount, "BufferNo:", bufferNo, EXPORTS[i].dataEnd-6)
	
	bs.seek(cMesh.offset)
	cm = NoeBitStream(bs.readBytes(cMesh.dataSize))
	
	if "rendRenderMorphTargetMeshBlob" in exportNames:
		mMesh = EXPORTS[exportNames.index("rendRenderMorphTargetMeshBlob")] 
		bs.seek(mMesh.offset)
		mm = NoeBitStream(bs.readBytes(mMesh.dataSize))
		

	
	#Quantization info
	quantScaleFlag = buildFlagFromNames(["quantizationScale","Vector4"],nameToIndex,0)
	if not findFlag(rm, quantScaleFlag, rMesh.dataSize, skipFlag):
		print("No quantization scale found")
		return 0
	else:
		rm.seek(0x9,1)
		qScale = []
		for i in range(4):
			rm.seek(0x8,1)
			qScale.append(rm.readFloat())	
	rm.seek(0)
	
	quantOffFlag = buildFlagFromNames(["quantizationOffset","Vector4"],nameToIndex,0)
	if not findFlag(rm, quantOffFlag, rMesh.dataSize, skipFlag):
		print("No quantization offset found")
		return 0
	else:
		rm.seek(0x9,1)
		qOff = []
		for i in range(4):
			rm.seek(0x8,1)
			qOff.append(rm.readFloat())	
	rm.seek(0)
	
	#get different vert/idx counts
	vCounts = []
	idxCounts = []
	vertDefs = []
	
	posFlag = buildFlagFromNames(["numVertices","Uint16"],nameToIndex,0)
	while findFlag(rm, posFlag, rMesh.dataSize, skipFlag):
		rm.seek(8,1)
		vCounts.append(rm.readUShort())
		rm.seek(8,1)
		idxCounts.append(rm.readUInt())
	rm.seek(0)
	submeshCount = len(idxCounts)
	
	#Grab bones if relevant
	if bRiggedModel:
		boneNames=[]; list = []
		if bParentToRootIfNoParent:
			boneNames.append("Noesis_Root")
			list.append([NoeVec4([1,0,0,0]), NoeVec4([0,1,0,0]), NoeVec4([0,0,1,0]), NoeVec4([0,0,0,1])]) #Noesis_Root bone matrix
			
		bones = []; bMap = []
		boneLoadLoop = True
		boneNameFlags = buildFlagFromNames(["boneNames","array:CName"],nameToIndex,0)
		boneFlags = buildFlagFromNames(["boneRigMatrices","array:Matrix"],nameToIndex,0)
		
		if (findFlag(cm, boneNameFlags, cMesh.dataSize, 0) if bIsMorphtarget else findFlag(cm, boneNameFlags, cMesh.dataSize, skipFlag)):
			cm.seek(8,1)
			boneCount = cm.readUInt()
			for i in range(boneCount):
				boneNames.append(indexToName[cm.readUShort()])
				
				
		if (findFlag(cm, boneFlags, cMesh.dataSize, 0) if bIsMorphtarget else findFlag(cm, boneFlags, cMesh.dataSize, skipFlag)):
			cm.seek(4,1)
			sectionSize = cm.readUInt()				
			
			for i in range(boneCount):
				cm.seek(3,1)
				v = []
				for j in range(4):
					cm.seek(11,1)
					for k in range(4):
						cm.seek(8,1)
						v.append(cm.readFloat())
				list.append([NoeVec4(v[4*u:4*u+4]) for u in range(4)])
			
			for i,l in enumerate(list):
				matrix = NoeMat44(l).toMat43()
				if not (bParentToRootIfNoParent and i == 0):
					matrix[3] *= meshScale
					matrix = (matrix * localMat.inverse()).inverse() #rotate it upright in-place
					matrix *= globalMat #rotate it upright in-world
				bone = NoeBone(i, boneNames[i], matrix, None)
				bones.append(bone)
				
			ogBones = copy.copy(bones)
			ogBoneNames = copy.copy(boneNames)
			
			#collect valid rig files for mesh:
			autoRigs = []
			if bAutoDetectRig:
				gameFolders = []
				doBodyRig = False; bLoadedHead = False
				rootFolder = os.path.dirname(rapi.getInputName())
				if os.path.isdir(extractedDir):
					for item in os.listdir(os.path.dirname(extractedDir)):
						if os.path.isdir(os.path.join(os.path.dirname(extractedDir), item)):
							if item.find("basegame_") != -1:
								gameFolders.append(item)
					for boneName in boneNames:
						lower = boneName.lower()
						if lower.find("hips") != -1 or lower.find("hand")  != -1 or lower.find("leg") != -1  or lower.find("spine") != -1:
							doBodyRig = True; break
					
					fName = rapi.getLocalFileName(rapi.getInputName())
					if (len(fName.split("_")) > 2):
						bodyType = fName.split("_")[2].replace("p","")
						for folder in gameFolders:
							if doBodyRig:
								rigFile = getBaseRig(bodyType, folder)
								if rapi.checkFileExists(rigFile):
									autoRigs.append(rigFile)
								rigFile = getBaseRig(bodyType, folder, True)
								if rapi.checkFileExists(rigFile):
									autoRigs.append(rigFile)
							if not bLoadedHead and "Head" in boneNames:
								if fName.find("wa_") != -1 and rapi.checkFileExists(extractedDir + folder + "\\base\\characters\\head\pwa\\h0_000_pwa_c__basehead\\h0_000_pwa_c__basehead_skeleton.rig"):
									autoRigs.append(extractedDir + folder + "\\base\\characters\\head\pwa\\h0_000_pwa_c__basehead\\h0_000_pwa_c__basehead_skeleton.rig")
									bLoadedHead = True
								elif rapi.checkFileExists(extractedDir + folder + "\\base\\characters\\head\\player_base_heads\\player_man_average\\h0_000_pma_c__basehead\\h0_000_pma_c__basehead_skeleton.rig"):
									autoRigs.append(extractedDir + folder + "\\base\\characters\\head\\player_base_heads\\player_man_average\\h0_000_pma_c__basehead\\h0_000_pma_c__basehead_skeleton.rig")
									bLoadedHead = True
						
				inputSplitted = os.path.splitext(rapi.getLocalFileName(rapi.getInputName().lower()))[0].split("_")
				for fileName in os.listdir(os.path.dirname(rapi.getInputName())):
					if os.path.isfile(os.path.join(os.path.dirname(rapi.getInputName()), fileName)):
						lowerName = fileName.lower()
						if fileName.endswith(".rig") and not fileName.endswith("out.rig"):
							autoRigs.append(os.path.join(rootFolder, fileName))
								
			#load rig file	
			if bLoadRigFile or len(autoRigs) > 0:
				rigBones = []
				rigsLoaded = 0
				while boneLoadLoop:
					rigData = None
					if bAutoDetectRig and rigsLoaded < len(autoRigs):
						if rapi.checkFileExists(autoRigs[rigsLoaded]):
							print ("Auto-detected rig file:", rapi.getLocalFileName(autoRigs[rigsLoaded]))
							rigData = rapi.loadIntoByteArray(autoRigs[rigsLoaded])
					elif bLoadRigFile:
						rigData = rapi.loadPairedFileOptional("rig file", ".rig")
						if rigData is not None:
							print ("Loading selected rig file...")
							
					#merge rig skeleton with skeleton:
					if rigData is not None:
						br = NoeBitStream(rigData)
						rigBones, glBoneNames = LoadRig(br, ogBoneNames, list)
						
						if rigBones:
							newBones = []
							newBoneNames = []; uniqueCopyBoneNames = []
							copyBoneNames = copy.copy(boneNames)
							copyBoneNames.extend(copy.copy(glBoneNames))
							#if not bParentToRootIfNoParent and glBoneNames[0] not in boneNames:
							#	copyBoneNames.insert(0, glBoneNames[0])
							
							for boneName in copyBoneNames:
								if boneName not in uniqueCopyBoneNames: 
									uniqueCopyBoneNames.append(boneName)
									
							for b, bName in enumerate(uniqueCopyBoneNames):
								newBone = None
								if bName in ogBoneNames and bName in glBoneNames:
									newBone = ogBones[ogBoneNames.index(bName)]
									if newBone.parentName == None:
										newBone.parentName = rigBones[glBoneNames.index(bName)].parentName
								elif bName in boneNames:
									newBone = bones[boneNames.index(bName)]
								#elif not bParentToRootIfNoParent and bName == glBoneNames[0] and glBoneNames[0] not in boneNames: #add rig root
								#	newBone = rigBones[0]
								
								if newBone is not None:
									if newBone.parentName in glBoneNames and newBone.parentName not in newBoneNames and newBone.parentName not in boneNames: #add only the rigbones bones needed to link meshbones together
										boneChain = []
										parentBone = rigBones[glBoneNames.index(newBone.parentName)]
										while parentBone.name in uniqueCopyBoneNames and parentBone.name not in boneNames and parentBone.name not in newBoneNames:
											boneChain.append(parentBone)
											if parentBone.parentName is not None and parentBone.parentName is not "":
												parentBone = rigBones[glBoneNames.index(parentBone.parentName)]
											else: break
										if boneChain is not None and (bConnectRigToRoot == True or boneChain[len(boneChain)-1].parentName in ogBoneNames):
											for bn in boneChain:
												newBones.append(bn)
												newBones[newBones.index(bn)].index = newBones.index(bn)
												newBoneNames.append(bn.name)
									newBones.append(newBone)
									newBones[newBones.index(newBone)].index = newBones.index(newBone)
									newBoneNames.append(newBone.name)
							bones = newBones
							boneNames = newBoneNames
							rigsLoaded += 1
						else:
							if bLoadRigFile:
								print("Invalid rig file, choose another one")
							else: break
					else:
						boneLoadLoop = False
			
			#fix bone map
			bMap = []
			for ogBoneName in ogBoneNames:
				for b, bone in enumerate(bones):
					if bone.name == ogBoneName and bone.name != "Noesis_Root":
						bMap.append(bone.index)
						break
			rapi.rpgSetBoneMap(bMap)
			
			if bParentToRootIfNoParent:
				for b, bone in enumerate(bones):
					if bone.parentName not in boneNames:
						bone.parentName = "Noesis_Root"
		cm.seek(0)
	
	# Index offsets for multiple meshes
	indOffs = []
	indOffs.append(0)
	if "teOffset" in nameToIndex:
		indOffFlag = buildFlagFromNames(["pe","GpuWrapApieIndexBufferChunkType"],nameToIndex,0)
		for i in range(submeshCount):
			if findFlag(rm, indOffFlag, rMesh.dataSize, skipFlag):
				if readUShortAt(rm, rm.tell() + 10) < len(indexToName) and indexToName[readUShortAt(rm, rm.tell()+10)] == "teOffset":
					indOffs.append(readUIntAt(rm, rm.tell()+18))
				elif i > 0:
					indOffs.append(0)
				rm.seek(22,1)
		rm.seek(0)
	
	# Vertex Component Definitions
	vDefFlag = buildFlagFromNames(["vertexLayout","GpuWrapApiVertexLayoutDesc"],nameToIndex,0)
	uvSeen = 0
	
	# Garment mesh data (type 2)
	doGarmentMesh = False
	doGarmentMesh2 = False #partially implemented
	if "garmentMeshParamGarment" in nameToIndex or "meshMeshParamCloth_Graphical" in exportNames:
		if "garmentMeshParamGarment" in nameToIndex:
			doGarmentMesh = True
			gMesh = EXPORTS[exportNames.index("garmentMeshParamGarment")]
		elif "meshMeshParamCloth_Graphical" in nameToIndex:
			doGarmentMesh2 = True
			gMesh = EXPORTS[exportNames.index("meshMeshParamCloth_Graphical")]
		
		bs.seek(gMesh.offset)
		GMESHES = parseGarmentMesh(bs, indexToName, nameToIndex, gMesh, doGarmentMesh, doGarmentMesh2, skipFlag)
	
	#collect morphtarget info:
	if bIsMorphtarget and bImportMorphtargets:
		allDiffsList = parseMorphs(mm, mMesh, nameToIndex, submeshCount, vCounts)
		
	bExtraDataTypeTwo = -1
	while findFlag(rm, vDefFlag, rMesh.dataSize, skipFlag):
		rm.seek(17, 1)
		compC = rm.readInt()
		rm.seek(1, 1)
		
		vertDef = []
		for c in range(compC):
			rm.seek(8, 1)
			compTInd = rm.readUShort()
			rm.seek(8, 1)
			compNInd = rm.readUShort()
			
			if compTInd >= len(indexToName) or compNInd >= len(indexToName):
				break
			
			compType = indexToName[compTInd]
			compName = indexToName[compNInd]
			
			if compName == "PS_TexCoord":
				uvSeen = 1
				
			if uvSeen == 1:
				uvSeen = 0
				
			if compName == "PS_ExtraData":
				bExtraDataTypeTwo += 1
				
			vertDef.append([compName, compType])		
			
			# Skip stream usage/type/index for now
			testName = indexToName[rm.readUShort()]
			if testName == "streamIndex" or testName == "usageIndex":
				rm.seek(7, 1)
				testName = indexToName[rm.readUShort()]
				if testName == "streamIndex":
					rm.seek(7, 1)
					testName = indexToName[rm.readUShort()]
					if testName == "streamType":
						rm.seek(11, 1)
					else:
						rm.seek(1, 1)
				elif testName == "streamType":
					rm.seek(11, 1)
				else:
					rm.seek(1, 1)
			else:
				rm.seek(1, 1)
				
			if compName == "PS_DestructionIndices":
				rm.seek(22, 1)
		vertDefs.append(vertDef)
	rm.seek(0)
	cmpOffFlag = buildFlagFromNames(["byteOffsets","static:5,Uint32"],nameToIndex,0)
	
	# Vertex component offsets
	vCompOffs = []
	while findFlag(rm, cmpOffFlag, rMesh.dataSize, skipFlag):
		rm.seek(8, 1)
		offC = rm.readInt()
		offs = []
		for a in range(offC):
			offs.append(rm.readInt())
		vCompOffs.append(offs)	
	rm.seek(0)
	
	#Get index section offset
	indexOfsFlag = buildFlagFromNames(["indexBufferOffset","Uint32"],nameToIndex,0)
	if not findFlag(rm, indexOfsFlag, rMesh.dataSize, skipFlag):
		print("Couldn't find index offset")
		return 0
	else:
		rm.seek(8,1)
		idxOffset = rm.readUInt()
	rm.seek(0)
	
	#Grab LOD info
	lodInfo = []
	LODInfoFlag = buildFlagFromNames(["lodMask","Uint8"],nameToIndex,0)
	while findFlag(rm, LODInfoFlag, rMesh.dataSize, skipFlag):
		rm.seek(8, 1)
		lodInfo.append(rm.readUByte())
	rm.seek(0)
	 
	
	if bufferNo > -1:
		bfs = GetCR2WBuffer(bs, buffers, ext, bufferNo)
		
	if not bfs or bfs.getSize() == 0:
		print ("Failed to acquire Vertex Buffer")
		return 0
	
	#rapi context settings
	rapi.rpgSetTransform((NoeVec3((-1,0,0)), NoeVec3((0,0,1)), NoeVec3((0,1,0)), NoeVec3((0,0,0)))) 
	rapi.rpgSetOption(noesis.RPGOPT_TRIWINDBACKWARD, 1)
	if bFlipImage:
		rapi.rpgSetUVScaleBias(NoeVec3 ((1.0, -1.0, 1.0)), NoeVec3 ((-1.0, 1.0, 1.0)), 0)
		rapi.rpgSetUVScaleBias(NoeVec3 ((1.0, -1.0, 1.0)), NoeVec3 ((-1.0, 1.0, 1.0)), 1)
	
	#Parsing semantics
	posBuffers = []
	posBuffers2 = []
	uvBuffers = []
	normBuffers = []
	posBStrides = []
	vDefInd = 0
	currentLOD = lodInfo[0]
	damageBuffer = 0
	isHairMesh = False
	
	for i,vc in enumerate(vCounts):
		if i >= len(indOffs):
			break
		if bHighestLODOnly and i < len(lodInfo) and lodInfo[i] != currentLOD:  #build previous LOD as new NoeModel
			try:
				mdl = rapi.rpgConstructModelAndSort()
			except:
				mdl = NoeModel()
			if bRiggedModel and bones: 
				mdl.setBones(bones)
			mdlList.append(mdl)
			currentLOD = lodInfo[i]
			ctx = rapi.rpgCreateContext()	
			
			#reset rapi context settings
			rapi.rpgSetTransform((NoeVec3((-1,0,0)), NoeVec3((0,0,1)), NoeVec3((0,1,0)), NoeVec3((0,0,0)))) 
			if bFlipImage:
				rapi.rpgSetUVScaleBias(NoeVec3 ((1.0, -1.0, 1.0)), NoeVec3 ((-1.0, 1.0, 1.0)), 0)
				rapi.rpgSetUVScaleBias(NoeVec3 ((1.0, -1.0, 1.0)), NoeVec3 ((-1.0, 1.0, 1.0)), 1)
			if isHairMesh:
				rapi.rpgSetOption(noesis.RPGOPT_FIXTRIWINDINGS, 1)
			else:
				rapi.rpgSetOption(noesis.RPGOPT_TRIWINDBACKWARD, 1)	
		
		if isHairMesh == False:
			bfs.seek(idxOffset + indOffs[i])
			testFcOne  = [bfs.readUShort(), bfs.readUShort(), bfs.readUShort()]; testFcTwo  = [bfs.readUShort(), bfs.readUShort(), bfs.readUShort()]
			if testFcOne == [testFcTwo[0], testFcTwo[2], testFcTwo[1]]:
				isHairMesh = True 
				rapi.rpgSetOption(noesis.RPGOPT_TRIWINDBACKWARD, 0)	
				rapi.rpgSetOption(noesis.RPGOPT_FIXTRIWINDINGS, 1)
			else:
				rapi.rpgSetOption(noesis.RPGOPT_TRIWINDBACKWARD, 1)
		
		vertDef = vertDefs[vDefInd]
		vCompOff = vCompOffs[vDefInd]
		vDefInd = vDefInd + 1
		skinBICount = 0
		skinBWCount = 0		
		posBStride = 8
		for comp in vertDef:
			if comp[0] == "PS_SkinIndices":
				skinBICount +=1
				posBStride+=4
			elif comp[0] == "PS_SkinWeights":
				skinBWCount +=1
				posBStride+=4
			elif comp[0] == "PS_ExtraData" and not bExtraDataTypeTwo > submeshCount:
				posBStride+=8
			
		uvAdded = 0
		if(vCompOff[0] < bfs.getSize()):
			bfs.seek(vCompOff[0])
		else:
			print("Positions: Error, wrong buffer file used, try to rename the mesh and the .buffer")
			print(vCompOff[0],bfs.getSize())
			print (bfs.getSize())
			return 0
		
		for comp in vertDef:
			#positions
			start = bfs.tell()
			if comp[0] == "PS_Position":
				buffer = bfs.readBytes(vc*(posBStride))
				posList = []
				for v in range(vc):
					idx = posBStride * v
					vx  = (float((struct.unpack_from('h', buffer, idx))[0]) / 32767.0)
					vy  = (float((struct.unpack_from('h', buffer, idx + 2))[0]) / 32767.0)
					vz  = (float((struct.unpack_from('h', buffer, idx + 4))[0]) / 32767.0)
					posList.append((vx * qScale[0] + qOff[0]) * meshScale) 
					posList.append((vy * qScale[1] + qOff[1]) * meshScale)
					posList.append((vz * qScale[2] + qOff[2]) * meshScale)
				
				posBuff = struct.pack("<" + 'f'*len(posList), *posList)
				rapi.rpgBindPositionBufferOfs(posBuff, noesis.RPGEODATA_FLOAT, 12, 0)
					
				if doGarmentMesh or doGarmentMesh2:
				
					vtxStream = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].vertices)
					
					if vtxStream:
						GposList = []
						for v in range(vc):
							GposList.append(vtxStream.readFloat() * meshScale) 
							GposList.append(vtxStream.readFloat() * meshScale)
							GposList.append(vtxStream.readFloat() * meshScale)
						gPosBuff = struct.pack("<" + 'f'*len(GposList), *GposList)
						
					mphStream = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].morphOffsets)
					if mphStream:
						morphList = []
						for v in range(vc):
							morphList.append(mphStream.readFloat() * meshScale) 
							morphList.append(mphStream.readFloat() * meshScale)
							morphList.append(mphStream.readFloat() * meshScale)
						#posBuff = struct.pack("<" + 'f'*len(morphList), *morphList)
					
					#force reverse GarmentMesh winding order:
					#gmFacesList = []
					#facesBuff = .getBuffer()
					#for idx in range(0, int(len(facesBuff)/2), 3):
					#	gmFacesList.extend([struct.unpack_from('h', facesBuff, idx*2)[0], struct.unpack_from('h', facesBuff, idx*2 + 4)[0], struct.unpack_from('h', facesBuff, idx*2 + 2)[0]])
					#facesStream = NoeBitStream(struct.pack("<" + 'h'*len(gmFacesList), *gmFacesList))
					facesStream = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].indices)
					
					if doGarmentMesh2:
						gs = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].skinIndices)
						if gs: 
							idxStream = NoeBitStream()
							if GMESHES[i].skinIndicesExt != -1:
								gs2 = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].skinIndicesExt)
								if gs2: 
									for j in range(gs2.getSize()):
										idxStream.writeBytes(gs.readBytes(4))
										idxStream.writeBytes(gs2.readBytes(4))
							if idxStream.getSize(): rapi.rpgBindBoneIndexBuffer(idxStream.getBuffer(), noesis.RPGEODATA_UBYTE, 8, 8)
							else: rapi.rpgBindBoneIndexBuffer(gs.getBuffer(), noesis.RPGEODATA_UBYTE, 4, 4)
								
						gsW = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].skinWeights)
						if gsW:
							if GMESHES[i].skinWeightsExt != -1:
								weightStream = NoeBitStream()
								gs2 = GetCR2WBuffer(bs, buffers, ext, GMESHES[i].skinWeightsExt)
								if gs2:
									for j in range(int(gs2.getSize() / 8)):
										weightStream.writeBytes(gsW.readBytes(16))
										weightStream.writeBytes(gs2.readBytes(16))
								if weightStream.getSize(): rapi.rpgBindBoneWeightBuffer(weightStream.getBuffer(), noesis.RPGEODATA_FLOAT, 32, 8)
								else: rapi.rpgBindBoneWeightBuffer(gs2.getBuffer(), noesis.RPGEODATA_FLOAT, 16, 4)
				
				if skinBICount > 0:
					rapi.rpgBindBoneIndexBufferOfs(buffer, noesis.RPGEODATA_UBYTE, posBStride, 8, 4 * skinBICount)
					rapi.rpgBindBoneWeightBufferOfs(buffer, noesis.RPGEODATA_UBYTE, posBStride, 8 + 4 * skinBICount, 4 * skinBWCount)
				
			elif comp[0] == "PS_TexCoord": 
				if uvAdded == 0:
					if(vCompOff[1] < bfs.getSize()):		
						bfs.seek(vCompOff[1])
					else:
						print("UV1: Error, wrong buffer file used, try to rename the mesh and the .buffer")
						return 0
					uv1buff = bfs.readBytes(vc*4)
					rapi.rpgBindUV1Buffer(uv1buff, noesis.RPGEODATA_HALFFLOAT, 4)
				elif uvAdded == 1: 
					if(vCompOff[3] < bfs.getSize()):		
						bfs.seek(vCompOff[3])
					else:
						print("UV2: Error, wrong buffer file used, try to rename the mesh and the .buffer")
						return 0
						
					uv2buff = bfs.readBytes(vc*8)
					rapi.rpgBindUV2BufferOfs(uv2buff, noesis.RPGEODATA_HALFFLOAT, 8, 4)
					if bVertexColors:
						rapi.rpgBindColorBufferOfs(uv2buff, noesis.RPGEODATA_UBYTE, 8, 0, 4)
				uvAdded = uvAdded + 1
				
			elif comp[0] == "PS_Normal":
				if(vCompOff[2] < bfs.getSize()):		
					bfs.seek(vCompOff[2])
				else:
					print("Normals: Error, wrong buffer file used, try to rename the mesh and the .buffer")
					return 0
				nrmList = []
				tanList = []
				for v in range(vc):
					norm = bfs.readInt()
					tan = bfs.readInt()
					nX = ((((norm & 1023)) ) - 511) / 512.0
					nY = ((((norm >> 10) & 1023) ) - 511) / 512.0
					nZ = ((((norm >> 20) & 1023) ) - 511) / 512.0
					nW = (int(((norm >> 30)) / 127.0)) / 3.0
					nrmList.append(nX)
					nrmList.append(nY)
					nrmList.append(nZ)
					if bReadTangents:
						tX = ((((tan & 1023)) ) - 511) / 512.0
						tY = ((((tan >> 10) & 1023) ) - 511) / 512.0
						tZ = ((((tan >> 20) & 1023) ) - 511) / 512.0
						tW = (int(((tan >> 30)) / 127.0)) / 3.0
						tanList.append(tX)
						tanList.append(tY)
						tanList.append(tZ)
						tanList.append(tW)
					
				#print ("Normals end:", bfs.tell())
				nrmBuff = struct.pack("<" + 'f'*len(nrmList), *nrmList)
				
				#rapi.rpgBindNormalBuffer(nrmBuff, noesis.RPGEODATA_FLOAT, 12)
				if bReadTangents:
					tanBuff = struct.pack("<" + 'f'*len(tanList), *tanList)
					rapi.rpgBindTangentBuffer(tanBuff, noesis.RPGEODATA_FLOAT, 16)
					
				if bIsMorphtarget and bImportMorphtargets:
					
					for t in range(1, len(allDiffsList)):
						#for j in range(len(allDiffsList[t])):
						j = i
						morphBStream = NoeBitStream()
						for k in range(0, len(allDiffsList[t][j][0])):
							morphBStream.writeBytes((allDiffsList[t][j][0][k] * (meshScale/2)).toBytes())
								
						#morphBuff = struct.pack("<" + 'f'*len(morphList), *morphList)
						#morphNormsBuff = struct.pack("<" + 'f'*len(morphNormsList), *morphNormsList)
						rapi.rpgFeedMorphTargetPositions(morphBStream.getBuffer(), noesis.RPGEODATA_FLOAT, 12)
						#rapi.rpgFeedMorphTargetNormals(morphNormsBuff, noesis.RPGEODATA_FLOAT, 12)
						rapi.rpgCommitMorphFrame(len(allDiffsList[t][j][0]))
					rapi.rpgCommitMorphFrameSet()
						
			elif comp[0] == "PS_VehicleDmgPosition":
				if(vCompOff[4] < bfs.getSize()):		
					bfs.seek(vCompOff[4])
				else:
					print("Normals: Error, wrong buffer file used, try to rename the mesh and the .buffer")
					return 0
				db = NoeBitStream()
				dn = NoeBitStream()
				for v in range(vc):
					dNorm = bfs.readInt()
					nX = ((((dNorm & 1023)) ) - 511) / 512.0
					nY = ((((dNorm >> 10) & 1023) ) - 511) / 512.0
					nZ = ((((dNorm >> 20) & 1023) ) - 511) / 512.0
					dn.writeFloat(nX)
					dn.writeFloat(nY)
					dn.writeFloat(nZ)
					dx = bfs.readFloat() * meshScale
					dy = bfs.readFloat() * meshScale
					dz = bfs.readFloat() * meshScale
					dw = bfs.readFloat()
					db.writeFloat(dx * 100)
					db.writeFloat(dy * 100)
					db.writeFloat(dz * 100)
				
				damageBuffer = db.getBuffer()
				damageNormals = dn.getBuffer()
				
			else:
				continue
				
		#grab indices, commit, clear buffers
		rapi.rpgSetName("submesh"+str(i))
		rapi.rpgSetMaterial("")
		
		bfs.seek(idxOffset + indOffs[i])
		idxBuff = bfs.readBytes(idxCounts[i]*2)
		#facesList = []
		#for idx in range(0, int(len(idxBuff)/2), 3):
		#	facesList.extend([struct.unpack_from('h', idxBuff, idx*2)[0], struct.unpack_from('h', idxBuff, idx*2 + 4)[0], struct.unpack_from('h', idxBuff, idx*2 + 2)[0]])
		#idxBuff = struct.pack("<" + 'h'*len(facesList), *facesList)
		
		rapi.rpgBindNormalBuffer(nrmBuff, noesis.RPGEODATA_FLOAT, 12)
		
		try:
			rapi.rpgCommitTriangles(idxBuff, noesis.RPGEODATA_USHORT, idxCounts[i], noesis.RPGEO_TRIANGLE, 1)
		except:
			print ("Failed to construct mesh \"submesh" + str(i) + "\"")
		
		if damageBuffer != 0 and bImportExportDamageMeshes:
			rapi.rpgSetName("submesh"+str(i)+"_damageMesh")
			rapi.rpgSetMaterial("")
			rapi.rpgSetTransform((NoeVec3((-1,0,0)), NoeVec3((0,0,1)), NoeVec3((0,1,0)), NoeVec3((0,0,0)))) 
			rapi.rpgBindPositionBufferOfs(damageBuffer, noesis.RPGEODATA_FLOAT, 12, 0)
			rapi.rpgBindNormalBuffer(damageNormals, noesis.RPGEODATA_FLOAT, 12) 
			rapi.rpgCommitTriangles(idxBuff, noesis.RPGEODATA_USHORT, idxCounts[i], noesis.RPGEO_TRIANGLE, 1)
			
		rapi.rpgClearBufferBinds()
		if bImportGarmentMesh and (doGarmentMesh or doGarmentMesh2):
			try:
				rapi.rpgSetPosScaleBias(NoeVec3((100,100,100)), None)
				rapi.rpgBindPositionBufferOfs(vtxStream.getBuffer(), noesis.RPGEODATA_FLOAT, 12, 0)
				rapi.rpgSetName("submesh"+str(i)+"_garmentMesh")
				rapi.rpgCommitTriangles(facesStream.getBuffer(), noesis.RPGEODATA_USHORT, int(facesStream.getSize()/2), noesis.RPGEO_TRIANGLE, 1)
			except:
				print("Failed to construct Garment Mesh", i) 
			rapi.rpgSetPosScaleBias(NoeVec3((1,1,1)), None)
			rapi.rpgClearBufferBinds()
			
	#rapi.rpgOptimize()
	#rapi.rpgUnifyBinormals(0)
	#rapi.rpgFlatNormals()
	#rapi.rpgSmoothTangents()
	#rapi.rpgSmoothNormals()
	
	try:
		mdl = rapi.rpgConstructModelAndSort()
	except:
		mdl = NoeModel()
		
	if noesis.optWasInvoked("-cp77optimize"):
		rapi.rpgOptimize()
		
	if bRiggedModel and bones: 
		mdl.setBones(bones)
	mdlList.append(mdl)
	
	
	if mdlList[0].meshes and not rapi.noesisIsExporting() and mdlList[0].meshes[0].name.find("_") != -1:
		print ("WARNING: Mesh split detected!\nUse the advanced option '-fbxmeshmerge' when exporting this model to FBX.")
	
	'''for mesh in mdl.meshes:
		for uvs in mesh.uvs: 
			uvs[0] = uvs[0] % 1.0
			uvs[1] = uvs[1] % 1.0
	if bImportMorphtargets:
		print ("")
		counter = 0
		for mesh in mdl.meshes:
			for m, mf in enumerate(mesh.morphList):
				print ("morph info:")
				#print ("len(mf.positions):", len(mf.positions))
				#print ("len(mf.normals):", len(mf.normals))
				for v, vec in enumerate(mf.positions):
					if vec != mesh.positions[v] and counter < 50:
						print (m, v, vec * (1/meshScale))
						print ("pos", mesh.positions[v] * (1/meshScale))
						counter += 1
				break'''
	print ("")
	return 1	
	
'''////////////////////////////////////////////////////////////////////////////////// MESH EXPORT //////////////////////////////////////////////////////////////////////////////////'''	
	
def meshWriteModel(mdl, outfile):
	global meshScale
		
	def getExportName(fileName):		
		if fileName == None:
			expOverMeshName = re.sub(r'out\w+\.', '.', rapi.getOutputName().lower()).replace("fbx",".").replace("out.mesh",".mesh").replace("out.morphtarget",".morphtarget")
		else:
			expOverMeshName = fileName
		expOverMeshName = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Export over .mesh", "Choose a .mesh file to export over", expOverMeshName, None)
		
		if expOverMeshName == None:
			print("Aborting...")
			return
		return expOverMeshName
		
	bWriteBonesOnly = noesis.optWasInvoked("-bones")
	bWriteBones = bWriteBonesOnly or noesis.optWasInvoked("-meshbones")
	bWriteRig = noesis.optWasInvoked("-rig")
	bWriteNewBones = noesis.optWasInvoked("-newbones")
	
	ctx = rapi.rpgCreateContext()
	nf = NoeBitStream()
	
	print ("\n		  ----Cyberpunk 2077 MESH Export----\n			by alphaZomega\nOpen fmt_CP77mesh.py in your Noesis plugins folder to change global options\n\nAdvanced Options:")
	print ("  -bones = Creates a copy of the picked mesh with bone positions from your FBX")
	print ("  -meshbones = Exports new mesh with new bone positions")
	print ("  -rig = Exports new rig file with new bone positions")
	print ("  -vf [factory] = Changes morphtarget Vertex Factory \n\n")
	
	fileName = None
	if noesis.optWasInvoked("-meshfile"):
		expOverMeshName = noesis.optGetArg("-meshfile")
	else:
		expOverMeshName = getExportName(fileName)
		
	if expOverMeshName == None:
		return 0
	while not (rapi.checkFileExists(expOverMeshName)):
		print ("File not found!")
		expOverMeshName = getExportName(fileName)	
		fileName = expOverMeshName
		if expOverMeshName == None:
			return 0
			
	newMesh = rapi.loadIntoByteArray(expOverMeshName)
	f = NoeBitStream(newMesh)
	magic = f.readUInt() 
	if magic != 1462915651:
		noesis.messagePrompt("Not a .mesh file.\nAborting...")
		return 0
		
	f.seek(0)
	names, nameToIndex, maxOffset, EXPORTS, exportNames, buffers = ParseHeader(f)	
	
	f.seek(0)
	nf.writeBytes(f.readBytes(f.getSize())) #copy file
	meshCount = 0
	bufferNo = -1
	bIsMorphtarget = True if "MorphTargetMesh" in exportNames else False
	
	#open bitstreams of the two main mesh classes inside the file:
	if bIsMorphtarget == True:
		cMesh = EXPORTS[exportNames.index("MorphTargetMesh")]
	else:
		cMesh = EXPORTS[exportNames.index("CMesh")]
		ext = "mesh"
		
	f.seek(cMesh.offset)
	cm = NoeBitStream(f.readBytes(cMesh.dataSize))
	rMesh = EXPORTS[exportNames.index("rendRenderMeshBlob")]
	f.seek(rMesh.offset)
	rm = NoeBitStream(f.readBytes(rMesh.dataSize))
	
	bRiggedModel = True if "boneRigMatrices" in names else False
	
	#build flags:
	skipFlag = buildFlagFromNames(["topology","array:rendTopologyData"],nameToIndex,0) 
	quantScaleFlag = buildFlagFromNames(["quantizationScale","Vector4"],nameToIndex,0)
	quantOffFlag = buildFlagFromNames(["quantizationOffset","Vector4"],nameToIndex,0)
	posFlag = buildFlagFromNames(["numVertices","Uint16"],nameToIndex,0)
	cmpOffFlag = buildFlagFromNames(["byteOffsets","static:5,Uint32"],nameToIndex,0)
	vDefFlag = buildFlagFromNames(["vertexLayout","GpuWrapApiVertexLayoutDesc"],nameToIndex,0)
	indOffFlag = buildFlagFromNames(["teOffset","Uint32"],nameToIndex,0)
	lodFlag = buildFlagFromNames(["lodMask","Uint8"],nameToIndex,0)
	indexOfsFlag = buildFlagFromNames(["indexBufferOffset","Uint32"],nameToIndex,0)
	uncompressedDataFlag = buildFlagFromNames(["renderBuffer","DataBuffer"],nameToIndex,0)
	if bRiggedModel:
		boneFlags = buildFlagFromNames(["boneRigMatrices","array:Matrix"],nameToIndex,0)
		bnNamesFlag = buildFlagFromNames(["boneNames", "array:CName"],nameToIndex,0)
		
	for i in range(len(EXPORTS)):
		if EXPORTS[i].name == "CMesh":
			meshCount += 1
		if EXPORTS[i].name == "rendRenderMeshBlob" and bufferNo == -1:
			findFlag(rm, uncompressedDataFlag, rMesh.dataSize, skipFlag) 
			rm.seek(4,1)
			bufferSize = rm.readUInt()
			rm.seek(4,1)
			if bufferSize > 8: #uncompressed DataBuffer
				bufferStart = rm.tell()
				bfs = NoeBitStream(rm.readBytes(rm.getSize()-rm.tell()))
				rm.seek(0)
				rm = NoeBitStream(rm.readBytes(bufferStart))
			else: #regular DataBuffer
				bufferNo = readUShortAt(f, EXPORTS[i].dataEnd-6) - 1
			rm.seek(0)
			
	ext = "mesh"
	if os.path.splitext(expOverMeshName)[1] == ".morphtarget":
		bIsMorphtarget = True
		ext = "morphtarget"
		vFactory = -1
		if noesis.optWasInvoked("-vf"):
			vFactory = int(noesis.optGetArg("-vf"))
			print ("Submesh vertex factories will be set to:", vFactory)
	
	doGarmentMesh = False
	doGarmentMesh2 = False
	if "garmentMeshParamGarment" in names or "meshMeshParamCloth_Graphical" in exportNames:
		if "garmentMeshParamGarment" in names:
			doGarmentMesh = True
			gMesh = EXPORTS[exportNames.index("garmentMeshParamGarment")]
		elif "meshMeshParamCloth_Graphical" in names:
			doGarmentMesh2 = True
			gMesh = EXPORTS[exportNames.index("meshMeshParamCloth_Graphical")]
			
		GMESHES = parseGarmentMesh(f, names, nameToIndex, gMesh, doGarmentMesh, doGarmentMesh2, skipFlag)
	
	if not bCompress:
		#Grab correct paired buffer file (old versions)
		bBufferDetected = False
		thisName = rapi.getLocalFileName(expOverMeshName)
		dir = os.path.dirname(expOverMeshName)
		for root, dirs, files in os.walk(dir):
			for fileName in files:
				lowerName = fileName.lower()
				#print (lowerName, lowerName.split(".")[0], "".join(thisName.split(".")[:-1]), lowerName.split(".")[1], ext)
				#print (rapi.getLocalFileName(lowerName), thisName)
				if lowerName.endswith(".buffer") and lowerName.split(".")[0] == thisName.split(".")[0]:
					
					bufferPath = os.path.join(root, fileName)
					if (rapi.checkFileExists(bufferPath)):
						bs2 = NoeBitStream(rapi.loadIntoByteArray(bufferPath))					
						bs2.seek(0x6,1)
						if bs2.readUShort()==0x7FFF:
							og = NoeBitStream(rapi.loadIntoByteArray(bufferPath))
							print("Detected Vertex Buffer: " + lowerName)
							bBufferDetected = True
							break
		if not bBufferDetected:
			print ("No buffer file was detected.")
		elif bWriteBones:
			bs.writeBytes(og.readBytes(og.getSize())) #clone file:
			bs.seek(0)
						
	bs = NoeBitStream()	
	#find bone names
	if bRiggedModel:
		if findFlag(cm, bnNamesFlag, cMesh.dataSize, skipFlag):
			cm.seek(8,1)
			boneCount = cm.readUInt()
			boneNames = []
			for i in range(boneCount):
				boneNames.append(names[cm.readUShort()])	
			cm.seek(0)
		#Write new bone positions:
		if bWriteBones or bWriteRig:
			if bWriteBones:
				if findFlag(cm, boneFlags, cMesh.dataSize, skipFlag):
					cm.seek(8,1)
					bnRigMatrixCount = cm.readUInt()
					for i in range(boneCount):
						fbxBoneIdx = -1
						for b, bone in enumerate(mdl.bones):
							if boneNames[i] == bone.name:
								fbxBoneIdx = b
								break

						#print (i, len(boneNames))
						if fbxBoneIdx != -1:
							matrix = ((mdl.bones[fbxBoneIdx].getMatrix()).inverse() * localMat).toMat44() #rotate back in-place
							nf.seek(cm.tell() + cMesh.offset + (i * 239) + 17 + 1)
							#print ("Writing bone", boneNames[i], "at", nf.tell(), "using bone", mdl.bones[fbxBoneIdx].name)
							nf.writeFloat(-matrix[0][0])
							nf.seek(8,1)
							nf.writeFloat(-matrix[0][1])
							nf.seek(8,1)
							nf.writeFloat(-matrix[0][2])
							nf.seek(31,1)
							nf.writeFloat(matrix[2][0])
							nf.seek(8,1)
							nf.writeFloat(matrix[2][1])
							nf.seek(8,1)
							nf.writeFloat(matrix[2][2])
							nf.seek(31,1)
							nf.writeFloat(matrix[1][0])
							nf.seek(8,1)
							nf.writeFloat(matrix[1][1])
							nf.seek(8,1)
							nf.writeFloat(matrix[1][2])
							nf.seek(31,1)
							nf.writeFloat(matrix[3][0] * (1 / meshScale)) 
							nf.seek(8,1)
							nf.writeFloat(matrix[3][1] * (1 / meshScale))
							nf.seek(8,1)
							nf.writeFloat(matrix[3][2] * (1 / meshScale))
						else:
							print ("No match for bone", boneNames[i], "found in FBX")
							
					cm.seek(0)
				
			#write new rig file:
			if bWriteRig:
				rigData = rapi.loadPairedFileOptional("rig file", ".rig")
				if rigData is not None:
					ogRigBytes = rigData
					ogRig = NoeBitStream(ogRigBytes)
					nuRig = NoeBitStream()
					nuRig.writeBytes(ogRig.readBytes(ogRig.getSize()))
					rigIdxToName, rigNameToIdx, rigMaxOffset, rigEXPORTS, rigExportNames, rigBuffers = ParseHeader(nuRig)
					checkPoint = nuRig.tell()
					
					# Read bone names
					glBoneNames = []
					rigBnNamesFlag = buildFlagFromNames(["boneNames","array:CName"], rigNameToIdx, 0)
					if findFlag(nuRig, rigBnNamesFlag, rigMaxOffset, 0):
						nuRig.seek(0x8,1)
						boneC = nuRig.readInt()
						for i in range(boneC):
							glBoneNames.append(rigIdxToName[nuRig.readUShort()])
						nuRig.seek(checkPoint)
						
						#prepare matrices for writing
						rigTRSes = []; mdlBoneNames = []
						for bone in mdl.bones:
							mdlBoneNames.append(bone.name)
							matrix = (bone.getMatrix().inverse() * localMat).inverse() #rotate back in-place
							if bone.parentIndex > -1:
								matrix *= (mdl.bones[bone.parentIndex].getMatrix().inverse() * localMat.inverse()) #rotate parent back in-place (meshBones)
							translation = matrix.toMat44()[3] * (1 / meshScale); translation[3] = 0
							rotation = matrix.toQuat().normalize().transpose()
							scale = [magnitude([matrix[0][0],matrix[1][0],matrix[2][0]]), magnitude([matrix[0][1],matrix[1][1],matrix[2][1]]), magnitude([matrix[0][2],matrix[1][2],matrix[2][2]]), 1]
							rigTRSes.append([translation, rotation, scale])
						
						# Write A-poseLS bones
						if "aPoseLS" in rigIdxToName:
							aposeLSFlag = buildFlagFromNames(["aPoseLS","array:QsTransform"],rigNameToIdx,0)
							if findFlag(nuRig, aposeLSFlag, rigMaxOffset, 0):
								nuRig.seek(8,1)
								apBoneCLS = nuRig.readInt()
								for i in range(apBoneCLS):
									if glBoneNames[i] in mdlBoneNames:
										matrix = rigTRSes[mdlBoneNames.index(glBoneNames[i])]
										pos = nuRig.tell()
										writeFloatAt(nuRig, pos+18, matrix[0][0])
										writeFloatAt(nuRig, pos+30, matrix[0][1])
										writeFloatAt(nuRig, pos+42, matrix[0][2]); pos += 59
										writeFloatAt(nuRig, pos+18, matrix[1][0])
										writeFloatAt(nuRig, pos+30, matrix[1][1])
										writeFloatAt(nuRig, pos+42, matrix[1][2])
										writeFloatAt(nuRig, pos+54, matrix[1][3]); pos += 59
										writeFloatAt(nuRig, pos+18, matrix[2][0])
										writeFloatAt(nuRig, pos+30, matrix[2][1])
										writeFloatAt(nuRig, pos+42, matrix[2][2]); nuRig.seek(pos + 62)
									else:
										nuRig.seek(180,1)
							nuRig.seek(checkPoint)
						
						# Write A-poseMS bones
						if "aPoseMS" in rigIdxToName:
							aposeMSFlag = buildFlagFromNames(["aPoseMS","array:QsTransform"],rigNameToIdx,0)
							if findFlag(nuRig, aposeLSFlag, rigMaxOffset, 0):
								nuRig.seek(8,1)
								apBoneCMS = nuRig.readInt()
								for i in range(apBoneCMS):
									if glBoneNames[i] in mdlBoneNames:
										matrix = rigTRSes[mdlBoneNames.index(glBoneNames[i])]
										pos = nuRig.tell()
										writeFloatAt(nuRig, pos+18, matrix[0][0])
										writeFloatAt(nuRig, pos+30, matrix[0][1])
										writeFloatAt(nuRig, pos+42, matrix[0][2]); pos += 59
										writeFloatAt(nuRig, pos+18, matrix[1][0])
										writeFloatAt(nuRig, pos+30, matrix[1][1])
										writeFloatAt(nuRig, pos+42, matrix[1][2])
										writeFloatAt(nuRig, pos+54, matrix[1][3]); pos += 59
										writeFloatAt(nuRig, pos+18, matrix[2][0])
										writeFloatAt(nuRig, pos+30, matrix[2][1])
										writeFloatAt(nuRig, pos+42, matrix[2][2]); nuRig.seek(pos + 62)
									else:
										nuRig.seek(180,1)
							nuRig.seek(checkPoint)
							
						# Parenting info
						findFlag(nuRig, b'\xFF\xFF\x00\x00', rigMaxOffset, 0)
						parIds = []
						for b in range(boneC):
							wroteBone = False
							for bone in mdl.bones:
								if bone.parentName != "Noesis_Root" and bone.name == glBoneNames[b] and bone.parentName in glBoneNames:
									nuRig.writeUShort(glBoneNames.index(bone.parentName))
									wroteBone = True
									break
							if not wroteBone:
								nuRig.seek(2, 1)
						
						#T R S
						for b in range(boneC):
							wroteBone = False
							for bone in mdl.bones:
								#if bone.parentName != "Noesis_Root" and bone.name == glBoneNames[b] and bone.parentName in glBoneNames:
								if glBoneNames[b] in mdlBoneNames and len(rigTRSes[mdlBoneNames.index(glBoneNames[b])][0]) > 2:
									matrix = rigTRSes[mdlBoneNames.index(glBoneNames[i])]
									bNoRot = True if "aPoseLS" in rigIdxToName else False
									
									for k in range(3):
										for j in range(4):
											if k == 0:
												nuRig.writeFloat(matrix[0][j])
											elif k == 1:
												if bNoRot:
													nuRig.seek(4,1)
												else:
													nuRig.writeFloat(matrix[1][j])
											elif k == 2:
												nuRig.writeFloat(matrix[2][j])
									wroteBone = True
									break	
							if not wroteBone:
								nuRig.seek(48, 1)
								
						outRig = os.path.splitext(rapi.getOutputName())[0] + ".rig"
						open(outRig, "wb").write(nuRig.getBuffer()) 
						print ("Wrote", rapi.getLocalFileName(outRig))
						
			if bWriteBonesOnly:
				return 1
			
	#Grab LOD info
	lodInfo = []
	if bHighestLODOnly:
		if (findFlag(rm, lodFlag, rMesh.dataEnd, skipFlag)):
			rm.seek(8, 1)
			lodInfo.append(rm.readUByte())
		rm.seek(0)
	
	#get different vert/idx counts
	vCounts = []
	idxCounts = []
	vertDefs = []
	
	while findFlag(rm, posFlag, rMesh.dataSize, skipFlag):
		rm.seek(8,1)
		vCounts.append((rm.readUShort(), rm.tell() - 2 + rMesh.offset))
		rm.seek(8,1)
		idxCounts.append((rm.readUInt(), rm.tell() - 4 + rMesh.offset))
	rm.seek(0)
	
	submeshCount = len(idxCounts)
	
	#remove blender numbers
	for bone in mdl.bones:
		if bone.name.find('.') != -1:
			print ("Renaming Bone " + str(bone.name) + " to " + str(bone.name.split('.')[0]))
			bone.name = bone.name.split('.')[0] 
	for mesh in mdl.meshes:
		if mesh.name.find('.') != -1:
			print ("Renaming Mesh " + str(mesh.name) + " to " + str(mesh.name.split('.')[0]))
			mesh.name = mesh.name.split('.')[0] 
	
	#merge Noesis-split meshes back together:	
	meshesToExport = mdl.meshes
	if mdl.meshes[0].name.find("_") == 4:
		print ("WARNING: Noesis-split meshes detected. Merging meshes back together...")
		combinedMeshes = []
		lastMesh = None
		offset = 0
		
		for i, mesh in enumerate(mdl.meshes):
			mesh.name = mesh.name[5:len(mesh.name)]
			
			if lastMesh == None:
				lastMesh = copy.copy(mesh)
				offset += len(mesh.positions)
			elif mesh.name == lastMesh.name:
				if len(lastMesh.positions) == len(mesh.positions) and len(lastMesh.indices) == len(mesh.indices): #ignore real duplicates
					continue
				newIndices = []
				for j in range(len(mesh.indices)):
					newIndices.append(mesh.indices[j]  + offset)
				lastMesh.setPositions((lastMesh.positions + mesh.positions))
				lastMesh.setUVs((lastMesh.uvs + mesh.uvs))
				lastMesh.setUVs((lastMesh.lmUVs + mesh.lmUVs), 1)
				lastMesh.setTangents((lastMesh.tangents + mesh.tangents))
				lastMesh.setWeights((lastMesh.weights + mesh.weights))
				lastMesh.setIndices((lastMesh.indices + tuple(newIndices)))
				offset += len(mesh.positions)
				
			if i == len(mdl.meshes)-1:
				if mesh.name == lastMesh.name:
					combinedMeshes.append(lastMesh)
				else:
					combinedMeshes.append(mesh)
			elif mdl.meshes[i+1].sourceName != mesh.sourceName:
				combinedMeshes.append(lastMesh)
				offset = 0
				lastMesh = None	
		meshesToExport = combinedMeshes
	
	#create list of objects to export:
	submeshes = []
	blankCounter = 0
	doBlankMesh = False
	for i in range(submeshCount):
		bFound = False
		for mesh in meshesToExport:
			try:
				if int(mesh.name.split('submesh')[1]) == i:
					submeshes.append(mesh)
					bFound = True
					break
			except:
				pass
		if bFound == False:
			print ("submesh" + str(i), "was not found in FBX and was omitted")
			blankTangent = NoeMat43((NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0)))) 
			blankWeight = NoeVertWeight([0,0,0,0,0,0,0,0], [1,0,0,0,0,0,0,0])
			blankMesh = NoeMesh([0, 1, 2], [NoeVec3((0.00000000001,0,0)), NoeVec3((0,0.00000000001,0)), NoeVec3((0,0,0.00000000001))], "submesh"+str(i), "submesh"+str(i), -1, -1) #positions and face
			blankMesh.setUVs([NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0))]) #UV1
			blankMesh.setUVs([NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0))], 1) #UV2
			blankMesh.setTangents([blankTangent, blankTangent, blankTangent]) #Normals + Tangents
			if bRiggedModel:
				blankMesh.setWeights([blankWeight,blankWeight,blankWeight]) #Weights + Indices
			submeshes.append(blankMesh) #invisible placeholder submesh
			blankCounter += 1
	if blankCounter == submeshCount:
		doBlankMesh = True
	
	# Index offsets for multiple meshes:
	indOffs = []
	indOffs.append((0,0))
	if "teOffset" in names:
		indOffFlag = buildFlagFromNames(["pe","GpuWrapApieIndexBufferChunkType"],nameToIndex,0)
		for i in range(submeshCount):
			if findFlag(rm, indOffFlag, rMesh.dataSize, skipFlag):
				if readUShortAt(rm, rm.tell() + 10) < len(names) and names[readUShortAt(rm, rm.tell()+10)] == "teOffset":
					indOffs.append((readUIntAt(rm, rm.tell()+18), rm.tell()+18+rMesh.offset))
				elif i > 0:
					indOffs.append((0,0))
					print ("WARNING!! Low LOD mesh submesh" + str(i), "uses same face indices as submesh0 and must \n    have the same geometry as submesh0")
				rm.seek(22,1)
		rm.seek(0)
	elif submeshCount > 1:
		print ("WARNING: Submesh index buffer offset not found")
		
	# Vertex component offsets
	vCompOffs = []
	while findFlag(rm, cmpOffFlag, rMesh.dataSize, skipFlag):
		rm.seek(8, 1)
		offC = rm.readInt()
		offs = []
		for a in range(offC):
			offs.append((rm.readInt(), rm.tell() - 4 + rMesh.offset))
		vCompOffs.append(offs)
	rm.seek(0)
	
	if findFlag(rm, indexOfsFlag, rMesh.dataSize, skipFlag):
		rm.seek(8,1)
		idxOffset = (rm.readUInt(), rm.tell() - 4 + rMesh.offset)
	else:
		print ("Fatal Error: Index buffer offset not found")
		return 0
	rm.seek(0)
	
	#get vertex strides:
	uvSeen = 0
	vertDefs = []
	extraDataIndexOffs = 0
	while findFlag(rm, vDefFlag, rMesh.dataSize, skipFlag):
		rm.seek(17,1)
		compC = rm.readInt()
		rm.seek(1, 1)
		
		vertDef = []
		for c in range(compC):
			rm.seek(8, 1)
			compTInd = rm.readUShort()
			rm.seek(8, 1)
			compNInd = rm.readUShort()
			
			if compTInd >= len(names) or compNInd >= len(names):
				break
			
			compType = names[compTInd]
			compName = names[compNInd]
			if compName == "PS_ExtraData" or compType == "PS_ExtraData":
				extraDataIndexOffs = rm.tell() - 2 + rMesh.offset
				
			if compName == "PS_TexCoord":
				uvSeen = 1
			if uvSeen == 1:
				uvSeen = 0
			
			vertDef.append([compName, compType])		
			
			testName = names[rm.readUShort()]
			if testName == "streamIndex" or testName == "usageIndex":
				rm.seek(7, 1)
				testName = names[rm.readUShort()]
				if testName == "streamIndex":
					rm.seek(7, 1)
					testName = names[rm.readUShort()]
					if testName == "streamType":
						rm.seek(11, 1)
					else:
						rm.seek(1, 1)
				elif testName == "streamType":
					rm.seek(11, 1)
				else:
					rm.seek(1, 1)
			else:
				rm.seek(1, 1)
				
			if compName == "PS_DestructionIndices":
				rm.seek(22, 1)	
				
		vertDefs.append(vertDef)
	rm.seek(0)
	
	#Quantization info 
	findFlag(rm, quantScaleFlag, rMesh.dataSize, skipFlag)
	quantOffs = rm.tell() + rMesh.offset
	rm.seek(0)
	
	if doBlankMesh:
		print ("Warning: Empty Mesh! Make sure your FBX submesh names are correct\n")
		qScale = NoeVec4((1,1,1,0))
		qOff = NoeVec4((0,0,0,1))
	else:
		#compute new quantization scale + offset
		min = NoeVec3((10000000.0, 10000000.0, 10000000.0))
		max = NoeVec3((-10000000.1, -10000000.1, -10000000.1))
		for mesh in submeshes:
			for v in mesh.positions:
				if v[0] > max[0]: 
					max[0] = v[0]
				if v[0] < min[0]: 
					min[0] = v[0]
				if v[1] > max[1]: 
					max[1] = v[1]
				if v[1] < min[1]: 
					min[1] = v[1]
				if v[2] > max[2]: 
					max[2] = v[2]
				if v[2] < min[2]: 
					min[2] = v[2]
		qScale = NoeVec4(((max[0] - min[0]) / 2, (max[1] - min[1]) / 2, (max[2] - min[2]) / 2, 0)) * (1 / meshScale)
		qOff = NoeVec4(((max[0] + min[0]) / 2, (max[1] + min[1]) / 2, (max[2] + min[2]) / 2, 1)) * (1 / meshScale)
		
	vDefInd = 0
	
	if bExportAllBuffers and not bCompress:
		copyBuffers(expOverMeshName, ext, readUIntAt(f, 104))
	
	for i,vc in enumerate(vCounts):
		if i >= len(indOffs):
			break
		
		vertDef = vertDefs[vDefInd]
		vCompOff = vCompOffs[vDefInd]
		vDefInd = vDefInd + 1
		skinBICount = 0
		skinBWCount = 0
			
		posBStride = 8
		for comp in vertDef:
			if comp[0] == "PS_SkinIndices":
				skinBICount +=1
				posBStride+=4
			elif comp[0] == "PS_SkinWeights":
				skinBWCount +=1
				posBStride+=4
			elif comp[0] == "PS_ExtraData":
				posBStride+=8	
		
		uvAdded = 0
		for m, comp in enumerate(vertDef):
			dataStart = bs.tell()
			#positions
			if comp[0] == "PS_Position":	
					
				nf.seek(vCompOff[0][1])
				nf.writeUInt(bs.tell())
				if doGarmentMesh:
					nf.seek(GMESHES[i].offset)
					nf.writeUInt(len(submeshes[i].positions))
					
				gs = NoeBitStream()
				if doGarmentMesh2:
					gsSkinI1 = NoeBitStream()
					gsSkinW1 = NoeBitStream()
					gsSkinI2 = NoeBitStream()
					gsSkinW2 = NoeBitStream()
				else:
					ms = NoeBitStream()
					gfs = NoeBitStream()
				
				#print ("positions start", bs.tell(), "count", len(submeshes[i].positions))
				for v, vert in enumerate(submeshes[i].positions):
					startpos = bs.tell()
					
					valueA =  (int((vert[0] * (1 / meshScale) - qOff[0]) / qScale[0] * 32767.0))
					valueB =  (int((vert[2] * (1 / meshScale) - qOff[2]) / qScale[2] * 32767.0))
					valueC =  (int((vert[1] * (1 / meshScale) - qOff[1]) / qScale[1] * 32767.0))
					bs.writeShort(-valueA)
					bs.writeShort(valueB)
					bs.writeShort(valueC)	
					bs.writeShort(32767)
					
					if doGarmentMesh or doGarmentMesh2:
						gs.writeFloat(vert[0] * (1 / meshScale))
						gs.writeFloat(vert[2] * (1 / meshScale))
						gs.writeFloat(vert[1] * (1 / meshScale))
						if doGarmentMesh:
							ms.writeFloat(0)
							ms.writeFloat(0)
							ms.writeFloat(0)
							gfs.writeUShort(0)
							
					if bRiggedModel:
					
						doRegularWeights = True if (['PS_SkinIndices', 'PT_UByte4']) in vertDef else False
						
						#write 00's
						pos = bs.tell()
						if doRegularWeights:
							for k in range(skinBICount + skinBWCount):
								bs.writeUInt(0)
						bs.seek(pos)
						if doGarmentMesh2:
							if GMESHES[i].skinWeights != -1:
								gsSkinI1.writeUInt(0)
								gsSkinI1.seek(-4,1)
								gsSkinW1.writeUInt64(0); gsSkinW1.writeUInt64(0)
								gsSkinW1.seek(-16,1)
							if GMESHES[i].skinWeightsExt != -1:
								gsSkinI2.writeUInt(0)
								gsSkinI2.seek(-4,1)
								gsSkinW2.writeUInt64(0); gsSkinW2.writeUInt64(0)
								gsSkinW2.seek(-16,1)
							iEndPosOne = gsSkinI1.tell() + 4
							iEndPosTwo = gsSkinI2.tell() + 4
							wEndPosOne = gsSkinW1.tell() + 16
							wEndPosTwo = gsSkinW2.tell() + 16
							
						#bone indices
						lastGoodIdx = 0
						try:
							submeshes[i].weights[0].indices
						except IndexError:
							print ("Error: No rigging detected for submesh" + str(i))
							break
							
						for idx in range(len(submeshes[i].weights[v].indices)):
							if (doGarmentMesh2 == True and GMESHES[i].skinIndicesExt != -1 and idx > 8) or (doGarmentMesh2 == False and idx > skinBWCount * 4): #prevent from going over
								break
							idxToWrite = lastGoodIdx
							if mdl.bones[submeshes[i].weights[v].indices[idx]].name in boneNames:
								idxToWrite = boneNames.index(mdl.bones[submeshes[i].weights[v].indices[idx]].name)
								lastGoodIdx = idxToWrite
							if doRegularWeights:	
								bs.writeUByte(idxToWrite)
							if doGarmentMesh2:
								if idx < 4:
									gsSkinI1.writeUByte(idxToWrite)
								else:
									gsSkinI2.writeUByte(idxToWrite)
						if doRegularWeights:				
							bs.seek(pos + (skinBICount * 4))
						pos = bs.tell()
						
						#skin weights
						for idx in range(len(submeshes[i].weights[v].weights)):
							if (doGarmentMesh2 == True and GMESHES[i].skinWeightsExt != -1 and idx > 8) or (doGarmentMesh2 == False and idx > skinBWCount * 4):
								break
								
							if doRegularWeights:
								bs.writeUByte(int(submeshes[i].weights[v].weights[idx] * 255.0))
							
							if doGarmentMesh2:
								if idx < 4:
									gsSkinW1.writeFloat(submeshes[i].weights[v].weights[idx])
								else:
									gsSkinW2.writeFloat(submeshes[i].weights[v].weights[idx])
									
						if doGarmentMesh2:			
							gsSkinI1.seek(iEndPosOne)
							gsSkinI2.seek(iEndPosTwo)
							gsSkinW1.seek(wEndPosOne)
							gsSkinW2.seek(wEndPosTwo)
					
						if doRegularWeights:
							#ExtraData is for morphOffsets, 4 half floats "X Y Z _"
							if posBStride > bs.tell() - startpos:
								for k in range(posBStride - (bs.tell() - startpos)):
									bs.writeUByte(0)
							else:
								bs.seek(startpos + posBStride)
				if doGarmentMesh or doGarmentMesh2:
					if not bCompress:
						newgMeshVBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].vertices) + ".buffer")
						open(newgMeshVBuff, "wb").write(gs.getBuffer())
						print ("Wrote GarmentMesh (Vertices):", rapi.getLocalFileName(newgMeshVBuff))
						
						if doGarmentMesh2:	
							newGMeshBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].skinWeights) + ".buffer")
							open(newGMeshBuff, "wb").write(gsSkinW1.getBuffer())
							print ("Wrote GarmentMesh (Skin Weights 1):", rapi.getLocalFileName(newGMeshBuff))
							
							newGMeshBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].skinIndices) + ".buffer")
							open(newGMeshBuff, "wb").write(gsSkinI1.getBuffer())
							print ("Wrote GarmentMesh (Skin Indices 1):", rapi.getLocalFileName(newGMeshBuff))
							
							if GMESHES[i].skinWeightsExt != -1:
								newGMeshBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].skinWeightsExt) + ".buffer")
								open(newGMeshBuff, "wb").write(gsSkinW2.getBuffer())
								print ("Wrote GarmentMesh (Skin Weights 2):", rapi.getLocalFileName(newGMeshBuff))
								
							if GMESHES[i].skinIndicesExt != -1:
								newGMeshBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].skinIndicesExt) + ".buffer")
								open(newGMeshBuff, "wb").write(gsSkinI2.getBuffer())
								print ("Wrote GarmentMesh (Skin Indices 2):", rapi.getLocalFileName(newGMeshBuff))
						else:
							newgMeshMOBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].morphOffsets) + ".buffer")
							open(newgMeshMOBuff, "wb").write(ms.getBuffer())
							print ("Wrote GarmentMesh (morphOffsets):", rapi.getLocalFileName(newgMeshMOBuff))
							newgMeshMOBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].garmentFlags) + ".buffer")
							open(newgMeshMOBuff, "wb").write(gfs.getBuffer())
							print ("Wrote GarmentMesh (garmentFlags):", rapi.getLocalFileName(newgMeshMOBuff))
					else:
						buffers = WriteCR2WBuffer(buffers, gs, GMESHES[i].vertices)
						if doGarmentMesh2:
							buffers = WriteCR2WBuffer(buffers, gsSkinW1, GMESHES[i].skinWeights)
							buffers = WriteCR2WBuffer(buffers, gsSkinI1, GMESHES[i].skinIndices)
							if GMESHES[i].skinWeightsExt != -1:
								buffers = WriteCR2WBuffer(buffers, gsSkinW2, GMESHES[i].skinWeightsExt)
							if GMESHES[i].skinIndicesExt != -1:
								buffers = WriteCR2WBuffer(buffers, gsSkinI2, GMESHES[i].skinIndicesExt)
						#else:
						#	buffers = WriteCR2WBuffer(buffers, ms, GMESHES[i].morphOffsets)
						#	buffers = WriteCR2WBuffer(buffers, gfs, GMESHES[i].garmentFlags)
						
				
			elif comp[0] == "PS_TexCoord":
				if uvAdded == 0:
					nf.seek(vCompOff[1][1])
					nf.writeUInt(bs.tell())
						
					for v, vert in enumerate(submeshes[i].uvs):
						pos = bs.tell()
						if bFlipImage:
							bs.writeHalfFloat(vert[0])
							bs.writeHalfFloat(1-vert[1])
						else:
							bs.writeHalfFloat(vert[0])
							bs.writeHalfFloat(vert[1])
					
				elif uvAdded == 1: 
					nf.seek(vCompOff[3][1])
					nf.writeUInt(bs.tell())
						
					try:
						submeshes[i].lmUVs[0][0]
					except IndexError:
						print ("UV2 not found, writing UV1 as UV2")
						submeshes[i].lmUVs = submeshes[i].uvs
						
					for v, vert in enumerate(submeshes[i].lmUVs):
						pos = bs.tell()
						if bVertexColors:
							try:
								bs.writeUByte(int(submeshes[i].colors[v][0] * 255.0))
								bs.writeUByte(int(submeshes[i].colors[v][1] * 255.0))
								bs.writeUByte(int(submeshes[i].colors[v][2] * 255.0))
								bs.writeUByte(int(submeshes[i].colors[v][3] * 255.0))
							except IndexError:
								bs.writeInt(0)
						if bFlipImage:
							bs.writeHalfFloat(vert[0])
							bs.writeHalfFloat(1-vert[1])
						else:
							bs.writeHalfFloat(vert[0])
							bs.writeHalfFloat(vert[1])
						
				uvAdded = uvAdded + 1
				
			elif comp[0] == "PS_Normal":
				nf.seek(vCompOff[2][1])
				nf.writeUInt(bs.tell())
				for v, nrm in enumerate(submeshes[i].tangents):
					nX = int(-(nrm[0][0] * 512.0) + 511.0000001)
					nY = int((nrm[0][2] * 512.0)  + 511.0000001) << 10
					nZ = int((nrm[0][1] * 512.0)  + 511.0000001) << 20
					bs.writeInt(1073741824 | nX | nY | nZ)
					tX = int(-(nrm[2][0] * 512.0)  + 511.0000001)
					tY = int((nrm[2][2] * 512.0) + 511.0000001) << 10
					tZ = int((nrm[2][1] * 512.0)  + 511.0000001) << 20
					bs.writeInt(0 | tX | tY | tZ)
						
			elif comp[0] == "PS_VehicleDmgPosition":
				nf.seek(vCompOff[4][1])
				nf.writeUInt(bs.tell())
				
				theMesh = submeshes[i]
				if bImportExportDamageMeshes:
					for mesh in meshesToExport:
						if mesh.name == "submesh" + str(i) + "_damageMesh" and len(mesh.positions) == len(submeshes[i].positions):
							print("Writing submesh" + str(i) + "_damageMesh")
							theMesh = mesh
							break
				
				for v in range(len(theMesh.positions)):
					nX = int(-(theMesh.tangents[v][0][0] * 512.0) + 511.0000001)
					nY = int((theMesh.tangents[v][0][2] * 512.0)  + 511.0000001) << 10
					nZ = int((theMesh.tangents[v][0][1] * 512.0)  + 511.0000001) << 20
					bs.writeInt(1073741824 | nX | nY | nZ)
					bs.writeFloat(-theMesh.positions[v][0] * (1 / meshScale)  * (1 / 100))
					bs.writeFloat(theMesh.positions[v][2] * (1 / meshScale)  * (1 / 100))
					bs.writeFloat(theMesh.positions[v][1] * (1 / meshScale)  * (1 / 100))
					bs.writeFloat(0)
			else:
				continue
				
			dataSize = bs.tell()-dataStart
			while dataSize % 16 != 0:
				bs.writeUByte(0)
				dataSize += 1
				
	newVertBuffSize = bs.tell()
	
	#padding to make idx buffer offset divisible by 1024
	while bs.tell() % 1024 != 0:
		bs.writeByte(0)
		
	#write faces
	newIdxOffs = bs.tell()
	
	for i, mesh in enumerate(submeshes):
		gs = NoeBitStream()
			
		if len(indOffs) > 1 and indOffs[i][1] != 0:
			nf.seek(indOffs[i][1])
			nf.writeUInt(bs.tell() - newIdxOffs)
			
		for v in range(0, len(mesh.indices), 3):
			pos = bs.tell()
			try:	#reverse winding order
				bs.writeUShort(mesh.indices[v+2])
				bs.writeUShort(mesh.indices[v+1])
				bs.writeUShort(mesh.indices[v])
					
			except IndexError:
				bs.seek(pos+6)	
				
			if doGarmentMesh or doGarmentMesh2:
				gs.writeUShort(mesh.indices[v+2])
				gs.writeUShort(mesh.indices[v+1])
				gs.writeUShort(mesh.indices[v])
		
		if doGarmentMesh or doGarmentMesh2:
			if not bCompress:
				newgMeshFBuff = rapi.getOutputName().replace(".mesh", ".mesh." + str(GMESHES[i].indices) + ".buffer")
				open(newgMeshFBuff, "wb").write(gs.getBuffer())
				print ("Wrote GarmentMesh (Faces):", rapi.getLocalFileName(newgMeshFBuff))
			else:
				buffers = WriteCR2WBuffer(buffers, gs, GMESHES[i].indices)
			
		newIdxBuffSize = bs.tell() - newIdxOffs
		
	#diff = idxOffset[0] + indOffs[len(indOffs)-1][0] + (idxCounts[len(idxCounts)-1][0] * 2) - bs.tell()
	nf.seek(idxOffset[1])
	nf.writeUInt(newIdxOffs)
	nf.seek(-16,1)
	nf.writeUInt(newIdxBuffSize)
	nf.seek(-16,1)
	nf.writeUInt(newVertBuffSize)
		
	#change modded .mesh file:
	nf.seek(quantOffs + 17)
	nf.writeFloat(qScale[0])
	nf.seek(8, 1)
	nf.writeFloat(qScale[2])
	nf.seek(8, 1)
	nf.writeFloat(qScale[1])
	nf.seek(31, 1)
	nf.writeFloat(-qOff[0])
	nf.seek(8, 1)
	nf.writeFloat(qOff[2])
	nf.seek(8, 1)
	nf.writeFloat(qOff[1])
	
	for i, mesh in enumerate(submeshes):
		if len(mesh.positions) != vCounts[i][0]:
			nf.seek(vCounts[i][1])
			nf.writeUShort(len(mesh.positions))
			
		if len(mesh.indices) != idxCounts[i][0]:
			nf.seek(idxCounts[i][1])
			nf.writeUInt(len(mesh.indices))
	
	#remove now-incorrect morphs from morphtarget:
	if bIsMorphtarget:
		targetsFlag = buildFlagFromNames(["targets", "array:MorphTargetMeshEntry"], nameToIndex, 0)
		nf.seek(cMesh.offset)
		if findFlag(nf, targetsFlag, cMesh.offset + cMesh.dataSize, 0):
			nf.seek(8,1)
			nf.writeUInt(0)
		
		nf.seek(cMesh.offset)
		numTargetsFlag = buildFlagFromNames(["numTargets", "Uint32"], nameToIndex, 0)
		if findFlag(nf, numTargetsFlag, cMesh.offset + cMesh.dataSize, targetsFlag):
			nf.seek(8,1)
			nf.writeUInt(0)
			
		nf.seek(cMesh.offset)	
		morphsFlag = buildFlagFromNames(["targetTextureDiffsData", "array:rendRenderMorphTargetMeshBlobTextureData"], nameToIndex, 0)
		if findFlag(nf, morphsFlag, cMesh.offset + cMesh.dataSize, targetsFlag):
			nf.seek(8,1)
			nf.writeUInt(0)
			
		if vFactory != -1:
			vertFactoryFlag = buildFlagFromNames(["vertexFactory", "Uint8"], nameToIndex, 0)
			nf.seek(rMesh.offset)
			if findFlag(nf, vertFactoryFlag, cMesh.dataEnd, 0):
				nf.seek(8,1)
				nf.writeUShort(vFactory)
	
	#LOD hack:
	if bHighestLODOnly:
		LODflag = buildFlagFromNames(["renderLODs" , "array:Float"], nameToIndex, 0)
		nf.seek(rMesh.offset)
		if findFlag(nf, LODflag, maxOffset, skipFlag):
			nf.seek(8,1)
			nf.writeUInt(1)
			
	nf.seek(0)
	if not bCompress:
		newBuffer = rapi.getExtensionlessName(rapi.getOutputName()) + "." + ext + "." + str(bufferNo) + ".buffer"
		outfile.writeBytes(nf.getBuffer()) #write meshfile part
		open(newBuffer, "wb").write(bs.getBuffer())
		print("Wrote", rapi.getLocalFileName(newBuffer))
	else:		
		#buffers = sorted(buffers, key=lambda x: x.offset)
		if bufferNo == -1:
			outfile.writeBytes(nf.readBytes(rMesh.offset+bufferStart-8))
			outfile.writeUInt(bs.getSize()+8)
			outfile.writeUInt(bs.getSize())
			outfile.writeBytes(bs.getBuffer())
			outfile.writeUShort(0)
			nf.seek(bufferStart + bufferSize - 8)
			diff = bs.getSize() - (bufferSize - 8)
			writeUIntAt(outfile, rMesh.exportOffset+8, rMesh.dataSize+diff)
		else:
			buffers = WriteCR2WBuffer(buffers, bs, bufferNo)
			outfile.writeBytes(nf.readBytes(buffers[0].offset)) #write meshfile part
		
		
		for buff in buffers:
			if buff.data.getSize() == 0:
				f.seek(buff.origOffset)
				buff.data.writeBytes(f.readBytes(buff.diskSize))
			buff.offset = outfile.tell()
			outfile.writeBytes(buff.data.getBuffer())
			buff.diskSize = buff.data.getSize()
		for buff in buffers:
			outfile.seek(buff.bufferOffset + 8)
			outfile.writeUInt(buff.offset)
			outfile.writeUInt(buff.diskSize)
			outfile.writeUInt(buff.memSize)
		outfile.seek(28)
		outfile.writeUInt(outfile.getSize()) #bufferSize
		#outfile.writeUInt(4476749) #MOD (CRC)
	
	return 1