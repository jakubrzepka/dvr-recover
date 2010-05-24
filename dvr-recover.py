#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Stefan Haller <haliner@googlemail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


'''
dvr-recover - extract MPEG2 files of digital video recorder hdd
===============================================================

Version: 0.5


Copyright (C) 2010 Stefan Haller <haliner@googlemail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.


Sqlite database file
--------------------

The script will create a sqlite3 database in the current directory with the
name "dvr-recover.sqlite". All settings and data will be stored in this
database.


Settings file
-------------

Before you can use dvr-recover you will have to change the default settings.
You can do this by simply calling the script with the parameter "setup"
followed by the setting to change and the new value. To change the value of
the blocksize setting call:

    python dvr-recover.py setup blocksize 2048

Here is a full listing of all available settings:

   The square brackets in this listing are representing the type of the value.
   Replace them with an integer for "[integer]". Don't copy this square
   brackets, so write

    blocksize 2048

  instead of

    blocksize [2048]


  input clear            This option sets the path of the hard disk drive
  input add [filename]   file used as input. You can either use a copy of the
  input del [filename]   block device (created with something like dd or so) or
                         the block device directly (required root privileges).
                         The file must be readable. It's possible to specify
                         multiple hdd-files by calling the add parameter
                         multiply times. The script will threat the single files
                         as one big file. That way you can split the hdd into
                         smaller pieces.
                         
                         parameter clear:   clear list of input file
                         parameter add:     add one file to list of input files
                         parameter del:     delete one file from list of input
                                            files

  exportdir [string]     Defines where the output should be written to. Must
                         match an existing path. Both relative and absolute
                         paths are accepted. Current directory is "./".

  blocksize [integer]    The blocksize of the filesystem can be configured
                         with this option. Set this to a value in bytes.
                         The default value is 2048 bytes. Probably this value
                         should work, but if not, you're free to tune it.

  minchunksize [integer] If the script finds chunks smaller than this size
                         (value must be given in blocks!), it will ignore them
                         silently. If this value is too small, the script
                         will find chunks that were deleted or can't be used.
                         Otherwise, if the value is too big, valuable chunks
                         will be ignored. The default value is 25600 blocks
                         (50 MiB by blocksize of 2048 bytes).

  maxcreategap [integer] The script will split the stream into two chunks if
                         it finds two frames where the timecode differs more
                         than this value. MPEG uses a clock of 90 kHz.
                         So the default value of 90,000 ticks equals one second.

  maxsortgap [integer]   See maxcreategap. This value is used to concatenate
                         two chunks if the difference of the timecode is smaller
                         than this value. The default value of 90,000 ticks
                         equals one second.


Input hdd file
--------------

You can create either a copy of the hdd or use the hdd directly as input.

Linux:
  If you want to copy the hdd (assuming the hdd is /dev/sdb) then you can use
  this dd command: (setting the blocksize to 10MB should increase performance.)

    dd if=/dev/sdb if=hddfile bs=10MB

  If you want to use the hdd directly as input, use this as value for hdd-file:
  (Assuming that the hdd is /dev/sdb.)

    hdd-file=/dev/sdb

Windows:
  Use a tool to create a copy of the hdd. Direct access to Windows device
  files (\\.\PhysicalDrive0, ...) is not supported at the moment.


Steps:
------

Step 1: Export information of chunks
  The hdd file will be analyzed and all necessary information are collected.
  This step may take quite a long time, be patient! This step is only necessary
  once. All other steps will use the stored chunk info to save time.
  (The script tries to find mpeg headers and extract the timecode. Depending on
  the timecode it's possible to split the stream into separate chunks.)

  Parameter: create

Step 2: Analyze and sort chunks
  This step will analyze the stored chunk info and sort the chunks. The tools
  tries to find parts of the same recording (by analyzing the timecode
  informationof the chunks) and bring them into the right order.

  Parameter: sort

Step 3: Show chunks
  You can list all chunks to make sure that the program did the job properly.

  Parameter: show

Step 4: Export chunks
  This step will use the conditioned chunk data and export the chunks. You can
  either export all chunks at once or select chunks. The tool will assembly all
  parts of the same recording into one file.
  Use paramater "show" to get the id of the chunk you want to extract. If you
  call export without any additional parameter, all chunks will be exported.

  Parameter: export


Additional Parameters:
----------------------

setup [setup-args]        Manage all settings necessary for a working script.

setup show                Show all settings.
setup reset               Reset all settings to default values.

setup input clear         Delete all input files from list.
setup input add [FILE]    Add input file to list.
setup input remove [FILE] Remove input file from list.

setup blocksize [INTEGER]
setup exportdir [STRING]
setup minchunksize [INTEGER]
setup maxcreategap [INTEGER]
setup maxsortgap [INTEGER]



Usage:
------

  usage
  sample_settings
  test_settings
  create
  sort
  reset
  clear
  show
  export [chunk-id]


Tested devices:
---------------

  * Panasonic DMR-EH55
  * Panasonic DMR-EH56
  * Panasonic DMR-EH57

'''


