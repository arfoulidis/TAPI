import os
import requests
from PIL import Image
from multiprocessing import Pool, cpu_count

# Load API keys from the provided URL
API_URL = 'https://raw.githubusercontent.com/arfoulidis/TAPI/main/api.txt'

def load_api_keys():
    response = requests.get(API_URL)
    response.raise_for_status()
    return response.text.strip().split('\n')

# Function to compress image using TinyPNG API
def compress_image(api_key, image_path):
    with open(image_path, 'rb') as image_file:
        response = requests.post(
            'https://api.tinify.com/shrink',
            auth=('api', api_key),
            data=image_file
        )
    if response.status_code == 201:
        # Retrieve the compressed image
        result_url = response.json()['output']['url']
        result_response = requests.get(result_url)
        result_response.raise_for_status()
        with open(image_path, 'wb') as out_file:
            out_file.write(result_response.content)
        print(f"Compressed {image_path}")
    else:
        raise Exception(f"Compression failed for {image_path} with status {response.status_code}")

# Function to resize image if it exceeds max dimension
def resize_image(image_path, max_dimension=2000):
    with Image.open(image_path) as img:
        width, height = img.size
        if max(width, height) > max_dimension:
            if width > height:
                new_width = max_dimension
                new_height = int((max_dimension / width) * height)
            else:
                new_height = max_dimension
                new_width = int((max_dimension / height) * width)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            img.save(image_path)
            print(f"Resized {image_path} to {new_width}x{new_height}")

# Function to process a single image
def process_image(args):
    api_keys, image_path = args
    current_api_index = 0

    if os.path.getsize(image_path) < 200 * 1024:  # Skip files under 200KB
        print(f"Skipping {image_path}, size under 200KB")
        return

    resize_image(image_path)  # Resize if needed

    # Try to compress the image with available API keys
    while current_api_index < len(api_keys):
        try:
            compress_image(api_keys[current_api_index], image_path)
            break
        except Exception as e:
            print(f"Error with API key {current_api_index}: {e}")
            current_api_index += 1
            if current_api_index >= len(api_keys):
                print("No more API keys available")
                return

# Function to process images in a directory recursively
def process_directory(directory):
    api_keys = load_api_keys()
    image_paths = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('png', 'jpg', 'jpeg')):
                file_path = os.path.join(root, file)
                image_paths.append((api_keys, file_path))

    # Use multiprocessing to process images concurrently
    with Pool(cpu_count()) as pool:
        pool.map(process_image, image_paths)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python compress_images.py <directory>")
        sys.exit(1)

    directory = sys.argv[1]
    process_directory(directory)