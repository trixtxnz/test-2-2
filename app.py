from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import json
import os
import hashlib
from datetime import datetime
import re # Added for validation

# OpenCV imports are placed inside the detect_objects function
# to avoid dependency issues if not installed globally.

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production
socketio = SocketIO(app, cors_allowed_origins="*")

# File to store user data
USERS_FILE = 'users.json'
CHAT_HISTORY_FILE = 'chat_history.json'

# In-memory chat storage (will also persist to file)
chat_messages = []

# File upload configuration
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def load_users():
    """Load users from JSON file"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # If file is corrupted, return empty dict
            print("Warning: users.json is corrupted, returning empty user dict")
            return {}
    return {}

def save_users(users):
    """Save users to JSON file"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
            f.flush()  # Ensure data is written to disk
    except Exception as e:
        print(f"Error saving users: {e}")

def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def load_chat_history():
    """Load chat history from JSON file"""
    global chat_messages
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, 'r') as f:
            chat_messages = json.load(f)
    else:
        chat_messages = []
    return chat_messages

def save_chat_history():
    """Save chat history to JSON file"""
    with open(CHAT_HISTORY_FILE, 'w') as f:
        json.dump(chat_messages, f, indent=2)

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_default_prefs():
    """Get default user preferences"""
    return {
        'welcome_text': 'Welcome to the website made by your ideas!',
        'bg_color': '#f5f5f5',
        'text_color': '#333333',
        'font_size': '16',
        'bg_image': None
    }

def get_user_prefs(username):
    """Get user preferences with defaults"""
    users = load_users()
    if username not in users:
        return get_default_prefs()

    user_data = users[username]
    if 'prefs' not in user_data:
        return get_default_prefs()

    # Ensure all required keys exist with defaults
    prefs = get_default_prefs()
    prefs.update(user_data['prefs'])
    return prefs

def validate_prefs(form):
    """Validate and normalize user preferences"""
    errors = []
    prefs = {}

    # Validate welcome text
    welcome_text = form.get('welcome_text', '').strip()
    if not welcome_text:
        errors.append('Welcome text cannot be empty')
    elif len(welcome_text) > 100:
        errors.append('Welcome text must be 100 characters or less')
    elif '<' in welcome_text or '>' in welcome_text:
        errors.append('Welcome text cannot contain HTML tags')
    else:
        prefs['welcome_text'] = welcome_text

    # Validate background color
    bg_color = form.get('bg_color', '').strip().lower()
    if not bg_color:
        errors.append('Background color is required')
    elif not re.match(r'^#([0-9a-f]{6}|[0-9a-f]{3})$', bg_color):
        errors.append('Background color must be a valid hex color (e.g., #ff0000)')
    else:
        prefs['bg_color'] = bg_color

    # Validate text color
    text_color = form.get('text_color', '').strip().lower()
    if not text_color:
        errors.append('Text color is required')
    elif not re.match(r'^#([0-9a-f]{6}|[0-9a-f]{3})$', text_color):
        errors.append('Text color must be a valid hex color (e.g., #000000)')
    else:
        prefs['text_color'] = text_color

    # Validate font size
    font_size = form.get('font_size', '').strip()
    if not font_size:
        errors.append('Font size is required')
    else:
        try:
            size = int(font_size)
            if size < 10 or size > 72:
                errors.append('Font size must be between 10 and 72')
            else:
                prefs['font_size'] = str(size)
        except ValueError:
            errors.append('Font size must be a valid number')

    return prefs, errors

# Load chat history on startup
load_chat_history()

# --- Public Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/webcam')
def webcam():
    return render_template('webcam.html')

@app.route('/platform')
def platform():
    username = session.get('username', 'Guest')
    return render_template('platform.html', username=username)

@app.route('/ptest3')
def ptest3():
    return render_template('ptest3.html')

@app.route('/ptest2')
def ptest2():
    return render_template('ptest2.html')

@app.route('/rtg')
def rtg():
    return render_template('rtg.html')

@app.route('/ttg')
def ttg():
    return render_template('ttg.html')

@app.route('/ideas')
def ideas():
    return render_template('ideas.html')

