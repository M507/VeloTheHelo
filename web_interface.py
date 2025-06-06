from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import json
from collector_manager import CollectorManager
from config import Config, init_directories, get_winrm_credentials
import threading
import time
import argparse
import ssl
from OpenSSL import crypto
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import logging

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# Global collector manager instance
collector_manager = None

def load_profiles() -> List[Dict[str, Any]]:
    """Load artifact collection profiles from the profiles directory"""
    profiles = []
    profiles_dir = 'profiles'
    if os.path.exists(profiles_dir):
        for filename in os.listdir(profiles_dir):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(profiles_dir, filename), 'r') as f:
                        profile = json.load(f)
                        profile['id'] = os.path.splitext(filename)[0]
                        profiles.append(profile)
                except Exception as e:
                    print(f"Error loading profile {filename}: {e}")
    return profiles

def get_runtime_stats() -> Dict[str, Any]:
    """Get runtime statistics from the collector manager"""
    if not collector_manager:
        return {
            'artifacts_processed': 0,
            'success_rate': 0,
            'total_execution_time': 0,
            'average_execution_time': 0
        }
    
    stats = collector_manager.get_status()
    successful = len(stats['artifact_stats']['successful'])
    failed = len(stats['artifact_stats']['failed'])
    total = successful + failed
    
    if total > 0:
        success_rate = (successful / total) * 100
        total_time = sum(
            artifact['execution_time'] 
            for artifact in stats['artifact_stats']['successful'] + stats['artifact_stats']['failed']
        )
        avg_time = total_time / total
    else:
        success_rate = 0
        total_time = 0
        avg_time = 0
    
    return {
        'artifacts_processed': total,
        'success_rate': round(success_rate, 2),
        'total_execution_time': round(total_time, 2),
        'average_execution_time': round(avg_time, 2)
    }

@app.route('/')
def index():
    """Render main page with profiles and current status"""
    profiles = load_profiles()
    runtime_stats = get_runtime_stats()
    return render_template(
        'index.html',
        profiles=profiles,
        runtime_stats=runtime_stats
    )

@app.route('/start', methods=['POST'])
def start_processing():
    """Start artifact collection and processing"""
    global collector_manager
    
    if collector_manager and collector_manager.status['processing']:
        return jsonify({
            'error': 'Processing already in progress',
            'current_artifact': collector_manager.status['current_artifact']
        })

    # Get processing parameters
    profile_id = request.form.get('profile')
    build_collectors = request.form.get('build_collectors', 'false').lower() == 'true'
    mode = request.form.get('mode', 'batch')
    host = request.form.get('host')

    # Log the received parameters
    app.logger.info(f"Received processing request - Profile: {profile_id}, Build Collectors: {build_collectors}, Mode: {mode}, Host: {host}")

    # Validate host selection
    if not host:
        return jsonify({'error': 'No host selected'})

    # Set the appropriate host in environment variables
    if host == 'win10':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WIN10')
    elif host == 'win11':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WIN11')
    elif host == 'winserver12':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer12')
    elif host == 'winserver16':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer16')
    elif host == 'winserver19':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer19')
    elif host == 'winserver22':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer22')
    elif host == 'winserver25':
        os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer25')
    else:
        return jsonify({'error': 'Invalid host selected'})

    # Get artifacts list
    artifacts = []
    if profile_id:
        try:
            with open(os.path.join('profiles', f'{profile_id}.json'), 'r') as f:
                profile = json.load(f)
                artifacts = profile.get('artifacts', [])
                app.logger.info(f"Loaded artifacts from profile {profile_id}: {artifacts}")
        except Exception as e:
            error_msg = f'Error loading profile: {str(e)}'
            app.logger.error(error_msg)
            return jsonify({'error': error_msg})
    else:
        artifacts = request.form.get('artifacts', '').split(',')
        artifacts = [a.strip() for a in artifacts if a.strip()]
        app.logger.info(f"Using manually specified artifacts: {artifacts}")

    if not artifacts:
        return jsonify({'error': 'No artifacts specified'})

    try:
        # Create new collector manager instance
        collector_manager = CollectorManager(mode=mode)
        app.logger.info(f"Created new CollectorManager instance with mode: {mode}")
        
        # Start processing in background thread
        thread = threading.Thread(
            target=collector_manager.run,
            args=(artifacts, build_collectors)
        )
        thread.daemon = True
        thread.start()

        app.logger.info(f"Started processing thread with {len(artifacts)} artifacts and build_collectors={build_collectors}")

        return jsonify({
            'status': 'started',
            'total_artifacts': len(artifacts),
            'mode': mode,
            'build_collectors': build_collectors
        })

    except Exception as e:
        error_msg = f'Failed to start processing: {str(e)}'
        app.logger.error(error_msg)
        return jsonify({'error': error_msg})

