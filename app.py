from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import shutil
import os
import subprocess
import tempfile
import uuid
from datetime import datetime
import json
from supabase import create_client, Client
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)


# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')
SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET', 'manim-videos')  # Default bucket name

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# def initialize_manim(OUTPUT_DIR):
#     """Initialize Manim on startup to avoid first-request issues"""
#     try:
#         # Create a simple test script to initialize Manim
#         test_script = '''
# from manim import *

# class InitTest(Scene):
#     def construct(self):
#         text = Text("Init")
#         self.add(text)
# '''
        
#         # Create temporary file
#         init_filename = f"init_test_{uuid.uuid4().hex[:8]}"
#         script_path = os.path.join(OUTPUT_DIR, f"{init_filename}.py")
        
#         with open(script_path, 'w') as f:
#             f.write(test_script)
        
#         # Run manim command to initialize
#         cmd = [
#             'manim', 
#             f"{init_filename}.py", 
#             'InitTest',  # Specify the scene class name
#             '-ql',  
#             '--disable_caching',
#             '--output_file', f"{init_filename}.mp4"
#         ]
        
#         result = subprocess.run(
#             cmd,
#             cwd=OUTPUT_DIR,
#             capture_output=True,
#             text=True,
#             timeout=60
#         )
        
#         print(f"Manim initialization result: {result.returncode}")
#         if result.returncode != 0:
#             print(f"Init warning: {result.stderr}")
            
#     except Exception as e:
#         print(f"Manim initialization error: {e}")



def validate_manim_script(script_content):
    """Basic validation of Manim script"""
    required_imports = ['manim', 'Scene']
    has_scene_class = 'class' in script_content and 'Scene' in script_content
    has_construct = 'def construct' in script_content
    
    return has_scene_class and has_construct

def upload_to_supabase(file_path, filename):
    """Upload file to Supabase storage"""
    try:
        print(f"Attempting to upload file: {file_path}")
        print(f"File exists: {os.path.exists(file_path)}")
        print(f"File size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'} bytes")
        
        # Check if file exists and is not empty
        if not os.path.exists(file_path):
            return None, f"File not found: {file_path}"
        
        if os.path.getsize(file_path) == 0:
            return None, f"File is empty: {file_path}"
        
        # Read the file
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        print(f"File read successfully, size: {len(file_data)} bytes")
        
        # Upload to Supabase storage
        try:
            response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=filename,
                file=file_data,
                file_options={
                    'content-type': 'video/mp4',
                    'upsert': "true"  # Allow overwriting if file exists
                }
            )
            print(f"Upload response: {response}")
            
            # Check if upload was successful
            if hasattr(response, 'path') or hasattr(response, 'full_path'):
                public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
                print(f"Upload successful, public URL: {public_url}")
                return public_url, None
            else:
                error_msg = f"Upload failed - Unexpected response: {response}"
                print(error_msg)
                return None, error_msg

                            
        except Exception as upload_error:
            error_msg = f"Supabase upload error: {str(upload_error)}"
            print(error_msg)
            return None, error_msg
            
    except Exception as e:
        error_msg = f"Error uploading to Supabase: {str(e)}"
        print(error_msg)
        return None, error_msg

def save_video_metadata(filename, public_url, script_content, render_time):
    """Save video metadata to Supabase database"""
    try:
        data = {
            'filename': filename,
            'public_url': public_url,
            'script_content': script_content,
            'render_time': render_time,
            'created_at': datetime.now().isoformat()
        }
        
        response = supabase.table('manim_videos').insert(data).execute()
        return response.data, None
        
    except Exception as e:
        return None, f"Error saving metadata: {str(e)}"