import os.path
import sqlite3
import sys
import time


class DvrRecoverError(Exception):
    '''Base class for all Exceptions in this module'''
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

class OptionFileError(DvrRecoverError):
    pass

class SqlManagerError(DvrRecoverError):
    pass

class CreateError(DvrRecoverError):
    '''Error while creating chunk list'''
    pass

class ExportError(DvrRecoverError):
    '''Error while exporting chunks'''
    pass

class UnexpectedResultError(DvrRecoverError):
    '''Unexpected result encountered'''
    pass

class FileReaderError(DvrRecoverError):
    '''Exception class for FileReader class'''
    pass



class Chunk(object):
    '''Object to save information about one chunk'''

    __slots__ = ('id',
                 'block_start',
                 'block_size',
                 'clock_start',
                 'clock_end',
                 'concat',
                 'new')

    def __init__(self, new = True):
        for i in self.__slots__:
            setattr(self, i, None)
        self.new = new



class FileReader(object):
    '''Handle multiple input streams as one big file'''
    class FilePart(object):
        '''Object to save information about one input file'''
        def __init__(self):
            self.filename = None
            self.size = None


    def __init__(self, filenames):
        '''Initialize FileReader'''
        self.parts = []
        for filename in filenames:
            if filename[0:3] == r'\\.':
                raise FileReaderError('Direct access to Windows devices files '
                                      'is not supported currently.')
            part = self.FilePart()
            part.filename = filename
            part.size = os.stat(part.filename).st_size
            self.parts.append(part)
        self.current_file = None
        self.file = None


    def get_size(self):
        '''Return the total size of all input streams'''
        size = 0
        for part in self.parts:
            size += part.size
        return size


    def get_index(self, offset):
        '''Return the index of the file where offset is located'''
        index = 0
        start = 0
        for part in self.parts:
            end = start + part.size
            if ((offset >= start) and
                (offset < end)):
                return index
            start = end
            index += 1
        return None


    def get_offset(self, index):
        '''Return the starting offset of a specified file part'''
        i = 0
        offset = 0
        for part in self.parts:
            if i < index:
                offset += part.size
            else:
                break
            i += 1
        return offset


    def open(self, index):
        '''Open input stream with the specified index'''
        self.close()
        if (index >= 0) and (index < len(self.parts)):
            self.file = open(self.parts[index].filename, 'rb')
            self.current_file = index
        else:
            raise FileReaderError('Index out of range!')


    def close(self):
        '''Close current input stream'''
        if self.file is not None:
            self.file.close()
        self.current_file = None
        self.file = None


    def seek(self, offset):
        '''Seek to offset (open correct file, seek, ...)'''
        index = self.get_index(offset)
        delta = offset - self.get_offset(index)
        if self.current_file is None:
            self.open(index)
        else:
            if self.current_file != index:
                self.open(index)
        self.file.seek(delta)


    def is_eof(self):
        '''Return true if eof of current file part is reached'''
        return (self.file.tell() == self.parts[self.current_file].size)


    def next_file(self):
        '''Open next input file'''
        if self.current_file + 1 < len(self.parts):
            self.open(self.current_file + 1)
        else:
            self.close()


    def read(self, size):
        '''Read data from stream, automatically switch stream if necessary'''
        if self.file is None:
            return ''
        buf = self.file.read(size)
        delta = size - len(buf)
        if delta != 0:
            if self.is_eof():
                self.next_file()
                buf += self.read(delta)
            else:
                raise FileReaderError('Incomplete filled buffer without '
                                      'reaching end of file!')
        return buf



