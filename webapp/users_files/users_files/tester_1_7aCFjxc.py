#!/usr/bin/env python3

import socket
from subprocess import Popen, PIPE, STDOUT, TimeoutExpired
import sys
from time import sleep
from datetime import datetime
from typing import List, Optional, Sequence, Tuple, Callable, Dict, Union
import random
import os
import binascii
import re
import time
import struct
import shutil
import zipfile
from pathlib import Path
import sqlite3
import argparse
from matplotlib import pyplot as plt
import numpy as np
import traceback
import csv



EXIT_FAILURE = 1
EXIT_SUCCESS = 0

# Configuration

min_port = 11212
max_port = 15212
startup_timeout = 2  # wait up to 2 seconds for server startup
startup_wait_quantum = 0.1
socket_timeout = 1
socket_big_timeout = 7
max_points = 8
stop_wait = 0.1
stop_timeout = 1
big_file_size = 2**28 
make_time_limit = 60

# Penalties:
wrong_archive_name = 0.1
wrong_archive_structure = 0.1
wrong_binary_name = 0.1
no_makefile = 0.2
build_failed = 0.5
wrong_content_type = 0.4
wrong_location_header = 0.4




# ===================================
# ======== Logging functions ========
# ===================================
startTime = datetime.now()

ENDC = '\033[0m'
COLOUR_RED = '\033[0;31m'
COLOUR_GREEN = '\033[0;32m'
COLOUR_YELLOW = '\033[0;33m'
COLOUR_BLUE = '\033[0;34m'
COLOUR_CYAN = '\033[2;96m'


def logInfo(*args, end='\n', flush=False):
    print(COLOUR_BLUE + "[{0:06f}|".format((datetime.now() - startTime).total_seconds()) \
          + COLOUR_CYAN + '{:^16s}'.format(sys._getframe(1).f_code.co_name[:16]) + COLOUR_BLUE + ']' \
          + COLOUR_GREEN + '[+]' + ENDC, " ".join(map(str, args)), end=end, flush=flush)


def logError(*args, end='\n', flush=False):
    print(COLOUR_BLUE + "[{0:06f}|".format((datetime.now() - startTime).total_seconds()) \
          + COLOUR_CYAN + '{:^16s}'.format(sys._getframe(1).f_code.co_name[:16]) + COLOUR_BLUE + ']' \
          + COLOUR_RED + '[!!!]' + ENDC, " ".join(map(str, args)), end=end, flush=flush)

# ===================================
# ======== Exception classes ========
# ===================================

class ServerNotAvailableException(Exception):
    def __init__(self, msg):
        super().__init__(self)
        self.msg = msg


class ServerCommunicationException(Exception):
    def __init__(self, msg):
        super().__init__(self)
        self.msg = msg


class TestFailedException(Exception):
    def __init__(self, msg):
        super().__init__(self)
        self.msg = msg

# ===================================
# ======== Various utilities ========
# ===================================

def try_remove(path: Path):
    path.unlink(missing_ok=True)


def try_rmdir(path: Path):
    try:
        path.rmdir()
    except FileNotFoundError:
        pass


def try_rmtree(path: Path):
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


def read_until_correct(prompt: str, validator: Callable[[str], bool]):
    while True:
        inp = input(prompt)
        if validator(inp):
            return inp


def valid_name(name: str) -> bool:
    return bool(re.fullmatch(r'[a-zA-Z]{2}\d{6}', name))


def float_convertible(f: str) -> bool:
    try:
        float(f)
        return True
    except ValueError:
        return False

def float_or_empty(f: str) -> bool:
    if f == '':
        return True
    return float_convertible(f)


# ============================================================
# ======== Functions for server starting/stopping/etc ========
# ============================================================

def get_tcp_port_users(port_no: int) -> List[Tuple[str, str]]:
    with open("/proc/net/tcp", "r") as f:
        lines = f.readlines()[1:]
    #print(lines)
    hex_port = "{:04x}".format(port_no).upper()
    pattern = (
        r"^[^:]*: ([0-9A-Fa-f]{8}:[0-9A-Fa-f]{4}) ([0-9A-Fa-f]{8}:[0-9A-Fa-f]{4}).*$"
    )
    matching = [
        match.group(1, 2)
        for match in (re.search(pattern, l) for l in lines)
        if match.group(1)[-4:] == hex_port
    ]
    return matching


# Checks if there is a server listening on a given port or a connection that is
# using this port on our end
def check_if_port_available(port_no: int) -> bool:
    matching = get_tcp_port_users(port_no)
    if matching:
        return False
    return True


def get_free_port_in_range(ports: Sequence[int]) -> int:
    for port in ports:
        if check_if_port_available(port):
            return port

    raise Exception("No available port found in range")


def launch_server(args: Sequence[str], base_dir: Path) -> Tuple[Popen, int]:
    """Launches the server with given parameters

    If there is %d in the parameters' list, it is substituted with an
    available port number before running the server.

    Returns: server's Popen object and server's port"""

    port = get_free_port_in_range(range(min_port, max_port))
    args = [a.replace('%d', str(port)).replace('%p', str(base_dir)) for a in args]
    #print(args)
    srv = Popen(args, stdout=PIPE, stderr=STDOUT)

    # wait till the port is not available
    waited = 0.0
    while check_if_port_available(port):
        sleep(startup_wait_quantum)
        waited += startup_wait_quantum
        if waited >= startup_timeout:
            srv.stdout.close()
            srv.kill()
            raise Exception("Server not ready in time")
        if not is_server_running(srv):
            raise Exception('Server quit unexpectedly')

    return srv, port


def is_server_running(srv: Popen) -> bool:
    return srv.poll() is None


def stop_server(srv: Optional[Popen]):
    if not srv:
        return
    srv.terminate()
    sleep(stop_wait)
    if srv.poll() is None:
        sleep(stop_timeout)
        if srv.poll() is None:
            srv.kill()
            sleep(stop_wait)

    if srv.poll() is None:
        raise Exception("Unkillable server")


def get_server_output_and_exit_code(srv: Popen) -> Tuple[Union[bytes, str], int]:
    if is_server_running(srv):
        raise Exception("Stop server before getting its output!")
    out_raw = srv.stdout.read()
    try:
        out = out_raw.decode()
    except:
        out = out_raw
    return out, srv.wait()

# ==============================
# ======== Socket utils ========
# ==============================

def connect(srv: Popen, port: int, addr=None) -> socket.socket:
    if not is_server_running(srv):
        raise ServerNotAvailableException("Unable to connect to a non-running server")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(socket_timeout)
    if sock == -1:
        raise ServerCommunicationException("Unable to create socket")
    if addr is None:
        addr = "localhost"
    try:
        sock.connect((addr, port))
    except Exception as exc:
        raise ServerCommunicationException("Unable to connect to socket: " + str(exc))
    return sock