# --- User Authentication Routes ---

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username')
    password = request.form.get('password')
    gender = request.form.get('gender')

    if not username or not password or not gender:
        flash('All fields are required', 'error')
        return redirect(url_for('index'))

    # Validate username (alphanumeric and underscores only, 3-20 chars)
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        flash('Username must be 3-20 characters and contain only letters, numbers, and underscores', 'error')
        return redirect(url_for('index'))

    users = load_users()

    # Check if user already exists
    if username in users:
        flash('Username already exists', 'error')
        return redirect(url_for('index'))

    # Save user data with initial clicker stats and default prefs
    users[username] = {
        'password': hash_password(password),
        'gender': gender,
        'clicks': 0,
        'click_bonus': 1,
        'has_unlocked_100': False,
        'has_unlocked_1000': False,
        'has_unlocked_10000': False,
        'has_auto_clicker': False,
        'prefs': get_default_prefs()
    }
    save_users(users)

    flash('Account created successfully! You can now sign in.', 'success')
    return redirect(url_for('welcome'))

@app.route('/signin', methods=['POST'])
def signin():
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash('Username and password are required', 'error')
        return redirect(url_for('welcome'))

    users = load_users()

    # Check credentials
    if username in users and users[username]['password'] == hash_password(password):
        session['username'] = username
        return redirect(url_for('website'))
    else:
        flash('Invalid username or password', 'error')
        return redirect(url_for('welcome'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))

# --- Authenticated Routes ---

@app.route('/website')
def website():
    if 'username' not in session:
        flash('Please sign in to access the website', 'error')
        return redirect(url_for('welcome'))

    username = session['username']
    prefs = get_user_prefs(username)
    return render_template('website.html', username=username, prefs=prefs)

@app.route('/settings')
def settings():
    if 'username' not in session:
        flash('Please sign in to access settings', 'error')
        return redirect(url_for('welcome'))

    username = session['username']
    prefs = get_user_prefs(username)
    return render_template('settings.html', prefs=prefs)

@app.route('/settings', methods=['POST'])
def save_settings():
    if 'username' not in session:
        flash('Please sign in to access settings', 'error')
        return redirect(url_for('welcome'))

    username = session['username']
    prefs, errors = validate_prefs(request.form)

    if errors:
        for error in errors:
            flash(error, 'error')
        current_prefs = get_user_prefs(username)
        return render_template('settings.html', prefs=current_prefs)

    # Sanitize username for file operations (defense in depth)
    safe_username = secure_filename(username)

    # Get current background image before making changes
    users = load_users()
    current_bg_image = None
    if username in users and 'prefs' in users[username]:
        current_bg_image = users[username]['prefs'].get('bg_image')

    # Process removal BEFORE upload (takes precedence)
    if request.form.get('remove_bg_image') == 'true':
        # Delete the file from disk if it exists
        if current_bg_image:
            old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_bg_image)
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except OSError:
                    pass  # File deletion failed, but continue
        prefs['bg_image'] = None
        flash('Background image removed.', 'success')
    # Handle background image upload
    elif 'bg_image' in request.files:
        file = request.files['bg_image']

        # Check if a file was actually selected
        if file and file.filename and file.filename != '':
            if allowed_file(file.filename):
                # Delete old background image files for this user (all extensions)
                for ext in ALLOWED_EXTENSIONS:
                    old_filename = f"{safe_username}_bg.{ext}"
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                        except OSError:
                            pass  # Continue even if deletion fails

                # Create a unique filename with sanitized username prefix
                original_filename = secure_filename(file.filename)
                file_extension = original_filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{safe_username}_bg.{file_extension}"

                # Save the file
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)

                # Store the filename in preferences
                prefs['bg_image'] = unique_filename
                flash('Background image uploaded successfully!', 'success')
            else:
                flash('Invalid file type. Please upload PNG, JPG, JPEG, GIF, or WebP files.', 'error')
        else:
            # If no new file was uploaded, keep the current one (if not explicitly removed)
            prefs['bg_image'] = current_bg_image

    # If no file operations were performed, ensure current bg_image is retained
    elif current_bg_image and 'bg_image' not in prefs:
        prefs['bg_image'] = current_bg_image

    # Save preferences
    if username not in users: # Safety check for concurrent operations
        users[username] = {'prefs': {}}
    if 'prefs' not in users[username]:
        users[username]['prefs'] = {}

    users[username]['prefs'].update(prefs)
    save_users(users)

    flash('Settings saved successfully!', 'success')
    return redirect(url_for('website'))

# --- OpenCV Detection Route ---

