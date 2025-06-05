from flask import Flask, render_template, request, jsonify
import os
import json
from test_one_by_one import (
    SpecFileGenerator, CollectorManager, process_artifacts,
    clean_all_directories, init_directories, build_collector
)
from config import Config
import threading
import queue
import time
import argparse
import ssl
from OpenSSL import crypto
from pathlib import Path

app = Flask(__name__)

# Global variables to track progress
progress_queue = queue.Queue()
current_status = {
    'processing': False,
    'total_artifacts': 0,
    'processed': 0,
    'current_artifact': '',
    'messages': [],
    'completed': False,
    'task_start_time': None,  # Track the start time of current task
    'artifact_stats': {
        'successful': [],
        'failed': []
    }
}

def is_valid_json_file(file_path: str) -> bool:
    """Check if a file contains valid JSON data."""
    if not os.path.exists(file_path):
        return False
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:  # Empty file
                return False
            
            # Try to parse each line as JSON
            for line in content.split('\n'):
                if line.strip():  # Skip empty lines
                    json.loads(line)
            return True
    except (json.JSONDecodeError, Exception):
        return False

def collect_artifact_stats() -> dict:
    """Collect statistics about artifact processing success/failure."""
    stats = {
        'successful': [],
        'failed': []
    }
    
    # Look for the most recent collection directory
    runtime_zip = Path('runtime_zip')
    if not runtime_zip.exists():
        return stats
        
    # Get all collection directories sorted by modification time (most recent first)
    collection_dirs = sorted(
        [d for d in runtime_zip.iterdir() if d.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    if not collection_dirs:
        return stats
        
    # Use the most recent collection
    latest_dir = collection_dirs[0]
    results_dir = latest_dir / 'results'
    
    if not results_dir.exists():
        return stats
    
    # Check each JSON file in the results directory
    for json_file in results_dir.glob('*.json'):
        # Skip BasicInformation.json as it's not an artifact result
        if json_file.name == 'Generic.Client.Info.BasicInformation.json':
            continue
            
        # Get artifact name from filename
        artifact_name = json_file.stem
        
        # Get file creation/modification time
        file_stat = json_file.stat()
        file_info = {
            'name': artifact_name,
            'created_at': time.strftime('%H:%M:%S', time.localtime(file_stat.st_ctime)),
            'size': f"{file_stat.st_size / 1024:.1f}KB"  # Convert to KB
        }
        
        # Check if the file is valid and non-empty
        if is_valid_json_file(str(json_file)):
            stats['successful'].append(file_info)
        else:
            stats['failed'].append(file_info)
            
    return stats

def update_status(message, is_error=False):
    current_time = time.time()
    elapsed = ""
    
    # Calculate elapsed time if there was a previous task
    if current_status['task_start_time'] is not None:
        elapsed = f"(took {current_time - current_status['task_start_time']:.2f}s)"
    
    # Update start time for the new task
    current_status['task_start_time'] = current_time
    
    status_update = {
        'message': message,  # Remove elapsed time from message
        'timestamp': time.strftime('%H:%M:%S'),
        'type': 'error' if is_error else 'info',
        'elapsed': elapsed
    }
    progress_queue.put(status_update)
    current_status['messages'].append(status_update)

def process_artifacts_async(artifacts, build_collectors):
    current_status['processing'] = True
    current_status['completed'] = False
    current_status['total_artifacts'] = len(artifacts)
    current_status['processed'] = 0
    current_status['messages'] = []
    current_status['task_start_time'] = time.time()
    current_status['artifact_stats'] = {
        'successful': [],
        'failed': []
    }

    try:
        # Clean and initialize directories
        update_status("Cleaning directories...")
        if not clean_all_directories():
            update_status("Failed to clean directories", True)
            return

        init_directories()
        update_status("Directories initialized successfully")

        # Initialize generators
        spec_generator = SpecFileGenerator(
            Config.get('ARTIFACT_TEMPLATE_PATH'),
            Config.get('ARTIFACT_LIST_FILE'),
            Config.get('ARTIFACT_SPECS_DIR')
        )

        collector_manager = None
        if build_collectors:
            collector_manager = CollectorManager(
                Config.get('VELO_BINARY_PATH'),
                Config.get('WINRM_HOST')
            )

        # Process each artifact
        for artifact in artifacts:
            current_status['current_artifact'] = artifact
            artifact_start_time = time.time()
            update_status(f"Processing artifact: {artifact}")
            
            artifact_info = {
                'name': artifact,
                'execution_time': 0.0  # Default value
            }
            
            spec_path = spec_generator.create_spec_file(
                artifact,
                [],  # These will be populated in the create_spec_file method
                []
            )
            
            if spec_path:
                update_status(f"Created spec file for {artifact}")
                if build_collectors and collector_manager:
                    collector_start_time = time.time()
                    build_success = build_collector(artifact, spec_path, collector_manager)
                    collector_end_time = time.time()
                    artifact_info['execution_time'] = round(collector_end_time - collector_start_time, 2)
                    
                    if build_success:
                        update_status(f"Successfully built collector for {artifact}")
                        current_status['artifact_stats']['successful'].append(artifact_info)
                    else:
                        update_status(f"Failed to build collector for {artifact}", True)
                        current_status['artifact_stats']['failed'].append(artifact_info)
            else:
                artifact_info['execution_time'] = round(time.time() - artifact_start_time, 2)
                update_status(f"Failed to create spec for {artifact}", True)
                current_status['artifact_stats']['failed'].append(artifact_info)
            
            current_status['processed'] += 1

        update_status("Processing completed")
        
    except Exception as e:
        update_status(f"Error during processing: {str(e)}", True)
    finally:
        current_status['processing'] = False
        current_status['completed'] = True
        current_status['task_start_time'] = None  # Reset start time

def load_profiles():
    profiles = []
    profiles_dir = 'profiles'
    if os.path.exists(profiles_dir):
        for filename in os.listdir(profiles_dir):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(profiles_dir, filename), 'r') as f:
                        profile = json.load(f)
                        profile['id'] = os.path.splitext(filename)[0]  # Add filename without extension as ID
                        profiles.append(profile)
                except Exception as e:
                    print(f"Error loading profile {filename}: {e}")
    return profiles

@app.route('/')
def index():
    profiles = load_profiles()
    return render_template('index.html', profiles=profiles)

@app.route('/start', methods=['POST'])
def start_processing():
    if current_status['processing']:
        return jsonify({'error': 'Processing already in progress'})

    # Clear previous results and status
    current_status['messages'] = []
    current_status['processed'] = 0
    current_status['total_artifacts'] = 0
    current_status['current_artifact'] = ''
    current_status['completed'] = False
    current_status['task_start_time'] = None
    current_status['artifact_stats'] = {  # Clear artifact statistics
        'successful': [],
        'failed': []
    }

    profile_id = request.form.get('profile')
    build_collectors = request.form.get('build_collectors') is not None

    # Get artifacts from profile
    artifacts = []
    if profile_id:
        try:
            with open(os.path.join('profiles', f'{profile_id}.json'), 'r') as f:
                profile = json.load(f)
                artifacts = profile.get('artifacts', [])
        except Exception as e:
            return jsonify({'error': f'Error loading profile: {str(e)}'})
    else:
        # Fallback to direct artifact input
        artifacts = request.form.get('artifacts', '').split(',')
        artifacts = [a.strip() for a in artifacts if a.strip()]

    if not artifacts:
        return jsonify({'error': 'No artifacts specified'})

    # Start processing in a background thread
    thread = threading.Thread(
        target=process_artifacts_async,
        args=(artifacts, build_collectors)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'started', 'cleared': True})

