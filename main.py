"""
Deutsche Telekom Tariff Simulator
--------------------------------
Main entry point for the Deutsche Telekom Tariff Simulator application.
This file imports and runs the Flask application from the web module.
"""

import os
from src.web.app import app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', '1') == '1'
    
    print(f"Starting Deutsche Telekom Tariff Simulator on {host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
