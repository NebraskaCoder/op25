# Server-Sent Events (SSE) Implementation for OP25

## Overview

This implementation adds real-time updates to the OP25 web interface using Server-Sent Events (SSE). Instead of polling the server every second, the browser now receives immediate updates when events occur.

## Features

- **Real-time Updates**: Immediate updates for frequency changes, call logs, channel status, and plot updates
- **Automatic Fallback**: Falls back to polling if SSE fails or is disabled
- **Connection Management**: Automatic reconnection with exponential backoff
- **User Control**: Toggle SSE on/off in the settings
- **Backward Compatibility**: Works with existing OP25 installations

## How It Works

### Backend Changes

1. **New SSE Endpoint**: `/events` endpoint for Server-Sent Events
2. **Event Broadcasting**: Messages from the GNU Radio message queue are automatically broadcast to all connected SSE clients
3. **Connection Pool**: Manages multiple SSE connections with proper cleanup

### Frontend Changes

1. **EventSource**: Replaces polling with EventSource for real-time updates
2. **Event Handling**: Processes different event types (frequency_update, call_log, etc.)
3. **Fallback Mechanism**: Automatically falls back to polling if SSE fails
4. **Settings Integration**: SSE can be enabled/disabled in the UI settings

## Event Types

The following event types are supported:

- `frequency_update`: Real-time frequency and tuning changes
- `call_log`: New calls as they happen
- `channel_status`: Channel state changes
- `plot_update`: New plot images
- `trunk_update`: Trunking system updates

## Configuration

### Enable/Disable SSE

1. Open the OP25 web interface
2. Click "Settings" in the top navigation
3. Check/uncheck "Enable Real-time Updates (SSE)"
4. The setting is automatically saved to your browser

### Server Configuration

No additional server configuration is required. SSE is automatically enabled when using the HTTP terminal type.

## Testing

A test script is provided to verify SSE functionality:

```bash
cd op25/gr-op25_repeater/apps
python3 test_sse.py
```

This script simulates OP25 events and broadcasts them via SSE.

## Browser Support

SSE is supported in all modern browsers:

- Chrome 6+
- Firefox 6+
- Safari 5+
- Edge 12+

## Troubleshooting

### SSE Not Working

1. Check browser console for errors
2. Verify the server is running with HTTP terminal type
3. Check if SSE is enabled in settings
4. Look for "Real-time updates disabled" warning

### Fallback to Polling

If SSE fails, the interface automatically falls back to polling mode. You'll see a warning message indicating this.

### Connection Issues

- SSE connections are automatically reconnected with exponential backoff
- After 5 failed attempts, it falls back to polling
- Check server logs for connection information

## Performance Benefits

- **Reduced Server Load**: No more 1-second polling intervals
- **Lower Latency**: Immediate updates instead of 1-second delays
- **Better Resource Usage**: Persistent connections instead of repeated HTTP requests
- **Real-time Experience**: Events appear as they happen

## Technical Details

### Message Flow

1. OP25 processes data and sends messages to GNU Radio message queue
2. `process_qmsg()` in `http_server.py` receives messages
3. Messages are broadcast to all connected SSE clients
4. Browser receives events and updates UI immediately

### Connection Management

- SSE connections are stored in `sse_connections` list
- Thread-safe operations using `sse_lock`
- Automatic cleanup of closed connections
- Keepalive messages every second

### Error Handling

- Automatic reconnection with exponential backoff
- Graceful fallback to polling
- User notification of connection status
- Console logging for debugging

## Future Enhancements

Potential improvements for future versions:

1. **WebSocket Support**: For bidirectional communication
2. **Event Filtering**: Allow clients to subscribe to specific event types
3. **Compression**: Gzip compression for large events
4. **Authentication**: Secure SSE connections
5. **Metrics**: Connection statistics and monitoring

## Files Modified

- `http_server.py`: Added SSE endpoint and broadcasting
- `main.js`: Added EventSource client and event handling
- `index.html`: Added SSE toggle in settings
- `test_sse.py`: Test script for SSE functionality

## License

This implementation is part of OP25 and is licensed under the GNU General Public License v3.
