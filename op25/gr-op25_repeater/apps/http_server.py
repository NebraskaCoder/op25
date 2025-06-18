# Copyright 2017, 2018 Max H. Parke KA1RBI
# 
# This file is part of OP25
# 
# OP25 is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# OP25 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
# License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with OP25; see the file COPYING. If not, write to the Free
# Software Foundation, Inc., 51 Franklin Street, Boston, MA
# 02110-1301, USA.

import sys
import os
import time
import re
import json
import socket
import traceback
import threading

from gnuradio import gr
from waitress.server import create_server

import gnuradio.op25_repeater as op25_repeater

my_input_q = None
my_output_q = None
my_recv_q = None
my_port = None

# SSE connection management
sse_connections = []
sse_lock = threading.Lock()

"""
fake http and ajax server module
TODO: make less fake
"""

def static_file(environ, start_response):
    content_types = { 'png': 'image/png', 'jpeg': 'image/jpeg', 'jpg': 'image/jpeg', 'gif': 'image/gif', 'css': 'text/css', 'js': 'application/javascript', 'html': 'text/html', 'ico' : 'image/x-icon'}
    img_types = 'png jpg jpeg gif'.split()
    if environ['PATH_INFO'] == '/':
        filename = 'index.html'
    else:
        filename = re.sub(r'[^a-zA-Z0-9_.\-]', '', environ['PATH_INFO'])
    suf = filename.split('.')[-1]
    pathname = '../www/www-static'
    if suf in img_types:
        pathname = '../www/images'
    pathname = '%s/%s' % (pathname, filename)
    if suf not in list(content_types.keys()) or '..' in filename or not os.access(pathname, os.R_OK):
        sys.stderr.write('404 %s\n' % pathname)
        status = '404 NOT FOUND'
        content_type = 'text/plain'
        output = status
    else:
        output = open(pathname, 'rb').read()
        content_type = content_types[suf]
        status = '200 OK'
    return status, content_type, output

def sse_endpoint(environ, start_response):
    """Server-Sent Events endpoint for real-time updates"""
    if environ['REQUEST_METHOD'] != 'GET':
        status = '405 METHOD NOT ALLOWED'
        content_type = 'text/plain'
        output = 'Only GET requests allowed for SSE'
        response_headers = [('Content-type', content_type),
                           ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output.encode() if sys.version[0] > '2' else output]

    # Set up SSE headers
    response_headers = [
        ('Content-Type', 'text/event-stream'),
        ('Cache-Control', 'no-cache'),
        ('Connection', 'keep-alive'),
        ('Access-Control-Allow-Origin', '*'),
        ('Access-Control-Allow-Headers', 'Cache-Control')
    ]
    start_response('200 OK', response_headers)

    # Create a simple response object that can write SSE data
    class SSEResponse:
        def __init__(self):
            self.closed = False
            self.write = None

    response = SSEResponse()
    
    # Get the write function from the WSGI environment
    if 'wsgi.file_wrapper' in environ:
        response.write = environ['wsgi.file_wrapper'](response, 1024)
    else:
        # Fallback for servers without file_wrapper
        response.write = lambda data: [data]

    # Add connection to the pool
    with sse_lock:
        sse_connections.append(response)
        sys.stderr.write('SSE: New connection added, total connections: %d\n' % len(sse_connections))

    # Send initial connection event
    try:
        initial_event = "data: " + json.dumps({
            "event": "connection",
            "timestamp": time.time(),
            "message": "SSE connection established"
        }) + "\n\n"
        if sys.version[0] > '2':
            initial_event = initial_event.encode()
        yield initial_event
    except:
        pass

    # Keep connection alive and handle cleanup
    try:
        while not response.closed:
            time.sleep(1)
            # Send keepalive comment
            keepalive = ": keepalive\n\n"
            if sys.version[0] > '2':
                keepalive = keepalive.encode()
            yield keepalive
    except:
        pass
    finally:
        # Remove connection from pool
        with sse_lock:
            if response in sse_connections:
                sse_connections.remove(response)
                sys.stderr.write('SSE: Connection removed, total connections: %d\n' % len(sse_connections))

def broadcast_sse_event(event_type, data):
    """Broadcast an SSE event to all connected clients"""
    if not sse_connections:
        return

    event_data = {
        "event": event_type,
        "timestamp": time.time(),
        "data": data
    }
    
    sse_message = "data: " + json.dumps(event_data) + "\n\n"
    if sys.version[0] > '2':
        sse_message = sse_message.encode()

    with sse_lock:
        # Remove closed connections
        sse_connections[:] = [conn for conn in sse_connections if not conn.closed]
        
        # Send to all active connections
        for conn in sse_connections:
            try:
                if hasattr(conn, 'write') and conn.write:
                    conn.write(sse_message)
            except:
                conn.closed = True

