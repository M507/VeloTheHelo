from flask import Flask, render_template, request, jsonify, send_from_directory, safe_join, send_file, make_response
import os
import json
from collector_manager import CollectorManager
from config import Config, init_directories, get_winrm_credentials
from colors import print_warning
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

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Clean up local and remote files"""
    global collector_manager
    
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
        
    data = request.get_json()
    host = data.get('host')
    
    if not host:
        return jsonify({'error': 'No host selected'}), 400
    
    try:
        status_messages = []
        errors = []
        
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
        
        status_messages.append(f"Selected host: {host}")
        
        # Create a temporary collector manager if none exists
        if not collector_manager:
            temp_collector_manager = CollectorManager(mode='batch')
            status_messages.append("Created temporary collector manager")
        else:
            temp_collector_manager = collector_manager
            status_messages.append("Using existing collector manager")
        
        # Clean local directories
        try:
            CollectorManager.clean_all_directories()
            status_messages.append("Successfully cleaned local directories")
        except Exception as e:
            error_msg = f"Error cleaning local directories: {str(e)}"
            app.logger.error(error_msg)
            errors.append(error_msg)
        
        # Clean remote files
        try:
            credentials = get_winrm_credentials()
            if not credentials:
                error_msg = "Failed to get WinRM credentials"
                app.logger.error(error_msg)
                errors.append(error_msg)
                raise Exception(error_msg)
                
            status_messages.append("Successfully obtained WinRM credentials")
            
            winrm_session = temp_collector_manager.create_winrm_session(credentials)
            if not winrm_session:
                error_msg = "Failed to create WinRM session"
                app.logger.error(error_msg)
                errors.append(error_msg)
                raise Exception(error_msg)
                
            status_messages.append("Successfully created WinRM session")
            
            if not temp_collector_manager.cleanup_remote_files(winrm_session):
                error_msg = "Failed to clean remote files"
                app.logger.error(error_msg)
                errors.append(error_msg)
                raise Exception(error_msg)
                
            status_messages.append("Successfully cleaned remote files")
            
        except Exception as e:
            if str(e) not in errors:  # Avoid duplicate error messages
                error_msg = f"Error during remote cleanup: {str(e)}"
                app.logger.error(error_msg)
                errors.append(error_msg)
        
        # Prepare response
        response = {
            'status': 'error' if errors else 'success',
            'messages': status_messages,
            'errors': errors
        }
        
        if errors:
            return jsonify(response), 500
        else:
            return jsonify(response)
        
    except Exception as e:
        app.logger.error(f"Unexpected error during cleanup: {str(e)}")
        return jsonify({
            'status': 'error',
            'messages': status_messages if 'status_messages' in locals() else [],
            'errors': [f"Unexpected error during cleanup: {str(e)}"]
        }), 500

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
            winrm_session = collector_manager.create_winrm_session(credentials)
            if not collector_manager.cleanup_remote_files(winrm_session):
                    print_warning("Proceeding despite cleanup issues...")
            
            # Initialize WinRM session if building collectors
            if build_collectors:
                if not collector_manager.initialize_connections():
                    return jsonify({'error': 'Failed to initialize WinRM connection'}), 500
            
            # Start processing in background thread
            thread = threading.Thread(
                target=process_profile_artifacts,
                args=(artifacts, build_collectors, False, 'windows')  # Not using Architectury
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

def process_profile_artifacts(artifacts, build_collectors, use_architectury=False, platform='windows'):
    """Process all artifacts from selected profiles in a single spec"""
    global collector_manager
    try:
        collector_manager.status.update({
            'processing': True,
            'total_artifacts': len(artifacts),
            'processed_artifacts': 0,
            'current_artifact': '',
            'artifact_results': [],
            'statistics': {
                'total_execution_time': 0,
                'average_execution_time': 0,
                'success_rate': 0,
                'artifacts_processed': 0
            }
        })

        # Update status message
        if use_architectury:
            collector_manager.update_status(
                f"Processing {len(artifacts)} artifacts using Architectury for platform {platform}"
            )
        else:
            collector_manager.update_status(
                f"Processing {len(artifacts)} artifacts from selected profiles"
            )

        # Process all artifacts in a single spec
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        spec_name = f"profile_test_{timestamp}"
        start_time = time.time()
        
        if use_architectury:
            success = collector_manager.process_artifact_combination(
                artifacts, 
                build_collectors, 
                use_architectury=True, 
                platform=platform
            )
        else:
            success = collector_manager.process_artifact_combination(artifacts, build_collectors)
        total_execution_time = time.time() - start_time
        
        if success and build_collectors:
            # Pull all collection data (zip files)
            collector_manager.update_status("Pulling collection data...")
            if collector_manager.pull_collection_data():
                # Process the pulled data
                collector_manager.update_status("Processing collection data...")
                if collector_manager.process_collection_data():
                    # After processing, analyze JSON files and verify outputs
                    collector_manager.update_status("Analyzing JSON results...")
                    runtime_dir = "./runtime"
                    json_files = []
                    
                    # First verify execution output
                    output_file = os.path.join(runtime_dir, "execution_output.txt")
                    if os.path.exists(output_file):
                        with open(output_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if "Exiting" in content:
                                collector_manager.update_status("Execution verification passed: Found 'Exiting' in output")
                            else:
                                collector_manager.update_status("Execution verification failed: 'Exiting' not found in output", True)
                    
                    # Then analyze all JSON files
                    for root, _, files in os.walk(runtime_dir):
                        for file in files:
                            if file.endswith('.json'):
                                file_path = os.path.join(root, file)
                                try:
                                    with open(file_path, 'r') as f:
                                        lines = f.readlines()
                                        if len(lines) >= 2:
                                            collector_manager.update_status(f"\n{file} (last 2 lines):")
                                            # Show the last two lines with line numbers
                                            for i, line in enumerate(lines[-2:], start=len(lines)-1):
                                                collector_manager.update_status(f"Line {i+1}: {line.strip()}")
                                            
                                            # Store JSON file contents for results
                                            json_files.append({
                                                'path': file,
                                                'lines': [line.strip() for line in lines]
                                            })
                                except Exception as e:
                                    collector_manager.update_status(f"Error reading {file}: {str(e)}", True)

        # Calculate statistics
        artifact_stats = collector_manager.get_status()['artifact_stats']
        successful_artifacts = len(artifact_stats.get('successful', []))
        failed_artifacts = len(artifact_stats.get('failed', []))
        total_artifacts = successful_artifacts + failed_artifacts
        
        if total_artifacts > 0:
            success_rate = (successful_artifacts / total_artifacts) * 100
            avg_execution_time = total_execution_time / total_artifacts
        else:
            success_rate = 0
            avg_execution_time = 0

        # Update statistics
        collector_manager.status['statistics'] = {
            'total_execution_time': round(total_execution_time, 2),
            'average_execution_time': round(avg_execution_time, 2),
            'success_rate': round(success_rate, 2),
            'artifacts_processed': total_artifacts
        }

        # Store results
        result = {
            'artifacts': artifacts,
            'success': success,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'stats': artifact_stats,
            'execution_time': round(total_execution_time, 2),
            'json_files': json_files  # Add JSON files to results
        }
        collector_manager.status['artifact_results'] = [result]
        collector_manager.status['completed'] = True
        collector_manager.status['processing'] = False  # Reset processing flag
        collector_manager.update_status("Processing completed")

    except Exception as e:
        app.logger.error(f"Error in process_profile_artifacts: {str(e)}")
        collector_manager.update_status(f"Error processing artifacts: {str(e)}", True)
        collector_manager.status['completed'] = True
        collector_manager.status['processing'] = False  # Reset processing flag

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

@app.route('/start-architectury', methods=['POST'])
def start_architectury_testing():
    """Start testing with Architectury build method using existing profile processing"""
    global collector_manager
    
    try:
        # Log raw request data for debugging
        app.logger.info(f"Raw Architectury request data: {request.get_data()}")
        
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
        app.logger.info(f"Parsed Architectury JSON data: {data}")
        
        artifacts = data.get('artifacts', [])
        platform = data.get('platform', 'windows')
        host = data.get('host')
        build_collectors = data.get('buildCollectors', True)
        use_architectury = data.get('useArchitectury', True)

        # Validate required fields
        if not artifacts:
            return jsonify({'error': 'No artifacts specified'}), 400
        if not platform:
            return jsonify({'error': 'No platform selected'}), 400
        if not host:
            return jsonify({'error': 'No host selected'}), 400

        # Log the received parameters
        app.logger.info(f"Received Architectury testing request - Artifacts: {artifacts}, Platform: {platform}, Host: {host}, Build Collectors: {build_collectors}")

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

        # Process artifacts - check if it's a profile ID or actual artifacts
        processed_artifacts = []
        if len(artifacts) == 1 and artifacts[0].endswith('.json'):
            # This is a profile ID, load the profile
            profile_id = artifacts[0]
            profile_path = os.path.join('profiles', f'{profile_id}.json')
            if not os.path.exists(profile_path):
                return jsonify({'error': f'Profile not found: {profile_id}'}), 404
                
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)
                    processed_artifacts = profile.get('artifacts', [])
                    app.logger.info(f"Loaded artifacts from profile {profile_id}: {processed_artifacts}")
            except json.JSONDecodeError as e:
                return jsonify({'error': f'Invalid JSON in profile {profile_id}: {str(e)}'}), 400
            except Exception as e:
                app.logger.error(f"Error loading profile {profile_id}: {str(e)}")
                return jsonify({'error': f'Error loading profile {profile_id}: {str(e)}'}), 500
        else:
            # These are actual artifacts
            processed_artifacts = artifacts

        if not processed_artifacts:
            return jsonify({'error': 'No artifacts found'}), 400

        try:
            # Create new collector manager instance
            collector_manager = CollectorManager(mode='batch')
            app.logger.info(f"Created new CollectorManager instance for Architectury testing")
            
            # Initialize credentials and connections if building collectors
            if build_collectors:
                credentials = get_winrm_credentials()
                if not credentials:
                    return jsonify({'error': 'Failed to get credentials'}), 500
                collector_manager.credentials = credentials
                winrm_session = collector_manager.create_winrm_session(credentials)
                if not collector_manager.cleanup_remote_files(winrm_session):
                    print_warning("Proceeding despite cleanup issues...")
                
                # Initialize WinRM session
                if not collector_manager.initialize_connections():
                    return jsonify({'error': 'Failed to initialize WinRM connection'}), 500
            
            # Start processing in background thread using existing process_profile_artifacts function
            thread = threading.Thread(
                target=process_profile_artifacts,
                args=(processed_artifacts, build_collectors, use_architectury, platform)
            )
            thread.daemon = True
            thread.start()

            return jsonify({
                'status': 'started',
                'total_artifacts': len(processed_artifacts),
                'platform': platform,
                'host': host,
                'build_collectors': build_collectors,
                'use_architectury': use_architectury
            })

        except Exception as e:
            app.logger.error(f"Failed to start Architectury testing: {str(e)}")
            return jsonify({'error': f'Failed to start Architectury testing: {str(e)}'}), 500

    except Exception as e:
        app.logger.error(f"Unexpected error in start_architectury_testing: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500



@app.route('/architectury-status')
def get_architectury_status():
    """Get current Architectury testing status and statistics"""
    global collector_manager
    if not collector_manager:
        return jsonify({
            'processing': False,
            'total_artifacts': 0,
            'processed_artifacts': 0,
            'current_artifact': '',
            'messages': [],
            'completed': False,
            'artifact_stats': {
                'successful': [],
                'failed': []
            }
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
        # Ensure collectors directory exists
        os.makedirs('collectors', exist_ok=True)
        app.logger.info("Application directories initialized successfully")
        return True
    except Exception as e:
        app.logger.error(f"Error initializing application: {e}")
        return False

def investigate_directory(directory: str) -> None:
    """Investigate a directory and log its contents"""
    try:
        # Convert to forward slashes
        directory = directory.replace('\\', '/')
        app.logger.info(f"\n=== Directory Investigation for: {directory} ===")
        app.logger.info(f"Directory exists: {os.path.exists(directory)}")
        app.logger.info(f"Is directory: {os.path.isdir(directory)}")
        app.logger.info(f"Absolute path: {os.path.abspath(directory).replace('\\', '/')}")
        
        if os.path.exists(directory):
            app.logger.info("Directory contents:")
            for root, dirs, files in os.walk(directory):
                # Convert paths to forward slashes
                root = root.replace('\\', '/')
                app.logger.info(f"\nIn directory: {root}")
                if dirs:
                    # Convert all directory paths
                    dirs_with_slashes = [d.replace('\\', '/') for d in dirs]
                    app.logger.info(f"Subdirectories: {dirs_with_slashes}")
                if files:
                    app.logger.info(f"Files: {files}")
                    # Log details of each file
                    for file in files:
                        file_path = os.path.join(root, file).replace('\\', '/')
                        try:
                            size = os.path.getsize(file_path)
                            is_executable = os.access(file_path, os.X_OK)
                            app.logger.info(f"  {file}:")
                            app.logger.info(f"    - Size: {size} bytes")
                            app.logger.info(f"    - Executable: {is_executable}")
                            app.logger.info(f"    - Last modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}")
                        except Exception as e:
                            app.logger.error(f"Error getting file details for {file}: {str(e)}")
        else:
            app.logger.warning("Directory does not exist!")
    except Exception as e:
        app.logger.error(f"Error investigating directory: {str(e)}")

def find_latest_collector(
    search_dir: str = "./collectors",
    file_pattern: str = "collector",
    file_extension: str = ".exe",
    recursive: bool = True
) -> str:
    """Find the latest collector file based on specified parameters."""
    # Convert search_dir to use forward slashes
    search_dir = os.path.abspath(search_dir).replace('\\', '/')
    app.logger.info(f"Searching for latest collector in {search_dir} "
                   f"(pattern: {file_pattern}, extension: {file_extension}, "
                   f"recursive: {recursive})")
    
    if not os.path.exists(search_dir):
        app.logger.error(f"Search directory does not exist: {search_dir}")
        return None
        
    collector_files = []
    
    try:
        if recursive:
            # Recursive search through all subdirectories
            for root, _, files in os.walk(search_dir):
                # Convert root path to forward slashes
                root = root.replace('\\', '/')
                for file in files:
                    # Handle empty file extension (for cross-platform support)
                    if (file_extension == "" or file.lower().endswith(file_extension.lower())) and file_pattern.lower() in file.lower():
                        file_path = os.path.join(root, file).replace('\\', '/')
                        collector_files.append((file_path, os.path.getmtime(file_path)))
                        app.logger.info(f"Found matching file: {file_path}")
        else:
            # Non-recursive search, only in the specified directory
            for file in os.listdir(search_dir):
                # Handle empty file extension (for cross-platform support)
                if (file_extension == "" or file.lower().endswith(file_extension.lower())) and file_pattern.lower() in file.lower():
                    file_path = os.path.join(search_dir, file).replace('\\', '/')
                    if os.path.isfile(file_path):
                        collector_files.append((file_path, os.path.getmtime(file_path)))
                        app.logger.info(f"Found matching file: {file_path}")
    
        if not collector_files:
            app.logger.warning(f"No matching files found in {search_dir}")
            return None
            
        # Return the most recently modified collector file
        latest_collector = sorted(collector_files, key=lambda x: x[1], reverse=True)[0][0]
        app.logger.info(f"Latest matching file is: {latest_collector}")
        return latest_collector
        
    except Exception as e:
        app.logger.error(f"Error while searching for collector files: {str(e)}")
        return None

def is_safe_path(basedir: str, path: str) -> bool:
    """Check if the path is safe (no directory traversal)"""
    try:
        # Convert paths to use forward slashes
        basedir = os.path.realpath(basedir).replace('\\', '/')
        path = os.path.realpath(path).replace('\\', '/')
        # Check if the path is within the base directory
        common_prefix = os.path.commonprefix([basedir, path])
        return common_prefix == basedir
    except Exception:
        return False

def is_valid_collector(file_path: str) -> bool:
    """Check if the file appears to be a valid collector executable."""
    try:
        # Convert path to use forward slashes
        file_path = file_path.replace('\\', '/')
        # Check file size (between 1KB and 100MB)
        size = os.path.getsize(file_path)
        if not (1024 <= size <= 100 * 1024 * 1024):
            app.logger.warning(f"Invalid collector file size: {size} bytes")
            return False

        # Check file extension
        if not file_path.lower().endswith('.exe'):
            app.logger.warning("Invalid collector file extension")
            return False

        # Check if file is actually executable (basic check)
        if not os.access(file_path, os.X_OK):
            app.logger.warning("File is not executable")
            return False

        return True
    except Exception as e:
        app.logger.error(f"Error validating collector: {str(e)}")
        return False

@app.route('/download-collector')
def download_collector():
    """Download the latest collector file"""
    try:
        app.logger.info("\n=== Starting Download Collector Request ===")
        
        # Get absolute path to the application root directory
        app_root = os.path.abspath(os.getcwd())
        app.logger.info(f"Application root: {app_root}")
        
        # Use Flask's safe_join to create a safe path to collectors directory
        collectors_dir = safe_join(app_root, 'collectors')
        if collectors_dir is None:
            error_msg = "Invalid collectors directory path"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
            
        collectors_dir = collectors_dir.replace('\\', '/')
        app.logger.info(f"Safe collectors directory: {collectors_dir}")
        
        if not os.path.exists(collectors_dir):
            error_msg = "Collectors directory does not exist"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 404

        # Find latest collector
        collector_path = find_latest_collector(
            search_dir=collectors_dir,
            file_pattern="collector",
            file_extension=".exe",
            recursive=True
        )
        
        if not collector_path:
            error_msg = "No collector file found in collectors directory"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
            
        # Get filename and verify file
        filename = os.path.basename(collector_path)
        full_path = safe_join(collectors_dir, filename)
        if full_path is None:
            error_msg = "Invalid collector file path"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
            
        full_path = full_path.replace('\\', '/')
        app.logger.info(f"\n=== File Details ===")
        app.logger.info(f"Full path: {full_path}")
        app.logger.info(f"Filename: {filename}")
        
        if not os.path.isfile(full_path):
            error_msg = f"Collector file not found at {full_path}"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
            
        try:
            app.logger.info("\n=== Attempting Download ===")
            
            # Get file size
            file_size = os.path.getsize(full_path)
            app.logger.info(f"File size: {file_size} bytes")
            
            # Read file in binary mode
            with open(full_path, 'rb') as f:
                file_data = f.read()
            
            # Create response with file data
            response = make_response(file_data)
            
            # Set headers
            response.headers['Content-Type'] = 'application/octet-stream'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['Content-Length'] = file_size
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            app.logger.info("Successfully created response")
            app.logger.info(f"Response headers: {dict(response.headers)}")
            
            return response
            
        except Exception as e:
            error_msg = f"Error sending file: {str(e)}"
            app.logger.error(f"\n=== Download Error Details ===")
            app.logger.error(f"Error message: {str(e)}")
            app.logger.error(f"Full path: {full_path}")
            app.logger.error(f"Filename: {filename}")
            return jsonify({'error': error_msg}), 500
            
    except Exception as e:
        error_msg = f"Unexpected error in download_collector: {str(e)}"
        app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

@app.route('/download-architectury-collector')
def download_architectury_collector():
    """Download the latest Architectury collector file"""
    try:
        app.logger.info("\n=== Starting Download Architectury Collector Request ===")
        
        # Get absolute path to the application root directory
        app_root = os.path.abspath(os.getcwd())
        app.logger.info(f"Application root: {app_root}")
        
        # Get the COLLECTOR_FILE path from config
        from config import Config
        collector_file_path = Config.get('COLLECTOR_FILE')
        app.logger.info(f"COLLECTOR_FILE path: {collector_file_path}")
        
        # Use Flask's safe_join to create a safe path to the collector file
        full_path = safe_join(app_root, collector_file_path)
        if full_path is None:
            error_msg = "Invalid collector file path"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
            
        full_path = full_path.replace('\\', '/')
        app.logger.info(f"Safe collector file path: {full_path}")
        
        if not os.path.exists(full_path):
            error_msg = f"Architectury collector file not found at {full_path}"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
            
        # Get filename and verify file
        filename = os.path.basename(full_path)
        app.logger.info(f"\n=== File Details ===")
        app.logger.info(f"Full path: {full_path}")
        app.logger.info(f"Filename: {filename}")
        
        if not os.path.isfile(full_path):
            error_msg = f"Collector file not found at {full_path}"
            app.logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
            
        try:
            app.logger.info("\n=== Attempting Download ===")
            
            # Get file size
            file_size = os.path.getsize(full_path)
            app.logger.info(f"File size: {file_size} bytes")
            
            # Read file in binary mode
            with open(full_path, 'rb') as f:
                file_data = f.read()
            
            # Create response with file data
            response = make_response(file_data)
            
            # Set headers
            response.headers['Content-Type'] = 'application/octet-stream'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['Content-Length'] = file_size
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            app.logger.info("Successfully created response")
            app.logger.info(f"Response headers: {dict(response.headers)}")
            
            return response
            
        except Exception as e:
            error_msg = f"Error sending file: {str(e)}"
            app.logger.error(f"\n=== Download Error Details ===")
            app.logger.error(f"Error message: {str(e)}")
            app.logger.error(f"Full path: {full_path}")
            app.logger.error(f"Filename: {filename}")
            return jsonify({'error': error_msg}), 500
            
    except Exception as e:
        error_msg = f"Unexpected error in download_architectury_collector: {str(e)}"
        app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

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