def render_manim_video(script_content, filename,OUTPUT_DIR):
    """Render Manim script to video"""
    try:
        # Create temporary Python file
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        script_path = os.path.join(OUTPUT_DIR, f"{filename}.py")
        with open(script_path, 'w') as f:
            f.write(script_content)
        script_filename = f"{filename}.py"
        
        # Run Manim command
        cmd = [
            'manim', 
            script_filename, 
            '-ql',  
            '--output_file', f"{filename}.mp4"
        ]
        
        result = subprocess.run(
            cmd,
            cwd=OUTPUT_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            video_path = None 
            # Find the generated video file
            for root, dirs, files in os.walk(OUTPUT_DIR):
                for file in files:
                    if file.endswith('.mp4') and filename in file:
                        video_path = os.path.join(root, file)
                        break
                if video_path:
                    break
            
            if video_path and os.path.exists(video_path):
                return video_path, None
            else:
                return None, "Video file was not generated despite successful command execution"
        else:
            print(f"First attempt failed, retrying... Error")
            
            error_msg = f"Manim rendering failed: {result.stderr}"
            print(error_msg)
            return None, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = "Manim rendering timed out (120 seconds)"
        print(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Error rendering video: {str(e)}"
        print(error_msg)
        return None, error_msg

@app.route('/render-video', methods=['POST'])
def render_video():
    try:
        data = request.json
        script = data.get('script', '')
        custom_filename = data.get('filename', '')
        
        if not script:
            return jsonify({'error': 'Script is required'}), 400
        
        # Generate unique filename
        if custom_filename:
            filename = f"{custom_filename}_{uuid.uuid4().hex[:8]}"
        else:
            filename = f"manim_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
        
        render_start_time = datetime.now()
        OUTPUT_DIR = tempfile.mkdtemp(prefix='manim_')
        # initialize_manim(OUTPUT_DIR)
        # Render video
        video_path, error = render_manim_video(script, filename,OUTPUT_DIR)
        print("Final video path:", video_path)

        if error or not video_path:
            return jsonify({'error': error or 'Failed to render video'}), 500
        
        render_end_time = datetime.now()
        render_duration = (render_end_time - render_start_time).total_seconds()
        
        # Upload to Supabase
        video_filename = f"{filename}.mp4"
        print(f"Attempting to upload: {video_path} as {video_filename}")
        
        public_url, upload_error = upload_to_supabase(video_path, video_filename)
        
        print("url",public_url)
        print("uploaderror",upload_error)
        response_data = {
            'success': True,
            'video_filename': video_filename,
            'local_video_path': video_path,
            'render_time': render_duration,
            'timestamp': datetime.now().isoformat()
        }
        
        if upload_error:
            print(f"Upload error: {upload_error}")
            response_data['upload_error'] = upload_error
            response_data['message'] = 'Video rendered but upload failed'
            response_data['local_video_filename'] = os.path.basename(video_path)
        else:
            print(f"Upload successful: {public_url}")
            response_data['public_url'] = public_url
            response_data['message'] = 'Video rendered and uploaded successfully'
            
            # # Save metadata to database only if upload was successful
            # metadata, metadata_error = save_video_metadata(
            #     video_filename, 
            #     public_url, 
            #     script, 
            #     render_duration
            # )
            
            # if metadata_error:
            #     print(f"Metadata save error: {metadata_error}")
            #     response_data['metadata_warning'] = f'Metadata save failed: {metadata_error}'
            
            # Clean up local files only if upload was successful
        try:
            print(f"Cleaning up local files...")
            # media_dir = os.path.join(OUTPUT_DIR, "media")
            if os.path.exists(OUTPUT_DIR):
                shutil.rmtree(OUTPUT_DIR)
                print(f"Deleted media directory: {OUTPUT_DIR}")
            response_data['cleanup_success'] = True
            
        except Exception as cleanup_error:
            print(f"Cleanup error: {cleanup_error}")
            response_data['cleanup_error'] = str(cleanup_error)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"General error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/video/<filename>', methods=['GET'])
def serve_video(filename):
    """Serve video from Supabase (redirect to public URL)"""
    try:
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
        print("Generated public URL:", public_url)

        return jsonify({
            'success': True,
            'url': public_url
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'url': None
        }), 500

@app.route('/videos', methods=['GET'])
def list_videos():
    """List all videos from Supabase database"""
    try:
        response = supabase.table('manim_videos').select('*').order('created_at', desc=True).execute()
        return jsonify({
            'videos': response.data,
            'count': len(response.data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/video/<filename>/delete', methods=['DELETE'])
def delete_video(filename):
    """Delete video from Supabase storage and database"""
    try:
        # Delete from storage
        storage_response = supabase.storage.from_(SUPABASE_BUCKET).remove([filename])
        
        # Delete from database
        db_response = supabase.table('manim_videos').delete().eq('filename', filename).execute()
        
        return jsonify({
            'success': True,
            'message': f'Video {filename} deleted successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/validate-script', methods=['POST'])
def validate_script():
    try:
        data = request.json
        script = data.get('script', '')
        
        if not script:
            return jsonify({'error': 'Script is required'}), 400
        
        is_valid = validate_manim_script(script)
        
        return jsonify({
            'valid': is_valid,
            'message': 'Script is valid' if is_valid else 'Script missing required components (Scene class, construct method)'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'supabase_configured': bool(SUPABASE_URL and SUPABASE_KEY),
        'supabase_url': SUPABASE_URL[:50] + '...' if SUPABASE_URL else None,
        'bucket_name': SUPABASE_BUCKET
    })

@app.route('/test-supabase', methods=['GET'])
def test_supabase():
    """Test Supabase connection"""
    try:
        # Test bucket access
        files = supabase.storage.from_(SUPABASE_BUCKET).list()
        
        # Test database access
        videos = supabase.table('manim_videos').select('count', count='exact').execute()
        
        return jsonify({
            'success': True,
            'bucket_accessible': True,
            'files_in_bucket': len(files) if files else 0,
            'database_accessible': True,
            'videos_in_db': videos.count if hasattr(videos, 'count') else 'unknown'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'supabase_url': SUPABASE_URL[:50] + '...' if SUPABASE_URL else None,
            'bucket_name': SUPABASE_BUCKET
        }), 500


# @app.route('/validate-script', methods=['POST'])
# def validate_script():
#     try:
#         data = request.json
#         script = data.get('script', '')
        
#         if not script:
#             return jsonify({'error': 'Script is required'}), 400
        
#         is_valid = validate_manim_script(script)
        
#         return jsonify({
#             'valid': is_valid,
#             'message': 'Script is valid' if is_valid else 'Script missing required components (Scene class, construct method)'
#         })
        
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

if __name__ == '__main__': 
    app.run(debug=True,use_reloader=False)