def post_req(environ, start_response, postdata):
    global my_input_q, my_output_q, my_recv_q, my_port
    valid_req = False
    try:
        data = json.loads(postdata)
        for d in data:
            msg = gr.message().make_from_string(str(d['command']), -2, d['arg1'], d['arg2'])
            if not my_output_q.full_p():
                my_output_q.insert_tail(msg)
        valid_req = True
        time.sleep(0.2)
    except:
        sys.stderr.write('post_req: error processing input: %s\n%s\n' % (postdata, traceback.format_exc()))

    resp_msg = []
    while not my_recv_q.empty_p():
        msg = my_recv_q.delete_head()
        if msg.type() == -4:
            resp_msg.append(json.loads(msg.to_string()))
    if not valid_req:
        resp_msg = []
    status = '200 OK'
    content_type = 'application/json'
    output = json.dumps(resp_msg)
    return status, content_type, output

def http_request(environ, start_response):
    if environ['REQUEST_METHOD'] == 'GET':
        if environ['PATH_INFO'] == '/events':
            # SSE endpoint
            return sse_endpoint(environ, start_response)
        else:
            # Static file serving
            status, content_type, output = static_file(environ, start_response)
    elif environ['REQUEST_METHOD'] == 'POST':
        postdata = environ['wsgi.input'].read()
        status, content_type, output = post_req(environ, start_response, postdata)
    else:
        status = '200 OK'
        content_type = 'text/plain'
        output = status
        sys.stderr.write('http_request: unexpected input %s\n' % environ['PATH_INFO'])
    
    response_headers = [('Content-type', content_type),
                        ('Content-Length', str(len(output)))]
    start_response(status, response_headers)

    if sys.version[0] > '2':
        if type(output) is str:
            output = output.encode()

    return [output]

def application(environ, start_response):
    failed = False
    try:
        result = http_request(environ, start_response)
    except:
        failed = True
        sys.stderr.write('application: request failed:\n%s\n' % traceback.format_exc())
        sys.exit(1)
    return result

def process_qmsg(msg):
    if my_recv_q.full_p():
        my_recv_q.delete_head_nowait()   # ignores result
    if my_recv_q.full_p():
        return
    if not my_recv_q.full_p():
        my_recv_q.insert_tail(msg)
    
    # Also broadcast SSE events for real-time updates
    try:
        if msg.type() == -4:  # JSON message type
            data = json.loads(msg.to_string())
            if 'json_type' in data:
                # Map message types to SSE events
                event_mapping = {
                    'rx_update': 'frequency_update',
                    'call_log': 'call_log',
                    'channel_update': 'channel_status',
                    'plot': 'plot_update',
                    'trunk_update': 'trunk_update'
                }
                
                event_type = event_mapping.get(data['json_type'])
                if event_type:
                    broadcast_sse_event(event_type, data)
    except:
        # Ignore SSE broadcast errors
        pass

class http_server(object):
    def __init__(self, input_q, output_q, endpoint, **kwds):
        global my_input_q, my_output_q, my_recv_q, my_port
        host, port = endpoint.split(':')
        if my_port is not None:
            raise AssertionError('this server is already active on port %s' % my_port)
        my_input_q = input_q
        my_output_q = output_q
        my_port = int(port)

        my_recv_q = gr.msg_queue(10)
        self.q_watcher = queue_watcher(my_input_q, process_qmsg)

        try:
            self.server = create_server(application, host=host, port=my_port, threads=6)
        except:
            sys.stderr.write('Failed to create http terminal server\n%s\n' % traceback.format_exc())
            sys.exit(1)

    def run(self):
        self.server.run()

class queue_watcher(threading.Thread):
    def __init__(self, msgq,  callback, **kwds):
        threading.Thread.__init__ (self, **kwds)
        self.setDaemon(1)
        self.msgq = msgq
        self.callback = callback
        self.keep_running = True
        self.start()

    def run(self):
        while(self.keep_running):
            if not self.msgq.empty_p(): # check queue before trying to read a message to avoid deadlock at startup
                msg = self.msgq.delete_head()
                if msg is not None:
                    self.callback(msg)
                else:
                    self.keep_running = False
            else: # empty queue
                time.sleep(0.01)
