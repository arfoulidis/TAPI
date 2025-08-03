import os
import sys
import requests
import sqlite3
from PIL import Image
from multiprocessing import Pool, cpu_count, Manager
from queue import Empty

# --- Constants ---
API_URL = 'https://raw.githubusercontent.com/arfoulidis/TAPI/main/api.txt'
DB_FILE = 'processed_files.db'
TINYPNG_API_URL = 'https://api.tinify.com/shrink'
MAX_DIMENSION = 2000

def setup_database():
    """Initializes the database and creates the processed_files table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_files (
            path TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

def load_api_keys():
    """Loads API keys from the configured URL."""
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        keys = response.text.strip().split('\n')
        if not keys or not all(keys):
            print("Error: API keys list is empty or contains invalid entries.")
            sys.exit(1)
        return keys
    except requests.exceptions.RequestException as e:
        print(f"Error loading API keys: {e}")
        sys.exit(1)

def is_file_processed(file_path):
    """Checks if a file has already been processed by querying the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_files WHERE path = ?", (file_path,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def log_processed_file(file_path):
    """Logs a successfully processed file path to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Use INSERT OR IGNORE to prevent errors if the file was already logged
    cursor.execute("INSERT OR IGNORE INTO processed_files (path) VALUES (?)", (file_path,))
    conn.commit()
    conn.close()

def compress_image(api_key, image_path):
    """Compresses a single image using the TinyPNG API."""
    with open(image_path, 'rb') as image_file:
        response = requests.post(
            TINYPNG_API_URL,
            auth=('api', api_key),
            data=image_file
        )
    response.raise_for_status()  # Raise an exception for HTTP error codes
    
    result_url = response.json()['output']['url']
    result_response = requests.get(result_url)
    result_response.raise_for_status()
    
    with open(image_path, 'wb') as out_file:
        out_file.write(result_response.content)
    print(f"Compressed {image_path}")

def resize_image(image_path):
    """Resizes an image if its dimensions exceed the maximum allowed."""
    with Image.open(image_path) as img:
        width, height = img.size
        if max(width, height) > MAX_DIMENSION:
            if width > height:
                new_width = MAX_DIMENSION
                new_height = int((MAX_DIMENSION / width) * height)
            else:
                new_height = MAX_DIMENSION
                new_width = int((MAX_DIMENSION / height) * width)
            
            img = img.resize((new_width, new_height), Image.LANCZOS)
            img.save(image_path)
            print(f"Resized {image_path} to {new_width}x{new_height}")

def process_image(args):
    """Worker function to process a single image."""
    api_keys_queue, image_path = args
    
    resize_image(image_path)

    while True:
        try:
            api_key = api_keys_queue.get_nowait()
        except Empty:
            print(f"Could not process {image_path}, no API keys available.")
            return False

        try:
            compress_image(api_key, image_path)
            log_processed_file(image_path)
            api_keys_queue.put(api_key) # Return the key to the queue on success
            return True
        except Exception as e:
            print(f"Error compressing {image_path} with a key (discarding key). Error: {e}")
            # Key is not returned to the queue, effectively discarding it

def process_directory(directory):
    """Finds images in a directory and processes them using a multiprocessing pool."""
    setup_database()
    manager = Manager()
    api_keys_queue = manager.Queue()
    for key in load_api_keys():
        api_keys_queue.put(key)

    image_paths_to_process = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('png', 'jpg', 'jpeg')):
                file_path = os.path.join(root, file)
                if not is_file_processed(file_path):
                    image_paths_to_process.append(file_path)
                else:
                    print(f"Skipping already processed file: {file_path}")

    pool_args = [(api_keys_queue, path) for path in image_paths_to_process]

    with Pool(cpu_count()) as pool:
        pool.map(process_image, pool_args)

    print("Finished processing.")
    if api_keys_queue.empty():
        print("All API keys failed and were discarded.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python compress_images.py <directory>")
        sys.exit(1)

    directory_arg = sys.argv[1]
    if not os.path.isdir(directory_arg):
        print(f"Error: Directory not found at '{directory_arg}'")
        sys.exit(1)
        
    process_directory(directory)