@app.route('/status')
def get_status():
    # Get any new messages from the queue
    while not progress_queue.empty():
        try:
            progress_queue.get_nowait()
        except queue.Empty:
            break

    # Get the results directory structure if completed
    results = []
    if current_status['completed']:
        runtime_zip_path = 'runtime_zip'
        if os.path.exists(runtime_zip_path):
            for root, dirs, files in os.walk(runtime_zip_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    result = {'path': file_path}
                    
                    # If it's a JSON file, read first two lines
                    if file.endswith('.json'):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                # Read all lines and get the last two
                                lines = f.readlines()
                                last_two = lines[-2:] if len(lines) >= 2 else lines
                                result['preview'] = [line.strip() for line in last_two]
                        except Exception as e:
                            result['preview'] = [f"Error reading file: {str(e)}"]
                    results.append(result)

    return jsonify({
        'processing': current_status['processing'],
        'total_artifacts': current_status['total_artifacts'],
        'processed': current_status['processed'],
        'current_artifact': current_status['current_artifact'],
        'messages': current_status['messages'],
        'completed': current_status['completed'],
        'results': results,
        'artifact_stats': {
            'successful': current_status['artifact_stats']['successful'],
            'failed': current_status['artifact_stats']['failed']
        }
    })

def create_self_signed_cert(cert_file, key_file):
    # Generate key
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)

    # Generate certificate
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

    # Save certificate and private key
    with open(cert_file, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    with open(key_file, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the web interface')
    parser.add_argument('--ssl', action='store_true', help='Enable SSL/HTTPS')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    args = parser.parse_args()

    if args.ssl:
        cert_file = "cert.pem"
        key_file = "key.pem"
        
        # Check if certificate files exist, if not create them
        if not (os.path.exists(cert_file) and os.path.exists(key_file)):
            print("SSL certificates not found. Creating self-signed certificates...")
            create_self_signed_cert(cert_file, key_file)
            print("Self-signed certificates created successfully.")

        ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        
        app.run(host='0.0.0.0', port=args.port, ssl_context=ssl_context, debug=True)
    else:
        app.run(host='0.0.0.0', port=args.port, debug=True) 