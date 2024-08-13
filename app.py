from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_socketio import SocketIO, emit
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import fitz
import re
import os
import time
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
socketio = SocketIO(app)

UPLOAD_FOLDER = 'resources/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
INDEX_FILE_PATH = 'resources/index.json'
FORUM_FILE_PATH = 'data/traibleKnowledge/tkData.json'
ALLOWED_EXTENSIONS = {'pdf'}

PDF_FILE_PATH = INDEX_FILE_PATH

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_sentences(page_num, text):
    sentences = re.split(r'(?<!\w.\w.)(?<![A-Z][a-z].)(?<=\.|\?)\s', text)
    return [{'Page Number': page_num + 1, 'Sentence': sentence} for sentence in sentences]

def preprocess_pdf(pdf_file, title):
    index = []
    try:
        pdf_document = fitz.open(pdf_file)
        total_pages = len(pdf_document)
        with ProcessPoolExecutor() as executor:
            futures = []
            for page_num in tqdm(range(total_pages), desc="Preprocessing PDF", unit="page"):
                future = executor.submit(extract_sentences, page_num, pdf_document.load_page(page_num).get_text("text"))
                futures.append(future)
                socketio.emit('progress', {'progress': (page_num + 1) / total_pages * 100})

            for future in as_completed(futures):
                index.extend(future.result())
        index.sort(key=lambda x: x['Page Number'])
    except Exception as e:
        print(f"An error occurred during preprocessing: {e}")
    return {title: index}

def is_pdf_already_uploaded(filename, index_file_path=INDEX_FILE_PATH):
    """Check if a PDF with the given filename is already in the index."""
    index = load_index_from_file(index_file_path)
    # Check if the filename exists in any branch of the index
    return filename in index


def save_index_to_file(index, filename):
    with open(filename, 'w') as file:
        json.dump(index, file, indent=4)

def load_index_from_file(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            return json.load(file)
    return {}

def load_forum_data():
    if os.path.exists(FORUM_FILE_PATH):
        with open(FORUM_FILE_PATH, 'r') as f:
            return json.load(f)
    else:
        return []


def is_index_file_empty(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            data = file.read().strip()
            return data == "" or data == "{}"
    return True

def search_keywords_in_index(index, keywords):
    all_data = []
    for title, entries in index.items():
        for entry in entries:
            for keyword in keywords:
                if keyword.lower() in entry['Sentence'].lower():
                    bold_keyword_in_sentence = re.sub(f"(?i)({re.escape(keyword)})", r"<b>\1</b>", entry['Sentence'], flags=re.IGNORECASE)
                    all_data.append({'Keyword': keyword, 'Page Number': entry['Page Number'], 'Sentence': bold_keyword_in_sentence, 'Title': title})
    return all_data

def search_keywords_in_tkdata(tkdata, keywords):
    results = []
    for entry in tkdata:
        for keyword in keywords:
            if keyword.lower() in entry['Problem Description'].lower() or keyword.lower() in entry['Solution'].lower():
                results.append({
                    'Name': entry['Name'],
                    'Keyword': keyword,
                    'Problem Description': re.sub(f"(?i)({re.escape(keyword)})", r"<b>\1</b>", entry['Problem Description'], flags=re.IGNORECASE),
                    'Solution': re.sub(f"(?i)({re.escape(keyword)})", r"<b>\1</b>", entry['Solution'], flags=re.IGNORECASE),
                    'Chapter': entry['Chapter'],
                    'Chapter Page': entry['Chapter Page']
                })
    return results

def search_keywords_in_pdf(pdf_file, keywords, title_filter=None):
    if not os.path.isfile(pdf_file):
        print("No such file:", os.path.basename(pdf_file))
        return [], 0.0

    start_time = time.time()

    if os.path.isfile(INDEX_FILE_PATH):
        index = load_index_from_file(INDEX_FILE_PATH)
    else:
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

def find_pdf_path(pdf_title, directory='resources/uploads'):
        # Ensure the title ends with '.pdf'
        if not pdf_title.lower().endswith('.pdf'):
            raise ValueError("The provided title must include the '.pdf' extension")
        
        # Construct the full path for the directory
        search_directory = os.path.abspath(directory)
        
        # Check if the directory exists
        if not os.path.isdir(search_directory):
            raise FileNotFoundError(f"The directory '{search_directory}' does not exist")
        
        # Search for the PDF file in the directory
        for root, dirs, files in os.walk(search_directory):
            if pdf_title in files:
                # Return the full path of the found PDF file
                return os.path.join(root, pdf_title)
        
        # Return None if the PDF file was not found
        return None

@app.route('/get_toc')
def get_toc():
    toc = extract_toc(PDF_FILE_PATH)
    return jsonify(toc)

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

@app.route('/')
def index():
    index_empty = is_index_file_empty(INDEX_FILE_PATH)
    pdf_path_set = PDF_FILE_PATH is not None
    pdf_titles = [title for title in load_index_from_file(INDEX_FILE_PATH).keys()]
    if not index_empty and pdf_path_set:
        return render_template('index.html', show_upload_modal=False, pdf_titles=pdf_titles)
    else:
        return render_template('index.html', show_upload_modal=True, pdf_titles=pdf_titles)


@app.route('/upload_prompt')
def upload_prompt():
    return render_template('upload_prompt.html')

@app.route('/search', methods=['POST'])
def search():
    if is_index_file_empty(INDEX_FILE_PATH):
        return jsonify({'error': 'Index is empty. Please upload a PDF to search through.'}), 400

    if PDF_FILE_PATH is None:
        return jsonify({'error': 'No PDF file has been uploaded. Please upload a PDF to search through.'}), 400

    data = request.get_json()
    keywords = data['keywords']
    pdf_title = data.get('pdf_title')  # New parameter for PDF title

    tk_data = search_keywords_in_tkdata(load_forum_data(), keywords)
    pdf_data, duration = search_keywords_in_pdf(PDF_FILE_PATH, keywords, pdf_title)  # Pass pdf_title

    response = {
        'results': {
            'tkData': tk_data,
            'pdfData': pdf_data
        },
        'duration': duration,
        'num_results': len(tk_data) + len(pdf_data)
    }
    return jsonify(response)

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

@app.route('/forum')
def forum():
    return render_template('forum.html')

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
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        global PDF_FILE_PATH
        PDF_FILE_PATH = file_path  # Ensure this is set correctly

        # Load existing index
        index = load_index_from_file(INDEX_FILE_PATH)

        # Preprocess the uploaded PDF
        new_index = preprocess_pdf(PDF_FILE_PATH, title=filename)

        # Merge the new index with the existing index
        index.update(new_index)

        # Save the merged index back to the file
        save_index_to_file(index, INDEX_FILE_PATH)

        # Emit socket event to update the PDF title dropdown
        socketio.emit('update_pdf_titles', list(index.keys()))

        return redirect(url_for('index'))
    else:
        return 'File not allowed', 400


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    socketio.run(app, debug=True)