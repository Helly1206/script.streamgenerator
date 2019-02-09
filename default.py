import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from xbmc import getCondVisibility as condition, translatePath as translate, log as xbmc_log
from subprocess import PIPE, Popen
import re
import sys
if sys.version_info[0] < 3:
    import urlparse
else:
    import urllib.parse as urlparse
import shutil

__scriptdebug__ = False

__addon__      = xbmcaddon.Addon()
__addonname__  = __addon__.getAddonInfo('name')
__addonid__    = __addon__.getAddonInfo('id')
__cwd__        = __addon__.getAddonInfo('path').decode("utf-8")
__version__    = __addon__.getAddonInfo('version')
__language__   = __addon__.getLocalizedString
__datapath__ = xbmc.translatePath(os.path.join('special://temp/', __addonid__))
__logfile__ = os.path.join(__datapath__, __addonid__ + '.log')
__LS__ = __addon__.getLocalizedString

# Globals needed for writeLog()
LASTMSG = ''
MSGCOUNT = 0
#

#path and icons
__path__ = __addon__.getAddonInfo('path')

__IconStop__ = xbmc.translatePath(os.path.join( __path__,'resources', 'media', 'stop.png'))
__IconError__ = xbmc.translatePath(os.path.join( __path__,'resources', 'media', 'error.png'))
__IconStream__ = xbmc.translatePath(os.path.join( __path__,'resources', 'media', 'stream.png'))

#Load all settings
__streams_folder__ = __addon__.getSetting('streams_folder')
__source_folder__ = __addon__.getSetting('source_folder')
__thumbs_folder__ = __addon__.getSetting('thumbs_folder')
__use_thumb__ = True if __addon__.getSetting('use_thumb').upper() == 'TRUE' else False
__generate_nfo__ = True if __addon__.getSetting('generate_nfo').upper() == 'TRUE' else False

DLG_TYPE_FOLDER = 0
DLG_TYPE_FILE = 1

PB_BUSY = 0
PB_CANCELED = 1
PB_TIMEOUT = 2

STREAM_URL=-2
STREAM_FILE=-3

__favorites_filename__ = 'favourites.xml'

class Stream(object):
    Name = None
    Thumb = None
    URL = None

####################################### GLOBAL FUNCTIONS #####################################

def notifyOSD(header, message, icon):
    xbmc.executebuiltin('XBMC.Notification(%s,%s,5000,%s)' % (header.encode('utf-8'), message.encode('utf-8'), icon))

def writeDebug(message, level=xbmc.LOGNOTICE):
    if __scriptdebug__ == True:
        writeLog("[Debug] %s" % message, level)

def writeLog(message, level=xbmc.LOGNOTICE):
    global LASTMSG, MSGCOUNT
    if LASTMSG == message:
        MSGCOUNT = MSGCOUNT + 1
        return
    else:
        LASTMSG = message
        MSGCOUNT = 0
        xbmc.log('%s: %s' % (__addonid__, message.encode('utf-8')), level)  

def GUI_Browse(title, defaultPath=None, dialogType=DLG_TYPE_FILE, mask=''):
        """

        @param title:
        @param dialogType: Integer - 0 : ShowAndGetDirectory
                                     1 : ShowAndGetFile
                                     2 : ShowAndGetImage
                                     3 : ShowAndGetWriteableDirectory

        shares         : string or unicode - from sources.xml. (i.e. 'myprograms')
        mask           : [opt] string or unicode - '|' separated file mask. (i.e. '.jpg|.png')
        useThumbs      : [opt] boolean - if True autoswitch to Thumb view if files exist.
        treatAsFolder  : [opt] boolean - if True playlists and archives act as folders.
        default        : [opt] string - default path or file.

        enableMultiple : [opt] boolean - if True multiple file selection is enabled.

        """
        if defaultPath is None:
            defaultPath = xbmc.translatePath("special://home")

        browseDialog = xbmcgui.Dialog()
        destFolder = browseDialog.browse(dialogType, title, 'programs', mask, True, True, defaultPath)
        if destFolder == defaultPath:
            destFolder = ""
        return destFolder