class SqlManager(object):
    '''Interface to access data via SQL queries'''
    def __init__(self):
        '''Initialize SqlManager'''
        self.conn = None


    def open(self, filename):
        '''Open Sqlite3 database'''
        self.conn = sqlite3.connect(filename)
        self.init_db()


    def close(self, commit=True):
        '''Close database connection after optional commit'''
        if commit:
            self.commit()
        self.conn.close()


    def commit(self):
        '''Commit all changes'''
        self.conn.commit()


    def init_db(self):
        '''Create structure of database'''
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS chunk("
            "id INTEGER PRIMARY KEY,"
            "block_start INTEGER,"
            "block_size INTEGER,"
            "clock_start INTEGER,"
            "clock_end INTEGER,"
            "concat INTEGER,"
            ")")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS state("
            "key TEXT PRIMARY KEY,"
            "value"
            ")")


    def chunk_count(self):
        '''Return count of rows in chunk table'''
        return self.conn.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]


    def chunk_load(self, chunk_id):
        '''Return chunk object by chunk_id'''
        result = self.conn.execute(
            "SELECT * FROM chunk "
            "WHERE id = ?",
            (chunk_id,)).fetchone()
        if result is None:
            return None
        chunk = Chunk()
        (chunk.id,
         chunk.block_start,
         chunk.block_size,
         chunk.clock_start,
         chunk.clock_end,
         chunk.concat) = result
        return chunk


    def chunk_save(self, chunk):
        '''Insert or update info in chunk table'''
        if chunk.new:
            cur = self.conn.execute(
                "INSERT INTO chunk "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chunk.id,
                 chunk.block_start,
                 chunk.block_size,
                 chunk.clock_start,
                 chunk.clock_end,
                 chunk.concat))

                 chunk.id = cur.rowid
                 chunk.new = False
        else:
            self.conn.execute(
                "UPDATE chunk "
                "SET block_start = ?,"
                    "block_size = ?,"
                    "clock_start = ?,"
                    "clock_end = ?,"
                    "concat = ?,"
                    "position = ? "
                "WHERE id = ?",
                (chunk.block_start,
                 chunk.block_size,
                 chunk.clock_start,
                 chunk.clock_end,
                 chunk.concat,
                 chunk.id))


    def chunk_delete_id(self, chunk_id):
    '''Delete row from chunk table by id'''
        self.conn.execute("DELETE FROM chunk WHERE id = ?",
                          (chunk_id,))


    def chunk_delete(self, chunk):
    '''Delete row from chunk table by chunk object'''
        self.chunk_delete_id(chunk.id)


    def chunk_reset(self):
    '''Delete all rows from chunk table'''
        self.conn.execute("DELETE FROM chunk")


    def chunk_query_ids(self):
    '''Return iterator for all chunk ids'''
        for result in self.conn.execute(
            "SELECT id FROM chunk "
            "ORDERD BY block_start"):
            yield result[0]


    def chunk_query(self):
    '''Return iterator for all chunk objects'''
        for chunk_id in self.chunk_query_ids():
            yield self.chunk_load(chunk_id)


    def state_reset(self):
        '''Delete all entries of state table'''
        self.conn.execute("DELETE FROM state")


    def state_init(self):
        '''Reset state table and set key values to null'''
        self.reset_states()
        for i in ('current_block',
                  'block_start',
                  'clock_start',
                  'old_clock'):
            self.insert_state(i, None)


    def state_query(self, key):
        '''Return value of state by key'''
        result = self.conn.execute(
            "SELECT value FROM state "
            "WHERE key = ?",
            (key,)).fetchone()
        if result is None:
            return None
        return result[0]


    def state_delete(self, key):
        '''Delete entry in state table by key'''
        self.conn.execute(
            "DELETE from state "
            "WHERE key = ?",
            (key,))


    def state_insert(self, key, value):
        '''Insert key/value pair into state table'''
        self.conn.execute(
            "INSERT INTO state "
            "VALUES (?, ?)",
            (key, value))


    def state_update(self, key, value):
        '''Update key/value pair in state table'''
        self.conn.execute(
            "UPDATE state "
            "SET value = ? "
            "WHERE key = ?",
            (value, key))