@app.route('/detect_objects', methods=['POST'])
def detect_objects():
    """Process webcam frame and detect objects using OpenCV"""
    try:
        import cv2
        import numpy as np
        import base64

        # Get the image data from request
        data = request.json
        image_data = data.get('image', '')

        # Remove the data URL prefix
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({'error': 'Failed to decode image'}), 400

        # Define cascade paths (custom cascades first, then fallback to built-in)
        cascade_configs = [
            {'name': 'Face', 'paths': ['cascades/haarcascade_frontalface_alt2.xml',  
                                       'cascades/face.xml',
                                       cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml',
                                       cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'],
             'color': '#10b981', 'params': {'scaleFactor': 1.05, 'minNeighbors': 6, 'minSize': (50, 50)}},

            {'name': 'Hand', 'paths': ['cascades/hand.xml',
                                       'cascades/Hand.Cascade.1.xml',
                                       'cascades/palm.xml'],
             'color': '#f59e0b', 'params': {'scaleFactor': 1.05, 'minNeighbors': 4, 'minSize': (40, 40)}}
        ]

        # Convert to grayscale and enhance image quality
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # Prepare detection results
        detections = []

        # Try each cascade configuration
        for config in cascade_configs:
            cascade = None

            # Try each path until one loads successfully
            for path in config['paths']:
                # The path check is simplified here as we cannot reliably check file system
                # Instead, we rely on cv2 to try to load it.
                test_cascade = cv2.CascadeClassifier(path)
                if not test_cascade.empty():
                    cascade = test_cascade
                    break

            # If cascade loaded, perform detection
            if cascade is not None and not cascade.empty():
                objects = cascade.detectMultiScale(
                    gray,
                    scaleFactor=config['params']['scaleFactor'],
                    minNeighbors=config['params']['minNeighbors'],
                    minSize=config['params']['minSize'],
                    flags=cv2.CASCADE_SCALE_IMAGE
                )

                # Add detections
                for (x, y, w, h) in objects:
                    detections.append({
                        'label': config['name'],
                        'confidence': 0.90 if config['name'] == 'Face' else 0.80,
                        'color': config['color'],
                        'box': {
                            'x': int(x),
                            'y': int(y),
                            'width': int(w),
                            'height': int(h)
                        }
                    })

        return jsonify({
            'detections': detections,
            'count': len(detections)
        })

    except ImportError:
        return jsonify({'error': 'OpenCV (cv2) not installed. Cannot perform object detection.'}), 500
    except Exception as e:
        print(f"Detection error: {e}")
        return jsonify({'error': str(e)}), 500


# --- Clicker Game Routes ---

@app.route('/c')
def clicker():
    if 'username' not in session:
        flash('Please sign in to play the clicker game', 'error')
        return redirect(url_for('welcome'))

    users = load_users()
    username = session['username']

    # Initialize clicks if not present (for existing users who didn't go through new signup)
    # This ensures backward compatibility for older user data.
    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'click_bonus' not in users[username]:
        users[username]['click_bonus'] = 1
    if 'has_unlocked_100' not in users[username]:
        users[username]['has_unlocked_100'] = False
    if 'has_unlocked_1000' not in users[username]:
        users[username]['has_unlocked_1000'] = False
    if 'has_unlocked_10000' not in users[username]:
        users[username]['has_unlocked_10000'] = False
    if 'has_auto_clicker' not in users[username]:
        users[username]['has_auto_clicker'] = False
    save_users(users)

    current_clicks = users[username]['clicks']
    current_bonus = users[username]['click_bonus']
    has_unlocked_100 = users[username]['has_unlocked_100']
    has_unlocked_1000 = users[username]['has_unlocked_1000']
    has_unlocked_10000 = users[username]['has_unlocked_10000']
    has_auto_clicker = users[username]['has_auto_clicker']

    return render_template('clicker game.html',
                           username=username,
                           clicks=current_clicks,  
                           click_bonus=current_bonus,  
                           has_unlocked_100=has_unlocked_100,  
                           has_unlocked_1000=has_unlocked_1000,
                           has_unlocked_10000=has_unlocked_10000,
                           has_auto_clicker=has_auto_clicker)

@app.route('/save_click', methods=['POST'])
def save_click():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    users = load_users()
    username = session['username']

    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'click_bonus' not in users[username]:
        users[username]['click_bonus'] = 1

    # Increment click count by the current bonus amount
    bonus = users[username]['click_bonus']
    users[username]['clicks'] += bonus
    save_users(users)

    return jsonify({'clicks': users[username]['clicks'], 'click_bonus': bonus})

@app.route('/spend_clicks', methods=['POST'])
def spend_clicks():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    users = load_users()
    username = session['username']
    SPEND_AMOUNT = 10

    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'click_bonus' not in users[username]:
        users[username]['click_bonus'] = 1
    if 'has_unlocked_100' not in users[username]:
        users[username]['has_unlocked_100'] = False

    current_clicks = users[username]['clicks']

    if current_clicks < SPEND_AMOUNT:
        return jsonify({
            'error': f'Insufficient clicks. Need {SPEND_AMOUNT}, have {current_clicks}.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100']
        }), 400

    users[username]['clicks'] -= SPEND_AMOUNT
    users[username]['click_bonus'] += 1
    users[username]['has_unlocked_100'] = True
    save_users(users)

    return jsonify({
        'clicks': users[username]['clicks'],
        'click_bonus': users[username]['click_bonus'],
        'has_unlocked_100': users[username]['has_unlocked_100']
    })