def GUI_KeyBoard(title="Type"):
    keyDialog = xbmcgui.Dialog()
    return keyDialog.input(title)

def GUI_SelectSourceFile(defaultPath=None):
	return GUI_Browse(__LS__(50000), defaultPath, dialogType=DLG_TYPE_FILE)

def GUI_SelectThumbFile(defaultPath=None):
    return GUI_Browse(__LS__(50010), defaultPath, dialogType=DLG_TYPE_FILE, mask='.jpg|.png')

def GUI_SelectDestinationFolder(defaultPath=None):
    return GUI_Browse(__LS__(50012), defaultPath, dialogType=DLG_TYPE_FOLDER, mask='.jpg|.png')

def GUI_LookupStream(ListContent=[]):
    nstreams=len(ListContent)
    dest = []
    
    for content in ListContent:
        dest.append("%s %s"%(__LS__(50200),content.Name))

    dest.append(__LS__(50201))
    dest.append(__LS__(50202))

    dialog = xbmcgui.Dialog()
    selected = dialog.select(__LS__(50001), dest)
    if (selected==nstreams):
        selected=STREAM_URL
    elif (selected==nstreams+1):
        selected=STREAM_FILE
    # TBD later ....        
    writeDebug('Selected Stream: %d' % (selected))

    return selected


####################################### STREAMGENERATOR FUNCTIONS #####################################

def getFavourites(filename, limit=10000):
    import xbmcgui

    xml  = '<favourites></favourites>'
    if xbmcvfs.exists(filename):
        f = file(filename, 'r')
        xml = f.read()
        f.close()

    items = []

    faves = re.compile('<favourite(.+?)</favourite>').findall(xml)

    for fave in faves:
        fave = fave.replace('&quot;', '&_quot_;')
        fave = fave.replace('\'', '"')
        fave = fave.replace('&amp;',  '&')
        fave = fave.replace('&quot;', '"')
        fave = fave.replace('&apos;', '\'')
        fave = fave.replace('&gt;',   '>')
        fave = fave.replace('&lt;',   '<')

        fave = fave.replace('name=""', '')
        try:    name = re.compile('name="(.+?)"').findall(fave)[0]
        except: name = ''

        try:    thumb = re.compile('thumb="(.+?)"').findall(fave)[0]
        except: thumb = ''

        try:    cmd   = fave.split('>', 1)[-1]
        except: cmd = ''

        #name  = utils.Clean(name.replace( '&_quot_;', '"'))
        name  = name.replace( '&_quot_;', '"')
        thumb = thumb.replace('&_quot_;', '"')
        cmd   = cmd.replace(  '&_quot_;', '"')

        if cmd.startswith('PlayMedia'):
            url=cmd.replace('PlayMedia','')
            url=url[2:-2]
            strm = Stream()
            strm.Name=name
            strm.Thumb=thumb
            strm.URL=ValidateURL(url)
            writeDebug(strm.Name)
            writeDebug(strm.Thumb)
            writeDebug(strm.URL)          
            items.append(strm)
            if len(items) > limit:
                return items

    return items

def ValidName(name):
    badchars= re.compile(r'[^A-Za-z0-9_.]+|^\.|\.$|^ | $|^$')
    return(badchars.sub('', name))

def getURLFromFile(filename):
    url=None
    try:
        if xbmcvfs.exists(filename):
            f = file(filename, 'r')
            cont = True
            while cont:
                rl = f.readline().strip()
                url = ValidateURL(rl)
                if (rl[:1]!='#') and (url != None):
                    cont = False
            f.close()
    except:
        url=None
    return url

