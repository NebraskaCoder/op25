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
import threading
from flask import Flask, Response, request, send_from_directory
import queue
from flask_cors import CORS

my_input_q = None
my_output_q = None
my_port = None

# SSE connection management
sse_clients = set()
sse_clients_lock = threading.Lock()

"""
fake http and ajax server module
TODO: make less fake
"""

class http_server(object):
    def __init__(self, input_q, output_q, endpoint, **kwds):
        global my_input_q, my_output_q, my_port
        host, port = endpoint.split(':')
        my_input_q = input_q  # This is ui_out_q from multi_rx.py
        my_output_q = output_q
        my_port = int(port)
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for all routes
        self._setup_routes()
        self.keep_running = True
        self.sse_queue = queue.Queue()
        self.sse_thread = threading.Thread(target=self._sse_queue_watcher, daemon=True)
        self.sse_thread.start()
        self.flask_thread = threading.Thread(target=self._run_flask, daemon=True)
        self.flask_thread.start()
        # Start a watcher to broadcast SSE events from my_input_q
        self.q_watcher = threading.Thread(target=self._input_q_watcher, daemon=True)
        self.q_watcher.start()

    def _setup_routes(self):
        app = self.app
        
        @app.route('/', defaults={'path': ''})
        @app.route('/<path:path>')
        def static_files(path):
            # Serve static files from www-static for root-level requests
            if path == '' or path == 'index.html':
                return send_from_directory('../www/www-static', 'index.html')
            elif path.startswith('images/'):
                return send_from_directory('../www/images', path[len('images/'):])
            else:
                # Try www-static first, fallback to 404 if not found
                static_dir = '../www/www-static'
                file_path = os.path.join(static_dir, path)
                if os.path.isfile(file_path):
                    return send_from_directory(static_dir, path)
                return ("Not Found", 404)

        @app.route('/events')
        def sse():
            def event_stream():
                q = queue.Queue()
                with sse_clients_lock:
                    sse_clients.add(q)
                # Send initial connection event
                init_event = json.dumps({"event": "connection", "message": "SSE connection established"})
                yield f"data: {init_event}\n\n"
                try:
                    while True:
                        data = q.get()
                        yield f"data: {data}\n\n"
                except GeneratorExit:
                    pass
                finally:
                    with sse_clients_lock:
                        sse_clients.discard(q)
            return Response(event_stream(), mimetype='text/event-stream')

        @app.route('/', methods=['POST'])
        def post_root():
            return self._handle_post()

    def _handle_post(self):
        global my_input_q, my_output_q
        try:
            data = request.get_json(force=True)
            print("HTTP POST received:", data)
            for d in data:
                msg = self._make_gr_message(d)
                if hasattr(my_output_q, 'full_p'):
                    if not my_output_q.full_p():
                        my_output_q.insert_tail(msg)
                else:
                    my_output_q.put(msg)
            time.sleep(0.2)
        except Exception as e:
            sys.stderr.write(f'post_req: error processing input: {e}\n')
        resp_msg = []
        # Drain my_input_q for responses using GNU Radio msg_queue methods
        while True:
            try:
                if not my_input_q.empty_p():
                    msg = my_input_q.delete_head()
                else:
                    break
                if hasattr(msg, 'type') and msg.type() == -4:
                    resp_msg.append(json.loads(msg.to_string()))
                elif isinstance(msg, dict):
                    resp_msg.append(msg)
            except Exception:
                break
        return Response(json.dumps(resp_msg), mimetype='application/json')

    def _make_gr_message(self, d):
        from gnuradio import gr
        return gr.message().make_from_string(str(d['command']), -2, d['arg1'], d['arg2'])

    def _run_flask(self):
        self.app.run(host='0.0.0.0', port=my_port, threaded=True, use_reloader=False)

    def _input_q_watcher(self):
        global my_input_q
        while self.keep_running:
            try:
                if hasattr(my_input_q, 'empty_p'):
                    if not my_input_q.empty_p():
                        msg = my_input_q.delete_head()
                        print("[DEBUG] http_server: got msg from queue:", getattr(msg, 'to_string', lambda: str(msg))())
                        self._broadcast_sse(msg)
                    else:
                        time.sleep(0.01)
                else:
                    msg = my_input_q.get(timeout=0.1)
                    print("[DEBUG] http_server: got msg from queue (no empty_p):", getattr(msg, 'to_string', lambda: str(msg))())
                    self._broadcast_sse(msg)
            except Exception:
                time.sleep(0.01)

    def _broadcast_sse(self, msg):
        # Only broadcast JSON messages
        try:
            if hasattr(msg, 'type') and msg.type() == -4:
                data = json.loads(msg.to_string())
                print("[DEBUG] http_server: broadcasting SSE event:", data)
                event_type = None
                if isinstance(data, dict) and 'json_type' in data:
                    jt = data['json_type']
                    if jt == 'rx_update':
                        event_type = 'frequency_update'
                    elif jt == 'call_log':
                        event_type = 'call_log'
                    elif jt == 'channel_update':
                        event_type = 'channel_status'
                    elif jt == 'plot':
                        event_type = 'plot_update'
                    elif jt == 'trunk_update':
                        event_type = 'trunk_update'
                if event_type:
                    sse_data = json.dumps({"event": event_type, "data": data})
                    with sse_clients_lock:
                        for q in list(sse_clients):
                            try:
                                q.put_nowait(sse_data)
                            except queue.Full:
                                pass
        except Exception:
            pass

    def _sse_queue_watcher(self):
        # Not used, but placeholder for future expansion
        while self.keep_running:
            time.sleep(1)

    def run(self):
        # Provided for compatibility; Flask runs in its own thread
        pass