@app.route('/spend_clicks_100', methods=['POST'])
def spend_clicks_100():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    users = load_users()
    username = session['username']
    SPEND_AMOUNT = 100

    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'click_bonus' not in users[username]:
        users[username]['click_bonus'] = 1
    if 'has_unlocked_100' not in users[username]:
        users[username]['has_unlocked_100'] = False
    if 'has_unlocked_1000' not in users[username]:
        users[username]['has_unlocked_1000'] = False

    current_clicks = users[username]['clicks']

    if not users[username]['has_unlocked_100']:
        return jsonify({
            'error': 'You must unlock this upgrade first by buying the 10 clicks upgrade.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100']
        }), 403

    if current_clicks < SPEND_AMOUNT:
        return jsonify({
            'error': f'Insufficient clicks. Need {SPEND_AMOUNT}, have {current_clicks}.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100']
        }), 400

    users[username]['clicks'] -= SPEND_AMOUNT
    users[username]['click_bonus'] += 10
    users[username]['has_unlocked_1000'] = True
    save_users(users)

    return jsonify({
        'clicks': users[username]['clicks'],
        'click_bonus': users[username]['click_bonus'],
        'has_unlocked_100': users[username]['has_unlocked_100'],
        'has_unlocked_1000': users[username]['has_unlocked_1000']
    })

@app.route('/spend_clicks_1000', methods=['POST'])
def spend_clicks_1000():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    users = load_users()
    username = session['username']
    SPEND_AMOUNT = 1000

    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'click_bonus' not in users[username]:
        users[username]['click_bonus'] = 1
    if 'has_unlocked_1000' not in users[username]:
        users[username]['has_unlocked_1000'] = False
    if 'has_unlocked_10000' not in users[username]:
        users[username]['has_unlocked_10000'] = False

    current_clicks = users[username]['clicks']

    if not users[username]['has_unlocked_1000']:
        return jsonify({
            'error': 'You must unlock this upgrade first by buying the 100 clicks upgrade.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100'],
            'has_unlocked_1000': users[username]['has_unlocked_1000']
        }), 403

    if current_clicks < SPEND_AMOUNT:
        return jsonify({
            'error': f'Insufficient clicks. Need {SPEND_AMOUNT}, have {current_clicks}.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100'],
            'has_unlocked_1000': users[username]['has_unlocked_1000']
        }), 400

    users[username]['clicks'] -= SPEND_AMOUNT
    users[username]['click_bonus'] += 100
    users[username]['has_unlocked_10000'] = True
    save_users(users)

    return jsonify({
        'clicks': users[username]['clicks'],
        'click_bonus': users[username]['click_bonus'],
        'has_unlocked_100': users[username]['has_unlocked_100'],
        'has_unlocked_1000': users[username]['has_unlocked_1000'],
        'has_unlocked_10000': users[username]['has_unlocked_10000']
    })

@app.route('/spend_clicks_10000', methods=['POST'])
def spend_clicks_10000():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    users = load_users()
    username = session['username']
    SPEND_AMOUNT = 10000

    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'click_bonus' not in users[username]:
        users[username]['click_bonus'] = 1
    if 'has_unlocked_10000' not in users[username]:
        users[username]['has_unlocked_10000'] = False

    current_clicks = users[username]['clicks']

    if not users[username]['has_unlocked_10000']:
        return jsonify({
            'error': 'You must unlock this upgrade first by buying the 1000 clicks upgrade.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100'],
            'has_unlocked_1000': users[username]['has_unlocked_1000'],
            'has_unlocked_10000': users[username]['has_unlocked_10000']
        }), 403

    if current_clicks < SPEND_AMOUNT:
        return jsonify({
            'error': f'Insufficient clicks. Need {SPEND_AMOUNT}, have {current_clicks}.',
            'clicks': current_clicks,
            'click_bonus': users[username]['click_bonus'],
            'has_unlocked_100': users[username]['has_unlocked_100'],
            'has_unlocked_1000': users[username]['has_unlocked_1000'],
            'has_unlocked_10000': users[username]['has_unlocked_10000']
        }), 400

    users[username]['clicks'] -= SPEND_AMOUNT
    users[username]['click_bonus'] += 1000
    save_users(users)

    return jsonify({
        'clicks': users[username]['clicks'],
        'click_bonus': users[username]['click_bonus'],
        'has_unlocked_100': users[username]['has_unlocked_100'],
        'has_unlocked_1000': users[username]['has_unlocked_1000'],
        'has_unlocked_10000': users[username]['has_unlocked_10000']
    })

