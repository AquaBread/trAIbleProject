from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_socketio import SocketIO, emit
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import fitz  # PyMuPDF for PDF processing
import re
import os
import time
import json
from werkzeug.utils import secure_filename
import requests

# Initialize Flask app and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

# Ollama API endpoint
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Configuration
UPLOAD_FOLDER = 'resources/uploads'
INDEX_FILE_PATH = 'resources/index.json'
FORUM_FILE_PATH = 'data/traibleKnowledge/tkData.json'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Global variable to store the current PDF file path
PDF_FILE_PATH = INDEX_FILE_PATH

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

""" Helper Functions """
# Check if the uploaded file has an allowed extension.
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Split the text into sentences and associate them with the page number.
def extract_sentences(page_num, text):
    sentences = re.split(r'(?<!\w.\w.)(?<![A-Z][a-z].)(?<=\.|\?)\s', text)
    return [{'Page Number': page_num + 1, 'Sentence': sentence} for sentence in sentences]

# Process the PDF file to extract sentences from each page and build an index.
def preprocess_pdf(pdf_file, title):
    index = []
    try:
        pdf_document = fitz.open(pdf_file)
        total_pages = len(pdf_document)
        with ProcessPoolExecutor() as executor:
            futures = []
            for page_num in tqdm(range(total_pages), desc="Preprocessing PDF", unit="page"):
                # Extract text from each page and submit to the executor
                page_text = pdf_document.load_page(page_num).get_text("text")
                future = executor.submit(extract_sentences, page_num, page_text)
                futures.append(future)
                
                # Emit progress to the client
                socketio.emit('progress', {'progress': (page_num + 1) / total_pages * 100})

            # Collect results as they complete
            for future in as_completed(futures):
                index.extend(future.result())
        
        # Sort the index by page number
        index.sort(key=lambda x: x['Page Number'])
    except Exception as e:
        print(f"An error occurred during preprocessing: {e}")
    return {title: index}

# Check if a PDF with the given filename is already in the index.
def is_pdf_already_uploaded(filename, index_file_path=INDEX_FILE_PATH):
    index = load_index_from_file(index_file_path)
    return filename in index

# Save the index dictionary to a JSON file.
def save_index_to_file(index, filename):
    with open(filename, 'w') as file:
        json.dump(index, file, indent=4)