def send(srv: Popen, sock: socket.socket, txt: str):
    if not is_server_running(srv):
        raise ServerNotAvailableException("Unable to send to a non-running server")
    stream = txt.encode("utf-8")
    r = sock.send(stream)
    if r == -1:
        raise ServerCommunicationException("Can't send data to the server")
    if not r == len(stream):
        raise ServerCommunicationException("Partial write!")
    if not is_server_running(srv):
        raise ServerNotAvailableException("Server stopped while receiving request")


def recv(srv: Popen, sock: socket.socket, max_size: int = 16384) -> bytes:
    if not is_server_running(srv):
        raise ServerNotAvailableException("Unable to read from a non-running server")
    stream = sock.recv(max_size)
    # handle empty string, i.e. EOF on higher level
    if not is_server_running(srv):
        raise ServerNotAvailableException("Server stopped while reading reply")
    return stream

# ============================
# ======== HTTP utils ========
# ============================

read_response_buffer = b""


def read_server_response_headers(srv: Popen, sock: socket.socket) -> List[str]:
    def read_response_line():
        global read_response_buffer
        # checks if it is in the buffer already
        while read_response_buffer.find(b"\r\n") == -1:
            data = recv(srv, sock)
            if data == b"":
                raise ServerCommunicationException(
                    "Unexpected EOF while reading from server"
                )
            read_response_buffer += data

        line, read_response_buffer = read_response_buffer.split(b"\r\n", maxsplit=1)
        return line.decode("utf-8")

    lines = []
    line = read_response_line()
    while line != "":
        lines.append(line)
        line = read_response_line()

    return lines


def read_server_response_bytes(srv: Popen, sock: socket.socket, size: int) -> bytes:
    global read_response_buffer
    while len(read_response_buffer) < size:
        data = recv(srv, sock)
        if data == b"":
            raise ServerCommunicationException(
                "Unexpected EOF while reading from server"
            )
        read_response_buffer += data

    ret = read_response_buffer[:size]
    read_response_buffer = read_response_buffer[size:]
    return ret


def check_server_response(
    lines: List[str], expected_codes: Sequence[int]
) -> Tuple[bool, str, int, Dict[str, str]]:
    if not lines:
        return False, "Empty server response", -1, {}
    first_line_pattern = r"HTTP/1.1 (\d+) .*"
    match = re.fullmatch(first_line_pattern, lines[0])
    if not match:
        return False, "Unexpected first line of response", -1, {}

    result_code = int(match.group(1))
    if result_code not in expected_codes:
        return False, f"Unexpected result code {result_code}, allowed: {expected_codes}", -1, {}

    headers: Dict[str, str] = {}
    content_length = -1
    for line in lines[1:]:
        match = re.fullmatch(r"([\w-]+):\s*(.*?)\s*", line)
        if not match:
            return False, "Bad header line: " + line, -1, headers
        name = match.group(1).lower()
        value = match.group(2).strip()
        if name in headers:
            return False, 'Repeated header name', -1, headers
        headers[name] = value
        if name == "content-length":
            cl_txt = value
            try:
                content_length = int(cl_txt)
            except ValueError:
                return False, f'Bad content length header: {cl_txt}', -1, headers

    return True, "OK", content_length, headers

# =======================================
# ======== Grading all solutions ========
# =======================================
test_report_format_ok = "Test {}: OK\n\n========================================\n\n"
test_report_format_err = """\
Test {}: FAILED

Fail reason: {}

Server exit code: {}
Server output:
{}

========================================

"""

report_format = """\
Report for {}:

{}
{}

Score: {} / {}
{} of {} tests passed.

Tests results:

========================================

{}
"""

class Report:
    def __init__(self, dirname):
        self.dirname = dirname
        self.name = None
        self.notes = []
        self.penalties = []
        self.tests = []
    
    def add_note(self, text):
        if text in self.notes:
            return
        self.notes.append(text)
    
    def add_penalty(self, reason, value, description):
        for r, _, _ in self.penalties:
            if r == reason:
                return
        self.penalties.append((reason, value, description))
    
    def add_test(self, name, points, passed, msg, out, exit_code):
        for n, _, _, _, _, _ in self.tests:
            if n == name:
                raise ValueError('Duplicate test?!')
        self.tests.append((name, points, passed, msg, out, exit_code))
    
    def get_notes_report(self):
        if not self.notes:
            return ''
        report = 'Notes:\n'
        for note in self.notes:
            report += f'\t- {note}\n'
        return report
    
    def get_penalty_report(self):
        if not self.penalties:
            return ''
        report = 'Penalties:\n'
        for penalty in self.penalties:
            report += f'\t#-{penalty[1]}: {penalty[2]}'
        return report
    
    def calculate_points(self):
        score = 0.0
        good_cnt = 0
        for test in self.tests:
            if test[2]:
                score += test[1]
                good_cnt += 1
        for penalty in self.penalties:
            score -= penalty[1]
        if score < 0.0:
            score = 0.0
        return round(score, 2), good_cnt

    def report_to_string(self):
        tests_report = ''
        for test in self.tests:
            if test[2]:
                tests_report += test_report_format_ok.format(test[0])
            else:
                tests_report += test_report_format_err.format(test[0], test[3], test[5], test[4])
        notes_report = self.get_notes_report()
        penalty_report= self.get_penalty_report()
        score, good_cnt = self.calculate_points()
        return report_format.format(self.name or self.dirname, notes_report, penalty_report, score, max_points, good_cnt, len(self.tests), tests_report)