class Main(object):
    '''Main class for this application'''
    def __init__(self):
        self.settings_filename = 'dvr-recover.conf'
        self.input_filenames = []
        self.db_filename = None
        self.export_dir = None
        self.blocksize = 2048
        self.min_chunk_size = 25600 # 50 MiB
        self.max_create_gap = 90000 # 1 second
        self.max_sort_gap = 90000   # 1 second

        self.db_manager = SqlManager()


    def load_settings(self):
        '''Load all settings and set class attributes'''
        try:
            f = open(self.settings_filename, 'r')
        except IOError:
            raise OptionFileError('Couldn\'t open option file! Use the '
                                  'sample_settings parameter to create one '
                                  'with the default values.')
        for line in f:
            # strip trailing new line character
            line = line[:-1]
            result = line.split('=', 1)
            # set value if no value is set
            if len(result) < 2:
                result.append('')
            (key, value) = result
            if key == 'hdd-file':
                self.input_filenames.append(value)
            elif key == 'db-file':
                self.db_filename = value
            elif key == 'export-dir':
                self.export_dir = value
            elif key == 'blocksize':
                self.blocksize = int(value)
            elif key == 'min-chunk-size':
                self.min_chunk_size = int(value)
            elif key == 'max-create-gap':
                self.max_create_gap = int(value)
            elif key == 'max-sort-gap':
                self.max_sort_gap = int(value)
            else:
                print 'Unknown key in settings file:', key
        f.close()


    def usage(self):
        '''Print usage message'''
        print __doc__


    def sample_settings(self):
        '''Create sample settings file'''
        f = open(self.settings_filename, 'w')
        print >>f, 'hdd-file='
        print >>f, 'db-file=dvr-recover.sqlite'
        print >>f, 'export-dir='
        print >>f, 'blocksize=2048'
        print >>f, 'min-chunk-size=25600'
        print >>f, 'max-create-gap=90000'
        print >>f, 'max-sort-gap=90000'
        f.close()


    def test_settings(self):
        '''Read, verify and show settings'''
        for filename in self.input_filenames:
            print 'input-file:', filename
        print 'chunk-file:', self.chunk_filename
        print 'export-dir:', self.export_dir
        print 'blocksize:', self.blocksize
        print 'min-chunk-size:', self.min_chunk_size
        print 'max-create-gap:', self.max_create_gap
        print 'max-sort-gap:', self.max_sort_gap


    def create(self):
        '''Find all chunks in input file and write them to chunk file'''
        class ChunkFactory(object):
            '''Extract information of all chunks'''
            def __init__(self, main, reader):
                self.current_block = 0
                self.clock = 0
                self.old_clock = 0
                self.chunk = None
                self.timer = time.time()
                self.timer_all = time.time()
                self.timer_blocks = 0

                self.blocksize = main.blocksize
                self.min_chunk_size = main.min_chunk_size
                self.max_gap = main.max_create_gap
                self.db_manager = main.db_manager

                self.reader = reader
                self.input_blocks = int(self.reader.get_size() / self.blocksize)

            def save_state(self):
                if self.chunk is None:
                    block_start = None
                    clock_start = None
                else:
                    block_start = self.chunk.block_start
                    clock_start = self.chunk.clock_start
                self.db_manager.update_state(
                    'current_block',
                    self.current_block)
                self.db_manager.update_state(
                    'block_start',
                    block_start)
                self.db_manager.update_state(
                    'clock_start',
                    clock_start)
                self.db_manager.update_state(
                    'old_clock',
                    self.old_clock)
                self.db_manager.commit()

            def load_state(self):
                current_block = self.db_manager.query_state('current_block')
                block_start = self.db_manager.query_state('block_start')
                clock_start = self.db_manager.query_state('clock_start')
                old_clock = self.db_manager.query_state('old_clock')

                self.current_block = current_block
                if (block_start is not None) and (clock_start is not None):
                    self.chunk = Chunk()
                    self.block_start = block_start
                    self.clock_start = clock_start
                self.old_clock = old_clock

            def check_timer(self):
                '''Print statistics and save state if timer elapses'''
                timer_new = time.time()
                delta = timer_new - self.timer
                if delta > 30:
                    self.save_state()

                    chunk_count = self.db_manager.count_chunks()
                    speed = float(self.current_block - self.timer_blocks) \
                                / float(delta)
                    print '[%5.1f%%] %i/%i blocks (%.1f bl/s; ' \
                          '%.1f MiB/s): %i chunks' % \
                          (
                            float(self.current_block) /
                                float(self.input_blocks) * 100.0,
                            self.current_block,
                            self.input_blocks,
                            speed,
                            float(speed * self.blocksize) / float(1024**2),
                            chunk_count
                          )
                    self.timer_blocks = self.current_block
                    self.timer = timer_new

            def finished(self):
                '''Print statistics and commit changes after finishing'''
                self.db_manager.reset_states()
                self.db_manager.commit()

                delta = time.time() - self.timer_all
                chunk_count = self.db_manager.count_chunks()
                speed = float(self.current_block + 1) / float(delta)
                print
                print 'Finished.'
                print 'Read %i of %i blocks.' % (self.current_block + 1,
                                                 self.input_blocks)
                print 'Found %i chunks.' % chunk_count
                print 'Took %.2f seconds.' % delta
                print 'Average speed was %.1f blocks/s (%.1f MiB/s).' % \
                      (speed, float(speed * self.blocksize) / float(1024**2))

            def mpeg_header(self, buf):
                '''Check if buffer is mpeg header and return system clock or None'''
                #            Partial Program Stream Pack header format
                #            =========================================
                #
                # Name                  |Number of bits| Description
                # ----------------------|--------------|----------------------------
                # sync bytes            | 32           | 0x000001BA
                # marker bits           | 2            | 01b
                # System clock [32..30] | 3            | System Clock Reference
                #                       |              | (SCR) bits 32 to 30
                # marker bit            | 1            | Bit always set.
                # System clock [29..15] | 15           | System clock bits 29 to 15
                # marker bit            | 1            | Bit always set.
                # System clock [14..0]  | 15           | System clock bits 14 to 0
                # marker bit            | 1            | 1 Bit always set.
                #
                #
                #    [4]     [5]      [6]      [7]      [8]      = buffer[x]
                # 01000100|00000000|00000100|00000000|00000100   = marker bits
                #   ^^^ ^^ ^^^^^^^^ ^^^^^ ^^ ^^^^^^^^ ^^^^^      = SCR
                #
                # SCR -> 90 kHz Timer
                #
                # See http://en.wikipedia.org/wiki/MPEG_program_stream#Coding_structure
                if ((ord(buf[0]) != 0x00) or
                    (ord(buf[1]) != 0x00) or
                    (ord(buf[2]) != 0x01) or
                    (ord(buf[3]) != 0xBA)):
                    return None

                marker_bit_1 = (ord(buf[4]) & (3 << 6)) >> 6
                marker_bit_2 = (ord(buf[4]) & (1 << 2)) >> 2
                marker_bit_3 = (ord(buf[6]) & (1 << 2)) >> 2
                marker_bit_4 = (ord(buf[8]) & (1 << 2)) >> 2

                if ((marker_bit_1 != 1) or
                    (marker_bit_2 != 1) or
                    (marker_bit_3 != 1) or
                    (marker_bit_4 != 1)):
                    return None

                clock_bits = [None] * 33

                clock_bits[32] = (ord(buf[4]) & (1 << 5)) >> 5;
                clock_bits[31] = (ord(buf[4]) & (1 << 4)) >> 4;
                clock_bits[30] = (ord(buf[4]) & (1 << 3)) >> 3;
                clock_bits[29] = (ord(buf[4]) & (1 << 1)) >> 1;
                clock_bits[28] = (ord(buf[4]) & (1 << 0)) >> 0;
                clock_bits[27] = (ord(buf[5]) & (1 << 7)) >> 7;
                clock_bits[26] = (ord(buf[5]) & (1 << 6)) >> 6;
                clock_bits[25] = (ord(buf[5]) & (1 << 5)) >> 5;
                clock_bits[24] = (ord(buf[5]) & (1 << 4)) >> 4;
                clock_bits[23] = (ord(buf[5]) & (1 << 3)) >> 3;
                clock_bits[22] = (ord(buf[5]) & (1 << 2)) >> 2;
                clock_bits[21] = (ord(buf[5]) & (1 << 1)) >> 1;
                clock_bits[20] = (ord(buf[5]) & (1 << 0)) >> 0;
                clock_bits[19] = (ord(buf[6]) & (1 << 7)) >> 7;
                clock_bits[18] = (ord(buf[6]) & (1 << 6)) >> 6;
                clock_bits[17] = (ord(buf[6]) & (1 << 5)) >> 5;
                clock_bits[16] = (ord(buf[6]) & (1 << 4)) >> 4;
                clock_bits[15] = (ord(buf[6]) & (1 << 3)) >> 3;
                clock_bits[14] = (ord(buf[6]) & (1 << 1)) >> 1;
                clock_bits[13] = (ord(buf[6]) & (1 << 0)) >> 0;
                clock_bits[12] = (ord(buf[7]) & (1 << 7)) >> 7;
                clock_bits[11] = (ord(buf[7]) & (1 << 6)) >> 6;
                clock_bits[10] = (ord(buf[7]) & (1 << 5)) >> 5;
                clock_bits[ 9] = (ord(buf[7]) & (1 << 4)) >> 4;
                clock_bits[ 8] = (ord(buf[7]) & (1 << 3)) >> 3;
                clock_bits[ 7] = (ord(buf[7]) & (1 << 2)) >> 2;
                clock_bits[ 6] = (ord(buf[7]) & (1 << 1)) >> 1;
                clock_bits[ 5] = (ord(buf[7]) & (1 << 0)) >> 0;
                clock_bits[ 4] = (ord(buf[8]) & (1 << 7)) >> 7;
                clock_bits[ 3] = (ord(buf[8]) & (1 << 6)) >> 6;
                clock_bits[ 2] = (ord(buf[8]) & (1 << 5)) >> 5;
                clock_bits[ 1] = (ord(buf[8]) & (1 << 4)) >> 4;
                clock_bits[ 0] = (ord(buf[8]) & (1 << 3)) >> 3;

                clock = 0
                for i in range(0,33):
                    clock += clock_bits[i] * 2**i
                return clock

            def split(self):
                '''End current chunk and start a new one'''
                if self.chunk is not None:
                    self.chunk.block_size = self.current_block - 1 - \
                                            self.chunk.block_start
                    self.chunk.clock_end = self.old_clock

                    if (self.chunk.block_size >= self.min_chunk_size):
                        self.db_manager.insert_chunk(self.chunk)
                    self.chunk = None

            def run(self):
                '''Main function for this class'''
                self.load_state()
                if self.current_block is None:
                    if self.db_manager.chunk_count() != 0:
                        raise CreateError('No state information, but chunk '
                                          'count is not 0. Probably the scan '
                                          'finished already. Abort process to '
                                          'avoid loss of data. Use parameter '
                                          'clear to clear database (you will
                                          'lose all chunk information).')
                    self.current_block = 0
                self.db_manager.reset_states()
                self.db_manager.init_states()
                self.reader.seek(self.current_block * self.blocksize)
                for self.current_block in xrange(self.current_block,
                                                 self.input_blocks):
                    self.check_timer()
                    buf = self.reader.read(self.blocksize)
                    if len(buf) != self.blocksize:
                        raise UnexpectedResultError('len(buf) != '
                                                    'self.blocksize')
                    self.clock = self.mpeg_header(buf)
                    if self.clock is None:
                        self.split()
                    else:
                        if self.chunk is None:
                            self.chunk = Chunk()
                            self.chunk.block_start = self.current_block
                            self.chunk.clock_start = self.clock
                        else:
                            delta = self.clock - self.old_clock
                            if (delta < 0) or (delta > self.max_gap):
                                self.split()
                        self.old_clock = self.clock
                self.split()
                self.finished()

        reader = FileReader(self.input_filenames)
        cf = ChunkFactory(self, reader)
        cf.run()
        reader.close()


    def sort(self):
        '''Sort chunks and try to concatenate parts of the same recording'''
        def find_next_part(chunk_id):
            '''Find the next chunk which should be concatenated'''
            chunk = self.db_manager.query_chunk_by_id(chunk_id)
            next_part = None
            for chunk_id2 in old_chunk_ids:
                if (chunk_id is chunk_id2) or (chunk_id2 in new_chunk_ids):
                    continue

                chunk2 = self.db_manager.query_chunk_by_id(chunk_id2)

                delta = chunk2.clock_start - chunk.clock_end
                if (delta < 0) or (delta > self.max_sort_gap):
                    continue

                if next_part is None:
                    next_part = chunk_id2
                else:
                    old = next_part.clock_start - chunk.clock_end
                    if delta < old:
                        next_part = chunk_id2

            if next_part is not None:
                new_chunk_ids.append((next_part, True))
                old_chunk_ids.remove(next_part)
                find_next_part(next_part)

        old_chunk_ids = self.db_manager.query_chunk_ids('clock_start')
        new_chunk_ids = []
        for chunk_id in old_chunk_ids:
            new_chunk_ids.append((chunk_id, False))
            find_next_part(chunk_id)

        index = 0
        for chunk_info in new_chunk_ids:
            chunk = self.db_manager.query_chunk_by_id(chunk_info[0])
            chunk.position = index
            chunk.concat = chunk_info[1]
            self.db_manager.update_chunk_by_id(chunk)
            index += 1


    def reset(self):
        '''Sort chunks by block_start and clear concat attribute'''
        self.db_manager.reset_chunk_status()


    def clear(self):
        '''Delete all chunks'''
        self.db_manager.chunk_reset()


    def show(self):
        '''Dump chunk list file in a human readable way'''
        chunk_ids = self.db_manager.query_chunk_ids('position')
        max_index_length = len(str(len(chunk_ids) - 1))
        header_lines = '-' * (max_index_length) + \
          '-+--------------+--------------+--------------+--------------+-------------'
        header_captions = ' ' * (max_index_length) + \
          ' |  Block Start |   Block Size |  Clock Start |    Clock End | Concatenate'
        print header_lines
        print header_captions
        print header_lines
        index = 0
        fstring = '%' + str(max_index_length) + \
                  'i | %12i | %12i | %12i | %12i | %8s'
        for chunk_id in chunk_ids:
            chunk = self.db_manager.query_chunk_by_id(chunk_id)
            print fstring % (index,
                             chunk.block_start,
                             chunk.block_size,
                             chunk.clock_start,
                             chunk.clock_end,
                             chunk.concat)
            index += 1


    def export(self):
        '''export single chunk or all chunks'''
        def copy_chunk(reader, outf, chunk):
            '''Copy data from inf to outf with help of chunk information'''
            print 'Chunk start: %i' % chunk.block_start
            print 'Chunk size:  %i' % chunk.block_size
            timer = time.time()
            reader.seek(chunk.block_start * self.blocksize)
            for i in xrange(0, chunk.block_size):
                buf = reader.read(self.blocksize)
                if len(buf) != self.blocksize:
                    raise UnexpectedResultError('len(buf) != self.blocksize')
                outf.write(buf)
            delta = time.time() - timer
            speed = float(chunk.block_size) / float(delta)
            print ' %.2fs (%.2f blocks/s; %.2f MiB/s).' % \
                  (delta,
                   speed,
                   float(speed * self.blocksize) / float(1024**2))
            print

        def extract_chunk(chunk_index):
            '''Extract single chunk with all its childs'''
            chunk = self.chunks[chunk_index]
            print 'Current chunk: #%i' % chunk_index
            if chunk.concat:
                raise ExportError(
                      'Specified chunk should be concatenated to another. ' \
                      'Please specify a starting chunk (concatenate must be ' \
                      'False!).'
                      )

            reader = FileReader(self.input_filenames)
            outf = open(os.path.join(self.export_dir, 'chunk_%04i.mpg' % \
                                  chunk_index), 'wb')
            copy_chunk(reader, outf, chunk)
            for i in xrange(chunk_index + 1, len(self.chunks)):
                chunk = self.chunks[i]
                if chunk.concat:
                    print 'Concatenate chunk: #%i' % i
                    copy_chunk(reader, outf, chunk)
                else:
                    break;
            outf.close()
            reader.close()

        if len(sys.argv) < 3:
            # no special chunk specified -> export all
            for i in xrange(0, self.db_manager):
                if not self.chunks[i].concat:
                    extract_chunk(i)
        else:
            # only export specified chunk
            i = int(sys.argv[2])
            if (i >= 0) and (i < len(self.chunks)):
                extract_chunk(i)
            else:
                raise ExportError('Incorrect chunk specified!')


    def run(self):
        '''Run the main program'''
        if len(sys.argv) < 2:
            self.usage()
            return
        if sys.argv[1] in ('sample_settings', 'test_settings', 'create',
                           'sort', 'reset', 'clear', 'show', 'export'):
            if sys.argv[1] != 'sample_settings':
                self.load_settings()
            self.db_manager.open(self.db_filename)
            func = getattr(self, sys.argv[1])
            func()
            self.db_manager.close()
        else:
            self.usage()


if __name__ == '__main__':
    Main().run()