def ValidateURL(url):
    myurl=url
    result=urlparse.urlparse(url)
    if (not result.scheme): # if not scheme, set http:// in front ....
        url="http://%s"%url
        result=urlparse.urlparse(url)
    if (not result.scheme or not result.netloc): 
        writeLog("invalid Stream URL: " + myurl)
        url=None
    writeDebug(result.scheme)
    writeDebug(result.netloc)

    return url

def getFromSelection(Selection=-1,ListContent=[]):
    if Selection==STREAM_URL:
        strm = Stream()
        strm.URL=ValidateURL(GUI_KeyBoard(__LS__(50002)))
    elif Selection==STREAM_FILE:
        strm = Stream()
        strm.Name=GUI_SelectSourceFile(__source_folder__)
        strm.URL=getURLFromFile(strm.Name)
    elif Selection!=-1:
        strm=ListContent[Selection]
    else:
        strm=None

    return strm

def CheckName(Stream):
    if (Stream.Name == None):
        Stream.Name = GUI_KeyBoard(__LS__(50003))
        if Stream.Name == "": Stream.Name = None
    if (Stream.Name == None):
        notifyOSD(__LS__(50004),__LS__(50005),__IconStream__)
        Stream.Name = Stream.URL

    return Stream

def CheckThumb(Stream):
    if __use_thumb__:
        if (Stream.Thumb == None):
            Stream.Thumb = GUI_SelectThumbFile(__thumbs_folder__)
            if Stream.Thumb == "": Stream.Thumb = None
        if (Stream.Thumb == None):
            notifyOSD(__LS__(50008),__LS__(50009),__IconStream__)

    return Stream

def GetDestination():
    df=GUI_SelectDestinationFolder(__streams_folder__)
    if (df==None or df==""):
        df=__streams_folder__
    return df

def CopyThumb(Stream,Dest):
    if __use_thumb__:
        base=os.path.basename(Stream.Thumb)
        Thumbext=os.path.splitext(base)[1]
        Destination=Dest+ValidName(Stream.Name)+Thumbext
        shutil.copy(Stream.Thumb, Destination)
        writeLog("Thumb copied")
        writeDebug(Destination)
        Stream.Thumb=Destination
    return Stream

def GenerateStrm(Stream,Dest):
    filename=Dest+ValidName(Stream.Name)+".strm"
    f = open(filename, 'w')
    f.write(Stream.URL)
    f.close()
    writeLog("Stream generated")
    writeDebug(filename)
    return

def GenerateNFO(Stream,Dest):
    if __generate_nfo__:
        filename=Dest+ValidName(Stream.Name)+".nfo"
        f = open(filename, 'w')
        f.write("<movie>\n")
        f.write("    <title>%s</title>\n"%Stream.Name)
        if __use_thumb__:
            f.write("    <thumb>%s</thumb>\n"%Stream.Thumb)
        f.write("</movie>\n\n")
        f.write("<musicvideo>\n")
        f.write("    <title>%s</title>\n"%Stream.Name)
        if __use_thumb__:
            f.write("    <thumb>%s</thumb>\n"%Stream.Thumb)
        f.write("</musicvideo>")
        f.close()
        writeLog("NFO generated")
        writeDebug(filename)
    return

####################################### START MAIN SERVICE #####################################

writeLog("StreamGenerator Started ...")

favsfile = xbmc.translatePath(os.path.join('special://profile', __favorites_filename__))

ListContent=getFavourites(favsfile)
Selection=GUI_LookupStream(ListContent)
Stream=getFromSelection(Selection,ListContent)
if Stream == None:
    notifyOSD(__LS__(50006),__LS__(50011),__IconError__)
    exit()
if Stream.URL == None:
    notifyOSD(__LS__(50006),__LS__(50007),__IconError__)
    exit()
Stream=CheckName(Stream)
Stream=CheckThumb(Stream)
Dest=GetDestination()
Stream=CopyThumb(Stream,Dest)
GenerateStrm(Stream,Dest)
GenerateNFO(Stream,Dest)
notifyOSD(__LS__(50013),__LS__(50014),__IconStream__)

writeLog("StreamGenerator Ready ...")

