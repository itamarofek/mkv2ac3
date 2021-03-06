#!/usr/bin/env python


import argparse
import os
import shlex
import subprocess
import time
import glob
import re
import tempfile
import sys
import ConfigParser
#import shutil
import hashlib
import textwrap
import errno
import logging
import colorlog
from distutils import spawn

version = ".1"

supported_formats = ['AAC', 'E-AC-3', 'DTS' ]
mkvtools = {'mkvinfo': None, 'mkvmerge': None, 'mkvextract': None}
mkvmerge_bin = None

ffmpegtools = {'ffmpeg': None}

def static_var(varname, value):
    def decorate(func):
        setattr(func, varname, value)
        return func
    return decorate

def setup_logger(level=0):
    mapping = {0: logging.CRITICAL, 1: logging.ERROR,
               2: logging.WARNING, 3: logging.INFO,
               4: logging.DEBUG}
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s %(log_color)s%(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = colorlog.getLogger(__file__)
    logger.addHandler(handler)
    logger.setLevel(mapping[level+1])


def get_logger():
    return colorlog.getLogger(__file__)

def set_tools_path(tools, path=None):
    for key in tools:
        tools[key] = spawn.find_executable(
                os.path.join(path,key) if path else key)
        if not tools[key]:
            logger.error("clould not find %s executable" % key)
            raise NameError('Key can not be found')


currentFuncName = lambda n=0: sys._getframe(n + 1).f_code.co_name

def call_prog(prog, args_list):
    cmd = [prog] + args_list
    get_logger().debug("call: %(cmd)s",{'cmd':cmd})
    output = subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()
    if len(output) == 0 or output[0] is None:
        output = ""
    else:
        output = output[0].splitlines()
    return output

def mkvinfo(media,*arguments):
    arg_list = ["--ui-language", "en_US", media]
    if arguments:
        arg_list = list(arguments) + arg_list
    return call_prog(mkvtools[currentFuncName()],arg_list)


def mkvmerge(media, *arguments):
    arg_list = ['-i', media] + [item for item in arguments]
    return  call_prog(mkvtools[currentFuncName()], arg_list)


def ffmpeg(media, *args):
    arg_list = ['-hide_banner', '-i', media] + [item for item in arguments]
    return  call_prog(ffmpegtools[currentFuncName()], arg_list)

def mkvextract(media, *args):
    arg_list = list(args)
    arg_list = [arg_list[0], media] + arg_list[1:]
    return  call_prog(mkvtools[currentFuncName()], arg_list)




def load_config():
    configFilename = os.path.join(os.path.dirname(sys.argv[0]), "mkv2ac3.conf")

    if os.path.isfile(configFilename):
        config = ConfigParser.SafeConfigParser()
        config.read(configFilename)
        defaults = dict(config.items("mkvd2ac3"))
        verbose_val = int (defaults.get('verbose',0))
        defaults['verbose'] = verbose_val
        return defaults
    return None

def set_prog_options(parser):
    parser.add_argument('fileordir',
            metavar='FileOrDirectory',
            nargs='+',
            help='a file or directory (wildcards may be used)')

    parser.add_argument(
            "-c", "--custom",
            metavar="TITLE",
            help="Custom AC3 track title")


#    parser.add_argument(
#            "-i", "--input",
#            metavar="INPUT",
#            help="input media file")

    parser.add_argument(
            "-d", "--default",
            help="Mark AC3 track as default", action="store_true")

    parser.add_argument(
            "--destdir", metavar="DIRECTORY",
            help="Destination Directory")

    parser.add_argument(
            "-e", "--external", action="store_true",
            help="Leave AC3 track out of file."
            " Does not modify the original matroska file."
            " This overrides '-n' and '-d' arguments")

    parser.add_argument(
            "-f", "--force", action="store_true",
            help="Force processing when AC3 track is detected")

    parser.add_argument(
            "--ffmpegpath", metavar="DIRECTORY",
            help="Path of ffmpeg")

    parser.add_argument(
            "-k", "--keeporig", help="Keep original track",
            action="store_true")

    parser.add_argument(
            "--mp4", help="create output in mp4 format", action="store_true")

    parser.add_argument(
            "--mkvtoolnixpath", metavar="DIRECTORY",
            help="Path of mkvextract, mkvinfo and mkvmerge")

    parser.add_argument(
            "-n", "--dont-retain", help="Do not retain the original track",
            action="store_true")

    parser.add_argument(
            "--new",
            help="Do not copy over original. Create new adjacent file",
            action="store_true")

    parser.add_argument(
            "--no-subtitles",
            help="Remove subtitles",
            action="store_true")

    parser.add_argument(
            "-o", "--overwrite",
            help="Overwrite file if already there."
            " This only applies if destdir or sabdestdir is set",
            action="store_true")

    parser.add_argument("-p", "--position",
            choices=['initial', 'last', 'afterdts'],
            default="last",
            help="Set position of AC3 track."
            " 'initial' = First track in file,"
            " 'last' = Last track in file,"
            " 'afterdts' = After the DTS track [default: last]")

    parser.add_argument(
            "-r", "--recursive",
            help="Recursively descend into directories", action="store_true")

    parser.add_argument(
            "-s", "--compress", metavar="MODE",
            help="Apply header compression to streams "
            " (See mkvmerge's --compression)",
            default='none')

    parser.add_argument(
            "--stereo",
            help="Make ac3 track stereo instead of 6 channel",
            action="store_true")

    parser.add_argument(
            "-t", "--track",
            metavar="TRACKID",
            help="Specify alternate track."
            " If it is not a supported audio track,"
            " it will default to the first supported audio track found")

    parser.add_argument(
            "--all-tracks", help="Convert all supported tracks",
            action="store_true")

    parser.add_argument("-w", "--wd",
            metavar="WORK_DIR",
            help="Specify alternate temporary working directory")

    parser.add_argument("-v", "--verbose",
            help="Turn on verbose output."
            " Use more v's for more verbosity."
            " -v will output what it is doing."
            " -vv will also output the command that it is running."
            " -vvv will also output the command output",
            action="count",
            default=0)

    parser.add_argument(
            "--test",
            help="Print commands only, execute nothing",
            action="store_true")

    parser.add_argument(
            "--debug",
            help="Print commands and pause before executing each",
            action="store_true")

    args = parser.parse_args()

    return args

def main():
    parser = argparse.ArgumentParser(
            description='convert mkv video files audio %s to ac3' %
            supported_formats)


    # set config file arguments
    configFilename = os.path.join(os.path.dirname(sys.argv[0]),
                                  "mkv2ac3.conf")

    cfg = load_config()

    if cfg:
        parser.set_defaults(**cfg)

    args = set_prog_options(parser)

    global mkvtools
    global ffmpegtools

    set_tools_path(mkvtools, args.mkvtoolnixpath)
    set_tools_path(ffmpegtools, args.ffmpegpath)

    if args.test or args.debug:
        args.verbose = max(args.verbose, 2)
    setup_logger(args.verbose)

    get_logger().info(" media is %(media)s", {'media': args.fileordir})

    convert=AudioConvertor(args.fileordir[0], ".")

    convert.process_media()


def silentremove(filename):
    try:
        os.remove(filename)
    except OSError, e:
        if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
            raise # re-raise exception if a different error occured


def elapsedstr(starttime):
    elapsed = (time.time() - starttime)
    minutes = int(elapsed / 60)
    seconds = int(elapsed) % 60
    return ("%s min:%s sec" %(minutes, seconds))

def getduration(time):
    (hms, ms) = time.split('.')
    (h, m, s) = hms.split(':')
    totalms = (int(ms) + (int(s) * 100) +
               (int(m) * 100 * 60) + (int(h) * 100 * 60 * 60))
    return totalms

class MediaInfo(object):
    def __init__(self,media):
        self.source = media
        self.info = dict()

    def analyse(self):
        output = mkvmerge(self.source)
        for line in output:
            entry = re.split('Track ID ([0-9]+)\: (.*) \((.*)/(.*)\)', line)
            if not entry or len(entry) != 6:
                continue
            self.info[entry[1]] = {'type' :entry[2],
                                   'codec_info': entry[3],
                                   'codec': entry[4]}

            get_logger().debug(
                         "parsed elementry stream %(id)s:"
                         "%(type)s, %(codec)s, %(codec_info)s",
                         {'id': entry[1], 'type': entry[2],
                          'codec': entry[4], 'codec_info': entry[3] })
        return self.info

    def get_source(self):
        return self.source

    def get_info(self):
        return self.info


class AudioConvertor(object):

    def __init__(self, media, work_dir=".", target=None, downmixing=False):
        self.media = MediaInfo(media)
        self.src_dir = None
        self.src_file = None
        self.asset_desc = None
        self.target = target
        self.work_dir = work_dir
        self.stereo = downmixing
        self.es =  None
        self.tmpaudio = None
        self.src_dir, self.src_file = os.path.split(media)
        self.asset_desc = os.path.splitext(self.src_file)[0]

    def process_audio(self):
        info = mkvinfo(self.media.source)
        trackinfo = {}
        line_count = 0
        record_found = False
        for line in info:
            if "Track number: %s" % (int(self.es) + 1) in line:
                record_found = True
                continue
            if not record_found:
                continue
            if 'A track' in line:
                break
            record = re.split('\|[\ ]+\+ (.*)\:(.*)', line)
            if len(record) > 3:
                trackinfo[record[1]] = record[2].strip()


        get_logger().debug("track: %(id)s, %(info)s",
                             dict(id=self.es,info=trackinfo))
        return trackinfo


    def process_media(self):
        info = self.media.analyse()
        for k,v in info.iteritems():
            if 'audio' in v['type'] and v['codec'] in supported_formats:
                self.es = k
                get_logger().info("found stream %(id)s, %(codec)s",
                                  {'id': k, 'codec': v['codec'] })
                break
        stream_info = self.process_audio()
        self.extract_stream(self.es)
        extracted_info = self.process_extracted()
        self.extract_timecode(self.es)
        channels = (2 if self.downmixing else 6)
        if not stream_info[channels] > 5:
            channels = 2
        bandwidth = 640
        if extracted_info['ab'] < 640:
            bandwidth = extracted_info['ab']
        self.convert_audio(channels, bandwidth)


    def process_extracted(self):
        output = ffmpeg(self.tmpaudio)
        result = dict()
        for line in output:
            if 'Audio:' in line:
                entry = re.split(r'\#|\,|\:|Hz|kb\/s|\(side\)', line)
                if not len(entry) == 12:
                    break
                result['codec'] = entry[4].strip()
                result['Hz'] = entry[5].strip()
                result['channel'] = entry[7].strip()
                result['ab'] = entry[10].strip()
        return result

    def extract_stream(self, stream_id):
        codec = self.media.get_info()[stream_id]['codec']
        tempfile = "%s_track:%s.%s" %(self.asset_desc, stream_id, codec)
        self.tmpaudio = os.path.join(self.work_dir,tempfile)
        result = mkvextract(self.media.source, "tracks",
                            stream_id + ':' + self.tmpaudio)

    def extract_timecode(self, stream_id):
        tempfile = "%s_track:%s.%s" %(self.asset_desc, stream_id, 'tc')
        self.tmptc = os.path.join(self.work_dir,tempfile)

        result = mkvextract(self.media.source, "timecodes_v2",
                            stream_id + ':' + self.tmptc)


    def remux_media(self):
        pass

    def convert_audio(channels, bandwidth, codec='ac3'):
        pass

    def mk_processing_dir(self):
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)
        else:
            tempdir = tempfile.mkdtemp()
            tempdir = os.path.join(tempdir, "mkv2ac3")


