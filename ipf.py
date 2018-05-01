#!/bin/env python

import argparse
import os
import struct
import sys
import zlib

IPF_MAGIC = 101010256
FILENAME_ENCODING = 'utf-8' # not sure which to use

class IpfMeta:
    @staticmethod
    def read(fin):
        self = IpfMeta()

        fpos = fin.tell()
        (
            self.fileCount,
            self.filetableOffset,
            footerOffset,
            magic,
        ) = struct.unpack('<HI2xII8x', fin.read(24))

        if magic != IPF_MAGIC:
            raise ValueError("wrong magic: {0:x} ({0:d})".format(magic))

        if footerOffset != fpos:
            sys.stderr.write('warning: wrong footerOffset {}'.format(footerOffset))

        return self

    def write(self, fout):
        footerOffset = fout.tell()
        fout.write(struct.pack(
            '<HIHIIII',
            self.fileCount,
            self.filetableOffset,
            0, # looks like unused
            footerOffset,
            IPF_MAGIC,
            0, # baseRevision
            0, # revision
        ))

class IpfFile:
    def __init__(self, archivename = '', filename = ''):
        self.archivename = archivename
        self.filename    = filename

    @staticmethod
    def read(fin):
        self = IpfFile()

        (
            self.filenameLength,
            self.crc,
            self.compressedLength,
            self.decompressedLength,
            self.dataOffset,
            self.archivenameLength,
        ) = struct.unpack('<HIIIIH', fin.read(20))

        self.archivename = fin.read(self.archivenameLength).decode(FILENAME_ENCODING)
        self.filename    = fin.read(self.filenameLength).decode(FILENAME_ENCODING)

        return self

    def write(self, fout):
        archivename = self.archivename.encode(FILENAME_ENCODING)
        filename    = self.filename.encode(FILENAME_ENCODING)

        fout.write(struct.pack(
            '<HIIIIH',
            len(filename),
            self.crc,
            self.compressedLength,
            self.decompressedLength,
            self.dataOffset,
            len(archivename)
        ))

        fout.write(archivename)
        fout.write(filename)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("archivename")
    parser.add_argument("files", nargs='*')
    args = parser.parse_args()

    if args.action == 'd':
        fin = open(args.archivename, 'rb')

        fin.seek(-24, 2)
        meta = IpfMeta.read(fin)

        fileTable = []

        fin.seek(meta.filetableOffset, 0)
        for i in range(meta.fileCount):
            fileInfo = IpfFile.read(fin)
            fileTable.append(fileInfo)

        for fileInfo in fileTable:
            fin.seek(fileInfo.dataOffset, 0)
            stream = zlib.decompressobj(-15)
            toread = fileInfo.compressedLength

            os.makedirs(os.path.dirname(fileInfo.filename), exist_ok=True)
            fout = open(fileInfo.filename, 'wb')
            crc = 0
            decompressedLength = 0

            while True:
                if toread > 0:
                    chunk = fin.read(4096 if toread > 4096 else toread)
                    toread -= len(chunk)
                    chunk = stream.decompress(chunk)
                else:
                    chunk = stream.flush

                decompressedLength += len(chunk)
                crc = zlib.crc32(chunk, crc)
                fout.write(chunk)

                if toread == 0: break

            fout.close()

            if decompressedLength != fileInfo.decompressedLength:
                sys.stderr.write('warning: wrong decompressed size for {0}\n'.format(fileInfo.filename))
            if crc != fileInfo.crc:
                sys.stderr.write('warning: wrong crc for {0}\n'.format(fileInfo.filename))

    elif args.action == 'c':
        if len(args.files) == 0:
            sys.stderr.write('empty file list\n')
            sys.exit(1)

        fout = open(args.archivename, 'wb')

        fileTable = []

        for filename in args.files:
            fin = open(filename, 'rb')
            stream = zlib.compressobj(-1, zlib.DEFLATED, -15)
            fileInfo = IpfFile(args.archivename, filename)
            fileInfo.compressedLength = 0
            fileInfo.crc = 0
            fileInfo.dataOffset = fout.tell()

            while True:
                chunk = fin.read(4096)

                if chunk:
                    fileInfo.crc = zlib.crc32(chunk, fileInfo.crc)
                    compressed = stream.compress(chunk)
                else:
                    compressed = stream.flush()

                fout.write(compressed)
                fileInfo.compressedLength += len(compressed)

                if not chunk: break

            fileInfo.decompressedLength = fin.tell()
            fin.close()
            fileTable.append(fileInfo)

        meta = IpfMeta()
        meta.fileCount = len(fileTable)
        meta.filetableOffset = fout.tell()

        for fileInfo in fileTable:
            fileInfo.write(fout)

        meta.write(fout)
        fout.close()

    else:
        sys.stderr.write('unsupported action {0}\n'.format(action))
        sys.exit(1)