# Load the index from a JSON file. Return an empty dict if the file doesn't exist.
def load_index_from_file(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            return json.load(file)
    return {}

# Load forum data from a JSON file. Return an empty list if the file doesn't exist.
def load_forum_data():
    if os.path.exists(FORUM_FILE_PATH):
        with open(FORUM_FILE_PATH, 'r') as f:
            return json.load(f)
    else:
        return []

# Check if the index file is empty or contains an empty JSON object.
def is_index_file_empty(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            data = file.read().strip()
            return data == "" or data == "{}"
    return True

# Search for keywords within the indexed PDF data.
def search_keywords_in_index(index, keywords):
    all_data = []
    for title, entries in index.items():
        for entry in entries:
            for keyword in keywords:
                if keyword.lower() in entry['Sentence'].lower():
                    # Highlight the keyword in the sentence
                    bold_keyword_in_sentence = re.sub(
                        f"(?i)({re.escape(keyword)})", 
                        r"<b>\1</b>", 
                        entry['Sentence'], 
                        flags=re.IGNORECASE
                    )
                    all_data.append({
                        'Keyword': keyword, 
                        'Page Number': entry['Page Number'], 
                        'Sentence': bold_keyword_in_sentence, 
                        'Title': title
                    })
    return all_data

# Search for keywords within the Traible Knowledge forum data.
def search_keywords_in_tkdata(tkdata, keywords):
    results = []
    for entry in tkdata:
        for keyword in keywords:
            if (keyword.lower() in entry['Problem Description'].lower() or 
                keyword.lower() in entry['Solution'].lower()):
                # Highlight the keyword in the descriptions
                highlighted_problem = re.sub(
                    f"(?i)({re.escape(keyword)})", 
                    r"<b>\1</b>", 
                    entry['Problem Description'], 
                    flags=re.IGNORECASE
                )
                highlighted_solution = re.sub(
                    f"(?i)({re.escape(keyword)})", 
                    r"<b>\1</b>", 
                    entry['Solution'], 
                    flags=re.IGNORECASE
                )
                results.append({
                    'Name': entry['Name'],
                    'Keyword': keyword,
                    'Problem Description': highlighted_problem,
                    'Solution': highlighted_solution,
                    'Chapter': entry['Chapter'],
                    'Chapter Page': entry['Chapter Page']
                })
    return results

# Search for keywords in the PDF index and measure the search duration.
def search_keywords_in_pdf(pdf_file, keywords, title_filter=None):
    if not os.path.isfile(pdf_file):
        print("No such file:", os.path.basename(pdf_file))
        return [], 0.0

    start_time = time.time()

    if os.path.isfile(INDEX_FILE_PATH):
        index = load_index_from_file(INDEX_FILE_PATH)
    else:
        # Preprocess the PDF if the index doesn't exist
        index = preprocess_pdf(pdf_file, title=os.path.basename(pdf_file))
        save_index_to_file(index, INDEX_FILE_PATH)

    found_data = []
    for title, entries in index.items():
        if title_filter and title != title_filter:
            continue
        found_data.extend(search_keywords_in_index({title: entries}, keywords))

    end_time = time.time()
    duration = end_time - start_time
    return found_data, duration

# Save a new forum entry to the forum data JSON file.
def save_forum_data(name, problem_description, solution, chapter_name, chapter_page):
    forum_data = {
        'Name': name,
        'Problem Description': problem_description,
        'Solution': solution,
        'Chapter': chapter_name,
        'Chapter Page': chapter_page
    }
    forum_list = load_forum_data()
    forum_list.append(forum_data)
    with open(FORUM_FILE_PATH, 'w') as f:
        json.dump(forum_list, f, indent=4)

# Extract the table of contents (TOC) from the PDF.
def extract_toc(pdf_file):
    toc = []
    try:
        pdf_document = fitz.open(pdf_file)
        toc_data = pdf_document.get_toc()
        for item in toc_data:
            level, title, page = item
            if re.match(r'^\d+\s', title) or re.match(r'^\d+[^.\d]', title):
                toc.append({'Chapter': level, 'Title': title, 'Page': page})
    except Exception as e:
        print(f"An error occurred while extracting TOC: {e}")
    return toc

# Find the full path of a PDF file given its title within a directory.
def find_pdf_path(pdf_title, directory='resources/uploads'):
    # Ensure the title ends with '.pdf'
    if not pdf_title.lower().endswith('.pdf'):
        raise ValueError("The provided title must include the '.pdf' extension")
    
    search_directory = os.path.abspath(directory)
    
    # Check if the directory exists
    if not os.path.isdir(search_directory):
        raise FileNotFoundError(f"The directory '{search_directory}' does not exist")
    
    # Search for the PDF file in the directory
    for root, dirs, files in os.walk(search_directory):
        if pdf_title in files:
            return os.path.join(root, pdf_title)
    
    return None

""" Route Definitions """
# Render the main index page. Show upload modal if the index is empty or no PDF is set.
@app.route('/')
def index():
    index_empty = is_index_file_empty(INDEX_FILE_PATH)
    pdf_path_set = PDF_FILE_PATH is not None
    pdf_titles = list(load_index_from_file(INDEX_FILE_PATH).keys())
    if not index_empty and pdf_path_set:
        return render_template('index.html', show_upload_modal=False, pdf_titles=pdf_titles)
    else:
        return render_template('index.html', show_upload_modal=True, pdf_titles=pdf_titles)

# Render the upload prompt page.
@app.route('/upload_prompt')
def upload_prompt():
    return render_template('upload_prompt.html')

# Handle file upload. Save the file, preprocess it, and update the index.
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        # Check if the PDF is already uploaded
        if is_pdf_already_uploaded(filename):
            return jsonify({'error': 'This PDF has already been uploaded.'}), 400
        
        # Save the uploaded file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        global PDF_FILE_PATH
        PDF_FILE_PATH = file_path  # Update the global PDF file path

        # Load existing index and preprocess the new PDF
        index = load_index_from_file(INDEX_FILE_PATH)
        new_index = preprocess_pdf(PDF_FILE_PATH, title=filename)
        index.update(new_index)

        # Save the updated index
        save_index_to_file(index, INDEX_FILE_PATH)

        # Emit an event to update PDF titles on the client side
        socketio.emit('update_pdf_titles', list(index.keys()))

        return redirect(url_for('index'))
    else:
        return 'File not allowed', 400

# Handle removal of a PDF file. Update the index and delete the file from the server.
@app.route('/remove_file', methods=['POST'])
def remove_file():
    try:
        data = request.json
        file_to_remove = data['file_name']

        # Load the current index
        index = load_index_from_file(INDEX_FILE_PATH)

        # Check if the file exists in the index
        if file_to_remove not in index:
            return jsonify({'error': 'File not found in index.'}), 404

        # Remove the file from the index
        del index[file_to_remove]

        # Save the updated index
        save_index_to_file(index, INDEX_FILE_PATH)

        # Delete the actual PDF file from the uploads folder
        file_path = find_pdf_path(file_to_remove)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # Emit an event to update PDF titles on the client side
        socketio.emit('update_pdf_titles', list(index.keys()))

        return jsonify({'message': f'File "{file_to_remove}" removed successfully.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Provide the table of contents (TOC) of the current PDF as JSON.
@app.route('/get_toc')
def get_toc():
    toc = extract_toc(PDF_FILE_PATH)
    return jsonify(toc)

# Render the forum page.
@app.route('/forum')
def forum():
    return render_template('forum.html')

# Handle submission of a new problem and solution to the forum.
@app.route('/submit_problem', methods=['POST'])
def submit_problem():
    try:
        data = request.json
        name = data['name']
        problem_description = data['problem-description']
        solution = data['solution']
        chapter_name = data['chapter-name']
        chapter_page = data['chapter-page']

        save_forum_data(name, problem_description, solution, chapter_name, chapter_page)
        return jsonify({'message': 'Data submitted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Handle search requests. Search both the forum data and the PDF index for keywords.
@app.route('/search', methods=['POST'])
def search():
    if is_index_file_empty(INDEX_FILE_PATH):
        return jsonify({'error': 'Index is empty. Please upload a PDF to search through.'}), 400

    if PDF_FILE_PATH is None:
        return jsonify({'error': 'No PDF file has been uploaded. Please upload a PDF to search through.'}), 400

    data = request.get_json()
    #keywords = data['keywords']
    keywords = data.get('keywords', [])
    pdf_title = data.get('pdf_title')  # Optional filter for a specific PDF

    # Search in forum data
    tk_data = search_keywords_in_tkdata(load_forum_data(), keywords)
    
    # Search in PDF index
    pdf_data, duration = search_keywords_in_pdf(PDF_FILE_PATH, keywords, pdf_title)

    response = {
        'results': {
            'tkData': tk_data,
            'pdfData': pdf_data
        },
        'duration': duration,
        'num_results': len(tk_data) + len(pdf_data)
    }
    return jsonify(response)

# Serve the PDF file to the client. Optionally, navigate to a specific page.
@app.route('/view_pdf')
def view_pdf():
    page_number = request.args.get('page')
    pdf_title = request.args.get('title')
    
    if not pdf_title:
        return "PDF title is required", 400

    # Find the path to the PDF
    pdf_path = find_pdf_path(pdf_title)
    
    if not pdf_path:
        return "PDF not found", 404

    # Return the PDF file
    return send_file(pdf_path)

@socketio.on('send_message')
def handle_message(data):
    user_message = data['message']
    
    # Prepare the request to Ollama
    payload = {
        "model": "llama3.2",  # AI model to generate the response
        "prompt": user_message,  # User's message is passed as the prompt
        "stream": False  # Response is not streamed; it returns the complete response
    }
    
    # Send request to Ollama API
    response = requests.post(OLLAMA_API_URL, json=payload)
    
    if response.status_code == 200:
        ai_response = response.json()['response']  # Extract the AI's response from the API response
    else:
        ai_response = "Sorry, I couldn't process that request."  # Fallback message if something goes wrong
    
    # Emit the AI's response back to the client
    emit('receive_message', {'message': ai_response})

# Run the Flask app with SocketIO
if __name__ == '__main__':
    socketio.run(app, debug=True)