@app.route('/unlock_auto_clicker', methods=['POST'])
def unlock_auto_clicker():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    users = load_users()
    username = session['username']
    SPEND_AMOUNT = 15000

    if 'clicks' not in users[username]:
        users[username]['clicks'] = 0
    if 'has_unlocked_10000' not in users[username]:
        users[username]['has_unlocked_10000'] = False
    if 'has_auto_clicker' not in users[username]:
        users[username]['has_auto_clicker'] = False

    current_clicks = users[username]['clicks']

    if not users[username]['has_unlocked_10000']:
        return jsonify({
            'error': 'You must unlock the 10000 upgrade first.',
            'clicks': current_clicks,
            'has_auto_clicker': users[username]['has_auto_clicker']
        }), 403

    if users[username]['has_auto_clicker']:
        return jsonify({
            'error': 'Auto-clicker already unlocked.',
            'clicks': current_clicks,
            'has_auto_clicker': True
        }), 400

    if current_clicks < SPEND_AMOUNT:
        return jsonify({
            'error': f'Insufficient clicks. Need {SPEND_AMOUNT}, have {current_clicks}.',
            'clicks': current_clicks,
            'has_auto_clicker': users[username]['has_auto_clicker']
        }), 400

    users[username]['clicks'] -= SPEND_AMOUNT
    users[username]['has_auto_clicker'] = True
    save_users(users)

    return jsonify({
        'clicks': users[username]['clicks'],
        'has_auto_clicker': users[username]['has_auto_clicker']
    })


# --- WebSocket Event Handlers for Multiplayer Chat/Platformer ---

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        emit('user_connected', {'username': session['username']}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if 'username' in session:
        emit('user_disconnected', {'username': session['username']}, broadcast=True)

@socketio.on('join_room')
def handle_join_room(data):
    if 'username' in session:
        room = data.get('room', 'default')
        # Use unified room for both website and platformer
        unified_room = 'unified_chat' if room in ['default', 'platformer_game'] else room
        join_room(unified_room)

        # Send chat history to the newly joined user
        emit('chat_history', {'messages': chat_messages})

        emit('user_joined', {
            'username': session['username'],
            'room': unified_room
        }, room=unified_room)

@socketio.on('leave_room')
def handle_leave_room(data):
    if 'username' in session:
        room = data.get('room', 'default')
        # Use unified room for both website and platformer
        unified_room = 'unified_chat' if room in ['default', 'platformer_game'] else room
        leave_room(unified_room)
        emit('user_left', {
            'username': session['username'],
            'room': unified_room
        }, room=unified_room)

@socketio.on('send_message')
def handle_message(data):
    if 'username' in session:
        room = data.get('room', 'default')
        # Use unified room for both website and platformer
        unified_room = 'unified_chat' if room in ['default', 'platformer_game'] else room

        message_data = {
            'username': session['username'],
            'message': data.get('message', ''),
            'timestamp': data.get('timestamp', datetime.now().strftime('%H:%M:%S'))
        }

        # Store message in history
        chat_messages.append(message_data)

        # Keep only last 100 messages to prevent file from growing too large
        if len(chat_messages) > 100:
            chat_messages.pop(0)

        # Save to file
        save_chat_history()

        emit('receive_message', message_data, room=unified_room)

@socketio.on('user_action')
def handle_user_action(data):
    if 'username' in session:
        room = data.get('room', 'default')
        # Use unified room for platformer actions
        unified_room = 'unified_chat' if room == 'platformer_game' else room

        emit('action_update', {
            'username': session['username'],
            'action': data.get('action', ''),
            'data': data.get('data', {})
        }, room=unified_room, include_self=False)


if __name__ == '__main__':
    # Using socketio.run instead of app.run for Flask-SocketIO apps
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