def runcommand(title, cmdlist):
    if args.debug:
        raw_input("Press Enter to continue...")
    cmdstarttime = time.time()
    if args.verbose >= 1:
        sys.stdout.write(title)
        if args.verbose >= 2:
            cmdstr = ''
            for e in cmdlist:
                cmdstr += e + ' '
            print
            print "    Running command:"
            print textwrap.fill(cmdstrrstrip(), initial_indent='      ', subsequent_indent='      ')
    if not args.test:
        if args.verbose >= 3:
            subprocess.call(cmdlist)
        elif args.verbose >= 1:
            if "ffmpeg" in cmdlist[0]:
                proc = subprocess.Popen(cmdlist, stderr=subprocess.PIPE)
                line = ''
                duration_regex = re.compile("  Duration: (\d+:\d\d:\d\d\.\d\d),")
                progress_regex = re.compile("size= +\d+.*time=(\d+:\d\d:\d\d\.\d\d) bitrate=")
                duration = False
                while True:
                    if not duration:
                        durationline = proc.stderr.readline()
                        match = duration_regex.match(durationline)
                        if match:
                            duration = getduration(match.group(1))
                    else:
                        out = proc.stderr.read(1)
                        if out == '' and proc.poll() != None:
                            break
                        if out != '\r':
                            line += out
                        else:
                            if 'size= ' in line:
                                match = progress_regex.search(line)
                                if match:
                                    percentage = int(float(getduration(match.group(1)) / float(duration)) * 100)
                                    if percentage > 100:
                                        percentage = 100
                                    sys.stdout.write("\r" + title + str(percentage) + '%')
                            line = ''
                        sys.stdout.flush()
                print "\r" + title + elapsedstr(cmdstarttime)
            else:
                proc = subprocess.Popen(cmdlist, stdout=subprocess.PIPE)
                line = ''
                progress_regex = re.compile("Progress: (\d+%)")
                while True:
                    out = proc.stdout.read(1)
                    if out == '' and proc.poll() != None:
                        break
                    if out != '\r':
                        line += out
                    else:
                        if 'Progress: ' in line:
                            match = progress_regex.search(line)
                            if match:
                                percentage = match.group(1)
                                sys.stdout.write("\r" + title + percentage)
                        line = ''
                    sys.stdout.flush()
                print "\r" + title + elapsedstr(cmdstarttime)
        else:
            subprocess.call(cmdlist, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def check_md5tree(orig, dest):
    rt = True
    orig = os.path.abspath(orig)
    dest = os.path.abspath(dest)
    for ofile in os.listdir(orig):
        if rt == True:
            if os.path.isdir(os.path.join(orig, ofile)):
                doprint("dir: " + os.path.join(orig, ofile) + "\n", 3)
                odir = os.path.join(orig, ofile)
                ddir = os.path.join(dest, ofile)
                rt = check_md5tree(odir, ddir)
            else:
                doprint("file: " + os.path.join(orig, ofile) + "\n", 3)
                if getmd5(os.path.join(orig, ofile)) != getmd5(os.path.join(dest, ofile)):
                    rt = False
    return rt



if __name__== "__main__":
    main()

