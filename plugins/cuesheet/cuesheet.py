# -*- coding: utf-8 -*-

PLUGIN_NAME = u"Generate Cuesheet"
PLUGIN_AUTHOR = u"Lukáš Lalinský"
PLUGIN_DESCRIPTION = "Generate cuesheet (.cue file) from an album."
PLUGIN_VERSION = "0.2"
PLUGIN_API_VERSIONS = ["0.10", "0.15"]


import os.path
import re
from PyQt4 import QtCore, QtGui
from picard.util import find_existing_path, encode_filename
from picard.ui.itemviews import BaseAction, register_album_action


_whitespace_re = re.compile('\s', re.UNICODE)
_split_re = re.compile('\s*("[^"]*"|[^ ]+)\s*', re.UNICODE)


def msfToMs(msf):
    msf = msf.split(":")
    return ((int(msf[0]) * 60 + int(msf[1])) * 75 + int(msf[2])) * 1000 / 75


class CuesheetTrack(list):

    def __init__(self, cuesheet, index):
        list.__init__(self)
        self.cuesheet = cuesheet
        self.index = index

    def set(self, *args):
        self.append(args)

    def find(self, prefix):
        return [i for i in self if tuple(i[:len(prefix)]) == tuple(prefix)]

    def getTrackNumber(self):
        return self.index

    def getLength(self):
        try:
            nextTrack = self.cuesheet.tracks[self.index + 1]
            index0 = self.find((u"INDEX", u"01"))
            index1 = nextTrack.find((u"INDEX", u"01"))
            return msfToMs(index1[0][2]) - msfToMs(index0[0][2])
        except IndexError:
            return 0

    def getField(self, prefix):
        try:
            return self.find(prefix)[0][len(prefix)]
        except IndexError:
            return u""

    def getArtist(self):
        return self.getField((u"PERFORMER",))

    def getTitle(self):
        return self.getField((u"TITLE",))

    def setArtist(self, artist):
        found = False
        for item in self:
            if item[0] == u"PERFORMER":
                if not found:
                    item[1] = artist
                    found = True
                else:
                    del item
        if not found:
            self.append((u"PERFORMER", artist))

    artist = property(getArtist, setArtist)


class Cuesheet(object):

    def __init__(self, filename, idx="1"):
        self.filename = filename
        if idx != "1":
            self.filename = filename[:filename.rfind('.')] + '-%s.cue' % idx
        self.tracks = []

    def read(self):
        with open(encode_filename(self.filename)) as f:
            self.parse(f.readlines())

    def unquote(self, string):
        if string.startswith('"'):
            if string.endswith('"'):
                return string[1:-1]
            else:
                return string[1:]
        return string

    def quote(self, string):
        if _whitespace_re.search(string):
            return '"' + string.replace('"', '\'') + '"'
        return string

    def parse(self, lines):
        track = CuesheetTrack(self, 0)
        self.tracks = [track]
        isUnicode = False
        for line in lines:
            # remove BOM
            if line.startswith('\xfe\xff'):
                isUnicode = True
                line = line[1:]
            # decode to unicode string
            line = line.strip()
            if isUnicode:
                line = line.decode('UTF-8', 'replace')
            else:
                line = line.decode('ISO-8859-1', 'replace')
            # parse the line
            split = [self.unquote(s) for s in _split_re.findall(line)]
            keyword = split[0].upper()
            if keyword == 'TRACK':
                trackNum = int(split[1])
                track = CuesheetTrack(self, trackNum)
                self.tracks.append(track)
            track.append(split)

    def write(self):
        lines = []
        for track in self.tracks:
            num = track.index
            for line in track:
                indent = 0
                if num > 0:
                    if line[0] == "TRACK":
                        indent = 2
                    elif line[0] != "FILE":
                        indent = 4
                line2 = u" ".join([self.quote(s) for s in line])
                lines.append(" " * indent + line2.encode("UTF-8") + "\n")
        with open(encode_filename(self.filename), "wt") as f:
            f.writelines(lines)


class GenerateCuesheet(BaseAction):
    NAME = "Generate &Cuesheet..."

    def callback(self, objs):
        album = objs[0]
        current_directory = self.config.persist["current_directory"] or QtCore.QDir.homePath()
        current_directory = find_existing_path(unicode(current_directory))
        filename, selected_format = QtGui.QFileDialog.getSaveFileNameAndFilter(
            None, "", current_directory, "Cuesheet (*.cue)")
        if filename:
            filename = unicode(filename)

            currentDiscNumber = None
            idx = 0
            cuesheet = None
            for track in album.tracks:
                if not currentDiscNumber or track.metadata["discnumber"] != currentDiscNumber:
                    if cuesheet:
                        cuesheet.write()
                    currentDiscNumber = track.metadata["discnumber"]
                    cuesheet = Cuesheet(filename, currentDiscNumber)
                    cuesheet.tracks = [CuesheetTrack(cuesheet, 0)] + [CuesheetTrack(cuesheet, i + 1) for i, x in enumerate(album.tracks) if x.metadata["discnumber"] == currentDiscNumber]
                    t = cuesheet.tracks[0]
                    t.set("PERFORMER", album.metadata["albumartist"])
                    t.set("TITLE", album.metadata["album"])
                    t.set("REM", "MUSICBRAINZ_ALBUM_ID", album.metadata["musicbrainz_albumid"])
                    t.set("REM", "MUSICBRAINZ_ALBUM_ARTIST_ID", album.metadata["musicbrainz_albumartistid"])
                    if "date" in album.metadata:
                        t.set("REM", "DATE", album.metadata["date"])
                    index = 0.0
                    idx = 0

                mm = index / 60.0
                ss = (mm - int(mm)) * 60.0
                ff = (ss - int(ss)) * 75.0
                index += track.metadata.length / 1000.0
                t = cuesheet.tracks[idx + 1]
                t.set("TRACK", "%02d" % (idx + 1), "AUDIO")
                t.set("PERFORMER", track.metadata["artist"])
                t.set("TITLE", track.metadata["title"])
                t.set("REM", "MUSICBRAINZ_TRACK_ID", track.metadata["musicbrainz_trackid"])
                t.set("REM", "MUSICBRAINZ_ARTIST_ID", track.metadata["musicbrainz_artistid"])
                t.set("INDEX", "01", "%02d:%02d:%02d" % (mm, ss, ff))
                for file in track.linked_files:
                    audio_filename = file.filename
                    if os.path.dirname(filename) == os.path.dirname(audio_filename):
                        audio_filename = os.path.basename(audio_filename)
                    cuesheet.tracks[idx + 1].set("FILE", audio_filename, "MP3")
                idx += 1

            cuesheet.write()


action = GenerateCuesheet()
register_album_action(action)