@app.route('/status')
def get_status():
    """Get current processing status and statistics"""
    global collector_manager
    if not collector_manager:
        return jsonify({
            'processing': False,
            'total_artifacts': 0,
            'processed': 0,
            'current_artifact': '',
            'messages': [],
            'completed': False,
            'results': [],
            'artifact_stats': {
                'successful': [],
                'failed': []
            },
            'runtime_stats': get_runtime_stats()
        })
    
    status = collector_manager.get_status()
    status['runtime_stats'] = get_runtime_stats()
    return jsonify(status)

@app.route('/results/<path:filename>')
def download_result(filename):
    """Download processed result files"""
    return send_from_directory('runtime_zip', filename)

@app.route('/stop', methods=['POST'])
def stop_processing():
    """Stop current processing if any"""
    global collector_manager
    if collector_manager and collector_manager.status['processing']:
        collector_manager.stop_processing()
        return jsonify({'status': 'stopping'})
    return jsonify({'status': 'not_running'})

@app.route('/start-combinations', methods=['POST'])
def start_profile_testing():
    """Start testing of complete profiles"""
    global collector_manager
    
    try:
        # Log raw request data for debugging
        app.logger.info(f"Raw request data: {request.get_data()}")
        
        if not request.is_json:
            app.logger.error("Request Content-Type is not application/json")
            return jsonify({'error': 'Request must be JSON'}), 400
            
        if collector_manager and collector_manager.status['processing']:
            return jsonify({
                'error': 'Processing already in progress',
                'current_artifact': collector_manager.status['current_artifact']
            })

        # Get processing parameters
        data = request.get_json()
        app.logger.info(f"Parsed JSON data: {data}")
        
        profiles = data.get('profiles', [])
        host = data.get('host')
        sequential_execution = data.get('sequentialExecution', False)
        build_collectors = data.get('buildCollectors', False)

        # Validate required fields
        if not profiles:
            return jsonify({'error': 'No profiles specified'}), 400
        if not host:
            return jsonify({'error': 'No host selected'}), 400

        # Log the received parameters
        app.logger.info(f"Received profile testing request - Profiles: {profiles}, Host: {host}, "
                    f"Sequential: {sequential_execution}, Build Collectors: {build_collectors}")

        # Clean all directories using collector_manager's function
        CollectorManager.clean_all_directories()

        # Set the appropriate host in environment variables
        if host == 'win10':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WIN10')
        elif host == 'win11':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WIN11')
        elif host == 'winserver12':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer12')
        elif host == 'winserver16':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer16')
        elif host == 'winserver19':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer19')
        elif host == 'winserver22':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer22')
        elif host == 'winserver25':
            os.environ['WINRM_HOST'] = Config.get('WINRM_HOST_WINServer25')
        else:
            return jsonify({'error': 'Invalid host selected'}), 400

        # Get artifacts from selected profiles
        artifacts = []
        for profile_id in profiles:
            profile_path = os.path.join('profiles', f'{profile_id}.json')
            if not os.path.exists(profile_path):
                return jsonify({'error': f'Profile not found: {profile_id}'}), 404
                
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)
                    profile_artifacts = profile.get('artifacts', [])
                    app.logger.info(f"Loaded artifacts from profile {profile_id}: {profile_artifacts}")
                    artifacts.extend(profile_artifacts)
            except json.JSONDecodeError as e:
                return jsonify({'error': f'Invalid JSON in profile {profile_id}: {str(e)}'}), 400
            except Exception as e:
                app.logger.error(f"Error loading profile {profile_id}: {str(e)}")
                return jsonify({'error': f'Error loading profile {profile_id}: {str(e)}'}), 500

        # Remove duplicates while preserving order
        artifacts = list(dict.fromkeys(artifacts))

        if not artifacts:
            return jsonify({'error': 'No artifacts found in selected profiles'}), 400

        try:
            # Create new collector manager instance
            collector_manager = CollectorManager(mode='sequential' if sequential_execution else 'batch')
            app.logger.info(f"Created new CollectorManager instance for profile testing")
            
            # Initialize credentials and connections
            credentials = get_winrm_credentials()
            if not credentials:
                return jsonify({'error': 'Failed to get credentials'}), 500
            collector_manager.credentials = credentials
            
            # Initialize WinRM session if building collectors
            if build_collectors:
                if not collector_manager.initialize_connections():
                    return jsonify({'error': 'Failed to initialize WinRM connection'}), 500
            
            # Start processing in background thread
            thread = threading.Thread(
                target=process_profile_artifacts,
                args=(artifacts, build_collectors)
            )
            thread.daemon = True
            thread.start()

            return jsonify({
                'status': 'started',
                'total_artifacts': len(artifacts),
                'sequential': sequential_execution,
                'build_collectors': build_collectors
            })

        except Exception as e:
            app.logger.error(f"Failed to start profile testing: {str(e)}")
            return jsonify({'error': f'Failed to start profile testing: {str(e)}'}), 500

    except Exception as e:
        app.logger.error(f"Unexpected error in start_profile_testing: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

def process_profile_artifacts(artifacts, build_collectors):
    """Process all artifacts from selected profiles in a single spec"""
    global collector_manager
    try:
        collector_manager.status.update({
            'processing': True,
            'total_artifacts': len(artifacts),
            'processed_artifacts': 0,
            'current_artifact': '',
            'artifact_results': []
        })

        # Update status message
        collector_manager.update_status(
            f"Processing {len(artifacts)} artifacts from selected profiles"
        )

        # Process all artifacts in a single spec
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        spec_name = f"profile_test_{timestamp}"
        success = collector_manager.process_artifact_combination(artifacts, build_collectors)
        
        # Store results
        result = {
            'artifacts': artifacts,
            'success': success,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'stats': collector_manager.get_status()['artifact_stats']
        }
        collector_manager.status['artifact_results'] = [result]

        collector_manager.status['completed'] = True
        collector_manager.update_status("Profile testing completed")

    except Exception as e:
        collector_manager.update_status(f"Error during profile testing: {str(e)}", True)
    finally:
        collector_manager.status['processing'] = False

@app.route('/profile-status')
def get_profile_status():
    """Get current profile testing status"""
    global collector_manager
    if not collector_manager:
        return jsonify({
            'processing': False,
            'total_artifacts': 0,
            'processed_artifacts': 0,
            'current_artifact': '',
            'messages': [],
            'completed': False,
            'artifact_results': []
        })
    
    status = collector_manager.get_status()
    return jsonify(status)

@app.route('/test-profile-status')
def test_profile_status():
    """Get the current status of test profile processing"""
    global collector_manager
    
    if not collector_manager:
        return jsonify({
            'processing': False,
            'total_artifacts': 0,
            'processed': 0,
            'messages': []
        })
    
    status = collector_manager.get_status()
    return jsonify({
        'processing': status['processing'],
        'total_artifacts': status['total_artifacts'],
        'processed': status['processed'],
        'messages': status['messages']
    })

def create_self_signed_cert(cert_file: str, key_file: str) -> None:
    """Create self-signed SSL certificate"""
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)

    cert = crypto.X509()
    cert.get_subject().C = "US"
    cert.get_subject().ST = "State"
    cert.get_subject().L = "City"
    cert.get_subject().O = "Organization"
    cert.get_subject().OU = "Organizational Unit"
    cert.get_subject().CN = "localhost"
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for one year
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha256')

    with open(cert_file, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    with open(key_file, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

def initialize_app():
    """Initialize application directories and settings"""
    try:
        init_directories()
        # Ensure runtime_zip directory exists
        os.makedirs('runtime_zip', exist_ok=True)
        return True
    except Exception as e:
        print(f"Error initializing application: {e}")
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Velociraptor Collector Web Interface')
    parser.add_argument('--ssl', action='store_true', help='Enable SSL/HTTPS')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()

    if not initialize_app():
        print("Failed to initialize application. Exiting.")
        exit(1)

    if args.ssl:
        cert_file = "cert.pem"
        key_file = "key.pem"
        
        if not (os.path.exists(cert_file) and os.path.exists(key_file)):
            print("SSL certificates not found. Creating self-signed certificates...")
            create_self_signed_cert(cert_file, key_file)
            print("Self-signed certificates created successfully.")

        ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        
        app.run(
            host=args.host,
            port=args.port,
            ssl_context=ssl_context,
            debug=True
        )
    else:
        app.run(
            host=args.host,
            port=args.port,
            debug=True
        ) 