class ReportDB:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
    
    def initdb(self):
        logInfo('Clearing and initializing database')
        cur = self.connection.cursor()
        cur.execute('''DROP TABLE IF EXISTS users''')
        cur.execute('''CREATE TABLE users (
            user CHAR(8) PRIMARY KEY,
            dirname CHAR(255))''')
        cur.execute('''DROP TABLE IF EXISTS tests''')
        cur.execute('''CREATE TABLE tests (
            user CHAR(8), 
            name CHAR(255),
            idx INTEGER,
            points REAL, 
            passed BOOLEAN, 
            msg TEXT, 
            out TEXT, 
            exit_code INTEGER, 
            PRIMARY KEY (user, name))''')
        cur.execute('''DROP TABLE IF EXISTS notes''')
        cur.execute('''CREATE TABLE notes (
            user CHAR(8),
            note TEXT,
            idx INTEGER,
            PRIMARY KEY (user, note))''')
        cur.execute('''DROP TABLE IF EXISTS penalties''')
        cur.execute('''CREATE TABLE penalties (
            user CHAR(8),
            reason CHAR(255),
            idx INTEGER,
            value REAL,
            description TEXT,
            PRIMARY KEY(user, reason))''')
        self.connection.commit()

    def add_report(self, report: Report):
        cur = self.connection.cursor()
        cur.execute('INSERT INTO users VALUES (?, ?)', (report.name, report.dirname))
        for i, note in enumerate(report.notes):
            cur.execute('INSERT INTO notes VALUES(?, ?, ?)', (report.name, note, i))
        for i, penalty in enumerate(report.penalties):
            reason, value, description = penalty
            cur.execute('INSERT INTO penalties VALUES (?, ?, ?, ?, ?)', (report.name, reason, i, value, description))
        for i, test in enumerate(report.tests):
            name, points, passed, msg, out, exit_code = test
            cur.execute('INSERT INTO tests VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (report.name, name, i, points, passed, msg, out, exit_code))
        self.connection.commit()

    def has_report(self, user: str) -> bool:
        cur = self.connection.cursor()
        res = cur.execute('SELECT count(*) FROM users WHERE user = ?', (user,))
        return bool(next(res)[0])
    
    def get_report(self, user: str) -> Optional[Report]:
        cur = self.connection.cursor()
        res = cur.execute('SELECT user, dirname FROM users WHERE user = ?', (user,)).fetchall()
        if not len(res) == 1:
            return None
        _, dirname = res[0]
        report = Report(dirname)
        report.name = user
        for row in cur.execute('''
            SELECT note 
            FROM notes 
            WHERE user = ? 
            ORDER BY idx ASC''', (user,)):
                report.add_note(*row)
        for row in cur.execute('''
            SELECT reason, value, description 
            FROM penalties 
            WHERE user = ? 
            ORDER BY idx ASC''', (user,)):
                report.add_penalty(*row)
        for row in cur.execute('''
            SELECT name, points, passed, msg, out, exit_code 
            FROM tests  
            WHERE user = ?
            ORDER BY idx ASC''', (user,)):
                report.add_test(*row)
        return report
    
    def get_all_users(self):
        cur = self.connection.cursor()
        return cur.execute('SELECT user FROM users').fetchall()
    
    def get_all_reports(self):
        users = self.get_all_users()
        reports = []
        for user in users:
            reports.append(self.get_report(user[0]))
        return reports

def read_penalty(default: float):
    inp = read_until_correct(f'Input penalty (empty for default = {default}): ', float_or_empty)
    if inp == '':
        return default
    return float(inp)

class Solution:
    def __init__(self, base_path):
        self.base_path: Path = base_path
        self.name = None
        self.archive_path: Path = None
        self.unpacked_path: Path = None
        self.binary_path: Path = None
        self.env_path: Path = base_path/'env'
        self.report = Report(str(self.base_path))

    def get_report(self):
        return self.report
    
    def identify_archive(self):
        logInfo(f'Searching for archive in {self.base_path}')
        candidates = sorted(self.base_path.glob('*'))
        for candidate in candidates:
            if re.fullmatch(r'[a-zA-Z]{2}\d{6}(\.tar)?\.gz', candidate.name):
                self.name = candidate.name[:8]
                self.report.name = self.name
                self.archive_path = candidate
                logInfo(f'Found archive: {candidate}, name: {self.name}')
                return
        # No matching file
        def valid_decision(d: str) -> bool:
            return (int(d) >= 0 and int(d) < len(candidates)) or d == 'a'
        
        logError(f'Cant find file to grade for directory {self.base_path}')
        logInfo('Available options:')
        for i, f in enumerate(candidates):
            logInfo(f'{i}) {f.name}')
        logInfo('')
        logInfo('a) skip')
        decision = read_until_correct('Choose option: ', valid_decision)
        if decision == 'a':
            logError('Skipped')
            self.report.add_note('Couldnt find archive file')
            raise ValueError('Cant identify archive')
        decision = int(decision)
        logInfo(f'Chosen file: {candidates[decision]}')
        self.archive_path = candidates[decision]
        self.name = read_until_correct('Input name in the form ab123456: ', valid_name)
        self.report.name = self.name
        penalty_value = read_penalty(wrong_archive_name)
        self.report.add_penalty('wrong_archive_name', penalty_value, 'Incorrect name of the archive file')
    
    def unpack_archive(self):
        def has_makefile(p: Path) -> bool:
            return (p/'GNUmakefile').is_file() or (p/'makefile').is_file() or (p/'Makefile').is_file()
        logInfo(f'Unpacking solution {self.name} (base_path: {self.base_path})')
        if self.base_path is None or self.archive_path is None:
            raise ValueError('Unknown base_path or archive_path, cant extract')
        unpacked_path = self.base_path/'unpacked'
        try_rmtree(unpacked_path)
        unpacked_path.mkdir()
        shutil.unpack_archive(self.archive_path, unpacked_path, 'gztar')
        # First option: exactly one dir, named e.g. ab123456, in it there should be Makefile
        listing = list(unpacked_path.glob('*'))
        if (len(listing) == 1 
            and listing[0].name == self.name
            and has_makefile(unpacked_path/self.name)):
                self.unpacked_path = unpacked_path/self.name
        # Second option: Makefile in main dir
        elif has_makefile(unpacked_path):
            self.unpacked_path = unpacked_path
            self.report.add_penalty('wrong_archive_structure', wrong_archive_structure, 'Incorrent archive structure')
        # Third option: folder is named differently, and contains Makefile
        elif (len(listing) == 1 
            and has_makefile(listing[0])):
                self.unpacked_path = listing[0]
                self.report.add_penalty('wrong_archive_structure', wrong_archive_structure, 'Incorrent archive structure')
        # I have no more ideas
        else:
            def valid_decision(d: str) -> bool:
                if d == 'a':
                    return True
                return has_makefile(self.base_path/'unpacked'/d)
            logError(f'Cant find Makefile for {self.name}')
            decision = read_until_correct(f'Input directory, relative to {self.base_path/"unpacked"}. a for abort: ', valid_decision)
            if decision == 'a':
                self.report.add_note('Couldnt find Makefile')
                raise ValueError('Invalid folder structure! - Makefile not found')
            self.unpacked_path = self.base_path/'unpacked'/decision
            penalty = read_penalty(no_makefile)
            self.report.add_penalty('no_makefile', penalty, 'Makefile not found')
                
 
    def build(self):
        if self.unpacked_path is None:
            raise ValueError('Cant build - no unpacked path')
        logInfo(f'Building solution {self.name} (path: {self.unpacked_path})')
        def valid_choice(s: str):
            return s.lower() in ['a', 'r']
        make = Popen(['make', '-B', '-C', str(self.unpacked_path)], stdout=PIPE, stderr=PIPE)
        try:
            stdout, stderr = make.communicate(timeout=make_time_limit)
        except TimeoutExpired as e:
            logError('Build not finished in time!\n')
            choice = read_until_correct('[A]bort / [r]etry? ', valid_choice)
            if choice.lower() == 'r':
                return self.build()
            else:
                self.report.add_note('Build timed out')
                raise Exception('Build timed out')
        if not make.returncode == 0:
            logError('Build failed!')
            error_str = 'stdout:\n' + stdout.decode() + '\nstderr:\n' + stderr.decode()
            logError('stdout:\n', stdout.decode())
            logError('stderr:\n', stderr.decode())
            choice = read_until_correct('[A]bort / [r]etry? ', valid_choice)
            if choice.lower() == 'r':
                penalty = read_penalty(build_failed)
                self.report.add_penalty('build_failed', penalty, 'Errors during compilation:\n' + error_str)
                return self.build()
            else:
                self.report.add_note('Building failed:\n' + error_str)
                raise Exception('Build failed!')
        self.identify_binary_file()
        
    def identify_binary_file(self):
        # Try to identify resulting binary
        # First, correct option: serwer binary
        def is_exec_file(f: Path) -> bool:
            return f.is_file() and os.access(f, os.X_OK)
        if is_exec_file(self.unpacked_path/'serwer'):
            self.binary_path = self.unpacked_path/'serwer'
        # Else, probably popular mistake: server
        elif is_exec_file(self.unpacked_path/'server'):
            self.binary_path = self.unpacked_path/'server'
            self.report.add_penalty('wrong_binary_name', wrong_binary_name, 'Binary file should be named serwer, not server')
        # Everything else...
        else:
            def is_correct_file(p: str):
                return not p or is_exec_file(self.unpacked_path/p)
            logError(f'Binary not found for {self.name}')
            s = read_until_correct(f'Input path relative to {self.unpacked_path}, empty for skip: ', is_correct_file)
            if not s:
                self.report.add_note('Couldnt find compiled binary')
                raise Exception('Cant find compiled binary')
            self.binary_path = self.unpacked_path/s
            penalty = read_penalty(wrong_binary_name)
            self.report.add_penalty('wrong_binary_name', penalty, f'Executable "serwer" not found')
            

# Current solution being testes - tests can access it to e.g. add notes
current_solution = None

class Tester:
    def __init__(self, tests):
        self.tests = tests

    def run_standard_test(
        self, test_fn, server_path: Path, files_path: str, resources_path: str, solution: Solution
    ) -> Tuple[bool, str, Union[bytes, str], int]:
        srv = None
        try:
            srv, port = launch_server([str(server_path), files_path, resources_path, "%d"], solution.env_path)
            test_fn(solution, srv, port)

            stop_server(srv)
            out, code = get_server_output_and_exit_code(srv)
            srv = None
            return True, "OK", out, code

        except (ServerCommunicationException, TestFailedException) as ex:
            if srv:
                stop_server(srv)
                out, code = get_server_output_and_exit_code(srv)
            else:
                out, code = b"", -1
            return False, ex.msg + '\ntraceback: ' + traceback.format_exc(), out, code
        except ServerNotAvailableException as sna:
            return False, sna.msg + '\ntraceback: ' + traceback.format_exc(), b"", -1
        except socket.timeout as ex:
            if srv:
                stop_server(srv)
                out, code = get_server_output_and_exit_code(srv)
            else:
                out, code = b"", -1
            return False, 'Timed out. \ntraceback: ' + traceback.format_exc(), out, code
        except KeyboardInterrupt as e:
            if srv:
                stop_server(srv)
                out, code = get_server_output_and_exit_code(srv)
            logError('')
            logError('Tests stopped by keyboard interrupt!')
            sys.exit(1)
        except:
            if srv:
                stop_server(srv)
                out, code = get_server_output_and_exit_code(srv)
            else:
                out, code = b"", -1
            return False, "Unexpected exception" + str(sys.exc_info()) + '\ntraceback: ' + traceback.format_exc(), out, code
        finally:
            if srv:
                stop_server(srv)


    def prepare_env(self, solution: Solution):
        if solution.base_path is None:
            raise ValueError('Unknown base_path, cant prepare env')
        logInfo(f'Preparing environment for {solution.name} at {solution.env_path}')
        env_path = solution.env_path
        try_rmtree(env_path)
        env_path.mkdir()

        os.mkdir(env_path/'data')
        for i in range(1, 65):
            with (env_path/'data'/f'{i}.data').open('wb') as f:
                f.write(os.urandom(i))
        with (env_path/'empty_resources').open('w+') as f:
            pass
        def int2ip(addr: int) -> str:
            return socket.inet_ntoa(struct.pack("!I", addr))
        with (env_path/'resources').open('w') as f:
            random.seed(12313123123)
            for i in range(1, 65):
                f.write(f'/remote-{i}.data\t{int2ip(random.getrandbits(32))}\t{random.randint(1, 65535)}\n')
        with (env_path/'data'/'bigfile.data').open('wb') as f:
            f.write(os.urandom(big_file_size))
    

    def teardown_env(self, solution: Solution):
        if solution.base_path is None:
            raise ValueError('Unknown base_path, cant prepare env')
        try_rmtree(solution.env_path)


    def run_tests(self, solution: Solution):
        global current_solution
        current_solution = solution
        self.prepare_env(solution)
        tests_sum = 0
        for test in self.tests:
            tests_sum += test[3]

        for i, test in enumerate(self.tests, start=1):
            test_fn = test[0]
            test_name = test_fn.__name__
            points = round((test[3] / tests_sum) * max_points, 2)
            logInfo(f"Running test {i}: {test_name}... ", end="", flush=True)
            reset_global_buffer()
            
            if test[1]:
                data_dir, res_file = test[2]
                good, msg, out, exit_code = self.run_standard_test(
                    test_fn, solution.binary_path, data_dir, res_file, solution
                )
            else:
                good, msg, out, exit_code = test_fn(solution.binary_path, *test[2], solution)

            solution.get_report().add_test(test_name, points, good, msg, out, exit_code)
            print("Done.", flush=True)
        self.teardown_env(solution)

def grade_all(solutions_dir: Path, grades: ReportDB):
    tester = Tester(tests_list)
    if not solutions_dir.is_dir():
        logError('Path must point to a directory')
        sys.exit(1)
    slist = list(solutions_dir.glob('*'))
    for i, d in enumerate(slist, start=1):
        logInfo(f'Testing solution {i}/{len(slist)}: {str(d)}')
        solution = Solution(d)
        try:
            solution.identify_archive()
        except ValueError as e:
            logError(f'Cant identify archive file for solution {solution.base_path}: {e}')
            continue
        if grades.has_report(solution.name):
            logInfo(f'Report for {solution.name} already in DB, skipping')
            continue
        try:
            solution.unpack_archive()
        except ValueError as e:
            logError(f'Cant unpack archive for solution {solution.base_path}: {e}')
            grades.add_report(solution.get_report())
            continue
        try:
            solution.build()
        except (Exception, ValueError) as e:
            logError(f'Cant build solution {solution.name}: {e}')
            grades.add_report(solution.get_report())
            continue
        tester.run_tests(solution)
        score, good_cnt = solution.get_report().calculate_points()
        logInfo(f'Score: {score}/{max_points}, tests passed: {good_cnt}/{len(tests_list)}')
        grades.add_report(solution.get_report())


def main():
    parser = argparse.ArgumentParser(description='Grade solutions to HTTP server task')
    subparsers = parser.add_subparsers(help='commands', dest='command')

    parser_simple = subparsers.add_parser('simple', help='Grade a solution and print report, dont save anything.')
    parser_simple.add_argument('--dir', type=Path, required=True, help='Directory with solution (contains Makefile)')

    parser_grade = subparsers.add_parser('grade', help='Grade all solutions. Save results to database.')
    parser_grade.add_argument('--dir', type=Path, required=True, help='Directory with all solutions - each subdir should contain archive with a solution.')
    parser_grade.add_argument('--db', type=Path, required=True, help='Database file to save results in.')

    parser_continue = subparsers.add_parser('continue', help='Continue interrupted grading process.')
    parser_continue.add_argument('--dir', type=Path, required=True, help='Directory with all solutions - each subdir should contain archive with a solution.')
    parser_continue.add_argument('--db', type=Path, required=True, help='Database file to save results in.')

    parser_report = subparsers.add_parser('report', help='Print given report from database')
    parser_report.add_argument('--db', type=Path, required=True, help='Database file to fetch results from.')
    parser_report.add_argument('--user', required=True, help='User to fetch report about.')

    parser_fill = subparsers.add_parser('fillUSOSReport', help='Fill spreadsheet for USOS')
    parser_fill.add_argument('--db', type=Path, required=True, help='Database file to fetch results from.')
    parser_fill.add_argument('--inp', type=Path, required=True, help='CSV file to fill')
    parser_fill.add_argument('--out', type=Path, required=True, help='Output file')

    parser_fill = subparsers.add_parser('plot', help='Show histogram of results')
    parser_fill.add_argument('--db', type=Path, required=True, help='Database file to fetch results from.')

    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    
    args = parser.parse_args()

    if args.command == 'simple':
        tester = Tester(tests_list)
        p = args.dir.resolve()
        if not p.is_dir():
            logError('Path must point to a directory')
            sys.exit(1)
        solution = Solution(p)
        solution.name = p.name
        solution.env_path = Path('env')
        solution.unpacked_path = p
        solution.build()
        tester.run_tests(solution)
        report_str = solution.get_report().report_to_string()
        logInfo(report_str)
    elif args.command == 'grade':
        db = ReportDB(args.db)
        db.initdb()
        grade_all(args.dir, db)

    elif args.command == 'continue':
        logInfo('Continuing grading...')
        db = ReportDB(args.db)
        grade_all(args.dir, db)

    elif args.command == 'report':
        logInfo(f'Printing report for {args.user}')
        db = ReportDB(args.db)
        report = db.get_report(args.user)
        if report is None:
            logError(f'Cant find report for {args.user}')
        logInfo(report.report_to_string())
    
    elif args.command == 'fillUSOSReport':
        db = ReportDB(args.db)
        reports_list = db.get_all_reports()
        reports = {}
        for r in reports_list:
            reports[r.name[2:]] = r
        ifile = csv.reader(open(args.inp, 'r', newline=''), delimiter=';')
        ofile = csv.writer(open(args.out, 'w', newline=''), delimiter=';')
        for row in ifile:
            if row[0] == 'os_id':
                ofile.writerow(row)
                continue
            name = row[1]
            surname = row[2]
            if row[3] not in reports:
                logInfo(f'Report not found for {name} {surname} ({row[3]})')
                ofile.writerow(row)
                continue
            r = reports[row[3]]
            rname, rsurname = re.fullmatch(r'(.+) (.+)_\d+_assignsubmission_file_', Path(r.dirname).name).group(1, 2)
            if not (name == rname and rsurname == surname):
                logError(f'Invalid name for {row[3]}. In report: {rname} {rsurname}, in document: {name} {surname}')
                def correct_choice(inp: str):
                    return inp.lower() in ['y', 'n']
                choice = read_until_correct('Continue? y/n: ', correct_choice)
                if choice.lower() == 'n':
                    sys.exit(1)
            points, _ = r.calculate_points()
            row[4] = points
            row[5] = f'Testy: {points}/{max_points}'
            ofile.writerow(row)
    
    elif args.command == 'plot':
        db = ReportDB(args.db)
        reports = db.get_all_reports()
        reports = sorted(reports, key=lambda r: r.calculate_points())
        results = []
        for report in reports:
            results.append(report.calculate_points()[0])
        
        for report in reports:
            score, good_cnt = report.calculate_points()
            print(f'{report.name}: {score}, tests: {good_cnt}')
        logInfo(f'avg: {sum(results)/len(results)}')
        plt.hist(results, bins=np.arange (0, 8, 0.399999), range=(0, 8))
        plt.savefig('plot.png')
        logInfo('Saved histogram to plot.png')
        

# ============================================
# ======== Helper functions for tests ========
# ============================================

def parse_correlated_servers(filename: Path) -> List[Tuple[str, str]]:
    with filename.open('r') as f:
        lines = f.readlines()
    parsed = []
    for line in lines:
        line = line.strip()
        spl = line.split('\t')
        parsed.append((spl[0], f'http://{spl[1]}:{spl[2]}{spl[0]}'))
    return parsed

def send_request(srv: Popen, sock: socket.socket, target: str, method: str, headers: Dict[str, str] = {}, user_agent: bool=True):
    if user_agent:
        headers['User-Agent'] = 'SIK-tests'
    headers_str = ''.join([f'{k}: {v}\r\n' for k, v in headers.items()])
    request_str = f'{method} {target} HTTP/1.1\r\n{headers_str}\r\n'
    send(srv, sock, request_str)

def receive_response(srv: Popen, sock: socket.socket, head: bool=False, allowed: List[int]=[200, 302, 400, 404, 500, 501]):
    lines = read_server_response_headers(srv, sock)
    ok, why, response_len, headers = check_server_response(lines, allowed)
    if not ok:
        raise TestFailedException("Bad response: " + why)
    data = b''
    if not head and response_len > 0:
        data = read_server_response_bytes(srv, sock, response_len)
        
    return response_len, headers, data

def try_existing_file(srv: Popen, sock: socket.socket, 
                      target: str, filename: Path, 
                      head: bool=False, headers: Dict[str, str]={}, skip_send: bool=False):
    method = 'GET' if not head else 'HEAD'
    if not skip_send:
        send_request(srv, sock, target, method, headers)
    response_len, headers, payload = receive_response(srv, sock, head, [200])

    with open(filename, 'rb') as f:
        data = f.read()
    if response_len != len(data):
        raise TestFailedException(f'Bad response content-length. Received {str(response_len)}, expected {len(data)}')
    if not head and not payload == data:
        raise TestFailedException("Bad payload")
    
    content_type = headers.get('content-type')
    if content_type is None or content_type.find("/") == -1:
        current_solution.get_report().add_penalty('wrong_content_type', wrong_content_type, '200 response should contain acceptable Content-Type header')
    return response_len, headers, payload

def try_redirected_file(srv: Popen, sock: socket.socket, 
                        target: str, loc: str, 
                        head: bool=False, headers: Dict[str, str]={}):
    method = 'GET' if not head else 'HEAD'
    send_request(srv, sock, target, method, headers)
    response_len, headers, payload = receive_response(srv, sock, head, [302])

    if not headers.get('location') == loc:
        current_solution.get_report().add_penalty('wrong_location_header', wrong_location_header, 'Location header has incorrect value or is not present')
    
    return response_len, headers, payload

def try_missing_file(srv: Popen, sock: socket.socket, target: str, head: bool=False, headers: Dict[str, str]={}):
    method = 'GET' if not head else 'HEAD'
    send_request(srv, sock, target, method, headers)
    response_len, headers, payload = receive_response(srv, sock, head, [404])
    
    return response_len, headers, payload

def try_any_response(srv: Popen, sock: socket.socket, 
                    target: str, head: bool=False, 
                    headers: Dict[str, str]={}, allowed: List[int]=[200, 302, 400, 404, 500, 501]):
    method = 'GET' if not head else 'HEAD'
    send_request(srv, sock, target, method, headers)
    response_len, headers, payload = receive_response(srv, sock, head, allowed)
    
    return response_len, headers, payload

# Returns random string of hexadecimal characters with len 2 * n
def random_string(n: int) -> str:
    return binascii.hexlify(os.urandom(n)).decode()

def reset_global_buffer():
    global read_response_buffer
    read_response_buffer = b''

# =======================================
# ============== Tests ==================
# =======================================

def test_no_args(srv_path, sol):
    '''If you ran ./serwer without args, it should terminate with EXIT_FAILURE exit code.
    '''
    try:
        srv = Popen([str(srv_path)], stdout=PIPE, stderr=STDOUT)
    except:
        return False, 'Failed to run server binary', b'', -1
    try :
        out, _ = srv.communicate(b'', timeout = startup_wait_quantum * 3)
    except TimeoutExpired as e:
        stop_server(srv)
        out, code = get_server_output_and_exit_code(srv)
        return False, 'Server is running without args (expected EXIT_FAILURE)', out, code
    code = srv.poll()
    if not code in [EXIT_FAILURE, EXIT_SUCCESS]:
        return False, f'Invalid return code (expected EXIT_FAILURE or EXIT_SUCCESS, got {code})', out, code
    return True, 'OK', out, code

def test_empty_file(sol, srv, port):
    '''Server shouldn't crash when correlated servers file is empty
    '''
    if not is_server_running(srv):
        raise TestFailedException('Server crashed with empty file')


def test_200_on_found(sol, srv, port):
    '''Tests if server correctly returns existing file.
    - Syntatically correct HTTP response
    - Status code 200
    - Correct Content-length
    - Correct file data
    - Content-type header present

    Returns nothing on success, raises exception on error.'''
    sock = connect(srv, port)
    try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data')

def test_302_on_redirect(sol, srv, port):
    '''Tests if server finds correlated resource and returns proper redirect
    - Syntatically correct HTTP response
    - Status code 302
    - Location header present and has correct value'''

    sock = connect(srv, port)
    parsed_resources = parse_correlated_servers(sol.env_path/'resources')
    requested_resource = parsed_resources[10]
    try_redirected_file(srv, sock, *requested_resource)

def test_404_on_nonexisting(sol, srv, port):
    '''Tests if server returns 404 if file doesn't exist
    - Syntatically correct HTTP response
    - Status code 404'''

    sock = connect(srv, port)
    try_missing_file(srv, sock, '/nosuchfile.txt')

def test_multiple_existing(sol, srv, port):
    '''Tests if server handles multiple queries for existing files on the same connection
    - Each request is handled correctly
    - Server doesn't close connection
    - No Connection: close header in response'''
    sock = connect(srv, port)
    for i in range(1, 65):
        _, headers, _ = try_existing_file(srv, sock, f'/{i}.data', sol.env_path/'data'/f'{i}.data')

def test_multiple_mixed(sol, srv, port):
    '''Tests if server handles multiple queries 
    for existing / correlated / non-existing files on the same connection
    - Each request is handled correctly
    - Server doesn't close connection
    - No Connection: close header in response'''
    sock = connect(srv, port)
    parsed_resources = parse_correlated_servers(sol.env_path/'resources')
    random.seed(1337)
    for i in range(30):
        r = random.randint(0, 2)
        idx = random.randint(1, 64)
        if r == 0:
            _, headers, _ = try_existing_file(srv, sock, f'/{idx}.data', sol.env_path/'data'/f'{idx}.data')
        elif r == 1:
            _, headers, _ = try_redirected_file(srv, sock, *parsed_resources[idx - 1])
        elif r == 2:
            _, headers, _ = try_missing_file(srv, sock, f'/nosuchfile_{idx}.data')

def test_head_mixed(sol, srv, port):
    '''Tests if server handles multiple HEAD queries 
    for existing / correlated / non-existing files on the same connection
    - Each request is handled correctly
    - Content-length is correct
    - Content-type sent
    - No body is sent
    - Server doesn't close connectionfillUSOSReport
    - No Connection: close header in response'''
    sock = connect(srv, port)
    parsed_resources = parse_correlated_servers(sol.env_path/'resources')
    random.seed(1337)
    for i in range(60):
        r = random.randint(0, 2)
        idx = random.randint(1, 64)
        if r == 0:
            _, headers, _ = try_existing_file(srv, sock, f'/{idx}.data', sol.env_path/'data'/f'{idx}.data', head=True)
        elif r == 1:
            _, headers, _ = try_redirected_file(srv, sock, *parsed_resources[idx - 1], head=True)
        elif r == 2:
            _, headers, _ = try_missing_file(srv, sock, f'/nosuchfile_{idx}.data', head=True)

def test_get_head_mixed(sol, srv, port):
    '''Tests if server handles multiple GET / HEAD queries 
    for existing / correlated / non-existing files on the same connection
    - See previous tests for details'''
    sock = connect(srv, port)
    parsed_resources = parse_correlated_servers(sol.env_path/'resources')
    random.seed(1337)
    for i in range(60):
        r = random.randint(0, 2)
        idx = random.randint(1, 64)
        head = random.getrandbits(1)
        if r == 0:
            _, headers, _ = try_existing_file(srv, sock, f'/{idx}.data', sol.env_path/'data'/f'{idx}.data', head=head)
        elif r == 1:
            _, headers, _ = try_redirected_file(srv, sock, *parsed_resources[idx - 1], head=head)
        elif r == 2:
            _, headers, _ = try_missing_file(srv, sock, f'/nosuchfile_{idx}.data', head=head)

def test_closing(sol, srv, port):
    '''Tests if server closes connection on invalid request 
    or when client sends Connection: close'''
    sock = connect(srv, port)
    send(srv, sock, 'aaaaaaaaa\r\n\r\n')
    _ = receive_response(srv, sock, head=False, allowed=[400])
    if not len(recv(srv, sock)) == 0:
        raise TestFailedException('Server should close connection on error 400')
    sock.close()

    reset_global_buffer()
    sock = connect(srv, port)
    _, headers, _ = try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data', headers={'Connection': 'close'})
    if not len(recv(srv, sock)) == 0:
        raise TestFailedException('Server should close connection when client requested it')

def test_repeated_headers(sol, srv, port):
    '''Tests if server detects repeated non-ignored headers, and responds with error 400.
    Tests if the above detection is case-insensitive.'''
    sock = connect(srv, port)
    request_1 = '''\
GET /32.data HTTP/1.1\r\n\
Connection: close\r\n\
Connection: close\r\n\
\r\n\
'''
    send(srv, sock, request_1)
    try:
        _ = receive_response(srv, sock, False, [400])
    except TestFailedException as e:
        raise TestFailedException('Error during testing repeated headers (same case): ' + e.msg)
    sock.close()

    reset_global_buffer()
    sock = connect(srv, port)
    request_2 = '''\
GET /33.data HTTP/1.1\r\n\
ConNeCtiOn: close\r\n\
Connection: close\r\n\
\r\n\
'''
    send(srv, sock, request_1)
    try:
        _ = receive_response(srv, sock, False, [400])
    except TestFailedException as e:
        raise TestFailedException('Error during testing repeated headers (different case): ' + e.msg)
    sock.close()

    # Check if server still works
    reset_global_buffer()
    sock = connect(srv, port)
    try:
        try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data')
    except TestFailedException as e:
        raise TestFailedException('Error during testing repeated headers (sanity check after): ' + e.msg)
    

def test_connection_case_insensitive(sol, srv, port):
    '''Tests if Connection header is properly recognized case-insensitive, 
    and results in server closing the connection'''
    sock = connect(srv, port)
    _, headers, _ = try_existing_file(srv, sock, '/32.data', sol.env_path/'data'/'32.data', headers={'CONNECTION': 'close'})
    if not len(recv(srv, sock)) == 0:
        raise TestFailedException('Server should close connection on Connection: close')
    sock.close()
    
    reset_global_buffer()
    sock = connect(srv, port)
    _, headers, _ = try_existing_file(srv, sock, '/33.data', sol.env_path/'data'/'33.data', headers={'coNnEctIon': 'close'})
    if not len(recv(srv, sock)) == 0:
        raise TestFailedException('Server should close connection on Connection: close (case insensitive)')
    
def test_create_delete_file(sol, srv, port):
    '''Tests if server properly recognizes that file was created/deleted while server is running.'''
    sock = connect(srv, port)
    random.seed(123456789)
    for i in range(20):
        file_present = random.getrandbits(1)
        file_length = random.randint(10, 16384)
        try_remove(sol.env_path/'data'/'tmpfile.data')
        if file_present:
            with (sol.env_path/'data'/'tmpfile.data').open('wb') as f:
                f.write(os.urandom(file_length))
            try_existing_file(srv, sock, '/tmpfile.data', sol.env_path/'data'/'tmpfile.data')
        else:
            try_missing_file(srv, sock, '/tmpfile.data')
    try_remove(sol.env_path/'data'/'tmpfile.data')

def test_big_file(sol, srv, port):
    '''Big file should be correctly received.
    It should not be terribly slow.
    '''
    global read_response_buffer
    sock = connect(srv, port)
    send(srv, sock, f'GET /bigfile.data HTTP/1.1\r\n\r\n')
    response_len, headers, payload = receive_response(srv, sock, True, [200])
    if not response_len == os.stat(sol.env_path/'data'/'bigfile.data').st_size == big_file_size:
        raise TestFailedException('Invalid file length')

    f = (sol.env_path/'data'/'bigfile.data').open('rb')
    read_size = 2 ** 20
    left_to_read = response_len
    total = 0
    start = time.time()
    # There may have been some data left in global buffer
    fdata = f.read(len(read_response_buffer))
    if not len(fdata) == len(read_response_buffer):
        logError('INVALID SIZE OF ARRAY - PARTIAL READ FROM FILE?!')
        sys.exit(1)
    if not fdata == read_response_buffer:
        raise TestFailedException('Invalid file data')
    read_response_buffer = b''
    left_to_read -= len(fdata)
    # Now read file data from socket
    while left_to_read > 0:
        sdata = recv(srv, sock, min(read_size, left_to_read))
        fdata = f.read(len(sdata))
        if not len(fdata) == len(sdata):
            logError('INVALID SIZE OF ARRAY - PARTIAL READ FROM FILE?!')
            sys.exit(1)
        if not fdata == sdata:
            raise TestFailedException('Invalid file data')
        left_to_read -= len(sdata)
        total += len(sdata)
        end = time.time()
        if (end - start > 1):
            raise TestFailedException('Sending file took too long')
    print(f'finished in {round(time.time() - start, 3)}s, ', end='')

    # Check if the server is still correctly working (didn't send us more data than it should)
    try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data')
    

def test_big_queries(sol, srv, port):
    '''Tests if server handles big queries correctly.
    Queries within limits set in tasks should return normal response.
    Larger shouldn't crash server.'''
    MAX = 2 ** 12
    sock = connect(srv, port)
    
    # Test a lot of headers
    headers = {}
    for i in range(30):
        headers[random_string(8)] = random_string(8)
    try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data', headers=headers)

    # Test big headers
    headers = {}
    for i in range(5):
        headers[random_string(8)] = random_string(MAX)
    try_existing_file(srv, sock, '/63.data', sol.env_path/'data'/'63.data', headers=headers)

    # Test big path
    try_rmdir(sol.env_path/'data'/'tmpdir')
    (sol.env_path/'data'/'tmpdir').mkdir()
    fpath = '/tmpdir/..' * 300 + '/62.data'
    try_existing_file(srv, sock, fpath, sol.env_path/'data'/fpath[1:], headers={'Connection': 'close'})
    sock.close()
    try_rmdir(sol.env_path/'data'/'tmpdir')

    # Try really big queries - 400 can be returned, or client can be dropped, but server shouldn't crash.

    # Test a lot of headers
    reset_global_buffer()
    sock = connect(srv, port)
    headers = {'Connection': 'close'}
    for i in range(20000):
        headers[random_string(8)] = random_string(8)
    try:
        try_any_response(srv, sock, f'/61.data', headers=headers, allowed=[200, 400, 500])
    except (ConnectionResetError, socket.timeout):
        pass

    # Test big headers
    reset_global_buffer()
    sock = connect(srv, port)
    headers = {'Connection': 'close'}
    for i in range(5):
        headers[random_string(8)] = random_string(MAX * 10)
    try:
        try_any_response(srv, sock, f'/60.data', headers=headers, allowed=[200, 400, 500])
    except (ConnectionResetError, socket.timeout):
        pass

    # Test big path
    try_rmdir(sol.env_path/'data'/'tmpdir')
    (sol.env_path/'data'/'tmpdir').mkdir()
    fpath = '/tmpdir/..' * 5000 + '/59.data'
    reset_global_buffer()
    sock = connect(srv, port)
    try:
        try_any_response(srv, sock, fpath, headers={'Connection': 'close'}, allowed=[200, 400, 404, 500])
    except (ConnectionResetError, socket.timeout):
        pass
    try_rmdir(sol.env_path/'data'/'tmpdir')

    # Check if server still works
    reset_global_buffer()
    sock = connect(srv, port)
    try_existing_file(srv, sock, '/58.data', sol.env_path/'data'/'58.data', headers={'Connection': 'close'})

def test_fragmented_query(sol, srv, port):
    '''Tests if server correctly supports multiple queries in 1 write, or 1 query in multiple writes'''
    sock = connect(srv, port)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    # Multiple queries at once
    queries_num = 3
    payload = 'GET /64.data HTTP/1.1\r\n\r\n' * queries_num
    send(srv, sock, payload)
    for i in range(queries_num):
        try:
            try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data', skip_send=True)
        except TestFailedException as e:
            raise TestFailedException('Exception during testing multiple queries in 1 write: ' + e.msg)
    
    # One query in multiple writes
    random.seed(345)
    payload = 'GET /8.data HTTP/1.1\r\nabra: kadabra\r\n\r\n'
    for i in range(100):
        index = 0
        while index < len(payload):
            r = random.randint(2, 5)
            fragment = payload[index : index + r]
            send(srv, sock, fragment)
            index += r
        try:
            try_existing_file(srv, sock, '/8.data', sol.env_path/'data'/'8.data', skip_send=True)
        except TestFailedException as e:
            raise TestFailedException('Exception during testing 1 query in multiple writes: ' + e.msg)


def test_protocol_handling(sol, srv, port):
    '''Test if server correctly detects some errors in messages'''
    def test_error_for_request(request, allowed=[400]):
        sock = connect(srv, port)
        send(srv, sock, request)
        response_len, headers, payload = receive_response(srv, sock, False, allowed)
        sock.close()
    
    # space before ':' in header
    test_error_for_request('GET /64.data HTTP/1.1\r\nabra : kadabra\r\nConnection: close\r\n\r\n')

    # CR replaced with space, or nothing - in 3 places
    test_error_for_request('GET /63.data HTTP/1.1 \nConnection: close\r\n\r\n')
    test_error_for_request('GET /62.data HTTP/1.1\nConnection: close\r\n\r\n')
    test_error_for_request('GET /61.data HTTP/1.1\r\nConnection: close \n\r\n\r\n\r\n', allowed=[200, 400])
    test_error_for_request('GET /60.data HTTP/1.1\r\nConnection: close\n\r\n\r\n\r\n', allowed=[200, 400])
    test_error_for_request('GET /59.data HTTP/1.1\r\nConnection: close\r\n \n\r\n\r\n')
    test_error_for_request('GET /58.data HTTP/1.1\r\nConnection: close\r\n\n\r\n\r\n')

    # NULL char in various points of request
    test_error_for_request('GET\0 /57.data HTTP/1.1\r\nConnection: close\r\n\r\n', allowed=[400, 501])
    test_error_for_request('GET /56.data\0HTTP/1.1\r\nConnection: close\r\n\r\n')
    test_error_for_request('GET /55.data HTTP\0/1.1\r\nConnection: close\r\n\r\n')
    # test_error_for_request('GET /64.data HTTP/1.1\r\nConnection: close\r\nC\0onnection: close\r\n\r\n')

def test_access_outside(sol, srv, port):
    '''Tests if server blocks access outside of working directory'''
    sock = connect(srv, port)
    try_missing_file(srv, sock, '/../../../../../../../../../etc/passwd')
    try_missing_file(srv, sock, '/....//....//....//....//....//....//....//....//etc/passwd')
    try_missing_file(srv, sock, '/./.././.././.././.././.././.././.././../etc/passwd')
    try_missing_file(srv, sock, '/./....//./....//./....//./....//./....//./....//./....//./....//etc/passwd')

def test_client_disconnected_recv(sol, srv, port):
    for i in range(3):
        reset_global_buffer()
        sock = connect(srv, port)
        send(srv, sock, f'GET /bigfile.data HTTP/1.1\r\n\r\n')

        response_len, headers, payload = receive_response(srv, sock, True, [200])

        _ = recv(srv, sock, max_size=10000)
        sock.close()
    # Check if the server is still correctly working
    reset_global_buffer()
    sock = connect(srv, port)
    try_existing_file(srv, sock, '/64.data', sol.env_path/'data'/'64.data')

def test_method_names(sol, srv, port):
    sock = connect(srv, port)
    send(srv, sock, f'gEt /34.data HTTP/1.1\r\nConnection: close\r\n\r\n')
    response_len, headers, payload = receive_response(srv, sock, False, [405, 501])
    sock.close()

    reset_global_buffer()
    sock = connect(srv, port)
    send(srv, sock, f'heaD /35.data HTTP/1.1\r\nConnection: close\r\n\r\n')
    response_len, headers, payload = receive_response(srv, sock, False, [405, 501])
    sock.close()

    reset_global_buffer()
    sock = connect(srv, port)
    send(srv, sock, f'asdasdas /36.data HTTP/1.1\r\nConnection: close\r\n\r\n')
    response_len, headers, payload = receive_response(srv, sock, False, [405, 501])
    sock.close()

    reset_global_buffer()
    sock = connect(srv, port)
    send(srv, sock, f'DFSDF /37.data HTTP/1.1\r\nConnection: close\r\n\r\n')
    response_len, headers, payload = receive_response(srv, sock, False, [405, 501])
    sock.close()

tests_list = [
    (test_no_args, False, [], 0.05),
    (test_empty_file, True, ['%p/data', '%p/empty_resources'], 0.05),
    (test_200_on_found, True, ["%p/data", "%p/resources"], 0.05),
    (test_302_on_redirect, True, ["%p/data", "%p/resources"], 0.05),
    (test_404_on_nonexisting, True, ["%p/data", "%p/resources"], 0.05),
    (test_multiple_existing, True, ["%p/data", "%p/resources"], 0.05),
    (test_multiple_mixed, True, ["%p/data", "%p/resources"], 0.05),
    (test_head_mixed, True, ["%p/data", "%p/resources"], 0.05),
    (test_get_head_mixed, True, ["%p/data", "%p/resources"], 0.05),
    (test_closing, True, ["%p/data", "%p/resources"], 0.05),
    (test_repeated_headers, True, ["%p/data", "%p/resources"], 0.05),
    (test_connection_case_insensitive, True, ["%p/data", "%p/resources"], 0.05),
    (test_create_delete_file, True, ["%p/data", "%p/resources"], 0.05),
    (test_big_file, True, ["%p/data", "%p/resources"], 0.05),
    (test_big_queries, True, ["%p/data", "%p/resources"], 0.05),
    (test_fragmented_query, True, ["%p/data", "%p/resources"], 0.05),
    (test_protocol_handling, True, ["%p/data", "%p/resources"], 0.05),
    (test_access_outside, True, ["%p/data", "%p/resources"], 0.05),
    (test_client_disconnected_recv, True, ["%p/data", "%p/resources"], 0.05),
    (test_method_names, True, ["%p/data", "%p/resources"], 0.05),
]

if __name__ == "__main__":
    main()
